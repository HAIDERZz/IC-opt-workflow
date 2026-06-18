# Test Project Factory Template Coupling Phase 11 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_real_result_record.py` from the packaged release
template while preserving real-result ledger/state behavior and CLI helper
compatibility.

**Architecture:** This phase is a targeted migration of one test module. Project
setup moves to `create_approved_generic_project()` and `prepare_real_run()`.
Expected parameters and metrics are derived from generated runtime artifacts
instead of old template names. Existing CLI imports remain stable.

**Tech Stack:** Python, pytest, JSON fixtures, `tests/project_factory.py`,
`hermes_workflow.real_result_record`.

---

## File Structure

- Modify `tests/test_real_result_record.py`
  - Remove direct template project creation.
  - Add small helpers to read candidate parameters and metric names from the
    prepared run.
  - Convert old parameter/metric fixtures to derived generic values.
  - Preserve `_create_ready_project()` and `_write_valid_checked_result()` for
    `tests/test_cli.py`.

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_real_result_record.py` from `ALLOWED_TEMPLATE_CALLERS`.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 11 status and verification.
  - Remove `tests/test_real_result_record.py` from remaining waves.

## Task 0: Baseline Check

**Files:**
- Read: `tests/test_real_result_record.py`
- Read: `tests/test_cli.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm target file is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
```

Expected:

```text
21 passed
```

- [ ] **Step 2: Confirm CLI consumer group is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_cli.py -q
```

Expected:

```text
70 passed, 13 warnings
```

- [ ] **Step 3: Confirm direct-template coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_real_result_record.py || true
```

Expected before edits: matches for the direct package import, `TEMPLATE_TEXT`,
old project name, old parameter names, and old metric names. The migration is
complete only when this command prints no matches.

- [ ] **Step 4: Confirm known consumers**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_real_result_record\|tests.test_real_result_record" tests || true
```

Expected before edits: source-level imports only in `tests/test_cli.py`, plus the
allowlist entry in `tests/test_template_coupling_guard.py`.

## Task 1: Replace Project Setup

**Files:**
- Modify: `tests/test_real_result_record.py`
- Test: `tests/test_real_result_record.py`

- [ ] **Step 1: Update imports**

Remove imports that are only needed for direct template setup:

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

- [ ] **Step 2: Remove `TEMPLATE_TEXT`**

Delete the old Spectre template constant entirely. The generic factory already
writes `netlists/templates/template.scs`.

- [ ] **Step 3: Replace `_create_ready_project()`**

Replace the full function with:

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

Rationale: `create_approved_generic_project()` builds the execution package,
writes passing preflight reports with the correct generic variable names, and
creates a valid supervisor approval. The helper name remains stable for
`tests/test_cli.py`.

- [ ] **Step 4: Run the target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
```

Expected at this point: several assertions may still fail because they still
expect old parameter and metric names. Continue to Task 2 before treating those
failures as blockers.

## Task 2: Add Derived Runtime Helpers

**Files:**
- Modify: `tests/test_real_result_record.py`

- [ ] **Step 1: Add candidate parameter helper**

Add after `_load_json()`:

```python
def _candidate_parameters(project_dir: Path) -> dict[str, str]:
    payload = _load_json(
        project_dir / "runs" / "real" / "real_001" / "candidate.json"
    )
    parameters = payload["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}
```

- [ ] **Step 2: Add metric helper functions**

Add:

```python
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

Rationale: the generic factory objective is maximize
`<objective_metric> - <constraint_metric>`, so the recorded ledger cost is the
negative of that expression.

- [ ] **Step 3: Add ledger/best fixture helper if useful**

If repeated existing ledger/best payloads get noisy, add a local helper such as:

```python
def _row_payload(
    project_dir: Path,
    *,
    candidate_id: str,
    objective_value: float,
    constraint_value: float = 1.0e-4,
    objective_cost: float | None = None,
    constraints_passed: bool = True,
    simulation_status: str = "mock_pass",
    timestamp_utc: str = "2026-06-02T11:00:00Z",
) -> dict:
    values = _metric_values(
        project_dir,
        objective_value=objective_value,
        constraint_value=constraint_value,
    )
    return {
        "candidate_id": candidate_id,
        "parameters": _candidate_parameters(project_dir),
        "metrics": values,
        "constraints_passed": constraints_passed,
        "objective": (
            _objective_cost(project_dir, values)
            if objective_cost is None
            else objective_cost
        ),
        "batch_id": 1,
        "simulation_status": simulation_status,
        "timestamp_utc": timestamp_utc,
    }
```

This helper is optional. Use it only if it keeps assertions clearer.

## Task 3: Make Fake Metric Manifests Generic

**Files:**
- Modify: `tests/test_real_result_record.py`
- Test: `tests/test_real_result_record.py`

- [ ] **Step 1: Update `_write_metric_result_manifest()` defaults**

Change:

```python
metric_values = values or {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
```

to:

```python
metric_values = values or _metric_values(project_dir)
```

- [ ] **Step 2: Keep request metadata exact**

Do not simplify the fake metric manifest. Keep using `request_by_name[name]` for
unit, result, expression, expression hash, and expression source. That preserves
the metric-result contract checks.

- [ ] **Step 3: Convert explicit metric values**

Replace old explicit metric dictionaries with `_metric_values(...)`.

Examples:

```python
_write_metric_result_manifest(
    project_dir,
    values=_metric_values(project_dir, objective_value=1.0, constraint_value=1.0),
)
```

for constraint-failing cases.

Use a better feasible existing row than the real result by giving it a more
negative stored objective cost, for example `objective_value=2.0` and
`constraint_value=1.0e-4`.

Use a worse feasible existing row than the real result by giving it a less
favorable objective cost.

- [ ] **Step 4: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
```

Expected: remaining failures, if any, should now be assertion names/objective
normalization issues, not project setup or metric-manifest validation failures.

## Task 4: Migrate Assertions and Existing Ledger Fixtures

**Files:**
- Modify: `tests/test_real_result_record.py`
- Test: `tests/test_real_result_record.py`

- [ ] **Step 1: Update pure `LedgerRow` schema tests**

Replace old names with neutral names. Example:

```python
parameters={"PARAM_A": "2", "PARAM_B": "0.3u"}
metrics={"metric_a": 1.25, "metric_b": 1.0e-4}
```

Keep the provenance, mock payload, and invalid-status assertions unchanged.

- [ ] **Step 2: Update valid-record assertions**

In `test_record_real_result_writes_ledger_state_best_and_report`:

- Assert `row["parameters"] == _candidate_parameters(project_dir)`.
- Derive `metric_values = _metric_values(project_dir)`.
- Assert `row["metrics"] == pytest.approx(metric_values)` or assert each derived
  metric key with `pytest.approx`.
- Assert `row["objective"] == pytest.approx(_objective_cost(project_dir, metric_values))`.
- Assert `best["parameters"] == _candidate_parameters(project_dir)`.
- Assert `best["metrics"] == row["metrics"]`.
- Keep all path, status, timestamp, state, and report assertions.

- [ ] **Step 3: Update duplicate-candidate fixture**

The duplicate-candidate test can use a minimal neutral or derived payload, but it
must keep candidate_id `"real_001"` to exercise duplicate candidate detection.
Avoid old parameter and metric names.

- [ ] **Step 4: Update existing best and ledger rows**

For tests that write existing ledger rows or best candidates:

- Use `_candidate_parameters(project_dir)` or a neutral parameter dict based on
  those keys.
- Use `_metric_values(project_dir, ...)`.
- Use explicit objective costs that make the test intent clear:
  - Better feasible existing best: more negative than the new real result.
  - Worse feasible existing best: less favorable than the new real result.
  - Infeasible best: `constraints_passed=False`.
  - Stale best: mismatched candidate_id/objective to prove repair/replacement.

Do not preserve old numeric constants if they only made sense for the old
inverter objective. Preserve the behavioral relationship.

- [ ] **Step 5: Update maximize normalization test**

The generic factory already uses `direction: maximize`. Remove the old text
replacement that attempted to change `direction: minimize` to `maximize`.

Use:

```python
values = _metric_values(project_dir, objective_value=2.0, constraint_value=1.0e-4)
```

Then assert:

```python
assert row["objective"] == pytest.approx(_objective_cost(project_dir, values))
assert row["objective"] < 0
```

- [ ] **Step 6: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
```

Expected:

```text
21 passed
```

- [ ] **Step 7: Run drift grep**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_real_result_record.py || true
```

Expected: no output.

## Task 5: Preserve CLI Consumer Compatibility

**Files:**
- Verify: `tests/test_cli.py`
- Do not modify this file in Phase 11.

- [ ] **Step 1: Run CLI consumer group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_cli.py -q
```

Expected:

```text
70 passed, 13 warnings
```

- [ ] **Step 2: Check cross-import output**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_real_result_record\|tests.test_real_result_record" tests || true
```

Expected after guard update: source-level matches only in `tests/test_cli.py`.

If `tests/test_cli.py` fails and requires edits, stop and report. Do not expand
Phase 11.

## Task 6: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove `tests/test_real_result_record.py` from the allowlist**

Remove:

```python
"tests/test_real_result_record.py",
```

After the edit the allowlist should contain 9 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/real_run_smoke_helpers.py",
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

- [ ] **Step 3: Run target plus guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
22 passed
```

## Task 7: Update the Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update the phase list in the header**

Change the phase summary ending from:

```markdown
9 (fix-run flow), and 10 (multi-testbench aggregation)
```

to:

```markdown
9 (fix-run flow), 10 (multi-testbench aggregation), and 11 (real-result recording)
```

- [ ] **Step 2: Update the introduction paragraph**

Append this sentence to the paragraph that lists completed migrations:

```markdown
Phase 11 migrated the real-result recording tests.
```

- [ ] **Step 3: Add a Phase 11 status section before Phase 10**

Insert this section above `## Phase 10 status`, adjusting counts only if verified
command output differs:

```markdown
## Phase 11 status

Migrated `tests/test_real_result_record.py` away from direct
`create_project_from_template()` usage. The file now creates approved generic
projects via `create_approved_generic_project()` and `prepare_real_run()`, while
retaining `_create_ready_project()` and `_write_valid_checked_result()` for
`tests/test_cli.py` record-real-result coverage. Candidate parameters are derived
from `runs/real/real_001/candidate.json`; metric names and values are derived
from `runs/real/real_001/metric_extraction_request.json`.

Coverage preserved: real-result provenance schemas, prerequisite failure paths,
valid ledger/state/best/report writes, duplicate run/candidate detection,
invalid-ledger protection, constraint-failing real results, existing-best
preservation, best recovery from ledger, stale/invalid best repair, stale best
removal, and maximize objective normalization.

`tests/test_real_result_record.py` was removed from
`ALLOWED_TEMPLATE_CALLERS` (allowlist 10 -> 9). `tests/test_cli.py` remains a
consumer of the helper functions and is covered by the Phase 11 consumer
regression command.
```

- [ ] **Step 4: Update remaining migration waves**

Remove:

```markdown
- tests/test_real_result_record.py
```

from the remote and adapter flows list.

- [ ] **Step 5: Add Phase 11 verification**

Add this verification block above Phase 10 verification, replacing counts only
if real command output differs:

```markdown
### Phase 11

- `pytest tests/test_real_result_record.py -q` -> `21 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_real_result_record.py tests/test_template_coupling_guard.py -q` -> `22 passed`
- `pytest tests/test_real_result_record.py tests/test_cli.py -q` -> `70 passed, 13 warnings`
- `pytest [Phase 1-11 regression group, 21 files] -q` -> `372 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep forbidden tokens over `tests/test_real_result_record.py` -> no matches
- grep cross-imports -> source-level matches only in `tests/test_cli.py`
- `ALLOWED_TEMPLATE_CALLERS` count: 10 -> 9.
```

## Task 8: Full Verification and Final Report

**Files:**
- Verify: target, CLI consumer, regression group, full suite, release checkout

- [ ] **Step 1: Run Phase 1-11 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py -q
```

Expected:

```text
372 passed, 13 warnings
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
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_real_result_record.py || true
```

Expected: no output.

- [ ] **Step 7: Run final cross-import grep**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_real_result_record\|tests.test_real_result_record" tests || true
```

Expected: source-level matches only in `tests/test_cli.py`.

- [ ] **Step 8: Check git status**

Run:

```bash
git status --short
```

Expected changed files:

```text
 M docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
 M tests/test_real_result_record.py
 M tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 9: Write final report**

Include:

- Files modified.
- Migration summary for `tests/test_real_result_record.py`.
- CLI consumer compatibility result.
- Guard allowlist count `10 -> 9`.
- Exact verification commands and pass/fail counts.
- Drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Remaining deferred allowlist files:

```text
tests/test_package.py
tests/real_run_smoke_helpers.py
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
- A test outside the three allowed files must be modified.
- `tests/test_cli.py` must be edited.
- Full-suite failures appear outside the migrated file and cannot be tied
  directly to this phase.
