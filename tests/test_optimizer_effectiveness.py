from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass
from typing import Any


def _load_module():
    try:
        return importlib.import_module("hermes_workflow.optimizer_effectiveness")
    except ModuleNotFoundError:
        return None


def _trace(status: str, objective: Any = 1.0, **overrides: Any) -> dict[str, Any]:
    row = {"status": status}
    if objective is not _MISSING:
        row["objective"] = objective
    row.update(overrides)
    return row


_MISSING = object()


def test_build_batch_effectiveness_audit_summarizes_mixed_batch_statuses() -> None:
    module = _load_module()
    assert module is not None
    assert module.SUCCESSFUL_STATUSES == {"feasible", "constraint_failed"}

    payload = {
        "batch_id": "batch_002",
        "phase": "openbox_batch",
        "history_size_before": 2,
        "history_size_after": 5,
        "suggestion_count": 3,
        "evaluation_count": 3,
        "duplicate_replacements": 1,
        "replay_history_count": 2,
        "resolved_surrogate_type": "gp",
        "resolved_acq_type": "ei",
        "resolved_acq_optimizer_type": "local_random",
        "current_batch_observations": [
            _trace("feasible", 8.0),
            _trace("constraint_failed", 4.0),
            _trace("metric_check_failed", 9.5),
        ],
        "all_traces_so_far": [
            _trace("feasible", 5.5),
            _trace("real_check_failed", "bad-objective"),
            _trace("feasible", 8.0),
            _trace("constraint_failed", 4.0),
            _trace("metric_check_failed", 9.5),
        ],
    }

    audit = module.build_batch_effectiveness_audit(payload)

    assert audit == {
        "batch_id": "batch_002",
        "phase": "openbox_batch",
        "history_size_before": 2,
        "history_size_after": 5,
        "suggestion_count": 3,
        "evaluation_count": 3,
        "successful_observation_count": 2,
        "penalty_observation_count": 1,
        "feasible_count": 2,
        "best_objective_so_far": 4.0,
        "best_feasible_so_far": 5.5,
        "duplicate_replacements": 1,
        "replay_history_count": 2,
        "resolved_surrogate_type": "gp",
        "resolved_acq_type": "ei",
        "resolved_acq_optimizer_type": "local_random",
    }


def test_build_batch_effectiveness_audit_tolerates_missing_or_non_finite_objectives() -> None:
    module = _load_module()
    assert module is not None

    payload = {
        "batch_id": "batch_003",
        "phase": "openbox_batch",
        "current_batch_observations": [
            _trace("feasible", math.nan),
            _trace("metric_check_failed", _MISSING),
        ],
        "all_traces_so_far": [
            _trace("feasible", math.nan),
            _trace("constraint_failed", math.inf),
            _trace("real_check_failed", None),
            _trace("metric_check_failed", "not-a-number"),
            _trace("feasible", _MISSING),
        ],
    }

    audit = module.build_batch_effectiveness_audit(payload)

    assert audit["history_size_before"] == 3
    assert audit["history_size_after"] == 5
    assert audit["suggestion_count"] == 2
    assert audit["evaluation_count"] == 2
    assert audit["successful_observation_count"] == 0
    assert audit["penalty_observation_count"] == 2
    assert audit["feasible_count"] == 2
    assert audit["best_objective_so_far"] is None
    assert audit["best_feasible_so_far"] is None


def test_build_batch_effectiveness_audit_returns_none_for_best_feasible_when_no_feasible_rows_exist() -> None:
    module = _load_module()
    assert module is not None

    payload = {
        "batch_id": "batch_004",
        "phase": "openbox_batch",
        "current_batch_observations": [
            _trace("constraint_failed", 7.0),
            _trace("real_check_failed", 1.0),
        ],
        "all_traces_so_far": [
            _trace("constraint_failed", 7.0),
            _trace("metric_check_failed", 1.0),
            _trace("adapter_failed", 3.0),
        ],
    }

    audit = module.build_batch_effectiveness_audit(payload)

    assert audit["feasible_count"] == 0
    assert audit["best_objective_so_far"] == 1.0
    assert audit["best_feasible_so_far"] is None


def test_build_batch_effectiveness_audit_accepts_dataclass_input_for_duplicate_and_replay_fields() -> None:
    module = _load_module()
    assert module is not None

    payload = module.OptimizerBatchAuditInput(
        batch_id="batch_005",
        phase="seed",
        history_size_before=4,
        history_size_after=6,
        suggestion_count=2,
        evaluation_count=2,
        current_batch_observations=[
            _trace("feasible", 3.0),
            _trace("real_check_failed", 11.0),
        ],
        all_traces_so_far=[
            _trace("feasible", 6.0),
            _trace("constraint_failed", 5.0),
            _trace("metric_check_failed", 12.0),
            _trace("feasible", 3.0),
            _trace("real_check_failed", 11.0),
            _trace("constraint_failed", 4.0),
        ],
        duplicate_replacements=2,
        replay_history_count=4,
        resolved_surrogate_type="prf",
        resolved_acq_type="eic",
        resolved_acq_optimizer_type="random_scipy",
    )

    audit = module.build_batch_effectiveness_audit(payload)

    assert audit["duplicate_replacements"] == 2
    assert audit["replay_history_count"] == 4
    assert audit["resolved_surrogate_type"] == "prf"
    assert audit["resolved_acq_type"] == "eic"
    assert audit["resolved_acq_optimizer_type"] == "random_scipy"
    assert audit["best_objective_so_far"] == 3.0
    assert audit["best_feasible_so_far"] == 3.0


def test_build_batch_effectiveness_audit_accepts_same_shape_object_payload() -> None:
    module = _load_module()
    assert module is not None

    @dataclass(frozen=True)
    class TraceRow:
        status: str
        objective: float

    @dataclass(frozen=True)
    class AuditPayload:
        batch_id: str
        phase: str
        history_size_before: int
        current_batch_observations: list[TraceRow]
        all_traces_so_far: list[TraceRow]
        resolved_surrogate_type: str
        resolved_acq_type: str
        resolved_acq_optimizer_type: str

    payload = AuditPayload(
        batch_id="batch_006",
        phase="bo",
        history_size_before=3,
        current_batch_observations=[
            TraceRow("feasible", 8.0),
            TraceRow("constraint_failed", 4.0),
            TraceRow("metric_check_failed", 2.0),
        ],
        all_traces_so_far=[
            TraceRow("feasible", 8.0),
            TraceRow("constraint_failed", 4.0),
            TraceRow("metric_check_failed", 2.0),
        ],
        resolved_surrogate_type="gp",
        resolved_acq_type="eic",
        resolved_acq_optimizer_type="random_scipy",
    )

    audit = module.build_batch_effectiveness_audit(payload)

    assert audit["successful_observation_count"] == 2
    assert audit["penalty_observation_count"] == 1
    assert audit["best_objective_so_far"] == 2.0
    assert audit["best_feasible_so_far"] == 8.0
    assert audit["resolved_acq_type"] == "eic"


def test_build_batch_effectiveness_audit_returns_json_serializable_dict() -> None:
    module = _load_module()
    assert module is not None

    audit = module.build_batch_effectiveness_audit(
        {
            "batch_id": "batch_006",
            "phase": "openbox_batch",
            "current_batch_observations": [_trace("feasible", 2.5)],
            "all_traces_so_far": [_trace("feasible", 2.5)],
        }
    )

    assert sorted(audit) == [
        "batch_id",
        "best_feasible_so_far",
        "best_objective_so_far",
        "duplicate_replacements",
        "evaluation_count",
        "feasible_count",
        "history_size_after",
        "history_size_before",
        "penalty_observation_count",
        "phase",
        "replay_history_count",
        "resolved_acq_optimizer_type",
        "resolved_acq_type",
        "resolved_surrogate_type",
        "successful_observation_count",
        "suggestion_count",
    ]
    assert json.loads(json.dumps(audit)) == audit
