from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
    RealRunCheckStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.validate import assert_valid_project


DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
BEST_CANDIDATE_PATH = "state/best_candidate.json"
RECORD_REPORT_PATH = "reports/real_result_record_report.json"
RESULT_MANIFEST_NAME = "result_manifest.json"
METRIC_RESULT_MANIFEST_NAME = "metrics/metric_result_manifest.json"


def record_real_result(
    project_dir: Path,
    *,
    run_id: str | None = None,
    recorded_at_utc: str | None = None,
) -> RealResultRecordReport:
    project_dir = Path(project_dir)
    selected_run_id = run_id or DEFAULT_RUN_ID
    _recorded_at = recorded_at_utc or _utc_now()
    issues: list[str] = []
    checks = RealResultRecordFlags()
    candidate_id: str | None = None

    try:
        assert_valid_project(project_dir)
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
