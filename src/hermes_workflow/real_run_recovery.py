from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from hermes_workflow.metric_results import (
    METRIC_BACKEND,
    MetricExtractionRequest,
    check_metric_results,
)
from hermes_workflow.package import sha256_file
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


@dataclass(frozen=True)
class _Assessment:
    classification: RealRunRecoveryClassification
    candidate_id: str | None
    issues: list[str]


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
        assessment = _classify_run(project_dir, selected_run_id, run_dir)
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


def _classify_run(project_dir: Path, run_id: str, run_dir: Path) -> _Assessment:
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
        real_report = check_real_run(project_dir, run_id=run_id, persist_report=True)
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

    real_report = check_real_run(project_dir, run_id=run_id, persist_report=True)
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

    metric_report = check_metric_results(project_dir, run_id=run_id, persist_report=True)
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
    return all(issue.startswith("result artifact is missing:") for issue in issues)


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


def _write_report(path: Path, report: RealRunRecoveryReport) -> None:
    path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
