---
name: skill-upgrader
description: Use when inspecting or upgrading managed local Codex skills against explicit upstream sources, or when syncing a Skills Manager central library across machines without re-deriving source mappings by hand.
---

# Skill Upgrader

## Overview

This skill manages two related jobs:

- refresh a fixed set of managed local skills from explicit upstream sources
- sync a `Skills Manager` central library repo in `~/.skills-manager/skills` across machines

It is for deterministic upgrade and sync, not source discovery.

When a visible install path is a symlink or projected skill view, do not upgrade the symlink entrypoint blindly. Use item-level `managed_path` when the whole skill has one real source-of-truth directory, or use mapping-level `target_base` when different parts of the skill belong to different real directories.

This skill is not the owner for the Codex CLI binary, Codex plugin marketplaces/cache, OPL domain plugin projections, repository dependency locks, or vulnerability remediation. For broad "update everything" requests, use this skill for the managed skill library slice, then verify the other surfaces through their native owner commands such as `codex update`, `codex plugin marketplace upgrade`, `opl system startup-maintenance --json`, repo lockfile installers, and repo health checks.

## When to Use

- User asks which installed skills can be upgraded
- User asks to upgrade managed skills to the latest known upstream versions
- User wants one machine to refresh skills and all other machines to stay in sync through `Skills Manager`
- You want a fast, repeatable alternative to manually re-mapping skill origins

Do not use this skill to guess where an unknown skill came from.

## Command Surface

The helper lives next to this skill at `scripts/skill_upgrader.py`.

Inspect managed targets:

```bash
python3 scripts/skill_upgrader.py inspect
python3 scripts/skill_upgrader.py inspect --only agent-browser --only ui-ux-pro-max
```

Upgrade managed targets:

```bash
python3 scripts/skill_upgrader.py upgrade
python3 scripts/skill_upgrader.py upgrade --only agent-browser --only ui-ux-pro-max
```

Sync the `Skills Manager` central library:

```bash
python3 scripts/skill_upgrader.py library-push
python3 scripts/skill_upgrader.py library-pull
python3 scripts/skill_upgrader.py bootstrap-manager-db
```

Local machine config:

```bash
python3 scripts/skill_upgrader.py inspect --local-config local_machine.json
python3 scripts/skill_upgrader.py upgrade --local-config local_machine.json
python3 scripts/skill_upgrader.py library-pull --private-config ~/.skills-manager/local_machine.private.json
```

## Workflow

Create this private config once per machine:

```json
{
  "skills_manager": {
    "library_remote": "git@github.com:<owner>/<private-library>.git",
    "library_branch": "main"
  }
}
```

Save it at `~/.skills-manager/local_machine.private.json`.

Recommended day-to-day usage:

1. On the machine that refreshes upstream skills:
   - run `python3 scripts/skill_upgrader.py upgrade`
   - run `python3 scripts/skill_upgrader.py inspect` again and read back `local_state`, `action`, `dirty`, and `changed`
   - then run `python3 scripts/skill_upgrader.py library-push`
2. On every other machine:
   - run `python3 scripts/skill_upgrader.py library-pull`
3. If `Skills Manager` metadata looks stale on any machine:
   - run `python3 scripts/skill_upgrader.py bootstrap-manager-db`

On this Mac, `local_machine.json` records the verified GitHub fast path:
- `git_repo` items fetch via GitHub SSH and fast-forward from `FETCH_HEAD`
- `overlay_sync` items compare/sync via `gh api` tree/blob data instead of `git clone`
- If the local config file is absent, the helper falls back to the original `git fetch` / `git clone` behavior

Sensitive settings such as the private library remote must stay in `~/.skills-manager/local_machine.private.json`, not in this public repo.

## Safety Rules

- Managed targets are defined only in `sources.json`.
- The helper must not infer repository URLs from skill names.
- Do not add Codex CLI, plugin marketplace, OPL module, npm audit, or repo dependency upgrade logic to this helper unless those surfaces first define explicit source mappings and safety rules comparable to `sources.json`.
- If a skill is installed through another manager, `managed_path` or mapping-level `target_base` must point to the directory that owns the files, not a symlinked projection.
- Use mapping-level `target_base` when a single skill spans multiple real directories, such as a projected `SKILL.md` plus separate source-of-truth `data/`, `scripts/`, or `templates/`.
- If an overlay target path is dirty inside a git worktree, inspect must report that state and block upgrade instead of overwriting local changes.
- If a target is dirty, ahead, or diverged, report that state instead of forcing an upgrade.
- `overlay_sync` targets are exact mirrors of declared upstream mappings. Local drift in those directories is removed on upgrade.
- `local_overrides` entries are intentional local files that inspect ignores and upgrade preserves; use them sparingly for prompt-budget or machine-specific installed-skill adaptations.
- `library-pull` only clones or fast-forwards. It must not auto-merge.
- `library-push` must fail if the library repo is behind or diverged.
- `bootstrap-manager-db` rebuilds `skills-manager.db` from the central library and defaults to `--reset`.

## Update Run Triage

- If `upgrade` changes a target but reports `dirty-current`, run `inspect` after any required `library-push`; the library commit can clear the dirty readback.
- If a target remains dirty, ahead, diverged, or different-dirty, do not force it. Report the target owner and the exact target path from the JSON output.
- If `codex doctor`, `codex update`, `codex plugin`, OPL startup maintenance, or a repo test fails during a broad update run, classify it as an adjacent owner-surface issue, not a `skill-upgrader` failure.
- If installed Codex plugin cache content matters, read back the actual cache or marketplace path. Source repo currentness alone is not installed-cache evidence.

## Current Managed Targets

- `agent-browser`
- `defuddle`
- `mineru-document-extractor`
- `pdf`
- `officecli`
- `ui-ux-pro-max`
