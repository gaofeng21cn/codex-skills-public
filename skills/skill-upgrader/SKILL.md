---
name: skill-upgrader
description: Use when inspecting or upgrading managed local Codex skills and the local superpowers repo against explicit upstream sources, especially when you want to avoid re-deriving source mappings by hand.
---

# Skill Upgrader

## Overview

This skill manages a fixed set of local Codex skills plus `~/.codex/superpowers` using an explicit source manifest. It is for deterministic inspection and upgrade, not source discovery.

When a visible install path is a symlink or projected skill view, do not upgrade the symlink entrypoint blindly. Use item-level `managed_path` when the whole skill has one real source-of-truth directory, or use mapping-level `target_base` when different parts of the skill belong to different real directories.

## When to Use

- User asks which installed skills can be upgraded
- User asks to upgrade managed skills to the latest known upstream versions
- You want a fast, repeatable alternative to manually re-mapping skill origins

Do not use this skill to guess where an unknown skill came from.

## Command Surface

The helper lives next to this skill at `scripts/skill_upgrader.py`.

Inspect managed targets:

```bash
python3 scripts/skill_upgrader.py inspect
python3 scripts/skill_upgrader.py inspect --only superpowers
python3 scripts/skill_upgrader.py inspect --only agent-browser --only ui-ux-pro-max
```

Upgrade managed targets:

```bash
python3 scripts/skill_upgrader.py upgrade
python3 scripts/skill_upgrader.py upgrade --only superpowers
python3 scripts/skill_upgrader.py upgrade --only agent-browser --only ui-ux-pro-max
```

Local machine overrides:

```bash
python3 scripts/skill_upgrader.py inspect --local-config local_machine.json
python3 scripts/skill_upgrader.py upgrade --local-config local_machine.json
```

## Workflow

1. Run `inspect` first.
2. Read the JSON results.
3. Upgrade only items with `"action": "upgrade"`.
4. Re-run `inspect` to confirm they are now current.

On this Mac, `local_machine.json` records the verified GitHub fast path:
- `git_repo` items fetch via GitHub SSH and fast-forward from `FETCH_HEAD`
- `overlay_sync` items compare/sync via `gh api` tree/blob data instead of `git clone`
- If the local config file is absent, the helper falls back to the original `git fetch` / `git clone` behavior

## Safety Rules

- Managed targets are defined only in `sources.json`.
- The helper must not infer repository URLs from skill names.
- If a skill is installed through another manager, `managed_path` or mapping-level `target_base` must point to the directory that owns the files, not a symlinked projection.
- Use mapping-level `target_base` when a single skill spans multiple real directories, such as a projected `SKILL.md` plus separate source-of-truth `data/`, `scripts/`, or `templates/`.
- If an overlay target path is dirty inside a git worktree, inspect must report that state and block upgrade instead of overwriting local changes.
- If a target is dirty, ahead, or diverged, report that state instead of forcing an upgrade.
- `overlay_sync` targets are exact mirrors of declared upstream mappings. Local drift in those directories is removed on upgrade.

## Current Managed Targets

- `superpowers`
- `agent-browser`
- `defuddle`
- `json-canvas`
- `mineru-document-extractor`
- `obsidian-bases`
- `obsidian-cli`
- `obsidian-markdown`
- `pdf`
- `ui-ux-pro-max`
