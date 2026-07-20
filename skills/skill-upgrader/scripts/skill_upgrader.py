#!/usr/bin/env python3
from __future__ import annotations

import base64
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "sources.json"
DEFAULT_LOCAL_CONFIG = Path(__file__).resolve().parents[1] / "local_machine.json"
DEFAULT_PRIVATE_CONFIG = Path("~/.skills-manager/local_machine.private.json").expanduser().resolve(strict=False)
DEFAULT_RUNTIME_DIR = Path("~/.skills-manager/skills").expanduser().resolve(strict=False)
DEFAULT_LIBRARY_DIR = DEFAULT_RUNTIME_DIR
DEFAULT_BOOTSTRAP_BASE_DIR = Path("~/.skills-manager").expanduser().resolve(strict=False)
DEFAULT_LIBRARY_BRANCH = "main"
DEFAULT_LIBRARY_COMMIT_MESSAGE = "chore: sync skills library"


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
    frontmatter_overrides: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True)
class ManagedItem:
    name: str
    kind: str
    local_path: Path
    managed_path: Path | None = None
    source: SourceRepo | None = None
    mappings: tuple[Mapping, ...] = ()
    local_overrides: tuple[str, ...] = ()
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
    private_config_path: Path = field(default_factory=lambda: DEFAULT_PRIVATE_CONFIG)
    library_dir: Path = field(default_factory=lambda: DEFAULT_LIBRARY_DIR)
    runtime_dir: Path = field(default_factory=lambda: DEFAULT_RUNTIME_DIR)
    library_remote: str | None = None
    library_branch: str = DEFAULT_LIBRARY_BRANCH
    bootstrap_base_dir: Path = field(default_factory=lambda: DEFAULT_BOOTSTRAP_BASE_DIR)
    bootstrap_script: Path = field(
        default_factory=lambda: default_bootstrap_script_path(DEFAULT_RUNTIME_DIR)
    )


@dataclass
class RepoCheckoutStore:
    temp_root: Path
    checkouts: dict[tuple[str, str], Path] = field(default_factory=dict)
    github_commits: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    github_trees: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    github_blobs: dict[tuple[str, str, str], bytes] = field(default_factory=dict)
    synthetic_blobs: dict[str, bytes] = field(default_factory=dict)

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

    def overlay_blob(self, source: SourceRepo, sha: str) -> bytes:
        synthetic = self.synthetic_blobs.get(sha)
        return synthetic if synthetic is not None else self.github_blob(source, sha)


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
    parser.add_argument(
        "--private-config",
        default=str(DEFAULT_PRIVATE_CONFIG),
        help="Path to the private machine configuration file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("inspect", "upgrade"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--only", action="append", default=[], help="Limit to selected managed item names.")

    library_push = subparsers.add_parser("library-push")
    library_push.add_argument("--message", help="Commit message to use when the library repo is dirty.")
    library_push.add_argument("--library-dir", help="Override the Skills Manager library directory.")
    library_push.add_argument("--library-remote", help="Override the library git remote URL.")
    library_push.add_argument("--library-branch", help="Override the library git branch.")

    library_pull = subparsers.add_parser("library-pull")
    library_pull.add_argument("--skip-bootstrap", action="store_true", help="Skip Skills Manager DB bootstrap.")
    library_pull.add_argument("--library-dir", help="Override the Skills Manager library directory.")
    library_pull.add_argument("--library-remote", help="Override the library git remote URL.")
    library_pull.add_argument("--library-branch", help="Override the library git branch.")
    library_pull.add_argument("--bootstrap-base-dir", help="Override the Skills Manager base directory.")
    library_pull.add_argument("--bootstrap-script", help="Override the bootstrap script path.")

    bootstrap = subparsers.add_parser("bootstrap-manager-db")
    bootstrap.add_argument("--no-reset", action="store_true", help="Do not pass --reset to the bootstrap script.")
    bootstrap.add_argument("--bootstrap-base-dir", help="Override the Skills Manager base directory.")
    bootstrap.add_argument("--bootstrap-script", help="Override the bootstrap script path.")

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


def expand_path(path_str: str) -> Path:
    return Path(path_str).expanduser().resolve(strict=False)


def default_bootstrap_script_path(library_dir: Path) -> Path:
    return (library_dir / "maintenance" / "bootstrap_xingkongliang_db.py").resolve(strict=False)


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
            parsed_mappings: list[Mapping] = []
            for mapping in raw["mappings"]:
                frontmatter_raw = mapping.get("frontmatter_overrides", {})
                if not isinstance(frontmatter_raw, dict) or not all(
                    isinstance(key, str) and (isinstance(value, str) or value is None)
                    for key, value in frontmatter_raw.items()
                ):
                    raise ValueError(
                        f"frontmatter_overrides must be a string-or-null mapping for {raw['name']}"
                    )
                if frontmatter_raw and mapping["kind"] != "file":
                    raise ValueError(
                        f"frontmatter_overrides requires a file mapping for {raw['name']}"
                    )
                parsed_mappings.append(
                    Mapping(
                        kind=mapping["kind"],
                        source=mapping["source"],
                        target=mapping["target"],
                        target_base=Path(mapping["target_base"]).expanduser().resolve(strict=False)
                        if "target_base" in mapping
                        else None,
                        frontmatter_overrides=tuple(frontmatter_raw.items()),
                    )
                )
            mappings = tuple(parsed_mappings)
        items.append(
            ManagedItem(
                name=raw["name"],
                kind=kind,
                local_path=local_path,
                managed_path=managed_path,
                source=source,
                mappings=mappings,
                local_overrides=tuple(raw.get("local_overrides", ())),
                remote=raw.get("remote", "origin"),
                branch=raw.get("branch", "main"),
            )
        )
    return items


def load_local_machine_config(path: Path, private_path: Path | None = None) -> LocalMachineConfig:
    public_data: dict[str, object] = {}
    if path.exists():
        public_data = json.loads(path.read_text(encoding="utf-8"))
    resolved_private_path = (
        private_path.expanduser().resolve(strict=False) if private_path is not None else DEFAULT_PRIVATE_CONFIG
    )
    private_data: dict[str, object] = {}
    if resolved_private_path.exists():
        private_data = json.loads(resolved_private_path.read_text(encoding="utf-8"))

    github = public_data.get("github", {})
    public_skills_manager = public_data.get("skills_manager", {})
    private_skills_manager = private_data.get("skills_manager", {})
    merged_skills_manager = {**public_skills_manager, **private_skills_manager}
    library_dir = expand_path(merged_skills_manager.get("library_dir", str(DEFAULT_LIBRARY_DIR)))
    runtime_dir = expand_path(merged_skills_manager.get("runtime_dir", str(DEFAULT_RUNTIME_DIR)))
    bootstrap_base_dir = expand_path(
        merged_skills_manager.get("bootstrap_base_dir", str(DEFAULT_BOOTSTRAP_BASE_DIR))
    )
    bootstrap_script_raw = merged_skills_manager.get(
        "bootstrap_script",
        str(default_bootstrap_script_path(runtime_dir)),
    )
    return LocalMachineConfig(
        github_overlay_transport=github.get("overlay_transport", "git_clone"),
        github_git_repo_transport=github.get("git_repo_transport", "git_fetch"),
        ssh_strict_host_key_checking=github.get("ssh_strict_host_key_checking", "accept-new"),
        ssh_connect_timeout_seconds=github.get("ssh_connect_timeout_seconds", 15),
        private_config_path=resolved_private_path,
        library_dir=library_dir,
        runtime_dir=runtime_dir,
        library_remote=merged_skills_manager.get("library_remote"),
        library_branch=merged_skills_manager.get("library_branch", DEFAULT_LIBRARY_BRANCH),
        bootstrap_base_dir=bootstrap_base_dir,
        bootstrap_script=expand_path(bootstrap_script_raw),
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


def relocate_path(path: Path | None, source_root: Path, target_root: Path) -> Path | None:
    if path is None or source_root == target_root:
        return path
    try:
        relative = path.resolve(strict=False).relative_to(source_root.resolve(strict=False))
    except ValueError:
        return path
    return (target_root / relative).resolve(strict=False)


def relocate_managed_items(items: list[ManagedItem], config: LocalMachineConfig) -> list[ManagedItem]:
    """Route manifest-owned library paths to the configured deployment checkout."""
    relocated: list[ManagedItem] = []
    for item in items:
        mappings = tuple(
            replace(
                mapping,
                target_base=relocate_path(mapping.target_base, config.runtime_dir, config.library_dir),
            )
            for mapping in item.mappings
        )
        relocated.append(
            replace(
                item,
                managed_path=relocate_path(item.managed_path, config.runtime_dir, config.library_dir),
                mappings=mappings,
            )
        )
    return relocated


def override_local_machine_config(config: LocalMachineConfig, args: argparse.Namespace) -> LocalMachineConfig:
    updates: dict[str, object] = {}
    library_dir_override = getattr(args, "library_dir", None)
    bootstrap_script_override = getattr(args, "bootstrap_script", None)
    if library_dir_override:
        new_library_dir = expand_path(library_dir_override)
        updates["library_dir"] = new_library_dir
    if getattr(args, "library_remote", None):
        updates["library_remote"] = args.library_remote
    if getattr(args, "library_branch", None):
        updates["library_branch"] = args.library_branch
    if getattr(args, "bootstrap_base_dir", None):
        updates["bootstrap_base_dir"] = expand_path(args.bootstrap_base_dir)
    if bootstrap_script_override:
        updates["bootstrap_script"] = expand_path(bootstrap_script_override)
    return replace(config, **updates) if updates else config


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


def is_runtime_cache_path(rel_path: str) -> bool:
    path = Path(rel_path)
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def is_ignored_overlay_path(rel_path: str, ignored_rel_paths: tuple[str, ...] = ()) -> bool:
    if is_runtime_cache_path(rel_path):
        return True
    return any(
        rel_path == ignored.rstrip("/") or rel_path.startswith(f"{ignored.rstrip('/')}/")
        for ignored in ignored_rel_paths
    )


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
        rel_posix = rel.as_posix()
        if is_runtime_cache_path(rel_posix):
            continue
        snapshot[rel_posix] = sha256_file(path)
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
        rel_posix = rel.as_posix()
        if is_runtime_cache_path(rel_posix):
            continue
        snapshot[rel_posix] = git_blob_oid_file(path)
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


def git_subtree_dirty(path: Path, ignored_rel_paths: tuple[str, ...] = ()) -> bool:
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
    if not ignored_rel_paths:
        return bool(result.stdout.strip())
    ignored_repo_paths = {
        (rel_path / ignored).as_posix() if rel_path != Path(".") else ignored
        for ignored in ignored_rel_paths
    }
    for line in result.stdout.splitlines():
        changed_path = line[3:].strip()
        if " -> " in changed_path:
            changed_path = changed_path.rsplit(" -> ", 1)[1]
        if changed_path not in ignored_repo_paths:
            return True
    return False


def apply_local_overrides(diff: dict[str, object], overrides: tuple[str, ...]) -> dict[str, object]:
    if not overrides:
        return diff
    only_local = [path for path in diff["only_local"] if not is_ignored_overlay_path(path, overrides)]
    only_expected = [path for path in diff["only_expected"] if not is_ignored_overlay_path(path, overrides)]
    changed = [path for path in diff["changed"] if not is_ignored_overlay_path(path, overrides)]
    return {
        **diff,
        "match": not only_local and not only_expected and not changed,
        "only_local": only_local,
        "only_expected": only_expected,
        "changed": changed,
        "local_overrides": sorted(overrides),
    }


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


FRONTMATTER_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+)\s*:")
SKILL_RESOURCE_PATTERN = re.compile(
    r"(?<![/A-Za-z0-9_.-])((?:references|scripts|templates|assets)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)"
)


def yaml_scalar(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def apply_frontmatter_overrides(data: bytes, overrides: tuple[tuple[str, str | None], ...]) -> bytes:
    if not overrides:
        return data
    text = data.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("frontmatter override target is missing the opening delimiter")
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing_index is None:
        raise ValueError("frontmatter override target is missing the closing delimiter")

    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    override_map = dict(overrides)
    seen: set[str] = set()
    output = [lines[0]]
    index = 1
    while index < closing_index:
        match = FRONTMATTER_KEY_PATTERN.match(lines[index])
        key = match.group(1) if match else None
        if key not in override_map:
            output.append(lines[index])
            index += 1
            continue

        value = override_map[key]
        if value is not None:
            output.append(f"{key}: {yaml_scalar(value)}{newline}")
        seen.add(key)
        index += 1
        while index < closing_index and not FRONTMATTER_KEY_PATTERN.match(lines[index]):
            index += 1

    for key, value in overrides:
        if key not in seen and value is not None:
            output.append(f"{key}: {yaml_scalar(value)}{newline}")
    output.extend(lines[closing_index:])
    return "".join(output).encode("utf-8")


def extract_skill_resource_paths(data: bytes) -> set[str]:
    text = data.decode("utf-8")
    return {match.group(1).rstrip(".,;:)") for match in SKILL_RESOURCE_PATTERN.finditer(text)}


def validate_skill_snapshot(
    item: ManagedItem,
    target_base: Path,
    snapshot: dict[str, str],
    content_loader: Callable[[str], bytes],
) -> None:
    skill_oid = snapshot.get("SKILL.md")
    if skill_oid is None:
        return
    missing = sorted(extract_skill_resource_paths(content_loader(skill_oid)) - snapshot.keys())
    if missing:
        raise FileNotFoundError(
            f"incomplete skill package for {item.name} at {target_base}: missing {', '.join(missing)}"
        )


def validate_skill_stage(item: ManagedItem, target_base: Path, stage_root: Path) -> None:
    skill_path = stage_root / "SKILL.md"
    if not skill_path.is_file():
        return
    missing = sorted(
        rel_path
        for rel_path in extract_skill_resource_paths(skill_path.read_bytes())
        if not (stage_root / rel_path).is_file()
    )
    if missing:
        raise FileNotFoundError(
            f"incomplete skill package for {item.name} at {target_base}: missing {', '.join(missing)}"
        )


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
            if mapping.frontmatter_overrides:
                target_path.write_bytes(
                    apply_frontmatter_overrides(target_path.read_bytes(), mapping.frontmatter_overrides)
                )
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
        validate_skill_stage(item, target_base, target_stage_root)
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


def sync_tree_exact(stage_root: Path, local_root: Path, ignored_rel_paths: tuple[str, ...] = ()) -> None:
    local_root.mkdir(parents=True, exist_ok=True)

    expected_entries = {
        path.relative_to(stage_root).as_posix()
        for path in stage_root.rglob("*")
        if not is_ignored_overlay_path(path.relative_to(stage_root).as_posix(), ignored_rel_paths)
    }
    local_entries = {
        path.relative_to(local_root).as_posix()
        for path in local_root.rglob("*")
        if not is_ignored_overlay_path(path.relative_to(local_root).as_posix(), ignored_rel_paths)
    }

    for rel in sorted(local_entries - expected_entries, reverse=True):
        remove_path(local_root / rel)

    for path in sorted(stage_root.rglob("*")):
        rel = path.relative_to(stage_root)
        rel_posix = rel.as_posix()
        if is_ignored_overlay_path(rel_posix, ignored_rel_paths):
            continue
        target = local_root / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        copy_file(path, target)


def sync_snapshot_exact(
    local_root: Path,
    expected_snapshot: dict[str, str],
    content_loader: Callable[[str], bytes],
    ignored_rel_paths: tuple[str, ...] = (),
) -> None:
    local_root.mkdir(parents=True, exist_ok=True)
    local_snapshot = snapshot_tree_git_blob_oids(local_root)
    filtered_expected = {
        rel: oid
        for rel, oid in expected_snapshot.items()
        if not is_ignored_overlay_path(rel, ignored_rel_paths)
    }

    for rel in sorted(local_snapshot.keys() - filtered_expected.keys(), reverse=True):
        remove_path(local_root / rel)

    for rel in sorted(filtered_expected.keys()):
        target = local_root / rel
        expected_oid = filtered_expected[rel]
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


def maybe_git_transport_env(remote_url: str, config: LocalMachineConfig) -> dict[str, str] | None:
    if parse_github_repo(remote_url) is None:
        return None
    return git_ssh_env(config)


def repo_remote_url(repo_path: Path, remote: str = "origin") -> str | None:
    result = try_run(["git", "-C", str(repo_path), "remote", "get-url", remote])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def require_repo_root(path: Path, label: str) -> Path:
    repo_root = git_repo_root(path)
    if repo_root is None:
        raise RuntimeError(f"{label} 不是 git 仓库: {path}")
    resolved_repo_root = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_repo_root != resolved_path:
        raise RuntimeError(f"{label} 必须是 git 仓根目录: {path}")
    return resolved_repo_root


def require_library_remote(config: LocalMachineConfig, repo_path: Path | None = None) -> str:
    configured = config.library_remote
    actual = repo_remote_url(repo_path) if repo_path is not None and repo_path.exists() else None
    if configured and actual and configured != actual:
        raise RuntimeError(f"library remote 不匹配: expected={configured} actual={actual}")
    if configured:
        return configured
    if actual:
        return actual
    raise RuntimeError(
        f"未配置 library_remote。请在 {config.private_config_path} 中设置 skills_manager.library_remote。"
    )


def managed_library_item(config: LocalMachineConfig) -> ManagedItem:
    return ManagedItem(
        name="skills-manager-library",
        kind="git_repo",
        local_path=config.library_dir,
        remote="origin",
        branch=config.library_branch,
    )


def default_library_commit_message() -> str:
    return DEFAULT_LIBRARY_COMMIT_MESSAGE


def maybe_parse_json_output(output: str) -> object:
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def bootstrap_manager_db(config: LocalMachineConfig, reset: bool = True) -> dict[str, object]:
    script_path = config.bootstrap_script
    if not script_path.is_file():
        raise RuntimeError(f"bootstrap script 不存在: {script_path}")
    args = ["python3", str(script_path), "--base-dir", str(config.bootstrap_base_dir)]
    if reset:
        args.append("--reset")
    output = run(args)
    return {
        "script": str(script_path),
        "base_dir": str(config.bootstrap_base_dir),
        "reset": reset,
        "output": maybe_parse_json_output(output),
    }


def library_pull(config: LocalMachineConfig, skip_bootstrap: bool = False) -> dict[str, object]:
    library_dir = config.library_dir
    remote_url = require_library_remote(config, library_dir if library_dir.exists() else None)
    remote_env = maybe_git_transport_env(remote_url, config)

    if not library_dir.exists():
        library_dir.parent.mkdir(parents=True, exist_ok=True)
        run(
            ["git", "clone", "--branch", config.library_branch, remote_url, str(library_dir)],
            env=remote_env,
        )
        result: dict[str, object] = {
            "name": "skills-manager-library",
            "kind": "git_repo",
            "local_path": str(library_dir),
            "remote": remote_url,
            "branch": config.library_branch,
            "local_state": "current",
            "action": "clone",
            "changed": True,
        }
    else:
        require_repo_root(library_dir, "library_dir")
        require_library_remote(config, library_dir)
        inspected = inspect_git_repo(managed_library_item(config), config)
        if inspected["dirty"]:
            raise RuntimeError(f"library repo 有未提交变更，不能执行 pull: {library_dir}")
        if inspected["local_state"] == "ahead":
            raise RuntimeError(f"library repo 比远端超前，不能执行 pull: {library_dir}")
        if inspected["local_state"] == "diverged":
            raise RuntimeError(f"library repo 与远端分叉，不能执行 pull: {library_dir}")
        if inspected["action"] == "upgrade":
            result = upgrade_git_repo(managed_library_item(config), config)
            result["action"] = "pull"
        else:
            result = inspected
            result["changed"] = False

    if not skip_bootstrap and config.library_dir == config.runtime_dir:
        result["bootstrap"] = bootstrap_manager_db(config, reset=True)
    elif not skip_bootstrap:
        result["bootstrap"] = {
            "status": "skipped_separate_runtime",
            "runtime_dir": str(config.runtime_dir),
            "note": "The deployment owner must project the published snapshot before rebuilding runtime metadata.",
        }
    return result


def library_push(config: LocalMachineConfig, message: str | None = None) -> dict[str, object]:
    library_dir = config.library_dir
    require_repo_root(library_dir, "library_dir")
    remote_url = require_library_remote(config, library_dir)
    remote_env = maybe_git_transport_env(remote_url, config)

    inspected = inspect_git_repo(managed_library_item(config), config)
    if inspected["local_state"] in {"behind", "behind-dirty"}:
        raise RuntimeError(f"library repo 落后于远端，不能执行 push: state={inspected['local_state']}")
    if inspected["local_state"] == "diverged":
        raise RuntimeError("library repo 与远端分叉，不能执行 push")

    commit_created = False
    if inspected["dirty"]:
        run(["git", "-C", str(library_dir), "add", "--all"])
        run(
            ["git", "-C", str(library_dir), "commit", "-m", message or default_library_commit_message()],
            env=remote_env,
        )
        commit_created = True

    refreshed = inspect_git_repo(managed_library_item(config), config)
    if refreshed["dirty"]:
        raise RuntimeError("library repo 提交后仍然存在未提交变更")
    if refreshed["local_state"] == "diverged":
        raise RuntimeError("library repo 提交后与远端分叉，不能执行 push")
    if refreshed["local_state"] in {"behind", "behind-dirty"}:
        raise RuntimeError(f"library repo 落后于远端，不能执行 push: state={refreshed['local_state']}")

    pushed = False
    if refreshed["local_state"] == "ahead":
        run(["git", "-C", str(library_dir), "push", "origin", config.library_branch], env=remote_env)
        pushed = True
        refreshed = inspect_git_repo(managed_library_item(config), config)

    return {
        "name": "skills-manager-library",
        "kind": "git_repo",
        "local_path": str(library_dir),
        "remote": remote_url,
        "branch": config.library_branch,
        "local_state": refreshed["local_state"],
        "action": "push" if pushed else "none",
        "changed": commit_created or pushed,
        "commit_created": commit_created,
        "pushed": pushed,
    }


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
            if not is_runtime_cache_path(target):
                expected[target] = oid
    return expected


def resolve_overlay_snapshots(
    item: ManagedItem,
    blob_paths: dict[str, str],
    store: RepoCheckoutStore,
) -> dict[Path, dict[str, str]]:
    grouped_mappings: dict[Path, list[Mapping]] = {}
    for mapping in item.mappings:
        grouped_mappings.setdefault(mapping_target_base(item, mapping), []).append(mapping)
    snapshots = {
        target_base: resolve_overlay_snapshot(mappings, blob_paths)
        for target_base, mappings in grouped_mappings.items()
    }
    assert item.source is not None
    for mapping in item.mappings:
        if not mapping.frontmatter_overrides:
            continue
        source_oid = blob_paths[mapping.source]
        transformed = apply_frontmatter_overrides(
            store.github_blob(item.source, source_oid),
            mapping.frontmatter_overrides,
        )
        synthetic_oid = git_blob_oid_bytes(transformed)
        store.synthetic_blobs[synthetic_oid] = transformed
        snapshots[mapping_target_base(item, mapping)][mapping.target] = synthetic_oid
    for target_base, snapshot in snapshots.items():
        validate_skill_snapshot(
            item,
            target_base,
            snapshot,
            lambda oid: store.overlay_blob(item.source, oid),
        )
    return snapshots


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
        for target_base, expected_snapshot in resolve_overlay_snapshots(
            item,
            store.github_tree(item.source),
            store,
        ).items():
            diff = apply_local_overrides(
                compare_snapshots(snapshot_tree_git_blob_oids(target_base), expected_snapshot),
                item.local_overrides,
            )
            dirty = git_subtree_dirty(target_base, item.local_overrides)
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
            diff = apply_local_overrides(compare_trees(target_base, target_stage_root), item.local_overrides)
            dirty = git_subtree_dirty(target_base, item.local_overrides)
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
        snapshots = resolve_overlay_snapshots(item, store.github_tree(item.source), store)
        with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
            staged: dict[Path, Path] = {}
            for index, (target_base, expected_snapshot) in enumerate(snapshots.items()):
                stage_root = Path(temp_dir) / str(index)
                sync_snapshot_exact(
                    stage_root,
                    expected_snapshot,
                    lambda oid: store.overlay_blob(item.source, oid),
                )
                staged[target_base] = stage_root
            for target_base, stage_root in staged.items():
                sync_tree_exact(stage_root, target_base, item.local_overrides)
        result = inspect_overlay_sync(item, store, resolved_config)
        result["changed"] = True
        return result

    checkout_root = store.checkout(item.source)
    with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
        stage_root = Path(temp_dir) / "stage"
        stages = build_overlay_stages(item, checkout_root, stage_root)
        for target_base, target_stage_root in stages.items():
            sync_tree_exact(target_stage_root, target_base, item.local_overrides)

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
    private_config_path = Path(args.private_config).expanduser().resolve()
    config = load_local_machine_config(local_config_path, private_config_path)
    config = override_local_machine_config(config, args)

    if args.command in {"inspect", "upgrade"}:
        items = select_items(
            relocate_managed_items(load_manifest(manifest_path), config),
            args.only,
        )
    else:
        items = []

    if args.command == "inspect":
        payload = {
            "command": "inspect",
            "sources": str(manifest_path),
            "local_config": str(local_config_path),
            "private_config": str(private_config_path),
            "results": inspect_items(items, config),
        }
    elif args.command == "upgrade":
        payload = {
            "command": "upgrade",
            "sources": str(manifest_path),
            "local_config": str(local_config_path),
            "private_config": str(private_config_path),
            "results": upgrade_items(items, config),
        }
    elif args.command == "library-pull":
        payload = {
            "command": "library-pull",
            "local_config": str(local_config_path),
            "private_config": str(private_config_path),
            "result": library_pull(config, skip_bootstrap=args.skip_bootstrap),
        }
    elif args.command == "library-push":
        payload = {
            "command": "library-push",
            "local_config": str(local_config_path),
            "private_config": str(private_config_path),
            "result": library_push(config, message=args.message),
        }
    else:
        payload = {
            "command": "bootstrap-manager-db",
            "local_config": str(local_config_path),
            "private_config": str(private_config_path),
            "result": bootstrap_manager_db(config, reset=not args.no_reset),
        }

    print(json.dumps(payload, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
