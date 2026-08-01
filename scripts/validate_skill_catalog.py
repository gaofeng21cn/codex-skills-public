#!/usr/bin/env python3
"""Validate the OPL Skills classification catalog and exact named presets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "contracts/skill-catalog.json"
SOFTWARE_DESIGN_METHODS = [
    "architect-and-simplify",
    "zoom-out",
    "improve-codebase-architecture",
    "grill-with-docs",
    "prototype",
]
SOFTWARE_ARCHITECTURE_LENSES = [
    "book-aposd",
    "book-clean-architecture",
    "book-ddia",
    "book-domain-driven-design",
    "book-legacy-code",
    "book-release-it",
]
DEVELOPMENT_COMPLETE = [*SOFTWARE_DESIGN_METHODS, *SOFTWARE_ARCHITECTURE_LENSES]


def load(path: Path = CATALOG_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("skill catalog must be an object")
    return payload


def validate(payload: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "opl_skill_catalog.v1":
        errors.append("unsupported schema")
    if payload.get("classification_policy") != "metadata_only_never_implies_installation":
        errors.append("classification must not imply installation")
    if payload.get("preset_selection_policy") != "explicit_named_preset_only":
        errors.append("presets must require explicit named selection")
    if payload.get("default_preset") is not None:
        errors.append("default_preset must be null")

    skills = payload.get("skills")
    presets = payload.get("presets")
    if not isinstance(skills, dict) or not skills:
        return [*errors, "skills must be a non-empty object"]
    if not isinstance(presets, dict) or not presets:
        return [*errors, "presets must be a non-empty object"]

    source_ids = {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}
    catalog_ids = set(skills)
    if source_ids != catalog_ids:
        errors.append(
            "catalog differs from source: "
            f"missing={sorted(source_ids - catalog_ids)} extra={sorted(catalog_ids - source_ids)}"
        )
    for skill_id, entry in sorted(skills.items()):
        if not isinstance(entry, dict):
            errors.append(f"{skill_id}: entry must be an object")
            continue
        if entry.get("source_path") != f"skills/{skill_id}":
            errors.append(f"{skill_id}: source_path must bind the Skill ID")
        categories = entry.get("categories")
        if not isinstance(categories, list) or not categories:
            errors.append(f"{skill_id}: categories must be non-empty")

    design_methods = {
        skill_id
        for skill_id, entry in skills.items()
        if isinstance(entry, dict) and "software-design-method" in entry.get("categories", [])
    }
    architecture_lenses = {
        skill_id
        for skill_id, entry in skills.items()
        if isinstance(entry, dict) and "software-architecture-lens" in entry.get("categories", [])
    }
    if design_methods != set(SOFTWARE_DESIGN_METHODS):
        errors.append("software-design-method classification drifted")
    if architecture_lenses != set(SOFTWARE_ARCHITECTURE_LENSES):
        errors.append("software-architecture-lens classification drifted")

    wildcard_tokens = {"*", "all", "development", "software-*", "book-*"}
    for preset_id, preset in sorted(presets.items()):
        if not isinstance(preset, dict):
            errors.append(f"{preset_id}: preset must be an object")
            continue
        if preset.get("selection") != "explicit_only":
            errors.append(f"{preset_id}: selection must be explicit_only")
        if preset.get("expansion") != "exact_members_only_no_category_or_wildcard_expansion":
            errors.append(f"{preset_id}: expansion policy is invalid")
        members = preset.get("members")
        if not isinstance(members, list) or not members:
            errors.append(f"{preset_id}: members must be non-empty")
            continue
        if len(members) != len(set(members)):
            errors.append(f"{preset_id}: members must be unique")
        invalid = [member for member in members if member not in skills]
        if invalid:
            errors.append(f"{preset_id}: unknown members {invalid}")
        wildcard = [member for member in members if member in wildcard_tokens or "*" in member]
        if wildcard:
            errors.append(f"{preset_id}: wildcard or category expansion is forbidden {wildcard}")

    development = presets.get("development-complete", {})
    if development.get("members") != DEVELOPMENT_COMPLETE:
        errors.append("development-complete members drifted")
    return errors


def main() -> int:
    errors = validate(load())
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
