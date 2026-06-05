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
- Use `superpowers:subagent-driven-development` for implementation-plan tasks when it materially reduces risk. This project overrides the generic "continuous execution" guidance: stop after each task is implemented, verified, committed if appropriate, and recorded unless the user explicitly asks to run multiple tasks without stopping.
- Use codegraph during Subagent-Driven or code-changing work to locate affected modules, symbols, and dependency paths. For docs-only, environment-gate, or practice-record tasks, codegraph is optional; use `rg`/targeted file reads unless code paths are actually being changed.
- Use review gates by risk, not by habit. High-risk code tasks that touch contracts, schemas, hashes, file writes, approval/recovery logic, ledger/state, safety guards, or real-tool adapters need spec-compliance and code-quality review evidence before `reviewed`. Medium-risk integration or CLI tasks can batch reviews over 2-3 related tasks. Low-risk docs, progress, environment gates, and practice evidence remain `verified-only` unless the user explicitly requests review.
- `docs/CURRENT_TASK_STATE.json` is the canonical resume anchor after context compaction. Read it before task work, keep it synchronized with the active spec, active implementation plan, top-level plan, and progress files, and update it before commit.
- The word `reviewed` is reserved for tasks with recorded spec-review and code-quality review evidence. If no callable subagent or explicit review path is available, use `verified-only` or `blocked-no-subagent` instead.
- After each task, report in a compact shape: status, changed files, verification commands, review status, commit if made, risks/next action. Keep it short unless the user asks for detail.
- Use the Lean Evidence Gate for node updates:
  - Always update `docs/CURRENT_TASK_STATE.json`.
  - Append a short entry to `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` when the task changes project state.
  - Update `docs/COMPACT_RESUME_CHECKPOINT.md` only before context compaction, at milestone boundaries, or when the next resume prompt would otherwise be wrong.
  - Update `docs/EXECUTION_PROGRESS_2026-05-29.md` only for phase/milestone completion, route changes, or user-requested summaries.
  - Update active implementation plan checkboxes/status at the end of a small flow or checkpoint. Do not spend a separate documentation cycle after every tiny subtask unless the user asks for per-task stop-and-report.
  - Update the top-level plan current node only when a milestone, route, or production-readiness state changes, especially after real-tool acceptance, production handoff, or optimizer route changes.
  - Update this `Current Development Cadence` section only when cadence, next-task rules, role model, or handoff expectations change.
- After each task, audit the current implementation against the top-level plan and the active spec. Record the audit in `CURRENT_TASK_STATE.json`; duplicate it into other progress files only when the Lean Evidence Gate says those files are due.
- If development reveals a plan/spec problem and the implementation must differ from the written plan, synchronize the active design spec, active implementation plan, and any affected top-level plan before claiming the task is complete. Do not leave code and planning documents divergent.
- Run verification by risk. Low-risk docs/environment tasks normally need only JSON validation when applicable, `python3 tools/check_development_cadence.py`, and `git diff --check`. Code tasks need targeted tests; high-risk code also needs broader regression checks and review evidence.
- Do not start the next task until the user confirms, unless the user explicitly asks to complete the next task or next step without interruption.
- Keep progress files aligned with implementation before context compaction.
- When the user explicitly authorizes a fast real-tool debug lane, label the work `verified-only`, keep changes surgical, record a concise debug note under `docs/debug/`, keep raw tool artifacts local-only, and return to the normal task/review cadence before claiming a reviewed implementation task is complete.
- Before running real Virtuoso/Spectre/OCEAN/OpenBox/native-TuRBO/bridge commands, read `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` and use its known-good environment, sandbox, workspace-preparation, and closeout commands. If a real-tool run fails, compare it against that reference before inventing a new debug path.

## Practice-First Tool Integration

Use real, working Cadence/Maestro/ADE/OCEAN behavior as the foundation. Do not rebuild a parallel foundation and try to make it resemble the proven flow.

- Preserve native Maestro/ADE file and directory structure when it is part of observed correct behavior. Adapt Hermes workflow contracts to that structure instead of flattening or inventing a substitute layout.
- Before designing optimizer or tool-adapter features whose correctness depends on external tool behavior, run a small manual or scripted practice flow first, record the successful case, and then productize that proven path.
- If a needed behavior has not been practically confirmed, the active design spec and implementation plan must include a scoped evidence-gathering task before code tries to generalize it.
- Treat successful local evidence as a constraint. When new code fails, compare against the successful evidence first and move the code toward that known-good path before adding new abstractions or contract fields.
- Do not change approved metric formulas to compensate for adapter/layout bugs. Fix the adapter/layout so the approved formulas run in the same context that made them valid.
- Reduce fake-run ladders. Fake/local runs are for contract, schema, CLI wiring, or unit behavior only. For features whose value depends on Cadence/OpenBox behavior, run at most one focused fake/local smoke per new command path, then move to the smallest meaningful real practice flow.
- Do not create speculative, overlapping, or overly broad assets.
- Prefer one narrow artifact per verified need. Avoid broad new specs, duplicate plans, extra schemas, or catch-all debug frameworks unless the current evidence proves they are necessary.

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
