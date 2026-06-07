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
                {"FN": 2, "WN": 0.2, "FP": 3, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "FP": 5, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "FP": 7, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "FP": 9, "WP": 2.2},
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
