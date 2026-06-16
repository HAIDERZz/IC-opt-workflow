from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


SUCCESSFUL_STATUSES = {"feasible", "constraint_failed"}


@dataclass(frozen=True)
class OptimizerBatchAuditInput:
    batch_id: str
    phase: str
    history_size_before: int
    current_batch_observations: Sequence[object]
    all_traces_so_far: Sequence[object] | None = None
    history_size_after: int | None = None
    suggestion_count: int | None = None
    evaluation_count: int | None = None
    duplicate_replacements: int = 0
    replay_history_count: int = 0
    resolved_surrogate_type: str | None = None
    resolved_acq_type: str | None = None
    resolved_acq_optimizer_type: str | None = None


@dataclass(frozen=True)
class OptimizerBatchAudit:
    batch_id: str
    phase: str
    history_size_before: int
    history_size_after: int
    suggestion_count: int
    evaluation_count: int
    successful_observation_count: int
    penalty_observation_count: int
    feasible_count: int
    best_objective_so_far: float | None
    best_feasible_so_far: float | None
    duplicate_replacements: int
    replay_history_count: int
    resolved_surrogate_type: str | None
    resolved_acq_type: str | None
    resolved_acq_optimizer_type: str | None


def build_batch_effectiveness_audit(
    payload: OptimizerBatchAuditInput | Mapping[str, Any] | object,
) -> dict[str, Any]:
    audit_input = _coerce_audit_input(payload)
    current_batch = list(audit_input.current_batch_observations)
    all_traces = list(audit_input.all_traces_so_far or current_batch)

    evaluation_count = _coerce_int(audit_input.evaluation_count, len(current_batch))
    history_size_after = _coerce_int(audit_input.history_size_after, len(all_traces))
    suggestion_count = _coerce_int(audit_input.suggestion_count, evaluation_count)

    successful_count = sum(_is_successful_observation(row) for row in current_batch)
    audit = OptimizerBatchAudit(
        batch_id=audit_input.batch_id,
        phase=audit_input.phase,
        history_size_before=audit_input.history_size_before,
        history_size_after=history_size_after,
        suggestion_count=suggestion_count,
        evaluation_count=evaluation_count,
        successful_observation_count=successful_count,
        penalty_observation_count=len(current_batch) - successful_count,
        feasible_count=sum(_status_of(row) == "feasible" for row in all_traces),
        best_objective_so_far=_best_finite_objective(all_traces),
        best_feasible_so_far=_best_finite_objective(
            [row for row in all_traces if _status_of(row) == "feasible"]
        ),
        duplicate_replacements=audit_input.duplicate_replacements,
        replay_history_count=audit_input.replay_history_count,
        resolved_surrogate_type=audit_input.resolved_surrogate_type,
        resolved_acq_type=audit_input.resolved_acq_type,
        resolved_acq_optimizer_type=audit_input.resolved_acq_optimizer_type,
    )
    return asdict(audit)


def _coerce_audit_input(
    payload: OptimizerBatchAuditInput | Mapping[str, Any] | object,
) -> OptimizerBatchAuditInput:
    if isinstance(payload, OptimizerBatchAuditInput):
        return payload

    current_batch = _sequence_value(payload, "current_batch_observations", "traces")
    all_traces = _sequence_value(payload, "all_traces_so_far", "history", "traces_so_far")
    default_history_size_before = max(
        len(all_traces or ()) - len(current_batch or ()),
        0,
    )

    return OptimizerBatchAuditInput(
        batch_id=str(_payload_value(payload, "batch_id", "")),
        phase=str(_payload_value(payload, "phase", "")),
        history_size_before=_coerce_int(
            _payload_value(payload, "history_size_before"),
            default_history_size_before,
        ),
        history_size_after=_coerce_int(_payload_value(payload, "history_size_after"), None),
        suggestion_count=_coerce_int(_payload_value(payload, "suggestion_count"), None),
        evaluation_count=_coerce_int(_payload_value(payload, "evaluation_count"), None),
        current_batch_observations=current_batch or (),
        all_traces_so_far=all_traces or (),
        duplicate_replacements=_coerce_int(
            _payload_value(payload, "duplicate_replacements"), 0
        ),
        replay_history_count=_coerce_int(
            _payload_value(
                payload,
                "replay_history_count",
                _payload_value(payload, "model_replay_evaluation_count"),
            ),
            0,
        ),
        resolved_surrogate_type=_string_or_none(
            _payload_value(
                payload,
                "resolved_surrogate_type",
                _payload_value(payload, "surrogate_type"),
            )
        ),
        resolved_acq_type=_string_or_none(
            _payload_value(
                payload,
                "resolved_acq_type",
                _payload_value(payload, "acq_type"),
            )
        ),
        resolved_acq_optimizer_type=_string_or_none(
            _payload_value(
                payload,
                "resolved_acq_optimizer_type",
                _payload_value(payload, "acq_optimizer_type"),
            )
        ),
    )


def _sequence_value(payload: object, *keys: str) -> Sequence[object] | None:
    for key in keys:
        value = _payload_value(payload, key)
        if value is not None:
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return value
            raise TypeError(f"{key} must be a sequence")
    return None


def _payload_value(payload: object, key: str, default: Any = None) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _is_successful_observation(row: object) -> bool:
    return (
        _status_of(row) in SUCCESSFUL_STATUSES
        and _finite_objective(_row_value(row, "objective")) is not None
    )


def _status_of(row: object) -> str:
    status = _row_value(row, "status")
    return str(status) if status is not None else ""


def _best_finite_objective(rows: Sequence[object] | Any) -> float | None:
    best: float | None = None
    for row in rows:
        objective = _finite_objective(_row_value(row, "objective"))
        if objective is None:
            continue
        if best is None or objective < best:
            best = objective
    return best


def _finite_objective(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        objective = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(objective):
        return None
    return objective


def _row_value(row: object, field_name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _coerce_int(value: Any, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
