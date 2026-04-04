from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "skill_upgrader.py"
SPEC = importlib.util.spec_from_file_location("skill_upgrader", SCRIPT_PATH)
assert SPEC and SPEC.loader
skill_upgrader = importlib.util.module_from_spec(SPEC)
sys.modules["skill_upgrader"] = skill_upgrader
SPEC.loader.exec_module(skill_upgrader)


def run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def configure_git_user(repo: Path) -> None:
    run_git(["config", "user.name", "Test User"], cwd=repo)
    run_git(["config", "user.email", "test@example.com"], cwd=repo)


def test_load_manifest_expands_user_paths(tmp_path: Path, monkeypatch) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "sample-repo",
                        "kind": "git_repo",
                        "local_path": "~/managed/repo",
                        "remote": "origin",
                        "branch": "main",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    items = skill_upgrader.load_manifest(manifest_path)

    assert len(items) == 1
    assert items[0].name == "sample-repo"
    assert items[0].local_path == home_dir / "managed" / "repo"
    assert items[0].managed_path == home_dir / "managed" / "repo"


def test_load_manifest_supports_explicit_managed_paths(tmp_path: Path, monkeypatch) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "sample-skill",
                        "kind": "overlay_sync",
                        "local_path": "~/.codex/skills/sample-skill",
                        "managed_path": "~/.skills-manager/repos/sample-skill/src/sample-skill",
                        "source": {
                            "repo_url": "https://example.invalid/repo.git",
                            "ref": "main",
                        },
                        "mappings": [
                            {
                                "kind": "dir_contents",
                                "source": "skill",
                                "target": ".",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    items = skill_upgrader.load_manifest(manifest_path)

    assert len(items) == 1
    assert items[0].local_path == home_dir / ".codex" / "skills" / "sample-skill"
    assert items[0].managed_path == home_dir / ".skills-manager" / "repos" / "sample-skill" / "src" / "sample-skill"


def test_load_manifest_supports_mapping_specific_target_bases(tmp_path: Path, monkeypatch) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "sample-skill",
                        "kind": "overlay_sync",
                        "local_path": "~/.codex/skills/sample-skill",
                        "source": {
                            "repo_url": "https://example.invalid/repo.git",
                            "ref": "main",
                        },
                        "mappings": [
                            {
                                "kind": "file",
                                "source": "docs/SKILL.md",
                                "target": "SKILL.md",
                                "target_base": "~/.skills-manager/skills/sample-skill",
                            },
                            {
                                "kind": "dir_contents",
                                "source": "src/sample-skill/data",
                                "target": "data",
                                "target_base": "~/.skills-manager/repos/sample-skill/src/sample-skill",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    items = skill_upgrader.load_manifest(manifest_path)

    assert len(items) == 1
    assert items[0].mappings[0].target_base == home_dir / ".skills-manager" / "skills" / "sample-skill"
    assert items[0].mappings[1].target_base == home_dir / ".skills-manager" / "repos" / "sample-skill" / "src" / "sample-skill"


def test_build_overlay_stage_combines_file_and_dir_contents(tmp_path: Path) -> None:
    checkout_root = tmp_path / "checkout"
    (checkout_root / "skill" / "nested").mkdir(parents=True)
    (checkout_root / "skill" / "nested" / "data.txt").write_text("payload\n", encoding="utf-8")
    (checkout_root / "docs").mkdir()
    (checkout_root / "docs" / "SKILL.md").write_text("---\nname: sample\ndescription: Use when testing.\n---\n", encoding="utf-8")
    stage_root = tmp_path / "stage"

    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=tmp_path / "local",
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(
            skill_upgrader.Mapping(kind="dir_contents", source="skill", target="."),
            skill_upgrader.Mapping(kind="file", source="docs/SKILL.md", target="SKILL.md"),
        ),
    )

    skill_upgrader.build_overlay_stage(item, checkout_root, stage_root)

    assert (stage_root / "nested" / "data.txt").read_text(encoding="utf-8") == "payload\n"
    assert (stage_root / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: sample")


def test_sync_tree_exact_removes_extraneous_entries(tmp_path: Path) -> None:
    stage_root = tmp_path / "stage"
    local_root = tmp_path / "local"
    (stage_root / "nested").mkdir(parents=True)
    (stage_root / "nested" / "keep.txt").write_text("fresh\n", encoding="utf-8")
    (stage_root / "SKILL.md").write_text("current\n", encoding="utf-8")

    (local_root / "nested").mkdir(parents=True)
    (local_root / "nested" / "keep.txt").write_text("stale\n", encoding="utf-8")
    (local_root / "obsolete.txt").write_text("remove me\n", encoding="utf-8")

    skill_upgrader.sync_tree_exact(stage_root, local_root)

    assert not (local_root / "obsolete.txt").exists()
    assert (local_root / "nested" / "keep.txt").read_text(encoding="utf-8") == "fresh\n"
    assert (local_root / "SKILL.md").read_text(encoding="utf-8") == "current\n"


def test_load_local_machine_config_reads_github_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "local_machine.json"
    config_path.write_text(
        json.dumps(
            {
                "github": {
                    "overlay_transport": "gh_api",
                    "git_repo_transport": "ssh_fetch",
                    "ssh_strict_host_key_checking": "accept-new",
                    "ssh_connect_timeout_seconds": 12,
                }
            }
        ),
        encoding="utf-8",
    )

    config = skill_upgrader.load_local_machine_config(config_path)

    assert config.github_overlay_transport == "gh_api"
    assert config.github_git_repo_transport == "ssh_fetch"
    assert config.ssh_strict_host_key_checking == "accept-new"
    assert config.ssh_connect_timeout_seconds == 12


def test_resolve_overlay_snapshot_maps_file_and_dir_contents_targets() -> None:
    mappings = (
        skill_upgrader.Mapping(kind="dir_contents", source="skills/demo", target="."),
        skill_upgrader.Mapping(kind="file", source="docs/SKILL.md", target="SKILL.md"),
    )
    blob_paths = {
        "skills/demo/references/guide.md": "sha-guide",
        "skills/demo/templates/start.sh": "sha-template",
        "docs/SKILL.md": "sha-skill",
    }

    snapshot = skill_upgrader.resolve_overlay_snapshot(mappings, blob_paths)

    assert snapshot == {
        "references/guide.md": "sha-guide",
        "templates/start.sh": "sha-template",
        "SKILL.md": "sha-skill",
    }


def test_sync_snapshot_exact_updates_changed_files_and_removes_extra_entries(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    (local_root / "nested").mkdir(parents=True)
    (local_root / "nested" / "keep.txt").write_text("stale\n", encoding="utf-8")
    (local_root / "obsolete.txt").write_text("remove me\n", encoding="utf-8")

    expected = {
        "nested/keep.txt": "sha-keep",
        "SKILL.md": "sha-skill",
    }
    contents = {
        "sha-keep": b"fresh\n",
        "sha-skill": b"current\n",
    }

    skill_upgrader.sync_snapshot_exact(local_root, expected, lambda sha: contents[sha])

    assert not (local_root / "obsolete.txt").exists()
    assert (local_root / "nested" / "keep.txt").read_text(encoding="utf-8") == "fresh\n"
    assert (local_root / "SKILL.md").read_text(encoding="utf-8") == "current\n"


def test_upgrade_overlay_sync_targets_managed_path_not_projection_path(tmp_path: Path) -> None:
    checkout_root = tmp_path / "checkout"
    (checkout_root / "skill" / "data").mkdir(parents=True)
    (checkout_root / "skill" / "data" / "catalog.csv").write_text("fresh\n", encoding="utf-8")
    (checkout_root / "skill" / "templates").mkdir(parents=True)
    (checkout_root / "skill" / "templates" / "skill-content.md").write_text("template\n", encoding="utf-8")
    (checkout_root / "docs").mkdir()
    (checkout_root / "docs" / "SKILL.md").write_text("---\nname: sample\ndescription: Use when testing.\n---\n", encoding="utf-8")

    managed_root = tmp_path / "managed"
    (managed_root / "data").mkdir(parents=True)
    (managed_root / "data" / "catalog.csv").write_text("stale\n", encoding="utf-8")
    (managed_root / "templates").mkdir()
    (managed_root / "templates" / "skill-content.md").write_text("old template\n", encoding="utf-8")
    (managed_root / "SKILL.md").write_text("old\n", encoding="utf-8")

    projection_root = tmp_path / "projection"
    projection_root.mkdir()
    (projection_root / "data").symlink_to(managed_root / "data", target_is_directory=True)
    (projection_root / "templates").symlink_to(managed_root / "templates", target_is_directory=True)
    (projection_root / "SKILL.md").write_text("old\n", encoding="utf-8")

    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=projection_root,
        managed_path=managed_root,
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(
            skill_upgrader.Mapping(kind="dir_contents", source="skill", target="."),
            skill_upgrader.Mapping(kind="file", source="docs/SKILL.md", target="SKILL.md"),
        ),
    )

    store = skill_upgrader.RepoCheckoutStore(tmp_path / "checkouts")
    store.checkouts[(item.source.repo_url, item.source.ref)] = checkout_root

    result = skill_upgrader.upgrade_overlay_sync(item, store)

    assert result["local_state"] == "current"
    assert result["action"] == "none"
    assert (managed_root / "data" / "catalog.csv").read_text(encoding="utf-8") == "fresh\n"
    assert (managed_root / "templates" / "skill-content.md").read_text(encoding="utf-8") == "template\n"


def test_upgrade_overlay_sync_supports_mapping_specific_target_bases(tmp_path: Path) -> None:
    checkout_root = tmp_path / "checkout"
    (checkout_root / "docs").mkdir(parents=True)
    (checkout_root / "docs" / "SKILL.md").write_text("---\nname: sample\ndescription: Use when testing.\n---\n", encoding="utf-8")
    (checkout_root / "src" / "sample-skill" / "data").mkdir(parents=True)
    (checkout_root / "src" / "sample-skill" / "data" / "catalog.csv").write_text("fresh\n", encoding="utf-8")
    (checkout_root / "src" / "sample-skill" / "scripts").mkdir(parents=True)
    (checkout_root / "src" / "sample-skill" / "scripts" / "search.py").write_text("print('fresh')\n", encoding="utf-8")

    projection_root = tmp_path / "projection"
    projection_root.mkdir()

    skill_view_root = tmp_path / "skill-view"
    skill_view_root.mkdir()
    (skill_view_root / "SKILL.md").write_text("old\n", encoding="utf-8")

    source_root = tmp_path / "source-root"
    (source_root / "data").mkdir(parents=True)
    (source_root / "data" / "catalog.csv").write_text("stale\n", encoding="utf-8")
    (source_root / "scripts").mkdir(parents=True)
    (source_root / "scripts" / "search.py").write_text("print('stale')\n", encoding="utf-8")

    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=projection_root,
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(
            skill_upgrader.Mapping(
                kind="file",
                source="docs/SKILL.md",
                target="SKILL.md",
                target_base=skill_view_root,
            ),
            skill_upgrader.Mapping(
                kind="dir_contents",
                source="src/sample-skill/data",
                target="data",
                target_base=source_root,
            ),
            skill_upgrader.Mapping(
                kind="dir_contents",
                source="src/sample-skill/scripts",
                target="scripts",
                target_base=source_root,
            ),
        ),
    )

    store = skill_upgrader.RepoCheckoutStore(tmp_path / "checkouts")
    store.checkouts[(item.source.repo_url, item.source.ref)] = checkout_root

    result = skill_upgrader.upgrade_overlay_sync(item, store)

    assert result["local_state"] == "current"
    assert result["action"] == "none"
    assert (skill_view_root / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: sample")
    assert (source_root / "data" / "catalog.csv").read_text(encoding="utf-8") == "fresh\n"
    assert (source_root / "scripts" / "search.py").read_text(encoding="utf-8") == "print('fresh')\n"


def test_inspect_overlay_sync_blocks_upgrade_for_dirty_git_targets(tmp_path: Path) -> None:
    checkout_root = tmp_path / "checkout"
    (checkout_root / "skill").mkdir(parents=True)
    (checkout_root / "skill" / "catalog.csv").write_text("fresh\n", encoding="utf-8")

    repo_root = tmp_path / "managed-repo"
    subprocess.run(["git", "init", str(repo_root)], check=True, text=True, capture_output=True)
    configure_git_user(repo_root)
    target_root = repo_root / "src" / "sample-skill"
    target_root.mkdir(parents=True)
    (target_root / "catalog.csv").write_text("baseline\n", encoding="utf-8")
    run_git(["add", "."], cwd=repo_root)
    run_git(["commit", "-m", "baseline"], cwd=repo_root)

    (target_root / "catalog.csv").write_text("local-dirty\n", encoding="utf-8")

    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=tmp_path / "projection",
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(
            skill_upgrader.Mapping(
                kind="dir_contents",
                source="skill",
                target=".",
                target_base=target_root,
            ),
        ),
    )

    store = skill_upgrader.RepoCheckoutStore(tmp_path / "checkouts")
    store.checkouts[(item.source.repo_url, item.source.ref)] = checkout_root

    result = skill_upgrader.inspect_overlay_sync(item, store)

    assert result["local_state"] == "different-dirty"
    assert result["action"] == "none"
    assert result["destinations"][0]["dirty"] is True


def test_upgrade_overlay_sync_gh_api_targets_managed_and_mapping_specific_paths(tmp_path: Path) -> None:
    projection_root = tmp_path / "projection"
    projection_root.mkdir()
    (projection_root / "SKILL.md").write_text("projection\n", encoding="utf-8")

    managed_root = tmp_path / "managed"
    managed_root.mkdir()
    (managed_root / "SKILL.md").write_text("old managed\n", encoding="utf-8")

    source_root = tmp_path / "source-root"
    (source_root / "data").mkdir(parents=True)
    (source_root / "data" / "catalog.csv").write_text("stale\n", encoding="utf-8")

    skill_content = b"---\nname: sample\ndescription: Use when testing.\n---\n"
    catalog_content = b"fresh\n"
    skill_sha = skill_upgrader.git_blob_oid_bytes(skill_content)
    catalog_sha = skill_upgrader.git_blob_oid_bytes(catalog_content)

    source = skill_upgrader.SourceRepo(repo_url="https://github.com/example/demo.git", ref="main")
    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=projection_root,
        managed_path=managed_root,
        source=source,
        mappings=(
            skill_upgrader.Mapping(kind="file", source="docs/SKILL.md", target="SKILL.md"),
            skill_upgrader.Mapping(
                kind="dir_contents",
                source="src/sample-skill/data",
                target="data",
                target_base=source_root,
            ),
        ),
    )

    store = skill_upgrader.RepoCheckoutStore(tmp_path / "checkouts")
    store.github_trees[("example/demo", "main")] = {
        "docs/SKILL.md": skill_sha,
        "src/sample-skill/data/catalog.csv": catalog_sha,
    }
    store.github_blobs[("example", "demo", skill_sha)] = skill_content
    store.github_blobs[("example", "demo", catalog_sha)] = catalog_content

    result = skill_upgrader.upgrade_overlay_sync(
        item,
        store,
        skill_upgrader.LocalMachineConfig(github_overlay_transport="gh_api"),
    )

    assert result["source"]["transport"] == "gh_api"
    assert result["local_state"] == "current"
    assert result["action"] == "none"
    assert result["changed"] is True
    assert (managed_root / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: sample")
    assert (source_root / "data" / "catalog.csv").read_text(encoding="utf-8") == "fresh\n"
    assert (projection_root / "SKILL.md").read_text(encoding="utf-8") == "projection\n"


def test_inspect_git_repo_detects_repo_behind_upstream(tmp_path: Path) -> None:
    remote_bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True, text=True, capture_output=True)

    seed_repo = tmp_path / "seed"
    subprocess.run(["git", "clone", str(remote_bare), str(seed_repo)], check=True, text=True, capture_output=True)
    configure_git_user(seed_repo)
    run_git(["checkout", "-b", "main"], cwd=seed_repo)
    (seed_repo / "README.md").write_text("seed\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=seed_repo)
    run_git(["commit", "-m", "seed"], cwd=seed_repo)
    run_git(["push", "-u", "origin", "main"], cwd=seed_repo)
    subprocess.run(
        ["git", f"--git-dir={remote_bare}", "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        text=True,
        capture_output=True,
    )

    local_repo = tmp_path / "local"
    subprocess.run(["git", "clone", str(remote_bare), str(local_repo)], check=True, text=True, capture_output=True)
    configure_git_user(local_repo)

    updater_repo = tmp_path / "updater"
    subprocess.run(["git", "clone", str(remote_bare), str(updater_repo)], check=True, text=True, capture_output=True)
    configure_git_user(updater_repo)
    (updater_repo / "README.md").write_text("seed\nupdate\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=updater_repo)
    run_git(["commit", "-m", "update"], cwd=updater_repo)
    run_git(["push", "origin", "main"], cwd=updater_repo)

    item = skill_upgrader.ManagedItem(
        name="superpowers",
        kind="git_repo",
        local_path=local_repo,
        remote="origin",
        branch="main",
    )

    result = skill_upgrader.inspect_git_repo(item)

    assert result["name"] == "superpowers"
    assert result["kind"] == "git_repo"
    assert result["local_state"] == "behind"
    assert result["action"] == "upgrade"
