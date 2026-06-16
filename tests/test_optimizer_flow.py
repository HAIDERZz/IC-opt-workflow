import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.execution_agent_handoff import ExecutionAgentHandoffReport
from hermes_workflow.optimizer_flow import OptimizerFlowServices, optimize_project
from hermes_workflow.package import create_project_from_template

runner = CliRunner()


def _status(value: str) -> SimpleNamespace:
    return SimpleNamespace(value=value)


def _set_optimizer_strategy(project_dir: Path, strategy: str) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_text = optimizer_path.read_text(encoding="utf-8").replace(
        "  algorithm: turbo",
        f"  algorithm: turbo\n  strategy: {strategy}",
        1,
    )
    optimizer_path.write_text(optimizer_text, encoding="utf-8")


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
        run_product_doctor=lambda _project, **_kwargs: record(
            "doctor",
            SimpleNamespace(status="pass", issues=[]),
        ),
    )


def _handoff_report(project_dir: Path) -> ExecutionAgentHandoffReport:
    report_path = project_dir / "reports" / "execution_agent_handoff_report.json"
    transcript_path = project_dir / "reports" / "execution_agent_handoff_transcript.txt"
    return ExecutionAgentHandoffReport(
        status="pass",
        project_dir=str(project_dir),
        execution_agent="claude",
        task_path=project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md",
        manifest_path=project_dir / "execution_package" / "optimizer_execution_manifest.json",
        command=["claude", "-p", "--dangerously-skip-permissions", "<prompt>"],
        transcript_path=transcript_path,
        report_path=report_path,
        returncode=0,
        started_at_utc="2026-06-07T00:00:00Z",
        finished_at_utc="2026-06-07T00:00:01Z",
        issues=[],
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
        "doctor",
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


def test_optimize_project_dry_orchestration_reports_turbo_strategy_backend(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# cadence", encoding="utf-8")
    calls: list[str] = []

    report = optimize_project(
        project_dir,
        real=True,
        dry_orchestration=True,
        max_evals=10,
        batch_size=2,
        parallel_jobs=2,
        cadence_cshrc=cadence_cshrc,
        strategy="turbo_trust_region",
        services=_services(project_dir, calls),
    )

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert report.backend == "native_turbo"
    assert report.stopped_before == "run-native-turbo-real"
    assert payload["backend"] == "native_turbo"
    assert payload["stopped_before"] == "run-native-turbo-real"


def test_optimize_project_dry_orchestration_uses_config_turbo_strategy_backend(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    create_project_from_template(project_dir)
    _set_optimizer_strategy(project_dir, "turbo_trust_region")
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# cadence", encoding="utf-8")
    calls: list[str] = []

    report = optimize_project(
        project_dir,
        real=True,
        dry_orchestration=True,
        max_evals=10,
        batch_size=2,
        parallel_jobs=2,
        cadence_cshrc=cadence_cshrc,
        services=_services(project_dir, calls),
    )

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert report.backend == "native_turbo"
    assert report.stopped_before == "run-native-turbo-real"
    assert payload["backend"] == "native_turbo"
    assert payload["stopped_before"] == "run-native-turbo-real"


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
        "doctor",
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


def test_optimize_project_claude_handoff_replaces_direct_optimizer_execution(
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
        execution_agent="claude",
        services=_services(project_dir, calls),
        dispatch_execution_agent=lambda project, **kwargs: record_handoff(
            calls, project, **kwargs
        ),
    )

    assert calls == [
        "doctor",
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
        "execution-agent-handoff",
        "check-optimizer-run",
        "summarize-optimizer-run",
        "finalize-optimizer-run",
        "visualize-optimizer-run",
        "decide-optimizer-run",
    ]
    assert report.status == "pass"
    assert report.execution_agent == "claude"
    assert report.handoff_report_path == (
        project_dir / "reports" / "execution_agent_handoff_report.json"
    )
    assert report.recommended_run_id == "real_002"


def test_optimize_project_turbo_strategy_routes_to_native_turbo(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# cadence", encoding="utf-8")
    calls: list[str] = []
    native_calls: list[dict[str, object]] = []
    package_calls: list[dict[str, object]] = []

    def fake_run_batch_native_turbo_optimization(
        project_dir_arg: Path,
        **kwargs: object,
    ) -> object:
        native_calls.append(
            {
                "project_dir": project_dir_arg,
                "max_evals": kwargs["max_evals"],
                "has_batch_size": "batch_size" in kwargs,
                "parallel_jobs": kwargs["parallel_jobs"],
                "cadence_cshrc": kwargs["cadence_cshrc"],
            }
        )
        return SimpleNamespace(
            evaluation_count=7,
            report_path=project_dir_arg / "reports" / "native_turbo_optimizer_report.json",
        )

    services = replace(
        _services(project_dir, calls),
        run_batch_native_turbo_optimization=fake_run_batch_native_turbo_optimization,
        build_optimizer_execution_task_package=lambda _project, **kwargs: (
            package_calls.append(kwargs)
            or SimpleNamespace(
                task_path=project_dir
                / "execution_package"
                / "OPTIMIZER_EXECUTION_TASK.md",
                manifest_path=project_dir
                / "execution_package"
                / "optimizer_execution_manifest.json",
                payload={},
            )
        ),
    )
    report = optimize_project(
        project_dir,
        real=True,
        max_evals=7,
        batch_size=3,
        parallel_jobs=2,
        cadence_cshrc=cadence_cshrc,
        strategy="turbo_trust_region",
        services=services,
    )

    assert native_calls == [
            {
                "project_dir": project_dir,
                "max_evals": 7,
                "has_batch_size": False,
                "parallel_jobs": 2,
                "cadence_cshrc": cadence_cshrc,
            }
    ]
    assert "run-openbox-real" not in calls
    assert report.status == "pass"
    assert package_calls[0]["optimizer_backend"] == "native_turbo"
    assert package_calls[0]["strategy"] == "turbo_trust_region"
    assert report.backend == "native_turbo"
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["backend"] == "native_turbo"


def record_handoff(calls: list[str], project: Path, **kwargs) -> ExecutionAgentHandoffReport:
    calls.append("execution-agent-handoff")
    assert kwargs["execution_agent"] == "claude"
    return _handoff_report(project)


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
        assert kwargs["max_evals"] is None
        assert kwargs["batch_size"] is None
        assert kwargs["parallel_jobs"] is None
        assert kwargs["cadence_cshrc"] == cadence_cshrc
        assert kwargs["execution_agent"] == "direct"
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
            "--cadence-cshrc",
            str(cadence_cshrc),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "optimizer flow completed" in result.output
    assert "stopped before: run-openbox-real" in result.output


def test_optimize_project_openbox_strategy_ignores_legacy_algorithm_for_routing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# cadence", encoding="utf-8")
    calls: list[str] = []
    openbox_calls: list[dict[str, object]] = []

    def fail_native_turbo(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("openbox strategy must not route to native TuRBO")

    def fake_openbox(project_dir_arg: Path, **kwargs: object) -> object:
        calls.append("run-openbox-real")
        openbox_calls.append(
            {
                "project_dir": project_dir_arg,
                "strategy": kwargs["strategy"],
                "max_evals": kwargs["max_evals"],
            }
        )
        return SimpleNamespace(
            evaluation_count=5,
            report_path=project_dir_arg / "reports" / "openbox_optimizer_report.json",
            evaluations_path=(
                project_dir_arg / "reports" / "openbox_optimizer_evaluations.jsonl"
            ),
        )

    monkeypatch.setattr(
        "hermes_workflow.optimizer_flow.run_batch_native_turbo_optimization",
        fail_native_turbo,
        raising=False,
    )
    services = replace(
        _services(project_dir, calls),
        run_openbox_real_optimization=fake_openbox,
    )

    report = optimize_project(
        project_dir,
        real=True,
        max_evals=5,
        batch_size=2,
        parallel_jobs=2,
        cadence_cshrc=cadence_cshrc,
        strategy="random_baseline",
        services=services,
    )

    assert report.status == "pass"
    assert openbox_calls == [
        {
            "project_dir": project_dir,
            "strategy": "random_baseline",
            "max_evals": 5,
        }
    ]
    assert "run-openbox-real" in calls
    assert "run-native-turbo-real" not in calls
