from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import sha256_file
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_next_real_run, prepare_real_run
from hermes_workflow.real_run_recovery import (
    assess_real_run_recovery,
    assert_no_unresolved_real_runs,
    prepare_real_run_retry,
    resolve_real_run_failure,
)
from hermes_workflow.reports import (
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunRecoveryReport,
    RealRunRecoveryStatus,
)
from hermes_workflow.result_handoff import check_real_run
from tests.project_factory import create_approved_generic_project


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc="2026-06-02T00:00:00Z",
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir


def _write_result_manifest(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    candidate_id: str | None = None,
    status: str = "succeeded",
    include_artifacts: bool = True,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = _load_json(run_dir / "real_run_manifest.json")
    selected_candidate_id = candidate_id or prepared["candidate_id"]
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    if include_artifacts:
        psf_dir.mkdir(parents=True, exist_ok=True)
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (psf_dir / "spectre.out").write_text(
            "sanitized spectre output\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean.log").write_text(
            "sanitized ocean log\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean_scalars.tsv").write_text(
            "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stdout").write_text(
            "sanitized stdout\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    _write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "status": status,
            "started_at_utc": "2026-06-02T00:30:00Z",
            "completed_at_utc": "2026-06-02T00:31:00Z",
            "simulator": {
                "engine": "spectre_x",
                "preset": "ax",
                "command_label": "spectre_ocean_adapter",
            },
            "prepared_input_scs": prepared["rendered_input_scs"],
            "prepared_input_sha256": prepared["rendered_input_sha256"],
            "log_file": f"runs/real/{run_id}/spectre.stdout",
            "artifact_files": [
                f"runs/real/{run_id}/spectre.stderr",
                f"runs/real/{run_id}/psf/spectre.out",
                f"runs/real/{run_id}/metrics/ocean.log",
                f"runs/real/{run_id}/metrics/ocean_scalars.tsv",
            ],
            "result_data": {
                "kind": "spectre_psf",
                "psf_dir": f"runs/real/{run_id}/psf",
                "spectre_out": f"runs/real/{run_id}/psf/spectre.out",
            },
            "metric_result_manifest": (
                f"runs/real/{run_id}/metrics/metric_result_manifest.json"
            ),
        },
    )


def _write_metric_result_manifest(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    candidate_id: str | None = None,
    status: str = "succeeded",
    metric_status: str = "succeeded",
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = {name: 1.0e-6 for name in request_by_name}
    selected_candidate_id = candidate_id or request["candidate_id"]
    _write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "backend": "spectre_ocean_batch",
            "status": status,
            "request_file": f"runs/real/{run_id}/metric_extraction_request.json",
            "request_sha256": sha256_file(request_path),
            "psf_dir": f"runs/real/{run_id}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "return_code": 0,
                "script_file": f"runs/real/{run_id}/metrics/metric_probe.ocn",
                "script_sha256": sha256_file(script_path),
                "log_file": f"runs/real/{run_id}/metrics/ocean.log",
                "scalar_output_file": (
                    f"runs/real/{run_id}/metrics/ocean_scalars.tsv"
                ),
            },
            "metrics": [
                {
                    "name": name,
                    "status": metric_status,
                    "value": value if metric_status == "succeeded" else None,
                    "value_text": (
                        f"{value:.12g}" if metric_status == "succeeded" else None
                    ),
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name]["result"],
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [] if metric_status == "succeeded" else ["scalar failed"],
                }
                for name, value in values.items()
            ],
            "issues": [] if status == "succeeded" else ["ocean failed"],
        },
    )


def _record_real_001(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status.value == "pass"
    assert check_metric_results(project_dir).status.value == "pass"
    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T00:40:00Z",
    )
    assert report.status.value == "pass"


def _write_manual_retry_package(
    project_dir: Path,
    *,
    retry_run_id: str = "real_002",
    candidate_id: str = "real_001",
    manifest_status: str = "prepared",
    manifest_run_id: str | None = None,
    manifest_candidate_id: str | None = None,
    candidate_file_id: str | None = None,
) -> None:
    retry_dir = project_dir / "runs" / "real" / retry_run_id
    retry_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        retry_dir / "real_run_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": manifest_run_id or retry_run_id,
            "status": manifest_status,
            "candidate_id": manifest_candidate_id or candidate_id,
        },
    )
    _write_json(
        retry_dir / "candidate.json",
        {
            "schema_version": "1.0",
            "candidate_id": candidate_file_id or candidate_id,
            "retry_of_run_id": "real_001",
            "retry_attempt_number": 2,
            "parameters": {"VAR_INT": "2", "VAR_WIDTH": "0.2u"},
        },
    )


def test_assess_recovery_classifies_pending_execution(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.PENDING_EXECUTION
    assert report.allowed_actions == [
        RealRunRecoveryAction.WAIT_FOR_EXECUTION,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]
    assert report.recommended_action == RealRunRecoveryAction.WAIT_FOR_EXECUTION
    persisted = _load_json(project_dir / "reports" / "real_run_recovery_report.json")
    assert persisted["classification"] == "pending_execution"


def test_assess_recovery_classifies_invalid_prepared_package(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    manifest_path = project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json"
    manifest = _load_json(manifest_path)
    manifest.pop("candidate_id")
    _write_json(manifest_path, manifest)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert report.allowed_actions == [
        RealRunRecoveryAction.REVISE_CONTRACTS,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]


def test_assess_recovery_classifies_missing_metric_request_as_contract_invalid(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    ).unlink()

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "metric extraction request is missing" in " ".join(report.issues)


def test_assess_recovery_classifies_missing_result_after_evidence(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    (run_dir / "spectre.stdout").write_text("tool started\n", encoding="utf-8")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_MISSING
    assert RealRunRecoveryAction.RETRY_SAME_CANDIDATE in report.allowed_actions


def test_assess_recovery_classifies_failed_tool_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_FAILED
    assert report.recommended_action == RealRunRecoveryAction.RETRY_SAME_CANDIDATE


def test_assess_recovery_classifies_partial_tool_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, include_artifacts=False)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_PARTIAL
    assert "result artifact is missing" in " ".join(report.issues)


def test_assess_recovery_classifies_invalid_result_handoff_as_contract_invalid(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="not_supported")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "result status is invalid" in " ".join(report.issues)


def test_assess_recovery_classifies_unsafe_result_path_as_partial(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result = _load_json(result_path)
    result["log_file"] = "/tmp/unsafe.log"
    _write_json(result_path, result)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_PARTIAL
    assert report.allowed_actions == [
        RealRunRecoveryAction.RETRY_SAME_CANDIDATE,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]
    assert "result artifact path is unsafe" in " ".join(report.issues)


def test_assess_recovery_classifies_missing_metric_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_MISSING


def test_assess_recovery_classifies_failed_metric_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(
        project_dir,
        status="failed",
        metric_status="failed",
    )

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_FAILED
    assert RealRunRecoveryAction.REVISE_CONTRACTS in report.allowed_actions


def test_assess_recovery_classifies_recordable_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.RECORDABLE_SUCCESS
    assert report.allowed_actions == [RealRunRecoveryAction.RECORD_RESULT]


def test_assess_recovery_classifies_already_recorded(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.ALREADY_RECORDED
    assert report.allowed_actions == []


def test_assess_recovery_classifies_valid_retry_decision_as_resolved(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json",
        {
            "decision": "retry_same_candidate",
            "retry_run_id": "real_002",
        },
    )
    _write_manual_retry_package(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.RESOLVED_RETRY_PREPARED
    assert report.allowed_actions == []


def test_assess_recovery_refuses_symlinked_decision_file(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    decision_path = project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    outside_decision = tmp_path / "outside_decision.json"
    _write_json(
        outside_decision,
        {
            "decision": "abandon_candidate",
        },
    )
    decision_path.symlink_to(outside_decision)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "recovery decision must not be a symlink" in " ".join(report.issues)


def test_assess_recovery_refuses_symlinked_retry_decision_file(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json",
        {
            "decision": "retry_same_candidate",
            "retry_run_id": "real_002",
        },
    )
    _write_manual_retry_package(project_dir)
    retry_decision_path = (
        project_dir / "runs" / "real" / "real_002" / "recovery_decision.json"
    )
    outside_decision = tmp_path / "outside_retry_decision.json"
    _write_json(
        outside_decision,
        {
            "decision": "abandon_candidate",
        },
    )
    retry_decision_path.symlink_to(outside_decision)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "recovery decision must not be a symlink" in " ".join(report.issues)


def test_unresolved_guard_blocks_retry_prepared_decision(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json",
        {
            "decision": "retry_same_candidate",
            "retry_run_id": "real_002",
        },
    )
    _write_manual_retry_package(project_dir)

    with pytest.raises(
        ValueError,
        match="real_001:resolved_retry_prepared",
    ):
        assert_no_unresolved_real_runs(project_dir)


def test_unresolved_guard_does_not_persist_checker_reports(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    real_report_path = project_dir / "reports" / "real_run_check_report.json"
    metric_report_path = project_dir / "reports" / "metric_result_check_report.json"
    real_report_path.unlink(missing_ok=True)
    metric_report_path.unlink(missing_ok=True)

    with pytest.raises(ValueError, match="real_001:metric_result_missing"):
        assert_no_unresolved_real_runs(project_dir)

    assert not real_report_path.exists()
    assert not metric_report_path.exists()


def test_unresolved_guard_allows_c9_after_retry_is_recorded(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002", status="failed")
    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_002",
        retry_run_id="real_003",
        reason="retry failed execution",
        decided_at_utc="2026-06-02T01:00:00Z",
    )
    _write_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )
    _write_metric_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )
    record_report = record_real_result(
        project_dir,
        run_id="real_003",
        recorded_at_utc="2026-06-02T01:10:00Z",
    )
    assert record_report.status.value == "pass"

    assert_no_unresolved_real_runs(project_dir)
    package = prepare_next_real_run(
        project_dir,
        run_id="real_004",
        created_at_utc="2026-06-02T01:20:00Z",
    )

    assert package.run_id == "real_004"


def test_unresolved_guard_allows_c9_after_retry_is_abandoned(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002", status="failed")
    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_002",
        retry_run_id="real_003",
        reason="retry failed execution",
        decided_at_utc="2026-06-02T01:00:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_003", status="failed")
    resolve_real_run_failure(
        project_dir,
        run_id="real_003",
        decision="abandon_candidate",
        reason="abandon after retry failure",
        decided_at_utc="2026-06-02T01:10:00Z",
    )

    assert_no_unresolved_real_runs(project_dir)
    package = prepare_next_real_run(
        project_dir,
        run_id="real_004",
        created_at_utc="2026-06-02T01:20:00Z",
    )

    assert package.run_id == "real_004"


def test_assess_recovery_rejects_retry_decision_symlink_target(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    decision_path = project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    _write_json(
        decision_path,
        {
            "decision": "retry_same_candidate",
            "retry_run_id": "real_002",
        },
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    retry_dir = project_dir / "runs" / "real" / "real_002"
    retry_dir.symlink_to(outside, target_is_directory=True)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "must not be a symlink" in " ".join(report.issues)


@pytest.mark.parametrize(
    ("override", "expected_issue"),
    [
        ({"manifest_status": "failed"}, "retry package is not prepared"),
        (
            {"manifest_candidate_id": "other_candidate"},
            "retry manifest candidate_id does not match failed candidate",
        ),
        (
            {"candidate_file_id": "other_candidate"},
            "retry candidate_id does not match failed candidate",
        ),
        (
            {"manifest_run_id": "real_003"},
            "retry manifest run_id does not match retry_run_id",
        ),
    ],
)
def test_assess_recovery_rejects_invalid_retry_package_identity(
    tmp_path: Path,
    override: dict[str, str],
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json",
        {
            "decision": "retry_same_candidate",
            "retry_run_id": "real_002",
        },
    )
    _write_manual_retry_package(project_dir, **override)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert expected_issue in " ".join(report.issues)


def test_assess_recovery_rejects_symlinked_attempt_directory(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    attempt_dir = project_dir / "runs" / "real" / "real_002"
    attempt_dir.symlink_to(outside, target_is_directory=True)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "must not be a symlink" in " ".join(report.issues)


def test_assess_recovery_rejects_corrupt_candidate_in_attempt_scan(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    corrupt_dir = project_dir / "runs" / "real" / "real_002"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "candidate.json").write_text("{not json}\n", encoding="utf-8")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.FAIL
    assert report.classification == RealRunRecoveryClassification.CONTRACT_INVALID
    assert "candidate.json" in " ".join(report.issues)


def test_prepare_retry_writes_decision_and_new_package_same_candidate(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    retry = prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="spectre exited non-zero",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    failed_decision = _load_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    )
    retry_candidate = _load_json(
        project_dir / "runs" / "real" / "real_002" / "candidate.json"
    )
    retry_manifest = _load_json(
        project_dir / "runs" / "real" / "real_002" / "real_run_manifest.json"
    )
    retry_request = _load_json(
        project_dir / "runs" / "real" / "real_002" / "metric_extraction_request.json"
    )

    assert retry.run_id == "real_002"
    assert failed_decision["decision"] == "retry_same_candidate"
    assert failed_decision["retry_run_id"] == "real_002"
    assert failed_decision["decided_by"] == "supervisor_agent"
    assert failed_decision["reason"] == "spectre exited non-zero"
    assert failed_decision["source_recovery_report"] == (
        "reports/real_run_recovery_report.json"
    )
    assert failed_decision["source_recovery_report_sha256"]
    assert failed_decision["issues"] == []
    assert retry_candidate["candidate_id"] == "real_001"
    assert retry_candidate["retry_of_run_id"] == "real_001"
    assert retry_candidate["retry_attempt_number"] == 2
    assert retry_candidate["recovery_decision"] == (
        "runs/real/real_001/recovery_decision.json"
    )
    assert retry_manifest["run_id"] == "real_002"
    assert retry_manifest["candidate_id"] == "real_001"
    assert retry_manifest["candidate_source"] == "retry_same_candidate"
    assert retry_manifest["package_kind"] == "retry"
    assert retry_manifest["retry_of_run_id"] == "real_001"
    assert retry_manifest["retry_attempt_number"] == 2
    assert retry_manifest["recovery_decision"] == (
        "runs/real/real_001/recovery_decision.json"
    )
    assert retry_manifest["recovery_decision_sha256"]
    assert retry_request["run_id"] == "real_002"
    assert retry_request["candidate_id"] == "real_001"


def test_prepare_retry_preserves_rendered_input(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    original = (
        project_dir / "runs" / "real" / "real_001" / "netlist" / "input.scs"
    ).read_text(encoding="utf-8")

    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="try once more",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    retry_text = (
        project_dir / "runs" / "real" / "real_002" / "netlist" / "input.scs"
    ).read_text(encoding="utf-8")
    assert retry_text == original


def test_prepare_retry_preserves_rendered_input_after_template_change(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    original = (
        project_dir / "runs" / "real" / "real_001" / "netlist" / "input.scs"
    ).read_text(encoding="utf-8")
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        template_path.read_text(encoding="utf-8").replace("stop=10n", "stop=20n"),
        encoding="utf-8",
    )

    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="try once more",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    retry_text = (
        project_dir / "runs" / "real" / "real_002" / "netlist" / "input.scs"
    ).read_text(encoding="utf-8")
    assert retry_text == original
    assert "stop=20n" not in retry_text


def test_prepare_retry_refuses_existing_target(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    target = project_dir / "runs" / "real" / "real_002"
    target.mkdir(parents=True)
    (target / "leftover.txt").write_text("old data\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="real run directory is not empty"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert (target / "leftover.txt").read_text(encoding="utf-8") == "old data\n"


def test_prepare_retry_refuses_existing_empty_target(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    target = project_dir / "runs" / "real" / "real_002"
    target.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="real run directory already exists"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert list(target.iterdir()) == []


def test_prepare_retry_refuses_symlink_target(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = project_dir / "runs" / "real" / "real_002"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileExistsError, match="must not be a symlink"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert list(outside.iterdir()) == []


def test_prepare_retry_refuses_symlinked_real_run_parent(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    real_root = project_dir / "runs" / "real"
    outside_real_root = tmp_path / "outside_real_root"
    real_root.rename(outside_real_root)
    real_root.symlink_to(outside_real_root, target_is_directory=True)

    with pytest.raises(FileExistsError, match="parent directory must not be a symlink"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert not (outside_real_root / "real_002").exists()


def test_prepare_retry_refuses_symlinked_runs_parent(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    runs_root = project_dir / "runs"
    outside_runs_root = tmp_path / "outside_runs_root"
    runs_root.rename(outside_runs_root)
    runs_root.symlink_to(outside_runs_root, target_is_directory=True)

    with pytest.raises(FileExistsError, match="parent directory must not be a symlink"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert not (outside_runs_root / "real" / "real_002").exists()


def test_prepare_retry_refuses_symlinked_decision_file(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    decision_path = project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    outside_decision = tmp_path / "outside_decision.json"
    decision_path.symlink_to(outside_decision)

    with pytest.raises(FileExistsError, match="recovery decision must not be a symlink"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert not outside_decision.exists()
    assert not (project_dir / "runs" / "real" / "real_002").exists()


def test_prepare_retry_requires_metric_formula_contract_to_match_failed_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request["metrics"][0]["expression"] = 'value(VT("/OUT") 1n)'
    request["metrics"][0]["expression_sha256"] = expression_sha256(
        request["metrics"][0]["expression"]
    )
    _write_json(request_path, request)
    manifest_path = run_dir / "real_run_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["metric_extraction_request_sha256"] = sha256_file(request_path)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        ValueError,
        match="retry metric formula contract does not match failed run",
    ):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert not (run_dir / "recovery_decision.json").exists()
    assert not (project_dir / "runs" / "real" / "real_002").exists()


def test_prepare_retry_refuses_third_attempt(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="first retry",
        decided_at_utc="2026-06-02T01:00:00Z",
    )
    _write_result_manifest(
        project_dir,
        run_id="real_002",
        candidate_id="real_001",
        status="failed",
    )

    with pytest.raises(ValueError, match="retry budget is exhausted"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_002",
            retry_run_id="real_003",
            reason="third attempt",
        )


def test_resolve_abandon_writes_decision_without_retry(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    report = resolve_real_run_failure(
        project_dir,
        run_id="real_001",
        decision="abandon_candidate",
        reason="candidate is not worth retrying",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    decision = _load_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    )
    assert decision["decision"] == "abandon_candidate"
    assert "retry_run_id" not in decision
    assert report.classification == RealRunRecoveryClassification.RESOLVED_ABANDONED


def test_resolve_failure_refuses_symlinked_runs_parent(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    runs_root = project_dir / "runs"
    outside_runs_root = tmp_path / "outside_runs_root"
    runs_root.rename(outside_runs_root)
    runs_root.symlink_to(outside_runs_root, target_is_directory=True)

    with pytest.raises(FileExistsError, match="parent directory must not be a symlink"):
        resolve_real_run_failure(
            project_dir,
            run_id="real_001",
            decision="abandon_candidate",
            reason="candidate is not worth retrying",
        )

    assert not (
        outside_runs_root / "real" / "real_001" / "recovery_decision.json"
    ).exists()


def test_resolve_failure_refuses_symlinked_decision_file(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    decision_path = project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    outside_decision = tmp_path / "outside_decision.json"
    decision_path.symlink_to(outside_decision)

    with pytest.raises(FileExistsError, match="recovery decision must not be a symlink"):
        resolve_real_run_failure(
            project_dir,
            run_id="real_001",
            decision="abandon_candidate",
            reason="candidate is not worth retrying",
        )

    assert not outside_decision.exists()
