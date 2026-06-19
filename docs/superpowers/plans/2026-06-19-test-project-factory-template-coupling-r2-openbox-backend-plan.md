# R2 OpenBox Backend Template-Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove packaged-template coupling from `tests/test_openbox_backend.py` while preserving all OpenBox backend test coverage.

**Architecture:** Replace direct template project setup with local generic-project helpers that mutate structured YAML before packaging and approval. Candidate, metric, trace, and ledger data must derive from project config rather than old inverter variable names.

**Tech Stack:** Python tests, pytest, YAML config mutation, `tests.project_factory.create_generic_project`, existing Hermes package/approval/real-run helpers.

---

## File Map

- Modify `tests/test_openbox_backend.py`
  - Remove direct `create_project_from_template` usage.
  - Add generic OpenBox project helper and config helpers.
  - Replace old variable/metric literals in advisor, retention, trace, ledger, and runtime-audit tests.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_openbox_backend.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R2 status and remove OpenBox from remaining waves.
  - Remove stale remaining-wave mention of `tests/test_real_result_record.py`.

## Task 1: Baseline and Scope Check

**Files:**
- Verify: `tests/test_openbox_backend.py`
- Verify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Run OpenBox baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected:

```text
45 passed, 13 warnings
```

- [ ] **Step 2: Run OpenBox plus guard baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
46 passed, 13 warnings
```

- [ ] **Step 3: Run known consumer baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
95 passed, 13 warnings
```

- [ ] **Step 4: Capture direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected before R2:

```text
tests/test_openbox_backend.py
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 2: Replace Imports and Add Generic Helpers

**Files:**
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Update imports**

Replace:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template
```

with:

```python
from hermes_workflow.package import build_execution_package
```

Add top-level imports:

```python
import yaml

from tests.project_factory import create_generic_project
```

Keep these existing imports from `tests.real_run_smoke_helpers`:

```python
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    default_metric_values,
    metric_names_for_run,
    variable_names,
)
```

Remove `advisor_batches` from that import list after Task 3 replaces its use.

- [ ] **Step 2: Delete `_TEMPLATE_TEXT`**

Remove the local `_TEMPLATE_TEXT` constant and its comment.

- [ ] **Step 3: Add YAML helpers below `_project_variable_grid`**

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _set_optimizer_value(project_dir: Path, key: str, value: object) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    payload["optimizer"][key] = value
    _write_yaml(optimizer_path, payload)


def _set_spectre_value(project_dir: Path, key: str, value: object) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(spectre_path)
    payload["spectre"][key] = value
    _write_yaml(spectre_path, payload)
```

- [ ] **Step 4: Add metric helpers**

```python
def _metric_names_from_config(project_dir: Path) -> tuple[str, str]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    names = [metric["name"] for metric in payload["metrics"]]
    assert len(names) == 2
    return names[0], names[1]


def _passing_metric_values_from_config(project_dir: Path) -> dict[str, float]:
    objective_metric, constraint_metric = _metric_names_from_config(project_dir)
    return {objective_metric: 10.0, constraint_metric: 1.0e-6}


def _constraint_failing_metric_values_from_config(project_dir: Path) -> dict[str, float]:
    objective_metric, constraint_metric = _metric_names_from_config(project_dir)
    return {objective_metric: 10.0, constraint_metric: 1.0}
```

- [ ] **Step 5: Add generic OpenBox project helper**

```python
def _create_openbox_project(
    tmp_path: Path,
    *,
    name: str = "openbox_project",
    max_evaluations: int = 12,
    batch_size: int = 2,
    parallel_jobs: int = 4,
    algorithm: str = "openbox",
    strategy: str | None = None,
    optimizer_cpu_threads: int = 2,
    keep_failed_runs: bool = True,
    keep_successful_runs: bool = True,
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name=name,
        max_evaluations=max_evaluations,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
    )
    _set_optimizer_value(project_dir, "algorithm", algorithm)
    _set_optimizer_value(project_dir, "optimizer_cpu_threads", optimizer_cpu_threads)
    if strategy is not None:
        _set_optimizer_value(project_dir, "strategy", strategy)
    _set_spectre_value(project_dir, "keep_failed_runs", keep_failed_runs)
    _set_spectre_value(project_dir, "keep_successful_runs", keep_successful_runs)

    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir, variable_names=variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir
```

Do not run the target after this helper-only edit. Continue to Task 3 so the new helpers have migrated callers before the next test run.

## Task 3: Make Advisor Suggestions Generic

**Files:**
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Add local advisor batch helpers after `_project_variable_grid`**

```python
def _suggestion_from_grid(
    grid: list[dict[str, object]],
    *,
    offset: int,
) -> dict[str, float]:
    suggestion: dict[str, float] = {}
    for index, spec in enumerate(grid):
        values = spec["grid"]
        assert isinstance(values, list)
        suggestion[str(spec["name"])] = float(values[(offset + index) % len(values)])
    return suggestion


def _advisor_batches_for_project(project_dir: Path) -> list[list[dict[str, float]]]:
    grid = _project_variable_grid(project_dir)
    return [
        [
            _suggestion_from_grid(grid, offset=0),
            _suggestion_from_grid(grid, offset=1),
        ],
        [
            _suggestion_from_grid(grid, offset=2),
            _suggestion_from_grid(grid, offset=3),
        ],
    ]
```

- [ ] **Step 2: Update `FakeAdvisor`**

Replace its conditional two-variable/four-variable logic with:

```python
class FakeAdvisor:
    def __init__(self, project_dir: Path) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self._batches = _advisor_batches_for_project(project_dir)
```

- [ ] **Step 3: Update continuation advisors**

In `ContinuationAdvisor.__init__`, replace:

```python
baseline = advisor_batches(project_dir)
```

with:

```python
baseline = _advisor_batches_for_project(project_dir)
```

In `ExhaustingContinuationAdvisor.get_suggestions`, replace:

```python
baseline = advisor_batches(self._project_dir)
```

with:

```python
baseline = _advisor_batches_for_project(self._project_dir)
```

- [ ] **Step 4: Remove `advisor_batches` import**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected:

```text
45 passed, 13 warnings
```

If it fails only in multi-testbench aggregate metrics, inspect the candidate keys generated from `_project_variable_grid(project_dir)` and keep the fix inside `tests/test_openbox_backend.py`.

## Task 4: Replace Direct Template Project Helpers

**Files:**
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Replace `create_approved_real_project_with_optimizer_max`**

Replace the whole function with:

```python
def create_approved_real_project_with_optimizer_max(
    tmp_path: Path,
    max_evaluations: int,
) -> Path:
    return _create_openbox_project(
        tmp_path,
        name="openbox_optimizer_max_project",
        max_evaluations=max_evaluations,
    )
```

- [ ] **Step 2: Replace config strategy preset project setup**

In `test_run_openbox_real_optimization_applies_config_strategy_preset`, replace the manual `bridge_test_inv` setup block with:

```python
project_dir = _create_openbox_project(
    tmp_path,
    name="openbox_config_strategy_project",
    algorithm="openbox",
    strategy="openbox_gp_eic",
)
```

Keep the existing adapter body, but let `write_fake_metric_result_manifest(project_dir, run_id=run_id)` use generic default metrics.

- [ ] **Step 3: Replace keep-flags helper**

Replace `_create_approved_real_project_with_keep_flags` with:

```python
def _create_approved_real_project_with_keep_flags(
    tmp_path: Path,
    *,
    keep_failed_runs: bool,
    keep_successful_runs: bool,
) -> Path:
    return _create_openbox_project(
        tmp_path,
        name="openbox_retention_project",
        keep_failed_runs=keep_failed_runs,
        keep_successful_runs=keep_successful_runs,
    )
```

- [ ] **Step 4: Delete `_set_keep_flags_for_retention` if unused**

After Step 3, remove `_set_keep_flags_for_retention` if no references remain.

- [ ] **Step 5: Run direct-template grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|_TEMPLATE_TEXT" tests/test_openbox_backend.py || true
```

Expected:

```text
```

## Task 5: Replace Old Metric and Parameter Literals

**Files:**
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Update retention adapter metric manifests**

In both OpenBox batch evaluator retention tests, replace:

```python
values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
```

with:

```python
values=default_metric_values(project_dir, run_id=run_id)
```

inside the adapter.

- [ ] **Step 2: Update retention candidates**

For each `NativeTurboBatchCandidate` in the retention tests, derive variables:

```python
int_name, width_name = variable_names(project_dir)
```

Use:

```python
raw_x=[4.0, 0.5],
parameters={int_name: "4", width_name: "0.5u"},
```

- [ ] **Step 3: Replace `_make_split_openbox_traces`**

Change signature:

```python
def _make_split_openbox_traces(project_dir: Path):
```

At the top:

```python
from hermes_workflow.native_turbo import NativeTurboEvaluationTrace

int_name, width_name = variable_names(project_dir)
metrics = _passing_metric_values_from_config(project_dir)
```

For the first seven traces use:

```python
parameters={int_name: str(index + 2), width_name: "0.5u"},
metrics=metrics,
```

For the final three traces use:

```python
parameters={int_name: str(index + 9), width_name: "0.5u"},
metrics=None,
```

Keep statuses, objectives, batch metadata, and issues unchanged.

- [ ] **Step 4: Replace `_write_seven_ledger_rows_openbox` literals**

At the top:

```python
int_name, _width_name = variable_names(project_dir)
objective_metric, _constraint_metric = _metric_names_from_config(project_dir)
```

Use:

```python
"parameters": {int_name: "2"},
"metrics": {objective_metric: 1.0},
```

- [ ] **Step 5: Update progress sync caller**

In `test_write_openbox_reports_syncs_optimizer_progress_state`, replace:

```python
traces = _make_split_openbox_traces()
```

with:

```python
traces = _make_split_openbox_traces(project_dir)
```

- [ ] **Step 6: Run old-token grep**

```bash
grep -n "FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_openbox_backend.py || true
```

Expected:

```text
```

## Task 6: Replace Remaining Text-Based YAML Mutation

**Files:**
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Replace `_set_optimizer_max_evals_openbox`**

Replace the body with:

```python
def _set_optimizer_max_evals_openbox(project_dir: Path, value: int) -> None:
    _set_optimizer_value(project_dir, "max_evaluations", value)
```

- [ ] **Step 2: Replace `_set_optimizer_initialization`**

Replace the function body with:

```python
def _set_optimizer_initialization(
    project_dir: Path,
    *,
    initialization: str,
    algorithm: str = "openbox",
) -> None:
    _set_optimizer_value(project_dir, "algorithm", algorithm)
    _set_optimizer_value(project_dir, "initialization", initialization)
    _set_optimizer_value(project_dir, "max_evaluations", 4)
    _set_optimizer_value(project_dir, "batch_size", 2)
```

- [ ] **Step 3: Replace runtime thread audit mutations**

In these tests:

- `test_openbox_fake_run_writes_runtime_thread_audit`
- `test_openbox_report_contains_runtime_thread_limits`
- `test_openbox_separate_effectiveness_audit_file_has_runtime_thread_limits`

Replace direct `optimizer_path.write_text` replacement blocks with:

```python
_set_optimizer_value(project_dir, "optimizer_cpu_threads", 32)
```

- [ ] **Step 4: Keep `_set_config_parallelism` structured**

`_set_config_parallelism` already uses YAML and must stay structured. It may continue to assert prepared/request runtime metadata does not carry `parallel_jobs`.

- [ ] **Step 5: Run OpenBox target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected:

```text
45 passed, 13 warnings
```

## Task 7: Guard and Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove OpenBox from allowlist**

Remove:

```python
"tests/test_openbox_backend.py",
```

Expected allowlist count:

```text
6 -> 5
```

- [ ] **Step 2: Update remaining waves**

In the inventory report:

- Remove `tests/test_openbox_backend.py` from optimizer backend remaining work.
- Remove stale remaining-wave mention of `tests/test_real_result_record.py`.
- Leave `tests/test_package.py` as intentionally template-based.
- Leave remote/adapter flows for later:
  - `tests/test_remote_optimizer_flow.py`
  - `tests/test_remote_fix_run_flow.py`
  - `tests/test_remote_spectre_ocean.py`
  - `tests/test_spectre_ocean_adapter.py`

- [ ] **Step 3: Add R2 verification section**

Add:

```markdown
### R2 OpenBox Backend

- `pytest tests/test_openbox_backend.py -q` -> `45 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_openbox_backend.py tests/test_template_coupling_guard.py -q` -> `46 passed, 13 warnings`
- `pytest tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q` -> `95 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep forbidden tokens over `tests/test_openbox_backend.py` -> no matches
- grep cross-imports -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 6 -> 5.
```

## Task 8: Full Verification

**Files:**
- Verify: target, guard, consumer group, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected:

```text
45 passed, 13 warnings
```

- [ ] **Step 2: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run target plus guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
46 passed, 13 warnings
```

- [ ] **Step 4: Run known consumer group**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
95 passed, 13 warnings
```

- [ ] **Step 5: Run full suite**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 6: Run ruff**

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 8: Confirm release checkout untouched**

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 9: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC\|_TEMPLATE_TEXT" tests/test_openbox_backend.py || true
```

Expected: no output.

- [ ] **Step 10: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_openbox_backend\|tests.test_openbox_backend" tests || true
```

Expected: no output.

- [ ] **Step 11: Run direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 9: Final Report

Report:

1. Files modified.
2. OpenBox migration summary.
3. Guard allowlist count `6 -> 5`.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
