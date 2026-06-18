# Test Project Factory Template Coupling Phase 10 Spec

Date: 2026-06-19

## Objective

Decouple `tests/test_multi_testbench_aggregation.py` from direct packaged-template project creation.

This phase targets the one remaining direct `create_project_from_template()` helper in the file: `_create_ready_single_testbench_corner_project()`. The multi-testbench requirement helpers should stay intact because they intentionally exercise requirement-intake generated multi-testbench projects and are imported by backend/remote tests.

## Scope

Allowed files to modify:

- `tests/test_multi_testbench_aggregation.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_spectre_ocean.py`
- `src/hermes_workflow/multi_testbench_aggregation.py`

No other production, test, release, prompt, plan, graph, or generated-output files may be modified unless the implementation discovers a real blocker and stops for review first.

## Requirements

### 1. Direct Template Call Removal

`tests/test_multi_testbench_aggregation.py` must stop importing and calling `create_project_from_template()`.

Required behavior:

- Replace the single-testbench corner helper's project setup with `create_generic_project()`.
- Keep the existing multi-testbench requirement helpers based on `_copy_multi_testbench_requirement_project()` unchanged unless a direct failure proves they must move.
- Keep `MAX_GAIN`, `IIP3`, `cg_nf`, and `iip3` assertions where they come from the explicit multi-testbench requirement fixture. Those are requirement-fixture semantics, not packaged-template drift.
- Remove old single-testbench template names and variables:
  - `bridge_test_inv`
  - `FN`
  - `WN`
  - `FP`
  - `WP`
  - `rise`
  - `fall`
  - `DC`
- Do not replace one hardcoded circuit family with another. Derive single-testbench metric names from `config/metrics.yaml`.

### 2. Single-Testbench Multi-Corner Behavior Preservation

The two single-testbench corner tests must remain meaningful after migration:

- `test_aggregate_single_testbench_multi_corner_feasible_uses_worst_case_corner_metrics`
- `test_aggregate_single_testbench_explicit_one_corner_preserves_configured_semantics`

Required behavior:

- Use the generic factory's two metrics from `config/metrics.yaml`.
- Treat the first metric as the objective metric and the second metric as the non-target metric for expected aggregate values.
- Keep objective policy and constraint policy assertions.
- Keep selected/worst corner assertions, adjusted to the generic objective expression.
- Keep aggregate metric manifest assertions, but derive metric names from generated config.
- Keep child status assertions for the explicit one-corner case.

### 3. Coupling Guard

Remove this file from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/test_multi_testbench_aggregation.py`

The allowlist count should shrink from 11 to 10.

### 4. Consumer Safety

`tests/test_multi_testbench_aggregation.py` exports helper functions used by:

- `tests/test_openbox_backend.py`
- `tests/test_remote_spectre_ocean.py`

Do not edit those consumer files in Phase 10. They must be run as regression coverage. If a consumer fails and the fix requires changing a consumer file, stop and report the dependency issue instead of widening scope.

### 5. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 10.
- Add a `Phase 10 status` section before Phase 9.
- State that `tests/test_multi_testbench_aggregation.py` was migrated.
- State that the allowlist changed from 11 to 10.
- Remove `tests/test_multi_testbench_aggregation.py` from the remaining migration waves.
- Add exact verification results after running the commands in this spec.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/real_run_smoke_helpers.py`
- Backend implementation files
- Remote implementation files
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

Do not commit, tag, push, or publish. The user will ask separately when this phase should be committed.

## Required Verification

Run these commands from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_multi_testbench_aggregation.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_multi_testbench_aggregation\|tests.test_multi_testbench_aggregation" tests || true
```

Expected baseline before migration:

- `tests/test_multi_testbench_aggregation.py`: `12 passed, 13 warnings`
- Consumer group (`test_multi_testbench_aggregation.py`, `test_openbox_backend.py`, `test_remote_spectre_ocean.py`): `95 passed, 13 warnings`
- Release checkout: clean

Expected after migration:

- `tests/test_multi_testbench_aggregation.py`: `12 passed, 13 warnings`
- Guard: `1 passed`
- Target plus guard: `13 passed, 13 warnings`
- Consumer group: `95 passed, 13 warnings`
- Phase 1-10 regression group: about `351 passed, 13 warnings`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes
- `git diff --check` is clean
- Release checkout remains clean
- Drift grep over `tests/test_multi_testbench_aggregation.py` prints no matches
- Cross-import grep prints only known consumers in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`

If any count differs because a prior phase changed collection counts, record the real count and explain the reason in the final report.

## Stop Conditions

Stop and report instead of widening scope if:

- A production-code change appears necessary.
- `tests/project_factory.py` needs another behavior change.
- Any test outside the three allowed files must be edited.
- `tests/test_openbox_backend.py` or `tests/test_remote_spectre_ocean.py` fails in a way that requires editing those files.
- `tests/real_run_smoke_helpers.py` becomes part of the fix.
- Full-suite failures appear outside the touched surface and cannot be tied directly to this migration.
