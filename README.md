# OPL Skills

Optional public enhancements for OPL Flow and ordinary Codex installations,
maintained by `gaofeng21cn`. The physical repository remains
`codex-skills-public` until the coordinated rename to `opl-skills` updates every
installer, manifest, remote, and live node.

## Repository Role

OPL Skills is not a required third layer of the OPL Flow product. The public
architecture is
[`OPL Reusable Development Workflow Architecture`](https://github.com/gaofeng21cn/opl-flow/blob/main/docs/reusable-workflow-architecture.md).

- Workflow-coupled Skills move into OPL Flow and install with the product.
- Independently useful, sanitized Skills remain here as optional enhancements.
- Personal Skills move into the owner's private OPL Instance.

During migration, the private
[`codex-management-boundaries.json`](https://github.com/gaofeng21cn/codex-skills-private/blob/main/contracts/codex-management-boundaries.json)
remains the current physical source map and `contracts/skill-reference.json`
remains the current owner-install inventory. They do not override the target
public architecture.

Upstream-owned skills such as Ponytail, OpenAI curated skills, and Agent Reach
are not copied or rewritten here. Install and update them directly through
their owner-supported channels.

## Skills

| Group | Skills |
| --- | --- |
| Development entry points | `architect-and-simplify`, `develop-and-deliver`, `recover-codex-tasks`, `task-mode-gate` |
| Architecture and reliability lenses | `book-aposd`, `book-clean-architecture`, `book-ddia`, `book-domain-driven-design`, `book-legacy-code`, `book-release-it`, `grill-with-docs`, `improve-codebase-architecture`, `prototype`, `zoom-out` |
| Artifact and learning workflows | `academic-defense-prep`, `evidence-bound-closeout`, `external-learning-landing`, `xiaohongshu-repo-scout` |
| Local application adapters | `apple-apps`, `mail-triage` |

Some skills adapt MIT-licensed upstream work. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Install

Install one skill with the bundled Codex installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/<skill-name>
```

Use the current physical repository name until the rename phase publishes and
reads back `gaofeng21cn/opl-skills`.

For the multi-machine environment, consult
`gaofeng21cn/codex-skills-private:contracts/skill-reference.json` and install
from the named owner. `codex-machine-sync` reports presence but does not install,
pin, update, copy, or delete skills. Private repository URLs and machine
configuration belong in local untracked configuration, never in this
repository.

## Development

```bash
python scripts/validate_skills.py
pytest skills/apple-apps/tests/test_mail_meta.py -q
```

Each skill must remain independently installable. Supporting scripts and tests
belong inside the owning skill. Public source must not contain credentials,
machine inventories, private remotes, or absolute personal paths.
