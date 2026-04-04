# Skill Upgrader Skills Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `skill-upgrader` so it can publish, pull, and bootstrap the `Skills Manager` central library workflow without exposing private repo details in the public source repo.

**Architecture:** Keep `inspect` and `upgrade` unchanged for upstream source refresh, then add a second command layer for the central library repo. Sensitive settings load from a machine-local private config file, while public defaults stay in the tracked `local_machine.json`.

**Tech Stack:** Python 3, `argparse`, `json`, `pathlib`, `subprocess`, `tempfile`, `hashlib`, `pytest`

---

### Task 1: Add Failing Tests For Skills Manager Flow

**Files:**
- Modify: `skills/skill-upgrader/tests/test_skill_upgrader.py`

- [ ] **Step 1: Write failing tests for private config loading, `library-pull`, `library-push`, and `bootstrap-manager-db`**
- [ ] **Step 2: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q` and confirm failures**

### Task 2: Extend Runtime Configuration And CLI

**Files:**
- Modify: `skills/skill-upgrader/scripts/skill_upgrader.py`

- [ ] **Step 1: Add private config loading and resolved Skills Manager defaults**
- [ ] **Step 2: Add `library-push`, `library-pull`, and `bootstrap-manager-db` subcommands**
- [ ] **Step 3: Implement exact git-state checks for clone, fast-forward pull, commit, and push**
- [ ] **Step 4: Implement bootstrap wrapper execution with deterministic arguments**
- [ ] **Step 5: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q` and confirm all tests pass**

### Task 3: Update Skill Documentation

**Files:**
- Modify: `skills/skill-upgrader/SKILL.md`

- [ ] **Step 1: Document the new library workflow and private config file path**
- [ ] **Step 2: Reduce the user-facing workflow to the smallest command set needed per machine role**

### Task 4: Update Repository Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the `skill-upgrader` description to include Skills Manager library sync**

### Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run `pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q`**
- [ ] **Step 2: Run `python3 skills/skill-upgrader/scripts/skill_upgrader.py inspect --only superpowers`**
- [ ] **Step 3: Run local smoke checks for `library-pull --skip-bootstrap` and `bootstrap-manager-db` with the configured machine paths**
