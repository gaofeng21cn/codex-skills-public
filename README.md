# OPL Skills

Independently useful public Codex workflows maintained by `gaofeng21cn`. The
canonical repository is `gaofeng21cn/opl-skills`.

## Repository Role

OPL-owned software-development Skills live in the OPL Flow Plugin and share one
installation and update lifecycle. This repository keeps only reusable
non-development workflows that remain useful without OPL Flow:

| Group | Skills |
| --- | --- |
| Academic delivery | `academic-defense-prep` |
| Artifact evidence | `evidence-bound-closeout` |
| External learning | `external-learning-landing`, `xiaohongshu-repo-scout` |
| Local app adapters | `apple-mail`, `mail-triage` |

Personal Skills belong in the owner's private OPL Instance. OpenAI and
third-party Skills are installed and updated through their native owner channel;
this repository does not copy them.

## Catalog

[`contracts/skill-catalog.json`](contracts/skill-catalog.json) maps each current
Skill ID to its source path and browsing category. Categories never install
Skills. There are no presets or wildcard installation rules.

## Install

Install only the requested Skill IDs with the bundled Codex installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/opl-skills \
  --path skills/<skill-name>
```

The private OPL Instance may record an explicit desired inventory for multiple
machines. Each node still installs from this owner; Fleet reports presence and
does not copy Skill bytes between machines.

## Development

```bash
python scripts/validate_skills.py
python -m unittest tests/test_validate_skill_catalog.py
pytest skills/apple-mail/tests/test_mail_meta.py -q
```

Each Skill must remain independently installable. Public source must not contain
credentials, machine inventories, private remotes, or absolute personal paths.
