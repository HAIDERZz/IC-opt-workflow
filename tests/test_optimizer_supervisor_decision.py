import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_supervisor_decision import (
    record_optimizer_supervisor_decision,
)
from tests.test_optimizer_decision import _write_mixer_project


runner = CliRunner()


def test_record_optimizer_supervisor_decision_accepts_recommended_candidate(
    tmp_path: Path,
) -> None:
    project_dir = _write_mixer_project(tmp_path)
    generate_optimizer_decision_report(project_dir)

    report = record_optimizer_supervisor_decision(
        project_dir,
        reason="user accepted the current configured-objective recommendation",
    )

    assert report.status == "pass"
    assert report.action == "accept_best_observed"
    assert report.accepted_run_id == "real_002"
    assert report.global_optimum_claim is False
    assert report.source_decision_report == "reports/optimizer_decision_report.json"
    assert report.accepted_candidate["parameters"]["F"] == "20"
    assert report.report_path == project_dir / "reports/optimizer_supervisor_decision.json"
    assert report.markdown_path == project_dir / "reports/optimizer_supervisor_decision.md"

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["accepted_run_id"] == "real_002"
    assert payload["boundaries"]["best_candidate_scope"] == "best_observed"

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "# Optimizer Supervisor Decision" in markdown
    assert "real_002" in markdown
    assert "accept_best_observed" in markdown
    assert "Global optimum claim: false" in markdown


def test_record_optimizer_decision_cli_writes_acceptance_record(tmp_path: Path) -> None:
    project_dir = _write_mixer_project(tmp_path)
    generate_optimizer_decision_report(project_dir)

    result = runner.invoke(
        app,
        [
            "record-optimizer-decision",
            str(project_dir),
            "--reason",
            "accept this current best observed point",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "optimizer supervisor decision recorded" in result.output
    assert "accepted: real_002" in result.output
    assert (project_dir / "reports/optimizer_supervisor_decision.json").exists()
