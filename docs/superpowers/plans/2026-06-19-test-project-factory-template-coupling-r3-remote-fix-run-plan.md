# R3 Remote Fix-Run Template-Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove packaged-template coupling from `tests/test_remote_fix_run_flow.py` while preserving remote fix-run orchestration coverage.

**Architecture:** Replace repeated hand-written packaged-template setup with one generic fix-run project helper built on `create_generic_project(tmp_path, name="remote_fix_run_project", workflow_mode="fix_run", parallel_jobs=4)`. Tests derive fixed-point candidate IDs and parameters from `config/fixed_points.yaml`; waveform export tests add explicit waveform config through a local helper.

**Tech Stack:** Python tests, pytest, YAML config mutation, `tests.project_factory.create_generic_project`, existing remote fix-run flow mocks.

---

## File Map

- Modify `tests/test_remote_fix_run_flow.py`
  - Add generic fix-run project helpers.
  - Remove local `create_project_from_template` imports.
  - Replace repeated `workflow.yaml` / `fixed_points.yaml` / `template.scs` setup with helper calls.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_remote_fix_run_flow.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R3 status and remove remote fix-run from remaining waves.

## Task 1: Baseline and Scope Check

**Files:**
- Verify: `tests/test_remote_fix_run_flow.py`
- Verify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Run target baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected:

```text
11 passed, 13 warnings
```

- [ ] **Step 2: Run target plus guard baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
12 passed, 13 warnings
```

- [ ] **Step 3: Confirm no source consumers**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_fix_run_flow\|tests.test_remote_fix_run_flow" tests || true
```

Expected before guard update:

```text
tests/test_template_coupling_guard.py:10:    "tests/test_remote_fix_run_flow.py",
```

- [ ] **Step 4: Capture direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected before R3:

```text
tests/test_package.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 2: Add Generic Fix-Run Helpers

**Files:**
- Modify: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Add import**

Add near test imports:

```python
from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add YAML read/write helpers after `_set_remote_spectre_parallel_jobs`**

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 3: Replace `_set_remote_spectre_parallel_jobs` body**

Use the helpers:

```python
def _set_remote_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(spectre_path)
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    _write_yaml(spectre_path, payload)
```

- [ ] **Step 4: Add fixed-point helpers**

```python
def _fixed_points(project_dir: Path) -> list[dict]:
    payload = _read_yaml(project_dir / "config" / "fixed_points.yaml")
    points = payload["points"]
    assert isinstance(points, list)
    return points


def _fixed_point_candidate_id(project_dir: Path) -> str:
    return str(_fixed_points(project_dir)[0]["candidate_id"])


def _fixed_point_parameters(project_dir: Path) -> dict[str, str]:
    parameters = _fixed_points(project_dir)[0]["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}
```

- [ ] **Step 5: Add waveform config helper**

```python
def _write_remote_waveform_exports(project_dir: Path) -> None:
    _write_yaml(
        project_dir / "config" / "waveform_exports.yaml",
        {
            "schema_version": "1.0",
            "exports": [
                {
                    "name": "nf_pnoise",
                    "testbench": "cg_nf",
                    "expression": 'getData("NF" ?result "pnoise")',
                    "output_format": "csv",
                    "nil_policy": "fail",
                }
            ],
        },
    )
```

- [ ] **Step 6: Add project factory helper**

```python
def _create_remote_fix_run_project(
    tmp_path: Path,
    *,
    name: str,
    parallel_jobs: int = 4,
    waveform_exports: bool = False,
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name=name,
        workflow_mode="fix_run",
        parallel_jobs=parallel_jobs,
    )
    if waveform_exports:
        _write_remote_waveform_exports(project_dir)
    return project_dir
```

- [ ] **Step 7: Replace `_strip_optimizer_configs_for_remote_fix_run`**

Delete `_strip_optimizer_configs_for_remote_fix_run`. The generic factory already removes `optimizer.yaml` for `workflow_mode="fix_run"`. Waveform exports are handled by `_write_remote_waveform_exports` or `_create_remote_fix_run_project(tmp_path, name="remote_fix_run_parallel", waveform_exports=True)`.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected after helper-only edits may still fail because callers are not migrated. Continue to Task 3 before debugging failures.

## Task 3: Replace Repeated Packaged-Template Setup

**Files:**
- Modify: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Remove local imports from test bodies**

Remove every local line:

```python
from hermes_workflow.package import create_project_from_template
```

- [ ] **Step 2: Replace setup in upload/report/children/failure tests**

For these tests:

- `test_remote_fix_run_uploads_fixed_point_artifacts`
- `test_remote_fix_run_writes_report_json`
- `test_remote_fix_run_calls_remote_spectre_ocean_per_child`
- `test_remote_failure_manifest_preserves_waveform_export_issues`

Replace the repeated project/template/workflow/fixed_points block with:

```python
project_dir = _create_remote_fix_run_project(tmp_path, name="<test-specific-name>")
```

Use descriptive names:

```text
remote_fix_run_upload
remote_fix_run_report
remote_fix_run_children
remote_fix_run_fail
```

- [ ] **Step 3: Replace setup in waveform artifact report test**

In `test_remote_fix_run_report_collects_waveform_artifacts`, replace manual `config/workflow.yaml` and `config/fixed_points.yaml` JSON setup with:

```python
project_dir = _create_remote_fix_run_project(
    tmp_path,
    name="remote_fix_run_artifacts",
    waveform_exports=True,
)
```

Keep the run directory and adapter side effect logic unchanged.

- [ ] **Step 4: Replace setup in parallelism tests**

For:

- `test_remote_fix_run_uses_parallel_jobs_for_child_runs`
- `test_remote_fix_run_parallel_jobs_one_keeps_child_runs_serial`
- `test_remote_fix_run_parallel_child_failure_preserved_and_report_fails`

Use:

```python
project_dir = _create_remote_fix_run_project(
    tmp_path,
    name="<test-specific-name>",
    parallel_jobs=<1-or-2>,
    waveform_exports=True,
)
```

Use names:

```text
remote_fix_run_parallel
remote_fix_run_serial
remote_fix_run_failure
```

Remove calls to `_strip_optimizer_configs_for_remote_fix_run(project_dir)` and `_set_remote_spectre_parallel_jobs(project_dir, 2)` or `_set_remote_spectre_parallel_jobs(project_dir, 1)` from these tests because the helper now sets both the workflow mode and `parallel_jobs`.

- [ ] **Step 5: Remove old hardcoded fixed-point parameter dictionaries**

Replace any remaining:

```python
{"FN": "2", "WN": "0.3u"}
```

with:

```python
_fixed_point_parameters(project_dir)
```

If only candidate ID is needed, use:

```python
_fixed_point_candidate_id(project_dir)
```

- [ ] **Step 6: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_fix_run_flow.py || true
```

Expected:

```text
```

## Task 4: Target Verification and Assertion Cleanup

**Files:**
- Modify: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected:

```text
11 passed, 13 warnings
```

- [ ] **Step 2: If a test fails on candidate ID**

Use:

```python
_fixed_point_candidate_id(project_dir)
```

instead of `"user_point_001"` or `"fixed_001"`.

- [ ] **Step 3: If a test fails on parameters**

Use:

```python
_fixed_point_parameters(project_dir)
```

instead of literal parameter dictionaries.

- [ ] **Step 4: If a waveform gate test fails**

Confirm the project is created with:

```python
waveform_exports=True
```

and the adapter side effect writes one `waveform_export_manifest.json` and one CSV per successful child.

## Task 5: Guard and Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove remote fix-run from allowlist**

Remove:

```python
"tests/test_remote_fix_run_flow.py",
```

Expected allowlist count:

```text
5 -> 4
```

- [ ] **Step 2: Update remaining waves**

In the inventory report, remove `tests/test_remote_fix_run_flow.py` from remaining remote/adapter flows.

Remaining direct template migration files after R3 should be:

```text
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

`tests/test_package.py` remains intentional template behavior.

- [ ] **Step 3: Add R3 verification section**

Add:

```markdown
### R3 Remote Fix-Run

- `pytest tests/test_remote_fix_run_flow.py -q` -> `11 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_remote_fix_run_flow.py tests/test_template_coupling_guard.py -q` -> `12 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep forbidden tokens over `tests/test_remote_fix_run_flow.py` -> no matches
- grep cross-imports -> no source-level matches
- direct template caller list -> package, remote optimizer, remote Spectre/OCEAN, local Spectre/OCEAN, guard
- `ALLOWED_TEMPLATE_CALLERS` count: 5 -> 4.
```

## Task 6: Full Verification

**Files:**
- Verify: target, guard, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected:

```text
11 passed, 13 warnings
```

- [ ] **Step 2: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run target plus guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
12 passed, 13 warnings
```

- [ ] **Step 4: Run full suite**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 5: Run ruff**

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 6: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 7: Confirm release checkout untouched**

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 8: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_fix_run_flow.py || true
```

Expected: no output.

- [ ] **Step 9: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_fix_run_flow\|tests.test_remote_fix_run_flow" tests || true
```

Expected: no output.

- [ ] **Step 10: Run direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 7: Final Report

Report:

1. Files modified.
2. Remote fix-run migration summary.
3. Guard allowlist count `5 -> 4`.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
