import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_final_summary import generate_optimizer_final_summary
from hermes_workflow.optimizer_supervisor_decision import (
    record_optimizer_supervisor_decision,
)
from tests.test_optimizer_decision import _write_mixer_project


runner = CliRunner()


def test_generate_optimizer_final_summary_writes_user_facing_report(
    tmp_path: Path,
) -> None:
    project_dir = _write_mixer_project(tmp_path)
    generate_optimizer_decision_report(project_dir)
    record_optimizer_supervisor_decision(
        project_dir,
        reason="user accepted the current recommendation",
    )

    report = generate_optimizer_final_summary(project_dir)

    assert report.status == "pass"
    assert report.accepted_run_id == "real_002"
    assert report.action == "accept_best_observed"
    assert report.global_optimum_claim is False
    assert report.accepted_candidate["parameters"]["F"] == "20"
    assert report.bottleneck["metric"] == "IIP3"
    assert "reports/optimizer_visuals/bottleneck_weighted_score.svg" in report.visuals
    assert report.report_path == project_dir / "reports/optimizer_final_summary.json"
    assert report.markdown_path == project_dir / "reports/optimizer_final_summary.md"

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["accepted_run_id"] == "real_002"
    assert payload["boundaries"]["best_candidate_scope"] == "best_observed"

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "# Optimizer Final Summary" in markdown
    assert "real_002" in markdown
    assert "Best observed" in markdown
    assert "IIP3" in markdown
    assert "reports/optimizer_visuals/bottleneck_weighted_score.svg" in markdown


def test_finalize_optimizer_summary_cli_writes_report(tmp_path: Path) -> None:
    project_dir = _write_mixer_project(tmp_path)
    generate_optimizer_decision_report(project_dir)
    record_optimizer_supervisor_decision(project_dir)

    result = runner.invoke(app, ["write-optimizer-final-summary", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "optimizer final summary written" in result.output
    assert "accepted: real_002" in result.output
    assert (project_dir / "reports/optimizer_final_summary.md").exists()
