from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
import yaml

from tests.project_factory import create_generic_project


def _create_retention_project(tmp_path: Path) -> Path:
    return create_generic_project(tmp_path, name="retention_project")


def _set_keep_flags(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    """Edit config/spectre.yaml to set the two retention flags."""
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    spectre = payload.setdefault("spectre", {})
    spectre["keep_failed_runs"] = keep_failed_runs
    spectre["keep_successful_runs"] = keep_successful_runs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _make_run_dir(project_dir: Path, run_id: str = "real_001") -> Path:
    run_dir = project_dir / "runs" / "real" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "sentinel.txt").write_text("hello\n", encoding="utf-8")
    return run_dir


def test_load_run_retention_policy_reads_spectre_settings(tmp_path: Path) -> None:
    from hermes_workflow.run_retention import load_run_retention_policy

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=True)

    policy = load_run_retention_policy(project_dir)
    assert policy.keep_failed_runs is False
    assert policy.keep_successful_runs is True
    assert policy.source == "Spectre Settings"


def test_apply_local_run_retention_keeps_successful_run_when_keep_successful_runs_true(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=True)
    run_dir = _make_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "kept"
    assert decision.run_status == "successful"
    assert run_dir.exists()
    assert (run_dir / "sentinel.txt").exists()


def test_apply_local_run_retention_deletes_successful_run_when_keep_successful_runs_false(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=False)
    run_dir = _make_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "deleted"
    assert decision.run_status == "successful"
    assert not run_dir.exists()


def test_apply_local_run_retention_keeps_failed_run_when_keep_failed_runs_true(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=False)
    run_dir = _make_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id=None,
        run_succeeded=False,
    )

    assert decision.local_action == "kept"
    assert decision.run_status == "failed"
    assert run_dir.exists()


def test_apply_local_run_retention_deletes_failed_run_when_keep_failed_runs_false(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=True)
    run_dir = _make_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=False,
    )

    assert decision.local_action == "deleted"
    assert decision.run_status == "failed"
    assert not run_dir.exists()


def test_apply_local_run_retention_writes_decision_report_with_required_fields(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=False)
    _make_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-06-14T00:00:00Z",
    )

    report_path = project_dir / "state" / "run_retention" / "real_001.json"
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    for key in (
        "schema_version",
        "run_id",
        "candidate_id",
        "run_status",
        "policy_source",
        "keep_failed_runs",
        "keep_successful_runs",
        "local_action",
        "remote_action",
        "local_run_dir",
        "remote_run_dir",
        "issues",
        "decided_at_utc",
    ):
        assert key in payload, f"missing key {key} in decision report"

    assert payload["schema_version"] == "1.0"
    assert payload["run_id"] == "real_001"
    assert payload["candidate_id"] == "candidate_000001"
    assert payload["run_status"] == "successful"
    assert payload["policy_source"] == "Spectre Settings"
    assert payload["keep_failed_runs"] is True
    assert payload["keep_successful_runs"] is False
    assert payload["local_action"] == "deleted"
    assert payload["remote_action"] == "not_applicable"
    assert payload["remote_run_dir"] is None
    assert payload["decided_at_utc"] == "2026-06-14T00:00:00Z"
    assert decision.local_run_dir == payload["local_run_dir"]


def test_apply_local_run_retention_records_missing_when_run_dir_does_not_exist(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    # Note: no run dir created.

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )
    assert decision.local_action == "missing"


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "../real_001",
        "real_xxx",
        "real_001/extra",
        "real_1",
        "real_0001",
        "REAL_001",
        "",
        "real_001*",
        "real_001?",
        "real_001\n",
    ],
)
def test_apply_local_run_retention_rejects_unsafe_run_id(
    tmp_path: Path, bad_run_id: str
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)

    with pytest.raises(ValueError):
        apply_local_run_retention(
            project_dir,
            run_id=bad_run_id,
            candidate_id=None,
            run_succeeded=True,
        )


def test_apply_local_run_retention_records_failed_when_rmtree_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=False)
    _make_run_dir(project_dir)

    def boom(_path: object) -> None:
        raise OSError("synthetic-rmtree-failure")

    monkeypatch.setattr(module.shutil, "rmtree", boom)

    decision = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "failed"
    assert any("synthetic-rmtree-failure" in i for i in decision.issues)


class _RetentionFakeRunner:
    """Minimal SSH runner stub for direct apply_remote_run_retention tests.

    Records every command and returns the supplied probe/rm return code.
    """

    def __init__(self, *, missing_remote: bool = False) -> None:
        self.commands: list[str] = []
        self._missing_remote = missing_remote

    def run(self, command: str, **_: object):
        from hermes_workflow.remote_ssh import RemoteCommandResult

        self.commands.append(command)
        if command.startswith("test -d ") and self._missing_remote:
            return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])


def _remote_ref() -> SimpleNamespace:
    return SimpleNamespace(remote_project_dir=PurePosixPath("/remote/project"))


def test_local_retention_after_remote_preserves_remote_fields_in_decision_report(
    tmp_path: Path,
) -> None:
    """Regression: remote retention runs first, then local retention. The final
    state/run_retention/<run_id>.json must preserve remote_action and
    remote_run_dir written by the remote step."""
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_run_dir(project_dir)

    runner = _RetentionFakeRunner()
    remote_decision = module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=runner,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )
    assert remote_decision.remote_action == "deleted"
    assert remote_decision.remote_run_dir == "/remote/project/runs/real/real_001"

    local_decision = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    report_path = project_dir / "state" / "run_retention" / "real_001.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["local_action"] == "deleted"
    assert payload["remote_action"] == "deleted"
    assert payload["remote_run_dir"] == "/remote/project/runs/real/real_001"
    assert payload["run_status"] == "successful"
    assert payload["candidate_id"] == "candidate_000001"
    # The returned decision must agree with the persisted report.
    assert local_decision.remote_action == "deleted"
    assert local_decision.remote_run_dir == "/remote/project/runs/real/real_001"
    assert local_decision.local_action == "deleted"


def test_remote_retention_after_local_preserves_local_fields_in_decision_report(
    tmp_path: Path,
) -> None:
    """Reverse order: local retention first, then remote retention. The final
    decision report must preserve local_action and local_run_dir from local."""
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_run_dir(project_dir)

    local_decision = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )
    assert local_decision.local_action == "deleted"

    runner = _RetentionFakeRunner()
    module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=runner,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    report_path = project_dir / "state" / "run_retention" / "real_001.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["local_action"] == "deleted"
    assert payload["remote_action"] == "deleted"
    assert payload["remote_run_dir"] == "/remote/project/runs/real/real_001"
    assert payload["local_run_dir"].endswith("runs/real/real_001")
    assert payload["run_status"] == "successful"


def test_local_retention_preserves_existing_remote_issues_when_merging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issues recorded by an earlier remote retention failure must survive the
    later local retention write — local must not silently drop them."""
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_run_dir(project_dir)

    class _BoomRunner(_RetentionFakeRunner):
        def run(self, command: str, **kwargs: object):
            from hermes_workflow.remote_ssh import RemoteCommandResult

            self.commands.append(command)
            if command.startswith("test -d "):
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            raise RuntimeError("synthetic-remote-rm-failure")

    runner = _BoomRunner()
    module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=runner,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=False,
    )

    module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=False,
    )

    payload = json.loads(
        (project_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["remote_action"] == "failed"
    assert any("synthetic-remote-rm-failure" in i for i in payload["issues"])
    assert payload["local_action"] == "deleted"
