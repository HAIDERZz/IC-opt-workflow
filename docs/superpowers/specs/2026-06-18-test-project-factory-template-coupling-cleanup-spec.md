# Test Project Factory and Template Coupling Cleanup Spec

## Problem

`create_project_from_template()` is a healthy product API for `hermes-workflow init` and for tests that verify packaging/template behavior. It is not healthy as a generic fixture for most optimizer, approval, remote, real-run, and adapter tests.

Current graph/source audit shows:

- `create_project_from_template()` has very high graph degree.
- It is called directly in 25 test files.
- It appears roughly 160 times in tests.
- Many callers use `bridge_test_inv`, `FN/WN/FP/WP`, and inverter-oriented metric names as an implicit "valid project" baseline.
- This couples unrelated tests to the current release template contents. A template update can break tests that are not actually testing templates.

This is the same failure pattern that previously caused release/example/template drift: local tests passed because stale or template-specific assumptions remained embedded in unrelated tests.

## Goal

Create a dedicated generic test project factory so most tests can build minimal valid projects without depending on the packaged release template.

`create_project_from_template()` should remain the source of truth only for:

- Template copy behavior.
- Packaged resource inclusion.
- `hermes-workflow init` / product template behavior.
- Explicit tests that intentionally verify the release example/template tree.

All other tests should prefer a shared test factory that writes the exact project shape needed by the behavior under test.

## Non-Goals

This spec does not require changing product runtime behavior.

Do not:

- Change `src/hermes_workflow/package.py` behavior.
- Change release examples or packaged templates.
- Change `opt_requirement.md` examples.
- Rewrite optimizer algorithms.
- Rename user-facing config fields.
- Migrate every test in one large edit.
- Touch release checkout `ic-auto-opt-workflow-v0.1`.
- Commit or include `graphify-out/`.

## Design Principles

1. **Template tests stay template-based.**  
   `tests/test_package.py` should continue to use `create_project_from_template()` for template creation, resource packaging, and template tree assertions.

2. **Behavior tests use generic factories.**  
   Tests for approvals, health, real-run, retention, remote flow, optimizer state, and adapter behavior should use a generic factory unless they explicitly assert template contents.

3. **Factories should be metric/variable generic.**  
   The default factory must not use `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, `rise`, `fall`, or `DC`.

4. **Circuit-specific names are profiles, not defaults.**  
   If a low-level optimizer quantization test really needs integer and continuous variable examples, it can request a named profile. That profile should be local to the test purpose and documented.

5. **Guard against drift.**  
   Add a test that audits direct `create_project_from_template()` usage and allows it only in an explicit allowlist. The allowlist should shrink over phases.

6. **Small migration waves.**  
   Migrate tests in waves. Each wave should pass focused tests and full pytest before the next wave starts.

## Proposed Factory API

Create `tests/project_factory.py` with these public helpers:

```python
def create_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    workflow_mode: str = "optimize",
    variable_names: tuple[str, ...] = ("VAR_INT", "VAR_WIDTH"),
    metric_names: tuple[str, ...] = ("metric_gain", "metric_power"),
    require_license_check: bool = True,
    parallel_jobs: int = 4,
    batch_size: int = 2,
    max_evaluations: int = 6,
) -> Path: ...
```

```python
def create_packaged_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    created_at_utc: str = "2026-06-18T00:00:00Z",
    **kwargs: object,
) -> Path: ...
```

```python
def create_approved_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    created_at_utc: str = "2026-06-18T00:00:00Z",
    **kwargs: object,
) -> Path: ...
```

```python
def write_generic_pass_reports(
    project_dir: Path,
    *,
    variable_names: tuple[str, ...] | None = None,
) -> None: ...
```

The factory should write:

- `config/project_config.yaml`
- `config/variables.yaml`
- `config/metrics.yaml`
- `config/spectre.yaml`
- `config/optimizer.yaml`
- `netlists/exported/input.scs`
- `netlists/templates/template.scs`
- empty `execution_package/`, `reports/`, `state/`, `ledger/`, `runs/real/`

The generated project must pass:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_project_factory.py -q
```

and direct validation:

```python
assert validate_project_files(project_dir).ok is True
assert_valid_project(project_dir)
```

## Default Generic Project Shape

Default project name:

```text
generic_project
```

Default variables:

```yaml
variables:
  - name: VAR_INT
    kind: integer
    lower: "1"
    upper: "5"
    step: "1"
  - name: VAR_WIDTH
    kind: continuous_step
    lower: "0.1u"
    upper: "0.5u"
    step: "0.1u"
```

Default metrics:

```yaml
metrics:
  - name: metric_gain
    unit: V/V
    maestro_formula: value(v("/OUT") 1n)
    required_signals: ["/OUT"]
    ocean:
      expression: value(v("/OUT") 1n)
      result: tran
      expression_source: user_approved
      source_reference: test_factory:generic:metric_gain
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail
  - name: metric_power
    unit: W
    maestro_formula: value(i("/VDD") 1n)
    required_signals: ["/VDD"]
    ocean:
      expression: value(i("/VDD") 1n)
      result: tran
      expression_source: user_approved
      source_reference: test_factory:generic:metric_power
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail
constraints:
  - metric: metric_power
    op: lt
    value: "1e-3 W"
objective:
  direction: maximize
  expression: "metric_gain - metric_power"
```

Default netlist template:

```spectre
// generic test template
parameters VAR_INT={{VAR_INT}} VAR_WIDTH={{VAR_WIDTH}}
tran tran stop=10n
```

## Migration Classification

### Keep template-based

These tests should continue to use `create_project_from_template()`:

- `tests/test_package.py` template creation tests.
- `tests/test_package.py` packaged resource tests.
- `src/hermes_workflow/cli.py:init_command()` product behavior.
- Tests that intentionally verify `hermes-workflow init`.

### Migrate first

Low-risk first wave:

- `tests/test_approvals.py`
- `tests/test_health.py`
- `tests/test_optimizer_flow.py`
- `tests/test_metric_results.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run.py`
- `tests/test_result_handoff.py`
- `tests/test_real_run_recovery.py`

These mostly need a valid project, execution package, preflight reports, or real-run directory facts. They do not need packaged template semantics.

### Migrate later

Larger follow-up waves:

- `tests/test_optimizer_task_package.py`
- `tests/test_run_retention.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_openbox_backend.py`
- `tests/test_native_turbo.py`
- `tests/test_mock_optimizer.py`

These contain more assumptions about variable names, optimizer traces, remote paths, candidate parameters, and adapter artifacts. They should be migrated in smaller focused batches after the factory is proven.

## Acceptance Criteria

Phase 1 is complete when:

- `tests/project_factory.py` exists and creates a valid generic project.
- `tests/test_project_factory.py` proves the factory is independent of packaged templates.
- First-wave tests are migrated away from `create_project_from_template()`.
- A guard test reports direct `create_project_from_template()` usage and enforces an explicit allowlist.
- The allowlist allows only intentionally template-based tests plus not-yet-migrated files with comments.
- Focused tests pass.
- Full pytest passes.
- Ruff passes.
- `graphify-out/` remains untracked and untouched.

Final cleanup is complete when:

- Direct test calls to `create_project_from_template()` remain only in template/product-init tests.
- No generic behavior test depends on `bridge_test_inv`, `FN/WN/FP/WP`, `rise/fall/DC`, or Mixer-specific names unless that is the behavior under test.
- A template update no longer causes unrelated optimizer/remote/real-run tests to fail.
