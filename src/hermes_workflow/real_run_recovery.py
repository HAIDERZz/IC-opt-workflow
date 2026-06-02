from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from hermes_workflow.metric_results import (
    METRIC_BACKEND,
    MetricExtractionRequest,
    check_metric_results,
)
from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import (
    RealRunPackage,
    _approved_hashes,
    _assert_approved,
    _assert_config_hashes,
    _assert_real_run_parent_dirs_are_not_symlinks,
    _load_execution_manifest,
    _load_supervisor_instruction,
    _next_unused_run_id,
    _write_real_run_package,
)
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealRunCheckReport,
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunRecoveryReport,
    RealRunRecoveryStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.schemas import LedgerRow
from hermes_workflow.validate import assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_SCHEMA_VERSION = "1.0"
REAL_RUN_ROOT = "runs/real"
RECOVERY_REPORT = "reports/real_run_recovery_report.json"
REAL_RUN_CHECK_REPORT = "reports/real_run_check_report.json"
METRIC_RESULT_CHECK_REPORT = "reports/metric_result_check_report.json"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
RECOVERY_DECISION_NAME = "recovery_decision.json"
MAX_ATTEMPTS_PER_CANDIDATE = 2
EXECUTION_EVIDENCE_NAMES = (
    "result_manifest.tmp",
    "spectre.stdout",
    "spectre.stderr",
    "psf",
    "metrics",
)
RESOLVED_CLASSIFICATIONS = {
    RealRunRecoveryClassification.ALREADY_RECORDED,
    RealRunRecoveryClassification.RESOLVED_ABANDONED,
}
METRIC_FORMULA_CONTRACT_FIELDS = (
    "name",
    "unit",
    "required_signals",
    "result",
    "expression",
    "expression_sha256",
    "expression_source",
    "source_reference",
    "expected_value_type",
    "nil_policy",
    "non_finite_policy",
)


@dataclass(frozen=True)
class _Assessment:
    classification: RealRunRecoveryClassification
    candidate_id: str | None
    issues: list[str]


@dataclass(frozen=True)
class RealRunRetryPackage:
    run_id: str
    failed_run_id: str
    decision_path: Path
    package: RealRunPackage


def assess_real_run_recovery(
    project_dir: Path,
    *,
    run_id: str,
    persist_report: bool = True,
) -> RealRunRecoveryReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id)
    bundle = assert_valid_project(project_dir)
    run_dir = _project_path(bundle.project_dir, f"{REAL_RUN_ROOT}/{selected_run_id}")
    report_path = _project_path(bundle.project_dir, RECOVERY_REPORT)
    if persist_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        assessment = _classify_run(
            project_dir,
            selected_run_id,
            run_dir,
            persist_reports=persist_report,
        )
    except Exception as exc:
        assessment = _Assessment(
            classification=RealRunRecoveryClassification.CONTRACT_INVALID,
            candidate_id=None,
            issues=[str(exc)],
        )
    try:
        attempt_number = _attempt_number(
            project_dir,
            assessment.candidate_id,
        )
    except Exception as exc:
        assessment = _Assessment(
            classification=RealRunRecoveryClassification.CONTRACT_INVALID,
            candidate_id=assessment.candidate_id,
            issues=[*assessment.issues, str(exc)],
        )
        attempt_number = 1

    status = (
        RealRunRecoveryStatus.FAIL
        if assessment.classification == RealRunRecoveryClassification.CONTRACT_INVALID
        else RealRunRecoveryStatus.PASS
    )
    retry_budget_remaining = max(0, MAX_ATTEMPTS_PER_CANDIDATE - attempt_number)
    allowed_actions = _allowed_actions(
        assessment.classification,
        retry_budget_remaining=retry_budget_remaining,
    )
    report = RealRunRecoveryReport(
        schema_version=DEFAULT_SCHEMA_VERSION,
        status=status,
        run_id=selected_run_id,
        candidate_id=assessment.candidate_id,
        classification=assessment.classification,
        allowed_actions=allowed_actions,
        recommended_action=allowed_actions[0] if allowed_actions else None,
        attempt_number=attempt_number,
        max_attempts_per_candidate=MAX_ATTEMPTS_PER_CANDIDATE,
        retry_budget_remaining=retry_budget_remaining,
        real_run_check_report=REAL_RUN_CHECK_REPORT,
        metric_result_check_report=METRIC_RESULT_CHECK_REPORT,
        ledger_path=LEDGER_PATH,
        recovery_decision=(
            _decision_relative(selected_run_id)
            if (run_dir / RECOVERY_DECISION_NAME).exists()
            else None
        ),
        issues=assessment.issues,
    )
    if persist_report:
        _write_report(report_path, report)
    return report


def prepare_real_run_retry(
    project_dir: Path,
    *,
    failed_run_id: str,
    retry_run_id: str | None = None,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRetryPackage:
    project_dir = Path(project_dir)
    selected_failed_run_id = _validate_run_id(failed_run_id)
    _assert_real_run_parent_dirs_are_not_symlinks(project_dir)
    selected_retry_run_id = _validate_run_id(retry_run_id) if retry_run_id else None
    if selected_retry_run_id == selected_failed_run_id:
        raise ValueError("retry run_id must differ from failed run_id")
    if selected_retry_run_id is not None:
        _assert_retry_target_available(project_dir, selected_retry_run_id)
    failed_run_dir = project_dir / REAL_RUN_ROOT / selected_failed_run_id
    decision_path = failed_run_dir / RECOVERY_DECISION_NAME
    _assert_decision_target_available(decision_path)

    assessment = assess_real_run_recovery(
        project_dir,
        run_id=selected_failed_run_id,
        persist_report=True,
    )
    if assessment.retry_budget_remaining <= 0:
        raise ValueError("retry budget is exhausted")
    if RealRunRecoveryAction.RETRY_SAME_CANDIDATE not in assessment.allowed_actions:
        raise ValueError("retry_same_candidate is not allowed for this run")

    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)
    bundle = assert_valid_project(project_dir)

    selected_retry_run_id = selected_retry_run_id or _next_unused_run_id(project_dir)

    retry_run_dir = _assert_retry_target_available(project_dir, selected_retry_run_id)
    retry_dir_existed = retry_run_dir.exists()

    failed_candidate = _load_json(failed_run_dir / "candidate.json")
    failed_input_text = _failed_rendered_input_text(failed_run_dir)
    failed_metric_request = _load_json(failed_run_dir / "metric_extraction_request.json")
    failed_parameters = failed_candidate.get("parameters")
    if not isinstance(failed_parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in failed_parameters.items()
    ):
        raise ValueError("failed run candidate parameters are invalid")
    candidate_id = assessment.candidate_id
    if candidate_id is None:
        raise ValueError("failed run candidate_id is unknown")

    decided_at = decided_at_utc or _utc_now()
    decision_payload = _decision_payload(
        project_dir,
        run_id=selected_failed_run_id,
        candidate_id=candidate_id,
        decision=RealRunRecoveryAction.RETRY_SAME_CANDIDATE,
        reason=reason,
        decided_at_utc=decided_at,
        retry_run_id=selected_retry_run_id,
        issues=assessment.issues,
    )
    decision_path.write_text(
        json.dumps(decision_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    retry_attempt_number = assessment.attempt_number + 1
    retry_candidate = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "source": "retry_same_candidate",
        "candidate_index": failed_candidate.get("candidate_index"),
        "parameters": failed_parameters,
        "retry_of_run_id": selected_failed_run_id,
        "retry_attempt_number": retry_attempt_number,
        "recovery_decision": _decision_relative(selected_failed_run_id),
    }
    try:
        package = _write_real_run_package(
            bundle,
            selected_retry_run_id,
            retry_candidate,
            decided_at,
            instruction,
            approved_hashes,
            manifest_extra={
                "candidate_source": "retry_same_candidate",
                "package_kind": "retry",
                "retry_of_run_id": selected_failed_run_id,
                "retry_attempt_number": retry_attempt_number,
                "recovery_decision": _decision_relative(selected_failed_run_id),
                "recovery_decision_sha256": sha256_file(decision_path),
            },
            rendered_text_override=failed_input_text,
        )
        _assert_metric_formula_contract_preserved(
            failed_metric_request,
            package.metric_request_payload,
        )
    except Exception:
        decision_path.unlink(missing_ok=True)
        if (
            not retry_dir_existed
            and retry_run_dir.exists()
            and not retry_run_dir.is_symlink()
        ):
            shutil.rmtree(retry_run_dir, ignore_errors=True)
        raise
    return RealRunRetryPackage(
        run_id=selected_retry_run_id,
        failed_run_id=selected_failed_run_id,
        decision_path=decision_path,
        package=package,
    )


def resolve_real_run_failure(
    project_dir: Path,
    *,
    run_id: str,
    decision: str,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRecoveryReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id)
    _assert_real_run_parent_dirs_are_not_symlinks(project_dir)
    action = RealRunRecoveryAction(decision)
    if action == RealRunRecoveryAction.RETRY_SAME_CANDIDATE:
        raise ValueError("use prepare_real_run_retry for retry_same_candidate")
    if action in {
        RealRunRecoveryAction.RECORD_RESULT,
        RealRunRecoveryAction.WAIT_FOR_EXECUTION,
    }:
        raise ValueError(f"{action.value} is not a recovery decision")
    run_dir = project_dir / REAL_RUN_ROOT / selected_run_id
    decision_path = run_dir / RECOVERY_DECISION_NAME
    _assert_decision_target_available(decision_path)

    assessment = assess_real_run_recovery(
        project_dir,
        run_id=selected_run_id,
        persist_report=True,
    )
    if action not in assessment.allowed_actions:
        raise ValueError(f"{action.value} is not allowed for this run")
    if assessment.candidate_id is None:
        raise ValueError("run candidate_id is unknown")

    payload = _decision_payload(
        project_dir,
        run_id=selected_run_id,
        candidate_id=assessment.candidate_id,
        decision=action,
        reason=reason,
        decided_at_utc=decided_at_utc or _utc_now(),
        retry_run_id=None,
        issues=assessment.issues,
    )
    decision_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return assess_real_run_recovery(project_dir, run_id=selected_run_id)


def assert_no_unresolved_real_runs(project_dir: Path) -> None:
    project_dir = Path(project_dir)
    _assert_real_run_parent_dirs_are_not_symlinks(project_dir)
    root = project_dir / REAL_RUN_ROOT
    if not root.exists():
        return
    unresolved: list[str] = []
    for run_dir in sorted(root.iterdir()):
        if not RUN_ID_RE.match(run_dir.name):
            continue
        if run_dir.is_symlink():
            raise FileExistsError(
                f"real run directory must not be a symlink: {run_dir}"
            )
        if not run_dir.is_dir():
            continue
        report = assess_real_run_recovery(
            project_dir,
            run_id=run_dir.name,
            persist_report=False,
        )
        if report.classification not in RESOLVED_CLASSIFICATIONS:
            unresolved.append(f"{run_dir.name}:{report.classification.value}")
    if unresolved:
        raise ValueError("unresolved real run exists: " + ", ".join(unresolved))


def _classify_run(
    project_dir: Path,
    run_id: str,
    run_dir: Path,
    *,
    persist_reports: bool,
) -> _Assessment:
    if not run_dir.exists():
        raise FileNotFoundError(f"real run directory is missing: {run_dir}")
    if run_dir.is_symlink():
        raise FileExistsError(f"real run directory must not be a symlink: {run_dir}")

    prepared = _load_json(run_dir / "real_run_manifest.json")
    candidate = _load_json(run_dir / "candidate.json")
    candidate_id = _candidate_id(prepared, candidate)
    contract_issues = _validate_metric_request_contract(
        run_dir,
        run_id,
        candidate_id,
        prepared,
    )
    if contract_issues:
        return _Assessment(
            RealRunRecoveryClassification.CONTRACT_INVALID,
            candidate_id,
            contract_issues,
        )
    decision = _load_optional_json(run_dir / RECOVERY_DECISION_NAME)
    if decision is not None:
        return _classify_resolved(project_dir, candidate_id, decision)

    if _ledger_has_run_or_candidate(project_dir, run_id, candidate_id):
        return _Assessment(
            RealRunRecoveryClassification.ALREADY_RECORDED,
            candidate_id,
            [],
        )

    result_path = run_dir / "result_manifest.json"
    if not result_path.exists():
        classification = (
            RealRunRecoveryClassification.TOOL_RESULT_MISSING
            if _has_execution_evidence(run_dir)
            else RealRunRecoveryClassification.PENDING_EXECUTION
        )
        return _Assessment(classification, candidate_id, [])

    result_payload = _load_json(result_path)
    if result_payload.get("status") == "failed":
        real_report = check_real_run(
            project_dir,
            run_id=run_id,
            persist_report=persist_reports,
        )
        if (
            real_report.status != RealRunCheckStatus.PASS
            and not _only_missing_metric_manifest(real_report)
        ):
            return _classify_real_run_check_failure(real_report, candidate_id)
        return _Assessment(
            RealRunRecoveryClassification.TOOL_RESULT_FAILED,
            candidate_id,
            [],
        )

    real_report = check_real_run(
        project_dir,
        run_id=run_id,
        persist_report=persist_reports,
    )
    if (
        real_report.status != RealRunCheckStatus.PASS
        and not _only_missing_metric_manifest(real_report)
    ):
        return _classify_real_run_check_failure(real_report, candidate_id)

    metric_manifest_path = run_dir / "metrics" / "metric_result_manifest.json"
    if not metric_manifest_path.exists():
        return _Assessment(
            RealRunRecoveryClassification.METRIC_RESULT_MISSING,
            candidate_id,
            [],
        )

    metric_report = check_metric_results(
        project_dir,
        run_id=run_id,
        persist_report=persist_reports,
    )
    if metric_report.status != MetricResultCheckStatus.PASS:
        return _Assessment(
            RealRunRecoveryClassification.METRIC_RESULT_FAILED,
            candidate_id,
            metric_report.issues,
        )

    return _Assessment(
        RealRunRecoveryClassification.RECORDABLE_SUCCESS,
        candidate_id,
        [],
    )


def _classify_resolved(
    project_dir: Path,
    candidate_id: str | None,
    decision: dict,
) -> _Assessment:
    decision_value = decision.get("decision")
    if decision_value == RealRunRecoveryAction.ABANDON_CANDIDATE.value:
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_ABANDONED,
            candidate_id,
            [],
        )
    if decision_value == RealRunRecoveryAction.STOP_WORKFLOW.value:
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_STOPPED,
            candidate_id,
            [],
        )
    if decision_value == RealRunRecoveryAction.RETRY_SAME_CANDIDATE.value:
        retry_run_id = decision.get("retry_run_id")
        if not isinstance(retry_run_id, str) or not RUN_ID_RE.match(retry_run_id):
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                ["retry decision has invalid retry_run_id"],
            )
        retry_dir = project_dir / REAL_RUN_ROOT / retry_run_id
        if retry_dir.is_symlink():
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                [f"retry real run directory must not be a symlink: {retry_dir}"],
            )
        retry_manifest_path = retry_dir / "real_run_manifest.json"
        retry_candidate_path = retry_dir / "candidate.json"
        if not retry_manifest_path.exists():
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                ["retry decision does not point to a prepared retry package"],
            )
        try:
            retry_manifest = _load_json(retry_manifest_path)
            retry_candidate = _load_json(retry_candidate_path)
        except (OSError, ValueError) as exc:
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                [f"retry package is invalid: {exc}"],
            )
        retry_issues = _validate_retry_package_identity(
            retry_run_id,
            candidate_id,
            retry_manifest,
            retry_candidate,
        )
        if retry_issues:
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                retry_issues,
            )
        if _ledger_has_run_or_candidate(project_dir, retry_run_id, candidate_id):
            return _Assessment(
                RealRunRecoveryClassification.ALREADY_RECORDED,
                candidate_id,
                [],
            )
        retry_decision = _load_optional_json(retry_dir / RECOVERY_DECISION_NAME)
        if retry_decision is not None:
            return _classify_resolved(project_dir, candidate_id, retry_decision)
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_RETRY_PREPARED,
            candidate_id,
            [],
        )
    if decision_value == RealRunRecoveryAction.REVISE_CONTRACTS.value:
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_STOPPED,
            candidate_id,
            ["contract revision decision requires a new approval flow"],
        )
    return _Assessment(
        RealRunRecoveryClassification.CONTRACT_INVALID,
        candidate_id,
        ["recovery decision is invalid"],
    )


def _allowed_actions(
    classification: RealRunRecoveryClassification,
    *,
    retry_budget_remaining: int,
) -> list[RealRunRecoveryAction]:
    retry_actions: list[RealRunRecoveryAction] = (
        [RealRunRecoveryAction.RETRY_SAME_CANDIDATE]
        if retry_budget_remaining > 0
        else []
    )
    table: dict[RealRunRecoveryClassification, list[RealRunRecoveryAction]] = {
        RealRunRecoveryClassification.PENDING_EXECUTION: [
            RealRunRecoveryAction.WAIT_FOR_EXECUTION,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.CONTRACT_INVALID: [
            RealRunRecoveryAction.REVISE_CONTRACTS,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_MISSING: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_FAILED: [
            *retry_actions,
            RealRunRecoveryAction.ABANDON_CANDIDATE,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_PARTIAL: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.METRIC_RESULT_MISSING: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.METRIC_RESULT_FAILED: [
            *retry_actions,
            RealRunRecoveryAction.ABANDON_CANDIDATE,
            RealRunRecoveryAction.REVISE_CONTRACTS,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.RECORDABLE_SUCCESS: [
            RealRunRecoveryAction.RECORD_RESULT,
        ],
        RealRunRecoveryClassification.ALREADY_RECORDED: [],
        RealRunRecoveryClassification.RESOLVED_RETRY_PREPARED: [],
        RealRunRecoveryClassification.RESOLVED_ABANDONED: [],
        RealRunRecoveryClassification.RESOLVED_STOPPED: [],
    }
    return table[classification]


def _validate_metric_request_contract(
    run_dir: Path,
    run_id: str,
    candidate_id: str,
    prepared: dict,
) -> list[str]:
    request_path = run_dir / "metric_extraction_request.json"
    if not request_path.exists():
        return ["metric extraction request is missing"]
    try:
        payload = _load_json(request_path)
    except (OSError, ValueError) as exc:
        return [f"metric extraction request is invalid: {exc}"]
    try:
        request = MetricExtractionRequest.model_validate(payload)
    except ValidationError as exc:
        return [f"metric extraction request is invalid: {exc}"]

    issues: list[str] = []
    expected_request = f"{REAL_RUN_ROOT}/{run_id}/metric_extraction_request.json"
    if prepared.get("metric_extraction_request") != expected_request:
        issues.append("prepared manifest metric_extraction_request is invalid")
    if prepared.get("metric_extraction_request_sha256") != sha256_file(request_path):
        issues.append("prepared manifest metric_extraction_request_sha256 mismatch")
    if request.run_id != run_id:
        issues.append("metric request run_id does not match selected run_id")
    if request.candidate_id != candidate_id:
        issues.append("metric request candidate_id does not match candidate")
    if request.backend != METRIC_BACKEND:
        issues.append(f"metric request backend is invalid: {request.backend}")
    if request.prepared_input_scs != prepared.get("rendered_input_scs"):
        issues.append("metric request prepared_input_scs does not match manifest")
    if request.prepared_input_sha256 != prepared.get("rendered_input_sha256"):
        issues.append("metric request prepared_input_sha256 does not match manifest")
    return issues


def _validate_retry_package_identity(
    retry_run_id: str,
    candidate_id: str | None,
    retry_manifest: dict,
    retry_candidate: dict,
) -> list[str]:
    issues: list[str] = []
    if retry_manifest.get("run_id") != retry_run_id:
        issues.append("retry manifest run_id does not match retry_run_id")
    if retry_manifest.get("status") != "prepared":
        issues.append("retry package is not prepared")
    if retry_manifest.get("candidate_id") != candidate_id:
        issues.append("retry manifest candidate_id does not match failed candidate")
    if retry_candidate.get("candidate_id") != candidate_id:
        issues.append("retry candidate_id does not match failed candidate")
    if retry_candidate.get("retry_attempt_number") != 2:
        issues.append("retry candidate retry_attempt_number is invalid")
    return issues


def _classify_real_run_check_failure(
    report: RealRunCheckReport,
    candidate_id: str | None,
) -> _Assessment:
    if _only_partial_artifact_issues(report.issues):
        return _Assessment(
            RealRunRecoveryClassification.TOOL_RESULT_PARTIAL,
            candidate_id,
            report.issues,
        )
    return _Assessment(
        RealRunRecoveryClassification.CONTRACT_INVALID,
        candidate_id,
        report.issues,
    )


def _only_partial_artifact_issues(issues: list[str]) -> bool:
    if not issues:
        return False
    return all(
        issue.startswith(("result artifact is missing:", "result artifact path is unsafe:"))
        for issue in issues
    )


def _only_missing_metric_manifest(report: RealRunCheckReport) -> bool:
    expected_issue = (
        f"result artifact is missing: {REAL_RUN_ROOT}/{report.run_id}/"
        "metrics/metric_result_manifest.json"
    )
    return (
        report.issues == [expected_issue]
        and report.checks.prepared_manifest_ok
        and report.checks.candidate_ok
        and report.checks.result_manifest_ok
        and report.checks.prepared_input_hash_ok
    )


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _project_path(project_dir: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must be project-relative and safe: {relative_path}")
    return project_dir / Path(*path.parts)


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"JSON file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON file is invalid: {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _load_optional_json(path: Path) -> dict | None:
    if path.is_symlink():
        raise FileExistsError(f"recovery decision must not be a symlink: {path}")
    if not path.exists():
        return None
    return _load_json(path)


def _candidate_id(prepared: dict, candidate: dict) -> str:
    prepared_candidate_id = prepared.get("candidate_id")
    candidate_candidate_id = candidate.get("candidate_id")
    if not isinstance(prepared_candidate_id, str):
        raise ValueError("prepared manifest candidate_id is invalid")
    if prepared_candidate_id != candidate_candidate_id:
        raise ValueError("candidate_id mismatch between manifest and candidate")
    return prepared_candidate_id


def _has_execution_evidence(run_dir: Path) -> bool:
    return any((run_dir / name).exists() for name in EXECUTION_EVIDENCE_NAMES)


def _ledger_rows(project_dir: Path) -> list[LedgerRow]:
    ledger_path = project_dir / LEDGER_PATH
    if not ledger_path.exists():
        return []
    rows: list[LedgerRow] = []
    for line_number, raw_line in enumerate(
        ledger_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not raw_line.strip():
            continue
        try:
            rows.append(LedgerRow.model_validate(json.loads(raw_line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"ledger row {line_number} is invalid: {exc}") from exc
    return rows


def _ledger_has_run_or_candidate(
    project_dir: Path,
    run_id: str,
    candidate_id: str | None,
) -> bool:
    for row in _ledger_rows(project_dir):
        if row.run_id == run_id or row.candidate_id == candidate_id:
            return True
    return False


def _attempt_number(project_dir: Path, candidate_id: str | None) -> int:
    if candidate_id is None:
        return 1
    root = project_dir / REAL_RUN_ROOT
    if not root.exists():
        return 1
    attempts = 0
    for run_dir in root.iterdir():
        if not RUN_ID_RE.match(run_dir.name):
            continue
        if run_dir.is_symlink():
            raise FileExistsError(f"real run directory must not be a symlink: {run_dir}")
        candidate_path = run_dir / "candidate.json"
        if not candidate_path.exists():
            continue
        candidate = _load_json(candidate_path)
        candidate_value = candidate.get("candidate_id")
        if candidate_value is not None and not isinstance(candidate_value, str):
            raise ValueError(f"candidate_id is invalid: {candidate_path}")
        if candidate.get("candidate_id") == candidate_id:
            attempts += 1
    return max(1, attempts)


def _decision_relative(run_id: str) -> str:
    return f"{REAL_RUN_ROOT}/{run_id}/{RECOVERY_DECISION_NAME}"


def _assert_retry_target_available(project_dir: Path, run_id: str) -> Path:
    _assert_real_run_parent_dirs_are_not_symlinks(project_dir)
    run_dir = project_dir / REAL_RUN_ROOT / run_id
    if run_dir.is_symlink():
        raise FileExistsError(f"real run directory must not be a symlink: {run_dir}")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"real run directory is not empty: {run_dir}")
    if run_dir.exists():
        raise FileExistsError(f"real run directory already exists: {run_dir}")
    return run_dir


def _assert_decision_target_available(decision_path: Path) -> None:
    if decision_path.is_symlink():
        raise FileExistsError(
            f"recovery decision must not be a symlink: {decision_path}"
        )
    if decision_path.exists():
        raise FileExistsError(f"recovery decision already exists: {decision_path}")


def _failed_rendered_input_text(failed_run_dir: Path) -> str:
    input_path = failed_run_dir / "input.scs"
    if not input_path.exists():
        raise FileNotFoundError(f"failed run rendered input is missing: {input_path}")
    return input_path.read_text(encoding="utf-8")


def _assert_metric_formula_contract_preserved(
    failed_request: dict,
    retry_request: dict,
) -> None:
    if _metric_formula_contract(failed_request) != _metric_formula_contract(
        retry_request
    ):
        raise ValueError(
            "retry metric formula contract does not match failed run"
        )


def _metric_formula_contract(request: dict) -> list[dict]:
    metrics = request.get("metrics")
    if not isinstance(metrics, list):
        raise ValueError("metric extraction request metrics are invalid")
    contract = []
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("metric extraction request metric is invalid")
        contract.append(
            {
                field: metric.get(field)
                for field in METRIC_FORMULA_CONTRACT_FIELDS
            }
        )
    return contract


def _decision_payload(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str,
    decision: RealRunRecoveryAction,
    reason: str,
    decided_at_utc: str,
    retry_run_id: str | None,
    issues: list[str],
) -> dict:
    report_path = project_dir / RECOVERY_REPORT
    payload = {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "decision": decision.value,
        "decided_at_utc": decided_at_utc,
        "decided_by": "supervisor_agent",
        "reason": reason,
        "source_recovery_report": RECOVERY_REPORT,
        "source_recovery_report_sha256": sha256_file(report_path),
        "issues": issues,
    }
    if retry_run_id is not None:
        payload["retry_run_id"] = retry_run_id
    return payload


def _write_report(path: Path, report: RealRunRecoveryReport) -> None:
    path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
