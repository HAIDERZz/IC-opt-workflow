import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.project_readiness import check_project_ready
from hermes_workflow.requirement_intake import prepare_from_requirement
from tests.test_requirement_intake import _copy_multi_testbench_requirement_project


runner = CliRunner()


def test_check_project_ready_accepts_prepared_multi_testbench_project(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_from_requirement(project_dir)

    report = check_project_ready(project_dir)

    assert report.status == "pass"
    assert report.readiness == "ready_for_first_run"
    assert report.core_ready is True
    assert report.final_summary_ready is False
    assert report.report_path == project_dir / "reports/project_readiness_report.json"
    assert "final optimizer summary is not present yet" in report.warnings
    assert {
        "name": "multi_testbench_netlists",
        "status": "pass",
        "detail": "2 testbench netlist bundles are ready",
    } in report.checks

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["readiness"] == "ready_for_first_run"


def test_check_project_ready_reports_missing_core_config(tmp_path: Path) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_from_requirement(project_dir)
    (project_dir / "config" / "metrics.yaml").unlink()

    report = check_project_ready(project_dir)

    assert report.status == "fail"
    assert report.readiness == "needs_setup"
    assert "missing required config file: config/metrics.yaml" in report.issues


def test_check_project_ready_cli_prints_summary(tmp_path: Path) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_from_requirement(project_dir)

    result = runner.invoke(app, ["check-project-ready", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "project readiness: pass" in result.output
    assert "readiness: ready_for_first_run" in result.output
    assert "report: reports/project_readiness_report.json" in result.output


@pytest.mark.parametrize("path_name", ["missing_project"])
def test_check_project_ready_cli_fails_for_missing_project(
    tmp_path: Path,
    path_name: str,
) -> None:
    result = runner.invoke(app, ["check-project-ready", str(tmp_path / path_name)])

    assert result.exit_code == 1
    assert "project readiness: fail" in result.output
