import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from tests.test_optimizer_completion import _trace_row, _write_accepted_optimizer_project


runner = CliRunner()


def _write_mixer_project(tmp_path: Path) -> Path:
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
            objective=9.0,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="feasible",
            objective=8.0,
        ),
    ]
    rows[0]["metrics"] = {
        "BW": 18.0e9,
        "MAX_GAIN": 4.1,
        "NF_3G": 12.2,
        "IIP3": -0.2,
        "P1DB": -2.5,
    }
    rows[1]["metrics"] = {
        "BW": 22.0e9,
        "MAX_GAIN": 4.7,
        "NF_3G": 11.92,
        "IIP3": 0.2,
        "P1DB": -0.5,
    }
    rows[2]["metrics"] = {
        "BW": 20.2e9,
        "MAX_GAIN": 4.9,
        "NF_3G": 11.90,
        "IIP3": 0.2,
        "P1DB": -1.0,
    }
    rows[1]["parameters"] = {"F": "20", "W": "1.4u", "L": "30n", "VB_LO": "310m"}
    rows[2]["parameters"] = {"F": "24", "W": "1.2u", "L": "30n", "VB_LO": "250m"}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    (project_dir / "config" / "metrics.yaml").write_text(
        """
schema_version: "1.0"
metrics:
  - name: BW
    unit: Hz
  - name: MAX_GAIN
    unit: dB
  - name: NF_3G
    unit: dB
  - name: IIP3
    unit: dBm
  - name: P1DB
    unit: dBm
constraints:
  - metric: BW
    op: gt
    value: "19e9 Hz"
  - metric: MAX_GAIN
    op: gt
    value: "4 dB"
  - metric: NF_3G
    op: lt
    value: "12 dB"
objective:
  direction: minimize
  expression: "-(0.7*min(max(0,min(1,IIP3/0.5)), max(0,min(1,(12-NF_3G)/0.1))) + 0.3*max(0,min(1,(P1DB+2)/0.5)))"
""".lstrip(),
        encoding="utf-8",
    )
    return project_dir


def _write_process_corner_aggregation_report(
    project_dir: Path,
    *,
    run_id: str,
    status: str,
    constraint_policy: str = "all_corners",
    objective_policy: str = "worst_case",
    selected_corner: str = "ff",
    worst_corner: str | None = None,
    corner_objectives: dict[str, float] | None = None,
    corner_status_counts: dict[str, int] | None = None,
    corner_metrics: dict[str, dict[str, float]] | None = None,
) -> None:
    payload = {
        "schema_version": "1.0",
        "status": status,
        "run_id": run_id,
        "constraint_policy": constraint_policy,
        "objective_policy": objective_policy,
        "selected_corner": selected_corner,
        "worst_corner": worst_corner or selected_corner,
        "corner_objectives": corner_objectives or {},
        "corner_status_counts": corner_status_counts or {},
        "corner_metrics": corner_metrics or {},
        "child_statuses": [],
    }
    report_path = (
        project_dir
        / "runs"
        / "real"
        / run_id
        / "multi_testbench_aggregation_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_generate_optimizer_decision_report_writes_supervisor_decision(
    tmp_path: Path,
) -> None:
    project_dir = _write_mixer_project(tmp_path)

    report = generate_optimizer_decision_report(project_dir)

    assert report.status == "pass"
    assert report.recommended_run_id == "real_002"
    assert report.recommendation_basis == "configured_objective_ranking"
    assert report.global_optimum_claim is False
    assert report.recommended_candidate["parameters"]["F"] == "20"
    assert report.bottleneck["metric"] == "IIP3"
    assert report.recommended_action == "accept_best_observed_or_continue"
    assert report.report_path == project_dir / "reports/optimizer_decision_report.json"
    assert report.markdown_path == project_dir / "reports/optimizer_decision_report.md"

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["recommended_run_id"] == "real_002"
    assert payload["bottleneck"]["metric"] == "IIP3"
    assert payload["boundaries"]["best_candidate_scope"] == "best_observed"

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert "# Optimizer Decision Report" in markdown
    assert "real_002" in markdown
    assert "Global optimum claim: false" in markdown
    assert "IIP3" in markdown


def test_decide_optimizer_run_cli_writes_report(tmp_path: Path) -> None:
    project_dir = _write_mixer_project(tmp_path)

    result = runner.invoke(app, ["decide-optimizer-run", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "optimizer decision report written" in result.output
    assert "recommended: real_002" in result.output
    assert (project_dir / "reports/optimizer_decision_report.json").exists()


def test_generate_optimizer_decision_report_prefers_feasible_candidate_over_configured_failure(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=3.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=1.0,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="feasible",
            objective=2.0,
        ),
    ]
    rows[0]["metrics"] = {
        "BW": 18.0e9,
        "MAX_GAIN": 5.0,
        "NF_3G": 11.5,
        "IIP3": 1.0,
        "P1DB": -1.0,
    }
    rows[1]["metrics"] = {
        "BW": 22.0e9,
        "MAX_GAIN": 4.7,
        "NF_3G": 11.9,
        "IIP3": 0.5,
        "P1DB": -0.5,
    }
    rows[2]["metrics"] = {
        "BW": 21.0e9,
        "MAX_GAIN": 4.5,
        "NF_3G": 11.8,
        "IIP3": 0.4,
        "P1DB": -0.8,
    }
    rows[1]["parameters"] = {"F": "20", "W": "1.4u", "L": "30n", "VB_LO": "310m"}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    (project_dir / "config" / "metrics.yaml").write_text(
        """
schema_version: "1.0"
metrics:
  - name: BW
    unit: Hz
constraints:
  - metric: BW
    op: gt
    value: "19e9 Hz"
objective:
  direction: minimize
  expression: "BW"
""".lstrip(),
        encoding="utf-8",
    )

    report = generate_optimizer_decision_report(project_dir)

    assert report.status == "pass"
    assert report.recommended_run_id == "real_002"
    assert report.recommended_candidate["status"] == "feasible"
    assert report.recommendation_basis == "stored_best_observed_feasible_fallback"
    assert report.recommended_action == "accept_best_observed_or_continue"
    assert any(
        "configured objective best candidate is not feasible" in warning
        for warning in report.warnings
    )


def test_generate_optimizer_decision_report_describes_worst_case_corner_basis(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=3.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=1.0,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="feasible",
            objective=2.0,
        ),
    ]
    rows[1]["parameters"] = {"F": "20", "W": "1.4u", "L": "30n", "VB_LO": "310m"}
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)
    _write_process_corner_aggregation_report(
        project_dir,
        run_id="real_002",
        status="succeeded",
        selected_corner="ff",
        worst_corner="ff",
        corner_objectives={"tt": 1.0, "ff": 2.5, "ss": 1.5},
        corner_status_counts={"succeeded": 3},
        corner_metrics={
            "tt": {"MAX_GAIN": 8.0, "NF_3G": 11.9},
            "ff": {"MAX_GAIN": 4.0, "NF_3G": 12.4},
            "ss": {"MAX_GAIN": 9.0, "NF_3G": 11.7},
        },
    )

    report = generate_optimizer_decision_report(project_dir)

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["process_corner_summary"]["objective_policy"] == "worst_case"
    assert payload["process_corner_summary"]["worst_corner"] == "ff"

    markdown = report.markdown_path.read_text(encoding="utf-8")
    assert (
        "best observed feasible candidate under worst_case corner objective"
        in markdown
    )
    assert "- Selected corner: `ff`" in markdown
    assert "- Worst corner: `ff`" in markdown
