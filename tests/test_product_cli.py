from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow import product_cli


runner = CliRunner()


def test_ic_opt_invokes_optimizer_flow(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
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
            "execution_agent": "direct",
        }
    ]
    assert "optimizer flow completed" in result.output
    assert "report: reports/optimizer_flow_run_report.json" in result.output
    assert "stopped before: run-openbox-real" in result.output


def test_ic_opt_explicit_cadence_env_overrides_project_file(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "cadence_env.csh").write_text("# project\n", encoding="utf-8")
    explicit_cadence_cshrc = tmp_path / "explicit_env.csh"
    explicit_cadence_cshrc.write_text("# explicit\n", encoding="utf-8")
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
            "--cadence-cshrc",
            str(explicit_cadence_cshrc),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["cadence_cshrc"] == explicit_cadence_cshrc
    assert calls[0]["execution_agent"] == "direct"


def test_ic_opt_uses_cadence_env_variable(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "env_cadence.csh"
    cadence_cshrc.write_text("# env\n", encoding="utf-8")
    monkeypatch.setenv(product_cli.CADENCE_CSHRC_ENV_VAR, str(cadence_cshrc))
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
        [str(project_dir), "--real", "--dry-orchestration"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["cadence_cshrc"] == cadence_cshrc
    assert calls[0]["execution_agent"] == "direct"


def test_ic_opt_wires_claude_execution_agent(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
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
            stopped_before=None,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--execution-agent", "claude"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["execution_agent"] == "claude"
    assert "recommended: real_001" in result.output


def test_ic_opt_reports_missing_cadence_env(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.delenv(product_cli.CADENCE_CSHRC_ENV_VAR, raising=False)
    monkeypatch.setattr(
        product_cli,
        "USER_CADENCE_CSHRC",
        tmp_path / "missing_user_cadence_env.csh",
    )

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--dry-orchestration"],
    )

    assert result.exit_code == 1
    assert "Cadence cshrc was not found" in result.output
    assert "--cadence-cshrc" in result.output


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
