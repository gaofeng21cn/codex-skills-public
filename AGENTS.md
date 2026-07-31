# Repository Instructions

- This public repository owns reusable Codex skill source. Keep credentials, hostnames, machine inventories, private remotes, and absolute local paths out of tracked files.
- Change a skill here first and validate it. Keep fleet installation routes in
  `gaofeng21cn/opl-instance-gaofeng:contracts/skill-reference.json`; never create
  a fleet-owned byte projection.
- Preserve deterministic source mappings and fail closed on dirty, ahead, diverged, or incomplete skill packages.
- Run `python scripts/validate_skills.py` and the affected skill tests before committing.

<!-- CODEGRAPH_START -->
## CodeGraph

- This repository uses the local `.codegraph/` index; never commit that directory.
- Prefer CodeGraph for symbol, caller, and impact searches; use `rg` for literal text searches.
- Run `codegraph init .` when missing and `codegraph sync .` after structural changes.
<!-- CODEGRAPH_END -->
