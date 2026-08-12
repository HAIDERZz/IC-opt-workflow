from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from hermes_workflow.package import sha256_file
from hermes_workflow.remote_history_manifests import (
    materialize_remote_history_manifests,
)
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.retention_evidence import RetentionEvidence
from tests.project_factory import create_generic_project


RESULT_RELATIVE = PurePosixPath(
    "runs/real/real_001/result_manifest.json"
)
METRIC_RELATIVE = PurePosixPath(
    "runs/real/real_001/metrics/metric_result_manifest.json"
)


def _write_remote_deleted_decision(
    cache_dir: Path,
    evidence: RetentionEvidence,
) -> None:
    path = cache_dir / "state/run_retention" / f"{evidence.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": evidence.run_id,
                "remote_action": "deleted",
                "evidence_status": "preserved",
                "evidence_digest": evidence.digest,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _seed_history_bundle(
    tmp_path: Path,
) -> tuple[RemoteProjectRef, Path, Path, Path]:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = create_generic_project(tmp_path, name="cache")
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    history_path = reports_dir / "optimizer_evaluations.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "status": "feasible",
                "result_manifest": RESULT_RELATIVE.as_posix(),
                "metric_result_manifest": METRIC_RELATIVE.as_posix(),
            }
        )
        + "\n",
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
            RESULT_RELATIVE,
            {
                "run_id": "real_001",
                "status": "succeeded",
                "metric_result_manifest": METRIC_RELATIVE.as_posix(),
            },
        ),
        (METRIC_RELATIVE, {"run_id": "real_001", "status": "succeeded"}),
    ):
        path = remote_source.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (reports_dir / "remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_source.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (RESULT_RELATIVE, METRIC_RELATIVE)
        ),
        encoding="utf-8",
    )
    return ref, cache_dir, history_path, remote_source


class BundleRunner:
    profile = "lab"

    def __init__(
        self,
        remote_source: Path,
        *,
        remote_return_code: int = 0,
        download_error: Exception | None = None,
    ) -> None:
        self.remote_source = remote_source
        self.remote_return_code = remote_return_code
        self.download_error = download_error
        self.commands: list[str] = []
        self.downloads: list[tuple[PurePosixPath, ...]] = []

    def run(self, command: str, **_kwargs: object) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(
            return_code=self.remote_return_code,
            stdout="",
            stderr="checksum failed" if self.remote_return_code else "",
        )

    def download_files(
        self,
        _remote_root: PurePosixPath,
        paths: tuple[PurePosixPath, ...],
        local_root: Path,
    ) -> None:
        self.downloads.append(paths)
        if self.download_error is not None:
            raise self.download_error
        for relative in paths:
            source = self.remote_source.joinpath(*relative.parts)
            target = local_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())


def test_history_manifest_bundle_rejects_remote_checksum_failure_before_download(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    runner = BundleRunner(remote_source, remote_return_code=1)

    with pytest.raises(RuntimeError, match="remote run artifact checksum"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


def test_history_manifest_bundle_rejects_history_without_prior_acceptance(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    acceptance = cache_dir / "reports/optimizer_run_acceptance_report.json"
    acceptance.write_text(
        '{"status": "rejected", "evaluation_count": 1}\n',
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="prior optimizer acceptance is not accepted"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


def test_history_manifest_bundle_rejects_acceptance_history_count_mismatch(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    acceptance = cache_dir / "reports/optimizer_run_acceptance_report.json"
    acceptance.write_text(
        json.dumps(
            {
                "status": "accepted",
                "evaluation_count": 2,
                "result_manifest_count": 1,
                "metric_manifest_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="acceptance/history count mismatch"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


def test_history_manifest_bundle_skips_duplicate_candidate_without_parents(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    with history_path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "evaluation_index": 2,
                    "run_id": "real_002",
                    "status": "duplicate_candidate_skipped",
                    "result_manifest": None,
                    "metric_result_manifest": None,
                    "metrics": None,
                    "fom": None,
                    "objective": 1_000_000.0,
                    "constraint_penalty": 0.0,
                }
            )
            + "\n"
        )
    acceptance = cache_dir / "reports/optimizer_run_acceptance_report.json"
    acceptance.write_text(
        json.dumps(
            {
                "status": "accepted",
                "evaluation_count": 2,
                "result_manifest_count": 1,
                "metric_manifest_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    materialize_remote_history_manifests(
        ref,
        cache_dir,
        history_path,
        runner,
    )

    assert len(runner.downloads) == 1
    assert set(runner.downloads[0]) == {RESULT_RELATIVE, METRIC_RELATIVE}


def test_history_manifest_bundle_rejects_acceptance_manifest_count_mismatch(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    acceptance = cache_dir / "reports/optimizer_run_acceptance_report.json"
    acceptance.write_text(
        json.dumps(
                {
                    "status": "accepted",
                    "evaluation_count": 1,
                    "result_manifest_count": 0,
                    "metric_manifest_count": 0,
                }
        )
        + "\n",
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="manifest reference count mismatch"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


@pytest.mark.parametrize(
    "invalid_path",
    [
        "/tmp/result_manifest.json",
        "runs/real/real_001/../../result_manifest.json",
    ],
)
def test_history_manifest_bundle_rejects_unscoped_history_paths(
    tmp_path: Path,
    invalid_path: str,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    row = json.loads(history_path.read_text(encoding="utf-8"))
    row["result_manifest"] = invalid_path
    history_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="not project-relative"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


def test_history_manifest_bundle_rejects_path_absent_from_inventory(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    inventory = cache_dir / "reports/remote_run_artifacts.sha256"
    inventory.write_text(
        next(
            line
            for line in inventory.read_text(encoding="utf-8").splitlines()
            if RESULT_RELATIVE.as_posix() in line
        )
        + "\n",
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="absent from the remote checksum"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []


def test_history_manifest_bundle_rejects_local_digest_mismatch_and_preserves_old(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    inventory = cache_dir / "reports/remote_run_artifacts.sha256"
    inventory.write_text(
        inventory.read_text(encoding="utf-8").replace(
            sha256_file(remote_source.joinpath(*RESULT_RELATIVE.parts)),
            "f" * 64,
            1,
        ),
        encoding="utf-8",
    )
    existing = cache_dir / ".remote_history_manifests" / "verified-before.json"
    existing.parent.mkdir()
    existing.write_text("preserve me\n", encoding="utf-8")
    runner = BundleRunner(remote_source)

    with pytest.raises(RuntimeError, match="historical manifest checksum mismatch"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert existing.read_text(encoding="utf-8") == "preserve me\n"


def test_history_manifest_bundle_rejects_tar_failure_and_preserves_old(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    existing = cache_dir / ".remote_history_manifests" / "verified-before.json"
    existing.parent.mkdir()
    existing.write_text("preserve me\n", encoding="utf-8")
    runner = BundleRunner(
        remote_source,
        download_error=RuntimeError("remote selected-file tar download failed"),
    )

    with pytest.raises(RuntimeError, match="selected-file tar download failed"):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert existing.read_text(encoding="utf-8") == "preserve me\n"


def test_fresh_controller_materializes_deleted_history_from_synced_retention_evidence(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    for relative in (RESULT_RELATIVE, METRIC_RELATIVE):
        source = remote_source.joinpath(*relative.parts)
        target = cache_dir.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    evidence = preserve_retention_evidence(
        cache_dir,
        run_id="real_001",
        candidate_id=None,
    )
    _write_remote_deleted_decision(cache_dir, evidence)
    # The Remote publisher preserves the inventory artifact but writes zero
    # entries when every canonical run was deleted by retention.
    (cache_dir / "reports/remote_run_artifacts.sha256").write_text(
        "",
        encoding="utf-8",
    )
    import shutil

    shutil.rmtree(cache_dir / "runs")
    runner = BundleRunner(remote_source)

    supplementary = materialize_remote_history_manifests(
        ref,
        cache_dir,
        history_path,
        runner,
    )

    assert supplementary.joinpath(*RESULT_RELATIVE.parts).is_file()
    assert supplementary.joinpath(*METRIC_RELATIVE.parts).is_file()
    assert runner.downloads == []
    assert runner.commands == []


def test_empty_remote_inventory_without_complete_retention_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    (cache_dir / "reports/remote_run_artifacts.sha256").write_text(
        "",
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    with pytest.raises(
        RuntimeError,
        match="absent from the remote checksum inventory or retention evidence",
    ):
        materialize_remote_history_manifests(
            ref,
            cache_dir,
            history_path,
            runner,
        )

    assert runner.downloads == []
    assert runner.commands == []


def test_fresh_controller_merges_deleted_evidence_with_retained_remote_history(
    tmp_path: Path,
) -> None:
    import shutil

    from hermes_workflow.retention_evidence import preserve_retention_evidence

    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    for relative in (RESULT_RELATIVE, METRIC_RELATIVE):
        source = remote_source.joinpath(*relative.parts)
        target = cache_dir.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    evidence = preserve_retention_evidence(
        cache_dir,
        run_id="real_001",
        candidate_id=None,
    )
    _write_remote_deleted_decision(cache_dir, evidence)
    shutil.rmtree(cache_dir / "runs")

    result_2 = PurePosixPath("runs/real/real_002/result_manifest.json")
    metric_2 = PurePosixPath(
        "runs/real/real_002/metrics/metric_result_manifest.json"
    )
    for relative, payload in (
        (
            result_2,
            {
                "run_id": "real_002",
                "status": "succeeded",
                "metric_result_manifest": metric_2.as_posix(),
            },
        ),
        (metric_2, {"run_id": "real_002", "status": "succeeded"}),
    ):
        path = remote_source.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    history_path.write_text(
        history_path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "evaluation_index": 2,
                "run_id": "real_002",
                "status": "feasible",
                "result_manifest": result_2.as_posix(),
                "metric_result_manifest": metric_2.as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (cache_dir / "reports/optimizer_run_acceptance_report.json").write_text(
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
    (cache_dir / "reports/remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_source.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (result_2, metric_2)
        ),
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    supplementary = materialize_remote_history_manifests(
        ref,
        cache_dir,
        history_path,
        runner,
    )

    assert all(
        supplementary.joinpath(*relative.parts).is_file()
        for relative in (RESULT_RELATIVE, METRIC_RELATIVE, result_2, metric_2)
    )
    assert len(runner.downloads) == 1
    assert set(runner.downloads[0]) == {result_2, metric_2}


def test_current_remote_inventory_wins_over_stale_same_run_evidence(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    ref, cache_dir, history_path, remote_source = _seed_history_bundle(tmp_path)
    for relative in (RESULT_RELATIVE, METRIC_RELATIVE):
        source = remote_source.joinpath(*relative.parts)
        target = cache_dir.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    evidence = preserve_retention_evidence(
        cache_dir,
        run_id="real_001",
        candidate_id=None,
    )
    (evidence.bundle_path / "artifacts/result_manifest.json").write_text(
        "corrupt stale evidence\n",
        encoding="utf-8",
    )
    decision_path = cache_dir / "state/run_retention/real_001.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(
            {
                "run_id": "real_001",
                "remote_action": "kept",
                "evidence_status": "not_required",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    current_result = remote_source.joinpath(*RESULT_RELATIVE.parts)
    current_payload = json.loads(current_result.read_text(encoding="utf-8"))
    current_payload["attempt_marker"] = "current"
    current_result.write_text(json.dumps(current_payload) + "\n", encoding="utf-8")
    (cache_dir / "reports/remote_run_artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(remote_source.joinpath(*relative.parts))}  "
            f"{relative.as_posix()}\n"
            for relative in (RESULT_RELATIVE, METRIC_RELATIVE)
        ),
        encoding="utf-8",
    )
    runner = BundleRunner(remote_source)

    supplementary = materialize_remote_history_manifests(
        ref,
        cache_dir,
        history_path,
        runner,
    )

    materialized = json.loads(
        supplementary.joinpath(*RESULT_RELATIVE.parts).read_text(encoding="utf-8")
    )
    assert materialized["attempt_marker"] == "current"
    assert len(runner.downloads) == 1
    assert set(runner.downloads[0]) == {RESULT_RELATIVE, METRIC_RELATIVE}
