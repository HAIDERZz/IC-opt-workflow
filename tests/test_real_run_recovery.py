from __future__ import annotations

import pytest

from hermes_workflow.reports import (
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunRecoveryReport,
    RealRunRecoveryStatus,
)


def test_recovery_report_schema_accepts_classification_and_actions() -> None:
    report = RealRunRecoveryReport.model_validate(
        {
            "schema_version": "1.0",
            "status": "pass",
            "run_id": "real_002",
            "candidate_id": "real_002",
            "classification": "metric_result_failed",
            "allowed_actions": [
                "retry_same_candidate",
                "abandon_candidate",
                "revise_contracts",
                "stop_workflow",
            ],
            "recommended_action": "retry_same_candidate",
            "attempt_number": 1,
            "max_attempts_per_candidate": 2,
            "retry_budget_remaining": 1,
            "real_run_check_report": "reports/real_run_check_report.json",
            "metric_result_check_report": "reports/metric_result_check_report.json",
            "ledger_path": "ledger/experiment_ledger.jsonl",
            "recovery_decision": None,
            "issues": [],
        }
    )

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_FAILED
    assert report.allowed_actions == [
        RealRunRecoveryAction.RETRY_SAME_CANDIDATE,
        RealRunRecoveryAction.ABANDON_CANDIDATE,
        RealRunRecoveryAction.REVISE_CONTRACTS,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]


def test_recovery_report_schema_forbids_unknown_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "status": "pass",
        "run_id": "real_002",
        "candidate_id": "real_002",
        "classification": "pending_execution",
        "allowed_actions": ["wait_for_execution", "stop_workflow"],
        "recommended_action": "wait_for_execution",
        "attempt_number": 1,
        "max_attempts_per_candidate": 2,
        "retry_budget_remaining": 1,
        "real_run_check_report": "reports/real_run_check_report.json",
        "metric_result_check_report": "reports/metric_result_check_report.json",
        "ledger_path": "ledger/experiment_ledger.jsonl",
        "recovery_decision": None,
        "issues": [],
        "unexpected": True,
    }

    with pytest.raises(ValueError):
        RealRunRecoveryReport.model_validate(payload)
