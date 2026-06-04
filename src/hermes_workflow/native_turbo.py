from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from hermes_workflow.schemas import (
    ConstraintOp,
    MetricsConfig,
    ObjectiveDirection,
    OptimizerConfig,
    VariableKind,
    VariablesConfig,
)
from hermes_workflow.validate import (
    CONTINUOUS_RE,
    ContractBundle,
    assert_valid_project,
    evaluate_objective,
)


@dataclass(frozen=True)
class NativeTurboContract:
    variables: VariablesConfig
    metrics: MetricsConfig
    optimizer: OptimizerConfig


@dataclass(frozen=True)
class ObjectiveEvaluation:
    status: str
    objective: float
    fom: float | None
    constraints_passed: bool
    constraint_penalty: float
    issues: list[str]


@dataclass(frozen=True)
class NativeTurboEvaluationTrace:
    evaluation_index: int
    run_id: str
    selection_phase: str
    raw_x: list[float]
    parameters: dict[str, str]
    status: str
    objective: float
    fom: float | None
    constraint_penalty: float
    issues: list[str]


def load_native_turbo_contract(project_dir: Path) -> NativeTurboContract:
    bundle: ContractBundle = assert_valid_project(Path(project_dir))
    return NativeTurboContract(
        variables=bundle.variables,
        metrics=bundle.metrics,
        optimizer=bundle.optimizer,
    )


def quantize_candidate(
    variables_config: VariablesConfig,
    raw_values: Sequence[float],
) -> dict[str, str]:
    variables = variables_config.variables
    if len(raw_values) != len(variables):
        raise ValueError(
            f"expected {len(variables)} raw values, got {len(raw_values)}"
        )

    parameters: dict[str, str] = {}
    for variable, raw in zip(variables, raw_values, strict=True):
        if variable.kind == VariableKind.INTEGER:
            lower = int(variable.lower)
            upper = int(variable.upper)
            step = int(variable.step)
            offset = round((float(raw) - lower) / step)
            value = _clamp_int(lower + offset * step, lower, upper)
            parameters[variable.name] = str(value)
        else:
            lower, unit = _parse_decimal_unit(variable.lower)
            upper, upper_unit = _parse_decimal_unit(variable.upper)
            step, step_unit = _parse_decimal_unit(variable.step)
            if upper_unit != unit or step_unit != unit:
                raise ValueError(f"variable {variable.name} uses inconsistent units")
            offset = round((Decimal(str(raw)) - lower) / step)
            value = lower + Decimal(offset) * step
            value = max(lower, min(upper, value))
            parameters[variable.name] = f"{value.normalize():f}{unit}"
    return parameters


def evaluate_candidate_objective(
    metrics_config: MetricsConfig,
    optimizer_config: OptimizerConfig,
    metrics: dict[str, float],
) -> ObjectiveEvaluation:
    failure_penalty = optimizer_config.optimizer.failure_penalty
    metric_issues = _metric_issues(metrics_config, metrics)
    if metric_issues:
        return ObjectiveEvaluation(
            status="metric_failed",
            objective=failure_penalty,
            fom=None,
            constraints_passed=False,
            constraint_penalty=0.0,
            issues=metric_issues,
        )

    fom = evaluate_objective(metrics_config.objective.expression, metrics)
    if not math.isfinite(fom):
        return ObjectiveEvaluation(
            status="metric_failed",
            objective=failure_penalty,
            fom=None,
            constraints_passed=False,
            constraint_penalty=0.0,
            issues=["objective non_finite"],
        )

    constraint_penalty, constraint_issues = _constraint_penalty(metrics_config, metrics)
    if constraint_issues:
        return ObjectiveEvaluation(
            status="constraint_failed",
            objective=failure_penalty + constraint_penalty,
            fom=fom,
            constraints_passed=False,
            constraint_penalty=constraint_penalty,
            issues=constraint_issues,
        )

    objective = (
        -fom
        if metrics_config.objective.direction == ObjectiveDirection.MAXIMIZE
        else fom
    )
    return ObjectiveEvaluation(
        status="feasible",
        objective=objective,
        fom=fom,
        constraints_passed=True,
        constraint_penalty=0.0,
        issues=[],
    )


def _metric_issues(
    metrics_config: MetricsConfig,
    metrics: dict[str, float],
) -> list[str]:
    issues: list[str] = []
    for metric in metrics_config.metrics:
        value = metrics.get(metric.name)
        if value is None:
            issues.append(f"metric {metric.name} missing")
        elif not math.isfinite(float(value)):
            issues.append(f"metric {metric.name} non_finite")
    return issues


def _constraint_penalty(
    metrics_config: MetricsConfig,
    metrics: dict[str, float],
) -> tuple[float, list[str]]:
    penalty = 0.0
    issues: list[str] = []
    for constraint in metrics_config.constraints:
        metric_value = float(metrics[constraint.metric])
        threshold = _parse_constraint_value(constraint.value)
        if threshold is None:
            issues.append(f"constraint {constraint.metric} value unparseable")
            penalty += 1.0
            continue
        violation = _normalized_violation(metric_value, constraint.op, threshold)
        if violation > 0:
            penalty += violation * violation
            issues.append(
                "constraint "
                f"{constraint.metric} {constraint.op.value} {constraint.value} "
                f"violated by {metric_value}"
            )
    return penalty, issues


def _normalized_violation(value: float, op: ConstraintOp, threshold: float) -> float:
    scale = abs(threshold) if threshold != 0 else 1.0
    if op == ConstraintOp.LT and value >= threshold:
        return (value - threshold) / scale
    if op == ConstraintOp.LE and value > threshold:
        return (value - threshold) / scale
    if op == ConstraintOp.GT and value <= threshold:
        return (threshold - value) / scale
    if op == ConstraintOp.GE and value < threshold:
        return (threshold - value) / scale
    return 0.0


def _parse_constraint_value(raw: str) -> float | None:
    try:
        parsed = _parse_decimal_unit(raw)
        value, _unit = parsed
        return float(value)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_decimal_unit(raw: str) -> tuple[Decimal, str]:
    match = CONTINUOUS_RE.match(str(raw))
    if match is None:
        raise ValueError(f"cannot parse decimal value {raw!r}")
    return Decimal(match.group("value")), match.group("unit") or ""


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))
