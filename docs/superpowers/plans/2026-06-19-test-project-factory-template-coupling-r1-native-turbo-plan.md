# R1 Native TuRBO Template Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_native_turbo.py` from the packaged release template while preserving all Native TuRBO behavior coverage.

**Architecture:** Replace direct packaged-template setup with generic factory projects and derive variable, metric, scheduler, and retention expectations from generated config or runtime artifacts. Keep requirement-intake fixtures where tests intentionally cover multi-testbench/corner behavior, but remove old inverter-specific candidate payloads from those tests. Update the guard and inventory in the same phase.

**Tech Stack:** Python, pytest, PyYAML, `tests/project_factory.py`, `tests/real_run_smoke_helpers.py`, `hermes_workflow.native_turbo`.

---

## File Structure

- Modify `tests/test_native_turbo.py`
  - Remove `create_project_from_template`.
  - Add generic project/config helpers.
  - Rename standalone variable fixtures from old inverter names to neutral names.
  - Migrate project-backed setup to `create_generic_project()` or existing generic real-run helpers.
  - Replace string config rewrites with structured YAML mutation.

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_native_turbo.py` from allowlist.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R1/Native TuRBO status and verification.
  - Remove Native TuRBO from remaining waves.

## Task 0: Baseline and Orientation

**Files:**
- Read: `tests/test_native_turbo.py`
- Read: `tests/project_factory.py`
- Read: `tests/real_run_smoke_helpers.py`
- Read: `src/hermes_workflow/native_turbo.py`

- [ ] **Step 1: Confirm baseline target test**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

Expected:

```text
49 passed, 13 warnings
```

- [ ] **Step 2: Confirm direct template coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_native_turbo.py || true
```

Expected before edits: many matches.

- [ ] **Step 3: Confirm current direct caller set**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_native_turbo\|tests.test_native_turbo" tests || true
```

Expected before edits: no source-level consumers, except the guard while it still allowlists the file.

## Task 1: Add Generic Helpers

**Files:**
- Modify: `tests/test_native_turbo.py`

- [ ] **Step 1: Update imports**

Remove `create_project_from_template` from:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template
```

so it becomes:

```python
from hermes_workflow.package import build_execution_package
```

Add imports:

```python
import yaml

from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add YAML/config helpers near the top**

Add after imports:

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _create_native_project(
    tmp_path: Path,
    *,
    name: str = "native_turbo_project",
    batch_size: int = 2,
    parallel_jobs: int = 4,
    max_evaluations: int = 6,
) -> Path:
    return create_generic_project(
        tmp_path,
        name=name,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        max_evaluations=max_evaluations,
    )


def _variable_names(project_dir: Path) -> tuple[str, str]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    names = [variable["name"] for variable in payload["variables"]]
    assert len(names) == 2
    return names[0], names[1]


def _metric_names(project_dir: Path) -> tuple[str, str]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    names = [metric["name"] for metric in payload["metrics"]]
    assert len(names) == 2
    return names[0], names[1]


def _candidate_parameters(
    project_dir: Path,
    *,
    int_value: str = "3",
    width_value: str = "0.3u",
) -> dict[str, str]:
    int_name, width_name = _variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}


def _passing_metric_values(project_dir: Path) -> dict[str, float]:
    gain_name, power_name = _metric_names(project_dir)
    return {gain_name: 1.0, power_name: 1.0e-4}


def _constraint_failing_metric_values(project_dir: Path) -> dict[str, float]:
    gain_name, power_name = _metric_names(project_dir)
    return {gain_name: 1.0, power_name: 1.0}


def _set_optimizer_value(project_dir: Path, key: str, value: object) -> None:
    path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(path)
    payload["optimizer"][key] = value
    _write_yaml(path, payload)


def _set_spectre_value(project_dir: Path, key: str, value: object) -> None:
    path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(path)
    payload["spectre"][key] = value
    _write_yaml(path, payload)
```

## Task 2: Neutralize Standalone Variable Fixtures

**Files:**
- Modify: `tests/test_native_turbo.py`
- Test: `tests/test_native_turbo.py`

- [ ] **Step 1: Rename `_variables_config()` variable names**

Change `_variables_config()` to return `VAR_INT` and `VAR_WIDTH`:

```python
def _variables_config() -> VariablesConfig:
    return VariablesConfig(
        schema_version="1.0",
        variables=[
            VariableSpec(
                name="VAR_INT",
                kind=VariableKind.INTEGER,
                lower="2",
                upper="12",
                step="1",
            ),
            VariableSpec(
                name="VAR_WIDTH",
                kind=VariableKind.CONTINUOUS_STEP,
                lower="0.3u",
                upper="2.0u",
                step="0.1u",
            ),
        ],
    )
```

- [ ] **Step 2: Update standalone quantize tests**

Use neutral names:

```python
assert quantize_candidate(variables, [11.6, 1.94]) == {"VAR_INT": "12", "VAR_WIDTH": "1.9u"}
assert quantize_candidate(variables, [0.0, 3.0]) == {"VAR_INT": "2", "VAR_WIDTH": "2u"}
```

For the single continuous variable clamp test, use `VAR_WIDTH` and assert:

```python
assert quantize_candidate(variables, [3.0]) == {"VAR_WIDTH": "2.9u"}
assert quantize_candidate(variables, [3.1]) == {"VAR_WIDTH": "2.9u"}
```

- [ ] **Step 3: Update runner expected parameters**

Replace old expected dictionaries:

```python
{"FN": "2", "WN": "0.3u"}
```

with:

```python
{"VAR_INT": "2", "VAR_WIDTH": "0.3u"}
```

Apply this to:

- `test_runner_calls_turbo_optimize_and_records_phases`
- `test_runner_replaces_duplicate_quantized_candidate_before_evaluation`
- `test_runner_records_duplicate_penalty_when_no_replacement_is_allowed`
- `test_batch_runner_records_batch_metadata_and_order`

- [ ] **Step 4: Update workflow-failure issue string**

Change:

```python
issues=[f"no result manifest for {parameters['FN']}"]
```

to:

```python
issues=[f"no result manifest for {parameters['VAR_INT']}"]
```

- [ ] **Step 5: Run target test**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

Expected: failures may remain in project-backed tests until later tasks.

## Task 3: Migrate Direct Project-Backed Native TuRBO Tests

**Files:**
- Modify: `tests/test_native_turbo.py`

- [ ] **Step 1: Migrate `test_load_native_turbo_contract_reads_existing_project`**

Use:

```python
project_dir = _create_native_project(tmp_path)
contract = load_native_turbo_contract(project_dir)
assert [variable.name for variable in contract.variables.variables] == list(_variable_names(project_dir))
assert contract.optimizer.optimizer.failure_penalty > 0
assert contract.metrics.objective.expression
```

- [ ] **Step 2: Migrate `test_run_native_turbo_optimization_writes_compact_trace_files`**

Use:

```python
project_dir = _create_native_project(tmp_path)
expected_variables = set(_variable_names(project_dir))

def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
    assert set(parameters) == expected_variables
    return NativeTurboObservation(metrics=_passing_metric_values(project_dir))
```

Keep existing assertions for report path, evaluation count, best candidate,
initialization, effective initial design, and evaluations JSONL line count.

- [ ] **Step 3: Migrate batch optimizer tests**

For `test_run_batch_native_turbo_optimization_uses_optimizer_batch_size`, create:

```python
project_dir = _create_native_project(tmp_path, batch_size=5, parallel_jobs=5, max_evaluations=6)
```

Then assert:

```python
assert observed_batch_sizes == [5]
```

For `test_run_batch_native_turbo_optimization_accepts_adapter_argument`, use
`_passing_metric_values(project_dir)` in the batch evaluator and keep the report
runtime-thread assertions.

- [ ] **Step 4: Migrate CPU thread limit test**

Create:

```python
project_dir = _create_native_project(tmp_path)
_set_optimizer_value(project_dir, "optimizer_cpu_threads", 3)
```

Keep the monkeypatch and assert the call remains:

```python
assert calls == [(3, {"set_environment": True, "backend": "native_turbo", "execution_mode": "local"})]
```

- [ ] **Step 5: Run target test**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

## Task 4: Migrate Parallelism, Retention, and Progress Helpers

**Files:**
- Modify: `tests/test_native_turbo.py`

- [ ] **Step 1: Replace `_set_native_turbo_config_parallelism` with YAML mutation**

Use:

```python
def _set_native_turbo_config_parallelism(
    project_dir: Path,
    *,
    batch_size: int,
    parallel_jobs: int,
) -> None:
    _set_optimizer_value(project_dir, "batch_size", batch_size)
    _set_spectre_value(project_dir, "parallel_jobs", parallel_jobs)
```

- [ ] **Step 2: Migrate `test_native_turbo_uses_requirement_parallel_jobs_for_candidate_workers`**

Replace project setup with:

```python
project_dir = _create_native_project(
    case_root,
    name="project",
    batch_size=batch_size,
    parallel_jobs=parallel_jobs,
)
```

Keep the assertion that `runs/` is absent if the generic factory creates a
`runs/real` skeleton by changing it to:

```python
assert not any((project_dir / "runs" / "real").iterdir())
```

If this does not match the factory output, derive a precise empty-run assertion
from the actual factory directory shape and document it in the report.

- [ ] **Step 3: Replace `_set_keep_flags_for_retention` with YAML mutation**

Use:

```python
def _set_keep_flags_for_retention(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    _set_spectre_value(project_dir, "keep_failed_runs", keep_failed_runs)
    _set_spectre_value(project_dir, "keep_successful_runs", keep_successful_runs)
```

- [ ] **Step 4: Migrate `_create_approved_real_project_with_keep_flags`**

Use `create_generic_project()` instead of `create_project_from_template()` so
flags are changed before packaging:

```python
project_dir = create_generic_project(tmp_path, name="native_turbo_retention_project")
_set_keep_flags_for_retention(
    project_dir,
    keep_failed_runs=keep_failed_runs,
    keep_successful_runs=keep_successful_runs,
)
build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
instruction = decide_first_real_run(project_dir, created_at_utc="2026-06-03T00:10:00Z")
assert instruction["decision"] == "approve_first_real_run"
prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
return project_dir
```

Add `prepare_real_run` import locally or at module top if needed.

- [ ] **Step 5: Update retention tests**

Use:

```python
parameters=_candidate_parameters(project_dir, int_value="4", width_value="0.5u")
```

For successful metrics:

```python
values=_passing_metric_values(project_dir)
```

For constraint fail:

```python
values=_constraint_failing_metric_values(project_dir)
```

Update comments to refer to the generic power constraint, not old `rise`.

- [ ] **Step 6: Update progress-state helpers**

Change `_make_split_native_turbo_traces()` to accept `project_dir: Path` and use
generic names:

```python
def _make_split_native_turbo_traces(project_dir: Path) -> list[NativeTurboEvaluationTrace]:
    int_name, width_name = _variable_names(project_dir)
    gain_name, power_name = _metric_names(project_dir)
```

Use `{int_name: 2.0, width_name: 0.5}` for parameters and
`{gain_name: 1.0, power_name: 1.0e-4}` for metrics.

Change `_write_seven_ledger_rows(project_dir)` to derive the same names.

- [ ] **Step 7: Use generic project for progress sync**

In `test_write_native_turbo_reports_syncs_optimizer_progress_state`, use:

```python
project_dir = _create_native_project(tmp_path, max_evaluations=10)
_set_optimizer_max_evaluations_for_native(project_dir, 10)
_write_seven_ledger_rows(project_dir)
traces = _make_split_native_turbo_traces(project_dir)
```

- [ ] **Step 8: Run target test**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

## Task 5: Migrate CLI and Report-Only Fixtures

**Files:**
- Modify: `tests/test_native_turbo.py`

- [ ] **Step 1: Rename CLI dummy project paths**

For CLI tests that monkeypatch the optimizer runner and only need a path, replace:

```python
project_dir = tmp_path / "bridge_test_inv"
```

with:

```python
project_dir = tmp_path / "native_turbo_cli_project"
```

or:

```python
project_dir = tmp_path / "native_turbo_parallel_cli_project"
```

- [ ] **Step 2: Neutralize report-only traces**

In `test_write_native_turbo_reports_includes_batch_summary` and
`test_native_turbo_report_records_initialization`, replace old parameter payloads
with neutral names:

```python
parameters={"VAR_INT": "4", "VAR_WIDTH": "0.5u"}
```

Use neutral metrics already present (`delay`, `gain`) or generic names. Do not
use old packaged-template metrics.

- [ ] **Step 3: Migrate CPU report tests**

For:

- `test_native_turbo_report_contains_optimizer_cpu_threads`
- `test_native_turbo_report_contains_runtime_thread_limits`
- `test_native_turbo_effectiveness_audit_contains_runtime_thread_limits`

Use:

```python
project_dir = _create_native_project(tmp_path)
_set_optimizer_value(project_dir, "optimizer_cpu_threads", 32)

def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
    return NativeTurboObservation(metrics=_passing_metric_values(project_dir))
```

Keep assertions for report fields and env vars.

- [ ] **Step 4: Run target test**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

Expected:

```text
49 passed, 13 warnings
```

## Task 6: Drift Cleanup and Guard Shrink

**Files:**
- Modify: `tests/test_native_turbo.py`
- Modify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Run drift grep**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_native_turbo.py || true
```

Expected: no output.

- [ ] **Step 2: Remove Native TuRBO from guard allowlist**

In `tests/test_template_coupling_guard.py`, remove:

```python
"tests/test_native_turbo.py",
```

Expected allowlist entries after edit:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/test_openbox_backend.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_spectre_ocean_adapter.py",
}
```

- [ ] **Step 3: Run target plus guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
50 passed, 13 warnings
```

## Task 7: Update Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Add R1 status section**

Add a section before Phase 13:

```markdown
## R1 Native TuRBO status

Migrated `tests/test_native_turbo.py` away from direct
`create_project_from_template()` usage. Project-backed tests now create generic
projects through `tests/project_factory.py` or use existing generic real-run
helpers. Standalone runner/quantization/report fixtures use neutral variable and
metric names. Config mutation helpers now use structured YAML for optimizer and
Spectre settings.

Coverage preserved: Native TuRBO contract loading, candidate quantization,
objective evaluation, duplicate replacement/skip behavior, workflow failure
limits, batch metadata, compact trace reports, real candidate and batch
evaluators, multi-testbench/corner adapter dispatch, run retention integration,
optimizer progress sync, initialization reporting, and runtime thread-limit
audits.

`tests/test_native_turbo.py` was removed from `ALLOWED_TEMPLATE_CALLERS`
(allowlist 7 -> 6).
```

- [ ] **Step 2: Remove from remaining waves**

Remove `tests/test_native_turbo.py` from the remaining optimizer backend wave.

- [ ] **Step 3: Add exact verification results**

Add:

```markdown
### R1 Native TuRBO

- `pytest tests/test_native_turbo.py -q` -> `49 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_native_turbo.py tests/test_template_coupling_guard.py -q` -> `50 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean
- grep forbidden tokens over `tests/test_native_turbo.py` -> no matches
- grep cross-imports -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 7 -> 6.
```

## Task 8: Full Verification

**Files:**
- Verify target, guard, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
```

- [ ] **Step 2: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

- [ ] **Step 3: Run target plus guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_template_coupling_guard.py -q
```

- [ ] **Step 4: Run full suite**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

- [ ] **Step 5: Run ruff**

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

- [ ] **Step 6: Run whitespace check**

```bash
git diff --check
```

- [ ] **Step 7: Confirm release checkout untouched**

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

- [ ] **Step 8: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_native_turbo.py || true
```

- [ ] **Step 9: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_native_turbo\|tests.test_native_turbo" tests || true
```

Expected final status:

- `tests/test_native_turbo.py`: `49 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `50 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep: no output
- cross-import grep: no source-level matches

## Task 9: Final Report

Report:

- Files modified.
- Native TuRBO migration summary.
- Guard allowlist count `7 -> 6`.
- Exact verification commands and pass/fail counts.
- Drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Remaining deferred allowlist files:

```text
tests/test_package.py
tests/test_openbox_backend.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

Do not commit, tag, push, or publish.

## Stop Conditions

Stop and report before widening scope if:

- Production code under `src/` appears necessary.
- `tests/project_factory.py` or `tests/real_run_smoke_helpers.py` must change.
- `tests/test_openbox_backend.py` or remote/adapter tests must change.
- Full-suite failures appear outside this phase and cannot be tied directly to
  this migration.
