# Optimizer Flow Validation Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the optimizer-flow validation bug where non-positive `max_evals` is not rejected before workflow execution.

**Architecture:** Keep this as a minimal validation-layer bugfix. Add a regression test at the public `optimize_project()` boundary, then move the `max_evals` guard in `_validate_options()` so it is reachable for all valid backends. Do not refactor workflow orchestration.

**Tech Stack:** Python, pytest, Typer test helpers already present in the repo, Ruff.

---

## Files

- Modify: `src/hermes_workflow/optimizer_flow.py`
  - Fix `_validate_options()` reachability and type annotation.
  - Optionally clean broken indentation in the already-touched `optimize_project()` call/report blocks without behavior changes.
- Modify: `tests/test_optimizer_flow.py`
  - Import `pytest`.
  - Add regression test for `max_evals=0` and `max_evals=-1`.

## Task 1: Confirm Scope With Graph and Source

- [ ] **Step 1: Query graphify for scope only**

Run:

```bash
graphify query "Trace optimizer_flow.py optimize_project and _validate_options risks. Which surrounding tests and workflow nodes should be checked for a focused validation bugfix?" --budget 2200
```

Expected: The output should identify `optimizer_flow.py`, `test_optimizer_flow.py`, and caller context such as product CLI or remote optimizer flow. Do not rebuild graphify. Do not edit `graphify-out/`.

- [ ] **Step 2: Inspect exact source with codegraph**

Run:

```bash
codegraph_node _validate_options file=optimizer_flow.py includeCode=true
codegraph_node optimize_project file=optimizer_flow.py includeCode=true
```

Expected: `_validate_options()` shows the unreachable `max_evals` check under the invalid-backend branch.

## Task 2: Add the Failing Regression Test

**Files:**
- Modify: `tests/test_optimizer_flow.py`

- [ ] **Step 1: Add pytest import**

At the top of `tests/test_optimizer_flow.py`, add:

```python
import pytest
```

The import block should become:

```python
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner
```

- [ ] **Step 2: Add the regression test**

Add this test after `_services()` and before the existing happy-path tests:

```python
@pytest.mark.parametrize("max_evals", [0, -1])
def test_optimize_project_rejects_non_positive_max_evals_before_doctor(
    tmp_path: Path,
    max_evals: int,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []

    with pytest.raises(ValueError, match="max_evals must be >= 1"):
        optimize_project(
            project_dir,
            real=True,
            max_evals=max_evals,
            cadence_cshrc=cadence_cshrc,
            services=_services(project_dir, calls),
        )

    assert calls == []
    payload = json.loads(
        (project_dir / "reports" / "optimizer_flow_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "fail"
    assert payload["issues"] == ["max_evals must be >= 1"]
    assert payload["steps"] == []
```

- [ ] **Step 3: Run the test and confirm it fails before implementation**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py::test_optimize_project_rejects_non_positive_max_evals_before_doctor -q
```

Expected before code fix: FAIL because the error is not `max_evals must be >= 1`, and workflow services may run.

## Task 3: Fix `_validate_options()`

**Files:**
- Modify: `src/hermes_workflow/optimizer_flow.py`

- [ ] **Step 1: Replace `_validate_options()` with the corrected implementation**

Replace the whole function with:

```python
def _validate_options(
    *,
    real: bool,
    cadence_cshrc: Path | None,
    max_evals: int | None,
    backend: str,
) -> None:
    if not real:
        raise ValueError("optimize requires --real; fake optimize is not supported")
    if backend not in {"openbox", "native_turbo"}:
        raise ValueError("optimize backend must be openbox or native_turbo")
    if max_evals is not None and max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if cadence_cshrc is None:
        raise ValueError("--cadence-cshrc is required")
```

- [ ] **Step 2: Clean only broken indentation in touched `optimize_project()` blocks**

If the file still shows visibly broken indentation around `package-optimizer-task`, dry-orchestration report writing, exception report writing, or final report writing, normalize indentation without changing arguments or control flow.

The `package-optimizer-task` block must read:

```python
        _run_step(
            steps,
            "package-optimizer-task",
            lambda: service.build_optimizer_execution_task_package(
                project_root,
                cadence_cshrc=cadence_cshrc,
                parallel=True,
                optimizer_backend=execution_backend,
                strategy=strategy,
            ),
            _expect_success,
        )
```

The dry-orchestration return must preserve the same fields:

```python
        if dry_orchestration:
            return _write_report(
                project_root,
                _report(
                    project_root,
                    status="pass",
                    backend=execution_backend,
                    real=real,
                    dry_orchestration=dry_orchestration,
                    max_evals=max_evals,
                    batch_size=batch_size,
                    parallel_jobs=parallel_jobs,
                    steps=steps,
                    user_decision_required=False,
                    stopped_before=dry_stopped_before,
                    issues=issues,
                    warnings=warnings,
                ),
            )
```

The exception report must keep `backend=execution_backend` aligned with the other keyword arguments:

```python
        report = _report(
            project_root,
            status="fail",
            backend=execution_backend,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            steps=steps,
            user_decision_required=False,
            stopped_before=stopped_before,
            issues=issues,
            warnings=warnings,
        )
```

The final pass report must keep `issues=issues` aligned with the other keyword arguments:

```python
    return _write_report(
        project_root,
        _report(
            project_root,
            status="pass",
            backend=execution_backend,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            steps=steps,
            user_decision_required=user_decision_required,
            recommended_run_id=recommended_run_id,
            recommended_action=recommended_action,
            stopped_before=stopped_before,
            issues=issues,
            warnings=warnings,
        ),
    )
```

- [ ] **Step 3: Run the focused regression test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py::test_optimize_project_rejects_non_positive_max_evals_before_doctor -q
```

Expected: PASS.

## Task 4: Verify Existing Optimizer Flow Behavior

- [ ] **Step 1: Run optimizer flow tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py -q
```

Expected: all tests in `tests/test_optimizer_flow.py` pass.

- [ ] **Step 2: Run CLI regression tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_product_cli.py -q
```

Expected: all tests in `tests/test_product_cli.py` pass.

- [ ] **Step 3: Run Ruff on touched files**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m ruff check src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Check diff scope**

Run:

```bash
git diff -- src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py
git status --short
```

Expected: source/test diff is limited to this validation fix and formatting of the same touched blocks. Do not include `graphify-out/`.

## Task 5: Final Report

- [ ] **Step 1: Report exact result**

Final response must include:

```text
Changed:
- src/hermes_workflow/optimizer_flow.py
- tests/test_optimizer_flow.py

Behavior fixed:
- optimize_project now rejects max_evals=0 and max_evals=-1 before doctor or workflow services run.

Verification:
- <exact pytest command/result>
- <exact pytest command/result>
- <exact ruff command/result>

Not touched:
- release checkout ic-auto-opt-workflow-v0.1
- graphify-out/
```

Do not claim full-suite pass unless the full suite was actually run and the exact count is known.
