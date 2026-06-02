# Agent Working Constraints

This file is a workspace-level contract for agents working on `ic-auto-opt-workflow`.

Read this file before changing code, plans, specs, or handoff docs.

## Locked Project Role Model

Use the meanings from `docs/ROLE_MODEL_AND_TERMINOLOGY.md`:

- Supervisor agent: planning, approval, recovery decisions, and report reading.
- Hermes workflow tooling: deterministic file-contract, validation, package, report, and CLI tooling in this repository.
- Execution agent: tool-side worker that operates Virtuoso/Spectre/OCEAN only after approved packages exist.

Do not use "Hermes agent" as a role name. In this project, Hermes means workflow tooling, not the supervisor agent.

## Current Development Cadence

- Follow the active plan and task number exactly. Read this file, the active design spec, the active implementation plan, the current progress files, and the relevant top-level plan before changing code.
- Use `superpowers:subagent-driven-development` for implementation-plan tasks when subagents are available. This project overrides the generic "continuous execution" guidance: stop after each task is implemented, verified, reviewed, committed, and recorded unless the user explicitly asks to run multiple tasks without stopping.
- Use codegraph during Subagent-Driven work. Before implementation, use codegraph context/search/explore tools to locate the affected modules, symbols, and dependency paths. If codegraph is unavailable or stale, say so and use `rg`/file reads as the fallback.
- Per task, dispatch or emulate fresh-role work in this order: implementation, spec-compliance review, code-quality review. Spec review must pass before code-quality review starts. Open review issues must be fixed and re-reviewed.
- After each task, report the work to the user: what changed, which files changed, which verification commands ran, review-gate status, commits made, and any remaining risks or decisions.
- After each task, update project node files before stopping:
  - `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
  - `docs/EXECUTION_PROGRESS_2026-05-29.md`
  - `docs/COMPACT_RESUME_CHECKPOINT.md`
  - the active implementation plan checkboxes/status
  - this file's `Current Development Cadence` section if the cadence, next task, role model, or handoff expectations changed
- After each task, audit the current implementation against the top-level plan and the active spec. Record whether the route is still aligned or what changed.
- If development reveals a plan/spec problem and the implementation must differ from the written plan, synchronize the active design spec, active implementation plan, and any affected top-level plan before claiming the task is complete. Do not leave code and planning documents divergent.
- Do not start the next task until the user confirms. Do not jump to C-11 local smoke or real tool/agent integration until C-10 passes review/final gate.
- Keep progress files aligned with implementation before context compaction.

## Contract Boundaries

- Contract-only tasks must not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI as an execution agent, `virtuoso-bridge-lite`, or network access.
- Hermes workflow tooling must not parse PSF/waveform databases.
- Hermes workflow tooling must not rewrite Calculator/OCEAN formulas.
- Metric formulas in `metrics.yaml` or generated request files are authoritative only after user/project approval.
- Python may invoke/validate file contracts and record OCEAN-produced scalars/provenance, but must not reimplement metric formulas.
- Local real `input.scs` examples and Cadence evidence are reference material unless the user explicitly asks to commit them.

## Think Before Coding

Do not assume or hide confusion.

- State assumptions explicitly before risky changes.
- If multiple interpretations exist, present them instead of silently choosing.
- If a simpler approach exists, say so.
- Push back when an approach risks violating the workflow contract.
- If something is unclear and cannot be discovered from local context, stop and ask.

## Simplicity First

Use the minimum code that solves the requested problem.

- Do not add features beyond the task.
- Do not add abstractions for single-use code.
- Do not add flexibility or configurability that was not requested.
- Do not add error handling for scenarios that are impossible under the existing contract.
- If a change grows much larger than necessary, simplify before committing.

## Surgical Changes

Touch only what the task requires.

- Do not improve adjacent code, comments, or formatting unless required.
- Do not refactor unrelated code.
- Match existing style, even when another style looks cleaner.
- If unrelated dead code appears, mention it; do not delete it.
- Remove imports, variables, functions, or files made unused by your own changes.
- Every changed line should trace back to the user request, the active plan, or a review finding.

## Goal-Driven Execution

Turn tasks into verifiable goals.

- For validation work, write or identify tests for invalid inputs before making them pass.
- For bug fixes, reproduce the bug or define a focused failing condition first.
- For refactors, keep before/after verification explicit.
- For multi-step tasks, state a short plan with the verification command for each step.
- Before claiming completion, run fresh verification and report the actual evidence.
