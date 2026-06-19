from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report


REPORT_RELATIVE = Path("reports/optimizer_finalize_report.json")
ACCEPTANCE_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")
COMPLETION_RELATIVE = Path("reports/optimizer_completion_report.json")
INSIGHT_RELATIVE = Path("reports/optimizer_insight_report.json")
INSIGHT_HTML_RELATIVE = Path("reports/optimizer_insight_report.html")


@dataclass(frozen=True)
class OptimizerFinalizeReport:
    status: str
    acceptance_status: str
    completion_status: str
    insight_status: str
    decision: str | None
    confidence: str | None
    best_observed_run_id: str | None
    reports: dict[str, str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None


def finalize_optimizer_run(project_dir: str | Path) -> OptimizerFinalizeReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []

    acceptance = check_optimizer_run(project_root)
    warnings.extend(acceptance.warnings)
    if acceptance.status != "accepted":
        issues.append("optimizer run acceptance rejected")
        issues.extend(acceptance.issues)
        return _write_finalize_report(
            project_root,
            OptimizerFinalizeReport(
                status="fail",
                acceptance_status=acceptance.status,
                completion_status="not_run",
                insight_status="not_run",
                decision=None,
                confidence=None,
                best_observed_run_id=None,
                reports=_report_paths(include_completion=False, include_insight=False),
                issues=issues,
                warnings=warnings,
                report_path=project_root / REPORT_RELATIVE,
            ),
        )

    completion = summarize_optimizer_run(project_root)
    warnings.extend(completion.warnings)
    if completion.status != "pass":
        issues.append("optimizer completion summary failed")
        issues.extend(completion.issues)
        return _write_finalize_report(
            project_root,
            OptimizerFinalizeReport(
                status="fail",
                acceptance_status=acceptance.status,
                completion_status=completion.status,
                insight_status="not_run",
                decision=completion.decision,
                confidence=completion.confidence,
                best_observed_run_id=_run_id(completion.best_observed),
                reports=_report_paths(include_completion=True, include_insight=False),
                issues=issues,
                warnings=warnings,
                report_path=project_root / REPORT_RELATIVE,
            ),
        )

    insight = generate_optimizer_insight_report(project_root)
    warnings.extend(insight.warnings)
    if insight.status != "pass":
        issues.append("optimizer insight report failed")
        issues.extend(insight.issues)

    return _write_finalize_report(
        project_root,
        OptimizerFinalizeReport(
            status="fail" if issues else "pass",
            acceptance_status=acceptance.status,
            completion_status=completion.status,
            insight_status=insight.status,
            decision=completion.decision,
            confidence=completion.confidence,
            best_observed_run_id=_run_id(completion.best_observed),
            reports=_report_paths(include_completion=True, include_insight=True),
            issues=issues,
            warnings=warnings,
            report_path=project_root / REPORT_RELATIVE,
        ),
    )


def _write_finalize_report(
    project_root: Path,
    report: OptimizerFinalizeReport,
) -> OptimizerFinalizeReport:
    report_path = project_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _report_paths(*, include_completion: bool, include_insight: bool) -> dict[str, str]:
    reports = {"acceptance": ACCEPTANCE_RELATIVE.as_posix()}
    if include_completion:
        reports["completion"] = COMPLETION_RELATIVE.as_posix()
    if include_insight:
        reports["insight"] = INSIGHT_RELATIVE.as_posix()
        reports["insight_html"] = INSIGHT_HTML_RELATIVE.as_posix()
    return reports


def _run_id(candidate: dict[str, Any] | None) -> str | None:
    if not isinstance(candidate, dict):
        return None
    run_id = candidate.get("run_id")
    return run_id if isinstance(run_id, str) and run_id else None
