from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_finalize import finalize_optimizer_run


COMPLETION_RELATIVE = Path("reports/optimizer_completion_report.json")
FINALIZE_RELATIVE = Path("reports/optimizer_finalize_report.json")
EFFECTIVENESS_AUDIT_RELATIVE = Path("reports/optimizer_effectiveness_audit.json")


@dataclass(frozen=True)
class OptimizerStatusSummary:
    status: str
    decision: str | None
    confidence: str | None
    global_optimum_claim: bool | None
    best_observed_run_id: str | None
    evaluation_count: int | None
    status_counts: dict[str, int]
    continuation_recommended: bool | None
    continuation_reason: str | None
    plateau_detected: bool | None
    reports: dict[str, str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def summarize_optimizer_status(project_dir: str | Path) -> OptimizerStatusSummary:
    project_root = Path(project_dir)
    finalize = finalize_optimizer_run(project_root)
    completion = _load_completion(project_root / COMPLETION_RELATIVE)
    continuation = _dict_value(completion.get("continuation"))

    reports = dict(finalize.reports)
    reports["finalize"] = FINALIZE_RELATIVE.as_posix()
    if (project_root / EFFECTIVENESS_AUDIT_RELATIVE).exists():
        reports["effectiveness_audit"] = EFFECTIVENESS_AUDIT_RELATIVE.as_posix()

    return OptimizerStatusSummary(
        status=finalize.status,
        decision=finalize.decision,
        confidence=finalize.confidence,
        global_optimum_claim=_bool_or_none(completion.get("global_optimum_claim")),
        best_observed_run_id=finalize.best_observed_run_id,
        evaluation_count=_int_or_none(completion.get("evaluation_count")),
        status_counts=_status_counts(completion.get("status_counts")),
        continuation_recommended=_bool_or_none(continuation.get("recommended")),
        continuation_reason=_string_or_none(continuation.get("reason")),
        plateau_detected=_bool_or_none(continuation.get("plateau_detected")),
        reports=reports,
        issues=finalize.issues,
        warnings=finalize.warnings,
    )


def _load_completion(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int):
            counts[key] = count
    return counts


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
