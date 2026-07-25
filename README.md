# codex-skills-public

Public source repository for reusable Codex skills maintained by
`gaofeng21cn`.

## Repository Role

This repository is one of three deliberately separate layers:

- `codex-skills-public`: public, reusable skill development source
- `codex-skills-private`: private or machine-specific skill development source
- `ai-skills-library`: private, generated deployment snapshot for the machine fleet

The paired `public` / `private` names are intentional. They state the access and
reuse boundary directly; changing them to broader names such as
`codex-skills` or `codex-skills-internal` would make that boundary less obvious
without changing the architecture.

Upstream-owned skills such as Ponytail, OpenAI curated skills, and Agent Reach
are not copied here as development source. Their projections are declared in
[`skills/skill-upgrader/sources.json`](skills/skill-upgrader/sources.json) and
refreshed from their official repositories.

## Skills

| Group | Skills |
| --- | --- |
| Development entry points | `architect-and-simplify`, `develop-and-deliver`, `task-mode-gate` |
| Architecture and reliability lenses | `book-aposd`, `book-clean-architecture`, `book-ddia`, `book-domain-driven-design`, `book-legacy-code`, `book-release-it`, `grill-with-docs`, `improve-codebase-architecture`, `prototype`, `zoom-out` |
| Artifact and learning workflows | `academic-defense-prep`, `evidence-bound-closeout`, `external-learning-landing`, `xiaohongshu-repo-scout` |
| Local application adapters | `apple-apps`, `mail-triage` |
| Maintenance | `skill-upgrader` |

Some skills adapt MIT-licensed upstream work. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Install

Install one skill with the bundled Codex installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/<skill-name>
```

For the managed multi-machine environment, use `skill-upgrader` and
`codex-machine-sync`; do not install from the deployment snapshot by hand.
Private repository URLs and machine configuration belong in local untracked
configuration, never in this repository.

## Development

```bash
python scripts/validate_skills.py
pytest skills/apple-apps/tests/test_mail_meta.py -q
pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q
```

Each skill must remain independently installable. Supporting scripts and tests
belong inside the owning skill. Public source must not contain credentials,
machine inventories, private remotes, or absolute personal paths.
