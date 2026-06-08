from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from hermes_workflow.remote_optimizer_flow import optimize_remote_project
from hermes_workflow.remote_project import RemoteProjectRef


def test_optimize_remote_project_runs_doctor_prepare_openbox_and_sync(tmp_path: Path, monkeypatch) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[str] = []
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )

    def fake_optimize_project(project_dir: Path, **kwargs):
        calls.append("optimize_project")
        assert project_dir == cache_dir
        assert kwargs["real"] is True
        assert kwargs["execution_agent"] == "direct"
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

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
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
    assert "adapter" in captured_kwargs


def test_continue_remote_project_ensures_manifest_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """When execution_package is missing (not synced), it must build it."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    # No execution_package directory

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


def test_continue_remote_project_passes_openbox_strategy_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    """Remote continuation must pass surrogate_type, acq_type, acq_optimizer_type
    matching the local continuation defaults (prf, eic, local_random)."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "execution_package").mkdir()
    ((cache_dir / "execution_package") / "execution_manifest.json").write_text("{}")

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
        batch_size=2,
        parallel_jobs=2,
        cache_root=tmp_path,
        runner=object(),
    )

    assert captured_kwargs["surrogate_type"] == "prf"
    assert captured_kwargs["acq_type"] == "eic"
    assert captured_kwargs["acq_optimizer_type"] == "local_random"


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
        def exists(self, path):
            return True

        def download_tree(self, remote, local):
            raise OSError("connection reset")

    import pytest

    with pytest.raises(RuntimeError, match="ledger"):
        _sync_remote_history_to_cache(ref, cache_dir, FakeSSH())
