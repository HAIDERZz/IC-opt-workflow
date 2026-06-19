# R4 Remote Optimizer Flow Template-Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove packaged-template coupling from `tests/test_remote_optimizer_flow.py` while preserving remote optimizer orchestration and continuation coverage.

**Architecture:** Replace the few full-project setup points with a local generic optimize project helper built on `tests.project_factory.create_generic_project`. Keep continuation-only cache fixtures minimal when they intentionally exercise mocked continuation behavior. Replace text-based config edits with structured YAML mutation.

**Tech Stack:** Python tests, pytest, YAML config mutation, `tests.project_factory.create_generic_project`, remote optimizer flow mocks.

---

## File Map

- Modify `tests/test_remote_optimizer_flow.py`
  - Import `yaml` and `create_generic_project`.
  - Remove `create_project_from_template`.
  - Add structured config helpers.
  - Replace project-backed setup in first-run, retention, and audit tests.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_remote_optimizer_flow.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R4 status and remove remote optimizer flow from remaining waves.

## Task 1: Baseline and Scope Check

**Files:**
- Verify: `tests/test_remote_optimizer_flow.py`
- Verify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Run target baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

Expected:

```text
21 passed, 13 warnings
```

- [ ] **Step 2: Run target plus guard baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
22 passed, 13 warnings
```

- [ ] **Step 3: Confirm no source consumers**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_optimizer_flow\|tests.test_remote_optimizer_flow" tests || true
```

Expected before guard update:

```text
tests/test_template_coupling_guard.py:10:    "tests/test_remote_optimizer_flow.py",
```

- [ ] **Step 4: Capture direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected before R4:

```text
tests/test_package.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 2: Add Generic Project and YAML Helpers

**Files:**
- Modify: `tests/test_remote_optimizer_flow.py`

- [ ] **Step 1: Replace imports**

Remove:

```python
from hermes_workflow.package import create_project_from_template
```

Add:

```python
import yaml

from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add YAML helpers near the top of the file**

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 3: Add a generic remote optimizer project helper**

```python
def _create_remote_optimizer_project(
    tmp_path: Path,
    *,
    name: str = "remote_optimizer_project",
    batch_size: int = 2,
    parallel_jobs: int = 2,
    max_evaluations: int = 12,
) -> Path:
    return create_generic_project(
        tmp_path,
        name=name,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        max_evaluations=max_evaluations,
    )
```

Use explicit names per test when the path is asserted or helpful for debugging:

```text
remote_optimizer_turbo
remote_optimizer_config_turbo
remote_optimizer_retention
remote_optimizer_audit
```

- [ ] **Step 4: Replace `_set_optimizer_strategy` with structured YAML**

```python
def _set_optimizer_strategy(project_dir: Path, strategy: str, algorithm: str) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    optimizer = payload.setdefault("optimizer", {})
    assert isinstance(optimizer, dict)
    optimizer["algorithm"] = algorithm
    optimizer["strategy"] = strategy
    _write_yaml(optimizer_path, payload)
```

- [ ] **Step 5: Replace `_set_keep_flags_for_retention_remote` with structured YAML**

```python
def _set_keep_flags_for_retention_remote(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(spectre_path)
    spectre = payload.setdefault("spectre", {})
    assert isinstance(spectre, dict)
    spectre["keep_failed_runs"] = keep_failed_runs
    spectre["keep_successful_runs"] = keep_successful_runs
    _write_yaml(spectre_path, payload)
```

## Task 3: Replace Full-Project Template Setup

**Files:**
- Modify: `tests/test_remote_optimizer_flow.py`

- [ ] **Step 1: Replace first-run native TuRBO project setup**

In `test_optimize_remote_project_routes_turbo_strategy_through_remote_adapter`, replace:

```python
create_project_from_template(cache_dir)
```

with a helper-created project. Preserve `cache_dir` identity if the test asserts exact path. If the helper returns a path, assign `cache_dir` from it:

```python
cache_dir = _create_remote_optimizer_project(
    tmp_path,
    name="remote_optimizer_turbo",
    batch_size=1,
    parallel_jobs=1,
    max_evaluations=2,
)
```

Update assertions only where they compare to the new path. Do not weaken remote adapter argument assertions.

- [ ] **Step 2: Replace config-driven turbo setup**

In `test_optimize_remote_project_allows_config_turbo_strategy_before_local_execution`, replace template setup with:

```python
cache_dir = _create_remote_optimizer_project(
    tmp_path / "cache",
    name="project",
    batch_size=1,
    parallel_jobs=1,
    max_evaluations=2,
)
_set_optimizer_strategy(cache_dir, "turbo_trust_region", "turbo")
```

Keep the assertion that `kwargs["strategy"] is None`; this test verifies config-driven strategy routing.

- [ ] **Step 3: Replace retention project setup**

For each remote retention test, replace:

```python
cache_dir = tmp_path / "cache" / "project"
create_project_from_template(cache_dir)
_set_keep_flags_for_retention_remote(...)
```

with:

```python
cache_dir = _create_remote_optimizer_project(
    tmp_path / "cache",
    name="project",
    batch_size=1,
    parallel_jobs=1,
    max_evaluations=2,
)
_set_keep_flags_for_retention_remote(...)
```

Affected tests:

- `test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_successful_runs_false_single_tb`
- `test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_successful_runs_false_multi_tb`
- `test_remote_adapter_wrapper_keeps_remote_run_dir_when_keep_successful_runs_true`
- `test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_failed_runs_false_on_failure`
- `test_remote_adapter_wrapper_remote_command_has_no_glob_and_is_under_remote_project_dir`

Preserve all command safety and `state/run_retention/*.json` assertions.

- [ ] **Step 4: Replace audit project setup**

In `test_remote_optimizer_audit_records_remote_transport_mode`, replace template setup with:

```python
cache_dir = _create_remote_optimizer_project(
    tmp_path,
    name="remote_optimizer_audit",
    batch_size=1,
    parallel_jobs=1,
    max_evaluations=2,
)
_set_optimizer_strategy(cache_dir, "turbo_trust_region", "turbo")
```

Preserve exact audit assertions:

- `execution_mode == "local"`
- `process_scope == "local_optimizer_process"`
- `transport_mode == "remote"`
- `requested_threads == 32`

- [ ] **Step 5: Leave continuation-only minimal cache tests alone unless needed**

Do not force these tests to use the generic factory if their current minimal cache is enough:

- `test_continue_remote_project_does_not_call_first_run_optimize_project`
- `test_continue_remote_project_calls_openbox_with_continuation_params`
- `test_continue_remote_project_fails_when_no_optimizer_history`
- `test_continue_remote_project_ensures_manifest_when_missing`
- `test_continue_remote_project_resource_inheritance_no_explicit_override`
- `test_continue_remote_project_writes_flow_report`
- `test_continue_remote_project_syncs_history_and_runs_additional_evals`
- `test_continue_remote_project_does_not_pass_strategy_detail_overrides`

These tests intentionally exercise continuation control flow with mocked validation and minimal synced history.

- [ ] **Step 6: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_optimizer_flow.py || true
```

Expected:

```text
```

## Task 4: Target Verification and Assertion Cleanup

**Files:**
- Modify: `tests/test_remote_optimizer_flow.py`

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

Expected:

```text
21 passed, 13 warnings
```

- [ ] **Step 2: If path assertions fail**

Preserve exact-path assertions by using helper return values consistently. Do not broaden to substring or truthiness checks unless the old assertion was already broad.

- [ ] **Step 3: If validation fails**

Check whether the affected test truly needs a full generic project or intentionally uses a minimal cache with mocked `assert_valid_project`. Do not edit production code.

- [ ] **Step 4: If retention assertions fail**

Confirm `spectre.keep_failed_runs` and `spectre.keep_successful_runs` are written under the `spectre` mapping in `config/spectre.yaml`.

## Task 5: Guard and Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove remote optimizer flow from allowlist**

Remove:

```python
"tests/test_remote_optimizer_flow.py",
```

Expected allowlist count:

```text
4 -> 3
```

- [ ] **Step 2: Update remaining waves**

In the inventory report, remove `tests/test_remote_optimizer_flow.py` from remaining remote/adapter flows.

Remaining direct template migration files after R4 should be:

```text
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

`tests/test_package.py` remains intentional template behavior.

- [ ] **Step 3: Add R4 verification section**

Add:

```markdown
### R4 Remote Optimizer Flow

- `pytest tests/test_remote_optimizer_flow.py -q` -> `21 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q` -> `22 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep forbidden tokens over `tests/test_remote_optimizer_flow.py` -> no matches
- grep cross-imports -> no source-level matches
- direct template caller list -> package, remote Spectre/OCEAN, local Spectre/OCEAN, guard
- `ALLOWED_TEMPLATE_CALLERS` count: 4 -> 3.
```

## Task 6: Full Verification

**Files:**
- Verify: target, guard, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

Expected:

```text
21 passed, 13 warnings
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
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
22 passed, 13 warnings
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
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_optimizer_flow.py || true
```

Expected: no output.

- [ ] **Step 9: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_optimizer_flow\|tests.test_remote_optimizer_flow" tests || true
```

Expected: no output.

- [ ] **Step 10: Run direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 7: Final Report

Report:

1. Files modified.
2. Remote optimizer flow migration summary.
3. Guard allowlist count `4 -> 3`.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
