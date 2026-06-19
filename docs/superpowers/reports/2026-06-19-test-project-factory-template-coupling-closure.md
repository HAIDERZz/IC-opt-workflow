# Test Project Factory Template Coupling Cleanup — Closure Report

Date: 2026-06-19
Status: complete

## Summary

The Test Project Factory and Template Coupling Cleanup is complete. Over 13 phases
and 6 rounds (R1-R6), every non-product test file in `tests/` was migrated away
from direct `create_project_from_template()` usage and old packaged-template
assumptions (`bridge_test_inv`, `FN/WN/FP/WP`, `rise/fall/DC`, `TEMPLATE_TEXT`).

The generic test project factory (`tests/project_factory.py`) creates valid projects
with neutral variable names (`VAR_INT`, `VAR_WIDTH`), neutral metric names
(`metric_gain`, `metric_power`), and a valid template. Shared helper modules
(`tests/real_run_cluster_helpers.py`, `tests/real_run_smoke_helpers.py`,
`tests/netlist_dry_run_helpers.py`) provide reusable fixture builders.

## Final guard contract

`tests/test_template_coupling_guard.py` enforces:

```python
INTENTIONAL_TEMPLATE_API_CALLERS = {
    "tests/test_package.py",
}
```

Any new `tests/*.py` file (other than the guard itself) that contains
`create_project_from_template` and is not in this set will fail the guard test.

## Final direct caller list

- `tests/test_package.py` — intentionally tests the product/template API
  (template tree, packaged resources, `hermes-workflow init`).
- `tests/test_template_coupling_guard.py` — the guard itself (contains the
  string for scanning).

## Final verification

- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean

## What was built

| Artifact | Purpose |
|---|---|
| `tests/project_factory.py` | Generic project factory (2 variables, 2 metrics) |
| `tests/real_run_cluster_helpers.py` | Shared next-run cluster helpers |
| `tests/real_run_smoke_helpers.py` | Shared smoke test helpers + advisor batches |
| `tests/netlist_dry_run_helpers.py` | Shared netlist/dry-run preflight helpers |
| `tests/test_template_coupling_guard.py` | Guard enforcing no new direct template usage |

## Migration history (phases)

| Phase | Files migrated | Allowlist delta |
|---|---|---|
| 1 | test_health.py, test_optimizer_flow.py | 25→23 |
| 2 | test_result_handoff.py, test_metric_results.py | 23→21 |
| 3 | test_real_run.py, test_real_run_recovery.py | 21→19 |
| 4 | test_next_real_run.py + cluster (4 files) | 19→18 |
| 5 | test_netlists.py, test_dry_run.py | 18→16 |
| 6 | test_approvals.py (+ factory fix_run fix) | 16→15 |
| 7 | test_optimizer_task_package.py | 15→14 |
| 8 | test_run_retention.py, test_optimizer_progress_state.py | 14→12 |
| 9 | test_fix_run_flow.py | 12→11 |
| 10 | test_multi_testbench_aggregation.py | 11→10 |
| 11 | test_real_result_record.py | 10→9 |
| 12 | real_run_smoke_helpers.py + 9 consumers | 9→8 |
| 13 | test_mock_optimizer.py | 8→7 |
| R1 | test_native_turbo.py | 7→6 |
| R2 | test_openbox_backend.py | 6→5 |
| R3 | test_remote_fix_run_flow.py | 5→4 |
| R4 | test_remote_optimizer_flow.py | 4→3 |
| R5 | test_spectre_ocean_adapter.py | 3→2 |
| R6 | test_remote_spectre_ocean.py | 2→1 |
| Closure | Guard rename + inventory cleanup | 1 (final) |
