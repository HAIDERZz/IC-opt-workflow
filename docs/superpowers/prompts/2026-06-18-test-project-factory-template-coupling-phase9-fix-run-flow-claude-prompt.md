# Claude Prompt: Phase 9 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 9 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase9-fix-run-flow-spec.md
docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase9-fix-run-flow-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_project_factory.py
tests/test_fix_run_flow.py
tests/test_template_coupling_guard.py
src/hermes_workflow/fix_run_flow.py
src/hermes_workflow/fix_run_models.py
```

If codegraph and graphify are available, use them for orientation only. Source files and tests are authoritative. Do not use graph output as a reason to widen scope.

## Objective

Migrate:

```text
tests/test_fix_run_flow.py
```

away from direct `create_project_from_template()` usage. Use `tests.project_factory.create_generic_project(..., workflow_mode="fix_run")` and derive expected fixed-point candidate ids/parameters from `config/fixed_points.yaml`.

## Strict Scope

Allowed to modify only:

```text
tests/test_fix_run_flow.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_project_factory.py
tests/test_multi_testbench_aggregation.py
tests/real_run_smoke_helpers.py
tests/test_package.py
tests/test_cli.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

Do not commit, tag, push, or publish.

## Required Implementation

### tests/test_fix_run_flow.py

Replace:

```python
from hermes_workflow.package import create_project_from_template
```

with:

```python
from tests.project_factory import create_generic_project
```

Remove:

```python
TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")
```

Add:

```python
def _fixed_points(project_dir: Path) -> list[dict[str, object]]:
    payload = yaml.safe_load(
        (project_dir / "config" / "fixed_points.yaml").read_text(encoding="utf-8")
    )
    points = payload["points"]
    assert isinstance(points, list)
    return points


def _fixed_point_parameters(project_dir: Path, index: int = 0) -> dict[str, str]:
    parameters = _fixed_points(project_dir)[index]["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}


def _fixed_point_candidate_id(project_dir: Path, index: int = 0) -> str:
    candidate_id = _fixed_points(project_dir)[index]["candidate_id"]
    assert isinstance(candidate_id, str)
    return candidate_id
```

Replace `_create_fix_run_project()` with:

```python
def _create_fix_run_project(tmp_path: Path) -> Path:
    """Create a minimal project with fix_run mode configured."""
    return create_generic_project(
        tmp_path,
        name="fix_run_project",
        workflow_mode="fix_run",
    )
```

Replace `_create_two_point_fix_run_project()` with:

```python
def _create_two_point_fix_run_project(tmp_path: Path) -> Path:
    """Create a fix_run project with two fixed points."""
    project_dir = create_generic_project(
        tmp_path,
        name="fix_run_two_points",
        workflow_mode="fix_run",
    )
    first_point = _fixed_points(project_dir)[0]
    first_parameters = _fixed_point_parameters(project_dir)
    parameter_names = list(first_parameters)
    assert len(parameter_names) == 2
    second_parameters = {
        parameter_names[0]: "4",
        parameter_names[1]: "0.4u",
    }
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    first_point,
                    {
                        "candidate_id": "fixed_002",
                        "parameters": second_parameters,
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return project_dir
```

Replace hardcoded fixed-point assertions:

```python
assert call_kwargs.kwargs["candidate_id"] == "user_point_001"
assert call_kwargs.kwargs["parameters"] == {
    "FN": "2",
    "WN": "0.3u",
    "FP": "2",
    "WP": "0.3u",
}
```

with:

```python
assert call_kwargs.kwargs["candidate_id"] == _fixed_point_candidate_id(project_dir)
assert call_kwargs.kwargs["parameters"] == _fixed_point_parameters(project_dir)
```

Replace:

```python
assert report.points[0].candidate_id == "user_point_001"
```

with:

```python
assert report.points[0].candidate_id == _fixed_point_candidate_id(project_dir)
```

Keep `cg_nf`, `tt`, `ss`, `ff`, `nf_pnoise`, and waveform path names where they test child-run or waveform-export behavior.

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/test_fix_run_flow.py",
```

Expected allowlist count: `12 -> 11`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 9 status, update the phase list, remove `tests/test_fix_run_flow.py` from remaining waves, and add exact verification results.

## Required Verification

Run these commands from repo root:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|fix_run_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_fix_run_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_fix_run_flow\|tests.test_fix_run_flow" tests || true
git status --short
```

Expected results:

- target file: `17 passed`
- guard: `1 passed`
- target plus guard: `18 passed`
- Phase 1-9 regression group: about `339 passed`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_fix_run_flow.py`: no output
- cross-import grep: no source-level matches
- changed files only:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/test_fix_run_flow.py
tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` needs another behavior change.
- Any test outside the three allowed files needs to change.
- `tests/real_run_smoke_helpers.py`, backend tests, remote tests, adapter tests, or multi-testbench aggregation tests become involved.
- The full suite fails outside this phase and the failure is not directly caused by these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_fix_run_flow.py`.
3. Guard allowlist count `12 -> 11`.
4. Exact verification commands and pass/fail counts.
5. Drift grep result.
6. Cross-import grep result.
7. Release checkout status.
8. Confirmation that `graphify-out/` was untouched.
9. Remaining deferred allowlist files.

Claim only Phase 9 completion. Do not claim the broader template-coupling cleanup is complete.
