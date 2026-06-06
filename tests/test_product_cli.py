from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow import product_cli


runner = CliRunner()


def test_ic_opt_invokes_optimizer_flow(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            stopped_before="run-openbox-real",
            recommended_run_id=None,
            user_decision_required=False,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--dry-orchestration",
            "--max-evals",
            "100",
            "--batch-size",
            "10",
            "--parallel-jobs",
            "10",
            "--cadence-cshrc",
            str(cadence_cshrc),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "project": project_dir,
            "real": True,
            "dry_orchestration": True,
            "max_evals": 100,
            "batch_size": 10,
            "parallel_jobs": 10,
            "cadence_cshrc": cadence_cshrc,
        }
    ]
    assert "optimizer flow completed" in result.output
    assert "report: reports/optimizer_flow_run_report.json" in result.output
    assert "stopped before: run-openbox-real" in result.output


def test_ic_opt_reports_optimizer_flow_failure(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    def fake_optimize_project(_project: Path, **_kwargs: object) -> object:
        raise ValueError("check-requirement failed: missing opt_requirement.md")

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--cadence-cshrc",
            str(cadence_cshrc),
        ],
    )

    assert result.exit_code == 1
    assert "check-requirement failed: missing opt_requirement.md" in result.output
