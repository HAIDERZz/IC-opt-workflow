import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from tests.test_optimizer_completion import _trace_row, _write_accepted_optimizer_project


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
        "all_evaluable_fom": "reports/optimizer_visuals/all_evaluable_fom.svg",
        "bottleneck_weighted_score": (
            "reports/optimizer_visuals/bottleneck_weighted_score.svg"
        ),
        "constraint_margins": "reports/optimizer_visuals/constraint_margins.svg",
        "convergence": "reports/optimizer_visuals/convergence.svg",
        "feasible_convergence": "reports/optimizer_visuals/feasible_convergence.svg",
        "parameter_objective_scatter": (
            "reports/optimizer_visuals/parameter_objective_scatter.svg"
        ),
        "status_distribution": "reports/optimizer_visuals/status_distribution.svg",
    }

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "# Optimizer Insight Report" in markdown
    assert "Best observed" in markdown
    assert "Observed Relationships" in markdown
    assert "all_evaluable_fom" in markdown

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


def test_generate_optimizer_insight_report_links_openbox_advanced_visualization(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)
    report_path = project_dir / "reports/native_turbo_optimizer_report.json"
    optimizer_report = json.loads(report_path.read_text(encoding="utf-8"))
    optimizer_report["openbox"] = {
        "advanced_visualization": {
            "status": "generated",
            "mode": "advanced",
            "html_path": "reports/openbox_advanced_visualization/history/run/run.html",
            "json_path": "reports/openbox_advanced_visualization/history/run/data.json",
            "manifest_path": "reports/openbox_advanced_visualization_manifest.json",
            "includes": [
                "objective_and_constraint_history",
                "surrogate_fit_verification",
                "parameter_importance",
            ],
            "open_html": False,
            "show_importance": True,
            "verify_surrogate": True,
        }
    }
    report_path.write_text(
        json.dumps(optimizer_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = generate_optimizer_insight_report(project_dir)

    assert report.advanced_surrogate_visualization["status"] == "generated"
    assert report.advanced_surrogate_visualization["html_path"].endswith("run.html")
    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "reports/openbox_advanced_visualization/history/run/run.html" in markdown
    assert "parameter_importance" in markdown


def test_generate_optimizer_insight_report_writes_ic_native_sections(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=1_000_000.1,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=4.5e-14,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="feasible",
            objective=4.0e-14,
        ),
    ]
    rows[0]["metrics"] = {"rise": 100e-12, "fall": 75e-12, "DC": 350e-6}
    rows[1]["metrics"] = {"rise": 72e-12, "fall": 70e-12, "DC": 340e-6}
    rows[2]["metrics"] = {"rise": 68e-12, "fall": 66e-12, "DC": 320e-6}
    rows[2]["parameters"] = {"FN": "12", "WN": "2.7u", "FP": "7", "WP": "0.7u"}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    (project_dir / "config" / "metrics.yaml").write_text(
        """
schema_version: "1.0"
metrics:
  - name: rise
    unit: s
  - name: fall
    unit: s
  - name: DC
    unit: W
constraints:
  - metric: rise
    op: lt
    value: "80e-12 s"
  - metric: fall
    op: lt
    value: "80e-12 s"
  - metric: DC
    op: lt
    value: "4e-4 W"
objective:
  direction: minimize
  expression: "(rise + fall) * DC"
""".lstrip(),
        encoding="utf-8",
    )

    report = generate_optimizer_insight_report(project_dir)

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["ic_metric_summary"]["objective"]["best_feasible_run_id"] == "real_003"
    assert payload["top_feasible_candidates"][0]["run_id"] == "real_003"
    assert payload["top_feasible_candidates"][0]["metrics_display"] == {
        "DC": "320 uW",
        "fall": "66 ps",
        "rise": "68 ps",
    }
    assert payload["constraint_margin_summary"]["rise"]["best_margin_display"] == "12 ps"
    assert payload["constraint_margin_summary"]["DC"]["best_margin_display"] == "80 uW"
    assert payload["plots"]["feasible_convergence"] == (
        "reports/optimizer_visuals/feasible_convergence.svg"
    )
    assert payload["plots"]["constraint_margins"] == (
        "reports/optimizer_visuals/constraint_margins.svg"
    )
    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "IC-native Summary" in markdown
    assert "Top feasible candidates" in markdown
    assert "Constraint margins" in markdown
    assert "real_003" in markdown


def test_generate_optimizer_insight_report_recomputes_all_evaluable_fom(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="feasible",
            objective=100.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=1.0,
        ),
    ]
    rows[0]["metrics"] = {"rise": "10", "fall": 2.0, "DC": "20"}
    rows[1]["metrics"] = {"rise": "5", "fall": 6.0, "DC": "1000"}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    (project_dir / "config" / "metrics.yaml").write_text(
        """
schema_version: "1.0"
metrics:
  - name: rise
    unit: s
  - name: fall
    unit: s
  - name: DC
    unit: W
constraints: []
objective:
  direction: minimize
  expression: "min(max(rise, fall), ln(DC))"
""".lstrip(),
        encoding="utf-8",
    )

    report = generate_optimizer_insight_report(project_dir)

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    summary = payload["all_evaluable_fom_summary"]
    assert summary["source"] == "configured_objective"
    assert summary["sample_count"] == 2
    assert summary["best_run_id"] == "real_001"
    assert summary["best_objective"] == pytest.approx(math.log(20))
    assert summary["series"][0]["objective"] == pytest.approx(math.log(20))
    assert summary["series"][1]["objective"] == pytest.approx(6.0)
    ranking = payload["configured_objective_ranking"]
    assert ranking["source"] == "configured_objective"
    assert ranking["best_candidate"]["run_id"] == "real_001"
    assert ranking["best_candidate"]["objective"] == pytest.approx(math.log(20))
    assert ranking["top_candidates"][0]["run_id"] == "real_001"
    assert ranking["top_candidates"][1]["run_id"] == "real_002"
    svg = (project_dir / payload["plots"]["all_evaluable_fom"]).read_text(
        encoding="utf-8"
    )
    assert "All Evaluable FoM" in svg
    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "Source: `configured_objective`" in markdown
    assert "Configured Objective Ranking" in markdown


def test_generate_optimizer_insight_report_respects_maximize_direction(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="feasible",
            objective=-0.25,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=-0.9,
        ),
    ]
    rows[0]["metrics"] = {"score": 0.25}
    rows[1]["metrics"] = {"score": 0.9}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    (project_dir / "config" / "metrics.yaml").write_text(
        """
schema_version: "1.0"
metrics:
  - name: score
    unit: ""
constraints: []
objective:
  direction: maximize
  expression: "score"
""".lstrip(),
        encoding="utf-8",
    )

    report = generate_optimizer_insight_report(project_dir)

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    summary = payload["all_evaluable_fom_summary"]
    assert summary["direction"] == "maximize"
    assert summary["best_run_id"] == "real_002"
    assert summary["best_fom"] == pytest.approx(0.9)
    assert summary["best_objective"] == pytest.approx(-0.9)
    ranking = payload["configured_objective_ranking"]
    assert ranking["direction"] == "maximize"
    assert ranking["best_candidate"]["run_id"] == "real_002"
    assert ranking["best_candidate"]["fom"] == pytest.approx(0.9)
    assert ranking["best_candidate"]["objective"] == pytest.approx(-0.9)


def test_generate_optimizer_insight_report_writes_bottleneck_weighted_plot(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=10.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=1.0,
        ),
    ]
    rows[0]["metrics"] = {
        "BW": 19e9 * (10**0.025),
        "MAX_GAIN": 4.25,
        "NF_3G": 11.95,
        "IIP3": 0.25,
        "P1DB": -1.75,
    }
    rows[1]["metrics"] = {
        "BW": 19e9 * (10**0.05),
        "MAX_GAIN": 4.5,
        "NF_3G": 11.9,
        "IIP3": 0.5,
        "P1DB": -1.5,
    }
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)

    report = generate_optimizer_insight_report(project_dir)

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    summary = payload["bottleneck_weighted_score_summary"]
    assert summary["sample_count"] == 2
    assert summary["best_run_id"] == "real_002"
    assert summary["series"][0]["weighted_score"] == pytest.approx(0.5)
    assert summary["series"][0]["bottleneck_score"] == pytest.approx(0.5)
    assert summary["series"][0]["combined_score"] == pytest.approx(0.5)
    assert payload["plots"]["bottleneck_weighted_score"] == (
        "reports/optimizer_visuals/bottleneck_weighted_score.svg"
    )
    svg = (
        project_dir / payload["plots"]["bottleneck_weighted_score"]
    ).read_text(encoding="utf-8")
    assert "Normalized Margin Bottleneck Plot" in svg
    assert "real_002" in svg
    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "Normalized Margin Bottleneck Plot" in markdown


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
