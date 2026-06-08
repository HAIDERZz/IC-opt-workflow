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


def test_continue_remote_project_syncs_history_and_runs_additional_evals(tmp_path: Path, monkeypatch) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = tmp_path / "cache"
    calls: list[str] = []

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

    def fake_optimize_project(project_dir: Path, **kwargs):
        calls.append("optimize_project")
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_141",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr("hermes_workflow.remote_optimizer_flow.optimize_project", fake_optimize_project)

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
    assert calls == ["sync_history", "optimize_project", "sync_reports"]


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
