# Claude Prompt: Phase 10 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 10 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-phase10-multi-testbench-aggregation-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-phase10-multi-testbench-aggregation-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_project_factory.py
tests/test_multi_testbench_aggregation.py
tests/test_template_coupling_guard.py
tests/test_openbox_backend.py
tests/test_remote_spectre_ocean.py
src/hermes_workflow/multi_testbench_aggregation.py
```

If codegraph and graphify are available, use them for orientation only. Source files and tests are authoritative. Do not use graph output as a reason to widen scope.

## Objective

Migrate:

```text
tests/test_multi_testbench_aggregation.py
```

away from direct `create_project_from_template()` usage. The direct coupling is in `_create_ready_single_testbench_corner_project()`. Keep the multi-testbench requirement helpers intact because they are requirement-driven and used by OpenBox/remote consumer tests.

## Strict Scope

Allowed to modify only:

```text
tests/test_multi_testbench_aggregation.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_project_factory.py
tests/test_openbox_backend.py
tests/test_remote_spectre_ocean.py
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

### tests/test_multi_testbench_aggregation.py

Replace:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template, sha256_file
```

with:

```python
import yaml

from hermes_workflow.package import build_execution_package, sha256_file
from tests.project_factory import create_generic_project
```

Add after `_write_json()`:

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    variables = payload["variables"]
    assert isinstance(variables, list)
    names: list[str] = []
    for entry in variables:
        assert isinstance(entry, dict)
        name = entry["name"]
        assert isinstance(name, str)
        names.append(name)
    return tuple(names)


def _metric_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    metrics = payload["metrics"]
    assert isinstance(metrics, list)
    names: list[str] = []
    for entry in metrics:
        assert isinstance(entry, dict)
        name = entry["name"]
        assert isinstance(name, str)
        names.append(name)
    assert len(names) == 2
    return tuple(names)
```

Replace `_create_ready_single_testbench_corner_project()` with:

```python
def _create_ready_single_testbench_corner_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name="single_testbench_corner_project",
    )
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_text = (project_dir / "netlists" / "templates" / "template.scs").read_text(
        encoding="utf-8"
    )
    for corner_id in corner_ids:
        corner_template = (
            project_dir / "netlists" / "corners" / corner_id / "template.scs"
        )
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-13T00:20:00Z")
    return project_dir
```

In `test_aggregate_single_testbench_multi_corner_feasible_uses_worst_case_corner_metrics`, replace old hardcoded `rise`/`fall`/`DC` expectations with:

```python
    objective_metric, non_target_metric = _metric_names(project_dir)
    objective_values = {"tt": 10.0, "ff": 4.0, "ss": 8.0}

    for corner_id, value in objective_values.items():
        _write_corner_child_handoff(
            project_dir,
            testbench_id=None,
            corner_id=corner_id,
            metric_name=objective_metric,
            value=value,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "succeeded"
    assert report.constraint_policy == "all_corners"
    assert report.objective_policy == "worst_case"
    assert report.selected_corner == "ff"
    assert report.worst_corner == "ff"
    assert report.corner_objectives == pytest.approx(
        {"tt": 10.0 - 1.0e-4, "ff": 4.0 - 1.0e-4, "ss": 8.0 - 1.0e-4}
    )
    assert report.corner_status_counts == {"feasible": 3}
    aggregate_metrics = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    assert {
        metric["name"]: metric["value"]
        for metric in aggregate_metrics["metrics"]
    } == {
        objective_metric: 4.0,
        non_target_metric: 1.0e-4,
    }
```

In `test_aggregate_single_testbench_explicit_one_corner_preserves_configured_semantics`, replace old hardcoded metric setup and objective assertion with:

```python
    objective_metric, _non_target_metric = _metric_names(project_dir)

    _write_corner_child_handoff(
        project_dir,
        testbench_id=None,
        corner_id="ss",
        metric_name=objective_metric,
        value=7.0,
    )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "succeeded"
    assert report.constraint_policy == "all_corners"
    assert report.objective_policy == "worst_case"
    assert report.selected_corner == "ss"
    assert report.worst_corner == "ss"
    assert report.corner_objectives == pytest.approx({"ss": 7.0 - 1.0e-4})
    assert report.corner_status_counts == {"feasible": 1}
    assert [(child.testbench, child.corner) for child in report.child_statuses] == [
        ("default_testbench", "ss")
    ]
```

Do not remove `MAX_GAIN`, `IIP3`, `cg_nf`, or `iip3` assertions. Those belong to the multi-testbench requirement fixture.

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/test_multi_testbench_aggregation.py",
```

Expected allowlist count: `11 -> 10`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 10 status, update the phase list, remove `tests/test_multi_testbench_aggregation.py` from remaining waves, and add exact verification results.

## Required Verification

Run these commands from repo root:

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
git status --short
```

Expected results:

- target file: `12 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `13 passed, 13 warnings`
- consumer group: `95 passed, 13 warnings`
- Phase 1-10 regression group: about `351 passed, 13 warnings`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_multi_testbench_aggregation.py`: no output
- cross-import grep: known consumers only in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`
- changed files only:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/test_multi_testbench_aggregation.py
tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` needs a behavior change.
- Any test outside the three allowed files needs to change.
- `tests/test_openbox_backend.py`, `tests/test_remote_spectre_ocean.py`, or `tests/real_run_smoke_helpers.py` must be edited.
- The full suite fails outside this phase and the failure is not directly caused by these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_multi_testbench_aggregation.py`.
3. Consumer compatibility result for OpenBox and remote Spectre/OCEAN tests.
4. Guard allowlist count `11 -> 10`.
5. Exact verification commands and pass/fail counts.
6. Drift grep result.
7. Cross-import grep result.
8. Release checkout status.
9. Confirmation that `graphify-out/` was untouched.
10. Remaining deferred allowlist files.

Claim only Phase 10 completion. Do not claim the broader template-coupling cleanup is complete.
