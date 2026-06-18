# Test Project Factory Template Coupling Phase 9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_fix_run_flow.py` from the packaged release template while preserving local fix-run orchestration coverage.

**Architecture:** This phase is a single-file test migration plus guard and inventory updates. The generic factory already knows how to create valid fix-run projects through `workflow_mode="fix_run"`, so the test should consume that factory output and read `fixed_points.yaml` for expected candidate ids and parameters. The phase deliberately excludes `real_run_smoke_helpers.py`, backend tests, remote tests, and multi-testbench aggregation because those form separate dependency clusters.

**Tech Stack:** Python, pytest, PyYAML, `tests/project_factory.py`, `hermes_workflow.fix_run_flow`.

---

## File Structure

- Modify `tests/test_fix_run_flow.py`
  - Replace `create_project_from_template()` with `create_generic_project(workflow_mode="fix_run")`.
  - Remove old inverter `TEMPLATE_TEXT` and `_write_template()`.
  - Derive expected fixed-point ids/parameters from `config/fixed_points.yaml`.
  - Keep local waveform/child-run helpers.

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_fix_run_flow.py` from `ALLOWED_TEMPLATE_CALLERS`.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 9 status and verification.
  - Remove `tests/test_fix_run_flow.py` from remaining waves.

## Task 0: Baseline Check

**Files:**
- Read: `tests/test_fix_run_flow.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm target file is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected:

```text
17 passed
```

- [ ] **Step 2: Confirm direct-template coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|fix_run_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_fix_run_flow.py || true
```

Expected before edits: matches for `create_project_from_template`, `TEMPLATE_TEXT`, `fix_run_test_inv`, and old variable names. The migration is complete only when this command prints no matches.

- [ ] **Step 3: Confirm no external tests import this module**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_fix_run_flow\|tests.test_fix_run_flow" tests || true
```

Expected before edits: only the allowlist entry in `tests/test_template_coupling_guard.py`.

## Task 1: Replace Fix-Run Project Creation

**Files:**
- Modify: `tests/test_fix_run_flow.py`
- Test: `tests/test_fix_run_flow.py`

- [ ] **Step 1: Replace imports**

Change:

```python
from hermes_workflow.package import create_project_from_template
```

to:

```python
from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Delete old template helpers**

Remove this old inverter template block:

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

- [ ] **Step 3: Add fixed-point readers**

Add these helpers near the existing helper section:

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

- [ ] **Step 4: Replace `_create_fix_run_project()`**

Replace the existing `_create_fix_run_project()` body with:

```python
def _create_fix_run_project(tmp_path: Path) -> Path:
    """Create a minimal project with fix_run mode configured."""
    return create_generic_project(
        tmp_path,
        name="fix_run_project",
        workflow_mode="fix_run",
    )
```

- [ ] **Step 5: Replace `_create_two_point_fix_run_project()`**

Replace the existing `_create_two_point_fix_run_project()` body with:

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

- [ ] **Step 6: Run target file after project-helper replacement**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected: failures may remain in assertions that still expect `user_point_001` or old parameter names. Continue to Task 2 before treating those failures as blockers.

## Task 2: Replace Old Fixed-Point Assertions

**Files:**
- Modify: `tests/test_fix_run_flow.py`
- Test: `tests/test_fix_run_flow.py`

- [ ] **Step 1: Update one-point candidate assertions**

In `test_fix_run_one_fixed_point_creates_one_candidate`, replace:

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

- [ ] **Step 2: Update returned report candidate assertion**

In `test_fix_run_returns_fix_run_report`, replace:

```python
assert report.points[0].candidate_id == "user_point_001"
```

with:

```python
assert report.points[0].candidate_id == _fixed_point_candidate_id(project_dir)
```

- [ ] **Step 3: Keep run-id assertions unchanged**

Do not change:

```python
assert report.points[0].run_id == "real_001"
assert mock_prepare.call_args_list[0].kwargs["run_id"] == "real_001"
assert mock_prepare.call_args_list[1].kwargs["run_id"] == "real_002"
```

These are testing fix-run run-id allocation, not template coupling.

- [ ] **Step 4: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected:

```text
17 passed
```

## Task 3: Clean Fix-Run-Specific Helper Wording

**Files:**
- Modify: `tests/test_fix_run_flow.py`
- Test: `tests/test_fix_run_flow.py`

- [ ] **Step 1: Adjust `_strip_optimizer_configs_for_fix_run()` wording without changing behavior**

The generic factory already removes `optimizer.yaml` for fix-run mode, but this helper still removes both optimizer and metrics configs and writes waveform exports for the parallelism tests. Keep the behavior, but update the docstring so it no longer implies the helper is compensating for the old template:

```python
def _strip_optimizer_configs_for_fix_run(project_dir: Path) -> None:
    """Use waveform exports only for child-parallelism tests.
    The parallelism tests need a valid fix-run project when parallel_jobs is set
    to 1, and waveform_exports.yaml gives the flow an explicit artifact contract
    without relying on optimizer metric checks.
    """
```

Do not rename the helper in this phase unless the implementation is already editing every call site in the same file.

- [ ] **Step 2: Run the target file again**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected:

```text
17 passed
```

- [ ] **Step 3: Run drift grep for the migrated file**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|fix_run_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_fix_run_flow.py || true
```

Expected: no output.

## Task 4: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove `tests/test_fix_run_flow.py` from the allowlist**

Remove this entry:

```python
"tests/test_fix_run_flow.py",
```

After the edit the allowlist should contain 11 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/real_run_smoke_helpers.py",
    "tests/test_mock_optimizer.py",
    "tests/test_multi_testbench_aggregation.py",
    "tests/test_native_turbo.py",
    "tests/test_openbox_backend.py",
    "tests/test_real_result_record.py",
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

- [ ] **Step 3: Run target plus guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
18 passed
```

## Task 5: Update the Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update the phase list in the header**

Change the phase summary ending from:

```markdown
7 (optimizer task package), and 8 (retention + progress state)
```

to:

```markdown
7 (optimizer task package), 8 (retention + progress state), and 9 (local fix-run flow)
```

- [ ] **Step 2: Update the introduction paragraph**

Append this sentence to the paragraph that lists completed migrations:

```markdown
Phase 9 migrated the local fix-run orchestration tests.
```

- [ ] **Step 3: Add a Phase 9 status section before Phase 8**

Insert this section above `## Phase 8 status`, adjusting counts only if verified command output differs:

```markdown
## Phase 9 status

Migrated `tests/test_fix_run_flow.py` away from direct
`create_project_from_template()` usage. The file now creates valid fix-run
projects through `create_generic_project(workflow_mode="fix_run")` and derives
expected fixed-point candidate ids and parameters from `config/fixed_points.yaml`
instead of hardcoding release-template variable names.

Coverage preserved: product-doctor gating, fixed-point candidate preparation,
run-id allocation, child adapter invocation, fix-run report writing, optimizer
state non-creation, report model shape, waveform artifact collection, fix-run
approval wiring, adapter failure gates, missing waveform CSV failure,
`cadence_cshrc` propagation, child parallelism, serial fallback, and child failure
preservation.

`tests/test_fix_run_flow.py` was removed from `ALLOWED_TEMPLATE_CALLERS`
(allowlist 12 -> 11). No external tests import from this module.
```

- [ ] **Step 4: Update remaining migration waves**

Remove:

```markdown
- tests/test_fix_run_flow.py
```

The local packaging/state wave should now list:

```markdown
- tests/test_multi_testbench_aggregation.py
- tests/real_run_smoke_helpers.py
```

- [ ] **Step 5: Add Phase 9 verification**

Add this verification block above Phase 8 verification, replacing counts only if real command output differs:

```markdown
### Phase 9

- `pytest tests/test_fix_run_flow.py -q` -> `17 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_fix_run_flow.py tests/test_template_coupling_guard.py -q` -> `18 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py -q` -> `339 passed`
- `pytest -q` -> `1194 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|fix_run_test_inv|FN|WN|FP|WP|TEMPLATE_TEXT|rise|fall|DC` over `tests/test_fix_run_flow.py` -> no matches
- grep `from tests.test_fix_run_flow|tests.test_fix_run_flow` over `tests/` -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 12 -> 11.
```

## Task 6: Full Verification and Final Report

**Files:**
- Verify: target, regression group, full suite, release checkout

- [ ] **Step 1: Run Phase 1-9 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py -q
```

Expected:

```text
339 passed
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

- [ ] **Step 6: Run final drift grep**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|fix_run_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_fix_run_flow.py || true
```

Expected: no output.

- [ ] **Step 7: Run final cross-import grep**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_fix_run_flow\|tests.test_fix_run_flow" tests || true
```

Expected: no output.

- [ ] **Step 8: Check git status**

Run:

```bash
git status --short
```

Expected changed files:

```text
 M docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
 M tests/test_fix_run_flow.py
 M tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 9: Write final report**

Include:

- Files modified.
- Migration summary for `tests/test_fix_run_flow.py`.
- Guard allowlist count `12 -> 11`.
- Exact verification commands and pass/fail counts.
- Drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Deferred allowlist files:

```text
tests/test_package.py
tests/real_run_smoke_helpers.py
tests/test_mock_optimizer.py
tests/test_multi_testbench_aggregation.py
tests/test_native_turbo.py
tests/test_openbox_backend.py
tests/test_real_result_record.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

Do not commit, tag, push, or publish.

## Stop Conditions

Stop and report before making changes outside the allowed scope if any of these happens:

- Production code under `src/` appears necessary.
- `tests/project_factory.py` needs a behavior change.
- A test outside the three allowed files must be modified.
- `tests/real_run_smoke_helpers.py`, backend tests, remote tests, adapter tests, or multi-testbench aggregation tests become part of the fix.
- Full-suite failures appear outside the migrated file and cannot be tied directly to this phase.
