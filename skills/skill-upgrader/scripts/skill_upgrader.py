#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "sources.json"


@dataclass(frozen=True)
class SourceRepo:
    repo_url: str
    ref: str


@dataclass(frozen=True)
class Mapping:
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class ManagedItem:
    name: str
    kind: str
    local_path: Path
    source: SourceRepo | None = None
    mappings: tuple[Mapping, ...] = ()
    remote: str = "origin"
    branch: str = "main"


@dataclass
class RepoCheckoutStore:
    temp_root: Path
    checkouts: dict[tuple[str, str], Path] = field(default_factory=dict)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and upgrade managed Codex skills.")
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_MANIFEST),
        help="Path to the managed sources manifest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("inspect", "upgrade"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--only", action="append", default=[], help="Limit to selected managed item names.")

    return parser.parse_args()


def run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def load_manifest(path: Path) -> list[ManagedItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[ManagedItem] = []
    for raw in data["items"]:
        kind = raw["kind"]
        local_path = Path(raw["local_path"]).expanduser()
        source = None
        mappings: tuple[Mapping, ...] = ()
        if kind == "overlay_sync":
            source_raw = raw["source"]
            source = SourceRepo(repo_url=source_raw["repo_url"], ref=source_raw["ref"])
            mappings = tuple(
                Mapping(kind=mapping["kind"], source=mapping["source"], target=mapping["target"])
                for mapping in raw["mappings"]
            )
        items.append(
            ManagedItem(
                name=raw["name"],
                kind=kind,
                local_path=local_path,
                source=source,
                mappings=mappings,
                remote=raw.get("remote", "origin"),
                branch=raw.get("branch", "main"),
            )
        )
    return items


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


def compare_trees(local_root: Path, expected_root: Path) -> dict[str, object]:
    local_snapshot = snapshot_tree(local_root)
    expected_snapshot = snapshot_tree(expected_root)
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
    stage_root.mkdir(parents=True, exist_ok=True)
    for mapping in item.mappings:
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


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


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


def inspect_git_repo(item: ManagedItem) -> dict[str, object]:
    run(["git", "-C", str(item.local_path), "fetch", "--all", "--prune"])
    local_head = run(["git", "-C", str(item.local_path), "rev-parse", "HEAD"])
    upstream_ref = f"{item.remote}/{item.branch}"
    upstream_head = run(["git", "-C", str(item.local_path), "rev-parse", upstream_ref])
    merge_base = run(["git", "-C", str(item.local_path), "merge-base", "HEAD", upstream_ref])
    dirty = bool(run(["git", "-C", str(item.local_path), "status", "--short"]))

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
        "local_path": str(item.local_path),
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


def inspect_overlay_sync(item: ManagedItem, store: RepoCheckoutStore) -> dict[str, object]:
    assert item.source is not None
    checkout_root = store.checkout(item.source)
    with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
        stage_root = Path(temp_dir) / "stage"
        build_overlay_stage(item, checkout_root, stage_root)
        diff = compare_trees(item.local_path, stage_root)
    return {
        "name": item.name,
        "kind": item.kind,
        "local_path": str(item.local_path),
        "source": {
            "repo_url": item.source.repo_url,
            "ref": item.source.ref,
        },
        "local_state": "current" if diff["match"] else "different",
        "action": "none" if diff["match"] else "upgrade",
        "diff": diff,
        "changed": False,
    }


def upgrade_git_repo(item: ManagedItem) -> dict[str, object]:
    result = inspect_git_repo(item)
    if result["action"] == "upgrade":
        run(["git", "-C", str(item.local_path), "pull", "--ff-only", item.remote, item.branch])
        result = inspect_git_repo(item)
        result["changed"] = True
    return result


def upgrade_overlay_sync(item: ManagedItem, store: RepoCheckoutStore) -> dict[str, object]:
    inspected = inspect_overlay_sync(item, store)
    if inspected["action"] != "upgrade":
        return inspected

    assert item.source is not None
    checkout_root = store.checkout(item.source)
    with tempfile.TemporaryDirectory(prefix=f"skill-upgrader-{item.name}-") as temp_dir:
        stage_root = Path(temp_dir) / "stage"
        build_overlay_stage(item, checkout_root, stage_root)
        sync_tree_exact(stage_root, item.local_path)

    result = inspect_overlay_sync(item, store)
    result["changed"] = True
    return result


def inspect_items(items: list[ManagedItem]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="skill-upgrader-checkouts-") as temp_dir:
        store = RepoCheckoutStore(Path(temp_dir))
        for item in items:
            if item.kind == "git_repo":
                results.append(inspect_git_repo(item))
                continue
            if item.kind == "overlay_sync":
                results.append(inspect_overlay_sync(item, store))
                continue
            raise ValueError(f"unsupported managed item kind: {item.kind}")
    return results


def upgrade_items(items: list[ManagedItem]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="skill-upgrader-checkouts-") as temp_dir:
        store = RepoCheckoutStore(Path(temp_dir))
        for item in items:
            if item.kind == "git_repo":
                results.append(upgrade_git_repo(item))
                continue
            if item.kind == "overlay_sync":
                results.append(upgrade_overlay_sync(item, store))
                continue
            raise ValueError(f"unsupported managed item kind: {item.kind}")
    return results


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.sources).expanduser().resolve()
    items = select_items(load_manifest(manifest_path), args.only)

    if args.command == "inspect":
        payload = {
            "command": "inspect",
            "sources": str(manifest_path),
            "results": inspect_items(items),
        }
    else:
        payload = {
            "command": "upgrade",
            "sources": str(manifest_path),
            "results": upgrade_items(items),
        }

    print(json.dumps(payload, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
