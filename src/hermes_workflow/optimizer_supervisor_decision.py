from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_decision import (
    REPORT_RELATIVE as DECISION_REPORT_RELATIVE,
    generate_optimizer_decision_report,
)


REPORT_RELATIVE = Path("reports/optimizer_supervisor_decision.json")
MARKDOWN_RELATIVE = Path("reports/optimizer_supervisor_decision.md")
ALLOWED_ACTIONS = {
    "accept_best_observed",
    "continue_optimization",
    "revise_fom_or_constraints",
}


@dataclass(frozen=True)
class OptimizerSupervisorDecisionReport:
    status: str
    action: str
    accepted_run_id: str | None
    reason: str
    decided_at_utc: str
    global_optimum_claim: bool
    source_decision_report: str
    accepted_candidate: dict[str, Any]
    source_decision: dict[str, Any]
    boundaries: dict[str, Any]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None
    markdown_path: Path | None = None


def record_optimizer_supervisor_decision(
    project_dir: str | Path,
    *,
    action: str = "accept_best_observed",
    reason: str = "Supervisor accepted the current optimizer decision report.",
) -> OptimizerSupervisorDecisionReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []
    if action not in ALLOWED_ACTIONS:
        issues.append(f"unsupported optimizer supervisor action: {action}")

    decision = generate_optimizer_decision_report(project_root)
    warnings.extend(decision.warnings)
    if decision.status != "pass":
        issues.append("optimizer decision report failed")
        issues.extend(decision.issues)

    accepted_run_id = (
        decision.recommended_run_id if action == "accept_best_observed" else None
    )
    report = OptimizerSupervisorDecisionReport(
        status="fail" if issues else "pass",
        action=action,
        accepted_run_id=accepted_run_id,
        reason=reason,
        decided_at_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
        global_optimum_claim=False,
        source_decision_report=DECISION_REPORT_RELATIVE.as_posix(),
        accepted_candidate=decision.recommended_candidate
        if action == "accept_best_observed"
        else {},
        source_decision={
            "recommended_run_id": decision.recommended_run_id,
            "recommended_action": decision.recommended_action,
            "recommendation_basis": decision.recommendation_basis,
            "confidence": decision.confidence,
            "bottleneck": decision.bottleneck,
            "status_counts": decision.status_counts,
        },
        boundaries={
            "best_candidate_scope": "best_observed",
            "global_optimum_claim": False,
            "real_tool_rerun_performed": False,
        },
        issues=issues,
        warnings=warnings,
        report_path=project_root / REPORT_RELATIVE,
        markdown_path=project_root / MARKDOWN_RELATIVE,
    )
    _write_outputs(project_root, report)
    return report


def _write_outputs(
    project_root: Path,
    report: OptimizerSupervisorDecisionReport,
) -> None:
    report_path = project_root / REPORT_RELATIVE
    markdown_path = project_root / MARKDOWN_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    payload["markdown_path"] = MARKDOWN_RELATIVE.as_posix()
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")


def _markdown_report(report: OptimizerSupervisorDecisionReport) -> str:
    lines = [
        "# Optimizer Supervisor Decision",
        "",
        "## Decision",
        "",
        f"- Action: {report.action}",
        f"- Accepted run: {report.accepted_run_id or 'none'}",
        f"- Reason: {report.reason}",
        f"- Decided at UTC: {report.decided_at_utc}",
        f"- Global optimum claim: {str(report.global_optimum_claim).lower()}",
        "",
        "## Source Decision",
        "",
        f"- Source report: {report.source_decision_report}",
        f"- Recommendation basis: {report.source_decision.get('recommendation_basis')}",
        f"- Recommended action: {report.source_decision.get('recommended_action')}",
        f"- Confidence: {report.source_decision.get('confidence')}",
        f"- Bottleneck: {json.dumps(report.source_decision.get('bottleneck'), sort_keys=True)}",
        "",
        "## Accepted Candidate",
        "",
        f"- Candidate: {json.dumps(report.accepted_candidate, sort_keys=True)}",
        "",
        "## Boundaries",
        "",
        "- The accepted point is best observed under the current artifacts and FoM.",
        "- This record does not claim global optimality.",
        "- No Spectre/OCEAN rerun is performed while recording this decision.",
    ]
    if report.issues:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"
