"""Single objective-expression contract shared by intake and runtime."""

from __future__ import annotations

import ast
import math
from difflib import get_close_matches


_ALLOWED_NODES = (
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
    ast.Mod,
    ast.UAdd,
    ast.USub,
)
_ALLOWED_FUNCTIONS = frozenset({"min", "max", "ln"})


def objective_expression_issues(
    expression: str,
    declared_metrics: set[str],
) -> list[str]:
    """Statically validate an objective without inventing metric values."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return [f"invalid objective expression: {exc.msg}"]

    issues: list[str] = []
    called_name_ids = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return [f"unsupported objective expression node {type(node).__name__}"]

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                issues.append("unsupported objective function call")
                continue
            name = node.func.id
            if name not in _ALLOWED_FUNCTIONS:
                issues.append(f"unsupported objective function {name}")
                continue
            if node.keywords:
                issues.append("objective function keyword arguments are unsupported")
            if name in {"min", "max"} and not node.args:
                issues.append(
                    f"objective function {name} expects at least one argument"
                )
            if name == "ln" and len(node.args) != 1:
                issues.append("objective function ln expects one argument")
            continue

        if isinstance(node, ast.Name):
            if id(node) in called_name_ids:
                continue
            if node.id in _ALLOWED_FUNCTIONS:
                issues.append(f"objective function {node.id} must be called")
                continue
            if node.id not in declared_metrics:
                suggestion = _metric_suggestion(node.id, declared_metrics)
                message = f"objective references unknown metric {node.id}"
                if suggestion is not None:
                    message += f"; did you mean {suggestion}?"
                issues.append(message)
            continue

        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, int | float):
                issues.append(f"unsupported objective literal {value!r}")
            else:
                try:
                    literal_is_finite = math.isfinite(float(value))
                except (OverflowError, TypeError, ValueError):
                    literal_is_finite = False
                if not literal_is_finite:
                    issues.append("objective numeric literals must be finite")

    if not issues and not any(
        isinstance(node, ast.Name) and id(node) not in called_name_ids
        for node in ast.walk(tree)
    ):
        try:
            value = float(_evaluate_node(tree.body, {}))
            if not math.isfinite(value):
                raise ValueError("objective expression returned non-finite value")
        except (ArithmeticError, TypeError, ValueError) as exc:
            issues.append(f"objective constant expression is invalid: {exc}")

    return issues


def evaluate_objective_expression(
    expression: str,
    metrics: dict[str, float],
) -> float:
    """Evaluate an objective that follows :func:`objective_expression_issues`."""
    issues = objective_expression_issues(expression, set(metrics))
    if issues:
        raise ValueError(issues[0])
    tree = ast.parse(expression, mode="eval")
    try:
        value = float(_evaluate_node(tree.body, metrics))
        if not math.isfinite(value):
            raise ValueError("objective expression returned non-finite value")
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"objective expression evaluation failed: {exc}") from exc
    return value


def _evaluate_node(node: ast.AST, metrics: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return float(metrics[node.id])
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_node(node.operand, metrics)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left, metrics)
        right = _evaluate_node(node.right, metrics)
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
        if isinstance(node.op, ast.Mod):
            return left % right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_evaluate_node(arg, metrics) for arg in node.args]
        if node.func.id == "min":
            return float(min(args))
        if node.func.id == "max":
            return float(max(args))
        if node.func.id == "ln":
            if args[0] <= 0:
                raise ValueError("objective function ln argument must be positive")
            return float(math.log(args[0]))
    raise ValueError(f"unsupported objective expression node {type(node).__name__}")


def _metric_suggestion(value: str, declared_metrics: set[str]) -> str | None:
    normalized = {_normalize(metric): metric for metric in declared_metrics}
    matches = get_close_matches(
        _normalize(value),
        sorted(normalized),
        n=1,
        cutoff=0.75,
    )
    return normalized[matches[0]] if matches else None


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())
