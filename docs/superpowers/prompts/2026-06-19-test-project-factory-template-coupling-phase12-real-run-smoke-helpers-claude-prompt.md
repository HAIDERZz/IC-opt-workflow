# Claude Prompt: Phase 12 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 12 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-phase12-real-run-smoke-helpers-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-phase12-real-run-smoke-helpers-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/real_run_cluster_helpers.py
tests/real_run_smoke_helpers.py
tests/test_template_coupling_guard.py
tests/test_local_real_run_smoke.py
tests/test_optimizer_acceptance.py
tests/test_optimizer_completion.py
tests/test_optimizer_finalize.py
tests/test_optimizer_status.py
tests/test_native_turbo.py
tests/test_openbox_backend.py
tests/test_remote_spectre_ocean.py
src/hermes_workflow/openbox_backend.py
src/hermes_workflow/native_turbo.py
```

If codegraph and graphify are available, use them for orientation only. Source
files and tests are authoritative. Do not use graph output as a reason to widen
scope.

## Objective

Migrate:

```text
tests/real_run_smoke_helpers.py
```

away from direct `create_project_from_template()` usage while keeping all helper
consumers green. This is a helper-consumer cluster because several consumers use
fake advisors whose suggestions currently assume old template variable names.

## Strict Scope

Allowed to modify only:

```text
tests/real_run_smoke_helpers.py
tests/test_local_real_run_smoke.py
tests/test_optimizer_acceptance.py
tests/test_optimizer_completion.py
tests/test_optimizer_finalize.py
tests/test_optimizer_status.py
tests/test_native_turbo.py
tests/test_openbox_backend.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_project_factory.py
tests/test_package.py
tests/test_mock_optimizer.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_spectre_ocean_adapter.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

Do not commit, tag, push, or publish.

## Required Implementation

### tests/real_run_smoke_helpers.py

Remove direct template setup imports:

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
import yaml
from tests.project_factory import create_approved_generic_project
```

Delete `TEMPLATE_TEXT` and old `DEFAULT_VALUES`.

Replace `create_approved_real_project()` with:

```python
def create_approved_real_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        name="real_run_smoke_project",
        created_at_utc="2026-06-03T00:00:00Z",
        max_evaluations=12,
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir
```

Add these helpers after `load_json()`:

```python
def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    variables = payload["variables"]
    names = [variable["name"] for variable in variables]
    assert len(names) == 2
    return names[0], names[1]

def metric_names_for_run(project_dir: Path, run_id: str = "real_001") -> tuple[str, str]:
    request = load_json(
        project_dir / "runs" / "real" / run_id / "metric_extraction_request.json"
    )
    names = [metric["name"] for metric in request["metrics"]]
    assert len(names) == 2
    return names[0], names[1]

def default_metric_values(
    project_dir: Path,
    *,
    run_id: str = "real_001",
) -> dict[str, float]:
    objective_metric, constraint_metric = metric_names_for_run(project_dir, run_id)
    return {
        objective_metric: 10.0,
        constraint_metric: 1.0e-6,
    }

def advisor_suggestion(
    project_dir: Path,
    *,
    int_value: float,
    width_value: float,
) -> dict[str, float]:
    int_name, width_name = variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}

def advisor_batches(project_dir: Path) -> list[list[dict[str, float]]]:
    return [
        [
            advisor_suggestion(project_dir, int_value=2, width_value=0.2),
            advisor_suggestion(project_dir, int_value=4, width_value=0.4),
        ],
        [
            advisor_suggestion(project_dir, int_value=3, width_value=0.3),
            advisor_suggestion(project_dir, int_value=5, width_value=0.5),
        ],
    ]
```

Update `write_fake_metric_result_manifest()`:

```python
metric_values = values or default_metric_values(project_dir, run_id=run_id)
```

Keep request-derived unit/result/expression fields exactly as contract checks
expect.

### Consumer Adaptation

Run the helper consumer group after changing the helper. If fake advisor tests
fail because they still emit old variables, adapt those fake advisors inside the
allowed consumer files.

Use this pattern:

```python
from tests.real_run_smoke_helpers import advisor_batches

class FakeAdvisorForStatus:
    def __init__(self, project_dir: Path) -> None:
        self._batches = advisor_batches(project_dir)

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations
```

And update the factory call:

```python
advisor_factory=lambda _space, _seed: FakeAdvisorForStatus(project_dir)
```

Only do this for fake advisors used with `create_approved_real_project(tmp_path)`.
Do not migrate unrelated direct-template tests in backend/remote modules; those
files remain allowlisted for later phases.

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/real_run_smoke_helpers.py",
```

Expected allowlist count: `9 -> 8`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 12 status, update the phase list, remove
`tests/real_run_smoke_helpers.py` from remaining waves, and add exact
verification results.

## Required Verification

Run these commands from repo root:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|TEMPLATE_TEXT\|parameters FN" tests/real_run_smoke_helpers.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.real_run_smoke_helpers\|tests.real_run_smoke_helpers" tests || true
git status --short
```

Expected results:

- helper consumer group baseline before migration: `166 passed, 13 warnings`
- helper consumer group after migration: about `166 passed, 13 warnings`
- guard: `1 passed`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- helper drift grep: no output
- changed files only from the allowed scope
- existing untracked `graphify-out/` may still appear; do not stage or modify it

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` needs a behavior change.
- A test outside the allowed consumer set needs to change.
- Direct backend/remote template migrations become necessary to make the helper
  migration pass.
- The full suite fails outside this phase and the failure is not directly caused
  by these edits.

## Final Report Format

Return:

1. Files modified.
2. Helper migration summary.
3. Consumer files modified and why.
4. Guard allowlist count `9 -> 8`.
5. Exact verification commands and pass/fail counts.
6. Helper drift grep result.
7. Cross-import grep result.
8. Release checkout status.
9. Confirmation that `graphify-out/` was untouched.
10. Remaining deferred allowlist files.

Claim only Phase 12 completion. Do not claim the broader template-coupling cleanup
is complete.
