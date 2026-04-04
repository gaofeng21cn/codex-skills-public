#!/usr/bin/env python3
from __future__ import annotations

import base64
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "sources.json"
DEFAULT_LOCAL_CONFIG = Path(__file__).resolve().parents[1] / "local_machine.json"


@dataclass(frozen=True)
class SourceRepo:
    repo_url: str
    ref: str


@dataclass(frozen=True)
class Mapping:
    kind: str
    source: str
    target: str
    target_base: Path | None = None


@dataclass(frozen=True)
class ManagedItem:
    name: str
    kind: str
    local_path: Path
    managed_path: Path | None = None
    source: SourceRepo | None = None
    mappings: tuple[Mapping, ...] = ()
    remote: str = "origin"
    branch: str = "main"

    @property
    def target_path(self) -> Path:
        return self.managed_path if self.managed_path is not None else self.local_path


@dataclass(frozen=True)
class LocalMachineConfig:
    github_overlay_transport: str = "git_clone"
    github_git_repo_transport: str = "git_fetch"
    ssh_strict_host_key_checking: str = "accept-new"
    ssh_connect_timeout_seconds: int = 15


@dataclass
class RepoCheckoutStore:
    temp_root: Path
    checkouts: dict[tuple[str, str], Path] = field(default_factory=dict)
    github_commits: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    github_trees: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    github_blobs: dict[tuple[str, str, str], bytes] = field(default_factory=dict)

    def checkout(self, source: SourceRepo) -> Path:
        key = (source.repo_url, source.ref)
        existing = self.checkouts.get(key)
        if existing is not None:
            return existing
        target = self.temp_root / str(len(self.checkouts))
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                source.ref,
                source.repo_url,
                str(target),
            ]
        )
        self.checkouts[key] = target
        return target

    def github_commit(self, source: SourceRepo) -> dict[str, object]:
        repo = parse_github_repo(source.repo_url)
        if repo is None:
            raise ValueError(f"unsupported GitHub source: {source.repo_url}")
        key = (repo[0] + "/" + repo[1], source.ref)
        existing = self.github_commits.get(key)
        if existing is not None:
            return existing
        payload = gh_api_json(f"repos/{repo[0]}/{repo[1]}/commits/{source.ref}")
        self.github_commits[key] = payload
        return payload

    def github_tree(self, source: SourceRepo) -> dict[str, str]:
        repo = parse_github_repo(source.repo_url)
        if repo is None:
            raise ValueError(f"unsupported GitHub source: {source.repo_url}")
        key = (repo[0] + "/" + repo[1], source.ref)
        existing = self.github_trees.get(key)
        if existing is not None:
            return existing
        commit = self.github_commit(source)
        tree_sha = commit["commit"]["tree"]["sha"]
        payload = gh_api_json(f"repos/{repo[0]}/{repo[1]}/git/trees/{tree_sha}?recursive=1")
        blobs = {
            node["path"]: node["sha"]
            for node in payload["tree"]
            if node["type"] == "blob"
        }
        self.github_trees[key] = blobs
        return blobs

    def github_blob(self, source: SourceRepo, sha: str) -> bytes:
        repo = parse_github_repo(source.repo_url)
        if repo is None:
            raise ValueError(f"unsupported GitHub source: {source.repo_url}")
        key = (repo[0], repo[1], sha)
        existing = self.github_blobs.get(key)
        if existing is not None:
            return existing
        payload = gh_api_json(f"repos/{repo[0]}/{repo[1]}/git/blobs/{sha}")
        content = base64.b64decode(payload["content"])
        self.github_blobs[key] = content
        return content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and upgrade managed Codex skills.")
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_MANIFEST),
        help="Path to the managed sources manifest.",
    )
    parser.add_argument(
        "--local-config",
        default=str(DEFAULT_LOCAL_CONFIG),
        help="Path to the local machine configuration file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("inspect", "upgrade"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--only", action="append", default=[], help="Limit to selected managed item names.")

    return parser.parse_args()


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def try_run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def load_manifest(path: Path) -> list[ManagedItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[ManagedItem] = []
    for raw in data["items"]:
        kind = raw["kind"]
        local_path = Path(raw["local_path"]).expanduser()
        managed_path = Path(raw.get("managed_path", raw["local_path"])).expanduser().resolve(strict=False)
        source = None
        mappings: tuple[Mapping, ...] = ()
        if kind == "overlay_sync":
            source_raw = raw["source"]
            source = SourceRepo(repo_url=source_raw["repo_url"], ref=source_raw["ref"])
            mappings = tuple(
                Mapping(
                    kind=mapping["kind"],
                    source=mapping["source"],
                    target=mapping["target"],
                    target_base=Path(mapping["target_base"]).expanduser().resolve(strict=False)
                    if "target_base" in mapping
                    else None,
                )
                for mapping in raw["mappings"]
            )
        items.append(
            ManagedItem(
                name=raw["name"],
                kind=kind,
                local_path=local_path,
                managed_path=managed_path,
                source=source,
                mappings=mappings,
                remote=raw.get("remote", "origin"),
                branch=raw.get("branch", "main"),
            )
        )
    return items


def load_local_machine_config(path: Path) -> LocalMachineConfig:
    if not path.exists():
        return LocalMachineConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    github = data.get("github", {})
    return LocalMachineConfig(
        github_overlay_transport=github.get("overlay_transport", "git_clone"),
        github_git_repo_transport=github.get("git_repo_transport", "git_fetch"),
        ssh_strict_host_key_checking=github.get("ssh_strict_host_key_checking", "accept-new"),
        ssh_connect_timeout_seconds=github.get("ssh_connect_timeout_seconds", 15),
    )


def select_items(items: list[ManagedItem], selected: list[str]) -> list[ManagedItem]:
    if not selected:
        return items
    wanted = set(selected)
    chosen = [item for item in items if item.name in wanted]
    missing = sorted(wanted - {item.name for item in chosen})
    if missing:
        raise ValueError(f"unknown managed item(s): {', '.join(missing)}")
    return chosen


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_oid_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def git_blob_oid_file(path: Path) -> str:
    return git_blob_oid_bytes(path.read_bytes())


def snapshot_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if ".git" in rel.parts:
            continue
        snapshot[rel.as_posix()] = sha256_file(path)
    return snapshot


def snapshot_tree_git_blob_oids(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if ".git" in rel.parts:
            continue
        snapshot[rel.as_posix()] = git_blob_oid_file(path)
    return snapshot


def compare_snapshots(local_snapshot: dict[str, str], expected_snapshot: dict[str, str]) -> dict[str, object]:
    only_local = sorted(local_snapshot.keys() - expected_snapshot.keys())
    only_expected = sorted(expected_snapshot.keys() - local_snapshot.keys())
    changed = sorted(
        rel
        for rel in (local_snapshot.keys() & expected_snapshot.keys())
        if local_snapshot[rel] != expected_snapshot[rel]
    )
    return {
        "match": not only_local and not only_expected and not changed,
        "only_local": only_local,
        "only_expected": only_expected,
        "changed": changed,
        "local_file_count": len(local_snapshot),
        "expected_file_count": len(expected_snapshot),
    }


def compare_trees(local_root: Path, expected_root: Path) -> dict[str, object]:
    local_snapshot = snapshot_tree(local_root)
    expected_snapshot = snapshot_tree(expected_root)
    return compare_snapshots(local_snapshot, expected_snapshot)


def git_repo_root(path: Path) -> Path | None:
    result = try_run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def git_subtree_dirty(path: Path) -> bool:
    repo_root = git_repo_root(path)
    if repo_root is None:
        return False

    resolved_root = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    rel_path = resolved_path.relative_to(resolved_root)
    pathspec = "." if rel_path == Path(".") else rel_path.as_posix()
    result = try_run(
        ["git", "-C", str(repo_root), "status", "--short", "--untracked-files=all", "--", pathspec]
    )
    return bool(result.stdout.strip())


def result_paths(item: ManagedItem) -> dict[str, str]:
    payload = {"local_path": str(item.local_path)}
    if item.target_path != item.local_path:
        payload["managed_path"] = str(item.target_path)
    return payload


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path) -> None:
    ensure_parent(dest)
    shutil.copy2(src, dest)


def copy_dir_contents(src_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for child in sorted(src_dir.iterdir()):
        dest_child = dest_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest_child, dirs_exist_ok=True)
        else:
            copy_file(child, dest_child)


def build_overlay_stage(item: ManagedItem, checkout_root: Path, stage_root: Path) -> None:
    build_overlay_stage_for_mappings(item, item.mappings, checkout_root, stage_root)


def build_overlay_stage_for_mappings(
    item: ManagedItem,
    mappings: tuple[Mapping, ...] | list[Mapping],
    checkout_root: Path,
    stage_root: Path,
) -> None:
    stage_root.mkdir(parents=True, exist_ok=True)
    for mapping in mappings:
        source_path = checkout_root / mapping.source
        target_path = stage_root / mapping.target
        if mapping.kind == "file":
            if not source_path.is_file():
                raise FileNotFoundError(f"missing source file for {item.name}: {source_path}")
            copy_file(source_path, target_path)
            continue
        if mapping.kind == "dir_contents":
            if not source_path.is_dir():
                raise FileNotFoundError(f"missing source directory for {item.name}: {source_path}")
            copy_dir_contents(source_path, target_path)
            continue
        raise ValueError(f"unsupported mapping kind: {mapping.kind}")


def mapping_target_base(item: ManagedItem, mapping: Mapping) -> Path:
    return mapping.target_base if mapping.target_base is not None else item.target_path


def build_overlay_stages(item: ManagedItem, checkout_root: Path, stage_root: Path) -> dict[Path, Path]:
    grouped_mappings: dict[Path, list[Mapping]] = {}
    for mapping in item.mappings:
        grouped_mappings.setdefault(mapping_target_base(item, mapping), []).append(mapping)

    stages: dict[Path, Path] = {}
    for index, (target_base, mappings) in enumerate(grouped_mappings.items()):
        target_stage_root = stage_root / str(index)
        build_overlay_stage_for_mappings(item, mappings, checkout_root, target_stage_root)
        stages[target_base] = target_stage_root
    return stages


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted((node for node in root.rglob("*") if node.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            continue


def sync_tree_exact(stage_root: Path, local_root: Path) -> None:
    local_root.mkdir(parents=True, exist_ok=True)

    expected_entries = {path.relative_to(stage_root).as_posix() for path in stage_root.rglob("*")}
    local_entries = {path.relative_to(local_root).as_posix() for path in local_root.rglob("*")}

    for rel in sorted(local_entries - expected_entries, reverse=True):
        remove_path(local_root / rel)

    for path in sorted(stage_root.rglob("*")):
        rel = path.relative_to(stage_root)
        target = local_root / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        copy_file(path, target)


def sync_snapshot_exact(
    local_root: Path,
    expected_snapshot: dict[str, str],
    content_loader: Callable[[str], bytes],
) -> None:
    local_root.mkdir(parents=True, exist_ok=True)
    local_snapshot = snapshot_tree_git_blob_oids(local_root)

    for rel in sorted(local_snapshot.keys() - expected_snapshot.keys(), reverse=True):
        remove_path(local_root / rel)

    for rel in sorted(expected_snapshot.keys()):
        target = local_root / rel
        expected_oid = expected_snapshot[rel]
        current_oid = local_snapshot.get(rel)
        if current_oid == expected_oid:
            continue
        ensure_parent(target)
        target.write_bytes(content_loader(expected_oid))

    prune_empty_dirs(local_root)


def parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    if repo_url.startswith("git@github.com:"):
        path = repo_url.split(":", 1)[1]
    else:
        parsed = urlparse(repo_url)
        if parsed.netloc != "github.com":
            return None
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    owner, _, repo = path.partition("/")
    if not owner or not repo:
        return None
    return owner, repo


def github_ssh_url(owner: str, repo: str) -> str:
    return f"git@github.com:{owner}/{repo}.git"


def gh_api_json(path: str) -> dict[str, object] | list[object]:
    output = run(["gh", "api", path])
    return json.loads(output)


def git_ssh_env(config: LocalMachineConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        "ssh "
        f"-o StrictHostKeyChecking={config.ssh_strict_host_key_checking} "
        f"-o ConnectTimeout={config.ssh_connect_timeout_seconds}"
    )
    return env


def resolve_overlay_snapshot(
    mappings: tuple[Mapping, ...] | list[Mapping],
    blob_paths: dict[str, str],
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for mapping in mappings:
        if mapping.kind == "file":
            expected[mapping.target] = blob_paths[mapping.source]
            continue
        if mapping.kind != "dir_contents":
            raise ValueError(f"unsupported mapping kind: {mapping.kind}")
        source_root = mapping.source.rstrip("/")
        target_root = "" if mapping.target == "." else mapping.target.rstrip("/")
        for path, oid in sorted(blob_paths.items()):
            if source_root == ".":
                rel = path
            else:
                prefix = f"{source_root}/"
                if not path.startswith(prefix):
                    continue
                rel = path[len(prefix):]
            target = rel if not target_root else f"{target_root}/{rel}"
            expected[target] = oid
    return expected


def resolve_overlay_snapshots(item: ManagedItem, blob_paths: dict[str, str]) -> dict[Path, dict[str, str]]:
    grouped_mappings: dict[Path, list[Mapping]] = {}
    for mapping in item.mappings:
        grouped_mappings.setdefault(mapping_target_base(item, mapping), []).append(mapping)
    return {
        target_base: resolve_overlay_snapshot(mappings, blob_paths)
        for target_base, mappings in grouped_mappings.items()
    }


def should_use_github_overlay_api(item: ManagedItem, config: LocalMachineConfig) -> bool:
    if item.source is None:
        return False
    if config.github_overlay_transport != "gh_api":
        return False
    return parse_github_repo(item.source.repo_url) is not None


def inspect_git_repo(item: ManagedItem, config: LocalMachineConfig | None = None) -> dict[str, object]:
    resolved_config = config or LocalMachineConfig()
    repo_path = item.target_path
    remote_url = run(["git", "-C", str(repo_path), "remote", "get-url", item.remote])
    github_repo = parse_github_repo(remote_url)
    upstream_ref = f"{item.remote}/{item.branch}"

    if github_repo is not None and resolved_config.github_git_repo_transport == "ssh_fetch":
        ssh_url = github_ssh_url(github_repo[0], github_repo[1])
        run(
            ["git", "-C", str(repo_path), "fetch", ssh_url, item.branch],
            env=git_ssh_env(resolved_config),
        )
        upstream_ref = "FETCH_HEAD"
    else:
        run(["git", "-C", str(repo_path), "fetch", "--all", "--prune"])

    local_head = run(["git", "-C", str(repo_path), "rev-parse", "HEAD"])
    upstream_head = run(["git", "-C", str(repo_path), "rev-parse", upstream_ref])
    merge_base = run(["git", "-C", str(repo_path), "merge-base", "HEAD", upstream_ref])
    dirty = bool(run(["git", "-C", str(repo_path), "status", "--short"]))

    if local_head == upstream_head:
        local_state = "dirty-current" if dirty else "current"
        action = "none"
    elif local_head == merge_base:
        local_state = "behind-dirty" if dirty else "behind"
        action = "none" if dirty else "upgrade"
    elif upstream_head == merge_base:
        local_state = "ahead-dirty" if dirty else "ahead"
        action = "none"
    else:
        local_state = "diverged"
        action = "none"

    return {
        "name": item.name,
        "kind": item.kind,
        **result_paths(item),
        "source": {
            "remote": item.remote,
            "branch": item.branch,
        },
        "local_state": local_state,
        "action": action,
        "local_head": local_head,
        "remote_head": upstream_head,
        "merge_base": merge_base,
        "dirty": dirty,
        "changed": False,
    }


def inspect_overlay_sync(
    item: ManagedItem,
    store: RepoCheckoutStore,
    config: LocalMachineConfig | None = None,
) -> dict[str, object]:
    resolved_config = config or LocalMachineConfig()
    assert item.source is not None
    if should_use_github_overlay_api(item, resolved_config):
        destinations = []
        for target_base, expected_snapshot in resolve_overlay_snapshots(item, store.github_tree(item.source)).items():
            diff = compare_snapshots(snapshot_tree_git_blob_oids(target_base), expected_snapshot)
            dirty = git_subtree_dirty(target_base)
            destinations.append(
                {
                    "target_base": str(target_base),
                    "diff": diff,
                    "dirty": dirty,
                }
            )
        match = all(destination["diff"]["match"] for destination in destinations)
        dirty = any(destination["dirty"] for destination in destinations)
        if match:
            local_state = "dirty-current" if dirty else "current"
        else:
            local_state = "different-dirty" if dirty else "different"
        result = {
            "name": item.name,
            "kind": item.kind,
            **result_paths(item),
            "source": {
                "repo_url": item.source.repo_url,
                "ref": item.source.ref,
                "transport": "gh_api",
            },
            "local_state": local_state,
            "action": "none" if match or dirty else "upgrade",
            "destinations": destinations,
            "changed": False,
        }
        if len(destinations) == 1:
            result["diff"] = destinations[0]["diff"]
        return result

    checkout_root = store.checkout(item.source)
    with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
        stage_root = Path(temp_dir) / "stage"
        stages = build_overlay_stages(item, checkout_root, stage_root)
        destinations = []
        for target_base, target_stage_root in stages.items():
            diff = compare_trees(target_base, target_stage_root)
            dirty = git_subtree_dirty(target_base)
            destinations.append(
                {
                    "target_base": str(target_base),
                    "diff": diff,
                    "dirty": dirty,
                }
            )
    match = all(destination["diff"]["match"] for destination in destinations)
    dirty = any(destination["dirty"] for destination in destinations)
    if match:
        local_state = "dirty-current" if dirty else "current"
    else:
        local_state = "different-dirty" if dirty else "different"
    result = {
        "name": item.name,
        "kind": item.kind,
        **result_paths(item),
        "source": {
            "repo_url": item.source.repo_url,
            "ref": item.source.ref,
            "transport": "git_clone",
        },
        "local_state": local_state,
        "action": "none" if match or dirty else "upgrade",
        "destinations": destinations,
        "changed": False,
    }
    if len(destinations) == 1:
        result["diff"] = destinations[0]["diff"]
    return result


def upgrade_git_repo(item: ManagedItem, config: LocalMachineConfig | None = None) -> dict[str, object]:
    resolved_config = config or LocalMachineConfig()
    result = inspect_git_repo(item, resolved_config)
    if result["action"] == "upgrade":
        repo_path = item.target_path
        remote_url = run(["git", "-C", str(repo_path), "remote", "get-url", item.remote])
        github_repo = parse_github_repo(remote_url)
        if github_repo is not None and resolved_config.github_git_repo_transport == "ssh_fetch":
            ssh_url = github_ssh_url(github_repo[0], github_repo[1])
            run(
                ["git", "-C", str(repo_path), "fetch", ssh_url, item.branch],
                env=git_ssh_env(resolved_config),
            )
            run(["git", "-C", str(repo_path), "merge", "--ff-only", "FETCH_HEAD"])
        else:
            run(["git", "-C", str(repo_path), "pull", "--ff-only", item.remote, item.branch])
        result = inspect_git_repo(item, resolved_config)
        result["changed"] = True
    return result


def upgrade_overlay_sync(
    item: ManagedItem,
    store: RepoCheckoutStore,
    config: LocalMachineConfig | None = None,
) -> dict[str, object]:
    resolved_config = config or LocalMachineConfig()
    inspected = inspect_overlay_sync(item, store, resolved_config)
    if inspected["action"] != "upgrade":
        return inspected

    assert item.source is not None
    if should_use_github_overlay_api(item, resolved_config):
        for target_base, expected_snapshot in resolve_overlay_snapshots(item, store.github_tree(item.source)).items():
            sync_snapshot_exact(
                target_base,
                expected_snapshot,
                lambda oid: store.github_blob(item.source, oid),
            )
        result = inspect_overlay_sync(item, store, resolved_config)
        result["changed"] = True
        return result

    checkout_root = store.checkout(item.source)
    with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
        stage_root = Path(temp_dir) / "stage"
        stages = build_overlay_stages(item, checkout_root, stage_root)
        for target_base, target_stage_root in stages.items():
            sync_tree_exact(target_stage_root, target_base)

    result = inspect_overlay_sync(item, store, resolved_config)
    result["changed"] = True
    return result


def inspect_items(
    items: list[ManagedItem],
    config: LocalMachineConfig | None = None,
) -> list[dict[str, object]]:
    resolved_config = config or LocalMachineConfig()
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="skill-upgrader-checkouts-") as temp_dir:
        store = RepoCheckoutStore(Path(temp_dir))
        for item in items:
            if item.kind == "git_repo":
                results.append(inspect_git_repo(item, resolved_config))
                continue
            if item.kind == "overlay_sync":
                results.append(inspect_overlay_sync(item, store, resolved_config))
                continue
            raise ValueError(f"unsupported managed item kind: {item.kind}")
    return results


def upgrade_items(
    items: list[ManagedItem],
    config: LocalMachineConfig | None = None,
) -> list[dict[str, object]]:
    resolved_config = config or LocalMachineConfig()
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="skill-upgrader-checkouts-") as temp_dir:
        store = RepoCheckoutStore(Path(temp_dir))
        for item in items:
            if item.kind == "git_repo":
                results.append(upgrade_git_repo(item, resolved_config))
                continue
            if item.kind == "overlay_sync":
                results.append(upgrade_overlay_sync(item, store, resolved_config))
                continue
            raise ValueError(f"unsupported managed item kind: {item.kind}")
    return results


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.sources).expanduser().resolve()
    local_config_path = Path(args.local_config).expanduser().resolve()
    items = select_items(load_manifest(manifest_path), args.only)
    config = load_local_machine_config(local_config_path)

    if args.command == "inspect":
        payload = {
            "command": "inspect",
            "sources": str(manifest_path),
            "local_config": str(local_config_path),
            "results": inspect_items(items, config),
        }
    else:
        payload = {
            "command": "upgrade",
            "sources": str(manifest_path),
            "local_config": str(local_config_path),
            "results": upgrade_items(items, config),
        }

    print(json.dumps(payload, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
