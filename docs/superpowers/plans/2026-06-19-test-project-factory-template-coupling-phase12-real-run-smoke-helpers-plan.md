# Test Project Factory Template Coupling Phase 12 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/real_run_smoke_helpers.py` from the packaged release
template while keeping its helper consumers green.

**Architecture:** The shared smoke helper should create an approved generic
project with `tests/project_factory.py`, then derive candidate and metric names
from generated runtime artifacts. Consumer tests may need small fixture changes
where fake advisors still provide old `FN/WN/FP/WP` suggestions; those changes
must use helper-provided generic suggestion builders instead of hardcoded circuit
names.

**Tech Stack:** Python, pytest, JSON fixtures, `tests/project_factory.py`,
`hermes_workflow.real_result_record`, OpenBox/native fake optimizer tests.

---

## File Structure

- Modify `tests/real_run_smoke_helpers.py`
  - Replace direct template creation with `create_approved_generic_project()`.
  - Add generic variable/metric/advisor helper functions.
  - Keep public helper names used by consumers.

- Modify only if required by failing tests:
  - `tests/test_local_real_run_smoke.py`
  - `tests/test_optimizer_acceptance.py`
  - `tests/test_optimizer_completion.py`
  - `tests/test_optimizer_finalize.py`
  - `tests/test_optimizer_status.py`
  - `tests/test_native_turbo.py`
  - `tests/test_openbox_backend.py`
  - `tests/test_remote_spectre_ocean.py`

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/real_run_smoke_helpers.py` from the allowlist.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 12 status and verification.

## Task 0: Baseline Check

**Files:**
- Read: `tests/real_run_smoke_helpers.py`
- Read: direct consumer files listed in the spec

- [ ] **Step 1: Confirm helper consumer group is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
166 passed, 13 warnings
```

- [ ] **Step 2: Confirm current helper coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|TEMPLATE_TEXT\|parameters FN" tests/real_run_smoke_helpers.py || true
```

Expected before edits: matches for the direct template API and old template text.

- [ ] **Step 3: Confirm known consumers**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.real_run_smoke_helpers\|tests.real_run_smoke_helpers" tests || true
```

Expected before edits: source-level consumers in local smoke, optimizer
acceptance/completion/finalize/status, native TuRBO, OpenBox, remote
Spectre/OCEAN, and the allowlist entry.

## Task 1: Migrate the Shared Helper

**Files:**
- Modify: `tests/real_run_smoke_helpers.py`
- Test: `tests/test_local_real_run_smoke.py`

- [ ] **Step 1: Update imports**

Remove:

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

- [ ] **Step 2: Delete old constants**

Delete:

```python
TEMPLATE_TEXT = ...
DEFAULT_VALUES = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
```

- [ ] **Step 3: Replace `create_approved_real_project()`**

Replace the function with:

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

- [ ] **Step 4: Add generic name/value helpers**

Add after `load_json()`:

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

- [ ] **Step 5: Update fake metric manifest defaults**

Change:

```python
metric_values = values or DEFAULT_VALUES
```

to:

```python
metric_values = values or default_metric_values(project_dir, run_id=run_id)
```

Keep request-derived unit/result/expression fields unchanged.

- [ ] **Step 6: Run local smoke tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py -q
```

Expected: local smoke tests should pass. If they fail because helper output is
invalid, fix the helper before touching consumers.

## Task 2: Adapt Consumer Fake Advisors Only Where Needed

**Files:**
- Modify only if tests fail:
  - `tests/test_optimizer_acceptance.py`
  - `tests/test_optimizer_completion.py`
  - `tests/test_optimizer_finalize.py`
  - `tests/test_optimizer_status.py`
  - `tests/test_native_turbo.py`
  - `tests/test_openbox_backend.py`
  - `tests/test_remote_spectre_ocean.py`

- [ ] **Step 1: Run helper consumer group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

Expected: likely failures where a fake advisor still emits old variables.

- [ ] **Step 2: Replace fake advisor batches that are tied to helper projects**

For a fake advisor class used with `create_approved_real_project(tmp_path)`, change
its constructor from fixed old suggestions:

```python
class FakeAdvisorForStatus:
    def __init__(self) -> None:
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "FP": 3, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "FP": 5, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "FP": 7, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "FP": 9, "WP": 2.2},
            ],
        ]
```

to project-derived suggestions:

```python
from tests.real_run_smoke_helpers import advisor_batches

class FakeAdvisorForStatus:
    def __init__(self, project_dir: Path) -> None:
        self._batches = advisor_batches(project_dir)
```

Then update the factory call:

```python
advisor_factory=lambda _space, _seed: FakeAdvisorForStatus(project_dir)
```

Apply the same pattern to other fake advisors that are used with
`create_approved_real_project()`. Do not change fake advisors for tests that
intentionally build their own old template project; those files remain
allowlisted for later phases.

- [ ] **Step 3: Replace helper-backed metric fixtures if needed**

If a helper-backed consumer expects old metric names from the helper project, use:

```python
from tests.real_run_smoke_helpers import default_metric_values, metric_names_for_run
```

or derive the names from the generated run request. Do not hardcode the generic
factory metric names in consumers.

- [ ] **Step 4: Re-run helper consumer group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
166 passed, 13 warnings
```

If failures require production changes or broad behavior rewrites, stop and
report.

## Task 3: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove helper module from allowlist**

Remove:

```python
"tests/real_run_smoke_helpers.py",
```

After the edit the allowlist should contain 8 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/test_mock_optimizer.py",
    "tests/test_native_turbo.py",
    "tests/test_openbox_backend.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_spectre_ocean_adapter.py",
}
```

- [ ] **Step 2: Run the guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run helper drift grep**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|TEMPLATE_TEXT\|parameters FN" tests/real_run_smoke_helpers.py || true
```

Expected: no output.

## Task 4: Update the Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update the phase list**

Change the phase summary ending to include Phase 12:

```markdown
10 (multi-testbench aggregation), 11 (real-result recording), and 12 (real-run smoke helpers)
```

- [ ] **Step 2: Add Phase 12 status before Phase 11**

Add:

```markdown
## Phase 12 status

Migrated `tests/real_run_smoke_helpers.py` away from direct
`create_project_from_template()` usage. The helper now creates approved generic
projects via `create_approved_generic_project()` and `prepare_real_run()`, derives
metric names from each run's `metric_extraction_request.json`, and exposes
generic advisor suggestion helpers for consumers that need project-specific fake
optimizer suggestions.

Consumer compatibility was verified across local smoke, optimizer
acceptance/completion/finalize/status, native TuRBO, OpenBox, and remote
Spectre/OCEAN tests. Any consumer edits in this phase were limited to replacing
helper-backed old fake advisor suggestions with helper-derived generic
suggestions; direct template usage in backend/remote test modules remains
deferred.

`tests/real_run_smoke_helpers.py` was removed from
`ALLOWED_TEMPLATE_CALLERS` (allowlist 9 -> 8).
```

- [ ] **Step 3: Remove helper from remaining waves**

Remove:

```markdown
- tests/real_run_smoke_helpers.py
```

- [ ] **Step 4: Add verification results**

Add a Phase 12 verification block with the exact command results from this run.

## Task 5: Full Verification and Final Report

**Files:**
- Verify: helper consumer group, guard, regression group, full suite, release checkout

- [ ] **Step 1: Run Phase 1-12 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

- [ ] **Step 2: Run full suite**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 3: Run ruff**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 5: Confirm release checkout stayed untouched**

Run:

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 6: Check git status**

Run:

```bash
git status --short
```

Expected changed files include the helper, guard, inventory, and only the
allowed consumers that genuinely needed fixture adaptation. Existing untracked
`graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 7: Write final report**

Include:

- Files modified.
- Helper migration summary.
- Consumer files modified and why.
- Guard allowlist count `9 -> 8`.
- Exact verification commands and pass/fail counts.
- Helper drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Remaining deferred allowlist files:

```text
tests/test_package.py
tests/test_mock_optimizer.py
tests/test_native_turbo.py
tests/test_openbox_backend.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

Do not commit, tag, push, or publish.

## Stop Conditions

Stop and report before making changes outside the allowed scope if any of these
happens:

- Production code under `src/` appears necessary.
- `tests/project_factory.py` needs a behavior change.
- A test outside the allowed consumer set must be edited.
- Direct backend/remote template migrations become necessary to make the helper
  migration pass.
- Full-suite failures appear outside the migrated helper/consumer surface and
  cannot be tied directly to this phase.
