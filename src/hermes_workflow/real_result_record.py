from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.mock_optimizer import (
    evaluate_constraints,
    evaluate_objective_from_config,
    write_best_candidate,
    write_ledger_row,
    write_optimizer_state,
)
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    MetricResultCheckReport,
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
    RealRunCheckStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.schemas import (
    BestCandidate,
    LedgerRow,
    ObjectiveDirection,
    OptimizerState,
)
from hermes_workflow.validate import assert_valid_project


DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
BEST_CANDIDATE_PATH = "state/best_candidate.json"
RECORD_REPORT_PATH = "reports/real_result_record_report.json"
RESULT_MANIFEST_NAME = "result_manifest.json"
METRIC_RESULT_MANIFEST_NAME = "metrics/metric_result_manifest.json"
REAL_PASS = "real_pass"
REAL_CONSTRAINT_FAIL = "real_constraint_fail"


def record_real_result(
    project_dir: Path,
    *,
    run_id: str | None = None,
    recorded_at_utc: str | None = None,
) -> RealResultRecordReport:
    project_dir = Path(project_dir)
    selected_run_id = run_id or DEFAULT_RUN_ID
    recorded_at = recorded_at_utc or _utc_now()
    issues: list[str] = []
    checks = RealResultRecordFlags()
    candidate_id: str | None = None
    bundle = None
    metric_report: MetricResultCheckReport | None = None

    try:
        bundle = assert_valid_project(project_dir)
    except (OSError, ValueError) as exc:
        issues.append(str(exc))

    if not issues:
        try:
            real_report = check_real_run(
                project_dir,
                run_id=selected_run_id,
                persist_report=False,
            )
        except (OSError, ValueError) as exc:
            issues.append(str(exc))
        else:
            checks.real_run_check_ok = real_report.status == RealRunCheckStatus.PASS
            candidate_id = real_report.candidate_id
            if real_report.status != RealRunCheckStatus.PASS:
                issues.extend(real_report.issues)

    if not issues:
        try:
            metric_report = check_metric_results(
                project_dir,
                run_id=selected_run_id,
                persist_report=False,
            )
        except (OSError, ValueError) as exc:
            issues.append(str(exc))
        else:
            checks.metric_result_check_ok = (
                metric_report.status == MetricResultCheckStatus.PASS
            )
            candidate_id = metric_report.candidate_id or candidate_id
            if metric_report.status != MetricResultCheckStatus.PASS:
                issues.extend(metric_report.issues)

    row: LedgerRow | None = None
    best_candidate: BestCandidate | None = None
    best_candidate_id: str | None = None

    if not issues and bundle is not None and metric_report is not None:
        candidate_id = metric_report.candidate_id or candidate_id
        parameters = _candidate_parameters(
            project_dir,
            selected_run_id,
            candidate_id,
            issues,
        )
        if parameters is not None:
            checks.candidate_ok = True
        ledger_rows = _read_ledger_rows(project_dir, issues)
        if not issues and candidate_id is not None:
            checks.duplicate_ok = _check_duplicates(
                ledger_rows,
                run_id=selected_run_id,
                candidate_id=candidate_id,
                issues=issues,
            )
        metrics = _checked_metric_values(metric_report, issues)

        if parameters is not None and metrics is not None and candidate_id is not None:
            try:
                constraints_passed = evaluate_constraints(bundle.metrics, metrics)
                checks.constraints_ok = True
            except (TypeError, ValueError) as exc:
                issues.append(f"constraint evaluation failed: {exc}")
                constraints_passed = False

            try:
                objective_value = evaluate_objective_from_config(bundle.metrics, metrics)
                if bundle.metrics.objective.direction == ObjectiveDirection.MAXIMIZE:
                    objective_value = -objective_value
                checks.objective_ok = True
            except (TypeError, ValueError) as exc:
                issues.append(f"objective evaluation failed: {exc}")
                objective_value = 0.0

            if not issues:
                simulation_status = (
                    REAL_PASS if constraints_passed else REAL_CONSTRAINT_FAIL
                )
                row = LedgerRow(
                    candidate_id=candidate_id,
                    parameters=parameters,
                    metrics=metrics,
                    constraints_passed=constraints_passed,
                    objective=objective_value,
                    batch_id=_next_batch_id(
                        len(ledger_rows),
                        bundle.optimizer.optimizer.batch_size,
                    ),
                    simulation_status=simulation_status,
                    timestamp_utc=recorded_at,
                    result_source="real",
                    run_id=selected_run_id,
                    result_manifest=(
                        f"{REAL_RUN_ROOT}/{selected_run_id}/{RESULT_MANIFEST_NAME}"
                    ),
                    metric_result_manifest=(
                        f"{REAL_RUN_ROOT}/{selected_run_id}/"
                        f"{METRIC_RESULT_MANIFEST_NAME}"
                    ),
                )
                existing_best = _load_best_candidate(project_dir, issues)
                if not issues:
                    best_candidate = _choose_best(existing_best, row)
                    best_candidate_id = (
                        best_candidate.candidate_id
                        if best_candidate is not None
                        else None
                    )

    if not issues and bundle is not None and row is not None:
        write_ledger_row(project_dir, row)
        checks.ledger_write_ok = True
        if best_candidate is not None and best_candidate.candidate_id == row.candidate_id:
            write_best_candidate(project_dir, best_candidate)
        state = _new_optimizer_state(
            bundle,
            current_evaluations=len(ledger_rows) + 1,
            best_candidate_id=best_candidate_id,
            recorded_at_utc=recorded_at,
        )
        write_optimizer_state(project_dir, state)
        checks.state_write_ok = True

        report = RealResultRecordReport(
            schema_version="1.0",
            status=RealResultRecordStatus.PASS,
            run_id=selected_run_id,
            candidate_id=row.candidate_id,
            ledger_path=LEDGER_PATH,
            optimizer_state_path=OPTIMIZER_STATE_PATH,
            best_candidate_path=(
                BEST_CANDIDATE_PATH if best_candidate is not None else None
            ),
            checks=checks,
            issues=[],
        )
        _write_report(project_dir, report)
        return report

    report = RealResultRecordReport(
        schema_version="1.0",
        status=RealResultRecordStatus.FAIL,
        run_id=selected_run_id,
        candidate_id=candidate_id,
        ledger_path=LEDGER_PATH,
        optimizer_state_path=OPTIMIZER_STATE_PATH,
        best_candidate_path=None,
        checks=checks,
        issues=issues,
    )
    _write_report(project_dir, report)
    return report


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_report(project_dir: Path, report: RealResultRecordReport) -> Path:
    report_path = project_dir / RECORD_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report_path


def _load_json(path: Path, label: str, issues: list[str]) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        issues.append(f"{label} cannot be read: {exc}")
        return None
    except json.JSONDecodeError as exc:
        issues.append(f"{label} is invalid JSON: {exc.msg}")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label} is invalid")
        return None
    return payload


def _candidate_parameters(
    project_dir: Path,
    run_id: str,
    candidate_id: str | None,
    issues: list[str],
) -> dict[str, str] | None:
    payload = _load_json(
        project_dir / REAL_RUN_ROOT / run_id / "candidate.json",
        "candidate file",
        issues,
    )
    if payload is None:
        return None
    if payload.get("candidate_id") != candidate_id:
        issues.append("candidate id mismatch")
        return None
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parameters.items()
    ):
        issues.append("candidate parameters are invalid")
        return None
    return parameters


def _checked_metric_values(
    metric_report: MetricResultCheckReport,
    issues: list[str],
) -> dict[str, float] | None:
    metrics: dict[str, float] = {}
    for name, checked in metric_report.metrics.items():
        if checked.value is None or not math.isfinite(checked.value):
            issues.append(f"metric {name} value is not finite")
            return None
        metrics[name] = float(checked.value)
    return metrics


def _read_ledger_rows(project_dir: Path, issues: list[str]) -> list[LedgerRow]:
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
            payload = json.loads(raw_line)
            rows.append(LedgerRow.model_validate(payload))
        except (json.JSONDecodeError, ValidationError) as exc:
            issues.append(f"ledger row {line_number} is invalid: {exc}")
            return []
    return rows


def _check_duplicates(
    rows: list[LedgerRow],
    *,
    run_id: str,
    candidate_id: str,
    issues: list[str],
) -> bool:
    duplicate_issues: list[str] = []
    for row in rows:
        if row.run_id == run_id:
            duplicate_issues.append(f"ledger already contains run_id {run_id}")
        if row.candidate_id == candidate_id:
            duplicate_issues.append(
                f"ledger already contains candidate_id {candidate_id}"
            )
    issues.extend(duplicate_issues)
    return not duplicate_issues


def _load_best_candidate(project_dir: Path, issues: list[str]) -> BestCandidate | None:
    best_path = project_dir / BEST_CANDIDATE_PATH
    if not best_path.exists():
        return None
    payload = _load_json(best_path, "best candidate", issues)
    if payload is None:
        return None
    try:
        return BestCandidate.model_validate(payload)
    except ValidationError as exc:
        issues.append(f"best candidate is invalid: {exc}")
        return None


def _choose_best(
    existing: BestCandidate | None,
    current: LedgerRow,
) -> BestCandidate | None:
    if not current.constraints_passed:
        return existing
    if existing is not None and current.objective >= existing.objective:
        return existing
    return BestCandidate(
        candidate_id=current.candidate_id,
        parameters=current.parameters,
        metrics=current.metrics,
        constraints_passed=current.constraints_passed,
        objective=current.objective,
        batch_id=current.batch_id,
        timestamp_utc=current.timestamp_utc,
    )


def _next_batch_id(existing_count: int, batch_size: int) -> int:
    return (existing_count // batch_size) + 1


def _new_optimizer_state(
    bundle: object,
    *,
    current_evaluations: int,
    best_candidate_id: str | None,
    recorded_at_utc: str,
) -> OptimizerState:
    optimizer = bundle.optimizer.optimizer
    status = (
        "completed" if current_evaluations >= optimizer.max_evaluations else "running"
    )
    started_at = _existing_started_at(bundle.project_dir) or recorded_at_utc
    return OptimizerState(
        schema_version="1.0",
        project_name=bundle.project_config.project.name,
        algorithm=optimizer.algorithm.value,
        initialization=optimizer.initialization.value,
        current_evaluations=current_evaluations,
        max_evaluations=optimizer.max_evaluations,
        batch_size=optimizer.batch_size,
        random_seed=optimizer.random_seed,
        best_candidate_id=best_candidate_id,
        status=status,
        started_at_utc=started_at,
        updated_at_utc=recorded_at_utc,
    )


def _existing_started_at(project_dir: Path) -> str | None:
    payload = _load_json(project_dir / OPTIMIZER_STATE_PATH, "optimizer state", [])
    if payload is None:
        return None
    started_at = payload.get("started_at_utc")
    return started_at if isinstance(started_at, str) else None
