from __future__ import annotations

import json
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
    (reports / "optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1}\n', encoding="utf-8"
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
    )

    assert captured_kwargs["additional_evals"] == 4
    assert captured_kwargs["continue_from_existing"] is True
    assert captured_kwargs["max_evals"] is None
    assert captured_kwargs["batch_size"] == 2
    assert captured_kwargs["parallel_jobs"] == 2
    assert captured_kwargs["strategy"] is None
    assert "adapter" in captured_kwargs


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
    )

    assert result.status == "pass"
    assert result.recommended_run_id == "real_141"
    assert "optimize_project" not in calls
    assert calls[0] == "sync_history"
    assert "run_openbox" in calls
    assert calls[-1] == "sync_reports"


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

    with pytest.raises(RuntimeError, match="Failed to probe remote history"):
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
    from hermes_workflow.remote_optimizer_flow import (
        _sync_cache_reports_to_remote,
    )

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
    retention = cache_dir / "state" / "run_retention" / "real_001.json"
    retention.parent.mkdir(parents=True)
    retention.write_text(
        json.dumps(
            {
                "run_id": "real_001",
                "local_action": "deleted",
                "remote_action": "deleted",
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
        )

    assert len(commands) == 1
    assert "optimizer_flow_run_report.previous.json" in commands[0]


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

    captured_adapter: list[object] = []

    def fake_native_turbo(project_dir, **kwargs):
        captured_adapter.append(kwargs["adapter"])
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        # Exercise the wrapper: this records adapter as a closure.
        services.run_batch_native_turbo_optimization(project_dir)
        wrapper = captured_adapter[0]
        # Call wrapper with run_id=real_001 to trigger retention.
        result = wrapper(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
        assert result.status == "succeeded"
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

    captured_adapter: list[object] = []

    def fake_native_turbo(project_dir, **kwargs):
        captured_adapter.append(kwargs["adapter"])
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        wrapper = captured_adapter[0]
        result = wrapper(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
        assert result.status == "succeeded"
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

    captured_adapter: list[object] = []

    def fake_native_turbo(project_dir, **kwargs):
        captured_adapter.append(kwargs["adapter"])
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        wrapper = captured_adapter[0]
        wrapper(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
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

    captured_adapter: list[object] = []

    def fake_native_turbo(project_dir, **kwargs):
        captured_adapter.append(kwargs["adapter"])
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        wrapper = captured_adapter[0]
        wrapper(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
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

    captured_adapter: list[object] = []

    def fake_native_turbo(project_dir, **kwargs):
        captured_adapter.append(kwargs["adapter"])
        return SimpleNamespace(report_path=Path("/tmp/x"))

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_batch_native_turbo_optimization",
        fake_native_turbo,
    )

    def fake_optimize_project(project_dir, **kwargs):
        services = kwargs["services"]
        services.run_batch_native_turbo_optimization(project_dir)
        wrapper = captured_adapter[0]
        wrapper(project_dir, run_id="real_001", cadence_cshrc=Path("x"))
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
