from __future__ import annotations

import json
import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.native_turbo import (
    NativeTurboBatchCandidate,
    NativeTurboEvaluationTrace,
    NativeTurboObservation,
    NativeTurboRunResult,
    execute_and_check_real_candidate,
    evaluate_candidate_objective,
    load_native_turbo_contract,
    quantize_candidate,
)
from hermes_workflow.optimizer_artifacts import (
    EVALUATIONS_RELATIVE,
    REPORT_RELATIVE,
    load_optimizer_artifacts,
)
from hermes_workflow.optimizer_resources import optimizer_cpu_thread_limits
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
from hermes_workflow.schemas import (
    ConstraintOp,
    MetricsConfig,
    VariableKind,
    VariablesConfig,
)
from hermes_workflow.validate import assert_valid_project


OPENBOX_BACKEND = "openbox"
FAKE_EXECUTION_MODE = "fake"
REAL_EXECUTION_MODE = "real"
OPENBOX_BATCH_PHASE = "openbox_batch"
OPENBOX_SOURCE = "openbox_optimizer"
OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE = Path(
    "reports/openbox_advanced_visualization_manifest.json"
)
OPENBOX_ADVANCED_VISUALIZATION_LOGGING_RELATIVE = Path(
    "reports/openbox_advanced_visualization"
)

AdvisorFactory = Callable[[object, int], object]
BatchEvaluator = Callable[[list[NativeTurboBatchCandidate]], list[NativeTurboObservation]]


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


@dataclass(frozen=True)
class OpenBoxBatchRunSettings:
    execution_mode: str
    max_evals: int
    batch_size: int
    random_seed: int
    parallel_jobs: int
    threads_per_run: int | None
    optimizer_cpu_threads: int | None
    continuation_enabled: bool = False
    prior_evaluation_count: int = 0
    additional_evals: int | None = None


@dataclass(frozen=True)
class OpenBoxPreparedSuggestion:
    config: object
    values: dict[str, Any]
    raw_x: list[float]
    parameters: dict[str, str]
    candidate_id: str
    run_id: str
    batch_id: str
    batch_slot: int
    batch_size: int
    replacement_issues: list[str]


@dataclass(frozen=True)
class OpenBoxBatchResult:
    candidates: list[OpenBoxPreparedSuggestion]
    duplicate_replacements: int


def run_openbox_fake_optimization(
    project_dir: str | Path,
    *,
    max_evals: int | None = None,
    additional_evals: int | None = None,
    continue_from_existing: bool = False,
    batch_size: int,
    advisor_factory: AdvisorFactory | None = None,
    random_seed: int | None = None,
    surrogate_type: str | None = None,
    acq_type: str | None = None,
    acq_optimizer_type: str | None = None,
) -> NativeTurboRunResult:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    project_root = Path(project_dir)
    contract = load_native_turbo_contract(project_root)
    seed = (
        random_seed
        if random_seed is not None
        else contract.optimizer.optimizer.random_seed
    )
    prior_traces = _load_continuation_traces(
        project_root,
        execution_mode=FAKE_EXECUTION_MODE,
        enabled=continue_from_existing,
    )
    selected_max_evals = _select_target_evaluation_count(
        max_evals=max_evals,
        additional_evals=additional_evals,
        continue_from_existing=continue_from_existing,
        prior_count=len(prior_traces),
        default_max_evals=None,
    )
    result = _run_openbox_batches(
        project_root,
        max_evals=selected_max_evals,
        batch_size=batch_size,
        advisor_factory=advisor_factory,
        evaluator=_fake_batch_evaluator,
        execution_mode=FAKE_EXECUTION_MODE,
        random_seed=seed,
        parallel_jobs=batch_size,
        threads_per_run=None,
        optimizer_cpu_threads=contract.optimizer.optimizer.optimizer_cpu_threads,
        prior_traces=prior_traces,
        continuation_additional_evals=additional_evals,
        surrogate_type=surrogate_type,
        acq_type=acq_type,
        acq_optimizer_type=acq_optimizer_type,
    )
    return result


def run_openbox_real_optimization(
    project_dir: str | Path,
    *,
    max_evals: int | None = None,
    additional_evals: int | None = None,
    continue_from_existing: bool = False,
    batch_size: int | None = None,
    parallel_jobs: int | None = None,
    cadence_cshrc: Path | None = None,
    advisor_factory: AdvisorFactory | None = None,
    adapter: Callable[..., object] | None = None,
    random_seed: int | None = None,
    surrogate_type: str | None = None,
    acq_type: str | None = None,
    acq_optimizer_type: str | None = None,
) -> NativeTurboRunResult:
    project_root = Path(project_dir)
    bundle = assert_valid_project(project_root)
    selected_batch_size = batch_size or bundle.optimizer.optimizer.batch_size
    selected_parallel_jobs = parallel_jobs or bundle.spectre.spectre.parallel_jobs
    if selected_batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if selected_parallel_jobs < 1:
        raise ValueError("parallel_jobs must be >= 1")

    contract = load_native_turbo_contract(project_root)
    seed = (
        random_seed
        if random_seed is not None
        else contract.optimizer.optimizer.random_seed
    )
    prior_traces = _load_continuation_traces(
        project_root,
        execution_mode=REAL_EXECUTION_MODE,
        enabled=continue_from_existing,
    )
    selected_max_evals = _select_target_evaluation_count(
        max_evals=max_evals,
        additional_evals=additional_evals,
        continue_from_existing=continue_from_existing,
        prior_count=len(prior_traces),
        default_max_evals=bundle.optimizer.optimizer.max_evaluations,
    )
    evaluator = make_openbox_real_candidate_batch_evaluator(
        project_root,
        cadence_cshrc=cadence_cshrc,
        max_workers=min(selected_parallel_jobs, selected_batch_size),
        adapter=adapter,
        allow_optimizer_continuation=continue_from_existing,
    )
    return _run_openbox_batches(
        project_root,
        max_evals=selected_max_evals,
        batch_size=selected_batch_size,
        advisor_factory=advisor_factory,
        evaluator=evaluator,
        execution_mode=REAL_EXECUTION_MODE,
        random_seed=seed,
        parallel_jobs=selected_parallel_jobs,
        threads_per_run=bundle.spectre.spectre.threads_per_run,
        optimizer_cpu_threads=bundle.optimizer.optimizer.optimizer_cpu_threads,
        prior_traces=prior_traces,
        continuation_additional_evals=additional_evals,
        surrogate_type=surrogate_type,
        acq_type=acq_type,
        acq_optimizer_type=acq_optimizer_type,
    )


def write_openbox_fake_reports(
    project_dir: Path,
    result: NativeTurboRunResult,
) -> tuple[Path, Path]:
    return write_openbox_reports(
        project_dir,
        result,
        settings=OpenBoxBatchRunSettings(
            execution_mode=FAKE_EXECUTION_MODE,
            max_evals=result.evaluation_count,
            batch_size=max(
                (trace.batch_size or 0 for trace in result.traces),
                default=0,
            ),
            random_seed=0,
            parallel_jobs=max(
                (trace.parallel_jobs or 0 for trace in result.traces),
                default=0,
            ),
            threads_per_run=None,
            optimizer_cpu_threads=None,
        ),
        duplicate_replacements=0,
    )


def write_openbox_reports(
    project_dir: Path,
    result: NativeTurboRunResult,
    *,
    settings: OpenBoxBatchRunSettings,
    duplicate_replacements: int,
    advanced_visualization: dict[str, Any] | None = None,
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
        "execution_mode": settings.execution_mode,
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
        "openbox": {
            "random_seed": settings.random_seed,
            "max_evals": settings.max_evals,
            "batch_size": settings.batch_size,
            "parallel_jobs": settings.parallel_jobs,
            "threads_per_run": settings.threads_per_run,
            "optimizer_cpu_threads": settings.optimizer_cpu_threads,
            "duplicate_replacements": duplicate_replacements,
            "continuation": {
                "enabled": settings.continuation_enabled,
                "prior_evaluation_count": settings.prior_evaluation_count,
                "additional_evals": settings.additional_evals,
                "target_total_evals": settings.max_evals,
            },
            "advanced_visualization": advanced_visualization
            or {
                "status": "not_generated",
                "reason": "OpenBox advanced visualization is generated only at final run closeout.",
            },
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


def _load_continuation_traces(
    project_dir: Path,
    *,
    execution_mode: str,
    enabled: bool,
) -> list[NativeTurboEvaluationTrace]:
    if not enabled:
        return []
    issues: list[str] = []
    artifacts = load_optimizer_artifacts(project_dir, issues)
    if issues:
        raise ValueError(
            "cannot load OpenBox continuation artifacts: " + "; ".join(issues)
        )
    if artifacts.report.get("backend") != OPENBOX_BACKEND:
        raise ValueError("OpenBox continuation requires prior OpenBox artifacts")
    if artifacts.report.get("execution_mode") != execution_mode:
        raise ValueError(
            "OpenBox continuation execution mode mismatch: "
            f"expected {execution_mode}"
        )
    traces = [_trace_from_payload(row) for row in artifacts.traces]
    if not traces:
        raise ValueError("OpenBox continuation requires at least one prior trace")
    return traces


def _trace_from_payload(payload: dict[str, Any]) -> NativeTurboEvaluationTrace:
    field_names = {field.name for field in fields(NativeTurboEvaluationTrace)}
    values = {name: payload[name] for name in field_names if name in payload}
    try:
        return NativeTurboEvaluationTrace(**values)
    except TypeError as exc:
        raise ValueError("invalid OpenBox continuation trace payload") from exc


def _select_target_evaluation_count(
    *,
    max_evals: int | None,
    additional_evals: int | None,
    continue_from_existing: bool,
    prior_count: int,
    default_max_evals: int | None,
) -> int:
    if continue_from_existing:
        if additional_evals is None:
            raise ValueError("additional_evals is required for OpenBox continuation")
        if additional_evals < 1:
            raise ValueError("additional_evals must be >= 1")
        return prior_count + additional_evals

    if additional_evals is not None:
        raise ValueError("additional_evals is only valid for OpenBox continuation")
    selected = max_evals if max_evals is not None else default_max_evals
    if selected is None:
        raise ValueError("max_evals is required")
    if selected < 1:
        raise ValueError("max_evals must be >= 1")
    return selected


def _run_openbox_batches(
    project_dir: Path,
    *,
    max_evals: int,
    batch_size: int,
    advisor_factory: AdvisorFactory | None,
    evaluator: BatchEvaluator,
    execution_mode: str,
    random_seed: int,
    parallel_jobs: int,
    threads_per_run: int | None,
    optimizer_cpu_threads: int,
    prior_traces: list[NativeTurboEvaluationTrace] | None = None,
    continuation_additional_evals: int | None = None,
    surrogate_type: str | None = None,
    acq_type: str | None = None,
    acq_optimizer_type: str | None = None,
) -> NativeTurboRunResult:
    contract = load_native_turbo_contract(project_dir)
    with optimizer_cpu_thread_limits(
        optimizer_cpu_threads,
        set_environment=True,
        set_torch=False,
    ):
        advisor, observation_factory, config_builder = _create_advisor(
            project_dir,
            contract.variables,
            random_seed,
            advisor_factory=advisor_factory,
            num_constraints=len(contract.metrics.constraints),
            surrogate_type=surrogate_type,
            acq_type=acq_type,
            acq_optimizer_type=acq_optimizer_type,
        )
    traces: list[NativeTurboEvaluationTrace] = list(prior_traces or [])
    prior_count = len(traces)
    seen_keys: set[tuple[tuple[str, str], ...]] = _seen_keys_from_traces(traces)
    duplicate_replacements = 0
    batch_index = _max_batch_index(traces)
    run_offset = (
        _next_run_offset(project_dir, "real")
        if execution_mode == REAL_EXECUTION_MODE
        else prior_count
    )
    settings = OpenBoxBatchRunSettings(
        execution_mode=execution_mode,
        max_evals=max_evals,
        batch_size=batch_size,
        random_seed=random_seed,
        parallel_jobs=parallel_jobs,
        threads_per_run=threads_per_run,
        optimizer_cpu_threads=optimizer_cpu_threads,
        continuation_enabled=prior_count > 0,
        prior_evaluation_count=prior_count,
        additional_evals=continuation_additional_evals,
    )
    if traces:
        with optimizer_cpu_thread_limits(
            optimizer_cpu_threads,
            set_environment=True,
            set_torch=False,
        ):
            _update_observations(
                advisor,
                [
                    _make_openbox_observation(
                        metrics_config=contract.metrics,
                        trace=trace,
                        config=config_builder(trace.parameters),
                        observation_factory=observation_factory,
                    )
                    for trace in traces
                ],
            )

    while len(traces) < max_evals:
        batch_index += 1
        selected_batch_size = min(batch_size, max_evals - len(traces))
        with optimizer_cpu_thread_limits(
            optimizer_cpu_threads,
            set_environment=True,
            set_torch=False,
        ):
            batch = _prepare_unique_batch(
                advisor=advisor,
                variables=contract.variables,
                seen_keys=seen_keys,
                batch_id=f"batch_{batch_index:03d}",
                batch_size=selected_batch_size,
                evaluation_offset=len(traces),
                run_evaluation_offset=len(traces) - prior_count,
                run_offset=run_offset,
                run_prefix=(
                    "fake" if execution_mode == FAKE_EXECUTION_MODE else "real"
                ),
            )
        duplicate_replacements += batch.duplicate_replacements
        observations = evaluator(
            [
                NativeTurboBatchCandidate(
                    evaluation_index=candidate.batch_slot + len(traces),
                    run_id=candidate.run_id,
                    candidate_id=candidate.candidate_id,
                    batch_id=candidate.batch_id,
                    batch_slot=candidate.batch_slot,
                    batch_size=candidate.batch_size,
                    selection_phase=OPENBOX_BATCH_PHASE,
                    raw_x=candidate.raw_x,
                    parameters=candidate.parameters,
                    replacement_issues=candidate.replacement_issues,
                )
                for candidate in batch.candidates
            ]
        )
        if len(observations) != len(batch.candidates):
            raise RuntimeError("OpenBox evaluator returned an unexpected observation count")

        openbox_observations: list[object] = []
        for candidate, observation in zip(batch.candidates, observations, strict=True):
            trace = _trace_from_observation(
                contract_metrics=contract.metrics,
                contract_optimizer=contract.optimizer,
                candidate=candidate,
                observation=observation,
                evaluation_index=len(traces) + 1,
                parallel_jobs=parallel_jobs,
                threads_per_run=threads_per_run,
            )
            traces.append(trace)
            openbox_observations.append(
                _make_openbox_observation(
                    metrics_config=contract.metrics,
                    trace=trace,
                    config=candidate.config,
                    observation_factory=observation_factory,
                )
            )

        with optimizer_cpu_thread_limits(
            optimizer_cpu_threads,
            set_environment=True,
            set_torch=False,
        ):
            _update_observations(advisor, openbox_observations)
        partial = NativeTurboRunResult(
            evaluation_count=len(traces),
            traces=list(traces),
            best_trace=_best_trace(traces),
        )
        write_openbox_reports(
            project_dir,
            partial,
            settings=settings,
            duplicate_replacements=duplicate_replacements,
        )

    result = NativeTurboRunResult(
        evaluation_count=len(traces),
        traces=traces,
        best_trace=_best_trace(traces),
    )
    with optimizer_cpu_thread_limits(
        optimizer_cpu_threads,
        set_environment=True,
        set_torch=False,
    ):
        advanced_visualization = _write_openbox_advanced_visualization_manifest(
            project_dir,
            advisor=advisor,
            max_evals=max_evals,
        )
    report_path, evaluations_path = write_openbox_reports(
        project_dir,
        result,
        settings=settings,
        duplicate_replacements=duplicate_replacements,
        advanced_visualization=advanced_visualization,
    )
    return NativeTurboRunResult(
        evaluation_count=result.evaluation_count,
        traces=result.traces,
        best_trace=result.best_trace,
        report_path=report_path,
        evaluations_path=evaluations_path,
    )


def _write_openbox_advanced_visualization_manifest(
    project_dir: Path,
    *,
    advisor: object,
    max_evals: int,
) -> dict[str, Any]:
    manifest_path = project_dir / OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _generate_openbox_advanced_visualization(
        project_dir,
        advisor=advisor,
        max_evals=max_evals,
    )
    payload["schema_version"] = "1.0"
    payload["manifest_path"] = OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE.as_posix()
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _generate_openbox_advanced_visualization(
    project_dir: Path,
    *,
    advisor: object,
    max_evals: int,
) -> dict[str, Any]:
    requested_includes = [
        "objective_and_constraint_history",
        "surrogate_fit_verification",
        "parameter_importance",
    ]
    base = {
        "mode": "advanced",
        "open_html": False,
        "show_importance": True,
        "verify_surrogate": True,
        "logging_dir": OPENBOX_ADVANCED_VISUALIZATION_LOGGING_RELATIVE.as_posix(),
        "requested_includes": requested_includes,
    }
    if not hasattr(advisor, "get_history"):
        return {
            **base,
            "status": "not_available",
            "reason": "OpenBox advisor history is unavailable for this runner.",
        }

    try:
        history = advisor.get_history()
        if not hasattr(history, "visualize_html"):
            return {
                **base,
                "status": "not_available",
                "reason": "OpenBox history does not provide visualize_html.",
            }
        visualizer = history.visualize_html(
            logging_dir=str(project_dir / OPENBOX_ADVANCED_VISUALIZATION_LOGGING_RELATIVE),
            open_html=False,
            show_importance=True,
            verify_surrogate=True,
            advisor=advisor,
            task_info={"max_runs": max_evals},
        )
    except ModuleNotFoundError as exc:
        return {
            **base,
            "status": "failed",
            "failure_kind": "dependency_missing",
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_kind": "visualization_error",
            "reason": str(exc),
        }

    raw_html_path = getattr(visualizer, "html_path", None)
    raw_json_path = getattr(visualizer, "json_path", None)
    if not raw_html_path or not raw_json_path:
        return {
            **base,
            "status": "failed",
            "failure_kind": "artifact_missing",
            "reason": "OpenBox visualizer did not expose HTML/JSON artifact paths.",
        }
    html_path = Path(raw_html_path)
    json_path = Path(raw_json_path)
    if not html_path.exists() or not json_path.exists():
        return {
            **base,
            "status": "failed",
            "failure_kind": "artifact_missing",
            "reason": "OpenBox visualizer returned without expected HTML/JSON artifacts.",
            "html_path": _project_relative(project_dir, html_path),
            "json_path": _project_relative(project_dir, json_path),
        }

    includes, warnings = _openbox_visualization_capabilities(json_path)
    status = (
        "generated"
        if set(requested_includes).issubset(set(includes))
        else "generated_partial"
    )
    payload = {
        **base,
        "status": status,
        "html_path": _project_relative(project_dir, html_path),
        "json_path": _project_relative(project_dir, json_path),
        "output_dir": _project_relative(
            project_dir,
            Path(getattr(visualizer, "output_dir", html_path.parent)),
        ),
        "includes": includes,
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def _openbox_visualization_capabilities(json_path: Path) -> tuple[list[str], list[str]]:
    includes = ["objective_and_constraint_history"]
    warnings: list[str] = []
    try:
        text = json_path.read_text(encoding="utf-8").strip()
        if text.startswith("var info="):
            text = text[len("var info=") :]
        if text.endswith(";"):
            text = text[:-1]
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        return includes, [f"could not inspect OpenBox visualization data: {exc}"]

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return includes, ["OpenBox visualization data is missing the data object"]

    if data.get("pred_label_data") is not None or data.get("grade_data") is not None:
        includes.append("surrogate_fit_verification")
    else:
        warnings.append("surrogate verification data was not generated")

    if data.get("importance_data") is not None:
        includes.append("parameter_importance")
    else:
        warnings.append("parameter importance data was not generated")

    return includes, warnings


def _project_relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _seen_keys_from_traces(
    traces: list[NativeTurboEvaluationTrace],
) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(trace.parameters.items())) for trace in traces}


def _max_batch_index(traces: list[NativeTurboEvaluationTrace]) -> int:
    indexes: list[int] = []
    for trace in traces:
        if trace.batch_id is None or not trace.batch_id.startswith("batch_"):
            continue
        try:
            indexes.append(int(trace.batch_id.rsplit("_", 1)[1]))
        except ValueError:
            continue
    return max(indexes, default=0)


def _build_openbox_space(
    variables: VariablesConfig,
    space_module: object | None = None,
) -> object:
    if space_module is None:
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

    space = space_module.Space()
    for variable in variables.variables:
        lower = _numeric_value(variable.lower)
        upper = _numeric_value(variable.upper)
        step = _numeric_value(variable.step)
        if variable.kind == VariableKind.INTEGER:
            space.add_variable(
                space_module.Int(
                    variable.name,
                    int(lower),
                    int(upper),
                    q=int(step),
                    default_value=int(lower),
                )
            )
            continue

        lower_decimal, unit = _parse_decimal_unit(variable.lower)
        upper_decimal, upper_unit = _parse_decimal_unit(variable.upper)
        step_decimal, step_unit = _parse_decimal_unit(variable.step)
        if upper_unit != unit or step_unit != unit:
            raise ValueError(f"variable {variable.name} uses inconsistent units")
        effective_upper = _effective_continuous_upper(
            lower_decimal,
            upper_decimal,
            step_decimal,
        )
        space.add_variable(
            space_module.Real(
                variable.name,
                float(lower_decimal),
                float(effective_upper),
                q=float(step),
                default_value=float(lower_decimal),
            )
        )
    return space


def _values_from_parameters(
    variables: VariablesConfig,
    parameters: dict[str, str],
) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    for variable in variables.variables:
        if variable.name not in parameters:
            raise ValueError(f"continuation trace missing parameter {variable.name}")
        if variable.kind == VariableKind.INTEGER:
            values[variable.name] = int(_numeric_value(parameters[variable.name]))
        else:
            values[variable.name] = _numeric_value(parameters[variable.name])
    return values


def _build_openbox_advisor(
    variables: VariablesConfig,
    seed: int,
    *,
    num_constraints: int = 0,
) -> object:
    Advisor, _Observation, sp = _load_openbox()
    space = _build_openbox_space(variables, sp)
    return Advisor(
        space,
        num_objectives=1,
        num_constraints=num_constraints,
        random_state=seed,
    )


def _create_advisor(
    project_dir: Path,
    variables: VariablesConfig,
    seed: int,
    *,
    advisor_factory: AdvisorFactory | None,
    num_constraints: int,
    surrogate_type: str | None,
    acq_type: str | None,
    acq_optimizer_type: str | None,
) -> tuple[object, Callable[..., object], Callable[[dict[str, str]], object]]:
    if advisor_factory is not None:
        return (
            advisor_factory(_build_openbox_space(variables), seed),
            FakeOpenBoxObservation,
            lambda parameters: _values_from_parameters(variables, parameters),
        )

    Advisor, Observation, sp = _load_openbox()
    space = _build_openbox_space(variables, sp)
    output_dir = project_dir / "reports" / "openbox_workdir"
    output_dir.mkdir(parents=True, exist_ok=True)
    return (
        Advisor(
            space,
            num_objectives=1,
            num_constraints=num_constraints,
            initial_trials=max(2 * len(variables.variables), 1),
            init_strategy="sobol",
            surrogate_type=surrogate_type or "auto",
            acq_type=acq_type or "auto",
            acq_optimizer_type=acq_optimizer_type or "auto",
            task_id="hermes_openbox_real",
            output_dir=str(output_dir),
            random_state=seed,
        ),
        Observation,
        lambda parameters: sp.Configuration(
            space,
            values=_values_from_parameters(variables, parameters),
        ),
    )


def _effective_continuous_upper(
    lower: Decimal,
    upper: Decimal,
    step: Decimal,
) -> Decimal:
    max_offset = int((upper - lower) / step)
    return lower + Decimal(max_offset) * step


def _prepare_unique_batch(
    *,
    advisor: object,
    variables: VariablesConfig,
    seen_keys: set[tuple[tuple[str, str], ...]],
    batch_id: str,
    batch_size: int,
    evaluation_offset: int,
    run_evaluation_offset: int,
    run_offset: int,
    run_prefix: str,
) -> OpenBoxBatchResult:
    candidates: list[OpenBoxPreparedSuggestion] = []
    duplicate_replacements = 0
    attempts = 0
    max_attempts = max(batch_size * 30, 100)
    while len(candidates) < batch_size and attempts < max_attempts:
        attempts += 1
        for suggestion in _get_suggestions(advisor, batch_size - len(candidates)):
            values = _suggestion_dict(suggestion)
            raw_x = _raw_values_from_suggestion(variables, values)
            parameters = quantize_candidate(variables, raw_x)
            key = tuple(sorted(parameters.items()))
            if key in seen_keys:
                duplicate_replacements += 1
                continue
            replacement_issues = (
                ["duplicate candidate replaced"] if duplicate_replacements else []
            )
            seen_keys.add(key)
            evaluation_index = evaluation_offset + len(candidates) + 1
            run_index = run_offset + run_evaluation_offset + len(candidates) + 1
            candidates.append(
                OpenBoxPreparedSuggestion(
                    config=suggestion,
                    values=values,
                    raw_x=raw_x,
                    parameters=parameters,
                    candidate_id=f"candidate_{evaluation_index:06d}",
                    run_id=f"{run_prefix}_{run_index:03d}",
                    batch_id=batch_id,
                    batch_slot=len(candidates) + 1,
                    batch_size=batch_size,
                    replacement_issues=replacement_issues,
                )
            )
            if len(candidates) == batch_size:
                break
    if len(candidates) != batch_size:
        raise ValueError(
            "OpenBox duplicate replacement exhausted: "
            f"requested={batch_size} prepared={len(candidates)} attempts={attempts}"
        )
    return OpenBoxBatchResult(
        candidates=candidates,
        duplicate_replacements=duplicate_replacements,
    )


def _next_run_offset(project_dir: Path, run_prefix: str) -> int:
    root = project_dir / "runs" / "real"
    next_index = 1
    while (root / f"{run_prefix}_{next_index:03d}").exists():
        next_index += 1
    return next_index - 1


def _fake_batch_evaluator(
    candidates: list[NativeTurboBatchCandidate],
) -> list[NativeTurboObservation]:
    observations: list[NativeTurboObservation] = []
    for candidate in candidates:
        metric_observation = _fake_inverter_metrics(candidate.parameters)
        observations.append(
            NativeTurboObservation(
                status="recorded",
                metrics=metric_observation.metrics,
                issues=metric_observation.issues,
            )
        )
    return observations


def make_openbox_real_candidate_batch_evaluator(
    project_dir: Path,
    *,
    cadence_cshrc: Path | None,
    max_workers: int,
    adapter: Callable[..., object] | None = None,
    allow_optimizer_continuation: bool = False,
) -> BatchEvaluator:
    project_dir = Path(project_dir)
    selected_max_workers = max(1, max_workers)

    def evaluate(
        candidates: list[NativeTurboBatchCandidate],
    ) -> list[NativeTurboObservation]:
        for candidate in candidates:
            prepare_explicit_candidate_real_run(
                project_dir,
                candidate_id=candidate.candidate_id,
                source=OPENBOX_SOURCE,
                parameters=candidate.parameters,
                run_id=candidate.run_id,
                metadata={
                    "optimizer": "openbox",
                    "batch_id": candidate.batch_id,
                    "batch_slot": candidate.batch_slot,
                    "selection_phase": candidate.selection_phase,
                    "ask_tell": True,
                },
                allow_unresolved_batch_runs=True,
                allow_optimizer_continuation=allow_optimizer_continuation,
            )

        observations: list[NativeTurboObservation | None] = [None] * len(candidates)
        with ThreadPoolExecutor(max_workers=selected_max_workers) as executor:
            future_to_index = {
                executor.submit(
                    execute_and_check_real_candidate,
                    project_dir,
                    run_id=candidate.run_id,
                    cadence_cshrc=cadence_cshrc,
                    adapter=adapter,
                ): index
                for index, candidate in enumerate(candidates)
            }
            for future in as_completed(future_to_index):
                observations[future_to_index[future]] = future.result()

        finalized: list[NativeTurboObservation] = []
        for candidate, observation in zip(candidates, observations, strict=True):
            if observation is None:
                raise RuntimeError("OpenBox batch candidate was not evaluated")
            if observation.status != "checked":
                finalized.append(observation)
                continue
            record_report = record_real_result(project_dir, run_id=candidate.run_id)
            if record_report.status.value != "pass":
                finalized.append(
                    NativeTurboObservation(
                        status="record_failed",
                        issues=record_report.issues,
                        result_manifest=observation.result_manifest,
                        metric_result_manifest=observation.metric_result_manifest,
                    )
                )
                continue
            finalized.append(
                NativeTurboObservation(
                    status="recorded",
                    metrics=observation.metrics,
                    result_manifest=observation.result_manifest,
                    metric_result_manifest=observation.metric_result_manifest,
                )
            )
        return finalized

    return evaluate


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
        if variable.name not in suggestion:
            raise ValueError(f"OpenBox suggestion missing variable {variable.name}")
        raw_values.append(float(suggestion[variable.name]))
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
    *,
    metrics_config: MetricsConfig,
    trace: NativeTurboEvaluationTrace,
    config: object,
    observation_factory: Callable[..., object],
) -> object:
    constraints = _constraint_residuals_for_metrics(metrics_config, trace.metrics)
    try:
        return observation_factory(
            config=config,
            objectives=[trace.objective],
            constraints=constraints,
            extra_info={
                "status": trace.status,
                "run_id": trace.run_id,
                "candidate_id": f"candidate_{trace.evaluation_index:06d}",
            },
        )
    except TypeError:
        return observation_factory(
            objectives=[trace.objective],
            constraints=constraints,
            config=_suggestion_dict(config),
        )


def _trace_from_observation(
    *,
    contract_metrics: MetricsConfig,
    contract_optimizer: object,
    candidate: OpenBoxPreparedSuggestion,
    observation: NativeTurboObservation,
    evaluation_index: int,
    parallel_jobs: int,
    threads_per_run: int | None,
) -> NativeTurboEvaluationTrace:
    if observation.metrics is not None and observation.status == "recorded":
        objective_eval = evaluate_candidate_objective(
            contract_metrics,
            contract_optimizer,
            observation.metrics,
        )
        status = objective_eval.status
        objective = objective_eval.objective
        fom = objective_eval.fom
        constraint_penalty = objective_eval.constraint_penalty
        issues = [
            *candidate.replacement_issues,
            *objective_eval.issues,
            *(observation.issues or []),
        ]
    else:
        status = observation.status if observation.status != "checked" else "metric_failed"
        objective = contract_optimizer.optimizer.failure_penalty
        fom = None
        constraint_penalty = 0.0
        issues = [*candidate.replacement_issues, *(observation.issues or [])]

    return NativeTurboEvaluationTrace(
        evaluation_index=evaluation_index,
        run_id=candidate.run_id,
        selection_phase=OPENBOX_BATCH_PHASE,
        raw_x=candidate.raw_x,
        parameters=candidate.parameters,
        status=status,
        objective=objective,
        fom=fom,
        constraint_penalty=constraint_penalty,
        metrics=observation.metrics,
        result_manifest=observation.result_manifest,
        metric_result_manifest=observation.metric_result_manifest,
        issues=issues,
        batch_id=candidate.batch_id,
        batch_slot=candidate.batch_slot,
        batch_size=candidate.batch_size,
        batch_worker_count=min(candidate.batch_size, parallel_jobs),
        max_parallel_jobs=parallel_jobs,
        threads_per_run=threads_per_run,
        parallel_jobs=parallel_jobs,
    )


def _constraint_residuals_for_metrics(
    metrics_config: MetricsConfig,
    metrics: dict[str, float] | None,
) -> list[float]:
    if metrics is None:
        return [1.0 for _constraint in metrics_config.constraints]
    residuals: list[float] = []
    for constraint in metrics_config.constraints:
        if constraint.metric not in metrics:
            residuals.append(1.0)
            continue
        value = float(metrics[constraint.metric])
        threshold = _numeric_value(constraint.value)
        if constraint.op in (ConstraintOp.LT, ConstraintOp.LE):
            residuals.append(value - threshold)
        elif constraint.op in (ConstraintOp.GT, ConstraintOp.GE):
            residuals.append(threshold - value)
        else:
            residuals.append(1.0)
    return residuals


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
