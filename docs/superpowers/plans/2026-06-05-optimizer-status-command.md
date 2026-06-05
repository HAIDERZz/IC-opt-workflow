# C-43 Optimizer Status Command Implementation Plan

Date: 2026-06-05

Design spec:

```text
docs/superpowers/specs/2026-06-05-optimizer-status-command-design.md
```

## Goal

Add a narrow `hermes-workflow optimizer-status PROJECT_DIR` command for
supervisor agents to read optimizer closeout status without manually opening
several report files.

## Route Audit

- Active spec: `docs/superpowers/specs/2026-06-05-optimizer-status-command-design.md`
- Top-level plan: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: improves supervisor readability on top of existing C-25/C-26/C-31/C-32
  reports and C-40/C-42 production handoff evidence.
- Drift: none intended. Do not run real tools, change optimizer behavior, add a
  new report contract, parse PSF, rewrite OCEAN formulas, or broaden the
  workflow framework.

## Task 1: Status Summary Tests

- [x] Add focused tests proving:
  - the library summary reads finalize and completion data;
  - the CLI output includes decision, confidence, global optimum claim, best
    observed, evaluation count, status counts, continuation recommendation, and
    report paths.

Verification:

```bash
python3 -m pytest tests/test_optimizer_status.py -q
```

## Task 2: Minimal Library And CLI

- [x] Add `src/hermes_workflow/optimizer_status.py`.
- [x] Add CLI command `hermes-workflow optimizer-status PROJECT_DIR`.
- [x] Keep behavior read/closeout-only; do not run real tools.

Verification:

```bash
python3 -m pytest tests/test_optimizer_status.py -q
python3 -m ruff check src/hermes_workflow/optimizer_status.py src/hermes_workflow/cli.py tests/test_optimizer_status.py
```

## Task 3: State Sync And Commit

- [x] Update `docs/CURRENT_TASK_STATE.json`,
  `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, and this plan.
- [x] Run cadence and diff checks.
- [x] Commit C-43.

Verification:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```
