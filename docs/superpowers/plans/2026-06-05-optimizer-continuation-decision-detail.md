# C-41 Optimizer Continuation Decision Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow continuation-detail object to optimizer completion
reports so the supervisor can decide whether to continue after 100/120 evals.

**Architecture:** Extend `OptimizerCompletionReport` in place. Reuse existing
status counts, search-space estimate, and improvement summary. Do not add a new
decision engine or optimizer backend.

**Tech Stack:** Python standard library, existing pytest tests, existing Typer
CLI.

---

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-continuation-decision-detail-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: improves supervisor reporting after accepted optimizer runs while
  preserving OpenBox/TuRBO execution, acceptance, and finalize contracts.
- Drift: none intended. C-41 does not run real tools, change optimizer
  algorithms, parse PSF, rewrite formulas, or add broad strategy assets.

## Task 1: Continuation Detail Tests

- [x] Add failing tests in `tests/test_optimizer_completion.py` proving:
  - a `continue_more_evals` report includes `continuation.recommended=true`;
  - the suggested additional eval count is present;
  - an accepted no-recent-improvement report sets `plateau_detected=true` and
    `recommended=false`.

Verification:

```bash
python3 -m pytest tests/test_optimizer_completion.py::test_summarize_optimizer_run_recommends_continue_when_recent_best_improves -q
```

## Task 2: Completion Report Implementation

- [x] Add a `continuation: dict[str, Any]` field to
  `OptimizerCompletionReport`.
- [x] Implement a small `_summarize_continuation(...)` helper.
- [x] Keep existing top-level `decision` behavior unchanged.

Verification:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/optimizer_completion.py tests/test_optimizer_completion.py
```

## Task 3: Docs And State Sync

- [x] Update `docs/CURRENT_TASK_STATE.json`.
- [x] Update progress logs.
- [x] Update this plan checklist.

Verification:

```bash
python3 tools/check_development_cadence.py
git diff --check
```

## Task 4: Final Verification And Commit

- [x] Run completion and closeout-adjacent tests.
- [x] Run full ruff and cadence checks.
- [x] Commit C-41.

Verification:

```bash
python3 -m pytest tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_acceptance.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```
