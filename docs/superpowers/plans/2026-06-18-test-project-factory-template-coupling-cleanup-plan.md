# Test Project Factory and Template Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a generic test project factory and start migrating behavior tests away from the packaged release template.

**Architecture:** Keep `create_project_from_template()` as the product/template API. Add `tests/project_factory.py` as a test-only factory that writes minimal valid projects directly. Migrate low-risk behavior tests first and add an allowlist guard so future template coupling is visible.

**Tech Stack:** Python, pytest, PyYAML, existing `hermes_workflow` validation/package/approval helpers.

---

## Current Evidence

Audit commands used to scope this plan:

```bash
graphify explain "create_project_from_template()"
codegraph_callers create_project_from_template
rg -n "create_project_from_template" tests src docs -g '!graphify-out/**'
rg -n "bridge_test_inv|FN|WN|FP|WP|NF_3G|VB_LO|create_project_from_template" tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_mock_optimizer.py tests/test_real_result_record.py tests/test_remote_optimizer_flow.py tests/test_optimizer_task_package.py tests/test_approvals.py
```

Findings:

- `create_project_from_template()` is a high-degree cross-community graph node.
- Direct usage appears in 25 test files.
- It is used about 160 times under `tests/`.
- `tests/test_package.py` is the main legitimate template behavior test file.
- Many other files use it only to get a valid project tree.

## Files

Create:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_template_coupling_guard.py`

Modify in Phase 1:

- `tests/report_helpers.py`
- `tests/test_approvals.py`
- `tests/test_health.py`
- `tests/test_optimizer_flow.py`
- `tests/test_metric_results.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run.py`
- `tests/test_result_handoff.py`
- `tests/test_real_run_recovery.py`

Do not modify:

- `src/hermes_workflow/package.py`
- `src/hermes_workflow/templates/`
- `examples/`
- `ic-auto-opt-workflow-v0.1/`
- `graphify-out/`

## Task 1: Add Generic Test Project Factory

**Files:**
- Create: `tests/project_factory.py`
- Test: `tests/test_project_factory.py`

- [ ] **Step 1: Create `tests/project_factory.py`**

Create the file with this implementation:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package
from hermes_workflow.validate import assert_valid_project, validate_project_files
from tests.report_helpers import write_pass_reports


DEFAULT_VARIABLE_NAMES = ("VAR_INT", "VAR_WIDTH")
DEFAULT_METRIC_NAMES = ("metric_gain", "metric_power")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def create_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    workflow_mode: str = "optimize",
    variable_names: tuple[str, ...] = DEFAULT_VARIABLE_NAMES,
    metric_names: tuple[str, ...] = DEFAULT_METRIC_NAMES,
    require_license_check: bool = True,
    parallel_jobs: int = 4,
    batch_size: int = 2,
    max_evaluations: int = 6,
) -> Path:
    if len(variable_names) != 2:
        raise ValueError("create_generic_project expects exactly two variables")
    if len(metric_names) != 2:
        raise ValueError("create_generic_project expects exactly two metrics")
    if workflow_mode not in {"optimize", "fix_run"}:
        raise ValueError("workflow_mode must be optimize or fix_run")

    project_dir = tmp_path / name
    _write_directories(project_dir)
    _write_project_config(project_dir, name=name)
    _write_variables_config(project_dir, variable_names=variable_names)
    _write_metrics_config(project_dir, metric_names=metric_names)
    _write_spectre_config(
        project_dir,
        require_license_check=require_license_check,
        parallel_jobs=parallel_jobs,
    )
    _write_optimizer_config(
        project_dir,
        batch_size=batch_size,
        max_evaluations=max_evaluations,
    )
    _write_netlists(project_dir, variable_names=variable_names)
    if workflow_mode == "fix_run":
        _write_fix_run_workflow(project_dir, variable_names=variable_names)

    report = validate_project_files(project_dir)
    assert report.ok, report.format()
    assert_valid_project(project_dir)
    return project_dir


def create_packaged_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    created_at_utc: str = "2026-06-18T00:00:00Z",
    **kwargs: Any,
) -> Path:
    project_dir = create_generic_project(tmp_path, name=name, **kwargs)
    build_execution_package(project_dir, created_at_utc=created_at_utc)
    return project_dir


def create_approved_generic_project(
    tmp_path: Path,
    *,
    name: str = "generic_project",
    created_at_utc: str = "2026-06-18T00:00:00Z",
    **kwargs: Any,
) -> Path:
    project_dir = create_packaged_generic_project(
        tmp_path,
        name=name,
        created_at_utc=created_at_utc,
        **kwargs,
    )
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-18T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    return project_dir


def _write_directories(project_dir: Path) -> None:
    for relative in [
        "config",
        "netlists/exported",
        "netlists/templates",
        "execution_package",
        "reports",
        "state",
        "ledger",
        "runs/real",
    ]:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)


def _write_project_config(project_dir: Path, *, name: str) -> None:
    write_yaml(
        project_dir / "config" / "project_config.yaml",
        {
            "schema_version": "1.0",
            "project": {
                "name": name,
                "description": "Generic test project",
                "backend": "maestro_exported_spectre_deck",
            },
            "testbench": {
                "virtuoso_library": "test_lib",
                "cell": name,
                "design_view": "schematic",
                "maestro_view": "maestro",
                "test_name": "generic_tb",
                "corner": "tt",
            },
            "netlist": {
                "source": "existing_maestro_setup",
                "export_method": "maeCreateNetlistForCorner",
                "exported_input_scs": "netlists/exported/input.scs",
                "template_scs": "netlists/templates/template.scs",
            },
            "safety": {
                "immutable_after_package": True,
                "require_hermes_approval_before_real_run": True,
                "allow_maestro_setup_modification": False,
                "allow_only_variable_templating": True,
            },
        },
    )


def _write_variables_config(
    project_dir: Path,
    *,
    variable_names: tuple[str, ...],
) -> None:
    int_name, width_name = variable_names
    write_yaml(
        project_dir / "config" / "variables.yaml",
        {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": int_name,
                    "kind": "integer",
                    "lower": "1",
                    "upper": "5",
                    "step": "1",
                },
                {
                    "name": width_name,
                    "kind": "continuous_step",
                    "lower": "0.1u",
                    "upper": "0.5u",
                    "step": "0.1u",
                },
            ],
        },
    )


def _write_metrics_config(
    project_dir: Path,
    *,
    metric_names: tuple[str, ...],
) -> None:
    gain_name, power_name = metric_names
    write_yaml(
        project_dir / "config" / "metrics.yaml",
        {
            "schema_version": "1.0",
            "metrics": [
                {
                    "name": gain_name,
                    "unit": "V/V",
                    "maestro_formula": 'value(v("/OUT") 1n)',
                    "required_signals": ["/OUT"],
                    "ocean": {
                        "expression": 'value(v("/OUT") 1n)',
                        "result": "tran",
                        "expression_source": "user_approved",
                        "source_reference": "test_factory:generic:metric_gain",
                        "expected_value_type": "real_scalar",
                        "nil_policy": "fail",
                        "non_finite_policy": "fail",
                    },
                },
                {
                    "name": power_name,
                    "unit": "W",
                    "maestro_formula": 'value(i("/VDD") 1n)',
                    "required_signals": ["/VDD"],
                    "ocean": {
                        "expression": 'value(i("/VDD") 1n)',
                        "result": "tran",
                        "expression_source": "user_approved",
                        "source_reference": "test_factory:generic:metric_power",
                        "expected_value_type": "real_scalar",
                        "nil_policy": "fail",
                        "non_finite_policy": "fail",
                    },
                },
            ],
            "constraints": [
                {
                    "metric": power_name,
                    "op": "lt",
                    "value": "1e-3 W",
                }
            ],
            "objective": {
                "direction": "maximize",
                "expression": f"{gain_name} - {power_name}",
            },
        },
    )


def _write_spectre_config(
    project_dir: Path,
    *,
    require_license_check: bool,
    parallel_jobs: int,
) -> None:
    write_yaml(
        project_dir / "config" / "spectre.yaml",
        {
            "schema_version": "1.0",
            "spectre": {
                "engine": "spectre_x",
                "preset": "ax",
                "output_format": "psfxl",
                "threads_per_run": 2,
                "parallel_jobs": parallel_jobs,
                "timeout_s": 3600,
                "require_license_check": require_license_check,
                "keep_failed_runs": True,
                "keep_successful_runs": True,
            },
        },
    )


def _write_optimizer_config(
    project_dir: Path,
    *,
    batch_size: int,
    max_evaluations: int,
) -> None:
    write_yaml(
        project_dir / "config" / "optimizer.yaml",
        {
            "schema_version": "1.0",
            "optimizer": {
                "algorithm": "turbo",
                "initialization": "sobol",
                "max_evaluations": max_evaluations,
                "batch_size": batch_size,
                "random_seed": 20260618,
                "optimizer_cpu_threads": 2,
                "failure_penalty": 1000000.0,
                "deduplicate_candidates": True,
            },
        },
    )


def _write_netlists(
    project_dir: Path,
    *,
    variable_names: tuple[str, ...],
) -> None:
    int_name, width_name = variable_names
    template = (
        "// generic test template\n"
        f"parameters {int_name}={{{{{int_name}}}}} {width_name}={{{{{width_name}}}}}\n"
        "tran tran stop=10n\n"
    )
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        template,
        encoding="utf-8",
    )
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "parameters placeholder=1\ntran tran stop=10n\n",
        encoding="utf-8",
    )


def _write_fix_run_workflow(
    project_dir: Path,
    *,
    variable_names: tuple[str, ...],
) -> None:
    int_name, width_name = variable_names
    write_yaml(
        project_dir / "config" / "workflow.yaml",
        {
            "schema_version": "1.0",
            "workflow": {"mode": "fix_run"},
            "fixed_points": [
                {
                    "candidate_id": "fixed_001",
                    "parameters": {int_name: "2", width_name: "0.2u"},
                }
            ],
        },
    )
    (project_dir / "config" / "optimizer.yaml").unlink(missing_ok=True)


def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return tuple(variable["name"] for variable in payload["variables"])
```

- [ ] **Step 2: Update `tests/report_helpers.py` to support generic variables**

Change `write_pass_reports()` to accept variable names while preserving the old default:

```python
def write_pass_reports(
    project_dir: Path,
    *,
    variable_names: tuple[str, ...] = ("FN", "WN", "FP", "WP"),
) -> None:
    approved_variables = {name: True for name in variable_names}
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": approved_variables,
            "analysis_statements": ["tran", "dc"],
            "forbidden_setup_changes_detected": False,
            "issues": [],
        },
    )
    write_json(
        project_dir / "reports" / "dry_run_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "rendered_candidate_scs": "runs/dry_run/input.scs",
            "placeholder_check": {
                "unresolved_placeholders": [],
                "unexpected_template_variables": [],
            },
            "metrics_import_ok": True,
            "mock_metrics_ok": True,
            "objective_ok": True,
            "constraints_ok": True,
            "ledger_write_ok": True,
            "state_write_ok": True,
            "issues": [],
        },
    )
    write_json(
        project_dir / "state" / "health_check.json",
        {
            "schema_version": "1.0",
            "status": "healthy",
            "real_run_started": False,
            "current_evaluations": 0,
            "best_candidate_path": None,
            "last_batch_id": None,
            "issues": [],
        },
    )
```

- [ ] **Step 3: Create `tests/test_project_factory.py`**

Create:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from hermes_workflow.validate import assert_valid_project, validate_project_files
from tests.project_factory import (
    create_approved_generic_project,
    create_generic_project,
    create_packaged_generic_project,
)


def test_create_generic_project_is_valid_and_template_independent(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)

    assert project_dir.name == "generic_project"
    assert validate_project_files(project_dir).ok is True
    assert_valid_project(project_dir)
    variables = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    variable_names = [entry["name"] for entry in variables["variables"]]
    assert variable_names == ["VAR_INT", "VAR_WIDTH"]
    assert "bridge_test_inv" not in (
        project_dir / "config" / "project_config.yaml"
    ).read_text(encoding="utf-8")


def test_create_packaged_generic_project_writes_execution_manifest(
    tmp_path: Path,
) -> None:
    project_dir = create_packaged_generic_project(tmp_path)

    manifest = json.loads(
        (
            project_dir / "execution_package" / "execution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["project_name"] == "generic_project"
    assert "config/variables.yaml" in manifest["immutable_config_files"]


def test_create_approved_generic_project_approves_first_real_run(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_generic_project(tmp_path)

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert instruction["decision"] == "approve_first_real_run"
    report = json.loads(
        (project_dir / "reports" / "netlist_preparation_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["approved_variables_template_status"] == {
        "VAR_INT": True,
        "VAR_WIDTH": True,
    }
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_project_factory.py -q
```

Expected:

```text
3 passed
```

## Task 2: Add Coupling Guard

**Files:**
- Create: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Create guard test with an explicit phase allowlist**

Create:

```python
from __future__ import annotations

from pathlib import Path


ALLOWED_TEMPLATE_CALLERS = {
    # Product/template behavior.
    "tests/test_package.py",
    "tests/test_cli.py",
    # Not yet migrated. Shrink this list in follow-up waves.
    "tests/real_run_smoke_helpers.py",
    "tests/test_approvals.py",
    "tests/test_dry_run.py",
    "tests/test_fix_run_flow.py",
    "tests/test_health.py",
    "tests/test_metric_results.py",
    "tests/test_mock_optimizer.py",
    "tests/test_multi_testbench_aggregation.py",
    "tests/test_native_turbo.py",
    "tests/test_netlists.py",
    "tests/test_next_real_run.py",
    "tests/test_openbox_backend.py",
    "tests/test_optimizer_flow.py",
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


def test_create_project_from_template_usage_is_explicitly_allowlisted() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "tests").glob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/test_template_coupling_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "create_project_from_template" in text and relative not in ALLOWED_TEMPLATE_CALLERS:
            offenders.append(relative)

    assert offenders == []
```

This guard intentionally starts permissive. It prevents new unreviewed usage immediately. Each migration task must remove files from the allowlist after replacing their direct template usage.

- [ ] **Step 2: Run the guard**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

## Task 3: Migrate First Low-Risk Files

Migrate these files in one small wave:

- `tests/test_health.py`
- `tests/test_optimizer_flow.py`
- `tests/test_metric_results.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run.py`
- `tests/test_result_handoff.py`
- `tests/test_real_run_recovery.py`

Leave `tests/test_approvals.py` for the next wave if it requires more expected-payload changes.

- [ ] **Step 1: Replace imports in each target file**

Replace:

```python
from hermes_workflow.package import create_project_from_template
```

or grouped imports containing `create_project_from_template`

with:

```python
from tests.project_factory import (
    create_approved_generic_project,
    create_generic_project,
    create_packaged_generic_project,
)
```

Keep any other imports from `hermes_workflow.package`, such as `build_execution_package` or `sha256_file`.

- [ ] **Step 2: Replace simple valid-project setup**

Replace patterns like:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
```

with:

```python
project_dir = create_generic_project(tmp_path)
```

- [ ] **Step 3: Replace packaged-project setup**

Replace patterns like:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
build_execution_package(project_dir, created_at_utc="2026-...")
```

with:

```python
project_dir = create_packaged_generic_project(
    tmp_path,
    created_at_utc="2026-...",
)
```

- [ ] **Step 4: Replace approved real-project setup**

Replace local helpers that only create, package, write pass reports, and approve with:

```python
project_dir = create_approved_generic_project(tmp_path)
```

If a helper also prepares a real run or writes custom netlist content, keep that extra behavior after the factory call.

- [ ] **Step 5: Update expected project and variable names**

For migrated files only, replace assertions that exist only because of the template baseline:

```python
"bridge_test_inv"
```

with:

```python
"generic_project"
```

Replace variable assumptions:

```python
("FN", "WN", "FP", "WP")
```

with:

```python
("VAR_INT", "VAR_WIDTH")
```

Only do this when the test is checking the generic project fixture. Do not change tests that intentionally exercise four-variable optimizer behavior; leave those for a later wave.

- [ ] **Step 6: Remove migrated files from the guard allowlist**

After a target file has no direct `create_project_from_template` usage, remove it from `ALLOWED_TEMPLATE_CALLERS` in `tests/test_template_coupling_guard.py`.

- [ ] **Step 7: Run focused tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_metric_results.py \
  tests/test_next_real_run.py \
  tests/test_real_run.py \
  tests/test_result_handoff.py \
  tests/test_real_run_recovery.py \
  -q
```

Expected: all selected tests pass.

## Task 4: Re-audit Direct Template Usage

- [ ] **Step 1: Count remaining usage**

Run:

```bash
rg -n "create_project_from_template" tests | cut -d: -f1 | sort | uniq -c
```

Expected:

- Migrated files no longer appear.
- `tests/test_package.py` still appears.
- Not-yet-migrated files still appear and remain listed in the guard allowlist.

- [ ] **Step 2: Record the remaining migration inventory**

Create or update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Use this format:

```markdown
# Test Project Factory Template Coupling Inventory

## Migrated in this wave

- tests/test_health.py
- tests/test_optimizer_flow.py
- tests/test_metric_results.py
- tests/test_next_real_run.py
- tests/test_real_run.py
- tests/test_result_handoff.py
- tests/test_real_run_recovery.py

## Intentionally template-based

- tests/test_package.py
- tests/test_cli.py

## Remaining migration waves

### Optimizer backend
- tests/test_openbox_backend.py
- tests/test_native_turbo.py
- tests/test_mock_optimizer.py

### Remote and adapter flows
- tests/test_remote_optimizer_flow.py
- tests/test_remote_fix_run_flow.py
- tests/test_remote_spectre_ocean.py
- tests/test_spectre_ocean_adapter.py

### Packaging/approval/retention
- tests/test_optimizer_task_package.py
- tests/test_approvals.py
- tests/test_run_retention.py
- tests/test_netlists.py
- tests/test_dry_run.py
- tests/test_fix_run_flow.py
- tests/test_multi_testbench_aggregation.py
- tests/test_optimizer_progress_state.py

## Verification

- `<command>` -> `<result>`
```

Do not include `graphify-out/`.

## Task 5: Final Verification

- [ ] **Step 1: Run focused factory/migration tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_metric_results.py \
  tests/test_next_real_run.py \
  tests/test_real_run.py \
  tests/test_result_handoff.py \
  tests/test_real_run_recovery.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run full suite**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Expected: full suite passes. Record exact count.

- [ ] **Step 3: Run Ruff**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m ruff check src tests
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

Expected: no output.

- [ ] **Step 5: Check worktree scope**

Run:

```bash
git status --short
```

Expected:

- Changed/new files are limited to test factory, migrated tests, guard, and reports/spec/plan docs.
- `graphify-out/` remains untracked and must not be staged.
- release checkout `ic-auto-opt-workflow-v0.1` is not touched.

## Task 6: Final Report

Final response must include:

```text
Created:
- tests/project_factory.py
- tests/test_project_factory.py
- tests/test_template_coupling_guard.py

Migrated:
- <list migrated files>

Still intentionally template-based:
- tests/test_package.py
- tests/test_cli.py

Remaining waves:
- <grouped list from inventory>

Verification:
- <focused pytest command/result>
- <full pytest command/result>
- <ruff command/result>
- <git diff --check result>

Not touched:
- ic-auto-opt-workflow-v0.1
- graphify-out/
```

Do not claim all template coupling is removed after Phase 1. Claim only that the factory and guard are in place and the first wave is migrated.
