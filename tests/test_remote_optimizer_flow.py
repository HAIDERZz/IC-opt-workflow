from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
import yaml

from hermes_workflow.remote_optimizer_flow import optimize_remote_project
from hermes_workflow.remote_project import RemoteProjectRef
from tests.project_factory import create_generic_project


def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _create_remote_optimizer_project(
    tmp_path: Path,
    *,
    name: str = "remote_optimizer_project",
    **kwargs: object,
) -> Path:
    return create_generic_project(tmp_path, name=name, **kwargs)


def _set_optimizer_strategy(project_dir: Path, strategy: str, algorithm: str) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    payload["optimizer"]["algorithm"] = algorithm
    payload["optimizer"]["strategy"] = strategy
    _write_yaml(optimizer_path, payload)


def _passed_remote_doctor_report() -> SimpleNamespace:
    """Represent a doctor report produced earlier in the same attempt."""
    return SimpleNamespace(
        status="pass",
        workflow_mode="optimize",
        issues=[],
    )


def test_continuation_closeout_propagates_native_backend_to_every_consumer(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import run_continuation_closeout

    project_dir = tmp_path / "project"
    calls: list[tuple[str, str | None]] = []

    def optimizer(project: Path) -> SimpleNamespace:
        assert project == project_dir
        calls.append(("optimizer", None))
        return SimpleNamespace(status="completed")

    def consumer(
        name: str,
        status: str,
    ):
        def invoke(
            project: Path,
            *,
            expected_backend: str | None = None,
        ) -> SimpleNamespace:
            assert project == project_dir
            calls.append((name, expected_backend))
            if name == "decision":
                return SimpleNamespace(
                    status=status,
                    recommended_run_id="real_007",
                    recommended_action="accept_best_observed_or_continue",
                )
            return SimpleNamespace(status=status)

        return invoke

    report = run_continuation_closeout(
        project_dir,
        optimizer_fn=optimizer,
        backend="native_turbo",
        run_step_name="run-native-turbo-real",
        check_fn=consumer("check", "accepted"),
        summarize_fn=consumer("summarize", "pass"),
        finalize_fn=consumer("finalize", "pass"),
        insight_fn=consumer("insight", "pass"),
        decision_fn=consumer("decision", "pass"),
        additional_evals=2,
        batch_size=1,
        parallel_jobs=1,
    )

    assert report.status == "pass"
    assert report.backend == "native_turbo"
    assert calls == [
        ("check", "native_turbo"),
        ("optimizer", None),
        ("check", "native_turbo"),
        ("summarize", "native_turbo"),
        ("finalize", "native_turbo"),
        ("insight", "native_turbo"),
        ("decision", "native_turbo"),
    ]


def test_native_continuation_history_gate_ignores_stale_neutral_openbox(
    tmp_path: Path,
) -> None:
    from hermes_workflow.optimizer_artifacts import (
        EVALUATIONS_RELATIVE,
        LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        LEGACY_NATIVE_REPORT_RELATIVE,
        REPORT_RELATIVE,
    )
    from hermes_workflow.remote_optimizer_flow import _continuation_history_path

    reports = tmp_path / "reports"
    reports.mkdir()
    (tmp_path / REPORT_RELATIVE).write_text(
        '{"backend": "openbox", "status": "completed"}\n',
        encoding="utf-8",
    )
    (tmp_path / EVALUATIONS_RELATIVE).write_text(
        '{"evaluation_index": 99}\n',
        encoding="utf-8",
    )
    (tmp_path / LEGACY_NATIVE_REPORT_RELATIVE).write_text(
        '{"backend": "native_turbo", "status": "completed"}\n',
        encoding="utf-8",
    )
    (tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE).write_text(
        '{"evaluation_index": 1}\n',
        encoding="utf-8",
    )

    history = _continuation_history_path(tmp_path, backend="native_turbo")

    assert history == tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE


def test_remote_continuation_rejects_fix_run_before_backend_dispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    config_dir = cache_dir / "config"
    config_dir.mkdir()
    (config_dir / "fixed_points.yaml").write_text("fixed_points: []\n")
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass",
            cache_dir=cache_dir,
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *args, **kwargs: SimpleNamespace(optimizer=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._backend_from_project_strategy",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fix-run must be rejected before backend dispatch")
        ),
    )

    with pytest.raises(
        ValueError,
        match="continuation requires an optimize workflow",
    ):
        continue_remote_project(
            ref,
            additional_evals=1,
            remote_cadence_cshrc=PurePosixPath("/remote/cadence_env.csh"),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=_passed_remote_doctor_report(),
            attempt_started=True,
        )


def test_optimize_remote_project_runs_doctor_prepare_openbox_and_sync(tmp_path: Path, monkeypatch) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[str] = []
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    def fake_prepare_remote_snapshot(*args: object, **kwargs: object) -> SimpleNamespace:
        assert kwargs["persist_snapshot"] is True
        return SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[])

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        fake_prepare_remote_snapshot,
    )

    def fake_optimize_project(project_dir: Path, **kwargs):
        calls.append("optimize_project")
        assert project_dir == cache_dir
        assert kwargs["real"] is True
        doctor = kwargs["services"].run_product_doctor(
            project_dir,
            cadence_cshrc=kwargs["cadence_cshrc"],
        )
        assert doctor.status == "pass"
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr("hermes_workflow.remote_optimizer_flow.optimize_project", fake_optimize_project)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=object(),
    )

    assert result.status == "pass"
    assert result.recommended_run_id == "real_001"
    assert calls == ["optimize_project", "sync_reports"]


def test_optimize_remote_project_reuses_frozen_remote_preparation_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    remote_maestro_root = "/remote/maestro/point_1"
    requirement_text = (
        Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
        .read_text(encoding="utf-8")
        .replace("__MAESTRO_POINT_ROOT__", remote_maestro_root)
    )
    (cache_dir / "opt_requirement.md").write_text(requirement_text, encoding="utf-8")

    class RemoteMaestroRunner:
        def __init__(self) -> None:
            self.commands: list[str] = []

        def run(self, command: str, **kwargs: object) -> SimpleNamespace:
            self.commands.append(command)
            if "optimizer_flow_run_report.json" in command:
                return SimpleNamespace(return_code=0, stdout="", stderr="")
            raise AssertionError(
                "remote Maestro paths must not be re-read after preparation"
            )

    runner = RemoteMaestroRunner()
    requirement_snapshot = SimpleNamespace(status="pass", issues=[])
    preparation_snapshot = SimpleNamespace(status="pass", issues=[])
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass",
            cache_dir=cache_dir,
            issues=[],
            requirement_report=requirement_snapshot,
            preparation_report=preparation_snapshot,
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: None,
    )

    def fake_optimize_project(project_dir: Path, **kwargs: object) -> SimpleNamespace:
        services = kwargs["services"]
        requirement_report = services.check_requirement(project_dir)
        assert requirement_report is requirement_snapshot
        preparation_report = services.prepare_from_requirement(project_dir)
        assert preparation_report is preparation_snapshot
        return SimpleNamespace(status="pass", recommended_run_id=None)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    assert result.status == "pass"
    assert len(runner.commands) == 1
    assert "optimizer_flow_run_report.previous.json" in runner.commands[0]


def test_optimize_remote_project_rejects_doctor_prepare_mode_race(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    prepared = SimpleNamespace(
        status="pass",
        cache_dir=tmp_path / "cache",
        issues=[],
        requirement_report=SimpleNamespace(workflow_mode="fix_run"),
        preparation_report=SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: prepared,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        lambda *args, **kwargs: pytest.fail(
            "fix-run snapshot must not enter optimizer flow"
        ),
    )

    with pytest.raises(ValueError, match="workflow mode changed"):
        optimize_remote_project(
            ref,
            real=True,
            max_evals=None,
            batch_size=None,
            parallel_jobs=None,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            cache_root=tmp_path,
            runner=object(),
        )


def test_optimize_remote_project_rejects_fix_run_before_prepare(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: pytest.fail(
            "fix-run requirement must not be prepared by remote optimize"
        ),
    )

    with pytest.raises(
        ValueError,
        match="remote optimize requires workflow mode 'optimize'",
    ):
        optimize_remote_project(
            ref,
            real=True,
            max_evals=None,
            batch_size=None,
            parallel_jobs=None,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            cache_root=tmp_path,
            runner=object(),
            doctor_report=SimpleNamespace(
                status="pass",
                workflow_mode="fix_run",
                issues=[],
            ),
            attempt_started=True,
        )


def test_optimize_remote_project_routes_turbo_strategy_through_remote_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    runner = object()
    calls: list[str] = []

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass", issues=[], cache_dir=cache_dir
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )

    def fake_single_adapter(local_project: Path, **kwargs: object) -> object:
        calls.append("single_adapter")
        assert local_project == cache_dir
        assert kwargs["run_id"] == "real_001"
        assert kwargs["remote_ref"] == ref
        assert kwargs["remote_cadence_cshrc"] == PurePosixPath(
            "/remote/project/cadence_env.csh"
        )
        assert kwargs["runner"] is runner
        return "single-remote-adapter"

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        fake_single_adapter,
    )

    def fake_native_turbo(project_dir: Path, **kwargs: object) -> object:
        calls.append("run_native_turbo")
        assert project_dir == cache_dir
        assert kwargs["max_evals"] == 2
        assert kwargs["parallel_jobs"] == 1
        assert kwargs["transport_mode"] == "remote"
        adapter = kwargs["adapter"]
        assert adapter(cache_dir, run_id="real_001", cadence_cshrc=Path("test")) == (
            "single-remote-adapter"
        )
        return SimpleNamespace(report_path=cache_dir / "reports" / "turbo.json")

    def fake_optimize_project(project_dir: Path, **kwargs: object) -> object:
        calls.append("optimize_project")
        assert project_dir == cache_dir
        assert kwargs["strategy"] == "turbo_trust_region"
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(
            project_dir,
            max_evals=kwargs["max_evals"],
            parallel_jobs=kwargs["parallel_jobs"],
            cadence_cshrc=kwargs["cadence_cshrc"],
        )
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        strategy="turbo_trust_region",
        cache_root=tmp_path,
        runner=runner,
    )

    assert result.status == "pass"
    assert calls == [
        "optimize_project",
        "run_native_turbo",
        "single_adapter",
        "sync_reports",
    ]


def _seed_optimizer_history(cache_dir: Path) -> None:
    """Create a non-empty optimizer_evaluations.jsonl so the no-history check passes."""
    reports = cache_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "optimizer_run_report.json").write_text(
        '{"backend": "openbox", "status": "completed"}\n',
        encoding="utf-8",
    )
    (reports / "optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1}\n', encoding="utf-8"
    )


def _stub_history_manifest_materialization(
    cache_dir: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.materialize_remote_history_manifests",
        lambda *args, **kwargs: cache_dir / ".remote_history_manifests",
    )


def _setup_continue_mocks(
    cache_dir: Path,
    calls: list[str],
    monkeypatch,
    *,
    openbox_result: object | None = None,
    closeout_result: object | None = None,
) -> None:
    """Wire up standard mocks for continue_remote_project tests."""
    if openbox_result is None:
        openbox_result = SimpleNamespace(
            evaluation_count=6,
            report_path=cache_dir / "reports" / "openbox_report.json",
            evaluations_path=cache_dir / "reports" / "evaluations.jsonl",
        )
    if closeout_result is None:
        closeout_result = SimpleNamespace(
            status="pass",
            recommended_run_id="real_141",
            recommended_action="stop_for_user_review",
        )

    def fake_prepare_remote_snapshot(*args, **kwargs):
        assert kwargs["frozen_snapshot"] is True
        return SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[])

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        fake_prepare_remote_snapshot,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *args, **kwargs: calls.append("sync_history"),
    )
    _stub_history_manifest_materialization(cache_dir, monkeypatch)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.build_execution_package",
        lambda *args, **kwargs: calls.append("build_execution_package"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *args, **kwargs: SimpleNamespace(testbenches=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        lambda *args, **kwargs: (calls.append("run_openbox"), openbox_result)[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *args, **kwargs: (calls.append("check_optimizer_run"), SimpleNamespace(status="accepted"))[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *args, **kwargs: (calls.append("summarize_optimizer_run"), SimpleNamespace(status="pass"))[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        lambda *args, **kwargs: (calls.append("finalize_optimizer_run"), SimpleNamespace(status="pass"))[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *args, **kwargs: (calls.append("generate_optimizer_insight_report"), SimpleNamespace(status="pass"))[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *args, **kwargs: (calls.append("generate_optimizer_decision_report"), closeout_result)[-1],
    )


def test_optimize_remote_project_allows_config_turbo_strategy_before_local_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_optimizer_strategy(cache_dir, "turbo_trust_region", "turbo")
    calls: list[str] = []

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[], cache_dir=cache_dir),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *args, **kwargs: calls.append("sync_history"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: calls.append("sync_reports"),
    )

    def fake_native_turbo(project_dir: Path, **kwargs: object) -> object:
        calls.append("run_native_turbo")
        assert project_dir == cache_dir
        assert "adapter" in kwargs
        return SimpleNamespace(report_path=cache_dir / "reports" / "turbo.json")

    def fake_optimize_project(project_dir: Path, **kwargs: object) -> object:
        calls.append("optimize_project")
        assert project_dir == cache_dir
        assert kwargs["strategy"] is None
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(
            project_dir,
            max_evals=kwargs["max_evals"],
            parallel_jobs=kwargs["parallel_jobs"],
            cadence_cshrc=kwargs["cadence_cshrc"],
        )
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        strategy=None,
        cache_root=tmp_path,
        runner=object(),
    )

    assert result.status == "pass"
    assert calls == ["optimize_project", "run_native_turbo", "sync_reports"]


def test_continue_remote_project_does_not_call_first_run_optimize_project(
    tmp_path: Path, monkeypatch
) -> None:
    """continue_remote_project must NOT call optimize_project (first-run flow)
    and must succeed when execution_package/ already exists."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    # Pre-create execution_package to simulate remote history sync
    pkg_dir = cache_dir / "execution_package"
    pkg_dir.mkdir()
    (pkg_dir / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)

    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)

    # Patch optimize_project so the test fails if it's called
    def fail_if_called(*args, **kwargs):
        raise AssertionError("optimize_project must not be called for continuation")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project", fail_if_called
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert result.status == "pass"
    assert result.recommended_run_id == "real_141"
    # Must NOT include optimize_project or build_execution_package
    assert "optimize_project" not in calls
    assert "build_execution_package" not in calls
    # Must call sync_history, openbox, closeout, then sync_reports
    assert calls[0] == "sync_history"
    assert "run_openbox" in calls
    assert "check_optimizer_run" in calls
    assert "summarize_optimizer_run" in calls
    assert "finalize_optimizer_run" in calls
    assert "generate_optimizer_insight_report" in calls
    assert "generate_optimizer_decision_report" in calls
    assert calls[-1] == "sync_reports"


def test_remote_continuation_materializes_prior_manifests_without_polluting_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from hermes_workflow.package import sha256_file
    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    (cache_dir / "execution_package" / "execution_manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    prior_result_relative = PurePosixPath(
        "runs/real/real_001/result_manifest.json"
    )
    prior_metric_relative = PurePosixPath(
        "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    prior_row = {
        "evaluation_index": 1,
        "run_id": "real_001",
        "status": "feasible",
        "result_manifest": prior_result_relative.as_posix(),
        "metric_result_manifest": prior_metric_relative.as_posix(),
    }
    (reports_dir / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "backend": "openbox",
                "evaluation_count": 1,
                "execution_mode": "real",
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        json.dumps(prior_row) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_run_acceptance_report.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "evaluation_count": 1,
                "result_manifest_count": 1,
                "metric_manifest_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    remote_source = tmp_path / "remote-source"
    for relative, payload in (
        (
            prior_result_relative,
            {
                "run_id": "real_001",
                "status": "succeeded",
                "metric_result_manifest": prior_metric_relative.as_posix(),
            },
        ),
        (prior_metric_relative, {"run_id": "real_001", "status": "succeeded"}),
    ):
        path = remote_source.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (reports_dir / "remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_source.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (prior_result_relative, prior_metric_relative)
        ),
        encoding="utf-8",
    )

    events: list[str] = []

    class Runner:
        profile = "lab"

        def run(self, command: str, **kwargs: object) -> SimpleNamespace:
            events.append(f"remote-check:{command}")
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def download_files(
            self,
            _remote_root: PurePosixPath,
            paths: tuple[PurePosixPath, ...],
            local_root: Path,
        ) -> None:
            events.append("download-prior-manifests")
            for relative in paths:
                source = remote_source.joinpath(*relative.parts)
                target = local_root.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            cache_dir=cache_dir,
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )

    def optimizer(project_dir: Path, **_kwargs: object) -> SimpleNamespace:
        from hermes_workflow.retention_evidence import preserve_retention_evidence

        events.append("optimizer")
        assert project_dir == cache_dir
        assert not (cache_dir / prior_result_relative).exists()
        assert (
            cache_dir / ".remote_history_manifests" / prior_result_relative
        ).is_file()
        new_result = cache_dir / "runs/real/real_002/result_manifest.json"
        new_result.parent.mkdir(parents=True)
        new_result.write_text(
            json.dumps({"run_id": "real_002", "status": "failed"}) + "\n",
            encoding="utf-8",
        )
        evidence = preserve_retention_evidence(
            cache_dir,
            run_id="real_002",
            candidate_id=None,
        )
        decision = cache_dir / "state/run_retention/real_002.json"
        decision.parent.mkdir(parents=True, exist_ok=True)
        decision.write_text(
            json.dumps(
                {
                    "run_id": "real_002",
                    "local_action": "deleted",
                    "remote_action": "deleted",
                    "evidence_status": "preserved",
                    "evidence_digest": evidence.digest,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        shutil.rmtree(new_result.parent)
        (reports_dir / "optimizer_evaluations.jsonl").write_text(
            json.dumps(prior_row)
            + "\n"
            + json.dumps(
                {
                    "evaluation_index": 2,
                    "run_id": "real_002",
                    "status": "real_check_failed",
                    "result_manifest": (
                        "runs/real/real_002/result_manifest.json"
                    ),
                    "metric_result_manifest": None,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (reports_dir / "optimizer_run_report.json").write_text(
            json.dumps(
                {
                    "backend": "openbox",
                    "evaluation_count": 2,
                    "execution_mode": "real",
                    "status": "completed",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(status="completed", evaluation_count=2)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        optimizer,
    )
    seen_supplementary: list[tuple[str, Path | None]] = []

    def acceptance(
        _project: Path,
        *,
        expected_backend: str | None = None,
        supplementary_artifact_root: Path | None = None,
    ) -> SimpleNamespace:
        assert expected_backend == "openbox"
        seen_supplementary.append(("check", supplementary_artifact_root))
        return SimpleNamespace(status="accepted")

    def finalize(
        _project: Path,
        *,
        expected_backend: str | None = None,
        supplementary_artifact_root: Path | None = None,
    ) -> SimpleNamespace:
        assert expected_backend == "openbox"
        seen_supplementary.append(("finalize", supplementary_artifact_root))
        return SimpleNamespace(status="pass")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        acceptance,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        finalize,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_002",
            recommended_action="stop_for_user_review",
        ),
    )

    def publish(_ref: object, project_dir: Path, _ssh: object) -> None:
        events.append("publish")
        assert {
            path.name
            for path in (project_dir / "runs" / "real").iterdir()
            if path.is_dir()
        } == set()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        publish,
    )

    report = continue_remote_project(
        ref,
        additional_evals=1,
        remote_cadence_cshrc=PurePosixPath("/remote/cadence_env.csh"),
        batch_size=1,
        parallel_jobs=1,
        cache_root=tmp_path,
        runner=Runner(),
        doctor_report=_passed_remote_doctor_report(),
        attempt_started=True,
    )

    supplementary_root = cache_dir / ".remote_history_manifests"
    combined_root = cache_dir / ".optimizer_supplementary_manifests"
    assert report.status == "pass"
    assert events.index("download-prior-manifests") < events.index("optimizer")
    assert seen_supplementary == [
        ("check", supplementary_root),
        ("check", combined_root),
        ("finalize", combined_root),
    ]
    assert (combined_root / prior_result_relative).is_file()
    assert (
        combined_root / "runs/real/real_002/result_manifest.json"
    ).is_file()


def test_openbox_remote_continuation_rejects_duplicate_accepted_history_before_optimizer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from hermes_workflow.package import sha256_file
    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    execution_package = cache_dir / "execution_package"
    execution_package.mkdir()
    (execution_package / "execution_manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    result_relative = PurePosixPath(
        "runs/real/real_001/result_manifest.json"
    )
    metric_relative = PurePosixPath(
        "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    duplicate_row = {
        "evaluation_index": 1,
        "run_id": "real_001",
        "status": "feasible",
        "result_manifest": result_relative.as_posix(),
        "metric_result_manifest": metric_relative.as_posix(),
    }
    (reports_dir / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "backend": "openbox",
                "evaluation_count": 2,
                "execution_mode": "real",
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        json.dumps(duplicate_row)
        + "\n"
        + json.dumps(duplicate_row)
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_run_acceptance_report.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "evaluation_count": 2,
                "result_manifest_count": 2,
                "metric_manifest_count": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    remote_source = tmp_path / "remote-source"
    for relative, payload in (
        (
            result_relative,
            {
                "run_id": "real_001",
                "status": "succeeded",
                "metric_result_manifest": metric_relative.as_posix(),
            },
        ),
        (metric_relative, {"run_id": "real_001", "status": "succeeded"}),
    ):
        path = remote_source.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (reports_dir / "remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_source.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (result_relative, metric_relative)
        ),
        encoding="utf-8",
    )
    optimizer_calls: list[str] = []

    class Runner:
        profile = "lab"

        def run(self, _command: str, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def download_files(
            self,
            _remote_root: PurePosixPath,
            paths: tuple[PurePosixPath, ...],
            local_root: Path,
        ) -> None:
            for relative in paths:
                source = remote_source.joinpath(*relative.parts)
                target = local_root.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            cache_dir=cache_dir,
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )

    def forbidden_optimizer(*_args: object, **_kwargs: object) -> object:
        optimizer_calls.append("optimizer")
        raise AssertionError("optimizer must not run")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        forbidden_optimizer,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        lambda *a, **k: None,
    )

    with pytest.raises(RuntimeError, match="duplicate run_id"):
        continue_remote_project(
            ref,
            additional_evals=1,
            remote_cadence_cshrc=PurePosixPath("/remote/cadence_env.csh"),
            batch_size=1,
            parallel_jobs=1,
            cache_root=tmp_path,
            runner=Runner(),
            doctor_report=_passed_remote_doctor_report(),
            attempt_started=True,
        )

    assert optimizer_calls == []


@pytest.mark.parametrize(
    (
        "result_status",
        "result_run_id",
        "candidate_id",
        "expected_rejection",
    ),
    [
        ("failed", "real_001", "candidate_000001", "result failure"),
        (
            "succeeded",
            "real_999",
            "candidate_000001",
            "result manifest run_id mismatch",
        ),
        (
            "succeeded",
            "real_001",
            "candidate_999999",
            "result manifest candidate_id mismatch",
        ),
    ],
)
def test_remote_continuation_rechecks_persistent_remote_history_before_optimizer(
    tmp_path: Path,
    monkeypatch,
    result_status: str,
    result_run_id: str,
    candidate_id: str,
    expected_rejection: str,
) -> None:
    """Exercise real sync, bundle materialization, and prior acceptance together."""
    from hermes_workflow.package import sha256_file
    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    remote_project = tmp_path / "remote-fs" / "project"
    controller_cache = create_generic_project(
        tmp_path / "controller-fs",
        name="cache",
    )
    _set_optimizer_strategy(controller_cache, "openbox_auto", "openbox")
    remote_reports = remote_project / "reports"
    remote_reports.mkdir(parents=True)
    remote_execution = remote_project / "execution_package"
    remote_execution.mkdir()
    (remote_execution / "execution_manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    result_relative = PurePosixPath(
        "runs/real/real_001/result_manifest.json"
    )
    metric_relative = PurePosixPath(
        "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    history_row = {
        "evaluation_index": 1,
        "run_id": "real_001",
        "status": "feasible",
        "result_manifest": result_relative.as_posix(),
        "metric_result_manifest": metric_relative.as_posix(),
    }
    (remote_reports / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "backend": "openbox",
                "evaluation_count": 1,
                "execution_mode": "real",
                "issues": [],
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (remote_reports / "optimizer_evaluations.jsonl").write_text(
        json.dumps(history_row) + "\n",
        encoding="utf-8",
    )
    (remote_reports / "optimizer_run_acceptance_report.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "evaluation_count": 1,
                "result_manifest_count": 1,
                "metric_manifest_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result_path = remote_project.joinpath(*result_relative.parts)
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "run_id": result_run_id,
                "status": result_status,
                "metric_result_manifest": metric_relative.as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    metric_path = remote_project.joinpath(*metric_relative.parts)
    metric_path.parent.mkdir(parents=True)
    metric_path.write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "run_id": "real_001",
                "status": "succeeded",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (remote_reports / "remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_project.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (result_relative, metric_relative)
        ),
        encoding="utf-8",
    )

    class PersistentDualFsRunner:
        profile = "lab"
        transfer_timeout_s = 30

        def run(self, command: str, **_kwargs: object) -> SimpleNamespace:
            completed = subprocess.run(
                ["/bin/sh", "-c", command],
                capture_output=True,
                check=False,
                text=True,
            )
            return SimpleNamespace(
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        def download_tree(
            self,
            remote_dir: PurePosixPath,
            local_dir: Path,
        ) -> None:
            shutil.copytree(Path(remote_dir.as_posix()), local_dir, dirs_exist_ok=True)

        def download_files(
            self,
            remote_root: PurePosixPath,
            paths: tuple[PurePosixPath, ...],
            local_root: Path,
        ) -> None:
            for relative in paths:
                source = Path(remote_root.as_posix()).joinpath(*relative.parts)
                target = local_root.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    controller_cache.mkdir(parents=True, exist_ok=True)
    ref = RemoteProjectRef("lab", PurePosixPath(remote_project.as_posix()))
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            cache_dir=controller_cache,
            issues=[],
        ),
    )
    optimizer_calls: list[str] = []

    def forbidden_optimizer(*_args: object, **_kwargs: object) -> object:
        optimizer_calls.append("optimizer")
        raise AssertionError("optimizer must not run")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        forbidden_optimizer,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "prior optimizer history acceptance rejected:.*"
            + expected_rejection
        ),
    ):
        continue_remote_project(
            ref,
            additional_evals=1,
            remote_cadence_cshrc=PurePosixPath("/remote/cadence_env.csh"),
            batch_size=1,
            parallel_jobs=1,
            cache_root=tmp_path,
            runner=PersistentDualFsRunner(),
            doctor_report=_passed_remote_doctor_report(),
            attempt_started=True,
        )

    assert optimizer_calls == []
    assert not controller_cache.joinpath(*result_relative.parts).exists()
    assert (
        controller_cache
        / ".remote_history_manifests"
        / result_relative
    ).is_file()


def test_continue_remote_project_calls_openbox_with_continuation_params(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify run_openbox_real_optimization receives continuation params."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)
    _stub_history_manifest_materialization(cache_dir, monkeypatch)

    captured_kwargs: dict = {}

    openbox_result = SimpleNamespace(
        evaluation_count=6,
        report_path=cache_dir / "reports" / "openbox_report.json",
        evaluations_path=cache_dir / "reports" / "evaluations.jsonl",
    )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.build_execution_package",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *args, **kwargs: SimpleNamespace(testbenches=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda *args, **kwargs: None,
    )

    def capture_openbox(project_dir, **kwargs):
        captured_kwargs.update(kwargs)
        return openbox_result

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        capture_openbox,
    )
    # Minimal closeout stubs
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_141",
            recommended_action="stop_for_user_review",
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert captured_kwargs["additional_evals"] == 4
    assert captured_kwargs["continue_from_existing"] is True
    assert captured_kwargs["max_evals"] is None
    assert captured_kwargs["batch_size"] == 2
    assert captured_kwargs["parallel_jobs"] == 2
    assert captured_kwargs["strategy"] is None
    assert "adapter" in captured_kwargs
    assert callable(captured_kwargs["retention_callback"])


def test_continue_remote_turbo_uses_legacy_history_remote_transport_and_orphan_floor(
    tmp_path: Path, monkeypatch
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    (cache_dir / "execution_package" / "execution_manifest.json").write_text("{}")
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir()
    (reports_dir / "native_turbo_optimizer_report.json").write_text(
        '{"backend": "native_turbo", "status": "completed"}\n',
        encoding="utf-8",
    )
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1, "run_id": "real_001"}\n',
        encoding="utf-8",
    )
    _stub_history_manifest_materialization(cache_dir, monkeypatch)
    captured: dict[str, object] = {}

    class Runner:
        profile = "lab"

        def run(self, command: str, **_kwargs: object) -> SimpleNamespace:
            captured["inventory_command"] = command
            return SimpleNamespace(
                return_code=0,
                stdout="real_003\nreal_019\n",
                stderr="",
            )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass", cache_dir=cache_dir, issues=[]
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._backend_from_project_strategy",
        lambda *_args, **_kwargs: "native_turbo",
        raising=False,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *a, **k: SimpleNamespace(testbenches=None, process_corners=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("OpenBox must not run for a TuRBO continuation")
        ),
    )

    def capture_native(project: Path, **kwargs: object) -> SimpleNamespace:
        captured["native_project"] = project
        captured["native_kwargs"] = kwargs
        return SimpleNamespace(evaluation_count=3)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        capture_native,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_020",
            recommended_action="stop_for_user_review",
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=2,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=Runner(),
        doctor_report=_passed_remote_doctor_report(),
        attempt_started=True,
    )

    assert result.status == "pass"
    assert result.backend == "native_turbo"
    assert [step.name for step in result.steps][0] == "run-native-turbo-real"
    assert captured["native_project"] == cache_dir
    native_kwargs = captured["native_kwargs"]
    assert native_kwargs["additional_evals"] == 2
    assert native_kwargs["continue_from_existing"] is True
    assert native_kwargs["transport_mode"] == "remote"
    assert native_kwargs["run_offset_floor"] == 19
    assert callable(native_kwargs["retention_callback"])
    assert "runs/real" in str(captured["inventory_command"])


def test_remote_turbo_run_inventory_transport_failure_is_not_directory_missing(
    tmp_path: Path, monkeypatch
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "execution_package").mkdir()
    (cache_dir / "execution_package" / "execution_manifest.json").write_text("{}")
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir()
    (reports_dir / "native_turbo_optimizer_report.json").write_text(
        '{"backend": "native_turbo", "status": "completed"}\n',
        encoding="utf-8",
    )
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1, "run_id": "real_001"}\n',
        encoding="utf-8",
    )
    _stub_history_manifest_materialization(cache_dir, monkeypatch)

    class Runner:
        profile = "lab"

        def run(self, _command: str, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                return_code=255,
                stdout="",
                stderr="connection reset",
            )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass", cache_dir=cache_dir, issues=[]
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._backend_from_project_strategy",
        lambda *_args, **_kwargs: "native_turbo",
        raising=False,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *a, **k: SimpleNamespace(testbenches=None, process_corners=None),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(ValueError, match="remote real-run inventory probe failed"):
        continue_remote_project(
            ref,
            additional_evals=2,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=Runner(),
            doctor_report=_passed_remote_doctor_report(),
            attempt_started=True,
        )


def test_continue_remote_project_fails_when_no_optimizer_history(
    tmp_path: Path, monkeypatch
) -> None:
    """Remote continuation must fail-closed when optimizer_evaluations.jsonl is missing."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    # NOTE: no reports/optimizer_evaluations.jsonl created.

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(ValueError, match=r"cannot continue without optimizer history"):
        continue_remote_project(
            ref,
            additional_evals=5,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=_passed_remote_doctor_report(),
        )


def test_continue_remote_project_ensures_manifest_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """When execution_package is missing (not synced), it must build it."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    # No execution_package directory
    _seed_optimizer_history(cache_dir)

    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("optimize_project must not be called")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project", fail_if_called
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=None,
        parallel_jobs=None,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert result.status == "pass"
    assert "build_execution_package" in calls
    assert "optimize_project" not in calls


def test_continue_remote_project_resource_inheritance_no_explicit_override(
    tmp_path: Path, monkeypatch
) -> None:
    """When batch_size and parallel_jobs are None, they must not be hardcoded."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)
    _stub_history_manifest_materialization(cache_dir, monkeypatch)

    captured_kwargs: dict = {}

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.build_execution_package",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *a, **k: SimpleNamespace(testbenches=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda *a, **k: None,
    )

    def capture_openbox(project_dir, **kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            evaluation_count=6,
            report_path=None,
            evaluations_path=None,
        )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        capture_openbox,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_141",
            recommended_action="stop_for_user_review",
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=None,
        parallel_jobs=None,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert captured_kwargs["batch_size"] is None
    assert captured_kwargs["parallel_jobs"] is None


def test_continue_remote_project_writes_flow_report(tmp_path: Path, monkeypatch) -> None:
    """Continuation must write a flow run report like optimize_project does."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)

    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("optimize_project must not be called")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project", fail_if_called
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert result.report_path is not None
    assert result.report_path.exists()


def test_continue_remote_project_syncs_history_and_runs_additional_evals(tmp_path: Path, monkeypatch) -> None:
    """Legacy test updated: continuation does NOT call optimize_project."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)

    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("optimize_project must not be called for continuation")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project", fail_if_called
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=40,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert result.status == "pass"
    assert result.recommended_run_id == "real_141"
    assert "optimize_project" not in calls
    assert calls[0] == "sync_history"
    assert "run_openbox" in calls
    assert calls[-1] == "sync_reports"


def test_continue_remote_project_writes_supervisor_instruction_before_optimizer(
    tmp_path: Path, monkeypatch
) -> None:
    """Remote continuation rebuilds its controller cache from the frozen
    snapshot, which never contains the real-run supervisor instruction, so the
    continuation flow must re-decide it into the cache before the optimizer
    step consumes it via the real-run approval gate."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)

    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)

    seen: dict[str, object] = {}
    openbox_result = SimpleNamespace(
        evaluation_count=6,
        report_path=cache_dir / "reports" / "openbox_report.json",
        evaluations_path=cache_dir / "reports" / "evaluations.jsonl",
    )

    def capture_instruction_then_run(*args, **kwargs):
        instruction_path = cache_dir / "supervisor_instruction.json"
        seen["exists_at_optimizer"] = instruction_path.exists()
        if instruction_path.exists():
            seen["payload"] = json.loads(
                instruction_path.read_text(encoding="utf-8")
            )
        calls.append("run_openbox")
        return openbox_result

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        capture_instruction_then_run,
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    result = continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert result.status == "pass"
    assert seen["exists_at_optimizer"] is True
    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert "decision" in payload
    assert "approved_config_hashes" in payload


def test_continue_remote_project_does_not_pass_strategy_detail_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    """Remote product continuation must pass `None` for every CLI-side
    strategy detail, so requirement/config drives the strategy resolver."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")
    _seed_optimizer_history(cache_dir)
    _stub_history_manifest_materialization(cache_dir, monkeypatch)

    captured_kwargs: dict = {}

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.build_execution_package",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *a, **k: SimpleNamespace(testbenches=None),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda *a, **k: None,
    )

    def capture_openbox(project_dir, **kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            evaluation_count=6,
            report_path=None,
            evaluations_path=None,
        )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        capture_openbox,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.finalize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_141",
            recommended_action="stop_for_user_review",
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    continue_remote_project(
        ref,
        additional_evals=4,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        batch_size=None,
        parallel_jobs=None,
        cache_root=tmp_path,
        runner=object(),
        doctor_report=_passed_remote_doctor_report(),
    )

    assert captured_kwargs["max_evals"] is None
    assert captured_kwargs["additional_evals"] == 4
    assert captured_kwargs["continue_from_existing"] is True
    assert captured_kwargs["batch_size"] is None
    assert captured_kwargs["parallel_jobs"] is None
    assert captured_kwargs["strategy"] is None
    assert captured_kwargs["surrogate_type"] is None
    assert captured_kwargs["acq_type"] is None
    assert captured_kwargs["acq_optimizer_type"] is None
    assert captured_kwargs["initial_trials"] is None


def test_optimize_remote_project_routes_multi_testbench_to_multi_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    """When testbenches config is present, optimize_remote_project must route
    to run_remote_multi_testbench_adapter instead of run_remote_spectre_ocean_adapter."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    captured_adapter_name: list[str] = []

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )

    # Mock run_openbox_real_optimization so it invokes the adapter callback
    # (the routing decision happens inside the adapter passed by remote_openbox).
    def fake_openbox(*args, **kwargs):
        assert kwargs["transport_mode"] == "remote"
        assert callable(kwargs["retention_callback"])
        adapter = kwargs.get("adapter")
        if adapter is not None:
            adapter(cache_dir, run_id="test_run", cadence_cshrc=Path("test"))
        return SimpleNamespace(evaluation_count=0)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        fake_openbox,
    )

    def fake_optimize_project(project_dir: Path, **kwargs):
        services = kwargs["services"]
        assert services is not None
        # Exercise the remote_openbox callback so the adapter routing fires.
        services.run_openbox_real_optimization(project_dir)
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr("hermes_workflow.remote_optimizer_flow.optimize_project", fake_optimize_project)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: None,
    )

    # Mock assert_valid_project to return a bundle WITH testbenches
    class FakeTestbench:
        def __init__(self, id: str) -> None:
            self.id = id

    class FakeTestbenches:
        testbenches = [FakeTestbench("tb1"), FakeTestbench("tb2")]

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *args, **kwargs: SimpleNamespace(testbenches=FakeTestbenches()),
    )

    # Capture which adapter is called
    def fake_multi_adapter(*args, **kwargs):
        captured_adapter_name.append("multi")
        return SimpleNamespace(status="succeeded", issues=[])

    def fake_single_adapter(*args, **kwargs):
        captured_adapter_name.append("single")
        return SimpleNamespace(status="succeeded", issues=[])

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_multi_testbench_adapter",
        fake_multi_adapter,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        fake_single_adapter,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=object(),
    )

    assert captured_adapter_name == ["multi"]
    assert result.status == "pass"


def test_optimize_remote_project_routes_single_testbench_to_single_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    """When testbenches config is absent, optimize_remote_project must route
    to run_remote_spectre_ocean_adapter, not run_remote_multi_testbench_adapter."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    captured_adapter_name: list[str] = []

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )

    # Mock run_openbox_real_optimization so it invokes the adapter callback
    # (the routing decision happens inside the adapter passed by remote_openbox).
    def fake_openbox(*args, **kwargs):
        assert kwargs["transport_mode"] == "remote"
        adapter = kwargs.get("adapter")
        if adapter is not None:
            adapter(cache_dir, run_id="test_run", cadence_cshrc=Path("test"))
        return SimpleNamespace(evaluation_count=0)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        fake_openbox,
    )

    def fake_optimize_project(project_dir: Path, **kwargs):
        services = kwargs["services"]
        # Exercise the remote_openbox callback so the adapter routing fires.
        services.run_openbox_real_optimization(project_dir)
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr("hermes_workflow.remote_optimizer_flow.optimize_project", fake_optimize_project)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda *args, **kwargs: SimpleNamespace(testbenches=None),
    )

    # Capture which adapter is called
    def fake_multi_adapter(*args, **kwargs):
        captured_adapter_name.append("multi")
        return SimpleNamespace(status="succeeded", issues=[])

    def fake_single_adapter(*args, **kwargs):
        captured_adapter_name.append("single")
        return SimpleNamespace(status="succeeded", issues=[])

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_multi_testbench_adapter",
        fake_multi_adapter,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        fake_single_adapter,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=object(),
    )

    assert captured_adapter_name == ["single"]
    assert result.status == "pass"


def test_sync_remote_history_to_cache_raises_on_download_failure(tmp_path: Path) -> None:
    from hermes_workflow.remote_optimizer_flow import _sync_remote_history_to_cache

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)

    class FakeSSH:
        def run(self, command):
            return SimpleNamespace(return_code=0, stderr="")

        def download_tree(self, remote, local):
            raise OSError("connection reset")

    with pytest.raises(RuntimeError, match="ledger"):
        _sync_remote_history_to_cache(ref, cache_dir, FakeSSH())


def test_sync_remote_history_to_cache_removes_controller_only_history(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import _sync_remote_history_to_cache

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    stale = cache_dir / "reports" / "optimizer_evaluations.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"evaluation_index": 1}\n', encoding="utf-8")

    class NoRemoteHistoryRunner:
        def run(self, command: str):
            return SimpleNamespace(return_code=1, stderr="")

    _sync_remote_history_to_cache(ref, cache_dir, NoRemoteHistoryRunner())

    assert not stale.exists()


def test_sync_remote_history_to_cache_preserves_local_history_on_probe_failure(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import _sync_remote_history_to_cache

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    stale = cache_dir / "ledger" / "experiment_ledger.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"run_id": "real_001"}\n', encoding="utf-8")

    class BrokenProbeRunner:
        def run(self, command: str):
            return SimpleNamespace(return_code=255, stderr="connection reset")

    with pytest.raises(
        RuntimeError,
        match="remote history subdir probe.*SSH passwordless login failed",
    ):
        _sync_remote_history_to_cache(ref, cache_dir, BrokenProbeRunner())

    assert stale.is_file()


def test_sync_cache_to_remote_publishes_reports_last(tmp_path: Path) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    for subdir in ("reports", "ledger", "state", "execution_package"):
        (cache_dir / subdir).mkdir(parents=True)
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    uploads: list[str] = []

    class RecordingRunner:
        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploads.append(f"tree:{PurePosixPath(remote_path).name}")

        def upload(self, local_path, remote_path) -> None:
            uploads.append(f"file:{PurePosixPath(remote_path).name}")

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert uploads == [
        "tree:ledger",
        "tree:state",
        "tree:execution_package",
        "tree:reports",
        "file:optimizer_flow_run_report.json",
    ]


def test_sync_cache_to_remote_republishes_parent_manifests_before_flow_marker(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    for subdir in ("reports", "ledger", "state", "execution_package"):
        (cache_dir / subdir).mkdir(parents=True)
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")

    for run_id in ("real_001", "real_002"):
        run_dir = cache_dir / "runs" / "real" / run_id
        metric_manifest = run_dir / "metrics" / "metric_result_manifest.json"
        metric_manifest.parent.mkdir(parents=True)
        metric_manifest.write_text('{"status": "succeeded"}\n', encoding="utf-8")
        result_manifest = run_dir / "result_manifest.json"
        netlist_input = run_dir / "netlist" / "input.scs"
        netlist_input.parent.mkdir(parents=True)
        netlist_input.write_text("simulator lang=spectre\n", encoding="utf-8")
        result_payload: dict[str, object] = {
            "status": "succeeded",
            "metric_result_manifest": (
                f"runs/real/{run_id}/metrics/metric_result_manifest.json"
            ),
            "child_results": [],
        }
        if run_id == "real_001":
            child_prefix = (
                "runs/real/real_001/testbenches/tb/corners/tt"
            )
            child_result = cache_dir / child_prefix / "result_manifest.json"
            child_metric = (
                cache_dir
                / child_prefix
                / "metrics"
                / "metric_result_manifest.json"
            )
            child_metric.parent.mkdir(parents=True)
            child_result.write_text(
                '{"status": "succeeded"}\n',
                encoding="utf-8",
            )
            child_metric.write_text(
                '{"status": "succeeded"}\n',
                encoding="utf-8",
            )
            result_payload["child_results"] = [
                {
                    "status": "succeeded",
                    "result_manifest": f"{child_prefix}/result_manifest.json",
                    "metric_result_manifest": (
                        f"{child_prefix}/metrics/metric_result_manifest.json"
                    ),
                }
            ]
        result_manifest.write_text(
            json.dumps(result_payload) + "\n",
            encoding="utf-8",
        )

    events: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            events.append(f"run:{command}")
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            events.append(f"tree:{PurePosixPath(remote_path).name}")

        def upload(self, local_path, remote_path) -> None:
            events.append(f"file:{PurePosixPath(remote_path).as_posix()}")

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    first_remote_run = "/remote/project/runs/real/real_001"
    second_remote_run = "/remote/project/runs/real/real_002"
    first_metric_event = (
        f"file:{first_remote_run}/metrics/metric_result_manifest.json"
    )
    second_metric_event = (
        f"file:{second_remote_run}/metrics/metric_result_manifest.json"
    )
    first_pending_event = (
        f"file:{first_remote_run}/result_manifest.pending.json"
    )
    second_pending_event = (
        f"file:{second_remote_run}/result_manifest.pending.json"
    )
    first_commit_event = next(
        event
        for event in events
        if event.startswith("run:mv -f --")
        and event.endswith(
            f"{first_remote_run}/result_manifest.pending.json "
            f"{first_remote_run}/result_manifest.json"
        )
    )
    second_commit_event = next(
        event
        for event in events
        if event.startswith("run:mv -f --")
        and event.endswith(
            f"{second_remote_run}/result_manifest.pending.json "
            f"{second_remote_run}/result_manifest.json"
        )
    )
    precommit_event = next(
        event
        for event in events
        if "sha256sum -c" in event and "precommit" in event
    )
    flow_event = "file:/remote/project/reports/optimizer_flow_run_report.json"
    assert events.index(first_metric_event) < events.index(first_pending_event)
    assert events.index(second_metric_event) < events.index(first_pending_event)
    assert events.index(first_pending_event) < events.index(second_pending_event)
    assert events.index(second_pending_event) < events.index(precommit_event)
    assert events.index(precommit_event) < events.index(first_commit_event)
    assert events.index(first_commit_event) < events.index(second_commit_event)
    assert events.index(second_commit_event) < events.index(flow_event)
    assert events.index("tree:netlist") < events.index(first_pending_event)
    assert any("sha256sum -c" in event for event in events if event.startswith("run:"))
    assert any("while IFS= read" in event for event in events if event.startswith("run:"))
    checksum_text = (
        cache_dir / "reports" / "remote_run_artifacts.sha256"
    ).read_text(encoding="utf-8")
    assert (
        "runs/real/real_001/testbenches/tb/corners/tt/"
        "metrics/metric_result_manifest.json" in checksum_text
    )
    assert (
        "runs/real/real_001/testbenches/tb/corners/tt/result_manifest.json"
        in checksum_text
    )


def test_sync_cache_to_remote_rejects_missing_referenced_child_manifest(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    run_dir = cache_dir / "runs" / "real" / "real_001"
    metric_manifest = run_dir / "metrics" / "metric_result_manifest.json"
    metric_manifest.parent.mkdir(parents=True)
    metric_manifest.write_text('{"status": "failed"}\n', encoding="utf-8")
    (run_dir / "result_manifest.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "metric_result_manifest": (
                    "runs/real/real_001/metrics/metric_result_manifest.json"
                ),
                "child_results": [
                    {
                        "status": "failed",
                        "result_manifest": (
                            "runs/real/real_001/testbenches/tb/corners/tt/"
                            "result_manifest.json"
                        ),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uploaded: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    with pytest.raises(RuntimeError, match="referenced child result manifest"):
        _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_omits_optional_failed_child_metric_reference(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    run_dir = cache_dir / "runs" / "real" / "real_001"
    child_prefix = "runs/real/real_001/testbenches/tb/corners/tt"
    child_result = cache_dir / child_prefix / "result_manifest.json"
    child_result.parent.mkdir(parents=True)
    child_result.write_text('{"status": "failed"}\n', encoding="utf-8")
    missing_metric = f"{child_prefix}/metrics/metric_result_manifest.json"
    (run_dir / "result_manifest.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "child_results": [
                    {
                        "status": "failed",
                        "result_manifest": f"{child_prefix}/result_manifest.json",
                        "metric_result_manifest": missing_metric,
                    }
                ],
                "command_trace": {"optional_metric": missing_metric},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            return None

        def upload(self, local_path, remote_path) -> None:
            return None

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    paths = (
        cache_dir / "reports" / "remote_run_artifact_paths.txt"
    ).read_text(encoding="utf-8")
    assert missing_metric not in paths


def test_sync_cache_to_remote_accepts_result_only_failed_run(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    result_manifest = cache_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_manifest.parent.mkdir(parents=True)
    result_manifest.write_text(
        '{"status": "failed", "notes": "spectre command failed"}\n',
        encoding="utf-8",
    )
    uploads: list[str] = []
    commands: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            commands.append(command)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploads.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploads.append(str(remote_path))

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert (
        str(
            ref.remote_project_dir
            / "runs/real/real_001/result_manifest.pending.json"
        )
        in uploads
    )
    assert any(
        command.endswith(
            "/runs/real/real_001/result_manifest.pending.json "
            "/remote/project/runs/real/real_001/result_manifest.json"
        )
        for command in commands
    )
    assert (
        str(ref.remote_project_dir / "reports/optimizer_flow_run_report.json")
        in uploads
    )


def test_sync_cache_to_remote_verifies_references_missing_from_controller(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    result_manifest = cache_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_manifest.parent.mkdir(parents=True)
    missing_log = "runs/real/real_001/spectre.stderr.log"
    result_manifest.write_text(
        json.dumps({"status": "failed", "log_file": missing_log}) + "\n",
        encoding="utf-8",
    )

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            return None

        def upload(self, local_path, remote_path) -> None:
            return None

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    inventory = (
        cache_dir / "reports" / "remote_run_artifact_paths.txt"
    ).read_text(encoding="utf-8")
    assert f"{missing_log}\n" in inventory


def test_sync_cache_to_remote_rejects_incomplete_parent_manifests(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    complete_run = cache_dir / "runs" / "real" / "real_001"
    complete_metric = complete_run / "metrics" / "metric_result_manifest.json"
    complete_metric.parent.mkdir(parents=True)
    complete_metric.write_text('{"status": "succeeded"}\n', encoding="utf-8")
    (complete_run / "result_manifest.json").write_text(
        '{"status": "succeeded"}\n',
        encoding="utf-8",
    )
    incomplete_metric = (
        cache_dir
        / "runs"
        / "real"
        / "real_002"
        / "metrics"
        / "metric_result_manifest.json"
    )
    incomplete_metric.parent.mkdir(parents=True)
    incomplete_metric.write_text('{"status": "succeeded"}\n', encoding="utf-8")
    uploaded: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    with pytest.raises(RuntimeError, match="incomplete remote parent"):
        _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert not any("/runs/real/" in remote for remote in uploaded)
    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_parent_upload_failure_prevents_flow_marker(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    run_dir = cache_dir / "runs" / "real" / "real_001"
    metric_manifest = run_dir / "metrics" / "metric_result_manifest.json"
    metric_manifest.parent.mkdir(parents=True)
    metric_manifest.write_text('{"status": "succeeded"}\n', encoding="utf-8")
    result_manifest = run_dir / "result_manifest.json"
    result_manifest.write_text('{"status": "succeeded"}\n', encoding="utf-8")
    uploaded: list[str] = []

    class ParentUploadFailingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            remote = str(remote_path)
            uploaded.append(remote)
            if remote.endswith("/metrics/metric_result_manifest.json"):
                raise RuntimeError("simulated parent upload failure")

    with pytest.raises(RuntimeError, match="simulated parent upload failure"):
        _sync_cache_reports_to_remote(
            ref,
            cache_dir,
            ParentUploadFailingRunner(),
        )

    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_commits_parent_marker_after_precommit_verification(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    result_manifest = cache_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_manifest.parent.mkdir(parents=True)
    result_manifest.write_text('{"status": "failed"}\n', encoding="utf-8")
    events: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            events.append(f"run:{command}")
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            events.append(f"tree:{remote_path}")

        def upload(self, local_path, remote_path) -> None:
            events.append(f"file:{remote_path}")

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    pending = "file:/remote/project/runs/real/real_001/result_manifest.pending.json"
    precommit_sha = next(
        index
        for index, event in enumerate(events)
        if "sha256sum -c" in event and "precommit" in event
    )
    precommit_refs = next(
        index
        for index, event in enumerate(events)
        if "while IFS= read" in event and "precommit" in event
    )
    commit = next(
        index
        for index, event in enumerate(events)
        if event.startswith("run:mv -f --")
        and event.endswith(
            "result_manifest.pending.json "
            "/remote/project/runs/real/real_001/result_manifest.json"
        )
    )
    flow = events.index(
        "file:/remote/project/reports/optimizer_flow_run_report.json"
    )
    assert events.index(pending) < precommit_sha < precommit_refs < commit < flow


def test_sync_cache_to_remote_checksum_failure_prevents_flow_marker(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    result_manifest = cache_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_manifest.parent.mkdir(parents=True)
    result_manifest.write_text('{"status": "failed"}\n', encoding="utf-8")
    uploaded: list[str] = []

    class ChecksumFailingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            if "sha256sum -c" in command:
                raise RuntimeError("simulated remote checksum mismatch")
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    with pytest.raises(RuntimeError, match="remote checksum mismatch"):
        _sync_cache_reports_to_remote(ref, cache_dir, ChecksumFailingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_without_runs_or_history_skips_inventory(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    (cache_dir / "runs" / "real").mkdir(parents=True)
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    uploaded: list[str] = []

    class EmptyInventoryRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            if "sha256sum -c" in command:
                raise RuntimeError("GNU sha256sum rejects an empty inventory")
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    _sync_cache_reports_to_remote(ref, cache_dir, EmptyInventoryRunner())

    assert (
        str(ref.remote_project_dir / "reports/optimizer_flow_run_report.json")
        in uploaded
    )
    assert not (cache_dir / "reports" / "remote_run_artifacts.sha256").exists()


def test_sync_cache_to_remote_skips_duplicate_candidate_without_run_directory(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = create_generic_project(tmp_path, name="cache")
    reports_dir = cache_dir / "reports"
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "status": "duplicate_candidate_skipped",
                "result_manifest": None,
                "metric_result_manifest": None,
                "metrics": None,
                "fom": None,
                "objective": 1_000_000.0,
                "constraint_penalty": 0.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uploaded: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) in uploaded
    assert not (reports_dir / "remote_run_artifacts.sha256").exists()


def test_sync_cache_to_remote_rejects_history_run_missing_without_retention(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "result_manifest": "runs/real/real_001/result_manifest.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uploaded: list[str] = []

    class RecordingRunner:
        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    with pytest.raises(RuntimeError, match="expected retained remote runs are missing"):
        _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_rejects_native_history_run_missing_without_retention(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "result_manifest": "runs/real/real_001/result_manifest.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uploaded: list[str] = []

    class RecordingRunner:
        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    with pytest.raises(RuntimeError, match="expected retained remote runs are missing"):
        _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) not in uploaded


def test_sync_cache_to_remote_accepts_history_run_deleted_by_retention(
    tmp_path: Path,
) -> None:
    import shutil

    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    (cache_dir / "runs" / "real").mkdir(parents=True)
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "result_manifest": "runs/real/real_001/result_manifest.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = cache_dir / "runs/real/real_001/result_manifest.json"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        json.dumps(
            {
                "run_id": "real_001",
                "candidate_id": "candidate_000001",
                "status": "failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = preserve_retention_evidence(
        cache_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    shutil.rmtree(cache_dir / "runs/real/real_001")
    retention = cache_dir / "state" / "run_retention" / "real_001.json"
    retention.parent.mkdir(parents=True)
    retention.write_text(
        json.dumps(
            {
                "run_id": "real_001",
                "local_action": "deleted",
                "remote_action": "deleted",
                "evidence_status": "preserved",
                "evidence_digest": evidence.digest,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uploaded: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            uploaded.append(str(remote_path))

        def upload(self, local_path, remote_path) -> None:
            uploaded.append(str(remote_path))

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    assert str(ref.remote_project_dir / "reports" / flow_report.name) in uploaded
    assert str(ref.remote_project_dir / "state") in uploaded
    assert not any("/runs/real/real_001" in path for path in uploaded)


def test_sync_cache_to_remote_merges_prior_inventory_for_continuation(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True)
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text('{"status": "pass"}\n', encoding="utf-8")
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "evaluation_index": index,
                    "run_id": run_id,
                    "result_manifest": (
                        f"runs/real/{run_id}/result_manifest.json"
                    ),
                }
            )
            + "\n"
            for index, run_id in enumerate(
                ("real_001", "real_002"),
                start=1,
            )
        ),
        encoding="utf-8",
    )
    old_result = PurePosixPath(
        "runs/real/real_001/result_manifest.json"
    )
    (reports_dir / "remote_run_artifacts.sha256").write_text(
        f"{'a' * 64}  {old_result.as_posix()}\n",
        encoding="utf-8",
    )
    (reports_dir / "remote_run_artifact_paths.txt").write_text(
        f"{old_result.as_posix()}\n",
        encoding="utf-8",
    )
    new_result = cache_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    new_result.parent.mkdir(parents=True)
    new_result.write_text('{"status": "failed"}\n', encoding="utf-8")

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            return None

        def upload(self, local_path, remote_path) -> None:
            return None

    _sync_cache_reports_to_remote(ref, cache_dir, RecordingRunner())

    final_inventory = (
        reports_dir / "remote_run_artifacts.sha256"
    ).read_text(encoding="utf-8")
    precommit_inventory = (
        cache_dir / ".remote_sync" / "remote_run_artifacts.precommit.sha256"
    ).read_text(encoding="utf-8")
    assert f"{'a' * 64}  {old_result.as_posix()}\n" in final_inventory
    assert "runs/real/real_002/result_manifest.json\n" in final_inventory
    assert f"{'a' * 64}  {old_result.as_posix()}\n" in precommit_inventory
    assert (
        "runs/real/real_002/result_manifest.pending.json\n"
        in precommit_inventory
    )


def test_archive_remote_flow_report_invalidates_stale_pass_marker() -> None:
    from hermes_workflow.remote_optimizer_flow import _archive_remote_flow_report

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[tuple[str, bool]] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            calls.append((command, kwargs.get("check", False)))
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    _archive_remote_flow_report(ref, RecordingRunner())

    assert calls == [
        (
            "if test -f /remote/project/reports/optimizer_flow_run_report.json; "
            "then mv -f -- "
            "/remote/project/reports/optimizer_flow_run_report.json "
            "/remote/project/reports/optimizer_flow_run_report.previous.json; fi",
            True,
        )
    ]


def test_begin_remote_attempt_invalidates_optimize_and_fix_run_markers() -> None:
    from hermes_workflow.remote_optimizer_flow import begin_remote_optimizer_attempt

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    commands: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            commands.append(command)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    lease = begin_remote_optimizer_attempt(ref, runner=RecordingRunner())

    assert len(commands) == 3
    assert "remote_attempt.lock" in commands[0]
    assert "optimizer_flow_run_report.previous.json" in commands[1]
    assert "fix_run_report.previous.json" in commands[2]

    lease.release()

    assert len(commands) == 4
    assert "rm -rf -- /remote/project/state/remote_attempt.lock" in commands[3]


def test_failure_evidence_sync_bypasses_incomplete_run_barrier(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _sync_failure_evidence_to_remote,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    flow_report = cache_dir / "reports" / "optimizer_flow_run_report.json"
    flow_report.parent.mkdir(parents=True)
    flow_report.write_text('{"status": "fail"}\n', encoding="utf-8")
    incomplete_metric = (
        cache_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    incomplete_metric.parent.mkdir(parents=True)
    incomplete_metric.write_text('{"status": "failed"}\n', encoding="utf-8")
    events: list[str] = []

    class RecordingRunner:
        def upload_tree(self, local_path, remote_path, **kwargs) -> None:
            events.append(f"tree:{PurePosixPath(remote_path).name}")

        def upload(self, local_path, remote_path) -> None:
            events.append(f"file:{PurePosixPath(remote_path).as_posix()}")

    _sync_failure_evidence_to_remote(ref, cache_dir, RecordingRunner())

    assert not any("/runs/" in event for event in events)
    assert events[-1] == (
        "file:/remote/project/reports/optimizer_flow_run_report.json"
    )


def test_normalize_remote_artifact_paths_removes_controller_cache_identity(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _normalize_remote_artifact_paths,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "controller-cache"
    execution_dir = cache_dir / "execution_package"
    reports_dir = cache_dir / "reports"
    execution_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    local_root = str(cache_dir.resolve())
    execution_manifest = execution_dir / "execution_manifest.json"
    execution_manifest.write_text(
        json.dumps({"source_project_dir": local_root}) + "\n",
        encoding="utf-8",
    )
    optimizer_manifest = execution_dir / "optimizer_execution_manifest.json"
    optimizer_manifest.write_text(
        json.dumps(
            {
                "project_dir": local_root,
                "command": ["hermes-workflow", "run-openbox-real", local_root],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    task = execution_dir / "OPTIMIZER_EXECUTION_TASK.md"
    task.write_text(f"Project: `{local_root}`\n", encoding="utf-8")
    flow_report = reports_dir / "optimizer_flow_run_report.json"
    flow_report.write_text(
        json.dumps(
            {
                "status": "pass",
                "project_dir": local_root,
                "steps": [
                    {"detail": f"report_path={local_root}/reports/result.json"}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _normalize_remote_artifact_paths(ref, cache_dir)

    for artifact in (execution_manifest, optimizer_manifest, task, flow_report):
        text = artifact.read_text(encoding="utf-8")
        assert local_root not in text
        assert "/remote/project" in text


def test_normalize_remote_artifact_paths_handles_windows_json_escaping(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_optimizer_flow import (
        _normalize_remote_artifact_paths,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / r"C:\Users\alice\controller-cache"
    execution_dir = cache_dir / "execution_package"
    execution_dir.mkdir(parents=True)
    controller_root = str(cache_dir.resolve())
    nested_path = f"{controller_root}\\runs\\real\\real_001"

    manifest = execution_dir / "execution_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "controller_root": controller_root,
                "records": [
                    {
                        "path": nested_path,
                        "attempt": 1,
                        "ready": True,
                        "error": None,
                    },
                    controller_root,
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    scalar_manifest = execution_dir / "controller_root.json"
    scalar_manifest.write_text(
        json.dumps(controller_root) + "\n",
        encoding="utf-8",
    )
    task = execution_dir / "OPTIMIZER_EXECUTION_TASK.md"
    task.write_text(f"Controller cache: `{controller_root}`\n", encoding="utf-8")

    _normalize_remote_artifact_paths(ref, cache_dir)

    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "controller_root": "/remote/project",
        "records": [
            {
                "path": "/remote/project\\runs\\real\\real_001",
                "attempt": 1,
                "ready": True,
                "error": None,
            },
            "/remote/project",
        ],
    }
    assert json.loads(scalar_manifest.read_text(encoding="utf-8")) == (
        "/remote/project"
    )
    assert task.read_text(encoding="utf-8") == (
        "Controller cache: `/remote/project`\n"
    )


def test_optimize_remote_project_syncs_failure_report_before_reraising(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    prepared = SimpleNamespace(
        status="pass",
        cache_dir=cache_dir,
        issues=[],
        requirement_report=SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        ),
        preparation_report=SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: prepared,
    )

    def fail_after_report(*args, **kwargs):
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "fail"}\n', encoding="utf-8")
        raise ValueError("optimizer failed")

    sync_calls: list[Path] = []
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fail_after_report,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        lambda ref, cache, runner: sync_calls.append(cache),
    )

    with pytest.raises(ValueError, match="optimizer failed"):
        optimize_remote_project(
            ref,
            real=True,
            max_evals=1,
            batch_size=1,
            parallel_jobs=1,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            cache_root=tmp_path,
            runner=object(),
        )

    assert sync_calls == [cache_dir]


def test_optimize_remote_project_publishes_fail_report_when_final_sync_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    prepared = SimpleNamespace(
        status="pass",
        cache_dir=cache_dir,
        issues=[],
        requirement_report=SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        ),
        preparation_report=SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: prepared,
    )

    def write_pass_report(*args, **kwargs):
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(
            json.dumps({"status": "pass", "issues": [], "steps": []}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(status="pass", report_path=report_path)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        write_pass_report,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("remote checksum mismatch")
        ),
    )
    published: list[dict[str, object]] = []

    def capture_failure(ref, cache, runner):
        published.append(
            json.loads(
                (cache / "reports" / "optimizer_flow_run_report.json").read_text(
                    encoding="utf-8"
                )
            )
        )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        capture_failure,
    )

    with pytest.raises(RuntimeError, match="remote checksum mismatch"):
        optimize_remote_project(
            ref,
            real=True,
            max_evals=1,
            batch_size=1,
            parallel_jobs=1,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            cache_root=tmp_path,
            runner=object(),
        )

    assert published[0]["status"] == "fail"
    assert any(
        "remote checksum mismatch" in str(issue)
        for issue in published[0]["issues"]
    )
    assert published[0]["steps"][-1]["name"] == "publish-remote-evidence"


def test_continue_remote_project_syncs_failure_report_before_reraising(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    _seed_optimizer_history(cache_dir)
    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_openbox_real_optimization",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("continuation failed")
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(ValueError, match="continuation failed"):
        continue_remote_project(
            ref,
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=2,
            parallel_jobs=2,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=_passed_remote_doctor_report(),
        )

    assert calls[-1] == "sync_reports"
    assert (cache_dir / "reports" / "optimizer_flow_run_report.json").is_file()


def test_continue_remote_project_publishes_fail_report_when_final_sync_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    _seed_optimizer_history(cache_dir)
    calls: list[str] = []
    _setup_continue_mocks(cache_dir, calls, monkeypatch)
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("continuation inventory mismatch")
        ),
    )
    published: list[dict[str, object]] = []

    def capture_failure(ref, cache, runner):
        published.append(
            json.loads(
                (cache / "reports" / "optimizer_flow_run_report.json").read_text(
                    encoding="utf-8"
                )
            )
        )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_failure_evidence_to_remote",
        capture_failure,
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(RuntimeError, match="continuation inventory mismatch"):
        continue_remote_project(
            ref,
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=2,
            parallel_jobs=2,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=_passed_remote_doctor_report(),
        )

    assert published[0]["status"] == "fail"
    assert any(
        "continuation inventory mismatch" in str(issue)
        for issue in published[0]["issues"]
    )
    assert published[0]["steps"][-1]["name"] == "publish-remote-evidence"


def test_optimize_remote_project_archives_stale_pass_before_doctor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    commands: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            commands.append(command)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("doctor transport failed")
        ),
    )

    with pytest.raises(RuntimeError, match="doctor transport failed"):
        optimize_remote_project(
            ref,
            real=True,
            max_evals=1,
            batch_size=1,
            parallel_jobs=1,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            cache_root=tmp_path,
            runner=RecordingRunner(),
        )

    assert len(commands) == 1
    assert "optimizer_flow_run_report.previous.json" in commands[0]


def test_optimize_remote_project_does_not_rearchive_cli_started_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    prepared = SimpleNamespace(
        status="pass",
        cache_dir=cache_dir,
        issues=[],
        requirement_report=SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        ),
        preparation_report=SimpleNamespace(status="pass", issues=[]),
    )
    commands: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            commands.append(command)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: prepared,
    )

    def write_pass_report(*args, **kwargs):
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(status="pass", report_path=report_path)

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        write_pass_report,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *args, **kwargs: None,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath(
            "/remote/project/cadence_env.csh"
        ),
        cache_root=tmp_path,
        runner=RecordingRunner(),
        doctor_report=SimpleNamespace(status="pass", issues=[]),
        attempt_started=True,
    )

    assert result.status == "pass"
    assert commands == []


def test_continue_remote_project_archives_stale_pass_before_prepare(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    commands: list[str] = []

    class RecordingRunner:
        def run(self, command: str, **kwargs) -> SimpleNamespace:
            commands.append(command)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("prepare transport failed")
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(RuntimeError, match="prepare transport failed"):
        continue_remote_project(
            ref,
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=2,
            parallel_jobs=2,
            cache_root=tmp_path,
            runner=RecordingRunner(),
            doctor_report=_passed_remote_doctor_report(),
        )

    assert len(commands) == 1
    assert "optimizer_flow_run_report.previous.json" in commands[0]


def test_continue_remote_project_runs_doctor_before_frozen_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct continuation call must revalidate the live Remote Host first."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    remote_cshrc = PurePosixPath("/remote/project/cadence_env.csh")
    remote_runner = object()
    events: list[str] = []

    def fake_doctor(*args: object, **kwargs: object) -> SimpleNamespace:
        assert args == (ref,)
        assert kwargs == {
            "runner": remote_runner,
            "cadence_cshrc": remote_cshrc,
            "cache_root": tmp_path,
        }
        events.append("doctor")
        return SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        )

    def stop_at_prepare(*args: object, **kwargs: object) -> object:
        events.append("frozen_prepare")
        raise RuntimeError("stop after ordering probe")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        fake_doctor,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        stop_at_prepare,
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(RuntimeError, match="stop after ordering probe"):
        continue_remote_project(
            ref,
            additional_evals=4,
            remote_cadence_cshrc=remote_cshrc,
            batch_size=2,
            parallel_jobs=2,
            cache_root=tmp_path,
            runner=remote_runner,
            attempt_started=True,
        )

    assert events == ["doctor", "frozen_prepare"]


def test_continue_remote_project_doctor_failure_stops_before_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[str] = []
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: (
            calls.append("doctor"),
            SimpleNamespace(
                status="fail",
                workflow_mode="optimize",
                issues=["remote environment changed"],
            ),
        )[-1],
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: pytest.fail(
            "frozen prepare must not run after doctor failure"
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *args, **kwargs: pytest.fail(
            "history sync must not run after doctor failure"
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(
        ValueError,
        match="remote doctor failed: remote environment changed",
    ):
        continue_remote_project(
            ref,
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=2,
            parallel_jobs=2,
            cache_root=tmp_path,
            runner=object(),
            attempt_started=True,
        )

    assert calls == ["doctor"]


def test_continue_remote_project_doctor_exception_stops_before_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("ssh reset during continuation doctor")
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: pytest.fail(
            "frozen prepare must not run after a doctor exception"
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(
        RuntimeError,
        match="ssh reset during continuation doctor",
    ):
        continue_remote_project(
            RemoteProjectRef("lab", PurePosixPath("/remote/project")),
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=object(),
            attempt_started=True,
        )


def test_continue_remote_project_reuses_same_attempt_doctor_report_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doctor_report = _passed_remote_doctor_report()
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: pytest.fail(
            "the same continuation attempt must not run doctor twice"
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("doctor report accepted")
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(RuntimeError, match="doctor report accepted"):
        continue_remote_project(
            RemoteProjectRef("lab", PurePosixPath("/remote/project")),
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=doctor_report,
            attempt_started=True,
        )


def test_continue_remote_project_rejects_non_optimize_doctor_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: pytest.fail(
            "frozen prepare must not run for a fix-run requirement"
        ),
    )

    from hermes_workflow.remote_optimizer_flow import continue_remote_project

    with pytest.raises(
        ValueError,
        match="remote continuation requires workflow mode 'optimize'",
    ):
        continue_remote_project(
            RemoteProjectRef("lab", PurePosixPath("/remote/project")),
            additional_evals=4,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            batch_size=None,
            parallel_jobs=None,
            cache_root=tmp_path,
            runner=object(),
            doctor_report=SimpleNamespace(
                status="pass",
                workflow_mode="fix_run",
                issues=[],
            ),
            attempt_started=True,
        )


# ---------------------------------------------------------------------------
# B-06 Remote run retention contract integration
# ---------------------------------------------------------------------------


def _set_keep_flags_for_retention_remote(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(spectre_path)
    payload["spectre"]["keep_failed_runs"] = keep_failed_runs
    payload["spectre"]["keep_successful_runs"] = keep_successful_runs
    _write_yaml(spectre_path, payload)


class _RemoteRetentionFakeRunner:
    """Records every runner.run() command and returns a successful default."""

    def __init__(self, missing_remote: bool = False) -> None:
        self.commands: list[str] = []
        self._missing_remote = missing_remote

    def upload_tree(
        self,
        _local_dir: Path,
        _remote_dir: PurePosixPath,
        **_kwargs: object,
    ) -> None:
        return None

    def run(self, command: str, **kwargs: object):
        from hermes_workflow.remote_ssh import RemoteCommandResult

        self.commands.append(command)
        # Probe for `test -d ...` returns 1 if missing, 0 otherwise.
        if command.startswith("test -d ") and self._missing_remote:
            return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])


def _adapter_run_result(
    *, run_id: str, status: str = "succeeded"
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        run_id=run_id,
        result_manifest_path=Path("/tmp/result.json"),
        metric_result_manifest_path=Path("/tmp/metrics.json"),
        issues=[],
    )


def _exercise_remote_candidate_and_final_retention(
    project_dir: Path,
    backend_kwargs: dict[str, object],
) -> SimpleNamespace:
    adapter = backend_kwargs["adapter"]
    result = adapter(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
    run_dir = project_dir / "runs/real/real_001"
    metric_relative = (
        "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    metric_path = project_dir / metric_relative
    metric_path.parent.mkdir(parents=True, exist_ok=True)
    metric_path.write_text(
        json.dumps({
            "schema_version": "1.0",
            "run_id": "real_001",
            "candidate_id": "candidate_000001",
            "status": "succeeded" if result.status == "succeeded" else "failed",
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "result_manifest.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "run_id": "real_001",
            "candidate_id": "candidate_000001",
            "status": result.status,
            "metric_result_manifest": metric_relative,
        }) + "\n",
        encoding="utf-8",
    )
    from hermes_workflow.run_retention import apply_local_run_retention

    apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=result.status == "succeeded",
    )
    callback = backend_kwargs["retention_callback"]
    issues = callback(
        project_dir,
        "real_001",
        "candidate_000001",
        result.status == "succeeded",
    )
    assert issues == []
    return result


def test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_successful_runs_false_single_tb(
    tmp_path: Path, monkeypatch
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir, keep_failed_runs=True, keep_successful_runs=False
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    def fake_single(local_project: Path, *, run_id: str, **kwargs: object):
        return _adapter_run_result(run_id=run_id, status="succeeded")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        fake_single,
    )

    def fake_native_turbo(project_dir, **kwargs):
        result = _exercise_remote_candidate_and_final_retention(project_dir, kwargs)
        assert result.status == "succeeded"
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    rm_commands = [c for c in runner.commands if c.startswith("rm -rf -- ")]
    assert len(rm_commands) == 1, runner.commands
    assert "/remote/project/runs/real/real_001" in rm_commands[0]
    decision = json.loads(
        (cache_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["remote_action"] == "deleted"
    assert decision["run_status"] == "successful"
    assert decision["remote_run_dir"] == "/remote/project/runs/real/real_001"


def test_remote_retention_callback_uses_final_record_failure_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir,
        keep_failed_runs=True,
        keep_successful_runs=False,
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            cache_dir=cache_dir,
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    def fake_native_turbo(project_dir: Path, **kwargs: object) -> object:
        callback = kwargs["retention_callback"]
        issues = callback(
            project_dir,
            "real_001",
            "candidate_000001",
            False,
        )
        assert issues == []
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir: Path, **kwargs: object) -> object:
        kwargs["services"].run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    assert not [command for command in runner.commands if command.startswith("rm -rf")]
    decision = json.loads(
        (cache_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["run_status"] == "failed"
    assert decision["remote_action"] == "kept"


def test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_successful_runs_false_multi_tb(
    tmp_path: Path, monkeypatch
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir, keep_failed_runs=True, keep_successful_runs=False
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    multi_calls: list[str] = []

    def fake_multi(local_project: Path, *, run_id: str, **kwargs: object):
        multi_calls.append(run_id)
        return _adapter_run_result(run_id=run_id, status="succeeded")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_multi_testbench_adapter",
        fake_multi,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.assert_valid_project",
        lambda _p: SimpleNamespace(
            testbenches=SimpleNamespace(
                testbenches=[SimpleNamespace(id="tb1"), SimpleNamespace(id="tb2")]
            ),
            process_corners=None,
        ),
    )

    def fake_native_turbo(project_dir, **kwargs):
        result = _exercise_remote_candidate_and_final_retention(project_dir, kwargs)
        assert result.status == "succeeded"
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    rm_commands = [c for c in runner.commands if c.startswith("rm -rf -- ")]
    assert len(rm_commands) == 1, (
        f"expected exactly ONE remote retention rm at parent run level, "
        f"got: {runner.commands}"
    )
    assert "/remote/project/runs/real/real_001" in rm_commands[0]


def test_remote_adapter_wrapper_keeps_remote_run_dir_when_keep_successful_runs_true(
    tmp_path: Path, monkeypatch
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir, keep_failed_runs=True, keep_successful_runs=True
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda local_project, *, run_id, **kw: _adapter_run_result(
            run_id=run_id, status="succeeded"
        ),
    )

    def fake_native_turbo(project_dir, **kwargs):
        _exercise_remote_candidate_and_final_retention(project_dir, kwargs)
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    # When keep_successful_runs=true, no rm command must be issued.
    rm_commands = [c for c in runner.commands if c.startswith("rm -rf")]
    assert rm_commands == [], runner.commands
    decision = json.loads(
        (cache_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["remote_action"] == "kept"


def test_remote_adapter_wrapper_deletes_remote_run_dir_when_keep_failed_runs_false_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir, keep_failed_runs=False, keep_successful_runs=True
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda local_project, *, run_id, **kw: _adapter_run_result(
            run_id=run_id, status="failed"
        ),
    )

    def fake_native_turbo(project_dir, **kwargs):
        result = _exercise_remote_candidate_and_final_retention(project_dir, kwargs)
        assert result.status == "failed"
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    rm_commands = [c for c in runner.commands if c.startswith("rm -rf -- ")]
    assert len(rm_commands) == 1, runner.commands
    assert "/remote/project/runs/real/real_001" in rm_commands[0]
    decision = json.loads(
        (cache_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["remote_action"] == "deleted"
    assert decision["run_status"] == "failed"


def test_remote_adapter_wrapper_remote_command_has_no_glob_and_is_under_remote_project_dir(
    tmp_path: Path, monkeypatch
) -> None:
    from hermes_workflow.remote_optimizer_flow import optimize_remote_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache" / "project"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_keep_flags_for_retention_remote(
        cache_dir, keep_failed_runs=True, keep_successful_runs=False
    )
    runner = _RemoteRetentionFakeRunner()

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_spectre_ocean_adapter",
        lambda local_project, *, run_id, **kw: _adapter_run_result(
            run_id=run_id, status="succeeded"
        ),
    )

    def fake_native_turbo(project_dir, **kwargs):
        _exercise_remote_candidate_and_final_retention(project_dir, kwargs)
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        return SimpleNamespace(status="pass", recommended_run_id="real_001")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    optimize_remote_project(
        ref,
        real=True,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=runner,
    )

    rm_commands = [c for c in runner.commands if c.startswith("rm -rf -- ")]
    assert len(rm_commands) == 1
    cmd = rm_commands[0]
    # Glob safety: literal command must not contain glob metacharacters in the path.
    assert "*" not in cmd
    assert "?" not in cmd
    assert ".." not in cmd
    # Must be quoted under the remote project dir.
    assert "/remote/project/runs/real/real_001" in cmd
    # The exact form is `rm -rf -- '<path>'`.
    assert cmd == "rm -rf -- /remote/project/runs/real/real_001"


def test_remote_optimizer_flow_syncs_updated_state_in_both_directions(
    tmp_path: Path,
) -> None:
    """B-09 regression: the cache <-> remote sync helpers must carry
    state/optimizer_state.json in both directions so the corrected
    progress contract is mirrored locally and remotely."""
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
        _sync_remote_history_to_cache,
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    state_dir = cache_dir / "state"
    state_dir.mkdir()
    state_path = state_dir / "optimizer_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "current_evaluations": 10,
                "recorded_observation_count": 7,
                "failed_evaluation_count": 3,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    upload_calls: list[tuple[Path, PurePosixPath]] = []
    download_calls: list[tuple[PurePosixPath, Path]] = []

    class FakeSSH:
        def run(self, command: str):
            return SimpleNamespace(return_code=0, stderr="")

        def upload_tree(self, local_dir: Path, remote_dir: PurePosixPath) -> None:
            upload_calls.append((Path(local_dir), PurePosixPath(str(remote_dir))))

        def download_tree(
            self, remote_dir: PurePosixPath, local_dir: Path
        ) -> None:
            download_calls.append(
                (PurePosixPath(str(remote_dir)), Path(local_dir))
            )

    _sync_cache_reports_to_remote(ref, cache_dir, FakeSSH())
    state_uploads = [
        call for call in upload_calls if call[1].name == "state"
    ]
    assert state_uploads, (
        "state/ must be uploaded back to the remote project in remote sync"
    )
    assert state_uploads[0][0] == state_dir
    assert state_uploads[0][1] == PurePosixPath("/remote/project/state")

    _sync_remote_history_to_cache(ref, cache_dir, FakeSSH())
    state_downloads = [
        call for call in download_calls if call[0].name == "state"
    ]
    assert state_downloads, (
        "state/ must be downloaded from the remote project to the cache"
    )
    assert state_downloads[0][0] == PurePosixPath("/remote/project/state")
    assert state_downloads[0][1] == cache_dir / "state"


# ---------------------------------------------------------------------------
# CPU thread limit runtime audit remote parity (B-11)
# ---------------------------------------------------------------------------


def test_remote_optimizer_audit_records_remote_transport_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """Remote optimizer audit must keep backend execution mode separate
    from remote transport mode."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    _create_remote_optimizer_project(cache_dir.parent, name=cache_dir.name)
    _set_optimizer_strategy(cache_dir, "turbo_trust_region", "turbo")

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *a, **k: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *a, **k: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_remote_history_to_cache",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow._sync_cache_reports_to_remote",
        lambda *a, **k: None,
    )

    def fake_native_turbo(project_dir: Path, **kwargs: object) -> object:
        # Write a fake report with runtime_thread_limits
        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        audit_path = reports_dir / "optimizer_effectiveness_audit.json"
        audit_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "backend": "native_turbo",
                    "runtime_thread_limits": {
                        "source": "optimizer.optimizer_cpu_threads",
                        "requested_threads": 32,
                        "effective_threads": 32,
                        "backend": "native_turbo",
                        "execution_mode": "local",
                        "process_scope": "local_optimizer_process",
                        "transport_mode": "remote",
                        "env_vars": {"OMP_NUM_THREADS": "32"},
                        "threadpoolctl": {"available": False, "libraries": []},
                        "torch": {"available": False},
                        "issues": [],
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(report_path=reports_dir / "turbo.json")

    def fake_optimize_project(project_dir: Path, **kwargs: object) -> object:
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.optimize_project",
        fake_optimize_project,
    )

    result = optimize_remote_project(
        ref,
        real=True,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        cache_root=tmp_path,
        runner=object(),
    )

    assert result.status == "pass"
    # Verify the audit file was written with correct execution_mode
    audit = json.loads(
        (cache_dir / "reports" / "optimizer_effectiveness_audit.json").read_text(
            encoding="utf-8"
        )
    )
    rtl = audit["runtime_thread_limits"]
    assert rtl["execution_mode"] == "local"
    assert rtl["process_scope"] == "local_optimizer_process"
    assert rtl["transport_mode"] == "remote"
    # Remote optimizer CPU threads must NOT be overridden
    assert rtl["requested_threads"] == 32
