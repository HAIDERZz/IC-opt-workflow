# R2 OpenBox Backend Template-Coupling Cleanup Spec

## Objective

Migrate `tests/test_openbox_backend.py` away from direct packaged-template usage while preserving all OpenBox backend behavior coverage.

R2 must remove `tests/test_openbox_backend.py` from `ALLOWED_TEMPLATE_CALLERS`, leaving only remote/adapter flows plus the intentionally template-based package tests.

## Current State

R1 Native TuRBO has been committed. The direct test callers of `create_project_from_template()` are now:

```text
tests/test_openbox_backend.py
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

The current OpenBox baseline is:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected:

```text
45 passed, 13 warnings
```

OpenBox plus its known multi-testbench/remote Spectre consumer group baseline is:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
95 passed, 13 warnings
```

## In Scope

Allowed files:

- `tests/test_openbox_backend.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Out of Scope

Do not modify:

- `src/`
- `tests/project_factory.py`
- `tests/real_run_smoke_helpers.py`
- `tests/test_multi_testbench_aggregation.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_package.py`
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

If any out-of-scope file appears required, stop and report the exact reason.

## Required Behavior

### OpenBox Tests Remain Behavior-Equivalent

All 45 OpenBox tests must still pass. Coverage must remain for:

- OpenBox fake optimization artifacts.
- OpenBox real optimization with injected adapters.
- OpenBox strategy preset and explicit override routing.
- OpenBox continuation and model replay behavior.
- OpenBox effectiveness audit and advanced visualization report paths.
- OpenBox CLI dependency gate and continuation commands.
- Multi-corner/multi-testbench aggregate metric behavior.
- OpenBox candidate worker parallelism.
- OpenBox run retention behavior.
- OpenBox optimizer progress state sync.
- OpenBox initialization routing.
- OpenBox runtime thread audit.

### Direct Template Usage Removed

`tests/test_openbox_backend.py` must not import or call `create_project_from_template`.

Remove the local `_TEMPLATE_TEXT` bridge template and all `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, `rise`, `fall`, and `DC` leftovers from the file.

### Config Changes Happen Before Packaging When They Affect Package Semantics

For helper-created projects that need `max_evaluations`, OpenBox strategy, optimizer CPU threads, or Spectre keep flags, create the generic project, mutate structured YAML, then build the execution package, write pass reports, approve, and prepare the real run.

Do not create stale package hashes by mutating package-relevant config after `build_execution_package()` for helper setup paths.

### Generic Candidate and Metric Names

Project-backed assertions must derive variable and metric names from the generated generic project:

- Variables: use `variable_names(project_dir)` from `tests.real_run_smoke_helpers` or local YAML-derived helpers.
- Metrics: use `metric_names_for_run(project_dir)` or local YAML-derived helpers.
- Passing metric values: use `default_metric_values(project_dir, run_id="real_001")` where a prepared run exists, or derive names from `config/metrics.yaml` for report-only helper data.

### Requirement-Driven Multi-Testbench Fixture Preserved

`tests/test_openbox_backend.py` imports `_create_ready_multi_corner_multi_testbench_project` and `_write_corner_child_handoff` from `tests/test_multi_testbench_aggregation.py`.

Do not migrate those helpers in R2. They are requirement-driven fixtures already preserved by Phase 10, and their consumer coverage must remain green.

### Advisor Behavior Preserved Without Old Variable Names

`FakeAdvisor`, `ContinuationAdvisor`, `ExhaustingContinuationAdvisor`, and `SequentialAdvisor` must generate candidate dictionaries using project variable names from `_project_variable_grid(project_dir)`.

Do not retain a special hardcoded 4-variable `FN/WN/FP/WP` fallback. Multi-testbench projects with four variables must receive suggestions keyed by their actual variable names.

### Guard and Inventory Updated

Remove `tests/test_openbox_backend.py` from `ALLOWED_TEMPLATE_CALLERS`.

Expected guard count:

```text
6 -> 5
```

Update the inventory report:

- Add an R2 OpenBox section with exact verification results.
- Remove `tests/test_openbox_backend.py` from remaining migration waves.
- Correct any stale remaining-wave mention of `tests/test_real_result_record.py`; it was migrated in Phase 11 and is no longer a direct template caller.

## Required Verification

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC\|_TEMPLATE_TEXT" tests/test_openbox_backend.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_openbox_backend\|tests.test_openbox_backend" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- `tests/test_openbox_backend.py`: `45 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `46 passed, 13 warnings`
- OpenBox consumer group: `95 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_openbox_backend.py`: no output
- cross-import grep: no source-level consumers other than guard text before guard update; after guard update it has no output
- direct template caller list contains only:

```text
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Stop Conditions

Stop and report before editing outside scope if:

- A remote/adapter test must change to keep full suite green.
- Multi-testbench requirement fixtures must change.
- A production `src/` change appears necessary.
- The migration would weaken assertions to broad truthiness or type-only checks.
- OpenBox behavior must be changed rather than test setup being made generic.
