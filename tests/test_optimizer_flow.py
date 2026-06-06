import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_flow import OptimizerFlowServices, optimize_project

runner = CliRunner()


def _status(value: str) -> SimpleNamespace:
    return SimpleNamespace(value=value)


def _services(project_dir: Path, calls: list[str]) -> OptimizerFlowServices:
    def record(name: str, result: object) -> object:
        calls.append(name)
        return result

    return OptimizerFlowServices(
        check_requirement=lambda _project: record(
            "check-requirement",
            SimpleNamespace(status="pass", issues=[]),
        ),
        prepare_from_requirement=lambda _project: record(
            "prepare-from-requirement",
            SimpleNamespace(status="pass", issues=[]),
        ),
        validate_project_files=lambda _project: record(
            "validate",
            SimpleNamespace(ok=True, issues=[]),
        ),
        check_project_ready=lambda _project: record(
            "check-project-ready",
            SimpleNamespace(status="pass", issues=[]),
        ),
        build_execution_package=lambda _project: record(
            "package",
            SimpleNamespace(path=project_dir / "execution_package" / "manifest.json"),
        ),
        prepare_netlist=lambda _project: record(
            "prepare-netlist",
            SimpleNamespace(status=_status("pass"), issues=[]),
        ),
        run_dry_run=lambda _project: record(
            "dry-run",
            SimpleNamespace(status=_status("pass"), issues=[]),
        ),
        write_preflight_health=lambda _project: record(
            "preflight-health",
            SimpleNamespace(status=_status("healthy"), issues=[]),
        ),
        decide_first_real_run=lambda _project: record(
            "approve",
            {"decision": "approve_first_real_run"},
        ),
        build_optimizer_execution_task_package=lambda _project, **_kwargs: record(
            "package-optimizer-task",
            SimpleNamespace(
                task_path=project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md",
                manifest_path=(
                    project_dir
                    / "execution_package"
                    / "optimizer_execution_manifest.json"
                ),
                payload={},
            ),
        ),
        run_openbox_real_optimization=lambda _project, **_kwargs: record(
            "run-openbox-real",
            SimpleNamespace(
                evaluation_count=100,
                report_path=project_dir / "reports" / "openbox_optimizer_report.json",
                evaluations_path=(
                    project_dir / "reports" / "openbox_optimizer_evaluations.jsonl"
                ),
            ),
        ),
        check_optimizer_run=lambda _project: record(
            "check-optimizer-run",
            SimpleNamespace(status="accepted", issues=[]),
        ),
        summarize_optimizer_run=lambda _project: record(
            "summarize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        finalize_optimizer_run=lambda _project: record(
            "finalize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        generate_optimizer_insight_report=lambda _project: record(
            "visualize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        generate_optimizer_decision_report=lambda _project: record(
            "decide-optimizer-run",
            SimpleNamespace(
                status="pass",
                recommended_run_id="real_002",
                recommended_action="accept_best_observed_or_continue",
                issues=[],
            ),
        ),
    )


def test_optimize_project_dry_orchestration_stops_before_real_optimizer(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []

    report = optimize_project(
        project_dir,
        real=True,
        dry_orchestration=True,
        max_evals=100,
        batch_size=10,
        parallel_jobs=10,
        cadence_cshrc=cadence_cshrc,
        services=_services(project_dir, calls),
    )

    assert calls == [
        "check-requirement",
        "prepare-from-requirement",
        "validate",
        "check-project-ready",
        "package",
        "prepare-netlist",
        "dry-run",
        "preflight-health",
        "approve",
        "package-optimizer-task",
    ]
    assert report.status == "pass"
    assert report.stopped_before == "run-openbox-real"
    assert report.user_decision_required is False
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["dry_orchestration"] is True
    assert payload["steps"][-1]["name"] == "package-optimizer-task"


def test_optimize_project_real_runs_closeout_without_recording_user_acceptance(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []

    report = optimize_project(
        project_dir,
        real=True,
        dry_orchestration=False,
        max_evals=100,
        batch_size=10,
        parallel_jobs=10,
        cadence_cshrc=cadence_cshrc,
        services=_services(project_dir, calls),
    )

    assert calls == [
        "check-requirement",
        "prepare-from-requirement",
        "validate",
        "check-project-ready",
        "package",
        "prepare-netlist",
        "dry-run",
        "preflight-health",
        "approve",
        "package-optimizer-task",
        "run-openbox-real",
        "check-optimizer-run",
        "summarize-optimizer-run",
        "finalize-optimizer-run",
        "visualize-optimizer-run",
        "decide-optimizer-run",
    ]
    assert report.status == "pass"
    assert report.recommended_run_id == "real_002"
    assert report.user_decision_required is True
    assert report.stopped_before is None


def test_optimize_cli_wires_real_dry_orchestration_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.cli as cli_module

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    def fake_optimize(project_dir_arg: Path, **kwargs) -> object:
        assert project_dir_arg == project_dir
        assert kwargs["real"] is True
        assert kwargs["dry_orchestration"] is True
        assert kwargs["max_evals"] == 7
        assert kwargs["batch_size"] == 3
        assert kwargs["parallel_jobs"] == 2
        assert kwargs["cadence_cshrc"] == cadence_cshrc
        return SimpleNamespace(
            status="pass",
            report_path=project_dir / "reports" / "optimizer_flow_run_report.json",
            stopped_before="run-openbox-real",
            recommended_run_id=None,
            user_decision_required=False,
        )

    monkeypatch.setattr(cli_module, "optimize_project", fake_optimize)
    result = runner.invoke(
        app,
        [
            "optimize",
            str(project_dir),
            "--real",
            "--dry-orchestration",
            "--max-evals",
            "7",
            "--batch-size",
            "3",
            "--parallel-jobs",
            "2",
            "--cadence-cshrc",
            str(cadence_cshrc),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "optimizer flow completed" in result.output
    assert "stopped before: run-openbox-real" in result.output
