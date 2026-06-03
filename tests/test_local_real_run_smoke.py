from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_next_real_run
from hermes_workflow.real_run_recovery import (
    assess_real_run_recovery,
    assert_no_unresolved_real_runs,
    prepare_real_run_retry,
)
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunCheckStatus,
    RealResultRecordStatus,
)
from hermes_workflow.result_handoff import check_real_run

from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    ledger_rows,
    load_json,
    record_checked_run,
    write_fake_metric_result_manifest,
    write_fake_result_manifest,
)


def test_c11_helper_seeds_recorded_real_result(tmp_path):
    project_dir = create_approved_real_project(tmp_path)

    report = record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    rows = ledger_rows(project_dir)
    assert report.status.value == "pass"
    assert [row["run_id"] for row in rows] == ["real_001"]
    assert [row["candidate_id"] for row in rows] == ["real_001"]
    assert_no_unresolved_real_runs(project_dir)


def test_c11_library_happy_path_records_next_real_run(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:50:00Z",
    )
    assert package.run_id == "real_002"

    write_fake_result_manifest(project_dir, run_id="real_002")
    write_fake_metric_result_manifest(project_dir, run_id="real_002")

    real_report = check_real_run(project_dir, run_id="real_002")
    metric_report = check_metric_results(project_dir, run_id="real_002")
    record_report = record_real_result(
        project_dir,
        run_id="real_002",
        recorded_at_utc="2026-06-03T01:00:00Z",
    )

    rows = ledger_rows(project_dir)
    state = load_json(project_dir / "state" / "optimizer_state.json")
    best = load_json(project_dir / "state" / "best_candidate.json")

    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
    assert record_report.status == RealResultRecordStatus.PASS
    assert [row["run_id"] for row in rows] == ["real_001", "real_002"]
    assert rows[1]["candidate_id"] == "real_002"
    assert rows[1]["parameters"] == package.candidate_payload["parameters"]
    assert state["current_evaluations"] == 2
    assert best["candidate_id"] in {row["candidate_id"] for row in rows}
    assert (project_dir / "reports" / "real_run_check_report.json").exists()
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()
    assert (project_dir / "reports" / "real_result_record_report.json").exists()
    assert_no_unresolved_real_runs(project_dir)


def test_c11_controlled_failure_retry_records_retry_success(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    failed_package = prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-03T00:50:00Z",
    )
    write_fake_result_manifest(
        project_dir,
        run_id="real_002",
        status="failed",
    )

    failed_report = assess_real_run_recovery(project_dir, run_id="real_002")
    assert (
        failed_report.classification
        == RealRunRecoveryClassification.TOOL_RESULT_FAILED
    )
    assert RealRunRecoveryAction.RETRY_SAME_CANDIDATE in failed_report.allowed_actions

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)

    retry = prepare_real_run_retry(
        project_dir,
        failed_run_id="real_002",
        retry_run_id="real_003",
        reason="retry fake failed execution",
        decided_at_utc="2026-06-03T01:00:00Z",
    )
    retry_candidate = load_json(retry.package.candidate_path)
    retry_manifest = load_json(retry.package.manifest_path)

    assert retry.run_id == "real_003"
    assert retry_candidate["candidate_id"] == "real_002"
    assert retry_candidate["parameters"] == failed_package.candidate_payload[
        "parameters"
    ]
    assert retry_manifest["retry_of_run_id"] == "real_002"
    assert retry_manifest["retry_attempt_number"] == 2
    assert retry.decision_path.exists()

    write_fake_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )
    write_fake_metric_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )

    assert (
        check_real_run(project_dir, run_id="real_003").status
        == RealRunCheckStatus.PASS
    )
    assert (
        check_metric_results(project_dir, run_id="real_003").status
        == MetricResultCheckStatus.PASS
    )
    retry_record = record_real_result(
        project_dir,
        run_id="real_003",
        recorded_at_utc="2026-06-03T01:10:00Z",
    )
    source_after_retry = assess_real_run_recovery(project_dir, run_id="real_002")
    rows = ledger_rows(project_dir)

    assert retry_record.status == RealResultRecordStatus.PASS
    assert (
        source_after_retry.classification
        == RealRunRecoveryClassification.ALREADY_RECORDED
    )
    assert [row["run_id"] for row in rows] == ["real_001", "real_003"]
    assert [row["candidate_id"] for row in rows] == ["real_001", "real_002"]
    assert_no_unresolved_real_runs(project_dir)

    next_package = prepare_next_real_run(
        project_dir,
        run_id="real_004",
        created_at_utc="2026-06-03T01:20:00Z",
    )
    assert next_package.run_id == "real_004"


def test_c11_cli_smoke_records_next_real_run(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )
    runner = CliRunner()

    prepare_result = runner.invoke(
        app,
        ["prepare-next-real-run", str(project_dir), "--run-id", "real_002"],
    )
    assert prepare_result.exit_code == 0
    assert "next real run package prepared" in prepare_result.stdout
    assert "run: runs/real/real_002" in prepare_result.stdout

    write_fake_result_manifest(project_dir, run_id="real_002")
    write_fake_metric_result_manifest(project_dir, run_id="real_002")

    real_result = runner.invoke(
        app,
        ["check-real-run", str(project_dir), "--run-id", "real_002"],
    )
    metric_result = runner.invoke(
        app,
        ["check-metric-results", str(project_dir), "--run-id", "real_002"],
    )
    record_result = runner.invoke(
        app,
        ["record-real-result", str(project_dir), "--run-id", "real_002"],
    )

    rows = ledger_rows(project_dir)
    assert real_result.exit_code == 0
    assert "real run handoff check passed" in real_result.stdout
    assert metric_result.exit_code == 0
    assert "metric result check passed" in metric_result.stdout
    assert record_result.exit_code == 0
    assert "real result recorded" in record_result.stdout
    assert [row["run_id"] for row in rows] == ["real_001", "real_002"]
