from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
import re
from typing import Any

from hermes_workflow.objective_contract import objective_expression_issues

_CONSTRAINT_THRESHOLD_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s+(?P<unit>\S(?:.*\S)?)\s*$"
)


def validate_requirement_semantics(sections: dict[str, Any]) -> list[str]:
    """Run deterministic semantic checks over requirement sections."""
    issues: list[str] = []

    constraints = _as_list(sections.get("Constraints"))
    variables = _as_list(sections.get("Design Variables"))
    metrics = _as_list(sections.get("Metrics"))
    objective = _as_dict(sections.get("Objective"))

    metric_names = [_metric_name(metric) for metric in metrics]
    declared_metrics = {metric for metric in metric_names if metric}
    metric_units = {
        name: str(metric.get("unit"))
        for metric, name in zip(metrics, metric_names, strict=True)
        if isinstance(metric, dict)
        and name is not None
        and isinstance(metric.get("unit"), str)
    }

    expression = objective.get("expression")
    if isinstance(expression, str):
        issues.extend(objective_expression_issues(expression, declared_metrics))
    issues.extend(_validate_constraints(constraints, metric_units))
    issues.extend(_validate_variables(variables, declared_metrics))

    named_metrics = [name for name in metric_names if name]
    if len(named_metrics) != len(set(named_metrics)):
        issues.append("metric names must be unique")

    return issues


def _validate_constraints(
    constraints: list[Any],
    metric_units: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        metric_name = constraint.get("metric")
        if not isinstance(metric_name, str) or not metric_name:
            continue
        if metric_name not in metric_units:
            suggestion = _metric_suggestion(metric_name, set(metric_units))
            if suggestion is None:
                issues.append(f"constraint references unknown metric {metric_name}")
            else:
                issues.append(
                    f"constraint references unknown metric {metric_name}; did you mean {suggestion}?"
                )
            continue
        raw_value = constraint.get("value")
        if not isinstance(raw_value, str):
            continue
        try:
            parse_constraint_threshold(raw_value, metric_units[metric_name])
        except ValueError as exc:
            issues.append(f"constraint {metric_name} {exc}")

    return issues


def parse_constraint_threshold(raw: str, expected_unit: str) -> float:
    """Parse a finite threshold and require its declared metric unit exactly."""
    match = _CONSTRAINT_THRESHOLD_RE.match(raw)
    if match is None:
        raise ValueError(
            "value must be a finite numeric threshold followed by "
            f"unit {expected_unit!r}"
        )
    unit = match.group("unit")
    if unit != expected_unit:
        raise ValueError(
            f"unit {unit!r} does not match metric unit {expected_unit!r}"
        )
    try:
        value = float(Decimal(match.group("value")))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(
            "value must be a finite numeric threshold followed by "
            f"unit {expected_unit!r}"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            "value must be a finite numeric threshold followed by "
            f"unit {expected_unit!r}"
        )
    return value


def _validate_variables(
    variables: list[Any],
    metric_names: set[str],
) -> list[str]:
    issues: list[str] = []
    names: list[str] = []

    for variable in variables:
        if not isinstance(variable, dict):
            continue

        name = variable.get("name")
        if not isinstance(name, str) or not name:
            continue
        names.append(name)

        if name in metric_names:
            issues.append(f"design variable {name} collides with metric name {name}")

    if len(names) != len(set(names)):
        issues.append("variable names must be unique")

    return issues


def _metric_suggestion(value: str, declared_metrics: set[str]) -> str | None:
    normalized_known = sorted((_normalize(metric), metric) for metric in declared_metrics)
    matches = get_close_matches(
        _normalize(value),
        [metric for metric, _ in normalized_known],
        n=1,
        cutoff=0.75,
    )
    if not matches:
        return None
    match = matches[0]
    for normalized_name, declared in normalized_known:
        if normalized_name == match:
            return declared
    return None


def _normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric_name(metric: dict[str, Any]) -> str:
    if not isinstance(metric, dict):
        return ""
    value = metric.get("name")
    return value if isinstance(value, str) else ""
