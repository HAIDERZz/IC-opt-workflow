from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_workflow.reports import (
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
)
from hermes_workflow.schemas import LedgerRow


def test_ledger_row_accepts_real_result_provenance() -> None:
    row = LedgerRow(
        candidate_id="real_001",
        parameters={"FN": "2", "WN": "0.3 um", "FP": "2", "WP": "0.3 um"},
        metrics={"rise": 1.25e-10, "fall": 1.45e-10, "DC": 3.2e-4},
        constraints_passed=True,
        objective=3.2e-4,
        batch_id=1,
        simulation_status="real_pass",
        timestamp_utc="2026-06-02T12:00:00Z",
        result_source="real",
        run_id="real_001",
        result_manifest="runs/real/real_001/result_manifest.json",
        metric_result_manifest=(
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
    )

    assert row.result_source == "real"
    assert row.run_id == "real_001"
    assert row.simulation_status == "real_pass"


def test_ledger_row_still_accepts_existing_mock_payload() -> None:
    row = LedgerRow(
        candidate_id="cand_001",
        parameters={"FN": "4"},
        metrics={"rise": 52.0},
        constraints_passed=True,
        objective=52.0,
        batch_id=1,
        simulation_status="mock_pass",
        timestamp_utc="2026-05-29T12:00:00Z",
    )

    assert row.result_source is None
    assert row.run_id is None


@pytest.mark.parametrize(
    "bad_status",
    ["real_error", "spectre_failed", "pass", ""],
)
def test_ledger_row_rejects_unapproved_real_statuses(bad_status: str) -> None:
    with pytest.raises(ValidationError, match="simulation_status must be one of"):
        LedgerRow(
            candidate_id="real_001",
            parameters={"FN": "2"},
            metrics={"rise": 1.25e-10},
            constraints_passed=True,
            objective=1.25e-10,
            batch_id=1,
            simulation_status=bad_status,
            timestamp_utc="2026-06-02T12:00:00Z",
            result_source="real",
            run_id="real_001",
        )


def test_real_result_record_report_schema_accepts_pass_report() -> None:
    report = RealResultRecordReport(
        schema_version="1.0",
        status=RealResultRecordStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        ledger_path="ledger/experiment_ledger.jsonl",
        optimizer_state_path="state/optimizer_state.json",
        best_candidate_path="state/best_candidate.json",
        checks=RealResultRecordFlags(
            real_run_check_ok=True,
            metric_result_check_ok=True,
            candidate_ok=True,
            duplicate_ok=True,
            objective_ok=True,
            constraints_ok=True,
            ledger_write_ok=True,
            state_write_ok=True,
        ),
        issues=[],
    )

    assert report.status == RealResultRecordStatus.PASS
    assert report.checks.ledger_write_ok is True
