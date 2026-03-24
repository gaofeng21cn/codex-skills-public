# Skill Upgrader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public `skill-upgrader` skill that can inspect and upgrade managed local skills plus `~/.codex/superpowers` from explicit upstream sources.

**Architecture:** Store managed upgrade targets in a JSON manifest, implement a Python CLI for `inspect` and `upgrade`, and verify behavior with deterministic unit tests that avoid live network dependencies. Use exact overlay syncing for managed skill directories and fast-forward-only pulls for managed git repos.

**Tech Stack:** Python 3, `argparse`, `json`, `pathlib`, `subprocess`, `tempfile`, `hashlib`, `pytest`

---

### Task 1: Add Failing Tests

**Files:**
- Create: `skills/skill-upgrader/tests/test_skill_upgrader.py`

- [ ] **Step 1: Write failing tests for manifest loading, overlay staging, exact sync, and git status inspection**
- [ ] **Step 2: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q` and confirm failures**

### Task 2: Implement CLI and Manifest

**Files:**
- Create: `skills/skill-upgrader/scripts/skill_upgrader.py`
- Create: `skills/skill-upgrader/sources.json`

- [ ] **Step 1: Implement manifest parsing and path expansion**
- [ ] **Step 2: Implement overlay stage construction and exact tree comparison**
- [ ] **Step 3: Implement exact tree sync**
- [ ] **Step 4: Implement managed git repo inspection and fast-forward upgrade**
- [ ] **Step 5: Implement `inspect` and `upgrade` subcommands with JSON output**
- [ ] **Step 6: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q` and confirm all tests pass**

### Task 3: Add Skill Documentation

**Files:**
- Create: `skills/skill-upgrader/SKILL.md`

- [ ] **Step 1: Document trigger conditions, command surface, and safety boundaries**
- [ ] **Step 2: Ensure frontmatter passes repo validation rules**

### Task 4: Update Repository Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add `skill-upgrader` to current skills**
- [ ] **Step 2: Add install and local validation commands**

### Task 5: Wire Local Codex Access

**Files:**
- Create symlink: `~/.codex/skills/skill-upgrader` -> `skills/skill-upgrader`

- [ ] **Step 1: Create or refresh the local symlink**
- [ ] **Step 2: Run `python3 skills/skill-upgrader/scripts/skill_upgrader.py inspect --only superpowers` as a smoke check**

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run `python3 scripts/validate_skills.py`**
- [ ] **Step 2: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q`**
- [ ] **Step 3: Re-run the smoke inspection command and confirm JSON output**
