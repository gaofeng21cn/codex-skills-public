# OPL Skills

Optional public enhancements for OPL Flow and ordinary Codex installations,
maintained by `gaofeng21cn`. The canonical repository is
`gaofeng21cn/opl-skills`.

## Repository Role

OPL Skills is not a required third layer of the OPL Flow product. The public
architecture is
[`OPL Reusable Development Workflow Architecture`](https://github.com/gaofeng21cn/opl-flow/blob/main/docs/reusable-workflow-architecture.md).

- Workflow-coupled Skills move into OPL Flow and install with the product.
- Independently useful, sanitized Skills remain here as optional enhancements.
- Personal Skills move into the owner's private OPL Instance.

The private
[`codex-management-boundaries.json`](https://github.com/gaofeng21cn/opl-instance-gaofeng/blob/main/contracts/codex-management-boundaries.json)
records the current source map and `contracts/skill-reference.json` records the
current owner-install inventory. They do not override the target public
architecture.

Upstream-owned skills such as Ponytail, OpenAI curated skills, and Agent Reach
are not copied or rewritten here. Install and update them directly through
their owner-supported channels.

## Catalog And Presets

[`contracts/skill-catalog.json`](contracts/skill-catalog.json) is the
machine-readable catalog. Skill categories describe what a Skill is useful for;
they never imply installation. There is no default preset and no category or
wildcard expansion.

The named `development-complete` preset is selected explicitly and resolves to
exactly eleven Skills: five software-design methods (`architect-and-simplify`,
`zoom-out`, `improve-codebase-architecture`, `grill-with-docs`, `prototype`)
plus the six `book-*` architecture and reliability lenses. The two sets remain
separately classified so discovery is precise, while the preset intentionally
combines them for a complete development enhancement installation.

## Skills

| Group | Skills |
| --- | --- |
| Software-design methods | `architect-and-simplify`, `zoom-out`, `improve-codebase-architecture`, `grill-with-docs`, `prototype` |
| Software architecture and reliability lenses | `book-aposd`, `book-clean-architecture`, `book-ddia`, `book-domain-driven-design`, `book-legacy-code`, `book-release-it` |
| Artifact and learning workflows | `academic-defense-prep`, `evidence-bound-closeout`, `external-learning-landing`, `xiaohongshu-repo-scout` |
| Local application adapters | `apple-apps`, `mail-triage` |

These groups are discovery metadata, not install profiles. Selecting either
group name installs nothing; only an explicit named preset or explicit Skill
IDs produce an install selection.

`develop-and-deliver`, `recover-codex-tasks`, and `task-mode-gate` are OPL
Flow core Skills. Install or update OPL Flow to receive them from their single
public source owner; do not install legacy projections from this enhancement
pack.

Some skills adapt MIT-licensed upstream work. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Install

Install one skill with the bundled Codex installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/opl-skills \
  --path skills/<skill-name>
```

For the multi-machine environment, resolve a named preset through the catalog,
then consult
`gaofeng21cn/opl-instance-gaofeng:contracts/skill-reference.json` and install
from the named owner. `codex-machine-sync` reports presence but does not install,
pin, update, copy, or delete skills. Private repository URLs and machine
configuration belong in local untracked configuration, never in this
repository.

## Development

```bash
python scripts/validate_skills.py
python -m unittest tests/test_validate_skill_catalog.py
pytest skills/apple-apps/tests/test_mail_meta.py -q
```

Each skill must remain independently installable. Supporting scripts and tests
belong inside the owning skill. Public source must not contain credentials,
machine inventories, private remotes, or absolute personal paths.
