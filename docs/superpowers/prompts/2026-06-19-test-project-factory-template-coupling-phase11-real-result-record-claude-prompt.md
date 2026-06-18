# Claude Prompt: Phase 11 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 11 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-phase11-real-result-record-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-phase11-real-result-record-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_project_factory.py
tests/test_real_result_record.py
tests/test_template_coupling_guard.py
tests/test_cli.py
src/hermes_workflow/real_result_record.py
src/hermes_workflow/mock_optimizer.py
```

If codegraph and graphify are available, use them for orientation only. Source
files and tests are authoritative. Do not use graph output as a reason to widen
scope.

## Objective

Migrate:

```text
tests/test_real_result_record.py
```

away from direct `create_project_from_template()` usage and old inverter-specific
fixture assumptions. Preserve the real-result recording behavior and preserve the
helper names imported by `tests/test_cli.py`.

## Strict Scope

Allowed to modify only:

```text
tests/test_real_result_record.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_project_factory.py
tests/test_cli.py
tests/real_run_smoke_helpers.py
tests/test_package.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

Do not commit, tag, push, or publish.

## Required Implementation

### tests/test_real_result_record.py

Remove direct template setup:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from tests.report_helpers import write_pass_reports
```

Keep:

```python
from hermes_workflow.package import sha256_file
```

Add:

```python
from tests.project_factory import create_approved_generic_project
```

Delete the old `TEMPLATE_TEXT`.

Replace `_create_ready_project()` with:

```python
def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        name="real_result_record_project",
        created_at_utc="2026-06-02T00:00:00Z",
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir
```

Keep `_create_ready_project()` and `_write_valid_checked_result()` as exported
helpers; `tests/test_cli.py` imports them.

Add derived helper functions after `_load_json()`:

```python
def _candidate_parameters(project_dir: Path) -> dict[str, str]:
    payload = _load_json(
        project_dir / "runs" / "real" / "real_001" / "candidate.json"
    )
    parameters = payload["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}

def _metric_names(project_dir: Path) -> tuple[str, str]:
    request = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metric_extraction_request.json"
    )
    metrics = request["metrics"]
    assert isinstance(metrics, list)
    names = [metric["name"] for metric in metrics]
    assert len(names) == 2
    assert all(isinstance(name, str) for name in names)
    return names[0], names[1]

def _metric_values(
    project_dir: Path,
    *,
    objective_value: float = 1.0,
    constraint_value: float = 1.0e-4,
) -> dict[str, float]:
    objective_metric, constraint_metric = _metric_names(project_dir)
    return {
        objective_metric: objective_value,
        constraint_metric: constraint_value,
    }

def _objective_cost(project_dir: Path, values: dict[str, float]) -> float:
    objective_metric, constraint_metric = _metric_names(project_dir)
    return -(values[objective_metric] - values[constraint_metric])
```

Update `_write_metric_result_manifest()`:

```python
metric_values = values or _metric_values(project_dir)
```

Then migrate all old parameter/metric fixtures:

- Replace `{"FN": ..., "WN": ..., "FP": ..., "WP": ...}` assertions with
  `_candidate_parameters(project_dir)` or neutral schema-only names in pure model
  tests.
- Replace old metric dictionaries with `_metric_values(project_dir, ...)`.
- For constraint-failing tests, use a constrained metric above `1e-3`, for
  example `constraint_value=1.0`.
- For feasible tests, use `constraint_value=1.0e-4`.
- For objective assertions, use `_objective_cost(project_dir, values)`.
- For existing-best tests, choose explicit objective relationships:
  - better existing best: more negative objective cost than the real result
  - worse existing best: less favorable objective cost than the real result
  - infeasible best: `constraints_passed=False`

The generic factory default objective is maximize
`<first_metric> - <second_metric>`. `record_real_result()` stores maximize
objectives as negative cost. The maximize-normalization test should not edit
`metrics.yaml`; assert that the default maximize objective records a negative
cost:

```python
values = _metric_values(project_dir, objective_value=2.0, constraint_value=1.0e-4)
assert row["objective"] == pytest.approx(_objective_cost(project_dir, values))
assert row["objective"] < 0
```

Do not weaken assertions into broad shape checks. Keep exact path/status/timestamp
assertions and exact derived parameter/metric/objective assertions.

The final drift grep over `tests/test_real_result_record.py` must print no
matches for:

```text
create_project_from_template|bridge_test_inv|FN|WN|FP|WP|TEMPLATE_TEXT|rise|fall|DC
```

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/test_real_result_record.py",
```

Expected allowlist count: `10 -> 9`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 11 status, update the phase list, remove
`tests/test_real_result_record.py` from remaining waves, and add exact
verification results.

## Required Verification

Run these commands from repo root:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_cli.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_real_result_record.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_real_result_record\|tests.test_real_result_record" tests || true
git status --short
```

Expected results:

- target file: `21 passed`
- guard: `1 passed`
- target plus guard: `22 passed`
- CLI consumer group: `70 passed, 13 warnings`
- Phase 1-11 regression group: about `372 passed, 13 warnings`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_real_result_record.py`: no output
- cross-import grep: source-level matches only in `tests/test_cli.py`
- changed implementation/report files only:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/test_real_result_record.py
tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` needs a behavior change.
- Any test outside the three allowed files needs to change.
- `tests/test_cli.py` must be edited.
- The full suite fails outside this phase and the failure is not directly caused
  by these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_real_result_record.py`.
3. CLI consumer compatibility result.
4. Guard allowlist count `10 -> 9`.
5. Exact verification commands and pass/fail counts.
6. Drift grep result.
7. Cross-import grep result.
8. Release checkout status.
9. Confirmation that `graphify-out/` was untouched.
10. Remaining deferred allowlist files.

Claim only Phase 11 completion. Do not claim the broader template-coupling cleanup
is complete.
