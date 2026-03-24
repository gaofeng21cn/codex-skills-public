# Skill Upgrader Design

## Goal

Add a reusable `skill-upgrader` skill to the public skills repository so future Codex sessions can inspect and upgrade managed local skills plus the local `superpowers` repo without re-deriving upstream mappings by hand.

## Scope

Included in v1:

- `~/.codex/superpowers`
- `~/.codex/skills/agent-browser`
- `~/.codex/skills/defuddle`
- `~/.codex/skills/json-canvas`
- `~/.codex/skills/mineru-document-extractor`
- `~/.codex/skills/obsidian-bases`
- `~/.codex/skills/obsidian-cli`
- `~/.codex/skills/obsidian-markdown`
- `~/.codex/skills/pdf`
- `~/.codex/skills/ui-ux-pro-max`

Excluded from v1:

- `~/.codex/skills/.system/*`
- symlinked public/private skills such as `apple-apps` and `mail-triage`
- automatic discovery of unknown skill origins
- public/private skill repo self-upgrades

## Non-Goals

- No heuristic source detection.
- No best-effort merging of local edits into managed skills.
- No hidden fallback to guessed GitHub repositories.

## Approach

The skill will be a small public multi-file skill:

- `SKILL.md` explains when to use it and the fixed command surface.
- `scripts/skill_upgrader.py` performs `inspect` and `upgrade`.
- `sources.json` is the single source of truth for managed upgrade targets.
- `tests/test_skill_upgrader.py` validates manifest parsing, overlay staging, exact sync behavior, and git-repo status detection.

The script will support two managed target kinds:

1. `git_repo`
   Used for local repos that already track a branch, such as `~/.codex/superpowers`.

2. `overlay_sync`
   Used for local skill directories that must exactly match explicit upstream file mappings.

## Data Model

Each managed target is explicitly declared in `sources.json`.

For `git_repo`:

- `name`
- `kind`
- `local_path`
- `remote`
- `branch`

For `overlay_sync`:

- `name`
- `kind`
- `local_path`
- `source.repo_url`
- `source.ref`
- `mappings`

Each mapping is either:

- `file`: copy one exact file from checkout to one exact destination path
- `dir_contents`: copy the contents of one source directory into one destination directory

This covers:

- plain upstream skill directory mirrors
- `ui-ux-pro-max`, which needs `SKILL.md` from one path and data/scripts/templates from another path

## Command Surface

The script will expose:

- `python3 scripts/skill_upgrader.py inspect`
- `python3 scripts/skill_upgrader.py inspect --only agent-browser`
- `python3 scripts/skill_upgrader.py upgrade`
- `python3 scripts/skill_upgrader.py upgrade --only superpowers --only ui-ux-pro-max`

Output is JSON so the agent can consume it directly.

## Inspection Semantics

`git_repo` inspection:

- fetch configured remote
- compare `HEAD`, upstream head, and merge-base
- classify state as `current`, `behind`, `ahead`, `diverged`, `dirty-current`, or `behind-dirty`

`overlay_sync` inspection:

- clone each explicit upstream repo once per run into a temp workspace
- materialize an expected stage tree from the declared mappings
- compare local tree and expected tree using file hashes

## Upgrade Semantics

For `git_repo`:

- allow upgrade only when the repo is strictly behind and clean
- execute `git pull --ff-only`

For `overlay_sync`:

- rebuild the expected stage tree
- apply an exact tree sync to the local path
- remove local files not present in the expected stage tree

## Safety Rules

- Never upgrade anything not declared in `sources.json`.
- Never infer a repo URL from a skill name.
- Never try to preserve unmanaged local drift inside managed skill directories.
- Report blocked upgrade states explicitly instead of falling back to partial behavior.

## Verification

Required checks:

- repo validator: `python3 scripts/validate_skills.py`
- unit tests: `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q`

Local integration check:

- create a symlink from `~/.codex/skills/skill-upgrader` to the repo skill directory
- run `python3 .../skill_upgrader.py inspect --only superpowers`
