from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts


REPORT_RELATIVE = Path("reports/optimizer_completion_report.json")
ACCEPTANCE_REPORT_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")


@dataclass(frozen=True)
class OptimizerCompletionReport:
    status: str
    decision: str
    confidence: str
    global_optimum_claim: bool
    best_observed: dict[str, Any] | None
    evaluation_count: int
    status_counts: dict[str, int]
    search_space: dict[str, Any]
    improvement: dict[str, Any]
    continuation: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    report_path: Path | None = None


def summarize_optimizer_run(
    project_dir: str | Path,
    *,
    expected_backend: str | None = None,
) -> OptimizerCompletionReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []

    acceptance_report = _load_json(project_root / ACCEPTANCE_REPORT_RELATIVE, issues)
    artifacts = load_optimizer_artifacts(
        project_root,
        issues,
        expected_backend=expected_backend,
    )
    native_report = artifacts.report
    traces = artifacts.traces

    if acceptance_report.get("status") != "accepted":
        issues.append("optimizer acceptance report status is not accepted")

    evaluation_count = _int_value(native_report.get("evaluation_count")) or len(traces)
    status_counts = dict(Counter(_string_value(row.get("status")) for row in traces))
    best_observed = (
        _dict_value(acceptance_report.get("best_candidate"))
        if acceptance_report.get("status") == "accepted"
        else None
    )
    valid_unique_coverage_count = _count_valid_unique_candidates(traces)

    search_space = _summarize_search_space(
        project_root=project_root,
        valid_unique_coverage_count=valid_unique_coverage_count,
        warnings=warnings,
    )
    improvement = _summarize_improvement(traces, evaluation_count=evaluation_count)
    decision, confidence, global_optimum_claim, reasons = _decide_completion(
        issues=issues,
        status_counts=status_counts,
        valid_unique_coverage_count=valid_unique_coverage_count,
        search_space=search_space,
        improvement=improvement,
    )
    continuation = _summarize_continuation(
        decision=decision,
        status_counts=status_counts,
        evaluation_count=evaluation_count,
        valid_unique_coverage_count=valid_unique_coverage_count,
        search_space=search_space,
        improvement=improvement,
    )

    report_path = project_root / REPORT_RELATIVE
    report = OptimizerCompletionReport(
        status="fail" if issues else "pass",
        decision=decision,
        confidence=confidence,
        global_optimum_claim=global_optimum_claim,
        best_observed=best_observed,
        evaluation_count=evaluation_count,
        status_counts=status_counts,
        search_space=search_space,
        improvement=improvement,
        continuation=continuation,
        reasons=reasons,
        warnings=warnings,
        issues=issues,
        report_path=report_path,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _load_json(path: Path, issues: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(f"missing file: {path}")
        return {}
    except json.JSONDecodeError as exc:
        issues.append(f"invalid JSON: {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"JSON file must contain an object: {path}")
        return {}
    return payload


_VALID_COVERAGE_STATUSES = {"feasible", "constraint_failed"}


def _count_valid_unique_candidates(traces: list[dict[str, Any]]) -> int:
    """Count credibly evaluated, unique parameter combinations.

    A trace counts toward search-space coverage only if its status is
    feasible or constraint_failed and its parameters are a non-empty dict.
    Traces with identical parameters count once. Skipped duplicates and
    simulation/metric/record failures never represent an independently
    evaluated combination, so they are excluded.
    """
    seen: set[str] = set()
    for row in traces:
        if _string_value(row.get("status")) not in _VALID_COVERAGE_STATUSES:
            continue
        parameters = row.get("parameters")
        if not isinstance(parameters, dict) or not parameters:
            continue
        seen.add(json.dumps(parameters, sort_keys=True, default=str))
    return len(seen)


def _summarize_search_space(
    *,
    project_root: Path,
    valid_unique_coverage_count: int,
    warnings: list[str],
) -> dict[str, Any]:
    estimate = _estimate_discrete_search_space(
        project_root / "config" / "variables.yaml",
        warnings,
    )
    evaluated_fraction = (
        min(1.0, valid_unique_coverage_count / estimate)
        if estimate and estimate > 0
        else None
    )
    return {
        "estimated_discrete_combinations": estimate,
        "evaluated_fraction": evaluated_fraction,
        "exhaustive_trace": (
            estimate is not None and estimate == valid_unique_coverage_count
        ),
    }


def _estimate_discrete_search_space(path: Path, warnings: list[str]) -> int | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(f"missing search-space file: {path}")
        return None
    except yaml.YAMLError as exc:
        warnings.append(f"invalid variables YAML: {path}: {exc}")
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("variables"), list):
        warnings.append(f"variables YAML must contain variables list: {path}")
        return None

    total = 1
    for variable in payload["variables"]:
        if not isinstance(variable, dict):
            return None
        count = _estimate_variable_grid_count(variable)
        if count is None:
            return None
        total *= count
    return total


def _estimate_variable_grid_count(variable: dict[str, Any]) -> int | None:
    kind = _string_value(variable.get("kind"))
    lower, lower_unit = _parse_decimal_unit(_string_value(variable.get("lower")))
    upper, upper_unit = _parse_decimal_unit(_string_value(variable.get("upper")))
    step, step_unit = _parse_decimal_unit(_string_value(variable.get("step")))
    if lower is None or upper is None or step is None:
        return None
    if lower_unit != upper_unit or lower_unit != step_unit:
        return None
    if step <= 0 or upper < lower:
        return None

    span = upper - lower
    if kind == "integer" and lower_unit == "":
        if lower != lower.to_integral_value() or upper != upper.to_integral_value():
            return None
        if step != step.to_integral_value():
            return None

    if kind not in {"integer", "continuous_step"}:
        return None

    quotient = span / step
    if quotient != quotient.to_integral_value():
        return None
    return int(quotient) + 1


def _parse_decimal_unit(value: str) -> tuple[Decimal | None, str]:
    if not value:
        return None, ""
    index = 0
    while index < len(value) and (
        value[index].isdigit() or value[index] in {"+", "-", "."}
    ):
        index += 1
    try:
        number = Decimal(value[:index])
    except (InvalidOperation, ValueError):
        return None, ""
    return number, value[index:]


def _summarize_improvement(
    traces: list[dict[str, Any]],
    *,
    evaluation_count: int,
) -> dict[str, Any]:
    objectives = [
        objective
        for row in traces
        if (objective := _float_value(row.get("objective"))) is not None
    ]
    if not objectives:
        return {
            "best_objective_start": None,
            "best_objective_end": None,
            "recent_best_improved": False,
            "recent_window": 0,
        }

    best_so_far: list[float] = []
    best = objectives[0]
    for objective in objectives:
        best = min(best, objective)
        best_so_far.append(best)

    recent_window = min(20, max(5, evaluation_count // 5))
    recent_window = min(recent_window, len(best_so_far))
    previous_best = (
        min(best_so_far[:-recent_window])
        if recent_window < len(best_so_far)
        else best_so_far[0]
    )
    recent_best = min(best_so_far[-recent_window:])
    return {
        "best_objective_start": best_so_far[0],
        "best_objective_end": best_so_far[-1],
        "recent_best_improved": recent_best < previous_best,
        "recent_window": recent_window,
    }


def _decide_completion(
    *,
    issues: list[str],
    status_counts: dict[str, int],
    valid_unique_coverage_count: int,
    search_space: dict[str, Any],
    improvement: dict[str, Any],
) -> tuple[str, str, bool, list[str]]:
    if issues:
        return (
            "stop_for_user_review",
            "low",
            False,
            ["optimizer completion report cannot trust rejected artifacts"],
        )

    if status_counts.get("feasible", 0) == 0:
        return (
            "stop_for_user_review",
            "low",
            False,
            ["no feasible candidate observed in accepted optimizer run"],
        )

    estimated = _int_or_none(search_space.get("estimated_discrete_combinations"))
    if estimated is not None and estimated == valid_unique_coverage_count:
        return (
            "accept_best_observed",
            "high",
            True,
            ["evaluated trace covers the full finite search space"],
        )

    if estimated is not None and estimated <= valid_unique_coverage_count * 3:
        return (
            "switch_to_exhaustive_sweep",
            "medium",
            False,
            ["finite search space is small enough to finish by exhaustive sweep"],
        )

    if improvement.get("recent_best_improved") is True:
        return (
            "continue_more_evals",
            "medium",
            False,
            ["best objective improved inside the recent window"],
        )

    return (
        "accept_best_observed",
        "medium",
        False,
        ["accepted best observed candidate; no recent improvement detected"],
    )


def _summarize_continuation(
    *,
    decision: str,
    status_counts: dict[str, int],
    evaluation_count: int,
    valid_unique_coverage_count: int,
    search_space: dict[str, Any],
    improvement: dict[str, Any],
) -> dict[str, Any]:
    feasible_count = status_counts.get("feasible", 0)
    feasible_ratio = feasible_count / evaluation_count if evaluation_count else 0.0
    recent_best_improved = improvement.get("recent_best_improved") is True
    recommended = decision == "continue_more_evals"
    estimated = _int_or_none(search_space.get("estimated_discrete_combinations"))
    remaining = (
        max(0, estimated - valid_unique_coverage_count)
        if estimated is not None
        else None
    )
    suggested = _suggest_additional_evals(
        recommended=recommended,
        remaining=remaining,
        recent_window=_int_or_none(improvement.get("recent_window")) or 0,
    )
    return {
        "recommended": recommended,
        "suggested_additional_evals": suggested,
        "recent_window": _int_or_none(improvement.get("recent_window")) or 0,
        "recent_best_improved": recent_best_improved,
        "plateau_detected": feasible_count > 0 and not recent_best_improved,
        "feasible_count": feasible_count,
        "feasible_ratio": feasible_ratio,
        "low_feasible_ratio": 0 < feasible_ratio < 0.1,
        "estimated_remaining_combinations": remaining,
        "reason": _continuation_reason(
            recommended=recommended,
            recent_best_improved=recent_best_improved,
            feasible_count=feasible_count,
        ),
    }


def _suggest_additional_evals(
    *,
    recommended: bool,
    remaining: int | None,
    recent_window: int,
) -> int:
    if not recommended:
        return 0
    suggestion = max(20, recent_window)
    if remaining is not None:
        return min(suggestion, remaining)
    return suggestion


def _continuation_reason(
    *,
    recommended: bool,
    recent_best_improved: bool,
    feasible_count: int,
) -> str:
    if feasible_count == 0:
        return "no feasible candidate observed; user review is required"
    if recommended and recent_best_improved:
        return "recent window improved; continue with another bounded batch"
    return "no recent best improvement; accept best observed unless user wants more exploration"


def _dict_value(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _float_value(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    number = float(value)
    return number if isfinite(number) else None
