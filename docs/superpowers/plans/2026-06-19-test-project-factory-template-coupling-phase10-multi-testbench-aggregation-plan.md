# Test Project Factory Template Coupling Phase 10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_multi_testbench_aggregation.py` from direct packaged-template project creation while preserving aggregation behavior and exported helper compatibility.

**Architecture:** This phase is a targeted migration of the single direct template call in `_create_ready_single_testbench_corner_project()`. The rest of the file's multi-testbench helpers still build requirement-driven projects and are used by backend/remote consumers, so they remain in place. The migrated single-testbench tests derive metric names and expected aggregate values from the generic factory's `config/metrics.yaml` instead of hardcoding inverter metric names.

**Tech Stack:** Python, pytest, PyYAML, `tests/project_factory.py`, `hermes_workflow.multi_testbench_aggregation`.

---

## File Structure

- Modify `tests/test_multi_testbench_aggregation.py`
  - Replace `create_project_from_template()` with `create_generic_project()` in the single-testbench corner helper.
  - Add small YAML readers for variable and metric names.
  - Update only the two single-testbench corner tests that depend on old `rise`/`fall`/`DC` names.
  - Leave multi-testbench fixture helpers and public helper names intact for consumers.

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_multi_testbench_aggregation.py` from `ALLOWED_TEMPLATE_CALLERS`.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 10 status and verification.
  - Remove `tests/test_multi_testbench_aggregation.py` from remaining waves.

## Task 0: Baseline Check

**Files:**
- Read: `tests/test_multi_testbench_aggregation.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm target file is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
12 passed, 13 warnings
```

- [ ] **Step 2: Confirm consumer group is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
95 passed, 13 warnings
```

- [ ] **Step 3: Confirm direct-template coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_multi_testbench_aggregation.py || true
```

Expected before edits: matches for the direct package import, `_create_ready_single_testbench_corner_project()`, old variable names, and the two single-testbench corner tests. The migration is complete only when this command prints no matches.

- [ ] **Step 4: Confirm known consumers**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_multi_testbench_aggregation\|tests.test_multi_testbench_aggregation" tests || true
```

Expected before edits: known source-level consumers in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`, plus the allowlist entry in `tests/test_template_coupling_guard.py`.

## Task 1: Replace Direct Template Creation

**Files:**
- Modify: `tests/test_multi_testbench_aggregation.py`
- Test: `tests/test_multi_testbench_aggregation.py`

- [ ] **Step 1: Update imports**

Change:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template, sha256_file
```

to:

```python
import yaml

from hermes_workflow.package import build_execution_package, sha256_file
from tests.project_factory import create_generic_project
```

Keep the existing `json`, `shutil`, `Path`, and pytest imports.

- [ ] **Step 2: Add YAML helper functions**

Add these helpers after `_write_json()`:

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

- [ ] **Step 3: Replace `_create_ready_single_testbench_corner_project()`**

Replace the full function with:

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

- [ ] **Step 4: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py -q
```

Expected at this point: the two single-testbench corner tests may still fail because they still expect old metric names and old objective values. Continue to Task 2 before treating those failures as blockers.

## Task 2: Migrate Single-Testbench Corner Expectations

**Files:**
- Modify: `tests/test_multi_testbench_aggregation.py`
- Test: `tests/test_multi_testbench_aggregation.py`

- [ ] **Step 1: Update the multi-corner single-testbench test**

In `test_aggregate_single_testbench_multi_corner_feasible_uses_worst_case_corner_metrics`, replace the old `rise` loop and old expected metric names with derived generic metrics:

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

Rationale: the generic factory objective is `<first_metric> - <second_metric>`, and `_write_corner_child_handoff()` gives W-unit non-target metrics the value `1.0e-4`. For maximize objectives, the worst-case corner is the lowest objective value.

- [ ] **Step 2: Update the explicit one-corner single-testbench test**

In `test_aggregate_single_testbench_explicit_one_corner_preserves_configured_semantics`, replace the old `rise` handoff and old objective assertion with:

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

- [ ] **Step 3: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
12 passed, 13 warnings
```

- [ ] **Step 4: Run drift grep for the target file**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_multi_testbench_aggregation.py || true
```

Expected: no output.

## Task 3: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove `tests/test_multi_testbench_aggregation.py` from the allowlist**

Remove this entry:

```python
"tests/test_multi_testbench_aggregation.py",
```

After the edit the allowlist should contain 10 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    # Product/template behavior.
    "tests/test_package.py",
    # Not yet migrated. Shrink this list in follow-up waves.
    "tests/real_run_smoke_helpers.py",
    "tests/test_mock_optimizer.py",
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
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
13 passed, 13 warnings
```

## Task 4: Verify Known Consumers

**Files:**
- Verify: `tests/test_openbox_backend.py`
- Verify: `tests/test_remote_spectre_ocean.py`
- Do not modify these files in this phase.

- [ ] **Step 1: Run the consumer group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
95 passed, 13 warnings
```

- [ ] **Step 2: Check cross-import output**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_multi_testbench_aggregation\|tests.test_multi_testbench_aggregation" tests || true
```

Expected: source-level matches only in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`. The guard entry should be gone.

If a consumer fails and the fix requires editing the consumer file, stop and report the dependency issue. Do not expand Phase 10.

## Task 5: Update the Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update the phase list in the header**

Change the phase summary ending from:

```markdown
8 (retention + progress state), and 9 (fix-run flow)
```

to:

```markdown
8 (retention + progress state), 9 (fix-run flow), and 10 (multi-testbench aggregation)
```

- [ ] **Step 2: Update the introduction paragraph**

Append this sentence to the paragraph that lists completed migrations:

```markdown
Phase 10 migrated the multi-testbench aggregation test module's remaining direct template setup.
```

- [ ] **Step 3: Add a Phase 10 status section before Phase 9**

Insert this section above `## Phase 9 status`, adjusting counts only if verified command output differs:

```markdown
## Phase 10 status

Migrated `tests/test_multi_testbench_aggregation.py` away from direct
`create_project_from_template()` usage. The file still owns helper functions used
by OpenBox and remote Spectre/OCEAN tests, but its single-testbench corner helper
now creates a generic project through `create_generic_project()` and derives
single-testbench metric expectations from `config/metrics.yaml`.

Coverage preserved: multi-testbench child manifest aggregation, inherited Spectre
settings, child command trace aggregation, metric and real failure propagation,
multi-corner objective/constraint policies, nominal policy behavior, and
single-testbench multi-corner aggregation semantics. Known consumers
(`tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`) remain
unchanged and are covered by the Phase 10 consumer regression command.

`tests/test_multi_testbench_aggregation.py` was removed from
`ALLOWED_TEMPLATE_CALLERS` (allowlist 11 -> 10).
```

- [ ] **Step 4: Update remaining migration waves**

Remove:

```markdown
- tests/test_multi_testbench_aggregation.py
```

The local packaging/state wave should now list only:

```markdown
- tests/real_run_smoke_helpers.py
```

- [ ] **Step 5: Add Phase 10 verification**

Add this verification block above Phase 9 verification, replacing counts only if real command output differs:

```markdown
### Phase 10

- `pytest tests/test_multi_testbench_aggregation.py -q` -> `12 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_multi_testbench_aggregation.py tests/test_template_coupling_guard.py -q` -> `13 passed, 13 warnings`
- `pytest tests/test_multi_testbench_aggregation.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q` -> `95 passed, 13 warnings`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py -q` -> `351 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|FN|WN|FP|WP|TEMPLATE_TEXT|rise|fall|DC` over `tests/test_multi_testbench_aggregation.py` -> no matches
- grep `from tests.test_multi_testbench_aggregation|tests.test_multi_testbench_aggregation` over `tests/` -> only known consumer matches in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`
- `ALLOWED_TEMPLATE_CALLERS` count: 11 -> 10.
```

## Task 6: Full Verification and Final Report

**Files:**
- Verify: target, consumers, regression group, full suite, release checkout

- [ ] **Step 1: Run Phase 1-10 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py -q
```

Expected:

```text
351 passed, 13 warnings
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
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_multi_testbench_aggregation.py || true
```

Expected: no output.

- [ ] **Step 7: Run final cross-import grep**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_multi_testbench_aggregation\|tests.test_multi_testbench_aggregation" tests || true
```

Expected: source-level matches only in `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`.

- [ ] **Step 8: Check git status**

Run:

```bash
git status --short
```

Expected changed files:

```text
 M docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
 M tests/test_multi_testbench_aggregation.py
 M tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 9: Write final report**

Include:

- Files modified.
- Migration summary for `tests/test_multi_testbench_aggregation.py`.
- Consumer compatibility result for `tests/test_openbox_backend.py` and `tests/test_remote_spectre_ocean.py`.
- Guard allowlist count `11 -> 10`.
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
- `tests/test_openbox_backend.py`, `tests/test_remote_spectre_ocean.py`, or `tests/real_run_smoke_helpers.py` must be edited.
- Full-suite failures appear outside the migrated file and cannot be tied directly to this phase.
