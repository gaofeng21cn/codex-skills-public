from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_ui_ux_pro_max_updates_the_publishable_library_snapshot() -> None:
    items = skill_upgrader.load_manifest(skill_upgrader.DEFAULT_MANIFEST)
    item = next(item for item in items if item.name == "ui-ux-pro-max")

    expected_root = (
        Path("~/.skills-manager/skills/ui-ux-pro-max").expanduser().resolve(strict=False)
    )
    assert item.target_path == expected_root
    assert item.local_overrides == ()
    assert {mapping.target for mapping in item.mappings} == {
        "SKILL.md",
        "references",
        "data",
        "scripts",
        "templates",
    }
    assert all(
        skill_upgrader.mapping_target_base(item, mapping) == expected_root
        for mapping in item.mappings
    )
    skill_mapping = next(mapping for mapping in item.mappings if mapping.target == "SKILL.md")
    assert dict(skill_mapping.frontmatter_overrides)["description"].startswith("Use only when")


def test_managed_browser_mineru_and_officecli_routes_are_narrow_and_publishable() -> None:
    items = {item.name: item for item in skill_upgrader.load_manifest(skill_upgrader.DEFAULT_MANIFEST)}

    for item_name in ("agent-browser", "mineru-document-extractor"):
        skill_mapping = next(
            mapping for mapping in items[item_name].mappings if mapping.target == "SKILL.md"
        )
        assert dict(skill_mapping.frontmatter_overrides)["description"].startswith("Use when")
        assert items[item_name].local_overrides == ()

    agent_overrides = dict(next(
        mapping for mapping in items["agent-browser"].mappings if mapping.target == "SKILL.md"
    ).frontmatter_overrides)
    assert "hidden" in agent_overrides
    assert agent_overrides["hidden"] is None

    officecli = items["officecli"]
    assert officecli.target_path == Path("~/.skills-manager/skills/officecli").expanduser().resolve(strict=False)
    assert officecli.local_overrides == ()
    assert all(
        dict(mapping.frontmatter_overrides)["description"].startswith("Use when")
        for mapping in officecli.mappings
    )


def test_openai_curated_skills_are_not_managed_overlays() -> None:
    items = {item.name: item for item in skill_upgrader.load_manifest(skill_upgrader.DEFAULT_MANIFEST)}

    assert {"cli-creator", "hatch-pet", "pdf", "playwright", "screenshot"}.isdisjoint(items)


def test_additional_third_party_skill_overlays_are_direct_and_narrow() -> None:
    items = {item.name: item for item in skill_upgrader.load_manifest(skill_upgrader.DEFAULT_MANIFEST)}

    agent_reach = items["agent-reach"]
    assert agent_reach.source is not None
    assert agent_reach.source.repo_url == "https://github.com/Panniantong/Agent-Reach.git"
    agent_override = dict(agent_reach.mappings[1].frontmatter_overrides)
    assert agent_override["name"] == "agent-reach"
    assert agent_override["description"].startswith("Use when")

    ponytail = items["ponytail-audit"]
    assert ponytail.source is not None
    assert ponytail.source.repo_url == "https://github.com/DietrichGebert/ponytail.git"
    assert ponytail.mappings[0].source == "skills/ponytail-audit"
    ponytail_override = dict(ponytail.mappings[1].frontmatter_overrides)
    assert ponytail_override["name"] == "ponytail-audit"
    assert ponytail_override["description"].startswith("Use when")


def test_apply_frontmatter_overrides_replaces_folded_field_without_touching_body() -> None:
    source = b"""---
name: Upstream Name
description: >
  Broad upstream trigger.
  More trigger text.
metadata: {\"source\":\"upstream\"}
hidden: true
---

# Body
Keep this body current.
"""

    transformed = skill_upgrader.apply_frontmatter_overrides(
        source,
        (
            ("name", "sample-skill"),
            ("description", "Use when explicitly requested."),
            ("hidden", None),
        ),
    ).decode("utf-8")

    assert "name: sample-skill" in transformed
    assert 'description: "Use when explicitly requested."' in transformed
    assert "Broad upstream trigger" not in transformed
    assert 'metadata: {"source":"upstream"}' in transformed
    assert "hidden:" not in transformed
    assert transformed.endswith("# Body\nKeep this body current.\n")


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


def test_overlay_comparison_ignores_python_runtime_caches(tmp_path: Path) -> None:
    expected_root = tmp_path / "expected"
    local_root = tmp_path / "local"
    for root in (expected_root, local_root):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "search.py").write_text("print('ok')\n", encoding="utf-8")
        (root / "SKILL.md").write_text("current\n", encoding="utf-8")
    cache_dir = local_root / "scripts" / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "search.cpython-313.pyc").write_bytes(b"runtime cache")

    assert skill_upgrader.compare_trees(local_root, expected_root)["match"] is True

    skill_upgrader.sync_tree_exact(expected_root, local_root)
    assert (cache_dir / "search.cpython-313.pyc").is_file()


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


def test_load_local_machine_config_reads_private_skills_manager_settings(tmp_path: Path, monkeypatch) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    public_config_path = tmp_path / "local_machine.json"
    public_config_path.write_text(
        json.dumps(
            {
                "github": {
                    "overlay_transport": "gh_api",
                }
            }
        ),
        encoding="utf-8",
    )
    private_config_path = tmp_path / "local_machine.private.json"
    private_config_path.write_text(
        json.dumps(
            {
                "skills_manager": {
                    "library_remote": "git@github.com:example/private-library.git",
                    "library_branch": "stable",
                    "library_dir": "~/custom/skills",
                    "runtime_dir": "~/.skills-manager/skills",
                    "bootstrap_base_dir": "~/custom",
                    "bootstrap_script": "~/custom/skills/maintenance/bootstrap.py",
                }
            }
        ),
        encoding="utf-8",
    )

    config = skill_upgrader.load_local_machine_config(public_config_path, private_config_path)

    assert config.github_overlay_transport == "gh_api"
    assert config.private_config_path == private_config_path.resolve()
    assert config.library_remote == "git@github.com:example/private-library.git"
    assert config.library_branch == "stable"
    assert config.library_dir == home_dir / "custom" / "skills"
    assert config.runtime_dir == home_dir / ".skills-manager" / "skills"
    assert config.bootstrap_base_dir == home_dir / "custom"
    assert config.bootstrap_script == home_dir / "custom" / "skills" / "maintenance" / "bootstrap.py"


def test_separate_library_relocates_only_manifest_owned_runtime_paths(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    library = tmp_path / "deployment"
    visible = tmp_path / "visible" / "sample"
    external = tmp_path / "external" / "data"
    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=visible,
        managed_path=runtime / "sample",
        mappings=(
            skill_upgrader.Mapping("file", "SKILL.md", "SKILL.md", runtime / "sample"),
            skill_upgrader.Mapping("dir_contents", "data", "data", external),
        ),
    )
    config = skill_upgrader.LocalMachineConfig(library_dir=library, runtime_dir=runtime)

    relocated = skill_upgrader.relocate_managed_items([item], config)[0]

    assert relocated.local_path == visible
    assert relocated.managed_path == library / "sample"
    assert relocated.mappings[0].target_base == library / "sample"
    assert relocated.mappings[1].target_base == external


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


def test_build_overlay_stages_rejects_missing_skill_resource(tmp_path: Path) -> None:
    checkout_root = tmp_path / "checkout"
    skill_root = checkout_root / "skill"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: sample\ndescription: Use when testing.\n---\n\n"
        "Read [the guide](references/guide.md).\n",
        encoding="utf-8",
    )
    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=tmp_path / "managed",
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(skill_upgrader.Mapping(kind="dir_contents", source="skill", target="."),),
    )

    with pytest.raises(FileNotFoundError, match="missing references/guide.md"):
        skill_upgrader.build_overlay_stages(item, checkout_root, tmp_path / "stage")


def test_generated_inline_resource_paths_are_not_treated_as_package_files(
    tmp_path: Path,
) -> None:
    checkout_root = tmp_path / "checkout"
    skill_root = checkout_root / "skill"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: sample\ndescription: Use when testing.\n---\n\n"
        "Create `references/generated-output.png` while running.\n",
        encoding="utf-8",
    )
    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=tmp_path / "managed",
        source=skill_upgrader.SourceRepo(repo_url="https://example.invalid/repo.git", ref="main"),
        mappings=(skill_upgrader.Mapping(kind="dir_contents", source="skill", target="."),),
    )

    stages = skill_upgrader.build_overlay_stages(item, checkout_root, tmp_path / "stage")

    assert (stages[item.target_path] / "SKILL.md").is_file()


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
            skill_upgrader.Mapping(
                kind="file",
                source="docs/SKILL.md",
                target="SKILL.md",
                frontmatter_overrides=(("description", "Use when explicitly requested."),),
            ),
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
    managed_skill = (managed_root / "SKILL.md").read_text(encoding="utf-8")
    assert managed_skill.startswith("---\nname: sample")
    assert 'description: "Use when explicitly requested."' in managed_skill
    assert (source_root / "data" / "catalog.csv").read_text(encoding="utf-8") == "fresh\n"
    assert (projection_root / "SKILL.md").read_text(encoding="utf-8") == "projection\n"


def test_upgrade_overlay_sync_gh_api_stages_all_blobs_before_writing(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed"
    managed_root.mkdir()
    (managed_root / "a.txt").write_text("old-a\n", encoding="utf-8")
    (managed_root / "b.txt").write_text("old-b\n", encoding="utf-8")

    fresh_a = b"fresh-a\n"
    fresh_b = b"fresh-b\n"
    sha_a = skill_upgrader.git_blob_oid_bytes(fresh_a)
    sha_b = skill_upgrader.git_blob_oid_bytes(fresh_b)
    source = skill_upgrader.SourceRepo(repo_url="https://github.com/example/demo.git", ref="main")
    item = skill_upgrader.ManagedItem(
        name="sample",
        kind="overlay_sync",
        local_path=managed_root,
        managed_path=managed_root,
        source=source,
        mappings=(skill_upgrader.Mapping(kind="dir_contents", source="skill", target="."),),
    )
    store = skill_upgrader.RepoCheckoutStore(tmp_path / "checkouts")
    store.github_trees[("example/demo", "main")] = {
        "skill/a.txt": sha_a,
        "skill/b.txt": sha_b,
    }

    def fail_on_second_blob(_source, oid: str) -> bytes:
        if oid == sha_b:
            raise RuntimeError("simulated blob download failure")
        return fresh_a

    store.github_blob = fail_on_second_blob

    with pytest.raises(RuntimeError, match="simulated blob download failure"):
        skill_upgrader.upgrade_overlay_sync(
            item,
            store,
            skill_upgrader.LocalMachineConfig(github_overlay_transport="gh_api"),
        )

    assert (managed_root / "a.txt").read_text(encoding="utf-8") == "old-a\n"
    assert (managed_root / "b.txt").read_text(encoding="utf-8") == "old-b\n"


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


def test_bootstrap_manager_db_runs_script_with_reset_and_base_dir(tmp_path: Path) -> None:
    base_dir = tmp_path / "skills-manager"
    base_dir.mkdir()
    script_path = tmp_path / "bootstrap.py"
    args_log_path = tmp_path / "bootstrap-args.json"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import sys",
                "from pathlib import Path",
                f"Path({str(args_log_path)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')",
                "print(json.dumps({'ok': True}, ensure_ascii=False))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    config = skill_upgrader.LocalMachineConfig(
        bootstrap_base_dir=base_dir,
        bootstrap_script=script_path,
    )

    result = skill_upgrader.bootstrap_manager_db(config)

    assert json.loads(args_log_path.read_text(encoding="utf-8")) == [
        "--base-dir",
        str(base_dir),
        "--reset",
    ]
    assert result["base_dir"] == str(base_dir)
    assert result["script"] == str(script_path)
    assert result["reset"] is True


def test_library_pull_clones_repo_and_runs_bootstrap(tmp_path: Path) -> None:
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

    base_dir = tmp_path / "skills-manager"
    library_dir = base_dir / "skills"
    base_dir.mkdir()
    script_path = tmp_path / "bootstrap.py"
    marker_path = tmp_path / "bootstrap-ran.txt"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import sys",
                "from pathlib import Path",
                f"Path({str(marker_path)!r}).write_text(' '.join(sys.argv[1:]), encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    config = skill_upgrader.LocalMachineConfig(
        library_dir=library_dir,
        runtime_dir=library_dir,
        library_remote=str(remote_bare),
        library_branch="main",
        bootstrap_base_dir=base_dir,
        bootstrap_script=script_path,
    )

    result = skill_upgrader.library_pull(config)

    assert result["action"] == "clone"
    assert result["changed"] is True
    assert (library_dir / "README.md").read_text(encoding="utf-8") == "seed\n"
    assert marker_path.read_text(encoding="utf-8") == f"--base-dir {base_dir} --reset"

    marker_path.unlink()
    separated = skill_upgrader.LocalMachineConfig(
        library_dir=library_dir,
        runtime_dir=base_dir / "runtime",
        library_remote=str(remote_bare),
        library_branch="main",
        bootstrap_base_dir=base_dir,
        bootstrap_script=script_path,
    )
    separated_result = skill_upgrader.library_pull(separated)
    assert separated_result["bootstrap"]["status"] == "skipped_separate_runtime"
    assert not marker_path.exists()


def test_library_push_commits_dirty_library_and_pushes(tmp_path: Path) -> None:
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

    library_dir = tmp_path / "library"
    subprocess.run(["git", "clone", str(remote_bare), str(library_dir)], check=True, text=True, capture_output=True)
    configure_git_user(library_dir)
    (library_dir / "README.md").write_text("seed\nlocal change\n", encoding="utf-8")

    config = skill_upgrader.LocalMachineConfig(
        library_dir=library_dir,
        library_remote=str(remote_bare),
        library_branch="main",
    )

    result = skill_upgrader.library_push(config, message="sync library")

    assert result["changed"] is True
    assert result["commit_created"] is True
    assert run_git(["log", "-1", "--pretty=%s"], cwd=library_dir) == "sync library"

    verify_repo = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote_bare), str(verify_repo)], check=True, text=True, capture_output=True)
    assert (verify_repo / "README.md").read_text(encoding="utf-8") == "seed\nlocal change\n"


def test_library_push_rejects_repo_behind_upstream(tmp_path: Path) -> None:
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

    library_dir = tmp_path / "library"
    subprocess.run(["git", "clone", str(remote_bare), str(library_dir)], check=True, text=True, capture_output=True)
    configure_git_user(library_dir)

    updater_repo = tmp_path / "updater"
    subprocess.run(["git", "clone", str(remote_bare), str(updater_repo)], check=True, text=True, capture_output=True)
    configure_git_user(updater_repo)
    (updater_repo / "README.md").write_text("seed\nupstream\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=updater_repo)
    run_git(["commit", "-m", "upstream"], cwd=updater_repo)
    run_git(["push", "origin", "main"], cwd=updater_repo)

    (library_dir / "README.md").write_text("seed\nlocal dirty\n", encoding="utf-8")
    config = skill_upgrader.LocalMachineConfig(
        library_dir=library_dir,
        library_remote=str(remote_bare),
        library_branch="main",
    )

    try:
        skill_upgrader.library_push(config, message="should fail")
    except RuntimeError as exc:
        assert "behind" in str(exc)
    else:
        raise AssertionError("expected library_push to reject behind repository")
