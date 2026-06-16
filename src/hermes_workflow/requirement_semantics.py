from __future__ import annotations

import ast
import math
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
import re
from typing import Any

_ALLOWED_OBJECTIVE_FUNCTIONS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "ln": math.log,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "pow": pow,
}

_ALLOWED_OBJECTIVE_NODES = {
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.UAdd,
    ast.USub,
}

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_SPICE_SCALE: dict[str, Decimal] = {
    "": Decimal("1"),
    "f": Decimal("1e-15"),
    "p": Decimal("1e-12"),
    "n": Decimal("1e-9"),
    "u": Decimal("1e-6"),
    "m": Decimal("1e-3"),
    "k": Decimal("1e3"),
    "meg": Decimal("1e6"),
    "g": Decimal("1e9"),
}
_SPICE_VALUE_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<unit>"
    + "|".join(sorted(_SPICE_SCALE, key=len, reverse=True))
    + r")?\s*$",
    re.IGNORECASE,
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

    issues.extend(_validate_objective_expression(objective, declared_metrics))
    issues.extend(_validate_constraints(constraints, declared_metrics))
    issues.extend(_validate_variables(variables, declared_metrics))

    named_metrics = [name for name in metric_names if name]
    if len(named_metrics) != len(set(named_metrics)):
        issues.append("metric names must be unique")

    return issues


def _validate_objective_expression(
    objective: dict[str, Any],
    declared_metrics: set[str],
) -> list[str]:
    expression = objective.get("expression")
    if not isinstance(expression, str):
        return []

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return [f"invalid objective expression: {exc.msg}"]

    issues: list[str] = []
    call_function_node_ids = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    for node in ast.walk(tree):
        if not isinstance(node, tuple(_ALLOWED_OBJECTIVE_NODES)):
            issues.append(f"unsupported objective node {type(node).__name__}")
            return issues

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                issues.append(f"unsupported objective literal {node.value!r}")
            elif not math.isfinite(float(node.value)):
                issues.append("objective numeric literals must be finite")
            continue

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                issues.append("unsupported objective function call")
                continue

            function_name = node.func.id
            if function_name not in _ALLOWED_OBJECTIVE_FUNCTIONS:
                issues.append(f"unsupported objective function {function_name}")
                continue
            if node.keywords:
                issues.append(
                    f"objective function {function_name} does not support keywords"
                )
            continue

        if isinstance(node, ast.Name):
            if id(node) in call_function_node_ids:
                continue
            if node.id in _ALLOWED_OBJECTIVE_FUNCTIONS:
                continue
            if node.id in declared_metrics:
                continue
            suggestion = _metric_suggestion(node.id, declared_metrics)
            if suggestion is None:
                issues.append(f"objective expression references unknown metric {node.id}")
            else:
                issues.append(
                    f"objective expression references unknown metric {node.id}; did you mean {suggestion}?"
                )

    if issues:
        return issues

    metric_values = {
        metric: float(index + 1)
        for index, metric in enumerate(sorted(declared_metrics))
    }

    try:
        result = _safe_eval_objective(tree, metric_values)
    except Exception as exc:  # intentionally broad
        return [str(exc)]

    if not math.isfinite(result):
        return ["objective expression returned non-finite value"]
    return []


def _safe_eval_objective(tree: ast.Expression, metric_values: dict[str, float]) -> float:
    return _eval_ast(tree.body, metric_values)


def _eval_ast(node: ast.AST, metric_values: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_OBJECTIVE_FUNCTIONS:
            raise ValueError(f"objective function {node.id} must be called")
        value = metric_values.get(node.id)
        if value is None:
            raise ValueError(f"objective references unknown metric {node.id}")
        return value

    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand, metric_values)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"unsupported unary operator {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, metric_values)
        right = _eval_ast(node.right, metric_values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise ValueError(f"unsupported binary operator {type(node.op).__name__}")

    if isinstance(node, ast.Call):
        function_name = node.func.id if isinstance(node.func, ast.Name) else None
        if function_name is None:
            raise ValueError("unsupported objective function call")
        handler = _ALLOWED_OBJECTIVE_FUNCTIONS.get(function_name)
        if handler is None:
            raise ValueError(f"unsupported objective function {function_name}")

        args = [_eval_ast(argument, metric_values) for argument in node.args]

        if function_name == "min":
            if len(args) == 0:
                raise ValueError("objective function min expects at least one argument")
            return float(min(args))
        if function_name == "max":
            if len(args) == 0:
                raise ValueError("objective function max expects at least one argument")
            return float(max(args))
        if function_name == "abs":
            if len(args) != 1:
                raise ValueError("objective function abs expects one argument")
            return float(abs(args[0]))
        if function_name == "ln":
            if len(args) != 1:
                raise ValueError("objective function ln expects one argument")
            if args[0] <= 0:
                raise ValueError("objective function ln argument must be positive")
            return float(handler(args[0]))
        if function_name == "log":
            if len(args) != 1:
                raise ValueError("objective function log expects one argument")
            if args[0] <= 0:
                raise ValueError("objective function log argument must be positive")
            return float(handler(args[0]))
        if function_name == "log10":
            if len(args) != 1:
                raise ValueError("objective function log10 expects one argument")
            if args[0] <= 0:
                raise ValueError("objective function log10 argument must be positive")
            return float(handler(args[0]))
        if function_name == "sqrt":
            if len(args) != 1:
                raise ValueError("objective function sqrt expects one argument")
            if args[0] < 0:
                raise ValueError("objective function sqrt argument must be non-negative")
            return float(handler(args[0]))
        if function_name == "exp":
            if len(args) != 1:
                raise ValueError("objective function exp expects one argument")
            return float(handler(args[0]))
        if function_name == "pow":
            if len(args) not in {2, 3}:
                raise ValueError("objective function pow expects two or three arguments")
            return float(handler(*args))

        return float(handler(*args))

    raise ValueError(f"unsupported objective node {type(node).__name__}")


def _validate_constraints(
    constraints: list[Any],
    declared_metrics: set[str],
) -> list[str]:
    issues: list[str] = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        metric_name = constraint.get("metric")
        if not isinstance(metric_name, str) or not metric_name:
            continue
        if metric_name in declared_metrics:
            continue
        suggestion = _metric_suggestion(metric_name, declared_metrics)
        if suggestion is None:
            issues.append(f"constraint references unknown metric {metric_name}")
        else:
            issues.append(
                f"constraint references unknown metric {metric_name}; did you mean {suggestion}?"
            )

    return issues


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

        kind = variable.get("kind")
        if kind == "continuous_step":
            lower_raw = variable.get("lower")
            upper_raw = variable.get("upper")
            step_raw = variable.get("step")
            parsed = (
                _parse_continuous_value(lower_raw),
                _parse_continuous_value(upper_raw),
                _parse_continuous_value(step_raw),
            )
            if any(value is None for value in parsed):
                issues.append(
                    f"variable {name} lower/upper/step must be numeric SPICE values for doctor range checks"
                )
                continue

            lower, upper, step = parsed
            if step <= 0:
                issues.append(f"variable {name} step must be positive")
            if lower > upper:
                issues.append(f"variable {name} lower must be <= upper")

            continue

        if kind == "integer":
            lower_raw = variable.get("lower")
            upper_raw = variable.get("upper")
            step_raw = variable.get("step")
            parsed = (
                _parse_integer_value(lower_raw),
                _parse_integer_value(upper_raw),
                _parse_integer_value(step_raw),
            )
            if any(value is None for value in parsed):
                issues.append(
                    f"variable {name} lower/upper/step must be integer values for doctor range checks"
                )
                continue
            lower, upper, step = parsed
            if step <= 0:
                issues.append(f"variable {name} step must be positive")
            if lower > upper:
                issues.append(f"variable {name} lower must be <= upper")

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


def _parse_continuous_value(raw: Any) -> Decimal | None:
    if not isinstance(raw, str):
        return None
    match = _SPICE_VALUE_RE.match(raw)
    if match is None:
        return None
    value_text = match.group("value")
    unit_text = (match.group("unit") or "").lower()
    if unit_text not in _SPICE_SCALE:
        return None
    try:
        return Decimal(value_text) * _SPICE_SCALE[unit_text]
    except InvalidOperation:
        return None


def _parse_integer_value(raw: Any) -> int | None:
    if not isinstance(raw, str) or not _INTEGER_RE.match(raw):
        return None
    try:
        return int(raw)
    except ValueError:
        return None
