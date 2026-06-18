# Test Project Factory Template Coupling Phase 8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_run_retention.py` and `tests/test_optimizer_progress_state.py` from the packaged release template while preserving their local state/report behavior coverage.

**Architecture:** This phase stays entirely in tests. Both target files should use the generic test project factory as their source of valid project structure, then derive incidental config names from generated YAML rather than hardcoding old release-template variables, metrics, or project names. The coupling guard is the enforcement point: remove both migrated files from the allowlist after their direct template calls are gone.

**Tech Stack:** Python, pytest, PyYAML, `tests/project_factory.py`, `hermes_workflow.run_retention`, `hermes_workflow.optimizer_progress_state`.

---

## File Structure

- Modify `tests/test_run_retention.py`
  - Replace `create_project_from_template()` setup with `create_generic_project()`.
  - Replace string replacement in `_set_keep_flags()` with structured YAML mutation.
  - Keep all retention decision/report assertions in the same file.

- Modify `tests/test_optimizer_progress_state.py`
  - Replace `create_project_from_template()` setup with `create_generic_project()`.
  - Remove `_set_optimizer_max_evaluations()`.
  - Add local helpers that read variable and metric names from generated YAML.
  - Replace old project/variable/metric literals with neutral constants or derived names.

- Modify `tests/test_template_coupling_guard.py`
  - Remove the two migrated files from `ALLOWED_TEMPLATE_CALLERS`.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 8 status and verification.
  - Move the two files out of the remaining wave list.

## Task 0: Baseline Check

**Files:**
- Read: `tests/test_run_retention.py`
- Read: `tests/test_optimizer_progress_state.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm target tests are green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
```

Expected:

```text
28 passed
```

- [ ] **Step 2: Confirm current direct-template coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_run_retention.py tests/test_optimizer_progress_state.py || true
```

Expected before edits: matches in both target files. The migration is complete only when this command prints no matches for the two files.

- [ ] **Step 3: Confirm no external test imports depend on these modules**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_run_retention\|tests.test_run_retention\|from tests.test_optimizer_progress_state\|tests.test_optimizer_progress_state" tests || true
```

Expected before edits: only allowlist references in `tests/test_template_coupling_guard.py`.

## Task 1: Migrate Run Retention Project Setup

**Files:**
- Modify: `tests/test_run_retention.py`
- Test: `tests/test_run_retention.py`

- [ ] **Step 1: Replace imports**

Change the top of `tests/test_run_retention.py` from:

```python
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from hermes_workflow.package import create_project_from_template
```

to:

```python
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
import yaml

from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add a small project factory wrapper**

Add this helper near the existing helpers:

```python
def _create_retention_project(tmp_path: Path) -> Path:
    return create_generic_project(tmp_path, name="retention_project")
```

- [ ] **Step 3: Replace `_set_keep_flags()` with structured YAML mutation**

Replace the existing `_set_keep_flags()` implementation with:

```python
def _set_keep_flags(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    """Edit config/spectre.yaml to set the two retention flags."""
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    spectre = payload.setdefault("spectre", {})
    spectre["keep_failed_runs"] = keep_failed_runs
    spectre["keep_successful_runs"] = keep_successful_runs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 4: Replace project creation call sites**

Replace each pair:

```python
project_dir = tmp_path / "project"
create_project_from_template(project_dir)
```

with:

```python
project_dir = _create_retention_project(tmp_path)
```

Do not change assertions unless they explicitly depend on a removed old template name. `tests/test_run_retention.py` currently uses neutral run ids and remote paths, so assertion changes should not be needed.

- [ ] **Step 5: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py -q
```

Expected:

```text
21 passed
```

- [ ] **Step 6: Check run-retention drift**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_run_retention.py || true
```

Expected: no output.

## Task 2: Migrate Optimizer Progress State Helpers

**Files:**
- Modify: `tests/test_optimizer_progress_state.py`
- Test: `tests/test_optimizer_progress_state.py`

- [ ] **Step 1: Replace imports and add constants**

Change the imports from:

```python
import json
from pathlib import Path

from hermes_workflow.optimizer_progress_state import (
    build_optimizer_progress_state,
    sync_optimizer_progress_state,
)
from hermes_workflow.package import create_project_from_template
from tests.report_helpers import write_json
```

to:

```python
import json
from pathlib import Path

import yaml

from hermes_workflow.optimizer_progress_state import (
    build_optimizer_progress_state,
    sync_optimizer_progress_state,
)
from tests.project_factory import create_generic_project
from tests.report_helpers import write_json

PROJECT_NAME = "progress_project"
MAX_EVALUATIONS = 10
BATCH_SIZE = 2
```

- [ ] **Step 2: Delete the string-replacement helper**

Remove this helper entirely:

```python
def _set_optimizer_max_evaluations(project_dir: Path, max_evaluations: int) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    text = optimizer_path.read_text(encoding="utf-8")
    text = text.replace("max_evaluations: 100", f"max_evaluations: {max_evaluations}")
    optimizer_path.write_text(text, encoding="utf-8")
```

- [ ] **Step 3: Add generic project and YAML reader helpers**

Add these helpers after `_ten_traces_seven_recorded_three_failed()`:

```python
def _create_progress_project(tmp_path: Path) -> Path:
    return create_generic_project(
        tmp_path,
        name=PROJECT_NAME,
        max_evaluations=MAX_EVALUATIONS,
        batch_size=BATCH_SIZE,
    )


def _read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    variables = payload.get("variables")
    assert isinstance(variables, list)
    names: list[str] = []
    for entry in variables:
        assert isinstance(entry, dict)
        name = entry.get("name")
        assert isinstance(name, str)
        names.append(name)
    assert names
    return tuple(names)


def _metric_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    metrics = payload.get("metrics")
    assert isinstance(metrics, list)
    names: list[str] = []
    for entry in metrics:
        assert isinstance(entry, dict)
        name = entry.get("name")
        assert isinstance(name, str)
        names.append(name)
    assert names
    return tuple(names)
```

- [ ] **Step 4: Derive fake ledger names from generated config**

In `_write_artifacts_for_progress()`, add derived names before writing the ledger:

```python
    variable_name = _variable_names(project_dir)[0]
    metric_name = _metric_names(project_dir)[0]
```

Then change the ledger row payload from:

```python
"parameters": {"FN": "2"},
"metrics": {"rise": 1.0e-12},
```

to:

```python
"parameters": {variable_name: "2"},
"metrics": {metric_name: 1.0e-12},
```

- [ ] **Step 5: Run target file after helper migration**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py -q
```

Expected before replacing old setup literals: failures may remain if pure builder or sync tests still use `bridge_test_inv` / direct template setup. Continue to Task 3 before treating this as a blocker.

## Task 3: Finish Optimizer Progress State Literal and Setup Migration

**Files:**
- Modify: `tests/test_optimizer_progress_state.py`
- Test: `tests/test_optimizer_progress_state.py`

- [ ] **Step 1: Replace pure builder project-name literals**

Replace every:

```python
project_name="bridge_test_inv",
```

with:

```python
project_name=PROJECT_NAME,
```

- [ ] **Step 2: Replace sync-test project creation**

Replace each sync-test setup:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
_set_optimizer_max_evaluations(project_dir, 10)
```

with:

```python
project_dir = _create_progress_project(tmp_path)
```

- [ ] **Step 3: Replace existing state payload project name**

In `test_sync_optimizer_progress_state_preserves_existing_started_at_utc`, change:

```python
"project_name": "bridge_test_inv",
```

to:

```python
"project_name": PROJECT_NAME,
```

- [ ] **Step 4: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 5: Check optimizer-progress drift**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_optimizer_progress_state.py || true
```

Expected: no output.

## Task 4: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove the two migrated files from the allowlist**

Remove these entries from `ALLOWED_TEMPLATE_CALLERS`:

```python
"tests/test_optimizer_progress_state.py",
"tests/test_run_retention.py",
```

After the edit the allowlist should contain 12 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/real_run_smoke_helpers.py",
    "tests/test_fix_run_flow.py",
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

- [ ] **Step 3: Run both migrated files with the guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
29 passed
```

## Task 5: Update the Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update the phase list in the header**

Change the phase summary from:

```markdown
6 (approval gate), and 7 (optimizer task package)
```

to:

```markdown
6 (approval gate), 7 (optimizer task package), and 8 (run retention + optimizer progress state)
```

- [ ] **Step 2: Update the introduction paragraph**

Append this sentence to the paragraph that lists completed phase migrations:

```markdown
Phase 8 migrated the local run-retention and optimizer-progress-state tests.
```

- [ ] **Step 3: Add a Phase 8 status section before Phase 7**

Insert this section above `## Phase 7 status`, adjusting counts only if the verified commands produce different numbers:

```markdown
## Phase 8 status

Migrated two local state-maintenance test files away from direct
`create_project_from_template()` usage:

- tests/test_run_retention.py — now creates a generic project through
  `create_generic_project()` and mutates `config/spectre.yaml` through structured
  YAML. The retention policy, local keep/delete/missing/failure behavior,
  decision-report schema, unsafe-run-id rejection, and local/remote decision merge
  assertions are preserved.
- tests/test_optimizer_progress_state.py — now creates sync-test projects through
  `create_generic_project(name="progress_project", max_evaluations=10,
  batch_size=2)`. Fake ledger rows derive variable and metric names from
  `config/variables.yaml` and `config/metrics.yaml`; pure builder tests use a
  neutral local `PROJECT_NAME` constant. Progress status, count, best-candidate,
  artifact sync, and `started_at_utc` preservation assertions are preserved.

Both files were removed from `ALLOWED_TEMPLATE_CALLERS` (allowlist 14 -> 12).
No external tests import from either migrated module.
```

- [ ] **Step 4: Update remaining migration waves**

Remove these files from the remaining wave list:

```markdown
- tests/test_run_retention.py
- tests/test_optimizer_progress_state.py
```

The local packaging/state wave should now list only:

```markdown
- tests/test_fix_run_flow.py
- tests/test_multi_testbench_aggregation.py
- tests/real_run_smoke_helpers.py
```

- [ ] **Step 5: Add Phase 8 verification**

Add this verification block above Phase 7 verification, replacing counts only if the real command output differs:

```markdown
### Phase 8

- `pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py -q` -> `28 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_template_coupling_guard.py -q` -> `29 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py -q` -> `322 passed`
- `pytest -q` -> `1194 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|FN|WN|FP|WP|rise` over `tests/test_run_retention.py tests/test_optimizer_progress_state.py` -> no matches
- grep `from tests.test_run_retention|tests.test_run_retention|from tests.test_optimizer_progress_state|tests.test_optimizer_progress_state` over `tests/` -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 14 -> 12.
```

## Task 6: Full Verification and Final Report

**Files:**
- Verify: entire repo test surface
- Verify: release checkout remains untouched

- [ ] **Step 1: Run Phase 8 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
```

Expected:

```text
322 passed
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
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_run_retention.py tests/test_optimizer_progress_state.py || true
```

Expected: no output.

- [ ] **Step 7: Run final cross-import grep**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_run_retention\|tests.test_run_retention\|from tests.test_optimizer_progress_state\|tests.test_optimizer_progress_state" tests || true
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
 M tests/test_optimizer_progress_state.py
 M tests/test_run_retention.py
 M tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 9: Write final report**

Include:

- Files modified.
- Exact migration summary per target file.
- Guard allowlist count `14 -> 12`.
- Exact verification commands and pass/fail counts.
- Drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Deferred files still in the allowlist:

```text
tests/test_package.py
tests/real_run_smoke_helpers.py
tests/test_fix_run_flow.py
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

- A production-code change under `src/` appears necessary.
- A test outside the four allowed files must be modified.
- `tests/project_factory.py` needs a behavior change.
- A remote, adapter, backend, fix-run, or multi-testbench flow becomes involved.
- Full-suite failures appear outside the migrated files and cannot be tied directly to this phase.
