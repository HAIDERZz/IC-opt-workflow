from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from hermes_workflow.candidate_contract import quantize_candidate
from hermes_workflow.optimizer_trace_identity import (
    optimizer_trace_identity_issues,
)
from hermes_workflow.schemas import VariablesConfig


REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
EVALUATIONS_RELATIVE = Path("reports/native_turbo_optimizer_evaluations.jsonl")
INITIALIZATION_PHASE = "initialization"
TRUST_REGION_PHASE = "turbo_trust_region"


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


def numbered_id_suffix(value: str | None, *, prefix: str) -> int:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(f"expected {prefix}<number>, got {value!r}")
    suffix = value[len(prefix) :]
    if not suffix.isdigit():
        raise ValueError(f"expected {prefix}<number>, got {value!r}")
    return int(suffix)


def load_native_turbo_history(
    project_dir: str | Path,
    *,
    variables: VariablesConfig,
) -> list[NativeTurboEvaluationTrace]:
    """Load and validate the backend's canonical continuation artifacts.

    Doctor and the runtime continuation loader intentionally share this entire
    entry point, including variable-name, raw-vector dimension, and grid
    quantization checks, so Doctor cannot approve history that runtime rejects
    immediately afterwards.
    """

    project_root = Path(project_dir)
    report_path = project_root / REPORT_RELATIVE
    evaluations_path = project_root / EVALUATIONS_RELATIVE
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"native TuRBO continuation report is missing: {report_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"native TuRBO continuation report is invalid JSON: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise ValueError("native TuRBO continuation report must be a JSON object")
    if report.get("schema_version") != "1.0":
        raise ValueError("native TuRBO continuation report schema_version must be 1.0")
    if report.get("status") != "completed":
        raise ValueError("native TuRBO continuation requires a completed report")
    # Reports written before the backend field was introduced are still
    # unambiguously native because both paths are Native-TuRBO-specific.
    if report.get("backend") not in {None, "native_turbo"}:
        raise ValueError(
            "native TuRBO continuation report backend must be native_turbo"
        )
    if report.get("evaluations") != EVALUATIONS_RELATIVE.as_posix():
        raise ValueError(
            "native TuRBO continuation report evaluations path is invalid"
        )

    try:
        raw_lines = evaluations_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(
            f"native TuRBO continuation evaluations are missing: {evaluations_path}"
        ) from exc
    if not raw_lines or any(not line.strip() for line in raw_lines):
        raise ValueError(
            "native TuRBO continuation evaluations must be non-empty JSONL"
        )

    traces: list[NativeTurboEvaluationTrace] = []
    for line_number, line in enumerate(raw_lines, start=1):
        try:
            raw_trace = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "native TuRBO continuation evaluations contain invalid JSON "
                f"at line {line_number}: {exc}"
            ) from exc
        if not isinstance(raw_trace, dict):
            raise ValueError(
                "native TuRBO continuation evaluation line "
                f"{line_number} must be an object"
            )
        try:
            trace = NativeTurboEvaluationTrace(**raw_trace)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "native TuRBO continuation evaluation line "
                f"{line_number} is invalid: {exc}"
            ) from exc

        _validate_trace_schema(trace, line_number=line_number)
        if trace.selection_phase not in {INITIALIZATION_PHASE, TRUST_REGION_PHASE}:
            raise ValueError(
                "native TuRBO continuation selection_phase is invalid at line "
                f"{line_number}: {trace.selection_phase!r}"
            )
        batch_metadata = (trace.batch_id, trace.batch_slot, trace.batch_size)
        if all(value is None for value in batch_metadata):
            # Sequential reports predate batch metadata. A one-point batch is
            # the exact runtime normalization used to reconstruct them.
            trace = replace(
                trace,
                batch_id=f"batch_{line_number:03d}",
                batch_slot=1,
                batch_size=1,
            )
        elif any(value is None for value in batch_metadata):
            raise ValueError(
                "native TuRBO continuation batch metadata must be all present "
                f"or all absent at line {line_number}"
            )
        numbered_id_suffix(trace.batch_id, prefix="batch_")
        if (
            not isinstance(trace.batch_slot, int)
            or isinstance(trace.batch_slot, bool)
            or trace.batch_slot < 1
            or not isinstance(trace.batch_size, int)
            or isinstance(trace.batch_size, bool)
            or trace.batch_size < trace.batch_slot
        ):
            raise ValueError(
                "native TuRBO continuation batch metadata is invalid at line "
                f"{line_number}"
            )
        traces.append(trace)

    identity_issues = optimizer_trace_identity_issues(
        [trace.__dict__ for trace in traces],
        is_fake=False,
    )
    if identity_issues:
        raise ValueError(
            "native TuRBO continuation trace identity is invalid: "
            + "; ".join(identity_issues)
        )
    _validate_native_turbo_batch_history(traces)

    evaluation_count = report.get("evaluation_count")
    if not isinstance(evaluation_count, int) or isinstance(evaluation_count, bool):
        raise ValueError(
            "native TuRBO continuation report evaluation_count must be an integer"
        )
    if evaluation_count != len(traces):
        raise ValueError(
            "native TuRBO continuation report evaluation_count does not match JSONL: "
            f"{evaluation_count} != {len(traces)}"
        )
    _validate_variable_semantics(traces, variables=variables)
    return traces


def _validate_variable_semantics(
    traces: Sequence[NativeTurboEvaluationTrace],
    *,
    variables: VariablesConfig,
) -> None:
    expected_names = {variable.name for variable in variables.variables}
    for line_number, trace in enumerate(traces, start=1):
        if len(trace.raw_x) != len(variables.variables):
            raise ValueError(
                "native TuRBO continuation raw_x dimension mismatch at line "
                f"{line_number}"
            )
        if set(trace.parameters) != expected_names:
            raise ValueError(
                "native TuRBO continuation parameters mismatch at line "
                f"{line_number}"
            )
        if quantize_candidate(variables, trace.raw_x) != trace.parameters:
            raise ValueError(
                "native TuRBO continuation raw_x/parameters mismatch at line "
                f"{line_number}"
            )


def _validate_trace_schema(
    trace: NativeTurboEvaluationTrace,
    *,
    line_number: int,
) -> None:
    if not isinstance(trace.evaluation_index, int) or isinstance(
        trace.evaluation_index, bool
    ):
        raise ValueError(
            "native TuRBO continuation evaluation_index is invalid at line "
            f"{line_number}"
        )
    if not isinstance(trace.status, str):
        raise ValueError(
            f"native TuRBO continuation status is invalid at line {line_number}"
        )
    if not isinstance(trace.selection_phase, str):
        raise ValueError(
            "native TuRBO continuation selection_phase is invalid at line "
            f"{line_number}"
        )
    if not isinstance(trace.raw_x, list) or not all(
        _is_finite_number(value) for value in trace.raw_x
    ):
        raise ValueError(
            f"native TuRBO continuation raw_x is invalid at line {line_number}"
        )
    if not isinstance(trace.parameters, dict) or not all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in trace.parameters.items()
    ):
        raise ValueError(
            f"native TuRBO continuation parameters are invalid at line {line_number}"
        )
    if not _is_finite_number(trace.objective):
        raise ValueError(
            f"native TuRBO continuation objective is non-finite at line {line_number}"
        )
    if trace.fom is not None and not _is_number(trace.fom):
        raise ValueError(
            f"native TuRBO continuation fom is invalid at line {line_number}"
        )
    if not _is_number(trace.constraint_penalty):
        raise ValueError(
            "native TuRBO continuation constraint_penalty is invalid at line "
            f"{line_number}"
        )
    if trace.metrics is not None and (
        not isinstance(trace.metrics, dict)
        or not all(
            isinstance(name, str) and _is_number(value)
            for name, value in trace.metrics.items()
        )
    ):
        raise ValueError(
            f"native TuRBO continuation metrics are invalid at line {line_number}"
        )
    if trace.result_manifest is not None and not isinstance(
        trace.result_manifest, str
    ):
        raise ValueError(
            "native TuRBO continuation result_manifest is invalid at line "
            f"{line_number}"
        )
    if trace.metric_result_manifest is not None and not isinstance(
        trace.metric_result_manifest, str
    ):
        raise ValueError(
            "native TuRBO continuation metric_result_manifest is invalid at line "
            f"{line_number}"
        )
    if not isinstance(trace.issues, list) or not all(
        isinstance(issue, str) for issue in trace.issues
    ):
        raise ValueError(
            f"native TuRBO continuation issues are invalid at line {line_number}"
        )
    for field_name in (
        "batch_worker_count",
        "max_parallel_jobs",
        "threads_per_run",
        "parallel_jobs",
    ):
        value = getattr(trace, field_name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 1
        ):
            raise ValueError(
                "native TuRBO continuation "
                f"{field_name} is invalid at line {line_number}"
            )


def _validate_native_turbo_batch_history(
    traces: Sequence[NativeTurboEvaluationTrace],
) -> None:
    groups: list[list[NativeTurboEvaluationTrace]] = []
    previous_batch_number = 0
    for trace in traces:
        if groups and groups[-1][0].batch_id == trace.batch_id:
            groups[-1].append(trace)
            continue
        batch_number = numbered_id_suffix(trace.batch_id, prefix="batch_")
        if batch_number <= previous_batch_number:
            raise ValueError(
                "native TuRBO continuation batch_id must be strictly increasing "
                "and may not reappear"
            )
        previous_batch_number = batch_number
        groups.append([trace])

    for group in groups:
        batch_id = group[0].batch_id
        phases = {trace.selection_phase for trace in group}
        if len(phases) != 1:
            raise ValueError(
                f"native TuRBO continuation batch {batch_id} mixes selection_phase"
            )
        declared_sizes = {trace.batch_size for trace in group}
        if len(declared_sizes) != 1:
            raise ValueError(
                f"native TuRBO continuation batch {batch_id} mixes batch_size"
            )
        declared_size = next(iter(declared_sizes))
        slots = [trace.batch_slot for trace in group]
        if declared_size != len(group) or sorted(slots) != list(
            range(1, declared_size + 1)
        ):
            raise ValueError(
                "native TuRBO continuation batch slots must be complete and unique "
                f"for {batch_id}"
            )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: object) -> bool:
    return _is_number(value) and math.isfinite(float(value))
