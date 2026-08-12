import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_flow import OptimizerFlowServices, optimize_project
from tests.project_factory import create_generic_project

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
        check_optimizer_run=lambda _project, **_kwargs: record(
            "check-optimizer-run",
            SimpleNamespace(status="accepted", issues=[]),
        ),
        summarize_optimizer_run=lambda _project, **_kwargs: record(
            "summarize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        finalize_optimizer_run=lambda _project, **_kwargs: record(
            "finalize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        generate_optimizer_insight_report=lambda _project, **_kwargs: record(
            "visualize-optimizer-run",
            SimpleNamespace(status="pass", issues=[]),
        ),
        generate_optimizer_decision_report=lambda _project, **_kwargs: record(
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


@pytest.mark.parametrize("max_evals", [0, -1])
def test_optimize_project_rejects_non_positive_max_evals_before_doctor(
    tmp_path: Path,
    max_evals: int,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []

    with pytest.raises(ValueError, match="max_evals must be >= 1"):
        optimize_project(
            project_dir,
            real=True,
            max_evals=max_evals,
            cadence_cshrc=cadence_cshrc,
            services=_services(project_dir, calls),
        )

    assert calls == []
    payload = json.loads(
        (project_dir / "reports" / "optimizer_flow_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "fail"
    assert payload["issues"] == ["max_evals must be >= 1"]
    assert payload["steps"] == []


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
        "doctor",
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


def test_optimize_project_rejects_fix_run_requirement_before_preparation(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []
    services = replace(
        _services(project_dir, calls),
        check_requirement=lambda _project: (
            calls.append("check-requirement")
            or SimpleNamespace(
                status="pass",
                issues=[],
                workflow_mode="fix_run",
            )
        ),
    )

    with pytest.raises(
        ValueError,
        match="optimize requires workflow mode 'optimize'",
    ):
        optimize_project(
            project_dir,
            real=True,
            cadence_cshrc=cadence_cshrc,
            services=services,
        )

    assert calls == ["check-requirement"]


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
    project_dir = create_generic_project(tmp_path)
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
        "check-requirement",
        "doctor",
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


def test_fresh_native_closeout_requires_current_backend_from_flow(
    tmp_path: Path,
) -> None:
    """Stale neutral OpenBox artifacts must not satisfy a fresh native closeout."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# cadence", encoding="utf-8")
    calls: list[str] = []
    consumers: list[tuple[str, str]] = []

    def closeout_consumer(name: str, status: str):
        def consume(
            _project: Path,
            *,
            expected_backend: str,
        ) -> SimpleNamespace:
            consumers.append((name, expected_backend))
            if name == "decide":
                return SimpleNamespace(
                    status=status,
                    recommended_run_id="real_007",
                    recommended_action="stop_for_user_review",
                    issues=[],
                )
            return SimpleNamespace(status=status, issues=[])

        return consume

    services = replace(
        _services(project_dir, calls),
        run_batch_native_turbo_optimization=lambda _project, **_kwargs: (
            SimpleNamespace(evaluation_count=7)
        ),
        check_optimizer_run=closeout_consumer("check", "accepted"),
        summarize_optimizer_run=closeout_consumer("summarize", "pass"),
        finalize_optimizer_run=closeout_consumer("finalize", "pass"),
        generate_optimizer_insight_report=closeout_consumer("insight", "pass"),
        generate_optimizer_decision_report=closeout_consumer("decide", "pass"),
    )

    report = optimize_project(
        project_dir,
        real=True,
        max_evals=7,
        batch_size=2,
        parallel_jobs=2,
        cadence_cshrc=cadence_cshrc,
        strategy="turbo_trust_region",
        services=services,
    )

    assert report.status == "pass"
    assert consumers == [
        ("check", "native_turbo"),
        ("summarize", "native_turbo"),
        ("finalize", "native_turbo"),
        ("insight", "native_turbo"),
        ("decide", "native_turbo"),
    ]


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
