from __future__ import annotations

from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    ledger_rows,
    record_checked_run,
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
