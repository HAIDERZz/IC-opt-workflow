# C-40 OpenBox Continuation Production Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the C-39 proven OpenBox continuation path reusable through the
generated execution-agent handoff packet and production guide.

**Architecture:** Keep `optimizer_task_package.py` as the single task packet
renderer. Add only OpenBox environment-gate handoff text, finalization closeout,
and returned artifact expectations. Do not add a new orchestration layer.

**Tech Stack:** Python standard library, Typer CLI tests, Markdown docs.

---

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-openbox-continuation-production-handoff-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: productionizes the accepted OpenBox continuation route while
  preserving the existing Spectre/OCEAN execution path and C-25/C-26/C-32
  reports.
- Drift: none intended. C-40 does not run real tools, change optimizer behavior,
  parse PSF, rewrite formulas, replace TuRBO, or add broad framework assets.

## Task 1: Packet Contract Tests

- [x] Add failing tests in `tests/test_optimizer_task_package.py` proving an
  OpenBox continuation packet includes:
  - `check-toolchain-env`;
  - `/tmp/ic_auto_opt_openbox_spike/.venv`;
  - `continue-openbox-real`;
  - `finalize-optimizer-run`;
  - non-sandbox/escalated execution wording;
  - returned acceptance/completion/finalize/insight artifacts.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py::test_build_optimizer_execution_task_package_writes_openbox_continuation -q
```

## Task 2: Minimal Packet Renderer Update

- [x] Update `src/hermes_workflow/optimizer_task_package.py` so OpenBox packets
  render the toolchain gate, execution environment notes, finalization command,
  and closeout artifacts.
- [x] Keep existing command payloads stable except for additive fields and
  audit commands.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/optimizer_task_package.py tests/test_optimizer_task_package.py
```

## Task 3: Production Guide And State Sync

- [x] Update `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` with first-run and
  continuation command examples.
- [x] Update `docs/CURRENT_TASK_STATE.json` and progress logs.
- [x] Update this plan checklist.

Verification:

```bash
python3 tools/check_development_cadence.py
git diff --check
```

## Task 4: Final Verification And Commit

- [x] Run optimizer task package tests.
- [x] Run optimizer closeout-adjacent tests.
- [x] Run full ruff and cadence checks.
- [x] Commit the C-40 changes.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py tests/test_optimizer_finalize.py tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```
