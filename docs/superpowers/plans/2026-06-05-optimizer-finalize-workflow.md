# Optimizer Finalize Workflow Implementation Plan

**Goal:** Add one supervisor-side closeout command for completed optimizer runs:
`hermes-workflow finalize-optimizer-run PROJECT_DIR`.

**Architecture:** A thin wrapper over existing deterministic functions:
`check_optimizer_run`, `summarize_optimizer_run`, and
`generate_optimizer_insight_report`.

## Boundaries

- Do not run real tools.
- Do not change optimizer algorithms.
- Do not add broad orchestration.
- Do not remove existing individual commands.
- Do not parse PSF or rewrite OCEAN formulas.

## File Map

- Add: `src/hermes_workflow/optimizer_finalize.py`
- Modify: `src/hermes_workflow/cli.py`
- Add: `tests/test_optimizer_finalize.py`
- Modify: project state/progress docs

## Task 1: Finalize Report Library

- [x] Add `finalize_optimizer_run(project_dir)`.
- [x] Run acceptance first.
- [x] Run completion only when acceptance is accepted.
- [x] Run insights only when completion passes.
- [x] Write `reports/optimizer_finalize_report.json`.

Verify:

```bash
python3 -m pytest tests/test_optimizer_finalize.py::test_finalize_optimizer_run_writes_closeout_report -q
```

## Task 2: CLI Wiring

- [x] Add `hermes-workflow finalize-optimizer-run PROJECT_DIR`.
- [x] Print final decision and report paths.
- [x] Exit non-zero when finalization fails.

Verify:

```bash
python3 -m pytest tests/test_optimizer_finalize.py -q
python3 -m ruff check src/hermes_workflow/optimizer_finalize.py src/hermes_workflow/cli.py tests/test_optimizer_finalize.py
```

## Task 3: State Sync And Commit

- [x] Update state/progress docs.
- [x] Run focused regression and cadence checks.
- [x] Commit C-32.

Verify:

```bash
python3 -m pytest tests/test_optimizer_finalize.py tests/test_optimizer_insights.py tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-finalize-workflow-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment:
  C-32 closes the post-run supervisor workflow with a thin command wrapper.
- Drift:
  None planned. It does not run tools or create a new optimizer framework.
