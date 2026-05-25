---
name: academic-defense-prep
description: Use when turning academic or medical-research materials into defense deliverables, including timed oral scripts, PPT speaker notes, narrative/storyline rewrites, reviewer-facing questions with background notes, or paired slide-notes plus script outputs. Trigger on PPT/PPTX plus source PDFs, thesis zip packages, proposal/application materials, dissertation defenses, project defenses, or requests such as "5-minute script", "speaker notes", "defense questions", "paced oral defense", or "storyline". Pair with Office/PPTX/PDF extraction skills for file operations.
---

# Academic Defense Prep

## Overview

This skill turns real academic materials into evaluator-ready defense outputs. It focuses on pacing, storyline, reviewer identity, and source-grounded wording; it does not replace Office/PPTX/PDF tools for low-level file extraction or editing.

## Evidence First

Before drafting:
- Read the current deck outline and visible slide text when a `.pptx` is provided.
- Extract or read backing PDFs, proposals, theses, abstracts, conclusions, and appendices that define the actual claims.
- For a zip of theses, extract text locally before writing questions; use abstracts/conclusions/results to map the topic.
- If the task involves editing speaker notes, inspect existing notes first and verify the final PPT package after editing.

Useful tool patterns:
- PPT structure: `officecli view <file.pptx> outline` and `officecli view <file.pptx> text`.
- PPT notes: `officecli query <file.pptx> notes`, `officecli help pptx notes`, `officecli set <file.pptx> '/slide[N]/notes' --prop text=...`.
- PDF text: prefer the configured PDF/MinerU workflow; `pdftotext -layout` is enough for many thesis PDFs.
- Integrity checks after PPT edits: `officecli validate <file.pptx>` and `unzip -t <file.pptx>`.

## Timed Defense Script

For requests like "5-minute script":
- Produce a spoken script, not bullet notes.
- Compress slides into speaking blocks: key slides get full explanation; support slides are bridged quickly.
- Mark milestone times when requested, such as `0:00-0:40`, `1:05`, or "section X ends here".
- Keep a small buffer under the stated limit; a 5-minute defense should often target about 4:45-5:00.
- Preserve slide body/layout unless the user explicitly asks to rewrite the deck.

Default script shape:
- Opening: problem/context and project objective.
- Core: method/technical route, major work packages, evidence/results, and feasibility.
- Support: team, platform, papers, patents, funding, collaborations, or prior basis.
- Closing: expected contribution, next step, or approval/translation target.

## Storyline Rewrite

For storyline or reviewer-facing rewrite:
- Do not prescribe a fixed slide count unless asked.
- State the narrative arc and where existing materials should move conceptually.
- Preserve support sections that matter to credibility, such as research contents, clinical/engineering team, papers, awards, IP, platform support, and prior clinical basis.
- For non-specialist reviewers, move from clinical pain point to why the current approach is insufficient, then to the proposed system, evidence, feasibility, team, and translation path.
- Use precise domain terminology once confirmed by the user or source material. In medical-device contexts, avoid vague approval wording when formal approval language is needed.

## Speaker Notes Editing

When asked to update PPT speaker notes:
- Treat notes plus timed script as paired deliverables if both are requested.
- Keep each note aligned to the slide's role in the oral flow, not a verbatim copy of slide bullets.
- After bulk note replacement, verify both the user-visible notes query and package integrity.
- If an old note survives despite successful high-level commands, inspect `ppt/notesSlides/notesSlideN.xml`; duplicate placeholder shapes can preserve stale text. Fix on a temporary copy first if the resident process hangs or reports a busy pipe.

## Defense Questions

For thesis or proposal review questions:
- Default to explanatory, constructive, non-hostile questions.
- For each student/project, usually provide 2 main questions plus at most one optional follow-up unless the user asks for more.
- Add a one-sentence background/rationale for each question so the evaluator can decide when to ask it.
- Shape questions to the user's stated reviewer identity. For medicine-AI review, emphasize data leakage, prediction window, thresholding, interpretability, external validation, domain shift, batch effects, multimodal integration, and clinical deployment boundaries.

## Output Shapes

Timed script:
```markdown
0:00-0:35 Opening and problem definition
...
4:35-4:55 Closing
```

Storyline advice:
```markdown
Arc: clinical pain point -> current boundary -> proposed system -> key evidence -> team and translation path
Materials to keep and move earlier: ...
Materials to weaken or move later: ...
```

Reviewer questions:
```markdown
Student / project: ...
1. Question...
   Background: ...
2. Question...
   Background: ...
Optional follow-up: ...
```

Notes-edit closeout:
- Files edited
- Verification commands and results
- Any slides with manual XML cleanup

## Stop Conditions

Pause and ask or report a blocker when:
- Required source files are missing or unreadable.
- The requested timing is incompatible with the amount of material and the user has forbidden compression.
- Editing the PPT would overwrite unrelated user changes or a package-level corruption cannot be verified.
- The user asks for exact current policy, regulatory, or submission wording that may have changed and no live source has been checked.

Do not invent results, publications, regulatory status, clinical claims, or authorship facts not supported by the provided materials.
