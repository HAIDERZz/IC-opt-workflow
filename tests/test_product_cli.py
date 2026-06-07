from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow import product_cli
from hermes_workflow.product_doctor import ProductDoctorCheck, ProductDoctorReport


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


def test_ic_opt_doctor_does_not_require_existing_cadence_env(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    calls: list[dict[str, object]] = []

    def fake_run_product_doctor(project: Path, **kwargs: object) -> object:
        calls.append({"project": project, **kwargs})
        return ProductDoctorReport(
            status="pass",
            project_dir=str(project),
            checks=[
                ProductDoctorCheck(
                    name="project_directory",
                    status="pass",
                    detail="project directory exists",
                )
            ],
            report_path=project / "reports" / "ic_opt_doctor_report.json",
        )

    monkeypatch.delenv(product_cli.CADENCE_CSHRC_ENV_VAR, raising=False)
    monkeypatch.setattr(
        product_cli,
        "USER_CADENCE_CSHRC",
        tmp_path / "missing_user_cadence_env.csh",
    )
    monkeypatch.setattr(product_cli, "run_product_doctor", fake_run_product_doctor)

    result = runner.invoke(product_cli.app, [str(project_dir), "--doctor"])

    assert result.exit_code == 0, result.output
    assert calls == [{"project": project_dir, "cadence_cshrc": None}]
    assert "ic-opt doctor pass" in result.output
    assert "PASS project_directory" in result.output


def test_ic_opt_doctor_exits_nonzero_for_failed_report(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    def fake_run_product_doctor(project: Path, **_kwargs: object) -> object:
        return ProductDoctorReport(
            status="fail",
            project_dir=str(project),
            checks=[
                ProductDoctorCheck(
                    name="cadence_cshrc",
                    status="fail",
                    detail="cadence_env.csh was not found",
                )
            ],
            issues=["cadence_cshrc: cadence_env.csh was not found"],
            report_path=project / "reports" / "ic_opt_doctor_report.json",
        )

    monkeypatch.setattr(product_cli, "run_product_doctor", fake_run_product_doctor)

    result = runner.invoke(product_cli.app, [str(project_dir), "--doctor"])

    assert result.exit_code == 1
    assert "ic-opt doctor fail" in result.output
    assert "FAIL cadence_cshrc" in result.output


def test_ic_opt_continue_runs_openbox_continuation_and_closeout(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text("{}\n", encoding="utf-8")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run_openbox_real_optimization(project: Path, **kwargs: object) -> object:
        calls.append(("run", {"project": project, **kwargs}))
        return SimpleNamespace(
            evaluation_count=140,
            report_path=project / "reports" / "optimizer_run_report.json",
            evaluations_path=project / "reports" / "optimizer_evaluations.jsonl",
        )

    def fake_status(name: str, status: str) -> object:
        def _fake(project: Path) -> object:
            calls.append((name, {"project": project}))
            return SimpleNamespace(status=status)

        return _fake

    def fake_decision(project: Path) -> object:
        calls.append(("decision", {"project": project}))
        return SimpleNamespace(status="pass", recommended_run_id="real_140")

    monkeypatch.setattr(
        product_cli,
        "run_openbox_real_optimization",
        fake_run_openbox_real_optimization,
    )
    monkeypatch.setattr(product_cli, "check_optimizer_run", fake_status("check", "accepted"))
    monkeypatch.setattr(product_cli, "summarize_optimizer_run", fake_status("summary", "pass"))
    monkeypatch.setattr(product_cli, "finalize_optimizer_run", fake_status("finalize", "pass"))
    monkeypatch.setattr(
        product_cli,
        "generate_optimizer_insight_report",
        fake_status("insight", "pass"),
    )
    monkeypatch.setattr(product_cli, "generate_optimizer_decision_report", fake_decision)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--continue",
            "40",
            "--batch-size",
            "10",
            "--parallel-jobs",
            "4",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls[0] == (
        "run",
        {
            "project": project_dir,
            "max_evals": None,
            "additional_evals": 40,
            "continue_from_existing": True,
            "batch_size": 10,
            "parallel_jobs": 4,
            "cadence_cshrc": cadence_cshrc,
            "surrogate_type": "prf",
            "acq_type": "eic",
            "acq_optimizer_type": "local_random",
        },
    )
    assert [name for name, _payload in calls[1:]] == [
        "check",
        "summary",
        "finalize",
        "insight",
        "decision",
    ]
    assert "optimizer continuation completed: 140 cumulative evaluations" in result.output
    assert "recommended: real_140" in result.output
    assert "decision: reports/optimizer_decision_report.md" in result.output


def test_ic_opt_continue_dry_orchestration_builds_continuation_task(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text("{}\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_build_optimizer_execution_task_package(
        project: Path, **kwargs: object
    ) -> object:
        calls.append({"project": project, **kwargs})
        return SimpleNamespace(
            task_path=project / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md",
            manifest_path=(
                project / "execution_package" / "optimizer_execution_manifest.json"
            ),
        )

    monkeypatch.setattr(
        product_cli,
        "build_optimizer_execution_task_package",
        fake_build_optimizer_execution_task_package,
    )

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--continue", "40", "--dry-orchestration"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "project": project_dir,
            "max_evals": None,
            "additional_evals": 40,
            "cadence_cshrc": cadence_cshrc,
            "parallel": True,
            "optimizer_backend": "openbox",
            "continuation": True,
        }
    ]
    assert "optimizer continuation orchestration completed" in result.output
    assert "manifest: execution_package/optimizer_execution_manifest.json" in result.output


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
