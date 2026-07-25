# codex-skills-public

Public source repository for reusable Codex skills maintained by
`gaofeng21cn`.

## Repository Role

This repository is one of three deliberately separate layers:

- `codex-skills-public`: public, reusable skill development source
- `codex-skills-private`: private or machine-specific skill development source
- `ai-skills-library`: machine-readable owner and installation reference

The paired `public` / `private` names are intentional. They state the access and
reuse boundary directly; changing them to broader names such as
`codex-skills` or `codex-skills-internal` would make that boundary less obvious
without changing the architecture.

Upstream-owned skills such as Ponytail, OpenAI curated skills, and Agent Reach
are not copied or rewritten here. Install and update them directly through
their owner-supported channels.

## Skills

| Group | Skills |
| --- | --- |
| Development entry points | `architect-and-simplify`, `develop-and-deliver`, `task-mode-gate` |
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

For the multi-machine environment, consult the `ai-skills-library` reference
catalog and install from the named owner. `codex-machine-sync` reports presence
but does not install, pin, update, copy, or delete skills. Private repository
URLs and machine configuration belong in local untracked configuration, never
in this repository.

## Development

```bash
python scripts/validate_skills.py
pytest skills/apple-apps/tests/test_mail_meta.py -q
```

Each skill must remain independently installable. Supporting scripts and tests
belong inside the owning skill. Public source must not contain credentials,
machine inventories, private remotes, or absolute personal paths.
