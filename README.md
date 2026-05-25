# codex-skills-public

Public Codex skills maintained as a multi-skill repository.

This repository hosts installable skills that can be pulled directly into a local Codex setup. The focus is practical, reusable workflows rather than generic prompt snippets.

## What This Repo Is For

- Publish reusable Codex skills as standalone installable directories
- Keep skill logic close to supporting scripts and tests
- Provide a small public catalog that can be installed one skill at a time

This repo is useful if you:

- use Codex and want installable skills instead of copying prompts by hand
- want examples of skills that include helper scripts and tests
- prefer explicit, repository-backed skill distribution

## Available Skills

| Skill | Purpose | Typical use |
| --- | --- | --- |
| `academic-defense-prep` | Turn academic and medical-research materials into defense deliverables | draft timed oral scripts, PPT speaker notes, storyline rewrites, and reviewer-facing questions |
| `apple-apps` | Apple Mail automation helpers on macOS | inspect inboxes, search messages, read or mutate messages in Mail.app |
| `skill-upgrader` | Inspect and upgrade managed local skills from explicit upstream sources, then sync a Skills Manager central library across machines | refresh upstream-managed skills on one machine, push them into a central library repo, and pull them on other machines |

## External Tools

Some heavier tools are intentionally maintained in standalone repositories instead of this catalog. Current example:

- [`gaofeng21cn/omx-project-installer`](https://github.com/gaofeng21cn/omx-project-installer)
  - A compatibility-focused OMX project-scope installer that keeps repository-root `AGENTS.md` App-native, writes OMX orchestration into `./.codex/AGENTS.md`, reconciles system-level model/provider config into project scope, and repairs legacy alias issues until upstream OMX releases fully absorb those fixes.

This stays separate because it is more than a single lightweight skill directory: it ships templates, examples, tests, install scripts, and upstream-compatibility logic as one coherent tool.

## Quick Start

Install a skill from this repo with Codex's GitHub installer:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/academic-defense-prep
```

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/apple-apps
```

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gaofeng21cn/codex-skills-public \
  --path skills/skill-upgrader
```

After installation, restart Codex or start a new session so the new skill is picked up reliably.

`skill-upgrader` can also drive a `Skills Manager` central library workflow. Keep the private library remote in `~/.skills-manager/local_machine.private.json`, not in this public repository.

## Repository Layout

- `skills/`: installable skill directories, each with its own `SKILL.md`
- `skills/<name>/scripts/`: helper scripts used by that skill
- `skills/<name>/tests/`: skill-specific tests
- `scripts/`: repository-level validation helpers
- `.github/workflows/`: CI configuration
- `docs/`: design notes and implementation plans for repo-maintained skills

## Development

Validate skill metadata:

```bash
python scripts/validate_skills.py
```

Run tests:

```bash
pytest skills/apple-apps/tests/test_mail_meta.py -q
pytest skills/skill-upgrader/tests/test_skill_upgrader.py -q
```

## Design Principles

- Each skill should be installable as an independent directory.
- Supporting automation belongs next to the skill that uses it.
- Public skills should prefer explicit behavior over hidden heuristics.
- Tests should cover the non-trivial logic in helper scripts.

## Notes

- This is a public repository, so only skills suitable for open distribution belong here.
- Private or machine-specific skills can live in a separate private repo and still be symlinked into a local Codex setup.
