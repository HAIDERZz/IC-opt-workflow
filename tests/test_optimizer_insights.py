import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from tests.test_optimizer_completion import _write_accepted_optimizer_project


runner = CliRunner()


def test_generate_optimizer_insight_report_writes_json_markdown_and_svgs(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    report = generate_optimizer_insight_report(project_dir)

    assert report.status == "pass"
    assert report.evaluation_count == 6
    assert report.status_counts == {"constraint_failed": 2, "feasible": 4}
    assert report.best_observed is not None
    assert report.best_observed["run_id"] == "real_006"
    assert report.report_path == project_dir / "reports/optimizer_insight_report.json"
    assert report.markdown_path == project_dir / "reports/optimizer_insight_report.md"

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["advanced_surrogate_visualization"]["status"] == "not_generated"
    assert "FN" in payload["observed_relationships"]
    assert "objective" in payload["observed_relationships"]["FN"]
    assert payload["plots"] == {
        "convergence": "reports/optimizer_visuals/convergence.svg",
        "parameter_objective_scatter": (
            "reports/optimizer_visuals/parameter_objective_scatter.svg"
        ),
        "status_distribution": "reports/optimizer_visuals/status_distribution.svg",
    }

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "# Optimizer Insight Report" in markdown
    assert "Best observed" in markdown
    assert "Observed Relationships" in markdown

    for relative_plot in payload["plots"].values():
        plot_text = (project_dir / relative_plot).read_text(encoding="utf-8")
        assert plot_text.startswith("<svg")


def test_generate_optimizer_insight_report_records_metric_relationships(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    report = generate_optimizer_insight_report(project_dir)

    relationships = report.observed_relationships
    assert "WN" in relationships
    assert "rise" in relationships["WN"]
    assert relationships["WN"]["rise"]["sample_count"] == 6
    assert relationships["WN"]["rise"]["relationship"] in {
        "positive",
        "negative",
        "weak",
    }


def test_visualize_optimizer_run_cli_writes_report(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    result = runner.invoke(app, ["visualize-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "optimizer insight report written" in result.output
    assert "reports/optimizer_insight_report.json" in result.output
    assert (project_dir / "reports/optimizer_insight_report.json").exists()


def test_generate_optimizer_insight_report_fails_without_traces(tmp_path: Path) -> None:
    project_dir = tmp_path / "empty"
    (project_dir / "reports").mkdir(parents=True)

    report = generate_optimizer_insight_report(project_dir)

    assert report.status == "fail"
    assert "no optimizer trace rows found" in report.issues
