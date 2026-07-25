---
name: evidence-bound-closeout
description: "Use when the user explicitly asks for evidence-bound-closeout, exact-byte artifact fingerprinting, or QA evidence bound to unchanged final file bytes."
---

# Evidence-Bound Artifact Closeout

1. Finish the final build or export.
2. Fingerprint the final artifact.
3. Run QA after fingerprinting and confirm the artifact did not change during QA.
4. If QA changes the file, rerun QA against the new fingerprint.

```bash
python3 ~/.codex/skills/evidence-bound-closeout/scripts/fresh_artifact_closeout.py fingerprint <artifact>
python3 ~/.codex/skills/evidence-bound-closeout/scripts/fresh_artifact_closeout.py verify --artifact <artifact> -- <qa command...>
```

Report the exact path, size, SHA-256, QA command, exit code, and whether the fingerprint stayed unchanged.

This proves only that QA ran against unchanged bytes. It does not prove semantic correctness, source authority, owner acceptance, runtime readiness, release readiness, or Git lane absorption.
