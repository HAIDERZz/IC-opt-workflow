# R3 Remote Fix-Run Template-Coupling Cleanup Spec

## Objective

Migrate `tests/test_remote_fix_run_flow.py` away from direct packaged-template usage while preserving all remote fix-run orchestration coverage.

R3 must remove `tests/test_remote_fix_run_flow.py` from `ALLOWED_TEMPLATE_CALLERS`, leaving only remote optimizer, Spectre/OCEAN adapter flows, and the intentionally template-based package tests.

## Current State

R2 OpenBox has been committed. The remaining direct test callers of `create_project_from_template()` are:

```text
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

Remote fix-run baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected:

```text
11 passed, 13 warnings
```

## In Scope

Allowed files:

- `tests/test_remote_fix_run_flow.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Out of Scope

Do not modify:

- `src/`
- `tests/project_factory.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_package.py`
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

If any out-of-scope file appears required, stop and report the exact reason.

## Required Behavior

### Remote Fix-Run Tests Remain Behavior-Equivalent

All 11 remote fix-run tests must still pass. Coverage must remain for:

- Remote doctor failure blocks execution.
- Fixed-point artifacts are uploaded or remote adapter path is reached.
- `reports/fix_run_report.json` is written.
- Remote Spectre/OCEAN adapter is called for child runs.
- Remote adapter failures preserve waveform export issues.
- Product CLI dispatches remote fix-run for `workflow_mode=fix_run`.
- Parent report collects waveform export manifests and CSV artifacts.
- Remote flow does not import optimizer approval.
- Remote child-level parallelism uses `spectre.parallel_jobs`.
- `parallel_jobs: 1` keeps child runs serial.
- Child failure under parallel execution is preserved and fails the parent report.

### Generic Fix-Run Factory Is the Source of Truth

Use:

```python
from tests.project_factory import create_generic_project
```

Create remote fix-run projects with:

```python
create_generic_project(
    tmp_path,
    name="remote_fix_run_project",
    workflow_mode="fix_run",
    parallel_jobs=4,
)
```

Do not hand-write `workflow.yaml`, `fixed_points.yaml`, or Spectre templates in each test.

### Remove Old Template Coupling

`tests/test_remote_fix_run_flow.py` must not import or call `create_project_from_template`.

Remove old project names and variables from the file:

- `bridge_test_inv`
- `remote_fix_run_test` only if it exists solely as a packaged-template project name
- `FN`
- `WN`
- `FP`
- `WP`

Generic fixed-point parameters must be read from `config/fixed_points.yaml`, not hardcoded.

### Waveform Export Setup Is Explicit

For tests that assert waveform artifacts or waveform artifact gates, add a small helper that writes `config/waveform_exports.yaml`.

Do not remove `metrics.yaml` unless the test explicitly needs a waveform-only contract. The generic fix-run factory already removes `optimizer.yaml` for `workflow_mode="fix_run"`.

### Guard and Inventory Updated

Remove `tests/test_remote_fix_run_flow.py` from `ALLOWED_TEMPLATE_CALLERS`.

Expected guard count:

```text
5 -> 4
```

Update the inventory report:

- Add R3 Remote Fix-Run status with exact verification results.
- Remove `tests/test_remote_fix_run_flow.py` from remaining migration waves.

## Required Verification

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_fix_run_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_fix_run_flow\|tests.test_remote_fix_run_flow" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `11 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `12 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_remote_fix_run_flow.py`: no output
- cross-import grep: no source-level consumers other than guard text before guard update; after guard update it has no output
- direct template caller list contains only:

```text
tests/test_package.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Stop Conditions

Stop and report before editing outside scope if:

- Remote optimizer, remote Spectre/OCEAN, or local Spectre/OCEAN tests must change.
- Production `src/` changes appear necessary.
- The generic fix-run factory cannot represent a needed remote fix-run project shape.
- Assertions would need to be weakened to broad truthiness or type-only checks.
