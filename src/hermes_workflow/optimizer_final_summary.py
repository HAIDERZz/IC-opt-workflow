from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_decision import (
    REPORT_RELATIVE as DECISION_REPORT_RELATIVE,
    generate_optimizer_decision_report,
)
from hermes_workflow.optimizer_supervisor_decision import (
    REPORT_RELATIVE as SUPERVISOR_DECISION_RELATIVE,
    record_optimizer_supervisor_decision,
)


REPORT_RELATIVE = Path("reports/optimizer_final_summary.json")
MARKDOWN_RELATIVE = Path("reports/optimizer_final_summary.md")
INSIGHT_REPORT_RELATIVE = Path("reports/optimizer_insight_report.json")
INSIGHT_MARKDOWN_RELATIVE = Path("reports/optimizer_insight_report.md")


@dataclass(frozen=True)
class OptimizerFinalSummaryReport:
    status: str
    accepted_run_id: str | None
    action: str
    global_optimum_claim: bool
    accepted_candidate: dict[str, Any]
    bottleneck: dict[str, Any]
    score_summary: dict[str, Any]
    status_counts: dict[str, int]
    visuals: list[str]
    reports: dict[str, str]
    boundaries: dict[str, Any]
    next_steps: list[str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None
    markdown_path: Path | None = None


def generate_optimizer_final_summary(
    project_dir: str | Path,
) -> OptimizerFinalSummaryReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []

    decision = generate_optimizer_decision_report(project_root)
    warnings.extend(decision.warnings)
    if decision.status != "pass":
        issues.append("optimizer decision report failed")
        issues.extend(decision.issues)

    supervisor = _load_supervisor_decision(project_root)
    if not supervisor:
        supervisor_report = record_optimizer_supervisor_decision(project_root)
        warnings.extend(supervisor_report.warnings)
        if supervisor_report.status != "pass":
            issues.append("optimizer supervisor decision report failed")
            issues.extend(supervisor_report.issues)
        supervisor = _load_supervisor_decision(project_root)
    if not supervisor:
        issues.append("optimizer supervisor decision report is unavailable")

    accepted_candidate = _dict_value(supervisor.get("accepted_candidate")) if supervisor else {}
    action = _string_value(supervisor.get("action")) if supervisor else "unknown"
    accepted_run_id = (
        _string_value(supervisor.get("accepted_run_id")) if supervisor else None
    )
    visuals = _visual_paths(project_root)
    report = OptimizerFinalSummaryReport(
        status="fail" if issues else "pass",
        accepted_run_id=accepted_run_id or None,
        action=action,
        global_optimum_claim=False,
        accepted_candidate=accepted_candidate,
        bottleneck=decision.bottleneck,
        score_summary=decision.score_summary,
        status_counts=decision.status_counts,
        visuals=visuals,
        reports=_report_paths(project_root),
        boundaries={
            "best_candidate_scope": "best_observed",
            "global_optimum_claim": False,
            "real_tool_rerun_performed": False,
        },
        next_steps=_next_steps(action, accepted_run_id),
        issues=issues,
        warnings=warnings,
        report_path=project_root / REPORT_RELATIVE,
        markdown_path=project_root / MARKDOWN_RELATIVE,
    )
    _write_outputs(project_root, report)
    return report


def _load_supervisor_decision(project_root: Path) -> dict[str, Any]:
    path = project_root / SUPERVISOR_DECISION_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _visual_paths(project_root: Path) -> list[str]:
    candidates = [
        "reports/optimizer_visuals/bottleneck_weighted_score.png",
        "reports/optimizer_visuals/all_evaluable_fom.svg",
        "reports/optimizer_visuals/feasible_convergence.svg",
        "reports/optimizer_visuals/constraint_margins.svg",
        "reports/openbox_advanced_visualization_manifest.json",
    ]
    return [path for path in candidates if (project_root / path).exists()]


def _report_paths(project_root: Path) -> dict[str, str]:
    candidates = {
        "final_summary_json": REPORT_RELATIVE.as_posix(),
        "final_summary_markdown": MARKDOWN_RELATIVE.as_posix(),
        "supervisor_decision": SUPERVISOR_DECISION_RELATIVE.as_posix(),
        "optimizer_decision": DECISION_REPORT_RELATIVE.as_posix(),
        "optimizer_insight": INSIGHT_REPORT_RELATIVE.as_posix(),
        "optimizer_insight_markdown": INSIGHT_MARKDOWN_RELATIVE.as_posix(),
    }
    return {
        name: path
        for name, path in candidates.items()
        if name.startswith("final_summary") or (project_root / path).exists()
    }


def _next_steps(action: str, accepted_run_id: str | None) -> list[str]:
    if action == "accept_best_observed":
        run_label = accepted_run_id or "the accepted run"
        return [
            f"Use {run_label} as the current accepted optimizer result.",
            "Review the bottleneck metric before deciding whether to continue optimization.",
            "For a new FoM or new constraints, regenerate reports from existing metrics first before spending more simulations.",
        ]
    return [
        "Follow the supervisor decision record before running more optimizer work.",
        "Regenerate the final summary after the supervisor decision changes.",
    ]


def _write_outputs(project_root: Path, report: OptimizerFinalSummaryReport) -> None:
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


def _markdown_report(report: OptimizerFinalSummaryReport) -> str:
    parameters = _dict_value(report.accepted_candidate.get("parameters"))
    metrics = _dict_value(report.accepted_candidate.get("metrics"))
    lines = [
        "# Optimizer Final Summary",
        "",
        "## Accepted Result",
        "",
        f"- Accepted run: {report.accepted_run_id or 'none'}",
        f"- Action: {report.action}",
        "- Scope: Best observed under the current evaluated artifacts and FoM.",
        f"- Global optimum claim: {str(report.global_optimum_claim).lower()}",
        f"- Parameters: {json.dumps(parameters, sort_keys=True)}",
        f"- Metrics: {json.dumps(metrics, sort_keys=True)}",
        "",
        "## Score And Bottleneck",
        "",
        f"- Score summary: {json.dumps(report.score_summary, sort_keys=True)}",
        f"- Bottleneck: {json.dumps(report.bottleneck, sort_keys=True)}",
        f"- Status counts: {json.dumps(report.status_counts, sort_keys=True)}",
        "",
        "## Visuals",
        "",
    ]
    if report.visuals:
        lines.extend(f"- {path}" for path in report.visuals)
    else:
        lines.append("- No optimizer visual artifacts were found.")
    lines.extend(
        [
            "",
            "## Reports",
            "",
        ]
    )
    lines.extend(f"- {name}: {path}" for name, path in sorted(report.reports.items()))
    lines.extend(
        [
            "",
            "## Next Steps",
            "",
        ]
    )
    lines.extend(f"- {step}" for step in report.next_steps)
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- Best observed means the best accepted point among evaluated artifacts, not a proof of global optimum.",
            "- No Spectre/OCEAN rerun is performed while generating this final summary.",
        ]
    )
    if report.issues:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""
