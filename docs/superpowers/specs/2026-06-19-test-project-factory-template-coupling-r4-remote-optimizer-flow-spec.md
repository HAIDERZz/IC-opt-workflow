# R4 Remote Optimizer Flow Template-Coupling Cleanup Spec

## Objective

Migrate `tests/test_remote_optimizer_flow.py` away from direct packaged-template usage while preserving all remote optimizer orchestration, continuation, adapter-routing, retention, sync, and audit coverage.

R4 must remove `tests/test_remote_optimizer_flow.py` from `ALLOWED_TEMPLATE_CALLERS`, leaving only the Spectre/OCEAN adapter files and the intentionally template-based package tests.

## Current State

R3 Remote Fix-Run has been committed as:

```text
34a5588 test: decouple remote fix-run tests from template
```

The remaining direct test callers of `create_project_from_template()` are:

```text
tests/test_package.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

Remote optimizer flow baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

Expected:

```text
21 passed, 13 warnings
```

Remote optimizer plus guard baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
22 passed, 13 warnings
```

## In Scope

Allowed files:

- `tests/test_remote_optimizer_flow.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Out of Scope

Do not modify:

- `src/`
- `tests/project_factory.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_package.py`
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

If any out-of-scope file appears required, stop and report the exact reason.

## Required Behavior

### Remote Optimizer Tests Remain Behavior-Equivalent

All 21 tests in `tests/test_remote_optimizer_flow.py` must still pass. Coverage must remain for:

- Remote doctor plus cache preparation feeding `optimize_project`.
- Remote native TuRBO path wrapping `run_remote_spectre_ocean_adapter`.
- Config-driven `turbo_trust_region` routing before local execution.
- Remote continuation not calling first-run `optimize_project`.
- Continuation argument propagation to OpenBox.
- Continuation fail-closed behavior when optimizer history is absent.
- Continuation manifest build when `execution_package/` is missing.
- Resource inheritance when `batch_size` and `parallel_jobs` are not explicitly overridden.
- Flow report writing.
- Remote history sync before additional evaluations.
- Strategy detail overrides staying `None` during continuation.
- Multi-testbench routing to `run_remote_multi_testbench_adapter`.
- Single-testbench routing to `run_remote_spectre_ocean_adapter`.
- Remote history download failure reporting.
- Remote retention deletion and keep behavior for successful and failed runs.
- Remote retention command safety.
- State sync in both directions.
- Remote transport mode in optimizer audit.

### Generic Optimize Factory Is the Source of Truth

Use:

```python
from tests.project_factory import create_generic_project
```

For tests that need a real project tree, use a local helper based on:

```python
create_generic_project(
    tmp_path,
    name="remote_optimizer_project",
)
```

Do not use `create_project_from_template()` in this test file.

Continuation-only tests that currently create only a minimal cache with `execution_package/` and `reports/optimizer_evaluations.jsonl` may stay minimal if they do not require a full project tree. Do not force generic factory into tests that intentionally exercise continuation control flow with mocked validation.

### Remove Old Template Coupling

`tests/test_remote_optimizer_flow.py` must not import or call `create_project_from_template`.

Remove or avoid old template assumptions:

- `bridge_test_inv`
- `FN`
- `WN`
- `FP`
- `WP`
- string replacement against packaged `optimizer.yaml` / `spectre.yaml`

Use structured YAML read/write helpers for config changes.

### Config Mutation Is Structured

Replace text-replacement helpers with YAML mutation helpers:

- Optimizer strategy changes should set `optimizer.algorithm` and `optimizer.strategy`.
- Retention changes should set `spectre.keep_failed_runs` and `spectre.keep_successful_runs`.

Do not rely on exact starter-template text such as `algorithm: turbo` or `keep_successful_runs: true`.

### Guard and Inventory Updated

Remove `tests/test_remote_optimizer_flow.py` from `ALLOWED_TEMPLATE_CALLERS`.

Expected guard count:

```text
4 -> 3
```

Update the inventory report:

- Add R4 Remote Optimizer Flow status with exact verification results.
- Remove `tests/test_remote_optimizer_flow.py` from remaining migration waves.
- Remaining migration wave should list only:

```text
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

`tests/test_package.py` remains intentionally template-based.

## Required Verification

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_optimizer_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_optimizer_flow\|tests.test_remote_optimizer_flow" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `21 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `22 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_remote_optimizer_flow.py`: no output
- cross-import grep: no source-level consumers other than guard text before guard update; after guard update it should have no output
- direct template caller list contains only:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Stop Conditions

Stop and report before editing outside scope if:

- `tests/test_remote_spectre_ocean.py` or `tests/test_spectre_ocean_adapter.py` must change.
- Production `src/` changes appear necessary.
- `tests/project_factory.py` cannot represent a needed remote optimizer project shape.
- Continuation tests would require weakening assertions instead of preserving behavior.
- Assertions would need to become broad truthiness, type-only checks, or merely "was called" checks where exact arguments are currently asserted.
