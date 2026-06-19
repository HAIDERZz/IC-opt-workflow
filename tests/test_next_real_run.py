from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.real_run import prepare_next_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import RealResultRecordStatus, RealRunCheckStatus
from hermes_workflow.result_handoff import check_real_run
from tests.real_run_cluster_helpers import (
    create_ready_project as _create_ready_project,
    load_json as _load_json,
    record_real_001 as _record_real_001,
    variable_names,
    write_json as _write_json,
    write_metric_result_manifest as _write_metric_result_manifest,
    write_result_manifest as _write_result_manifest,
)


def test_prepare_next_real_run_refuses_before_recorded_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_invalid_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    shutil.rmtree(project_dir / "runs" / "real")
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ledger row 1 is invalid"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_coerced_ledger_types(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    shutil.rmtree(project_dir / "runs" / "real")
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    row = json.loads(ledger_path.read_text(encoding="utf-8"))
    metric_name = next(iter(row["metrics"]))
    row["metrics"][metric_name] = str(row["metrics"][metric_name])
    row["constraints_passed"] = "true"
    row["objective"] = "2.0e-18"
    ledger_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ledger row 1 is invalid"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_optimizer_state_drift(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["random_seed"] = 99
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state random_seed disagrees"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_accepts_b09_state_with_recorded_observation_count(
    tmp_path: Path,
) -> None:
    """B-09 contract: state.current_evaluations is attempted count, ledger
    row count must match state.recorded_observation_count, NOT
    state.current_evaluations."""
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    # Simulate B-09 multi-eval state: 3 attempted, 1 recorded, 2 failed.
    # Ledger still has only 1 usable observation (the one recorded above).
    state["current_evaluations"] = 3
    state["recorded_observation_count"] = 1
    state["failed_evaluation_count"] = 2
    state["status_counts"] = {"feasible": 1, "metric_check_failed": 2}
    state["progress_source"] = "reports/optimizer_evaluations.jsonl"
    _write_json(state_path, state)

    # Should NOT raise -- B-09 state is internally consistent with ledger.
    package = prepare_next_real_run(
        project_dir, created_at_utc="2026-06-02T00:50:00Z"
    )
    assert package.run_id == "real_002"


def test_prepare_next_real_run_rejects_b09_state_with_recorded_count_mismatch(
    tmp_path: Path,
) -> None:
    """If recorded_observation_count is present, it MUST equal ledger row count."""
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["current_evaluations"] = 3
    state["recorded_observation_count"] = 0  # WRONG: ledger has 1 row.
    state["failed_evaluation_count"] = 3
    _write_json(state_path, state)

    with pytest.raises(
        ValueError,
        match=r"recorded_observation_count disagrees with ledger row count",
    ):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_legacy_state_without_recorded_count_still_checks_current_evaluations(
    tmp_path: Path,
) -> None:
    """Legacy (pre-B-09) state lacks recorded_observation_count; the old
    current_evaluations vs ledger rule must still hold for backward compat."""
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["current_evaluations"] = 5  # mismatched against 1 ledger row
    state.pop("recorded_observation_count", None)
    state.pop("failed_evaluation_count", None)
    state.pop("status_counts", None)
    state.pop("progress_source", None)
    _write_json(state_path, state)

    with pytest.raises(
        ValueError,
        match=r"current_evaluations disagrees with ledger row count",
    ):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_legacy_state_consistent_with_ledger_passes(
    tmp_path: Path,
) -> None:
    """Legacy state with current_evaluations == len(ledger) must keep passing."""
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state.pop("recorded_observation_count", None)
    state.pop("failed_evaluation_count", None)
    state.pop("status_counts", None)
    state.pop("progress_source", None)
    # current_evaluations == 1 == len(ledger_rows)
    _write_json(state_path, state)

    package = prepare_next_real_run(
        project_dir, created_at_utc="2026-06-02T00:50:00Z"
    )
    assert package.run_id == "real_002"


def test_prepare_next_real_run_refuses_completed_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["status"] = "completed"
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state is completed"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_when_max_evaluations_reached(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        re.sub(
            r"max_evaluations: \d+",
            "max_evaluations: 1",
            optimizer_path.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable config drift detected"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_writes_real_002_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_002"
    candidate = _load_json(run_dir / "candidate.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")
    metric_request = _load_json(run_dir / "metric_extraction_request.json")
    rendered = (run_dir / "netlist" / "input.scs").read_text(encoding="utf-8")

    assert package.run_id == "real_002"
    assert package.run_dir == run_dir
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert candidate["candidate_id"] == "real_002"
    assert candidate["source"] == "deterministic_initialization_sequence"
    assert candidate["candidate_index"] == 1
    expected_names = set(variable_names(project_dir))
    assert set(candidate["parameters"]) == expected_names
    assert all(candidate["parameters"][name] for name in expected_names)
    assert candidate["parameters"] != _load_json(
        project_dir / "runs" / "real" / "real_001" / "candidate.json"
    )["parameters"]
    assert manifest["run_id"] == "real_002"
    assert manifest["candidate_id"] == "real_002"
    assert manifest["candidate_source"] == "deterministic_initialization_sequence"
    assert manifest["candidate_index"] == 1
    assert manifest["selection_policy"] == (
        "next_unique_from_optimizer_initialization_sequence"
    )
    assert manifest["previous_evaluations"] == 1
    assert manifest["ledger_snapshot_sha256"]
    assert manifest["optimizer_state_sha256"]
    assert manifest["metric_extraction_request"] == (
        "runs/real/real_002/metric_extraction_request.json"
    )
    assert metric_request["run_id"] == "real_002"
    assert metric_request["candidate_id"] == "real_002"
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl.lock").exists()


def test_prepare_next_real_run_refuses_real_001_override(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    with pytest.raises(ValueError, match="prepare-next-real-run cannot target real_001"):
        prepare_next_real_run(project_dir, run_id="real_001")


def test_prepare_next_real_run_refuses_existing_run_manifest_override(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_002"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "real_run_manifest.json", {"status": "prepared"})

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir, run_id="real_002")


def test_prepare_next_real_run_refuses_existing_empty_run_directory(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    (project_dir / "runs" / "real" / "real_002").mkdir(parents=True)

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(
            project_dir,
            created_at_utc="2026-06-02T01:00:00Z",
        )


def test_prepare_next_real_run_refuses_existing_manifest_directory_by_default(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_002"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "real_run_manifest.json", {"status": "prepared"})

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(
            project_dir,
            created_at_utc="2026-06-02T01:00:00Z",
        )


def test_prepare_next_real_run_refuses_non_empty_override_directory(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_004"
    run_dir.mkdir(parents=True)
    (run_dir / "partial.log").write_text("partial previous attempt\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir, run_id="real_004")

    assert (run_dir / "partial.log").exists()


def test_prepare_next_real_run_refuses_symlink_run_directory_override(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    outside_dir = tmp_path / "outside_real_004"
    outside_dir.mkdir()
    run_dir = project_dir / "runs" / "real" / "real_004"
    run_dir.symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(FileExistsError, match="real run directory must not be a symlink"):
        prepare_next_real_run(project_dir, run_id="real_004")

    assert not (outside_dir / "input.scs").exists()
    assert not (outside_dir / "candidate.json").exists()
    assert not (outside_dir / "real_run_manifest.json").exists()


def test_prepare_next_real_run_refuses_symlink_run_directory_in_default_scan(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    outside_dir = tmp_path / "outside_real_002"
    outside_dir.mkdir()
    run_dir = project_dir / "runs" / "real" / "real_002"
    run_dir.symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(FileExistsError, match="real run directory must not be a symlink"):
        prepare_next_real_run(project_dir)

    assert not (outside_dir / "input.scs").exists()
    assert not (outside_dir / "candidate.json").exists()
    assert not (outside_dir / "real_run_manifest.json").exists()


def test_prepare_next_real_run_refuses_symlinked_real_run_parent(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    real_root = project_dir / "runs" / "real"
    shutil.rmtree(real_root)
    outside_real_root = tmp_path / "outside_real_root"
    outside_real_root.mkdir()
    real_root.symlink_to(outside_real_root, target_is_directory=True)

    with pytest.raises(FileExistsError, match="parent directory must not be a symlink"):
        prepare_next_real_run(project_dir)

    assert not (outside_real_root / "real_002").exists()


def test_prepare_next_real_run_refuses_already_prepared_candidate(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )
    assert first.run_id == "real_002"

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(
            project_dir,
            created_at_utc="2026-06-02T01:00:00Z",
        )


def test_prepare_next_real_run_refuses_unresolved_pending_package(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_unresolved_failed_package(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002")
    result_path = project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    result = _load_json(result_path)
    result["status"] = "failed"
    _write_json(result_path, result)

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_continues_after_abandoned_candidate(
    tmp_path: Path,
) -> None:
    from hermes_workflow.real_run_recovery import resolve_real_run_failure

    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002")
    result_path = project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    result = _load_json(result_path)
    result["status"] = "failed"
    _write_json(result_path, result)
    resolve_real_run_failure(
        project_dir,
        run_id="real_002",
        decision="abandon_candidate",
        reason="skip this candidate",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    package = prepare_next_real_run(
        project_dir,
        run_id="real_003",
        created_at_utc="2026-06-02T01:10:00Z",
    )

    assert package.run_id == "real_003"


def test_next_real_run_package_can_be_checked_and_recorded_after_fake_result(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )
    assert package.run_id == "real_002"

    _write_result_manifest(project_dir, run_id="real_002")
    _write_metric_result_manifest(project_dir, run_id="real_002")

    real_report = check_real_run(project_dir, run_id="real_002")
    assert real_report.status == RealRunCheckStatus.PASS
    record_report = record_real_result(
        project_dir,
        run_id="real_002",
        recorded_at_utc="2026-06-02T01:10:00Z",
    )

    assert record_report.status == RealResultRecordStatus.PASS
    ledger_rows = [
        json.loads(line)
        for line in (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert [row["run_id"] for row in ledger_rows] == ["real_001", "real_002"]
    assert ledger_rows[1]["candidate_id"] == "real_002"
    assert ledger_rows[1]["parameters"] == package.candidate_payload["parameters"]
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    assert state["current_evaluations"] == 2


def test_prepare_next_real_run_cli_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()

    result = runner.invoke(app, ["prepare-next-real-run", str(project_dir)])

    assert result.exit_code == 0
    assert "next real run package prepared" in result.output
    assert "run: runs/real/real_002" in result.output
    assert "manifest: runs/real/real_002/real_run_manifest.json" in result.output
    assert "candidate: runs/real/real_002/candidate.json" in result.output


def test_prepare_next_real_run_cli_failure(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["prepare-next-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert "unresolved real run exists" in result.output
