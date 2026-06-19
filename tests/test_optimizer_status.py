import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.openbox_backend import run_openbox_fake_optimization
from hermes_workflow.optimizer_status import summarize_optimizer_status
from tests.real_run_smoke_helpers import (
    advisor_batches,
    create_approved_real_project,
    default_metric_values,
)


runner = CliRunner()


def _patch_fake_metrics(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hermes_workflow.openbox_backend as _ob

    values = default_metric_values(project_dir)

    def _generic(_parameters: dict[str, str]) -> object:
        return type("_FakeObs", (), {"metrics": dict(values), "issues": []})()

    monkeypatch.setattr(_ob, "_fake_inverter_metrics", _generic)


class FakeAdvisorForStatus:
    def __init__(self, project_dir: Path) -> None:
        self._batches = advisor_batches(project_dir)

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def _write_fake_openbox_run(project_dir: Path) -> None:
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForStatus(project_dir),
    )


def test_summarize_optimizer_status_reads_closeout_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _patch_fake_metrics(project_dir, monkeypatch)
    _write_fake_openbox_run(project_dir)

    summary = summarize_optimizer_status(project_dir)

    assert summary.status == "pass"
    assert summary.decision in {"accept_best_observed", "continue_more_evals"}
    assert summary.confidence in {"low", "medium", "high"}
    assert summary.global_optimum_claim is False
    assert summary.best_observed_run_id is not None
    assert summary.evaluation_count == 4
    assert summary.status_counts
    assert summary.continuation_recommended in {True, False}
    assert summary.reports["effectiveness_audit"] == (
        "reports/optimizer_effectiveness_audit.json"
    )
    assert summary.reports["finalize"] == "reports/optimizer_finalize_report.json"
    assert summary.reports["insight_html"] == "reports/optimizer_insight_report.html"


def test_optimizer_status_cli_prints_supervisor_summary(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _write_fake_openbox_run(project_dir)

    result = runner.invoke(app, ["optimizer-status", str(project_dir)])

    assert result.exit_code == 0
    assert "optimizer status: pass" in result.output
    assert "decision:" in result.output
    assert "confidence:" in result.output
    assert "global optimum claim: false" in result.output
    assert "best observed:" in result.output
    assert "evaluations: 4" in result.output
    assert "status counts:" in result.output
    assert "continuation recommended:" in result.output
    assert "reports/optimizer_finalize_report.json" in result.output
    assert "insight_html: reports/optimizer_insight_report.html" in result.output


def test_optimizer_status_cli_fails_closed_when_finalize_fails(tmp_path: Path) -> None:
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

    result = runner.invoke(app, ["optimizer-status", str(project_dir)])

    assert result.exit_code == 1
    assert "optimizer status: fail" in result.output
    assert "optimizer run acceptance rejected" in result.output
