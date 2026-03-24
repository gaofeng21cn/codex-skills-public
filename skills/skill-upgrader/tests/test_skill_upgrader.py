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
