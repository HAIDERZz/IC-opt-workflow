import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.openbox_backend import run_openbox_fake_optimization
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from tests.real_run_smoke_helpers import create_approved_real_project


runner = CliRunner()


class FakeAdvisorForFinalize:
    def __init__(self) -> None:
        self._batches = [
            [
                {"F": 22, "W": 0.8, "L": 40, "VB_LO": 300},
                {"F": 24, "W": 1.0, "L": 30, "VB_LO": 340},
            ],
            [
                {"F": 26, "W": 1.2, "L": 40, "VB_LO": 360},
                {"F": 28, "W": 0.6, "L": 30, "VB_LO": 380},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def _write_fake_openbox_run(project_dir: Path) -> None:
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForFinalize(),
    )


def test_finalize_optimizer_run_writes_closeout_report(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _write_fake_openbox_run(project_dir)

    report = finalize_optimizer_run(project_dir)

    assert report.status == "pass"
    assert report.acceptance_status == "accepted"
    assert report.completion_status == "pass"
    assert report.insight_status == "pass"
    assert report.decision in {"accept_best_observed", "continue_more_evals"}
    assert report.best_observed_run_id is not None
    assert report.report_path == project_dir / "reports/optimizer_finalize_report.json"

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["reports"] == {
        "acceptance": "reports/optimizer_run_acceptance_report.json",
        "completion": "reports/optimizer_completion_report.json",
        "insight": "reports/optimizer_insight_report.json",
    }
    assert (project_dir / "reports/optimizer_completion_report.json").exists()
    assert (project_dir / "reports/optimizer_insight_report.json").exists()


def test_finalize_optimizer_run_fails_closed_when_acceptance_rejects(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bad_run"
    (project_dir / "reports").mkdir(parents=True)
    (project_dir / "reports/optimizer_run_report.json").write_text(
        json.dumps(
            {
                "evaluation_count": 1,
                "schema_version": "1.0",
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "reports/optimizer_evaluations.jsonl").write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "objective": 1.0,
                "parameters": {"FN": "2"},
                "run_id": "real_001",
                "status": "feasible",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = finalize_optimizer_run(project_dir)

    assert report.status == "fail"
    assert report.acceptance_status == "rejected"
    assert report.completion_status == "not_run"
    assert report.insight_status == "not_run"
    assert "optimizer run acceptance rejected" in report.issues
    assert (project_dir / "reports/optimizer_finalize_report.json").exists()


def test_finalize_optimizer_run_cli(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _write_fake_openbox_run(project_dir)

    result = runner.invoke(app, ["finalize-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "optimizer finalization passed" in result.output
    assert "decision:" in result.output
    assert "reports/optimizer_finalize_report.json" in result.output
