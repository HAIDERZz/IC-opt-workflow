from __future__ import annotations

import math
from typing import Any

import numpy as np
from openbox.utils.multi_objective import get_pareto_front

_MODE = "report_layer_raw_metric_tradeoff"
_SOURCE = "existing_optimizer_raw_metrics"
_UTILITY = "openbox.utils.multi_objective.get_pareto_front"
_DIRECTION_UNAVAILABLE_REASON = "fewer than two trade-off metrics have inferred directions"
_ROWS_UNAVAILABLE_REASON = "fewer than two eligible rows contain all trade-off metrics"


def build_pareto_tradeoff_summary(
    traces: list[dict[str, Any]],
    metric_contract: dict[str, Any],
) -> dict[str, Any]:
    metric_directions = _infer_metric_directions(metric_contract)
    observed_metrics = _observed_metrics(traces)
    unscored_metrics = [
        metric for metric in observed_metrics if metric not in metric_directions
    ]
    if len(metric_directions) < 2:
        return {
            "status": "not_available",
            "mode": _MODE,
            "optimizer_mode_changed": False,
            "reason": _DIRECTION_UNAVAILABLE_REASON,
            "metric_directions": metric_directions,
            "unscored_metrics": unscored_metrics,
        }

    metric_names = sorted(metric_directions)
    eligible_rows = [
        normalized
        for row in traces
        if (normalized := _tradeoff_row(row, metric_names, metric_directions))
        is not None
    ]
    if len(eligible_rows) < 2:
        return {
            "status": "not_available",
            "mode": _MODE,
            "optimizer_mode_changed": False,
            "reason": _ROWS_UNAVAILABLE_REASON,
            "metric_directions": metric_directions,
            "unscored_metrics": unscored_metrics,
            "eligible_count": len(eligible_rows),
        }

    cost_matrix = np.array([row["_costs"] for row in eligible_rows], dtype=float)
    front_indices = get_pareto_front(
        cost_matrix, return_index=True, lexsort=True
    )
    front_candidates = [
        _public_tradeoff_row(eligible_rows[int(index)]) for index in front_indices
    ]
    return {
        "status": "available",
        "mode": _MODE,
        "optimizer_mode_changed": False,
        "source": _SOURCE,
        "openbox_utility": _UTILITY,
        "metric_directions": metric_directions,
        "unscored_metrics": unscored_metrics,
        "eligible_count": len(eligible_rows),
        "front_count": len(front_candidates),
        "dominated_count": len(eligible_rows) - len(front_candidates),
        "front_candidates": front_candidates,
    }


def _infer_metric_directions(metric_contract: dict[str, Any]) -> dict[str, str]:
    directions: dict[str, str] = {}
    constraints = metric_contract.get("constraints")
    if not isinstance(constraints, list):
        return directions
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        metric = constraint.get("metric")
        op = constraint.get("op")
        if not isinstance(metric, str) or not metric:
            continue
        if op in {"lt", "le"}:
            directions[metric] = "minimize"
        elif op in {"gt", "ge"}:
            directions[metric] = "maximize"
    return directions


def _observed_metrics(traces: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(metric)
            for row in traces
            if isinstance(row.get("metrics"), dict)
            for metric in row["metrics"]
        }
    )


def _tradeoff_row(
    row: dict[str, Any],
    metric_names: list[str],
    metric_directions: dict[str, str],
) -> dict[str, Any] | None:
    metrics = row.get("metrics")
    parameters = row.get("parameters")
    if not isinstance(metrics, dict) or not isinstance(parameters, dict):
        return None
    costs: list[float] = []
    raw_metrics: dict[str, float] = {}
    for metric in metric_names:
        value = _finite_float(metrics.get(metric))
        if value is None:
            return None
        raw_metrics[metric] = value
        costs.append(value if metric_directions[metric] == "minimize" else -value)
    status = row.get("status") if isinstance(row.get("status"), str) else "unknown"
    return {
        "evaluation_index": row.get("evaluation_index"),
        "run_id": row.get("run_id"),
        "status": status,
        "parameters": dict(parameters),
        "metrics": raw_metrics,
        "objective": _finite_float(row.get("objective")),
        "constraint_penalty": _finite_float(row.get("constraint_penalty")),
        "_costs": costs,
    }


def _public_tradeoff_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None
