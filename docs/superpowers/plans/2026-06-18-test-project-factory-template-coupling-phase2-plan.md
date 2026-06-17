# Test Project Factory Template Coupling Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `tests/test_result_handoff.py` and `tests/test_metric_results.py` away from packaged release-template fixtures and shrink the template-coupling guard allowlist.

**Architecture:** Phase 2 keeps production code unchanged. The two target test files should use the generic project factory from `tests/project_factory.py`, derive incidental metric names from generated request files, and preserve their existing handoff-contract coverage. The guard allowlist must shrink after each migrated file.

**Tech Stack:** Python 3.11, pytest, Ruff, existing `hermes_workflow` test helpers, `tests/project_factory.py`.

---

## Files

- Modify: `tests/test_template_coupling_guard.py`
  - Remove `tests/test_result_handoff.py`.
  - Remove `tests/test_metric_results.py`.

- Modify: `tests/test_result_handoff.py`
  - Replace template fixture setup with `create_approved_generic_project()`.
  - Remove inverter-specific `TEMPLATE_TEXT` and template overlay helpers.

- Modify: `tests/test_metric_results.py`
  - Replace template fixture setup with `create_approved_generic_project()`.
  - Replace hardcoded metric issue strings with request-derived metric names.
  - Replace incidental `"rise"` payload names with generic metric names where
    those names are not the behavior under test.

- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Record Phase 2 migration.
  - Move the two files out of deferred status.

## Task 1: Tighten The Coupling Guard First

**Files:**
- Modify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove the two Phase 2 files from the allowlist**

Change this section:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/real_run_smoke_helpers.py",
    "tests/test_approvals.py",
    "tests/test_dry_run.py",
    "tests/test_fix_run_flow.py",
    "tests/test_metric_results.py",
    "tests/test_mock_optimizer.py",
    "tests/test_multi_testbench_aggregation.py",
    "tests/test_native_turbo.py",
    "tests/test_netlists.py",
    "tests/test_next_real_run.py",
    "tests/test_openbox_backend.py",
    "tests/test_optimizer_progress_state.py",
    "tests/test_optimizer_task_package.py",
    "tests/test_real_result_record.py",
    "tests/test_real_run.py",
    "tests/test_real_run_recovery.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_result_handoff.py",
    "tests/test_run_retention.py",
    "tests/test_spectre_ocean_adapter.py",
}
```

to:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/real_run_smoke_helpers.py",
    "tests/test_approvals.py",
    "tests/test_dry_run.py",
    "tests/test_fix_run_flow.py",
    "tests/test_mock_optimizer.py",
    "tests/test_multi_testbench_aggregation.py",
    "tests/test_native_turbo.py",
    "tests/test_netlists.py",
    "tests/test_next_real_run.py",
    "tests/test_openbox_backend.py",
    "tests/test_optimizer_progress_state.py",
    "tests/test_optimizer_task_package.py",
    "tests/test_real_result_record.py",
    "tests/test_real_run.py",
    "tests/test_real_run_recovery.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_run_retention.py",
    "tests/test_spectre_ocean_adapter.py",
}
```

- [ ] **Step 2: Run the guard and verify it fails for exactly the two target files**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected: FAIL. The offenders should include:

```text
tests/test_metric_results.py
tests/test_result_handoff.py
```

If any additional offender appears, stop and inspect before editing further.

## Task 2: Migrate `tests/test_result_handoff.py`

**Files:**
- Modify: `tests/test_result_handoff.py`

- [ ] **Step 1: Replace imports**

Replace the template-specific imports:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from tests.report_helpers import write_pass_reports
```

with:

```python
from tests.project_factory import create_approved_generic_project
```

Keep existing imports for `prepare_real_run`, `check_real_run`, report models,
`json`, `Path`, `pytest`, and `ValidationError`.

- [ ] **Step 2: Remove the inverter template helpers**

Delete these helpers completely:

```python
TEMPLATE_TEXT = """
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""

def _create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    return project_dir

def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")

def _approve_project(project_dir: Path) -> None:
    build_execution_package(project_dir, created_at_utc="2026-06-01T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
```

- [ ] **Step 3: Replace `_prepare_real_run_project()`**

Change the helper to:

```python
def _prepare_real_run_project(tmp_path: Path):
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc="2026-06-01T00:00:00Z",
    )
    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:20:00Z",
    )
    return project_dir, package
```

- [ ] **Step 4: Run the target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_result_handoff.py -q
```

Expected: PASS.

- [ ] **Step 5: Confirm the file no longer references the template API**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_result_handoff.py || true
```

Expected: no output.

## Task 3: Migrate `tests/test_metric_results.py`

**Files:**
- Modify: `tests/test_metric_results.py`

- [ ] **Step 1: Replace imports**

Replace this package import block:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from tests.report_helpers import write_pass_reports
```

with:

```python
from hermes_workflow.package import sha256_file
from tests.project_factory import create_approved_generic_project
```

Keep the existing imports for `WaveformExportResult`,
`MetricExtractionRequest`, `WaveformExportRequestEntry`,
`check_metric_results`, `prepare_real_run`, report models, `json`, `math`,
`shutil`, `Path`, `pytest`, and `ValidationError`.

- [ ] **Step 2: Remove the inverter template constant**

Delete:

```python
TEMPLATE_TEXT = """
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""
```

- [ ] **Step 3: Replace `_create_ready_project()`**

Change the helper to:

```python
def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc="2026-06-02T00:00:00Z",
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir
```

- [ ] **Step 4: Add metric-name helper functions**

Add these helpers after `_load_json()`:

```python
def _metric_names(project_dir: Path) -> list[str]:
    request = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    return [metric["name"] for metric in request["metrics"]]


def _first_metric_name(project_dir: Path) -> str:
    return _metric_names(project_dir)[0]
```

- [ ] **Step 5: Update the persisted success assertion**

Replace:

```python
assert persisted["metrics"]["rise"]["status"] == "succeeded"
```

with:

```python
first_metric = _first_metric_name(project_dir)
assert persisted["metrics"][first_metric]["status"] == "succeeded"
```

- [ ] **Step 6: Convert parameterized expected issue strings to templates**

In `test_check_metric_results_rejects_invalid_metric_contract`, rename the
parameter from `expected_issue` to `expected_issue_template`.

Replace every expected issue string containing `metric rise` with the same string
using `{metric}`:

```python
"metric {metric} expression does not match request"
"metric {metric} expression hash does not match request"
"metric {metric} unit does not match request"
"metric {metric} result selector does not match request"
"metric {metric} expression source does not match request"
"metric {metric} did not succeed"
"metric {metric} value is not finite"
"metric {metric} value_text is not a finite scalar"
"metric {metric} value_text looks like a waveform object"
```

Then update the assertion body:

```python
first_metric = _first_metric_name(project_dir)
expected_issue = expected_issue_template.format(metric=first_metric)
assert report.status == MetricResultCheckStatus.FAIL
assert expected_issue in report.issues
```

- [ ] **Step 7: Update missing and duplicate metric tests**

In `test_check_metric_results_rejects_missing_metric`, replace:

```python
assert "requested metric is missing from metric results: rise" in report.issues
```

with:

```python
first_metric = _first_metric_name(project_dir)
assert f"requested metric is missing from metric results: {first_metric}" in (
    report.issues
)
```

In `test_check_metric_results_rejects_duplicate_metric`, replace:

```python
assert "duplicate metric in metric results: rise" in report.issues
```

with:

```python
first_metric = _first_metric_name(project_dir)
assert f"duplicate metric in metric results: {first_metric}" in report.issues
```

- [ ] **Step 8: Update malformed request shape test data**

In `test_check_metric_results_rejects_malformed_request_shape`, replace:

```python
lambda payload: payload.update({"metrics": {"rise": {}}}),
```

with:

```python
lambda payload: payload.update({"metrics": {"not_a_metric_list": {}}}),
```

The expected issue remains:

```python
"metric extraction request is invalid"
```

- [ ] **Step 9: Update request-drift and formula-hash expected strings**

In `test_check_metric_results_rejects_invalid_formula_hash_even_when_manifests_agree`,
derive the metric name before assertions:

```python
first_metric = _first_metric_name(project_dir)
assert f"metric {first_metric} request expression hash is invalid" in report.issues
assert f"metric {first_metric} expression hash is invalid" in report.issues
```

Replace the old hardcoded `rise` assertions.

- [ ] **Step 10: Update non-numeric value parameterization**

In `test_check_metric_results_rejects_non_numeric_json_metric_value`, rename
`expected_issue` to `expected_issue_template` and replace the expected strings:

```python
"metric {metric} value is not a JSON number"
"metric {metric} value is not a JSON number"
```

Then assert:

```python
first_metric = _first_metric_name(project_dir)
expected_issue = expected_issue_template.format(metric=first_metric)
assert report.status == MetricResultCheckStatus.FAIL
assert expected_issue in report.issues
```

- [ ] **Step 11: Update standalone model payload metric names**

For direct `MetricExtractionRequest` model tests, replace incidental metric names:

```python
"name": "rise",
```

with:

```python
"name": "metric_gain",
```

Do this in:

- `test_metric_extraction_request_with_empty_waveform_exports_is_valid`
- `test_metric_extraction_request_with_populated_waveform_exports_validates`

These tests are model-shape tests; the metric name itself is not the behavior
under test.

- [ ] **Step 12: Update waveform manifest incidental parameter names**

In `test_check_metric_results_validates_waveform_export_manifest_if_present`,
replace:

```python
"parameters": {"FN": "1e-6", "WN": "2e-6"},
```

with:

```python
"parameters": {"VAR_INT": "1", "VAR_WIDTH": "0.2u"},
```

- [ ] **Step 13: Run the metric target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_metric_results.py -q
```

Expected: PASS.

- [ ] **Step 14: Confirm the file no longer references the template API or inverter names**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_metric_results.py || true
```

Expected: no output.

Run:

```bash
grep -n "\"rise\"" tests/test_metric_results.py || true
```

Expected: no output.

## Task 4: Verify The Guard Now Passes

**Files:**
- Verify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Run the guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected: PASS.

- [ ] **Step 2: Run target files together**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: PASS.

## Task 5: Update The Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Add a Phase 2 status section after the Phase 1 status summary**

Add:

```markdown
## Phase 2 status

Migrated away from direct `create_project_from_template()` usage:

- tests/test_result_handoff.py — now uses `create_approved_generic_project()`;
  result handoff setup no longer overlays an `FN/WN/FP/WP` template.
- tests/test_metric_results.py — now uses `create_approved_generic_project()`;
  metric-name assertions derive expected names from
  `metric_extraction_request.json` instead of hardcoding `rise`.

Both files were removed from `ALLOWED_TEMPLATE_CALLERS`.
```

- [ ] **Step 2: Move the two files out of deferred status**

Remove these bullets from the deferred section:

```markdown
- tests/test_metric_results.py ...
- tests/test_result_handoff.py ...
```

Add them to the migrated section, preserving the reason why the migration is
now complete.

- [ ] **Step 3: Update the "Remaining migration waves" section**

Remove `tests/test_result_handoff.py` and `tests/test_metric_results.py` from
the next-wave list. Keep these still listed for later waves:

```markdown
- tests/test_next_real_run.py
- tests/test_real_run.py
- tests/test_real_run_recovery.py
```

## Task 6: Full Verification

**Files:**
- Verify changed tests and repository health.

- [ ] **Step 1: Run factory and guard tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Phase 2 target tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the broader safety suite**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full pytest**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Run Ruff**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected: `All checks passed!`

- [ ] **Step 6: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 7: Confirm release checkout is untouched**

Run:

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 8: Confirm no graph output was staged or edited**

Run:

```bash
git status --short
```

Expected: changed files are limited to:

```text
tests/test_result_handoff.py
tests/test_metric_results.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

`graphify-out/` may remain untracked from prior graph work, but it must not be
staged or modified as part of Phase 2.

## Self-Review Checklist

- [ ] The allowlist shrank by exactly two files.
- [ ] No production files changed.
- [ ] No release checkout files changed.
- [ ] `tests/test_result_handoff.py` no longer references template API or
      inverter variable names.
- [ ] `tests/test_metric_results.py` no longer references template API,
      inverter variable names, or hardcoded `"rise"`.
- [ ] Expected issue strings still verify the exact runtime messages.
- [ ] Full pytest passes.
- [ ] Ruff passes.
- [ ] `git diff --check` is clean.
