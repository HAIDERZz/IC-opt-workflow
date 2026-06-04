# Optimizer Post-Run Visualization And Insight Report Implementation Plan

**Goal:** Generate a dependency-light post-run optimizer insight report with
static plots and observed variable/result relationship summaries.

**Architecture:** Add `src/hermes_workflow/optimizer_insights.py`, wire
`hermes-workflow visualize-optimizer-run`, and test against existing accepted
optimizer artifact fixtures. No real tools.

## Boundaries

- Do not run real Virtuoso/Spectre/OCEAN.
- Do not change optimizer candidate generation.
- Do not require OpenBox advanced visualization dependencies.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not add a service, dashboard, or broad reporting framework.

## File Map

- Add: `src/hermes_workflow/optimizer_insights.py`
- Modify: `src/hermes_workflow/cli.py`
- Add: `tests/test_optimizer_insights.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

## Task 1: Static Insight Report Library

- [x] Load accepted optimizer artifacts with `load_optimizer_artifacts`.
- [x] Compute status counts, best observed, finite objective rows, metric keys,
  and observed parameter/target correlations.
- [x] Write `optimizer_insight_report.json`.
- [x] Write `optimizer_insight_report.md`.

Verify:

```bash
python3 -m pytest tests/test_optimizer_insights.py::test_generate_optimizer_insight_report_writes_json_and_markdown -q
```

## Task 2: Static SVG Plots

- [x] Generate `convergence.svg`.
- [x] Generate `status_distribution.svg`.
- [x] Generate `parameter_objective_scatter.svg`.
- [x] Keep SVG generation standard-library only.

Verify:

```bash
python3 -m pytest tests/test_optimizer_insights.py -q
```

## Task 3: CLI Wiring

- [x] Add `hermes-workflow visualize-optimizer-run PROJECT_DIR`.
- [x] Print report and plot paths.
- [x] Fail closed when issues exist.

Verify:

```bash
python3 -m pytest tests/test_optimizer_insights.py -q
python3 -m ruff check src/hermes_workflow/optimizer_insights.py src/hermes_workflow/cli.py tests/test_optimizer_insights.py
```

## Task 4: Final Verification And State Sync

- [x] Update state/progress docs.
- [x] Run focused and cadence verification.
- [ ] Commit C-31.

Verify:

```bash
python3 -m pytest tests/test_optimizer_insights.py tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-post-run-visualization-insight-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment:
  C-31 adds post-run interpretation only after optimizer artifacts exist.
- Drift:
  None planned. Advanced OpenBox SHAP/surrogate HTML is not required by this
  MVP and remains a future optional add-on.
