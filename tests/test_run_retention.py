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


def _make_manifest_run_dir(
    project_dir: Path,
    run_id: str = "real_001",
    candidate_id: str = "candidate_000001",
) -> Path:
    run_dir = project_dir / "runs" / "real" / run_id
    metric_relative = (
        f"runs/real/{run_id}/metrics/metric_result_manifest.json"
    )
    metric_path = project_dir / metric_relative
    metric_path.parent.mkdir(parents=True, exist_ok=True)
    metric_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "candidate_id": candidate_id,
                "status": "succeeded",
                "metrics": {"gain": {"value": 12.0, "unit": "dB"}},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "result_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "candidate_id": candidate_id,
                "status": "succeeded",
                "metric_result_manifest": metric_relative,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "psf").mkdir()
    (run_dir / "psf" / "large.raw").write_bytes(b"not retention evidence")
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
    run_dir = _make_manifest_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "deleted"
    assert decision.run_status == "successful"
    assert not run_dir.exists()


def test_local_retention_preserves_only_parent_manifests_before_deleting_run(
    tmp_path: Path,
) -> None:
    from hermes_workflow.run_retention import apply_local_run_retention
    from hermes_workflow.retention_evidence import (
        materialize_retention_evidence,
    )

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=False)
    run_dir = _make_manifest_run_dir(project_dir)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "deleted"
    assert decision.evidence_status == "preserved"
    assert len(decision.evidence_digest) == 64
    assert not run_dir.exists()
    supplementary = materialize_retention_evidence(project_dir)
    assert supplementary is not None
    assert (
        supplementary / "runs/real/real_001/result_manifest.json"
    ).is_file()
    assert (
        supplementary
        / "runs/real/real_001/metrics/metric_result_manifest.json"
    ).is_file()
    evidence_files = [
        path.relative_to(project_dir).as_posix()
        for path in (project_dir / "state/run_retention_evidence").rglob("*")
        if path.is_file()
    ]
    assert not any("psf" in path or "large.raw" in path for path in evidence_files)


def test_local_retention_does_not_delete_unique_run_when_evidence_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_workflow import retention_evidence
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    run_dir = _make_manifest_run_dir(project_dir)

    def fail_copy(_source: object, _destination: object) -> None:
        raise OSError("synthetic-evidence-copy-failure")

    monkeypatch.setattr(retention_evidence.shutil, "copy2", fail_copy)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "failed"
    assert decision.evidence_status == "not_required"
    assert run_dir.is_dir()
    assert any("synthetic-evidence-copy-failure" in issue for issue in decision.issues)


def test_local_retention_does_not_delete_unique_run_when_evidence_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_workflow import retention_evidence
    from hermes_workflow.run_retention import apply_local_run_retention

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    run_dir = _make_manifest_run_dir(project_dir)
    original_write_text = retention_evidence.Path.write_text

    def fail_evidence_index(
        path: Path,
        data: str,
        *args: object,
        **kwargs: object,
    ) -> int:
        if path.name == "evidence.json":
            raise OSError("synthetic-evidence-write-failure")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(retention_evidence.Path, "write_text", fail_evidence_index)

    decision = apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.local_action == "failed"
    assert run_dir.is_dir()
    assert any("synthetic-evidence-write-failure" in issue for issue in decision.issues)


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("digest", "checksum mismatch"),
        ("payload", "run_id does not match"),
        ("path", "canonical path is invalid"),
    ],
)
def test_materialized_retention_evidence_fails_closed_on_corruption(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    from hermes_workflow.package import sha256_file
    from hermes_workflow.retention_evidence import (
        materialize_retention_evidence,
        preserve_retention_evidence,
    )

    project_dir = _create_retention_project(tmp_path)
    _make_manifest_run_dir(project_dir)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    index_path = evidence.bundle_path / "evidence.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    result_path = evidence.bundle_path / "artifacts/result_manifest.json"
    if corruption == "digest":
        result_path.write_text("{}\n", encoding="utf-8")
    elif corruption == "payload":
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["run_id"] = "real_002"
        result_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        index["artifacts"][0]["sha256"] = sha256_file(result_path)
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        index["artifacts"][0]["canonical_path"] = (
            "runs/real/real_999/result_manifest.json"
        )
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if corruption != "digest":
        (evidence.bundle_path / "checksums.sha256").write_text(
            "".join(
                f"{entry['sha256']}  {entry['bundle_path']}\n"
                for entry in index["artifacts"]
            )
            + f"{sha256_file(index_path)}  evidence.json\n",
            encoding="utf-8",
        )

    with pytest.raises(RuntimeError, match=message):
        materialize_retention_evidence(project_dir)


@pytest.mark.parametrize(
    ("extra_kind", "message"),
    [
        ("file", "contents do not match"),
        ("directory", "unexpected directory"),
        ("symlink", "symbolic link"),
    ],
)
def test_retention_evidence_bundle_rejects_undeclared_entries(
    tmp_path: Path,
    extra_kind: str,
    message: str,
) -> None:
    from hermes_workflow.retention_evidence import (
        materialize_retention_evidence,
        preserve_retention_evidence,
    )

    project_dir = _create_retention_project(tmp_path)
    _make_manifest_run_dir(project_dir)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    extra = evidence.bundle_path / "undeclared"
    if extra_kind == "file":
        extra.write_text("stale overlay\n", encoding="utf-8")
    elif extra_kind == "directory":
        extra.mkdir()
    else:
        extra.symlink_to(evidence.bundle_path / "evidence.json")

    with pytest.raises(RuntimeError, match=message):
        materialize_retention_evidence(project_dir)


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
    run_dir = _make_manifest_run_dir(project_dir)

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
    _make_manifest_run_dir(project_dir)

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
    _make_manifest_run_dir(project_dir)

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

    def __init__(
        self,
        *,
        missing_remote: bool = False,
        probe_return_code: int | None = None,
    ) -> None:
        self.commands: list[str] = []
        self.uploaded_trees: list[tuple[Path, PurePosixPath, bool]] = []
        self._missing_remote = missing_remote
        self._probe_return_code = probe_return_code

    def upload_tree(
        self,
        local_dir: Path,
        remote_dir: PurePosixPath,
        *,
        replace: bool = False,
    ) -> None:
        self.uploaded_trees.append((local_dir, remote_dir, replace))

    def run(self, command: str, **_: object):
        from hermes_workflow.remote_ssh import RemoteCommandResult

        self.commands.append(command)
        if command.startswith("test -d ") and self._probe_return_code is not None:
            return RemoteCommandResult(
                self._probe_return_code,
                "",
                "transport failed",
                ["ssh", "lab", command],
            )
        if command.startswith("test -d ") and self._missing_remote:
            return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])


def _remote_ref() -> SimpleNamespace:
    return SimpleNamespace(remote_project_dir=PurePosixPath("/remote/project"))


def test_remote_retention_does_not_classify_ssh_failure_as_missing(
    tmp_path: Path,
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)

    decision = module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=_RetentionFakeRunner(probe_return_code=255),
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.remote_action == "failed"
    assert any("transport failed" in issue for issue in decision.issues)


def test_remote_retention_publishes_verified_evidence_before_deleting_run(
    tmp_path: Path,
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_manifest_run_dir(project_dir)
    runner = _RetentionFakeRunner()

    decision = module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=runner,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.remote_action == "deleted"
    assert decision.evidence_status == "preserved"
    assert len(decision.evidence_digest or "") == 64
    assert runner.uploaded_trees[0][2] is True
    verification_index = next(
        index
        for index, command in enumerate(runner.commands)
        if "sha256sum --quiet -c -- checksums.sha256" in command
    )
    deletion_index = next(
        index
        for index, command in enumerate(runner.commands)
        if command.startswith("rm -rf -- ")
    )
    assert verification_index < deletion_index


def test_remote_retention_does_not_delete_when_evidence_upload_fails(
    tmp_path: Path,
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_manifest_run_dir(project_dir)

    class _UploadFailureRunner(_RetentionFakeRunner):
        def upload_tree(
            self,
            _local_dir: Path,
            _remote_dir: PurePosixPath,
            *,
            replace: bool = False,
        ) -> None:
            raise OSError("synthetic-evidence-upload-failure")

    runner = _UploadFailureRunner()
    decision = module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=runner,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
    )

    assert decision.remote_action == "failed"
    assert not any(command.startswith("rm -rf -- ") for command in runner.commands)
    assert any("synthetic-evidence-upload-failure" in issue for issue in decision.issues)


def test_local_retention_after_remote_preserves_remote_fields_in_decision_report(
    tmp_path: Path,
) -> None:
    """Regression: remote retention runs first, then local retention. The final
    state/run_retention/<run_id>.json must preserve remote_action and
    remote_run_dir written by the remote step."""
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_manifest_run_dir(project_dir)

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
    _make_manifest_run_dir(project_dir)

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
    _make_manifest_run_dir(project_dir)

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


def test_reused_run_id_starts_a_new_retention_attempt_instead_of_merging_stale_state(
    tmp_path: Path,
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_manifest_run_dir(project_dir)
    first_local = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-08-11T00:00:00Z",
    )
    module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=_RetentionFakeRunner(),
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-08-11T00:00:00Z",
    )
    assert first_local.local_action == "deleted"

    _set_keep_flags(project_dir, keep_failed_runs=True, keep_successful_runs=True)
    second_run = _make_manifest_run_dir(project_dir)
    result_path = second_run / "result_manifest.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["status"] = "failed"
    result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")
    second_local = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=False,
        now_utc="2026-08-12T00:00:00Z",
    )
    second = module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=_RetentionFakeRunner(),
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=False,
        now_utc="2026-08-12T00:00:00Z",
    )

    assert second_local.local_action == "kept"
    assert second.run_status == "failed"
    assert second.keep_failed_runs is True
    assert second.keep_successful_runs is True
    assert second.local_action == "kept"
    assert second.remote_action == "kept"
    assert second.evidence_status == "not_required"
    assert second.evidence_path is None
    assert second.evidence_digest is None
    assert second.decided_at_utc == "2026-08-12T00:00:00Z"
    assert second.attempt_identity != first_local.attempt_identity


def test_identical_manifest_reuse_resets_deleted_attempt_provenance(
    tmp_path: Path,
) -> None:
    from hermes_workflow import run_retention as module

    project_dir = _create_retention_project(tmp_path)
    _set_keep_flags(project_dir, keep_failed_runs=False, keep_successful_runs=False)
    _make_manifest_run_dir(project_dir)
    first = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-08-11T00:00:00Z",
    )
    module.apply_remote_run_retention(
        project_dir,
        remote_ref=_remote_ref(),
        runner=_RetentionFakeRunner(),
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-08-11T00:00:00Z",
    )

    _make_manifest_run_dir(project_dir)
    second = module.apply_local_run_retention(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
        run_succeeded=True,
        now_utc="2026-08-12T00:00:00Z",
    )

    assert second.attempt_identity == first.attempt_identity
    assert second.decided_at_utc == "2026-08-12T00:00:00Z"
    assert second.local_action == "deleted"
    assert second.remote_action == "not_applicable"
    assert second.issues == []
