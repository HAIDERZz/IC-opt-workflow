# C-44 Optimizer Status Handoff Integration Implementation Plan

Date: 2026-06-05

Design spec:

```text
docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md
```

## Goal

Put `optimizer-status` into the standard optimizer handoff closeout path without
changing optimizer execution behavior.

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: extends C-43 supervisor summary into the C-40/C-42 production
  handoff path while preserving existing acceptance/finalize semantics.
- Drift: none intended. No real tools, optimizer algorithm changes, new report
  contracts, PSF parsing, or OCEAN formula rewriting.

## Task 1: Packet Tests

- [x] Add focused assertions in `tests/test_optimizer_task_package.py` proving
  native TuRBO and OpenBox packets include `optimizer-status` in task text and
  manifest `audit_commands`.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
```

## Task 2: Packet Renderer And Guide

- [x] Add `optimizer-status` to generated audit commands.
- [x] Update `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` with the standard
  closeout sequence.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/optimizer_task_package.py tests/test_optimizer_task_package.py
```

## Task 3: State Sync And Commit

- [x] Update `docs/CURRENT_TASK_STATE.json`,
  `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, and this plan.
- [x] Run cadence and diff checks.
- [x] Commit C-44.

Verification:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```
