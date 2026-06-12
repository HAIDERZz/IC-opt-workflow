from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_insights import generate_optimizer_insight_report


REPORT_RELATIVE = Path("reports/optimizer_decision_report.json")
MARKDOWN_RELATIVE = Path("reports/optimizer_decision_report.md")
INSIGHT_RELATIVE = Path("reports/optimizer_insight_report.json")
COMPLETION_RELATIVE = Path("reports/optimizer_completion_report.json")
FINALIZE_RELATIVE = Path("reports/optimizer_finalize_report.json")


@dataclass(frozen=True)
class OptimizerDecisionReport:
    status: str
    recommended_run_id: str | None
    recommendation_basis: str
    recommended_action: str
    confidence: str
    global_optimum_claim: bool
    recommended_candidate: dict[str, Any]
    bottleneck: dict[str, Any]
    score_summary: dict[str, Any]
    evaluation_count: int
    status_counts: dict[str, int]
    boundaries: dict[str, Any]
    next_steps: list[str]
    reports: dict[str, str]
    process_corner_summary: dict[str, Any]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None
    markdown_path: Path | None = None


def generate_optimizer_decision_report(
    project_dir: str | Path,
) -> OptimizerDecisionReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []

    insight = generate_optimizer_insight_report(project_root)
    warnings.extend(insight.warnings)
    if insight.status != "pass":
        issues.append("optimizer insight report failed")
        issues.extend(insight.issues)

    candidate, basis, selection_warnings = _select_candidate(
        insight.configured_objective_ranking,
        insight.best_observed,
        insight.top_feasible_candidates,
    )
    warnings.extend(selection_warnings)
    if not candidate and basis != "no_feasible_candidate":
        issues.append("no recommended optimizer candidate found")

    run_id = _string_value(candidate.get("run_id")) if candidate else None
    bottleneck = _bottleneck_for_run(
        insight.bottleneck_weighted_score_summary,
        run_id,
    )
    score_summary = _score_summary_for_run(
        insight.bottleneck_weighted_score_summary,
        run_id,
    )
    action = _recommended_action(
        candidate=candidate,
        status_counts=insight.status_counts,
        has_issues=bool(issues),
    )
    confidence = _confidence(
        candidate=candidate,
        evaluation_count=insight.evaluation_count,
        status_counts=insight.status_counts,
        has_issues=bool(issues),
    )
    boundaries = {
        "best_candidate_scope": "best_observed",
        "global_optimum_claim": False,
        "real_tool_rerun_performed": False,
        "notes": [
            "This report ranks artifacts already present in the optimizer run.",
            "The recommended point is not a mathematical global optimum certificate.",
        ],
    }
    next_steps = _next_steps(action, run_id)

    report = OptimizerDecisionReport(
        status="fail" if issues else "pass",
        recommended_run_id=run_id,
        recommendation_basis=basis,
        recommended_action=action,
        confidence=confidence,
        global_optimum_claim=False,
        recommended_candidate=candidate or {},
        bottleneck=bottleneck,
        score_summary=score_summary,
        evaluation_count=insight.evaluation_count,
        status_counts=insight.status_counts,
        boundaries=boundaries,
        next_steps=next_steps,
        reports=_report_paths(project_root),
        process_corner_summary=insight.process_corner_summary,
        issues=issues,
        warnings=warnings,
        report_path=project_root / REPORT_RELATIVE,
        markdown_path=project_root / MARKDOWN_RELATIVE,
    )
    _write_outputs(project_root, report)
    return report


def _select_candidate(
    configured_ranking: dict[str, Any],
    best_observed: dict[str, Any] | None,
    top_feasible_candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, list[str]]:
    warnings: list[str] = []
    configured = _dict_value(configured_ranking.get("best_candidate"))
    if _is_feasible(configured):
        return configured, "configured_objective_ranking", warnings
    if configured is not None:
        warnings.append(
            "configured objective best candidate is not feasible; "
            f"ignored as primary recommendation: {_candidate_label(configured)}"
        )
    if _is_feasible(best_observed):
        return best_observed, "stored_best_observed_feasible_fallback", warnings
    top_feasible = _first_dict(top_feasible_candidates)
    if top_feasible is not None:
        candidate = dict(top_feasible)
        candidate.setdefault("status", "feasible")
        return candidate, "top_feasible_candidate_fallback", warnings
    if best_observed is not None:
        warnings.append(
            "stored best observed candidate is not feasible; "
            f"no primary recommendation: {_candidate_label(best_observed)}"
        )
    return None, "no_feasible_candidate", warnings

def _is_feasible(candidate: dict[str, Any] | None) -> bool:
    return bool(candidate) and _string_value(candidate.get("status")) == "feasible"

def _first_dict(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None

def _candidate_label(candidate: dict[str, Any]) -> str:
    run_id = _string_value(candidate.get("run_id")) or "unknown"
    status = _string_value(candidate.get("status")) or "unknown"
    return f"{run_id} status={status}"


def _recommended_action(
    *,
    candidate: dict[str, Any] | None,
    status_counts: dict[str, int],
    has_issues: bool,
) -> str:
    if has_issues:
        return "review_artifacts_before_decision"
    if not candidate:
        if status_counts and status_counts.get("feasible", 0) == 0:
            return "adjust_constraints_or_continue"
        return "continue_or_review_no_candidate"
    if _string_value(candidate.get("status")) == "feasible":
        return "accept_best_observed_or_continue"
    if status_counts.get("feasible", 0) > 0:
        return "review_best_feasible_or_continue"
    return "adjust_constraints_or_continue"


def _confidence(
    *,
    candidate: dict[str, Any] | None,
    evaluation_count: int,
    status_counts: dict[str, int],
    has_issues: bool,
) -> str:
    if has_issues or not candidate:
        return "low"
    if _string_value(candidate.get("status")) != "feasible":
        return "low"
    if evaluation_count >= 100 and status_counts.get("feasible", 0) >= 10:
        return "medium"
    return "low"


def _bottleneck_for_run(
    bottleneck_summary: dict[str, Any],
    run_id: str | None,
) -> dict[str, Any]:
    point = _bottleneck_point(bottleneck_summary, run_id)
    component_scores = _dict_value(point.get("component_scores"), default={})
    numeric_scores = {
        name: float(value)
        for name, value in component_scores.items()
        if isinstance(value, int | float)
    }
    if not numeric_scores:
        return {"status": "not_available"}
    metric, score = min(numeric_scores.items(), key=lambda item: item[1])
    return {
        "status": "available",
        "metric": metric,
        "score": score,
        "component_scores": numeric_scores,
    }


def _score_summary_for_run(
    bottleneck_summary: dict[str, Any],
    run_id: str | None,
) -> dict[str, Any]:
    point = _bottleneck_point(bottleneck_summary, run_id)
    if not point:
        return {"status": "not_available"}
    return {
        "status": "available",
        "weighted_score": point.get("weighted_score"),
        "bottleneck_score": point.get("bottleneck_score"),
        "combined_score": point.get("combined_score"),
        "combined_objective": point.get("combined_objective"),
        "formula": bottleneck_summary.get("formula"),
    }


def _bottleneck_point(
    bottleneck_summary: dict[str, Any],
    run_id: str | None,
) -> dict[str, Any]:
    if not run_id:
        return {}
    for point in bottleneck_summary.get("series", []):
        if isinstance(point, dict) and _string_value(point.get("run_id")) == run_id:
            return point
    return {}


def _next_steps(action: str, run_id: str | None) -> list[str]:
    if action == "accept_best_observed_or_continue":
        target = run_id or "the recommended candidate"
        return [
            f"Use {target} as the current best observed point.",
            "Continue optimization only if more budget is justified by the design goal.",
            "For post-layout or new constraints, rerun from the same project artifacts rather than rebuilding the flow.",
        ]
    if action == "adjust_constraints_or_continue":
        return [
            "Review metric thresholds and objective definition before spending more simulations.",
            "If the constraints are intentional, continue with a larger budget or adjusted search space.",
        ]
    return [
        "Review the report issues before accepting a candidate.",
        "Regenerate acceptance, insight, and decision reports after fixing artifacts.",
    ]


def _report_paths(project_root: Path) -> dict[str, str]:
    reports = {
        "insight": INSIGHT_RELATIVE.as_posix(),
        "decision_json": REPORT_RELATIVE.as_posix(),
        "decision_markdown": MARKDOWN_RELATIVE.as_posix(),
    }
    if (project_root / COMPLETION_RELATIVE).exists():
        reports["completion"] = COMPLETION_RELATIVE.as_posix()
    if (project_root / FINALIZE_RELATIVE).exists():
        reports["finalize"] = FINALIZE_RELATIVE.as_posix()
    return reports


def _write_outputs(project_root: Path, report: OptimizerDecisionReport) -> None:
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


def _markdown_report(report: OptimizerDecisionReport) -> str:
    candidate = report.recommended_candidate
    parameters = _dict_value(candidate.get("parameters"), default={})
    metrics = _dict_value(candidate.get("metrics"), default={})
    process_corner_summary = _dict_value(report.process_corner_summary, default={})
    lines = [
        "# Optimizer Decision Report",
        "",
        "## Recommendation",
        "",
        f"- Recommended run: {report.recommended_run_id or 'none'}",
        f"- Action: {report.recommended_action}",
        f"- Basis: {report.recommendation_basis}",
        f"- Confidence: {report.confidence}",
        f"- Global optimum claim: {str(report.global_optimum_claim).lower()}",
        "",
        "## Recommended Candidate",
        "",
        f"- Status: {_string_value(candidate.get('status')) or 'unknown'}",
        f"- Objective: {candidate.get('objective')}",
        f"- Parameters: {json.dumps(parameters, sort_keys=True)}",
        f"- Metrics: {json.dumps(metrics, sort_keys=True)}",
        "",
    ]
    if process_corner_summary.get("enabled"):
        objective_policy = (
            _string_value(process_corner_summary.get("objective_policy")) or "nominal"
        )
        constraint_policy = (
            _string_value(process_corner_summary.get("constraint_policy")) or "nominal"
        )
        selected_corner = (
            _string_value(process_corner_summary.get("selected_corner")) or "n/a"
        )
        worst_corner = (
            _string_value(process_corner_summary.get("worst_corner")) or "n/a"
        )
        lines.extend(
            [
                "## Worst-Case Objective Basis",
                "",
                (
                    "- This recommendation is the best observed feasible candidate "
                    f"under {objective_policy} corner objective."
                ),
                f"- Constraint policy: `{constraint_policy}`",
                f"- Objective policy: `{objective_policy}`",
                f"- Selected corner: `{selected_corner}`",
                f"- Worst corner: `{worst_corner}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Bottleneck",
            "",
        ]
    )
    if report.bottleneck.get("status") == "available":
        lines.extend(
            [
                f"- Metric: {report.bottleneck.get('metric')}",
                f"- Score: {report.bottleneck.get('score')}",
                f"- Component scores: {json.dumps(report.bottleneck.get('component_scores'), sort_keys=True)}",
            ]
        )
    else:
        lines.append("- Bottleneck score was not available for the recommended run.")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Evaluations: {report.evaluation_count}",
            f"- Status counts: {json.dumps(report.status_counts, sort_keys=True)}",
            f"- Score summary: {json.dumps(report.score_summary, sort_keys=True)}",
            "",
            "## Next Action",
            "",
        ]
    )
    lines.extend(f"- {step}" for step in report.next_steps)
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- The selected point is the best observed/configured candidate in the available artifacts.",
            "- This report does not claim global optimality.",
            "- No Spectre/OCEAN rerun is performed while generating this decision report.",
        ]
    )
    if report.issues:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def _dict_value(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {} if default is None else default


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""
