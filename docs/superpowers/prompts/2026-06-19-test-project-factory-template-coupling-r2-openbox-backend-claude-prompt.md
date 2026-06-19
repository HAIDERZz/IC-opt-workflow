# Claude Prompt: R2 OpenBox Backend Template-Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r2-openbox-backend-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r2-openbox-backend-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

## Goal

Migrate `tests/test_openbox_backend.py` away from direct packaged-template usage while preserving all 45 OpenBox backend tests and related consumer coverage.

## Strict Scope

Allowed to modify:

```text
tests/test_openbox_backend.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/real_run_smoke_helpers.py
tests/test_multi_testbench_aggregation.py
tests/test_remote_spectre_ocean.py
tests/test_remote_optimizer_flow.py
tests/test_remote_fix_run_flow.py
tests/test_spectre_ocean_adapter.py
tests/test_package.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

If an out-of-scope file looks necessary, stop and report the reason.

## Required Changes

In `tests/test_openbox_backend.py`:

1. Remove `create_project_from_template` import and calls.
2. Remove `_TEMPLATE_TEXT`.
3. Add `yaml` and `create_generic_project`.
4. Add local helpers:
   - `_read_yaml`
   - `_write_yaml`
   - `_set_optimizer_value`
   - `_set_spectre_value`
   - `_metric_names_from_config`
   - `_passing_metric_values_from_config`
   - `_constraint_failing_metric_values_from_config`
   - `_create_openbox_project`
   - `_suggestion_from_grid`
   - `_advisor_batches_for_project`
5. Ensure `_create_openbox_project` mutates config before `build_execution_package()`, `write_pass_reports()`, approval, and `prepare_real_run()`.
6. Replace hardcoded `FN/WN/FP/WP` advisor fallback with `_advisor_batches_for_project(project_dir)` for all variable counts.
7. Replace retention candidates with `variable_names(project_dir)` derived parameters.
8. Replace old metric manifests with `default_metric_values(project_dir, run_id=run_id)` or config-derived metric helpers.
9. Make `_make_split_openbox_traces(project_dir)` and `_write_seven_ledger_rows_openbox(project_dir)` derive variable and metric names from the project.
10. Replace text-based optimizer YAML edits with `_set_optimizer_value`.
11. Keep requirement-driven multi-testbench fixture imports from `tests/test_multi_testbench_aggregation.py`; do not migrate those helpers in R2.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_openbox_backend.py",
```

Expected allowlist count: `6 -> 5`.

In the inventory report:

- Add R2 OpenBox status and verification.
- Remove `tests/test_openbox_backend.py` from remaining waves.
- Remove stale remaining-wave mention of `tests/test_real_result_record.py`; it was already migrated in Phase 11.

## Required Verification

Run exactly:

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

- target: `45 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `46 passed, 13 warnings`
- OpenBox consumer group: `95 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep: no output
- cross-import grep: no output
- direct template caller list:

```text
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_openbox_backend.py`.
3. Guard allowlist count.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that no production files, release files, or `graphify-out/` were touched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.

