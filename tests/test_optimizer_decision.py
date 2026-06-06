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
