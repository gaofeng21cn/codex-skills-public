# Skill Upgrader Skills Manager Design

## Goal

Extend `skill-upgrader` so it can manage the real operating mode used with `xingkongliang/skills-manager`: deterministic upstream refresh into `~/.skills-manager/skills`, Git-backed library sync across machines, and metadata bootstrap for the local `skills-manager.db`.

## Scope

Included in this iteration:

- keep existing `inspect` and `upgrade` behavior unchanged for managed upstream sources
- add `library-push` for committing and pushing the central skills library repo
- add `library-pull` for cloning or fast-forwarding the central skills library repo and then rebuilding Skills Manager metadata
- add `bootstrap-manager-db` as a wrapper around `maintenance/bootstrap_xingkongliang_db.py`
- load sensitive library settings from a machine-local private config file instead of public repo files

Excluded from this iteration:

- no per-skill Git registration inside Skills Manager
- no automatic merge, rebase, or conflict resolution for library sync
- no secret or private remote committed to the public repository

## Constraints

- The public repo must not contain the private library remote URL.
- The CLI must keep using explicit paths and exact git state checks.
- Commands must fail on dirty, behind, or diverged states instead of attempting fallback behavior.

## Approach

`skill_upgrader.py` remains the single entrypoint. It gains a second responsibility layer for Skills Manager operations:

1. upstream layer
   - `inspect`
   - `upgrade`

2. library layer
   - `library-push`
   - `library-pull`
   - `bootstrap-manager-db`

Configuration is split into:

- public `local_machine.json`
  - safe transport defaults only
- private `~/.skills-manager/local_machine.private.json`
  - library remote and optional local overrides

If a private config value is absent, the CLI may use deterministic local defaults such as `~/.skills-manager/skills` and `~/.skills-manager`, but it must never guess a private remote.

## Data Model

Extend `LocalMachineConfig` with a `skills_manager` section:

- `private_config_path`
- `library_dir`
- `library_remote`
- `library_branch`
- `bootstrap_base_dir`
- `bootstrap_script`

Expected private config shape:

```json
{
  "skills_manager": {
    "library_remote": "git@github.com:owner/repo.git",
    "library_branch": "main"
  }
}
```

`library_dir`, `bootstrap_base_dir`, and `bootstrap_script` default to:

- `~/.skills-manager/skills`
- `~/.skills-manager`
- `~/.skills-manager/skills/maintenance/bootstrap_xingkongliang_db.py`

## Command Semantics

### `library-push`

- require an existing git repo at `library_dir`
- optionally verify the configured remote matches the repo remote
- fetch remote branch
- fail if local branch is behind or diverged from upstream
- if the worktree is dirty, create one commit with a user-provided or generated message
- push current branch to the configured remote and branch

### `library-pull`

- if `library_dir` does not exist, clone the configured remote and branch
- otherwise require a clean git repo and fast-forward it when behind
- fail on dirty, ahead, or diverged states
- run `bootstrap-manager-db` after clone, no-op pull, or fast-forward pull unless explicitly skipped

### `bootstrap-manager-db`

- run the configured bootstrap script with `--base-dir`
- default to `--reset` so Skills Manager metadata exactly matches the central library
- support opting out with `--no-reset`

## Error Handling

- missing private remote: fail with a concrete path to the expected private config file
- missing library repo: fail for `library-push`, clone for `library-pull`
- remote mismatch: fail and print both expected and actual remote URLs
- missing bootstrap script: fail without attempting alternate bootstrap logic

## Verification

Required checks:

- `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q`
- targeted CLI smoke checks against temporary git repos in tests
- local smoke:
  - `python3 skills/skill-upgrader/scripts/skill_upgrader.py library-pull --skip-bootstrap`
  - `python3 skills/skill-upgrader/scripts/skill_upgrader.py bootstrap-manager-db`
