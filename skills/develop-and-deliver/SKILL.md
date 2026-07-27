---
name: develop-and-deliver
description: Use when a software task needs systematic implementation, technical validation, or delivery orchestration across multiple steps; do not trigger for a tiny self-contained edit, a read-only explanation, or a review-only request.
---

# Develop And Deliver

Use the shortest safe path from the requested change to its real, user-verifiable
terminal outcome. This is a routing and execution skill, not a second project
methodology: repository instructions, contracts, source, and runtime readback
remain authoritative.

## Establish The Work

1. Read the effective instructions and locate the real source, caller,
   write set, acceptance surface, and terminal outcome before editing.
2. Separate the critical path from useful follow-up work. Do not turn nearby
   cleanup, general hardening, or a platform repair into a prerequisite unless
   it is the current real blocker.
3. Use the repository's existing tools, abstractions, commands, and validation
   lanes. Add a new abstraction only when the current task proves it necessary.

## Route Only What Is Needed

- Use `$task-mode-gate` as an additional narrow gate for release, deployment,
  migration, public or destructive writes, cross-carrier version orchestration,
  or a task that first validates a path and then productionizes it.
- Use `$prototype` when a disposable implementation is the fastest way to
  answer a state, logic, or UI design question.
- Use `$book-legacy-code` only when uncertain legacy behavior blocks a safe
  change and a characterization seam is needed.
- Use browser, Playwright, CLI-building, data, or production-failure skills only
  when their own trigger applies. Do not load a collection of adjacent skills
  pre-emptively.

If a named route is unavailable, follow the same narrow boundary directly and
report the missing managed capability; do not stop an otherwise executable task.

## Diagnose Before Repair

- For an ordinary first failure, reproduce it or trace the real call path to the
  deepest verifiable breakpoint, then fix that cause directly. A symptom, error
  code, `blocked` label, or missing dependency is evidence, not automatically
  the root cause.
- Escalate to a deeper root-cause analysis only after repeated or flaky failure,
  a cross-component boundary, runtime/currentness drift, or an explicit request
  for the root cause.
- In a deeper analysis, distinguish the visible symptom, immediate breakpoint,
  cross-surface evidence, canonical owner surface, and repair or decision path.
  Do not impose planner/debugger/executor/verifier role switching or a heavy
  diagnostic ceremony on ordinary narrow fixes.

## Make Progress

1. Implement the smallest coherent change that can reach the requested outcome.
2. Run the real path early enough to expose the first actual breakpoint.
3. At a breakpoint choose exactly one repair strategy:
   - `direct_fix`: repair the defect now when it is narrow or blocks trustworthy
     completion;
   - `delivery_bridge`: use a minimal, explicit, traceable, reversible path that
     preserves the real artifact and acceptance semantics;
   - `stop`: stop only when no safe path exists or authority is missing.
4. After the breakpoint closes, return immediately to the delivery path.
   Permanent cleanup can follow only if it is required for the terminal outcome
   or has a separate, non-overlapping owner.

A bridge must not be an unrecorded local change, mutable host assumption, force,
skipped qualification, fabricated receipt, stale artifact, or unknown external
result.

## Verify And Close

- Scale verification to risk and blast radius: focused checks for narrow edits,
  broader checks for shared contracts, and live readback for runtime or external
  claims.
- Do not call a plan, test pass, candidate, dry-run, handoff, or queued action
  complete. Verify the actual terminal surface.
- Creating a worktree creates a same-task terminal obligation. Immediately
  register its ACTIVE owner, objective, exact write set, and next action through
  the repository's supported ownership surface.
- Commit and push clean, non-sensitive stage results to a task-owned remote ref,
  then read back its commit and tree so unfinished work is recoverable.
- The original owner remains responsible for fetching fresh `main`, replaying
  the intended change against current SSOT, resolving conflicts, rerunning
  affected verification, ordinary-pushing the canonical result, and reading
  back final main/wire bytes. A handoff transfers this duty only when the
  receiver explicitly accepts ownership.
- After canonical absorption, remove this task's worktree, local and remote task
  refs, holders, and temporary artifacts through the supported guarded cleanup
  path. A callback, candidate, canonical push, or patch-equivalence checkpoint
  does not by itself end the source owner's cleanup duty.
