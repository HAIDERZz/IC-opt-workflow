"""Scientific binding for optimizer traces and their authoritative manifests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from hermes_workflow.native_turbo import (
    DUPLICATE_SKIPPED,
    WORKFLOW_FAILURE_STATUSES,
    evaluate_candidate_objective,
)
from hermes_workflow.schemas import MetricsConfig, OptimizerConfig


SCIENTIFIC_STATUSES = {
    "feasible",
    "constraint_failed",
    "metric_failed",
    "metric_check_failed",
    "real_check_failed",
    DUPLICATE_SKIPPED,
    *WORKFLOW_FAILURE_STATUSES,
}


@dataclass(frozen=True)
class TraceScienceValidation:
    verified_row: dict[str, Any] | None
    issues: list[str]


def validate_trace_science(
    trace: dict[str, Any],
    *,
    result_manifest: dict[str, Any],
    metric_manifest: dict[str, Any] | None,
    metrics_config: MetricsConfig,
    optimizer_config: OptimizerConfig,
) -> TraceScienceValidation:
    """Bind one trace's scientific fields to loaded parent evidence and config."""

    run_id = trace.get("run_id")
    label = run_id if isinstance(run_id, str) and run_id else "trace row"
    issues: list[str] = []
    trace_status = trace.get("status")
    if trace_status not in SCIENTIFIC_STATUSES:
        issues.append(f"{label} trace status is unknown: {trace_status!r}")

    failure_penalty = optimizer_config.optimizer.failure_penalty
    if trace_status == DUPLICATE_SKIPPED:
        issues.extend(
            duplicate_skipped_trace_issues(
                trace,
                failure_penalty=failure_penalty,
                label=label,
            )
        )
        verified = _with_science(
            trace,
            status=DUPLICATE_SKIPPED,
            metrics=None,
            fom=None,
            objective=failure_penalty,
            constraint_penalty=0.0,
        )
        return TraceScienceValidation(verified_row=verified, issues=issues)
    if result_manifest.get("status") != "succeeded":
        return _validate_failure_trace(
            trace,
            expected_status="real_check_failed",
            failure_penalty=failure_penalty,
            label=label,
            issues=issues,
        )

    if metric_manifest is None:
        issues.append(f"{label} scientific validation lacks metric manifest")
        return TraceScienceValidation(verified_row=None, issues=issues)
    if metric_manifest.get("status") != "succeeded":
        return _validate_failure_trace(
            trace,
            expected_status="metric_check_failed",
            failure_penalty=failure_penalty,
            label=label,
            issues=issues,
        )

    if trace_status in {"adapter_failed", "record_failed"}:
        return _validate_failure_trace(
            trace,
            expected_status=str(trace_status),
            failure_penalty=failure_penalty,
            label=label,
            issues=issues,
        )

    parent_metrics, metric_issues = _extract_parent_metrics(
        metric_manifest,
        metrics_config=metrics_config,
        label=label,
    )
    issues.extend(metric_issues)
    if parent_metrics is None:
        return TraceScienceValidation(verified_row=None, issues=issues)

    trace_metrics = trace.get("metrics")
    if not _same_metric_values(trace_metrics, parent_metrics):
        issues.append(
            f"{label} trace metrics do not match parent metric manifest"
        )

    evaluation = evaluate_candidate_objective(
        metrics_config,
        optimizer_config,
        parent_metrics,
    )
    if trace_status != evaluation.status:
        issues.append(
            f"{label} trace status mismatch: "
            f"expected={evaluation.status!r}, actual={trace_status!r}"
        )
    _append_optional_number_mismatch(
        issues,
        label=label,
        field="fom",
        expected=evaluation.fom,
        actual=trace.get("fom"),
    )
    _append_number_mismatch(
        issues,
        label=label,
        field="objective",
        expected=evaluation.objective,
        actual=trace.get("objective"),
    )
    _append_number_mismatch(
        issues,
        label=label,
        field="constraint_penalty",
        expected=evaluation.constraint_penalty,
        actual=trace.get("constraint_penalty"),
    )
    verified = _with_science(
        trace,
        status=evaluation.status,
        metrics=parent_metrics,
        fom=evaluation.fom,
        objective=evaluation.objective,
        constraint_penalty=evaluation.constraint_penalty,
    )
    return TraceScienceValidation(verified_row=verified, issues=issues)


def select_best_trace(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Apply the OpenBox/Native writer rule to verified trace dictionaries."""

    feasible = [row for row in rows if row.get("status") == "feasible"]
    candidates = feasible or [
        row for row in rows if _finite_number(row.get("objective")) is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: float(row["objective"]))


def duplicate_skipped_trace_issues(
    trace: dict[str, Any],
    *,
    failure_penalty: float,
    label: str | None = None,
) -> list[str]:
    """Validate the no-simulation sentinel emitted for exhausted duplicates."""

    trace_label = label or str(trace.get("run_id") or "trace row")
    issues: list[str] = []
    if trace.get("status") != DUPLICATE_SKIPPED:
        issues.append(
            f"{trace_label} duplicate trace status mismatch: "
            f"{trace.get('status')!r}"
        )
    for field in ("result_manifest", "metric_result_manifest"):
        if trace.get(field) not in (None, ""):
            issues.append(f"{trace_label} duplicate trace {field} must be null")
    if trace.get("metrics") is not None:
        issues.append(f"{trace_label} duplicate trace metrics must be null")
    if trace.get("fom") is not None:
        issues.append(f"{trace_label} duplicate trace fom must be null")
    _append_number_mismatch(
        issues,
        label=trace_label,
        field="objective",
        expected=failure_penalty,
        actual=trace.get("objective"),
    )
    _append_number_mismatch(
        issues,
        label=trace_label,
        field="constraint_penalty",
        expected=0.0,
        actual=trace.get("constraint_penalty"),
    )
    return issues


def _extract_parent_metrics(
    manifest: dict[str, Any],
    *,
    metrics_config: MetricsConfig,
    label: str,
) -> tuple[dict[str, float] | None, list[str]]:
    issues: list[str] = []
    raw_entries = manifest.get("metrics")
    if not isinstance(raw_entries, list):
        return None, [f"{label} parent metric manifest metrics must be a list"]

    configured_units = {metric.name: metric.unit for metric in metrics_config.metrics}
    values: dict[str, float] = {}
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            issues.append(f"{label} parent metric entry {index} must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            issues.append(f"{label} parent metric entry {index} has invalid name")
            continue
        if name in values:
            issues.append(f"{label} parent metric {name} is duplicated")
            continue
        if name not in configured_units:
            issues.append(f"{label} parent metric {name} is not configured")
            continue
        if entry.get("status") != "succeeded":
            issues.append(f"{label} parent metric {name} did not succeed")
            continue
        unit = entry.get("unit")
        if unit != configured_units[name]:
            issues.append(
                f"{label} parent metric {name} unit mismatch: "
                f"expected={configured_units[name]!r}, actual={unit!r}"
            )
            continue
        number = _finite_number(entry.get("value"))
        if number is None:
            issues.append(f"{label} parent metric {name} value is not finite")
            continue
        value_text = entry.get("value_text")
        if not isinstance(value_text, str):
            issues.append(
                f"{label} parent metric {name} value_text is not a finite scalar"
            )
            continue
        try:
            text_number = float(value_text.strip())
        except ValueError:
            text_number = math.nan
        if not math.isfinite(text_number):
            issues.append(
                f"{label} parent metric {name} value_text is not a finite scalar"
            )
            continue
        if not math.isclose(
            number,
            text_number,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            issues.append(
                f"{label} parent metric {name} value/value_text mismatch: "
                f"value={number!r}, value_text={value_text!r}"
            )
            continue
        values[name] = number

    missing = sorted(set(configured_units) - set(values))
    for name in missing:
        issues.append(f"{label} configured parent metric {name} is missing")
    if issues:
        return None, issues
    return values, []


def _validate_failure_trace(
    trace: dict[str, Any],
    *,
    expected_status: str,
    failure_penalty: float,
    label: str,
    issues: list[str],
) -> TraceScienceValidation:
    if trace.get("status") != expected_status:
        issues.append(
            f"{label} trace status mismatch: "
            f"expected={expected_status!r}, actual={trace.get('status')!r}"
        )
    if trace.get("metrics") is not None:
        issues.append(f"{label} failure trace metrics must be null")
    if trace.get("fom") is not None:
        issues.append(f"{label} failure trace fom must be null")
    _append_number_mismatch(
        issues,
        label=label,
        field="objective",
        expected=failure_penalty,
        actual=trace.get("objective"),
    )
    _append_number_mismatch(
        issues,
        label=label,
        field="constraint_penalty",
        expected=0.0,
        actual=trace.get("constraint_penalty"),
    )
    verified = _with_science(
        trace,
        status=expected_status,
        metrics=None,
        fom=None,
        objective=failure_penalty,
        constraint_penalty=0.0,
    )
    return TraceScienceValidation(verified_row=verified, issues=issues)


def _with_science(
    trace: dict[str, Any],
    *,
    status: str,
    metrics: dict[str, float] | None,
    fom: float | None,
    objective: float,
    constraint_penalty: float,
) -> dict[str, Any]:
    verified = dict(trace)
    verified.update(
        {
            "status": status,
            "metrics": metrics,
            "fom": fom,
            "objective": objective,
            "constraint_penalty": constraint_penalty,
        }
    )
    return verified


def _same_metric_values(actual: object, expected: dict[str, float]) -> bool:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    for name, expected_value in expected.items():
        actual_value = _finite_number(actual.get(name))
        if actual_value is None or actual_value != expected_value:
            return False
    return True


def _append_optional_number_mismatch(
    issues: list[str],
    *,
    label: str,
    field: str,
    expected: float | None,
    actual: object,
) -> None:
    if expected is None:
        if actual is not None:
            issues.append(
                f"{label} trace {field} mismatch: expected=None, actual={actual!r}"
            )
        return
    _append_number_mismatch(
        issues,
        label=label,
        field=field,
        expected=expected,
        actual=actual,
    )


def _append_number_mismatch(
    issues: list[str],
    *,
    label: str,
    field: str,
    expected: float,
    actual: object,
) -> None:
    actual_number = _finite_number(actual)
    if actual_number is None or not math.isclose(
        actual_number,
        float(expected),
        rel_tol=1e-12,
        abs_tol=1e-15,
    ):
        issues.append(
            f"{label} trace {field} mismatch: "
            f"expected={expected!r}, actual={actual!r}"
        )


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None
