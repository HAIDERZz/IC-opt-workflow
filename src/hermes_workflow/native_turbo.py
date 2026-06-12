from __future__ import annotations

import json
import math
import os
import random
import shlex
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Sequence

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.optimizer_resources import optimizer_cpu_thread_limits
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
from hermes_workflow.real_run_recovery import resolve_real_run_failure
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.reports import RealRunResultStatus
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

DEFAULT_TURBO_PATH = Path(
    os.environ.get(
        "TURBO_HOME",
        str(Path(__file__).resolve().parents[2] / "vendor" / "TuRBO"),
    )
)
REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
EVALUATIONS_RELATIVE = Path("reports/native_turbo_optimizer_evaluations.jsonl")
NATIVE_TURBO_SOURCE = "native_turbo_optimizer"
INITIALIZATION_PHASE = "initialization"
TRUST_REGION_PHASE = "turbo_trust_region"
DUPLICATE_SKIPPED = "duplicate_candidate_skipped"
WORKFLOW_FAILURE_STATUSES = {"adapter_failed", "real_check_failed", "record_failed"}
DEFAULT_WORKFLOW_FAILURE_LIMIT = 3


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
class NativeTurboObservation:
    metrics: dict[str, float] | None = None
    status: str = "recorded"
    issues: list[str] | None = None
    result_manifest: str | None = None
    metric_result_manifest: str | None = None


@dataclass(frozen=True)
class NativeTurboBatchCandidate:
    evaluation_index: int
    run_id: str
    candidate_id: str
    batch_id: str
    batch_slot: int
    batch_size: int
    selection_phase: str
    raw_x: list[float]
    parameters: dict[str, str]
    replacement_issues: list[str]


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
    metrics: dict[str, float] | None
    result_manifest: str | None
    metric_result_manifest: str | None
    issues: list[str]
    batch_id: str | None = None
    batch_slot: int | None = None
    batch_size: int | None = None
    batch_worker_count: int | None = None
    max_parallel_jobs: int | None = None
    threads_per_run: int | None = None
    parallel_jobs: int | None = None


@dataclass(frozen=True)
class NativeTurboRunResult:
    evaluation_count: int
    traces: list[NativeTurboEvaluationTrace]
    best_trace: NativeTurboEvaluationTrace | None
    report_path: Path | None = None
    evaluations_path: Path | None = None


Evaluator = Callable[[dict[str, str]], NativeTurboObservation]
BatchEvaluator = Callable[
    [list[NativeTurboBatchCandidate]],
    list[NativeTurboObservation],
]
Adapter = Callable[[Path], None]


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
            max_offset = (upper - lower) // step
            value = lower + _clamp_int(offset, 0, max_offset) * step
            parameters[variable.name] = str(value)
        else:
            lower, unit = _parse_decimal_unit(variable.lower)
            upper, upper_unit = _parse_decimal_unit(variable.upper)
            step, step_unit = _parse_decimal_unit(variable.step)
            if upper_unit != unit or step_unit != unit:
                raise ValueError(f"variable {variable.name} uses inconsistent units")
            offset = round((Decimal(str(raw)) - lower) / step)
            max_offset = int((upper - lower) / step)
            value = lower + Decimal(_clamp_int(offset, 0, max_offset)) * step
            parameters[variable.name] = f"{value.normalize():f}{unit}"
    return parameters


class NativeTurboRunner:
    def __init__(
        self,
        *,
        variables: VariablesConfig,
        metrics: MetricsConfig,
        optimizer: OptimizerConfig,
        evaluator: Evaluator,
        turbo_factory: Callable[..., object] | None = None,
        max_evals: int | None = None,
        replacement_attempts: int = 32,
        workflow_failure_limit: int = DEFAULT_WORKFLOW_FAILURE_LIMIT,
    ) -> None:
        self.variables = variables
        self.metrics = metrics
        self.optimizer = optimizer
        self.evaluator = evaluator
        self.turbo_factory = turbo_factory or _default_turbo_factory
        self.max_evals = max_evals or optimizer.optimizer.max_evaluations
        self.optimizer_cpu_threads = optimizer.optimizer.optimizer_cpu_threads
        self.replacement_attempts = replacement_attempts
        self.workflow_failure_limit = workflow_failure_limit
        self.traces: list[NativeTurboEvaluationTrace] = []
        self._used_keys: set[tuple[tuple[str, str], ...]] = set()
        self._rng = random.Random(optimizer.optimizer.random_seed)
        self._consecutive_workflow_failures = 0

    def run(self) -> NativeTurboRunResult:
        lb, ub = _raw_bounds(self.variables)
        n_params = len(self.variables.variables)
        n_init = 2 * n_params
        with optimizer_cpu_thread_limits(
            self.optimizer_cpu_threads,
            set_environment=False,
        ):
            turbo = self.turbo_factory(
                f=self._objective,
                lb=lb,
                ub=ub,
                n_init=n_init,
                max_evals=self.max_evals,
                batch_size=1,
                verbose=False,
            )
            turbo.optimize()
        return NativeTurboRunResult(
            evaluation_count=len(self.traces),
            traces=list(self.traces),
            best_trace=_best_trace(self.traces),
        )

    def _objective(self, raw_values: Sequence[float]) -> float:
        evaluation_index = len(self.traces) + 1
        phase = (
            INITIALIZATION_PHASE
            if evaluation_index <= 2 * len(self.variables.variables)
            else TRUST_REGION_PHASE
        )
        raw_x = [float(value) for value in raw_values]
        resolved = self._resolve_unique_candidate(raw_x)
        if resolved is None:
            objective = self.optimizer.optimizer.failure_penalty
            self.traces.append(
                NativeTurboEvaluationTrace(
                    evaluation_index=evaluation_index,
                    run_id=f"real_{evaluation_index:03d}",
                    selection_phase=phase,
                    raw_x=raw_x,
                    parameters=quantize_candidate(self.variables, raw_x),
                    status=DUPLICATE_SKIPPED,
                    objective=objective,
                    fom=None,
                    constraint_penalty=0.0,
                    metrics=None,
                    result_manifest=None,
                    metric_result_manifest=None,
                    issues=["duplicate candidate skipped"],
                )
            )
            return objective

        actual_raw, parameters, replacement_issues = resolved
        observation = self.evaluator(parameters)
        objective_eval = _objective_evaluation_for_observation(
            self.metrics,
            self.optimizer,
            observation,
        )
        issues = [*replacement_issues, *objective_eval.issues, *(observation.issues or [])]
        trace = NativeTurboEvaluationTrace(
            evaluation_index=evaluation_index,
            run_id=f"real_{evaluation_index:03d}",
            selection_phase=phase,
            raw_x=actual_raw,
            parameters=parameters,
            status=(
                observation.status
                if observation.metrics is None and observation.status != "recorded"
                else objective_eval.status
            ),
            objective=objective_eval.objective,
            fom=objective_eval.fom,
            constraint_penalty=objective_eval.constraint_penalty,
            metrics=observation.metrics,
            result_manifest=observation.result_manifest,
            metric_result_manifest=observation.metric_result_manifest,
            issues=issues,
        )
        self.traces.append(trace)
        self._raise_after_repeated_workflow_failure(trace)
        return objective_eval.objective

    def _raise_after_repeated_workflow_failure(
        self,
        trace: NativeTurboEvaluationTrace,
    ) -> None:
        if trace.status not in WORKFLOW_FAILURE_STATUSES:
            self._consecutive_workflow_failures = 0
            return
        self._consecutive_workflow_failures += 1
        if self._consecutive_workflow_failures < self.workflow_failure_limit:
            return
        issues = "; ".join(trace.issues) if trace.issues else trace.status
        raise RuntimeError(
            "workflow-level failure limit reached "
            f"after {self._consecutive_workflow_failures} consecutive failures: "
            f"{issues}"
        )

    def _resolve_unique_candidate(
        self,
        raw_values: list[float],
    ) -> tuple[list[float], dict[str, str], list[str]] | None:
        for candidate_raw, issues in self._candidate_replacements(raw_values):
            parameters = quantize_candidate(self.variables, candidate_raw)
            key = _parameter_key(parameters)
            if key in self._used_keys:
                continue
            self._used_keys.add(key)
            return candidate_raw, parameters, issues
        return None

    def _candidate_replacements(
        self,
        raw_values: list[float],
    ) -> list[tuple[list[float], list[str]]]:
        replacements: list[tuple[list[float], list[str]]] = [(raw_values, [])]
        if self.replacement_attempts <= 0:
            return replacements
        lb, ub = _raw_bounds(self.variables)
        steps = _raw_steps(self.variables)
        for index, step in enumerate(steps):
            for direction in (1.0, -1.0):
                candidate = list(raw_values)
                candidate[index] = max(lb[index], min(ub[index], candidate[index] + direction * step))
                replacements.append((candidate, ["duplicate candidate replaced"]))
                if len(replacements) > self.replacement_attempts:
                    return replacements
        while len(replacements) <= self.replacement_attempts:
            replacements.append(
                (_random_grid_raw(self.variables, self._rng), ["duplicate candidate replaced"])
            )
        return replacements


class NativeTurboBatchRunner(NativeTurboRunner):
    def __init__(
        self,
        *,
        variables: VariablesConfig,
        metrics: MetricsConfig,
        optimizer: OptimizerConfig,
        batch_evaluator: BatchEvaluator,
        batch_turbo_factory: Callable[..., object],
        max_evals: int | None = None,
        replacement_attempts: int = 32,
        workflow_failure_limit: int = DEFAULT_WORKFLOW_FAILURE_LIMIT,
        parallel_jobs: int = 1,
        threads_per_run: int | None = None,
    ) -> None:
        def unused_scalar_evaluator(
            _parameters: dict[str, str],
        ) -> NativeTurboObservation:
            raise RuntimeError("batch runner does not use scalar evaluator")

        super().__init__(
            variables=variables,
            metrics=metrics,
            optimizer=optimizer,
            evaluator=unused_scalar_evaluator,
            turbo_factory=batch_turbo_factory,
            max_evals=max_evals,
            replacement_attempts=replacement_attempts,
            workflow_failure_limit=workflow_failure_limit,
        )
        self.batch_evaluator = batch_evaluator
        self.parallel_jobs = parallel_jobs
        self.threads_per_run = threads_per_run
        self._batch_count = 0

    def run(self) -> NativeTurboRunResult:
        lb, ub = _raw_bounds(self.variables)
        n_params = len(self.variables.variables)
        n_init = 2 * n_params
        with optimizer_cpu_thread_limits(
            self.optimizer_cpu_threads,
            set_environment=False,
        ):
            turbo = self.turbo_factory(
                f_batch=self._objective_batch,
                lb=lb,
                ub=ub,
                n_init=n_init,
                max_evals=self.max_evals,
                batch_size=self.optimizer.optimizer.batch_size,
                verbose=False,
            )
            turbo.optimize()
        return NativeTurboRunResult(
            evaluation_count=len(self.traces),
            traces=list(self.traces),
            best_trace=_best_trace(self.traces),
        )

    def _objective_batch(
        self,
        raw_batch: Sequence[Sequence[float]],
        *,
        selection_phase: str,
    ) -> list[float]:
        remaining = self.max_evals - len(self.traces)
        if remaining <= 0:
            return []
        selected_raw_batch = list(raw_batch[:remaining])
        self._batch_count += 1
        batch_id = f"batch_{self._batch_count:03d}"
        batch_size = len(selected_raw_batch)
        batch_worker_count = min(self.optimizer.optimizer.batch_size, self.parallel_jobs)
        slots: list[NativeTurboBatchCandidate | NativeTurboEvaluationTrace] = []
        candidates: list[NativeTurboBatchCandidate] = []

        for slot_index, raw_values in enumerate(selected_raw_batch, start=1):
            evaluation_index = len(self.traces) + slot_index
            raw_x = [float(value) for value in raw_values]
            resolved = self._resolve_unique_candidate(raw_x)
            if resolved is None:
                slots.append(
                    NativeTurboEvaluationTrace(
                        evaluation_index=evaluation_index,
                        run_id=f"real_{evaluation_index:03d}",
                        selection_phase=selection_phase,
                        raw_x=raw_x,
                        parameters=quantize_candidate(self.variables, raw_x),
                        status=DUPLICATE_SKIPPED,
                        objective=self.optimizer.optimizer.failure_penalty,
                        fom=None,
                        constraint_penalty=0.0,
                        metrics=None,
                        result_manifest=None,
                        metric_result_manifest=None,
                        issues=["duplicate candidate skipped"],
                        batch_id=batch_id,
                        batch_slot=slot_index,
                        batch_size=batch_size,
                        batch_worker_count=batch_worker_count,
                        max_parallel_jobs=self.parallel_jobs,
                        threads_per_run=self.threads_per_run,
                        parallel_jobs=self.parallel_jobs,
                    )
                )
                continue

            actual_raw, parameters, replacement_issues = resolved
            candidate = NativeTurboBatchCandidate(
                evaluation_index=evaluation_index,
                run_id=f"real_{evaluation_index:03d}",
                candidate_id=f"candidate_{evaluation_index:06d}",
                batch_id=batch_id,
                batch_slot=slot_index,
                batch_size=batch_size,
                selection_phase=selection_phase,
                raw_x=actual_raw,
                parameters=parameters,
                replacement_issues=replacement_issues,
            )
            candidates.append(candidate)
            slots.append(candidate)

        observations = self.batch_evaluator(candidates) if candidates else []
        if len(observations) != len(candidates):
            raise RuntimeError("batch evaluator returned an unexpected observation count")
        observation_by_index = {
            candidate.evaluation_index: observation
            for candidate, observation in zip(candidates, observations, strict=True)
        }
        objectives: list[float] = []
        for slot in slots:
            if isinstance(slot, NativeTurboEvaluationTrace):
                trace = slot
            else:
                observation = observation_by_index[slot.evaluation_index]
                objective_eval = _objective_evaluation_for_observation(
                    self.metrics,
                    self.optimizer,
                    observation,
                )
                trace = NativeTurboEvaluationTrace(
                    evaluation_index=slot.evaluation_index,
                    run_id=slot.run_id,
                    selection_phase=slot.selection_phase,
                    raw_x=slot.raw_x,
                    parameters=slot.parameters,
                    status=(
                        observation.status
                        if observation.metrics is None and observation.status != "recorded"
                        else objective_eval.status
                    ),
                    objective=objective_eval.objective,
                    fom=objective_eval.fom,
                    constraint_penalty=objective_eval.constraint_penalty,
                    metrics=observation.metrics,
                    result_manifest=observation.result_manifest,
                    metric_result_manifest=observation.metric_result_manifest,
                    issues=[
                        *slot.replacement_issues,
                        *objective_eval.issues,
                        *(observation.issues or []),
                    ],
                    batch_id=slot.batch_id,
                    batch_slot=slot.batch_slot,
                    batch_size=slot.batch_size,
                    batch_worker_count=batch_worker_count,
                    max_parallel_jobs=self.parallel_jobs,
                    threads_per_run=self.threads_per_run,
                    parallel_jobs=self.parallel_jobs,
                )
            self.traces.append(trace)
            self._raise_after_repeated_workflow_failure(trace)
            objectives.append(trace.objective)
        return objectives

def run_native_turbo_optimization(
    project_dir: Path,
    *,
    max_evals: int | None = None,
    cadence_cshrc: Path | None = None,
    evaluator: Evaluator | None = None,
    turbo_factory: Callable[..., object] | None = None,
) -> NativeTurboRunResult:
    project_dir = Path(project_dir)
    contract = load_native_turbo_contract(project_dir)

    if evaluator is None:
        def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
            evaluation_index = len(runner.traces) + 1
            return evaluate_real_candidate(
                project_dir,
                candidate_id=f"candidate_{evaluation_index:06d}",
                parameters=parameters,
                run_id=f"real_{evaluation_index:03d}",
                cadence_cshrc=cadence_cshrc,
            )

    runner = NativeTurboRunner(
        variables=contract.variables,
        metrics=contract.metrics,
        optimizer=contract.optimizer,
        evaluator=evaluator,
        turbo_factory=turbo_factory,
        max_evals=max_evals,
    )
    result = runner.run()
    report_path, evaluations_path = write_native_turbo_reports(project_dir, result)
    return NativeTurboRunResult(
        evaluation_count=result.evaluation_count,
        traces=result.traces,
        best_trace=result.best_trace,
        report_path=report_path,
        evaluations_path=evaluations_path,
    )


def run_batch_native_turbo_optimization(
    project_dir: Path,
    *,
    max_evals: int | None = None,
    cadence_cshrc: Path | None = None,
    batch_evaluator: BatchEvaluator | None = None,
    batch_turbo_factory: Callable[..., object] | None = None,
    parallel_jobs: int | None = None,
    threads_per_run: int | None = None,
) -> NativeTurboRunResult:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    selected_parallel_jobs = parallel_jobs or bundle.spectre.spectre.parallel_jobs
    selected_threads_per_run = threads_per_run or bundle.spectre.spectre.threads_per_run
    if batch_evaluator is None:
        batch_evaluator = make_real_candidate_batch_evaluator(
            project_dir,
            cadence_cshrc=cadence_cshrc,
            max_workers=min(
                bundle.optimizer.optimizer.batch_size,
                selected_parallel_jobs,
            ),
        )

    runner = NativeTurboBatchRunner(
        variables=bundle.variables,
        metrics=bundle.metrics,
        optimizer=bundle.optimizer,
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=batch_turbo_factory or _default_batch_turbo_factory,
        max_evals=max_evals,
        parallel_jobs=selected_parallel_jobs,
        threads_per_run=selected_threads_per_run,
    )
    result = runner.run()
    report_path, evaluations_path = write_native_turbo_reports(project_dir, result)
    return NativeTurboRunResult(
        evaluation_count=result.evaluation_count,
        traces=result.traces,
        best_trace=result.best_trace,
        report_path=report_path,
        evaluations_path=evaluations_path,
    )


def evaluate_real_candidate(
    project_dir: Path,
    *,
    candidate_id: str,
    parameters: dict[str, str],
    run_id: str,
    cadence_cshrc: Path | None = None,
    adapter: Callable[..., object] | None = None,
) -> NativeTurboObservation:
    project_dir = Path(project_dir)
    prepare_explicit_candidate_real_run(
        project_dir,
        candidate_id=candidate_id,
        source=NATIVE_TURBO_SOURCE,
        parameters=parameters,
        run_id=run_id,
        metadata={"optimizer": "turbo"},
    )
    observation = execute_and_check_real_candidate(
        project_dir,
        run_id=run_id,
        cadence_cshrc=cadence_cshrc,
        adapter=adapter,
    )
    if observation.status != "checked":
        return observation
    record_report = record_real_result(project_dir, run_id=run_id)
    if record_report.status.value != "pass":
        _try_abandon_candidate(project_dir, run_id, "record-real-result failed")
        return NativeTurboObservation(
            status="record_failed",
            issues=record_report.issues,
            result_manifest=observation.result_manifest,
            metric_result_manifest=observation.metric_result_manifest,
        )
    return NativeTurboObservation(
        status="recorded",
        metrics=observation.metrics,
        result_manifest=observation.result_manifest,
        metric_result_manifest=observation.metric_result_manifest,
    )


def execute_and_check_real_candidate(
    project_dir: Path,
    *,
    run_id: str,
    cadence_cshrc: Path | None = None,
    adapter: Callable[..., object] | None = None,
) -> NativeTurboObservation:
    selected_adapter = adapter or _run_default_adapter
    adapter_error: str | None = None
    try:
        selected_adapter(project_dir, run_id=run_id, cadence_cshrc=cadence_cshrc)
    except Exception as exc:
        adapter_error = str(exc)

    real_report = check_real_run(project_dir, run_id=run_id, persist_report=False)
    if real_report.status.value != "pass":
        _try_abandon_candidate(project_dir, run_id, "real-run check failed")
        issues = real_report.issues or ([adapter_error] if adapter_error else [])
        return NativeTurboObservation(
            status="real_check_failed",
            issues=issues,
            result_manifest=f"runs/real/{run_id}/result_manifest.json",
        )
    if real_report.result_status != RealRunResultStatus.SUCCEEDED:
        # A failed result manifest means the real tool/transport failed even if
        # the manifest exists, so classify before metric extraction.
        issues = real_report.issues or ([adapter_error] if adapter_error else [])
        status_label = (
            real_report.result_status.value
            if real_report.result_status is not None
            else "missing"
        )
        issues = issues + [f"result_status is {status_label}"]
        _try_abandon_candidate(project_dir, run_id, "real-run check failed")
        return NativeTurboObservation(
            status="real_check_failed",
            issues=issues,
            result_manifest=real_report.result_manifest,
        )
    metric_report = check_metric_results(
        project_dir,
        run_id=run_id,
        persist_report=False,
    )
    if metric_report.status.value != "pass":
        _try_abandon_candidate(project_dir, run_id, "metric-result check failed")
        return NativeTurboObservation(
            status="metric_check_failed",
            issues=metric_report.issues,
            result_manifest=real_report.result_manifest,
            metric_result_manifest=metric_report.metric_result_manifest,
        )
    metrics = {
        name: float(checked.value)
        for name, checked in metric_report.metrics.items()
        if checked.value is not None and math.isfinite(float(checked.value))
    }
    if len(metrics) != len(metric_report.metrics):
        return NativeTurboObservation(
            status="metric_failed",
            issues=["metric result contains non-finite scalar"],
            result_manifest=real_report.result_manifest,
            metric_result_manifest=metric_report.metric_result_manifest,
        )
    return NativeTurboObservation(
        status="checked",
        metrics=metrics,
        result_manifest=real_report.result_manifest,
        metric_result_manifest=metric_report.metric_result_manifest,
    )


def make_real_candidate_batch_evaluator(
    project_dir: Path,
    *,
    cadence_cshrc: Path | None,
    max_workers: int,
    adapter: Callable[..., object] | None = None,
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
                source=NATIVE_TURBO_SOURCE,
                parameters=candidate.parameters,
                run_id=candidate.run_id,
                metadata={
                    "optimizer": "turbo",
                    "batch_id": candidate.batch_id,
                    "batch_slot": candidate.batch_slot,
                    "selection_phase": candidate.selection_phase,
                },
                allow_unresolved_batch_runs=True,
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
                raise RuntimeError("batch candidate was not evaluated")
            if observation.status != "checked":
                finalized.append(observation)
                continue
            record_report = record_real_result(project_dir, run_id=candidate.run_id)
            if record_report.status.value != "pass":
                _try_abandon_candidate(
                    project_dir,
                    candidate.run_id,
                    "record-real-result failed",
                )
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


def _try_abandon_candidate(project_dir: Path, run_id: str, reason: str) -> None:
    try:
        resolve_real_run_failure(
            project_dir,
            run_id=run_id,
            decision="abandon_candidate",
            reason=reason,
        )
    except Exception:
        return


def write_native_turbo_reports(
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
        "evaluation_count": result.evaluation_count,
        "best_candidate": (
            asdict(result.best_trace) if result.best_trace is not None else None
        ),
        "evaluations": str(EVALUATIONS_RELATIVE),
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


def _objective_evaluation_for_observation(
    metrics_config: MetricsConfig,
    optimizer_config: OptimizerConfig,
    observation: NativeTurboObservation,
) -> ObjectiveEvaluation:
    if observation.metrics is None:
        return ObjectiveEvaluation(
            status=observation.status,
            objective=optimizer_config.optimizer.failure_penalty,
            fom=None,
            constraints_passed=False,
            constraint_penalty=0.0,
            issues=observation.issues or [observation.status],
        )
    return evaluate_candidate_objective(
        metrics_config,
        optimizer_config,
        observation.metrics,
    )


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


def _raw_bounds(variables_config: VariablesConfig):
    import numpy as np

    lower: list[float] = []
    upper: list[float] = []
    for variable in variables_config.variables:
        if variable.kind == VariableKind.INTEGER:
            lower.append(float(variable.lower))
            upper.append(float(variable.upper))
        else:
            low, _unit = _parse_decimal_unit(variable.lower)
            high, _unit = _parse_decimal_unit(variable.upper)
            lower.append(float(low))
            upper.append(float(high))
    return np.array(lower, dtype=float), np.array(upper, dtype=float)


def _raw_steps(variables_config: VariablesConfig) -> list[float]:
    steps: list[float] = []
    for variable in variables_config.variables:
        if variable.kind == VariableKind.INTEGER:
            steps.append(float(variable.step))
        else:
            step, _unit = _parse_decimal_unit(variable.step)
            steps.append(float(step))
    return steps


def _random_grid_raw(
    variables_config: VariablesConfig,
    rng: random.Random,
) -> list[float]:
    values: list[float] = []
    for variable in variables_config.variables:
        if variable.kind == VariableKind.INTEGER:
            lower = int(variable.lower)
            upper = int(variable.upper)
            step = int(variable.step)
            count = (upper - lower) // step
            values.append(float(lower + rng.randrange(count + 1) * step))
        else:
            lower, _unit = _parse_decimal_unit(variable.lower)
            upper, _unit = _parse_decimal_unit(variable.upper)
            step, _unit = _parse_decimal_unit(variable.step)
            count = int((upper - lower) / step)
            values.append(float(lower + Decimal(rng.randrange(count + 1)) * step))
    return values


def _parameter_key(parameters: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(parameters.items()))


def _best_trace(
    traces: list[NativeTurboEvaluationTrace],
) -> NativeTurboEvaluationTrace | None:
    feasible = [trace for trace in traces if trace.status == "feasible"]
    if feasible:
        return min(feasible, key=lambda trace: trace.objective)
    finite = [trace for trace in traces if math.isfinite(trace.objective)]
    return min(finite, key=lambda trace: trace.objective) if finite else None


def _default_turbo_factory(**kwargs):
    if str(DEFAULT_TURBO_PATH) not in sys.path:
        sys.path.insert(0, str(DEFAULT_TURBO_PATH))
    from turbo import Turbo1

    return Turbo1(**kwargs)


def _default_batch_turbo_factory(**kwargs):
    if str(DEFAULT_TURBO_PATH) not in sys.path:
        sys.path.insert(0, str(DEFAULT_TURBO_PATH))
    import numpy as np
    from turbo import Turbo1
    from turbo.utils import from_unit_cube, latin_hypercube, to_unit_cube

    f_batch = kwargs.pop("f_batch")

    class BatchTurbo1(Turbo1):
        def __init__(self, *, f_batch, **turbo_kwargs) -> None:
            self.f_batch = f_batch
            super().__init__(f=lambda _x: math.inf, **turbo_kwargs)

        def _evaluate_rows(self, rows, *, selection_phase: str):
            values = self.f_batch(
                [list(row) for row in rows],
                selection_phase=selection_phase,
            )
            if len(values) != len(rows):
                raise RuntimeError("batch objective returned an unexpected value count")
            return np.array([[float(value)] for value in values])

        def optimize(self):
            while self.n_evals < self.max_evals:
                if len(self._fX) > 0 and self.verbose:
                    n_evals, fbest = self.n_evals, self._fX.min()
                    print(f"{n_evals}) Restarting with fbest = {fbest:.4}")
                    sys.stdout.flush()

                self._restart()

                init_count = min(self.n_init, self.max_evals - self.n_evals)
                X_init = latin_hypercube(init_count, self.dim)
                X_init = from_unit_cube(X_init, self.lb, self.ub)
                init_chunks = [
                    self._evaluate_rows(
                        X_init[start : start + self.batch_size],
                        selection_phase=INITIALIZATION_PHASE,
                    )
                    for start in range(0, init_count, self.batch_size)
                ]
                fX_init = np.vstack(init_chunks)

                self.n_evals += init_count
                self._X = deepcopy(X_init)
                self._fX = deepcopy(fX_init)

                self.X = np.vstack((self.X, deepcopy(X_init)))
                self.fX = np.vstack((self.fX, deepcopy(fX_init)))

                if self.verbose:
                    fbest = self._fX.min()
                    print(f"Starting from fbest = {fbest:.4}")
                    sys.stdout.flush()

                while self.n_evals < self.max_evals and self.length >= self.length_min:
                    X = to_unit_cube(deepcopy(self._X), self.lb, self.ub)
                    fX = deepcopy(self._fX).ravel()
                    current_batch_size = min(self.batch_size, self.max_evals - self.n_evals)
                    original_batch_size = self.batch_size
                    self.batch_size = current_batch_size
                    try:
                        X_cand, y_cand, _hypers = self._create_candidates(
                            X,
                            fX,
                            length=self.length,
                            n_training_steps=self.n_training_steps,
                            hypers={},
                        )
                        X_next = self._select_candidates(X_cand, y_cand)
                    finally:
                        self.batch_size = original_batch_size

                    X_next = from_unit_cube(X_next, self.lb, self.ub)
                    fX_next = self._evaluate_rows(
                        X_next,
                        selection_phase=TRUST_REGION_PHASE,
                    )

                    self._adjust_length(fX_next)
                    self.n_evals += len(X_next)
                    self._X = np.vstack((self._X, X_next))
                    self._fX = np.vstack((self._fX, fX_next))

                    if self.verbose and fX_next.min() < self.fX.min():
                        n_evals, fbest = self.n_evals, fX_next.min()
                        print(f"{n_evals}) New best: {fbest:.4}")
                        sys.stdout.flush()

                    self.X = np.vstack((self.X, deepcopy(X_next)))
                    self.fX = np.vstack((self.fX, deepcopy(fX_next)))

    return BatchTurbo1(f_batch=f_batch, **kwargs)


def _configured_corner_ids(bundle: ContractBundle) -> list[str | None]:
    if bundle.process_corners is None:
        return [None]
    return [corner.id for corner in bundle.process_corners.corners]


def _run_default_adapter(
    project_dir: Path,
    *,
    run_id: str,
    cadence_cshrc: Path | None,
) -> None:
    bundle = assert_valid_project(project_dir)
    corner_ids = _configured_corner_ids(bundle)
    if bundle.testbenches is not None or corner_ids != [None]:
        _run_multi_testbench_default_adapter(
            project_dir,
            run_id=run_id,
            cadence_cshrc=cadence_cshrc,
            testbench_ids=(
                [testbench.id for testbench in bundle.testbenches.testbenches]
                if bundle.testbenches is not None
                else [None]
            ),
            corner_ids=corner_ids,
        )
        return

    if cadence_cshrc is None:
        from hermes_workflow.execution_adapters.spectre_ocean import (
            run_spectre_ocean_adapter,
        )

        result = run_spectre_ocean_adapter(project_dir, run_id=run_id)
        if result.status != "succeeded":
            raise RuntimeError("; ".join(result.issues) or result.status)
        return

    repo_root = Path(__file__).resolve().parents[2]
    tool_path = repo_root / "tools" / "run_spectre_ocean_adapter.py"
    command = (
        f"source {shlex.quote(str(cadence_cshrc))}; "
        f"cd {shlex.quote(str(repo_root))}; "
        f"{shlex.quote(sys.executable)} {shlex.quote(str(tool_path))} "
        f"{shlex.quote(str(project_dir))} --run-id {shlex.quote(run_id)}"
    )
    completed = subprocess.run(
        ["csh", "-fc", command],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stdout + "\n" + completed.stderr).strip()
            or f"adapter failed with return code {completed.returncode}"
        )


def _run_multi_testbench_default_adapter(
    project_dir: Path,
    *,
    run_id: str,
    cadence_cshrc: Path | None,
    testbench_ids: list[str | None],
    corner_ids: list[str | None],
) -> None:
    issues: list[str] = []
    if cadence_cshrc is None:
        from hermes_workflow.execution_adapters.spectre_ocean import (
            run_spectre_ocean_adapter,
        )

        for testbench_id in testbench_ids:
            for corner_id in corner_ids:
                result = run_spectre_ocean_adapter(
                    project_dir,
                    run_id=run_id,
                    testbench_id=testbench_id,
                    corner_id=corner_id,
                )
                if result.status != "succeeded":
                    message = "; ".join(result.issues) or result.status
                    label = (
                        (testbench_id or "default_testbench")
                        if corner_id is None
                        else (
                            f"{testbench_id}/{corner_id}"
                            if testbench_id is not None
                            else corner_id
                        )
                    )
                    issues.append(f"{label}: {message}")
    else:
        repo_root = Path(__file__).resolve().parents[2]
        tool_path = repo_root / "tools" / "run_spectre_ocean_adapter.py"
        for testbench_id in testbench_ids:
            for corner_id in corner_ids:
                command = (
                    f"source {shlex.quote(str(cadence_cshrc))}; "
                    f"cd {shlex.quote(str(repo_root))}; "
                    f"{shlex.quote(sys.executable)} {shlex.quote(str(tool_path))} "
                    f"{shlex.quote(str(project_dir))} --run-id {shlex.quote(run_id)}"
                )
                if testbench_id is not None:
                    command += f" --testbench-id {shlex.quote(testbench_id)}"
                if corner_id is not None:
                    command += f" --corner-id {shlex.quote(corner_id)}"
                completed = subprocess.run(
                    ["csh", "-fc", command],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            if completed.returncode != 0:
                message = (completed.stdout + "\n" + completed.stderr).strip()
                label = (
                    (testbench_id or "default_testbench")
                    if corner_id is None
                    else (
                        f"{testbench_id}/{corner_id}"
                        if testbench_id is not None
                        else corner_id
                    )
                )
                issues.append(
                    f"{label}: "
                    + (message or f"adapter failed with return code {completed.returncode}")
                )

    from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run

    aggregate_multi_testbench_run(project_dir, run_id=run_id)
    if issues:
        raise RuntimeError("; ".join(issues))
