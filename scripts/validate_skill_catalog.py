#!/usr/bin/env python3
"""Validate the OPL Skills source catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "contracts/skill-catalog.json"


def load(path: Path = CATALOG_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("skill catalog must be an object")
    return payload


def validate(payload: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "opl_skill_catalog.v2":
        errors.append("unsupported schema")
    if payload.get("classification_policy") != "metadata_only_never_implies_installation":
        errors.append("classification must not imply installation")

    skills = payload.get("skills")
    if not isinstance(skills, dict) or not skills:
        return [*errors, "skills must be a non-empty object"]

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
    return errors


def main() -> int:
    errors = validate(load())
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
