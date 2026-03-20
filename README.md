# codex-skills-public

Public Codex skills maintained as a multi-skill repository.

## Layout

- `skills/`: installable skill directories
- `scripts/`: repo-local validation helpers used by CI
- `.github/workflows/`: GitHub Actions workflows

## Current Skills

- `apple-apps`: Apple Mail automation and search helpers for Codex

## Install

Install a skill from this repo with Codex's GitHub installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/apple-apps
```

## Local Validation

```bash
python scripts/validate_skills.py
pytest skills/apple-apps/tests/test_mail_meta.py -q
```
