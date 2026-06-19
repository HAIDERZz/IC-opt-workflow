from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

_MODE = "scripted_factual_summary"
_BOUNDARY = "facts_and_rule_based_notes_only"
_HISTORY_INTERPRETATION = (
    "History evidence was applied; repeated current points are exact parameter "
    "matches, not proof of optimizer improvement."
)


def build_tradeoff_interpretation_summary(
    *,
    traces: list[dict[str, Any]],
    metric_contract: dict[str, Any],
    pareto_summary: dict[str, Any],
) -> dict[str, Any]:
    metric_directions = _dict(pareto_summary.get("metric_directions"))
    eligible_count = _int(pareto_summary.get("eligible_count"))
    front_count = _int(pareto_summary.get("front_count"))
    ratio = front_count / eligible_count if eligible_count else 0.0
    if pareto_summary.get("status") == "not_available":
        reason = str(pareto_summary.get("reason") or "trade-off analysis is not available")
        return {
            "status": "not_available",
            "mode": _MODE,
            "confidence_boundary": _BOUNDARY,
            "reason": reason,
            "front_selectivity": {
                "eligible_count": eligible_count,
                "front_count": front_count,
                "ratio": ratio,
                "usefulness": "not_available",
                "message": f"Report-layer trade-off analysis is not available: {reason}.",
            },
            "constraint_blockers": [],
            "feasible_candidates": [],
            "metric_extremes": [],
        }
    usefulness = "low" if eligible_count and ratio >= 0.8 else "useful"
    constraints = _constraints_by_metric(metric_contract)
    return {
        "status": "available",
        "mode": _MODE,
        "confidence_boundary": _BOUNDARY,
        "front_selectivity": {
            "eligible_count": eligible_count,
            "front_count": front_count,
            "ratio": ratio,
            "usefulness": usefulness,
            "message": _front_selectivity_message(usefulness),
        },
        "constraint_blockers": _constraint_blockers(traces, constraints),
        "feasible_candidates": _feasible_candidates(traces, metric_directions),
        "metric_extremes": _metric_extremes(traces, metric_directions, constraints),
    }


def build_history_reuse_summary(
    project_root: Path,
    traces: list[dict[str, Any]],
    history_summary: dict[str, Any],
) -> dict[str, Any]:
    if not history_summary or history_summary.get("status") == "not_available":
        return {
            "status": "not_available",
            "reason": "history warm-start summary is not available",
        }
    audit = _load_history_audit(project_root)
    accepted_observations = [
        item
        for item in _list(audit.get("accepted_observations"))
        if isinstance(item, dict) and isinstance(item.get("parameters"), dict)
    ]
    accepted_keys = {
        _stable_parameters_key(_dict(item.get("parameters")))
        for item in accepted_observations
    }
    repeated = [
        row
        for row in traces
        if isinstance(row.get("parameters"), dict)
        and _stable_parameters_key(_dict(row.get("parameters"))) in accepted_keys
    ]
    finite_rows = [row for row in traces if _finite_float(row.get("objective")) is not None]
    best = min(
        finite_rows,
        key=lambda row: _finite_float(row.get("objective")) or math.inf,
    ) if finite_rows else None
    best_reused = (
        isinstance(best, dict)
        and isinstance(best.get("parameters"), dict)
        and _stable_parameters_key(_dict(best.get("parameters"))) in accepted_keys
    )
    return {
        "status": "available",
        "application_mode": history_summary.get("application_mode"),
        "accepted_observation_count": history_summary.get("accepted_observation_count"),
        "rejected_observation_count": audit.get("rejected_observation_count"),
        "applied_observation_count": history_summary.get("applied_observation_count"),
        "applied_to_advisor": history_summary.get("applied_to_advisor"),
        "source_paths": sorted(
            {
                str(item.get("source_path"))
                for item in accepted_observations
                if item.get("source_path") is not None
            }
        ),
        "repeated_current_point_count": len(repeated),
        "repeated_current_status_counts": dict(
            Counter(str(row.get("status") or "unknown") for row in repeated)
        ),
        "best_candidate_reused_history": bool(best_reused),
        "interpretation": _HISTORY_INTERPRETATION,
    }


def _front_selectivity_message(usefulness: str) -> str:
    if usefulness == "low":
        return (
            "The raw-metric Pareto front is broad and is not a useful ranking by itself. "
            "Use feasible candidates and constraint blockers for decision support."
        )
    return "The raw-metric Pareto front has useful filtering power."


def _constraint_blockers(
    traces: list[dict[str, Any]],
    constraints: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in traces:
        metrics = _dict(row.get("metrics"))
        if not metrics:
            continue
        for metric, constraint in constraints.items():
            value = _finite_float(metrics.get(metric))
            if value is None:
                continue
            if not _passes_constraint(value, constraint):
                counts[metric] += 1
    return [
        {"metric": metric, "failed_count": count}
        for metric, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0].lower())
        )
    ]


def _feasible_candidates(
    traces: list[dict[str, Any]],
    metric_directions: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in traces
        if row.get("status") == "feasible"
        and _finite_float(row.get("objective")) is not None
    ]
    rows.sort(key=lambda row: _finite_float(row.get("objective")) or math.inf)
    metric_names = sorted(metric_directions)
    return [
        {
            "run_id": row.get("run_id"),
            "objective": _finite_float(row.get("objective")),
            "parameters": _dict(row.get("parameters")),
            "metrics": {
                metric: _dict(row.get("metrics")).get(metric)
                for metric in metric_names
                if metric in _dict(row.get("metrics"))
            },
        }
        for row in rows[:10]
    ]


def _metric_extremes(
    traces: list[dict[str, Any]],
    metric_directions: dict[str, Any],
    constraints: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    extremes: list[dict[str, Any]] = []
    for metric, direction in sorted(metric_directions.items()):
        candidates = [
            row
            for row in traces
            if _finite_float(_dict(row.get("metrics")).get(metric)) is not None
        ]
        if not candidates:
            continue
        reverse = direction == "maximize"
        row = sorted(
            candidates,
            key=lambda item: _finite_float(_dict(item.get("metrics")).get(metric)) or 0.0,
            reverse=reverse,
        )[0]
        metrics = _dict(row.get("metrics"))
        extremes.append(
            {
                "metric": metric,
                "direction": direction,
                "run_id": row.get("run_id"),
                "status": row.get("status"),
                "value": _finite_float(metrics.get(metric)),
                "parameters": _dict(row.get("parameters")),
                "failed_constraints": _failed_constraint_metrics(metrics, constraints),
            }
        )
    return extremes


def _constraints_by_metric(metric_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    constraints: dict[str, dict[str, Any]] = {}
    for constraint in _list(metric_contract.get("constraints")):
        if not isinstance(constraint, dict):
            continue
        metric = constraint.get("metric")
        op = constraint.get("op")
        if not isinstance(metric, str) or op not in {"gt", "ge", "lt", "le"}:
            continue
        limit = _constraint_limit(constraint)
        if limit is None:
            continue
        constraints[metric] = {"op": op, "limit": limit}
    return constraints


def _constraint_limit(constraint: dict[str, Any]) -> float | None:
    value = constraint.get("limit", constraint.get("value"))
    if isinstance(value, dict):
        value = value.get("value")
    return _parse_numeric_prefix(value)


def _passes_constraint(value: float, constraint: dict[str, Any]) -> bool:
    limit = _finite_float(constraint.get("limit"))
    op = constraint.get("op")
    if limit is None:
        return True
    if op == "gt":
        return value > limit
    if op == "ge":
        return value >= limit
    if op == "lt":
        return value < limit
    if op == "le":
        return value <= limit
    return True


def _failed_constraint_metrics(
    metrics: dict[str, Any], constraints: dict[str, dict[str, Any]]
) -> list[str]:
    failed: list[str] = []
    for metric, constraint in sorted(constraints.items()):
        value = _finite_float(metrics.get(metric))
        if value is not None and not _passes_constraint(value, constraint):
            failed.append(metric)
    return failed


def _load_history_audit(project_root: Path) -> dict[str, Any]:
    path = project_root / "reports" / "history_warm_start_audit.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stable_parameters_key(parameters: dict[str, Any]) -> str:
    return json.dumps(parameters, sort_keys=True, separators=(",", ":"))


def _parse_numeric_prefix(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return _finite_float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    token = text.split()[0]
    try:
        result = float(token)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0
