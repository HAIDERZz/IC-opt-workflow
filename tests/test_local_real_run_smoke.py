from __future__ import annotations

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_next_real_run
from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs
from hermes_workflow.reports import (
    MetricResultCheckStatus,
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
