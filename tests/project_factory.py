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
