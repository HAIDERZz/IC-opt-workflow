from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from hermes_workflow.validate import assert_valid_project, validate_project_files


FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "bridge_test_inv"


def copy_fixture_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    shutil.copytree(FIXTURE_PROJECT, project_dir)
    return project_dir


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_valid_project_files_pass(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)

    report = validate_project_files(project_dir)

    assert report.ok is True
    assert report.issues == []
    assert report.format() == "validation passed"
    assert_valid_project(project_dir)


def test_batch_size_must_not_exceed_spectre_parallel_jobs(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = read_yaml(optimizer_path)
    payload["optimizer"]["batch_size"] = 11
    write_yaml(optimizer_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.message == "optimizer.batch_size must be <= spectre.parallel_jobs"
        for issue in report.issues
    )


def test_objective_expression_rejects_function_calls(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "max(rise, fall)"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "unsupported objective expression node Call" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_unknown_metric_names(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "(rise + slew) * DC"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective references unknown metric slew" in issue.message
        for issue in report.issues
    )


def test_netlist_paths_must_stay_under_expected_directories(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    project_config_path = project_dir / "config" / "project_config.yaml"
    payload = read_yaml(project_config_path)
    payload["netlist"]["exported_input_scs"] = "../input.scs"
    write_yaml(project_config_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "netlist.exported_input_scs must stay under netlists/exported/"
        in issue.message
        for issue in report.issues
    )


def test_continuous_step_units_must_match(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["step"] = "200 nm"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "WN lower, upper, and step unit suffixes must match" in issue.message
        for issue in report.issues
    )
