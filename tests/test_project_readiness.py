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


def _make_fix_run_readiness_project(tmp_path: Path) -> Path:
    """Build a fix-run-shape project from the multi-testbench requirement,
    then strip optimizer-only configs and add fix-run configs."""
    import yaml as _yaml

    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_from_requirement(project_dir)
    (project_dir / "config" / "optimizer.yaml").unlink()
    (project_dir / "config" / "metrics.yaml").unlink()
    (project_dir / "config" / "workflow.yaml").write_text(
        "schema_version: '1.0'\nmode: fix_run\nstarting_run_id: real_001\n",
        encoding="utf-8",
    )
    variables = _yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    parameters = {var["name"]: str(var["lower"]) for var in variables["variables"]}
    (project_dir / "config" / "fixed_points.yaml").write_text(
        _yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {"candidate_id": "user_point_001", "parameters": parameters},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "config" / "waveform_exports.yaml").write_text(
        _yaml.safe_dump(
            {
                "schema_version": "1.0",
                "exports": [
                    {
                        "name": "nf_pnoise",
                        "testbench": "cg_nf",
                        "expression": 'getData("NF" ?result "pnoise")',
                        "output_format": "csv",
                        "nil_policy": "fail",
                    },
                    {
                        "name": "iip3_spectrum",
                        "testbench": "iip3",
                        "expression": 'getData("iip3")',
                        "output_format": "csv",
                        "nil_policy": "fail",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return project_dir


def test_check_project_ready_accepts_fix_run_project(tmp_path: Path) -> None:
    """A fix-run project (with workflow.yaml and fixed_points.yaml, but no
    optimizer.yaml or metrics.yaml) must pass the project readiness check.
    It needs at least one of metrics.yaml or waveform_exports.yaml; here we
    have waveform_exports.yaml."""
    project_dir = _make_fix_run_readiness_project(tmp_path)

    report = check_project_ready(project_dir)

    assert report.status == "pass", report.issues


def test_check_project_ready_fix_run_requires_fixed_points(tmp_path: Path) -> None:
    project_dir = _make_fix_run_readiness_project(tmp_path)
    (project_dir / "config" / "fixed_points.yaml").unlink()

    report = check_project_ready(project_dir)

    assert report.status == "fail"
    assert any("fixed_points.yaml" in issue for issue in report.issues)


def test_check_project_ready_optimizer_mode_still_requires_optimizer_yaml(
    tmp_path: Path,
) -> None:
    """Optimizer mode (no workflow.yaml at all, or mode=optimize) must keep
    treating optimizer.yaml as required. Locks in the regression boundary."""
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_from_requirement(project_dir)
    (project_dir / "config" / "optimizer.yaml").unlink()

    report = check_project_ready(project_dir)

    assert report.status == "fail"
    assert any("optimizer.yaml" in issue for issue in report.issues)
