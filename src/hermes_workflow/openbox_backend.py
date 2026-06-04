from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.native_turbo import (
    NativeTurboEvaluationTrace,
    NativeTurboRunResult,
    evaluate_candidate_objective,
    load_native_turbo_contract,
    quantize_candidate,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from hermes_workflow.schemas import VariableKind, VariablesConfig


OPENBOX_BACKEND = "openbox"
FAKE_EXECUTION_MODE = "fake"
OPENBOX_BATCH_PHASE = "openbox_batch"

AdvisorFactory = Callable[[object, int], object]


@dataclass(frozen=True)
class OpenBoxVariable:
    name: str
    kind: str
    lower: float
    upper: float
    step: float
    unit: str


@dataclass(frozen=True)
class FakeMetricObservation:
    metrics: dict[str, float]
    issues: list[str]


@dataclass(frozen=True)
class FakeOpenBoxObservation:
    objectives: list[float]
    constraints: list[float]
    config: dict[str, Any]


def run_openbox_fake_optimization(
    project_dir: str | Path,
    *,
    max_evals: int,
    batch_size: int,
    advisor_factory: AdvisorFactory | None = None,
    random_seed: int | None = None,
) -> NativeTurboRunResult:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    project_root = Path(project_dir)
    contract = load_native_turbo_contract(project_root)
    seed = (
        random_seed
        if random_seed is not None
        else contract.optimizer.optimizer.random_seed
    )
    advisor = (
        advisor_factory(_build_openbox_space(contract.variables), seed)
        if advisor_factory is not None
        else _build_openbox_advisor(contract.variables, seed)
    )

    traces: list[NativeTurboEvaluationTrace] = []
    batch_index = 0
    while len(traces) < max_evals:
        batch_index += 1
        remaining = max_evals - len(traces)
        selected_batch_size = min(batch_size, remaining)
        suggestions = _get_suggestions(advisor, selected_batch_size)
        observations: list[Any] = []
        for slot, suggestion in enumerate(suggestions, start=1):
            evaluation_index = len(traces) + 1
            suggestion_values = _suggestion_dict(suggestion)
            raw_x = _raw_values_from_suggestion(contract.variables, suggestion_values)
            parameters = quantize_candidate(contract.variables, raw_x)
            metric_observation = _fake_inverter_metrics(parameters)
            objective_eval = evaluate_candidate_objective(
                contract.metrics,
                contract.optimizer,
                metric_observation.metrics,
            )
            trace = NativeTurboEvaluationTrace(
                evaluation_index=evaluation_index,
                run_id=f"fake_{evaluation_index:03d}",
                selection_phase=OPENBOX_BATCH_PHASE,
                raw_x=raw_x,
                parameters=parameters,
                status=objective_eval.status,
                objective=objective_eval.objective,
                fom=objective_eval.fom,
                constraint_penalty=objective_eval.constraint_penalty,
                metrics=metric_observation.metrics,
                result_manifest=None,
                metric_result_manifest=None,
                issues=[*objective_eval.issues, *metric_observation.issues],
                batch_id=f"batch_{batch_index:03d}",
                batch_slot=slot,
                batch_size=selected_batch_size,
                batch_worker_count=selected_batch_size,
                max_parallel_jobs=batch_size,
                threads_per_run=None,
                parallel_jobs=batch_size,
            )
            traces.append(trace)
            observations.append(_make_openbox_observation(trace, suggestion_values))
            if len(traces) == max_evals:
                break
        _update_observations(advisor, observations)

    result = NativeTurboRunResult(
        evaluation_count=len(traces),
        traces=traces,
        best_trace=_best_trace(traces),
    )
    report_path, evaluations_path = write_openbox_fake_reports(project_root, result)
    return NativeTurboRunResult(
        evaluation_count=result.evaluation_count,
        traces=result.traces,
        best_trace=result.best_trace,
        report_path=report_path,
        evaluations_path=evaluations_path,
    )


def write_openbox_fake_reports(
    project_dir: Path,
    result: NativeTurboRunResult,
) -> tuple[Path, Path]:
    reports_dir = Path(project_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    evaluations_path = Path(project_dir) / EVALUATIONS_RELATIVE
    report_path = Path(project_dir) / REPORT_RELATIVE
    with evaluations_path.open("w", encoding="utf-8") as handle:
        for trace in result.traces:
            handle.write(json.dumps(asdict(trace), sort_keys=True) + "\n")
    batch_ids = [trace.batch_id for trace in result.traces if trace.batch_id]
    payload = {
        "schema_version": "1.0",
        "status": "completed",
        "backend": OPENBOX_BACKEND,
        "execution_mode": FAKE_EXECUTION_MODE,
        "evaluation_count": result.evaluation_count,
        "best_candidate": (
            asdict(result.best_trace) if result.best_trace is not None else None
        ),
        "evaluations": EVALUATIONS_RELATIVE.as_posix(),
        "issues": [],
        "batch_summary": {
            "batch_count": len(set(batch_ids)),
            "max_batch_worker_count": max(
                (trace.batch_worker_count or 0 for trace in result.traces),
                default=0,
            ),
            "status_counts": dict(Counter(trace.status for trace in result.traces)),
        },
    }
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path, evaluations_path


def _load_openbox() -> tuple[Any, Any, Any]:
    try:
        from openbox import Advisor, Observation, space as sp
    except ImportError as exc:
        raise RuntimeError(
            "OpenBox is not installed; install it in the active environment "
            "to run the OpenBox backend"
        ) from exc
    return Advisor, Observation, sp


def _build_openbox_space(variables: VariablesConfig) -> list[OpenBoxVariable]:
    return [
        OpenBoxVariable(
            name=variable.name,
            kind=variable.kind.value,
            lower=_numeric_value(variable.lower),
            upper=_numeric_value(variable.upper),
            step=_numeric_value(variable.step),
            unit=_unit_suffix(variable.lower),
        )
        for variable in variables.variables
    ]


def _build_openbox_advisor(variables: VariablesConfig, seed: int) -> object:
    Advisor, _Observation, sp = _load_openbox()
    space = sp.Space()
    for variable in variables.variables:
        lower = _numeric_value(variable.lower)
        upper = _numeric_value(variable.upper)
        if variable.kind == VariableKind.INTEGER:
            space.add_variable(sp.Int(variable.name, int(lower), int(upper)))
        else:
            space.add_variable(sp.Real(variable.name, lower, upper))
    return Advisor(
        space,
        num_objectives=1,
        random_state=seed,
    )


def _get_suggestions(advisor: object, batch_size: int) -> list[object]:
    if hasattr(advisor, "get_suggestions"):
        suggestions = advisor.get_suggestions(batch_size=batch_size)
        return list(suggestions)
    if hasattr(advisor, "get_suggestion"):
        return [advisor.get_suggestion() for _ in range(batch_size)]
    raise TypeError("OpenBox advisor must provide get_suggestions or get_suggestion")


def _update_observations(advisor: object, observations: list[object]) -> None:
    if not observations:
        return
    if hasattr(advisor, "update_observations"):
        advisor.update_observations(observations)
        return
    if hasattr(advisor, "update_observation"):
        for observation in observations:
            advisor.update_observation(observation)
        return
    raise TypeError("OpenBox advisor must provide an observation update method")


def _suggestion_dict(suggestion: object) -> dict[str, Any]:
    if isinstance(suggestion, dict):
        return dict(suggestion)
    if hasattr(suggestion, "get_dictionary"):
        payload = suggestion.get_dictionary()
        if isinstance(payload, dict):
            return payload
    try:
        return dict(suggestion)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise TypeError("OpenBox suggestion must be mapping-like") from exc


def _raw_values_from_suggestion(
    variables: VariablesConfig,
    suggestion: dict[str, Any],
) -> list[float]:
    raw_values: list[float] = []
    for variable in variables.variables:
        if variable.name in suggestion:
            raw_values.append(float(suggestion[variable.name]))
            continue
        if variable.name == "FP" and "FN" in suggestion:
            raw_values.append(float(suggestion["FN"]))
            continue
        raise ValueError(f"OpenBox suggestion missing variable {variable.name}")
    return raw_values


def _fake_inverter_metrics(parameters: dict[str, str]) -> FakeMetricObservation:
    fn = float(parameters.get("FN", "1"))
    fp = float(parameters.get("FP", parameters.get("FN", "1")))
    wn = _numeric_value(parameters.get("WN", "1u"))
    wp = _numeric_value(parameters.get("WP", "1u"))
    n_drive = max(fn * wn, 1e-9)
    p_drive = max(fp * wp, 1e-9)
    rise = max(15e-12, 105e-12 / p_drive)
    fall = max(15e-12, 95e-12 / n_drive)
    power = (n_drive + p_drive) * 9.0e-6
    return FakeMetricObservation(
        metrics={"rise": rise, "fall": fall, "DC": power},
        issues=[],
    )


def _make_openbox_observation(
    trace: NativeTurboEvaluationTrace,
    suggestion: dict[str, Any],
) -> FakeOpenBoxObservation:
    constraints = [0.0 if trace.status == "feasible" else trace.constraint_penalty]
    return FakeOpenBoxObservation(
        objectives=[trace.objective],
        constraints=constraints,
        config=suggestion,
    )


def _best_trace(
    traces: list[NativeTurboEvaluationTrace],
) -> NativeTurboEvaluationTrace | None:
    feasible = [trace for trace in traces if trace.status == "feasible"]
    if feasible:
        return min(feasible, key=lambda trace: trace.objective)
    finite = [trace for trace in traces if math.isfinite(trace.objective)]
    return min(finite, key=lambda trace: trace.objective) if finite else None


def _numeric_value(raw: str) -> float:
    value, _unit = _parse_decimal_unit(raw)
    return float(value)


def _unit_suffix(raw: str) -> str:
    _value, unit = _parse_decimal_unit(raw)
    return unit


def _parse_decimal_unit(raw: str) -> tuple[Decimal, str]:
    index = 0
    text = str(raw).strip()
    while index < len(text) and (
        text[index].isdigit() or text[index] in {"+", "-", ".", "e", "E"}
    ):
        index += 1
    if index == 0:
        raise ValueError(f"cannot parse decimal value {raw!r}")
    return Decimal(text[:index]), text[index:].strip()
