"""History warm-start audit: compatibility checks and re-evaluation.

Reads configured previous-project sources, validates each evaluation row against
the CURRENT project contract (variable space, metric definitions, metric
completeness, old run status), recomputes the current objective and constraint
residuals from the current ``metrics.yaml`` / ``optimizer.yaml``, and writes
deterministic JSON / Markdown audit reports. Accepted observation payloads are
returned in memory so Task 4 can build OpenBox history without re-reading JSONL.

No OpenBox ``History`` / ``Observation`` / ``Configuration`` objects are created
here and no OpenBox runtime behavior is changed.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from hermes_workflow.native_turbo import evaluate_candidate_objective
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.schemas import (
    ConstraintOp,
    HistoryWarmStartConfig,
    HistoryWarmStartSource,
    MetricSpec,
    MetricsConfig,
    VariableKind,
    VariablesConfig,
)
from hermes_workflow.validate import ContractBundle, load_contract_bundle

HISTORY_WARM_START_AUDIT_RELATIVE = Path("reports/history_warm_start_audit.json")
HISTORY_WARM_START_AUDIT_MD_RELATIVE = Path("reports/history_warm_start_audit.md")

_SCHEMA_VERSION = "1.0"
_STATUS_DISABLED = "disabled"
_STATUS_COMPLETED = "completed"
_SOURCE_ACCEPTED = "accepted"
_SOURCE_REJECTED = "rejected"
_STATUS_FEASIBLE = "feasible"
_STATUS_CONSTRAINT_FAILED = "constraint_failed"
_STATUS_METRIC_FAILED = "metric_failed"
_COMPLETED_OLD_STATUSES = frozenset({_STATUS_FEASIBLE, _STATUS_CONSTRAINT_FAILED})

# Per-row rejection reasons.
_REASON_VARIABLE_SET_MISMATCH = "variable_set_mismatch"
_REASON_OUT_OF_CURRENT_SPACE = "out_of_current_space"
_REASON_INVALID_NUMERIC_VALUE = "invalid_numeric_value"
_REASON_MISSING_REQUIRED_METRIC = "missing_required_metric"
_REASON_FAILED_OR_INCOMPLETE_RUN = "failed_or_incomplete_run"
_REASON_INVALID_OPTIMIZER_EVALUATIONS = "invalid_optimizer_evaluations"
_REASON_MAX_OBSERVATIONS_EXCEEDED = "max_observations_exceeded"

# Source-level rejection reasons (recorded in the source ``issues`` list).
_REASON_SOURCE_PATH_MISSING = "source_path_missing"
_REASON_SOURCE_NOT_VALID_PROJECT = "source_not_valid_project"
_REASON_MISSING_OPTIMIZER_EVALUATIONS = "missing_optimizer_evaluations"
_REASON_VARIABLE_SET_MISMATCH_SOURCE = "variable_set_mismatch"
_REASON_METRIC_DEFINITION_MISMATCH = "metric_definition_mismatch"

_NO_ACCEPTED_OBSERVATIONS_ISSUE = (
    "history warm-start has no accepted observations; "
    "OpenBox will start without transfer history"
)

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_CONTINUOUS_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s*(?P<unit>\S+))?\s*$"
)


@dataclass(frozen=True)
class OpenBoxTransferLearningAudit:
    enabled: bool
    source_count: int
    accepted_observation_count: int
    warm_start_strategy: str | None
    applied_to_advisor: bool


@dataclass(frozen=True)
class HistoryWarmStartSourceAudit:
    label: str | None
    path: str
    status: str
    candidate_trace_count: int
    accepted_observation_count: int
    rejected_observation_count: int
    rejection_reasons: dict[str, int]
    issues: list[str]


@dataclass(frozen=True)
class AcceptedObservation:
    source_label: str | None
    source_path: str
    source_evaluation_index: int | None
    source_run_id: str | None
    parameters: dict[str, str]
    metrics: dict[str, float]
    objective: float
    fom: float | None
    constraint_penalty: float
    constraint_residuals: list[float]
    status: str
    issues: list[str]


@dataclass(frozen=True)
class HistoryWarmStartAudit:
    enabled: bool
    status: str
    sources: list[HistoryWarmStartSourceAudit]
    accepted_observation_count: int
    rejected_observation_count: int
    openbox_transfer_learning: OpenBoxTransferLearningAudit
    issues: list[str]
    accepted_observations: list[AcceptedObservation]


@dataclass
class _SourceResult:
    """Mutable per-source accumulator finalized after the max-observations cap."""

    label: str | None
    path: str
    candidate_trace_count: int
    accepted: list[AcceptedObservation]
    rejection_reasons: dict[str, int]
    issues: list[str]
    source_level_rejected: bool


def audit_history_warm_start(
    project_dir: Path, bundle: ContractBundle, *, write_reports: bool = True
) -> HistoryWarmStartAudit:
    """Audit configured history warm-start sources and write JSON/Markdown reports.

    Reports are written on every call by default, including when warm-start is
    disabled. Pass ``write_reports=False`` to compute the audit object without
    touching disk (used by the OpenBox integration to leave no-config projects'
    existing behavior untouched).
    """
    config = bundle.history_warm_start
    if config is None or not config.history_warm_start.enabled:
        audit = _disabled_audit()
    else:
        audit = _enabled_audit(project_dir, config, bundle)

    if write_reports:
        _write_reports(project_dir, audit)
    return audit


def _disabled_audit() -> HistoryWarmStartAudit:
    return HistoryWarmStartAudit(
        enabled=False,
        status=_STATUS_DISABLED,
        sources=[],
        accepted_observation_count=0,
        rejected_observation_count=0,
        openbox_transfer_learning=OpenBoxTransferLearningAudit(
            enabled=False,
            source_count=0,
            accepted_observation_count=0,
            warm_start_strategy=None,
            applied_to_advisor=False,
        ),
        issues=[],
        accepted_observations=[],
    )


def _enabled_audit(
    project_dir: Path,
    config: HistoryWarmStartConfig,
    current_bundle: ContractBundle,
) -> HistoryWarmStartAudit:
    settings = config.history_warm_start
    current_variables = current_bundle.variables
    current_metrics = current_bundle.metrics
    current_optimizer = current_bundle.optimizer

    results = [
        _audit_source(
            project_dir,
            source,
            current_variables,
            current_metrics,
            current_optimizer,
        )
        for source in settings.sources
    ]

    kept_observations, overflow_counts = _apply_observation_cap(
        results, settings.max_observations
    )

    source_audits: list[HistoryWarmStartSourceAudit] = []
    for index, result in enumerate(results):
        if result.source_level_rejected:
            source_audits.append(
                HistoryWarmStartSourceAudit(
                    label=result.label,
                    path=result.path,
                    status=_SOURCE_REJECTED,
                    candidate_trace_count=0,
                    accepted_observation_count=0,
                    rejected_observation_count=0,
                    rejection_reasons={},
                    issues=list(result.issues),
                )
            )
            continue

        overflow = overflow_counts[index]
        if overflow > 0:
            result.rejection_reasons[_REASON_MAX_OBSERVATIONS_EXCEEDED] = overflow
        accepted_count = len(result.accepted) - overflow
        rejected_count = sum(result.rejection_reasons.values())
        status = _SOURCE_ACCEPTED if accepted_count > 0 else _SOURCE_REJECTED
        source_audits.append(
            HistoryWarmStartSourceAudit(
                label=result.label,
                path=result.path,
                status=status,
                candidate_trace_count=result.candidate_trace_count,
                accepted_observation_count=accepted_count,
                rejected_observation_count=rejected_count,
                rejection_reasons=dict(result.rejection_reasons),
                issues=list(result.issues),
            )
        )

    accepted_total = len(kept_observations)
    rejected_total = sum(source.rejected_observation_count for source in source_audits)
    issues: list[str] = [_NO_ACCEPTED_OBSERVATIONS_ISSUE] if accepted_total == 0 else []

    return HistoryWarmStartAudit(
        enabled=True,
        status=_STATUS_COMPLETED,
        sources=source_audits,
        accepted_observation_count=accepted_total,
        rejected_observation_count=rejected_total,
        openbox_transfer_learning=OpenBoxTransferLearningAudit(
            enabled=True,
            source_count=len(settings.sources),
            accepted_observation_count=accepted_total,
            warm_start_strategy=settings.warm_start_strategy,
            applied_to_advisor=False,
        ),
        issues=issues,
        accepted_observations=kept_observations,
    )


def _audit_source(
    project_dir: Path,
    source: HistoryWarmStartSource,
    current_variables: VariablesConfig,
    current_metrics: MetricsConfig | None,
    current_optimizer: object,
) -> _SourceResult:
    raw_path = Path(source.path)
    resolved = raw_path if raw_path.is_absolute() else project_dir / raw_path
    resolved = resolved.resolve()
    display_path = str(resolved)
    label = source.label

    if not resolved.exists():
        return _source_level_result(
            label,
            display_path,
            f"{_REASON_SOURCE_PATH_MISSING}: source path does not exist: {display_path}",
        )
    try:
        source_bundle = load_contract_bundle(resolved)
    except ValueError:
        return _source_level_result(
            label,
            display_path,
            f"{_REASON_SOURCE_NOT_VALID_PROJECT}: source is not a valid project: {display_path}",
        )

    evaluations_path = resolved / EVALUATIONS_RELATIVE
    if not evaluations_path.exists():
        return _source_level_result(
            label,
            display_path,
            (
                f"{_REASON_MISSING_OPTIMIZER_EVALUATIONS}: source project has no "
                f"optimizer evaluations at {EVALUATIONS_RELATIVE}: {display_path}"
            ),
        )

    if not _variable_sets_match(current_variables, source_bundle.variables):
        return _source_level_result(
            label,
            display_path,
            (
                f"{_REASON_VARIABLE_SET_MISMATCH_SOURCE}: source variable names "
                f"do not match current project: {display_path}"
            ),
        )

    if not _metric_definitions_compatible(current_metrics, source_bundle.metrics):
        return _source_level_result(
            label,
            display_path,
            (
                f"{_REASON_METRIC_DEFINITION_MISMATCH}: source metric definitions "
                f"do not match current project: {display_path}"
            ),
        )

    assert current_metrics is not None
    assert current_optimizer is not None
    return _process_evaluation_rows(
        label,
        display_path,
        evaluations_path,
        current_variables,
        current_metrics,
        current_optimizer,
    )


def _source_level_result(
    label: str | None, path: str, issue: str
) -> _SourceResult:
    # Source-level failures are recorded in ``issues`` (the reason keyword is
    # embedded there); ``rejection_reasons`` is reserved for per-observation
    # counts so its values always sum to ``rejected_observation_count``.
    return _SourceResult(
        label=label,
        path=path,
        candidate_trace_count=0,
        accepted=[],
        rejection_reasons={},
        issues=[issue],
        source_level_rejected=True,
    )


def _variable_sets_match(
    current_variables: VariablesConfig, source_variables: VariablesConfig
) -> bool:
    current_names = {variable.name for variable in current_variables.variables}
    source_names = {variable.name for variable in source_variables.variables}
    return current_names == source_names


def _metric_definitions_compatible(
    current_metrics: MetricsConfig | None, source_metrics: MetricsConfig | None
) -> bool:
    if current_metrics is None or source_metrics is None:
        return current_metrics is None and source_metrics is None
    source_by_name = {metric.name: metric for metric in source_metrics.metrics}
    for current_metric in current_metrics.metrics:
        source_metric = source_by_name.get(current_metric.name)
        if source_metric is None:
            return False
        if _metric_signature(current_metric) != _metric_signature(source_metric):
            return False
    return True


def _metric_signature(metric: MetricSpec) -> object:
    ocean = metric.ocean
    ocean_signature = None
    if ocean is not None:
        ocean_signature = (
            ocean.expression,
            ocean.result,
            str(ocean.expression_source),
            ocean.source_reference,
            str(ocean.expected_value_type),
            str(ocean.nil_policy),
            str(ocean.non_finite_policy),
        )
    return (
        metric.name,
        metric.unit,
        metric.maestro_formula,
        metric.testbench,
        tuple(metric.required_signals),
        ocean_signature,
    )


def _process_evaluation_rows(
    label: str | None,
    display_path: str,
    evaluations_path: Path,
    current_variables: VariablesConfig,
    current_metrics: MetricsConfig,
    current_optimizer: object,
) -> _SourceResult:
    current_variable_by_name = {variable.name: variable for variable in current_variables.variables}
    current_metric_names = [metric.name for metric in current_metrics.metrics]

    candidate_trace_count = 0
    accepted: list[AcceptedObservation] = []
    rejection_reasons: dict[str, int] = {}

    text = evaluations_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        # Every non-blank line is a candidate trace: it is either accepted or
        # rejected (malformed rows included), so for each source
        # candidate_trace_count == accepted + rejected.
        candidate_trace_count += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            _bump(rejection_reasons, _REASON_INVALID_OPTIMIZER_EVALUATIONS)
            continue
        if not isinstance(row, dict):
            _bump(rejection_reasons, _REASON_INVALID_OPTIMIZER_EVALUATIONS)
            continue

        observation, reason = _evaluate_row(
            row,
            label,
            display_path,
            current_variable_by_name,
            current_metric_names,
            current_metrics,
            current_optimizer,
        )
        if observation is not None:
            accepted.append(observation)
        else:
            assert reason is not None
            _bump(rejection_reasons, reason)

    return _SourceResult(
        label=label,
        path=display_path,
        candidate_trace_count=candidate_trace_count,
        accepted=accepted,
        rejection_reasons=rejection_reasons,
        issues=[],
        source_level_rejected=False,
    )


def _evaluate_row(
    row: dict[str, object],
    label: str | None,
    display_path: str,
    current_variable_by_name: dict[str, object],
    current_metric_names: list[str],
    current_metrics: MetricsConfig,
    current_optimizer: object,
) -> tuple[AcceptedObservation | None, str | None]:
    parameters = row.get("parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(
        current_variable_by_name
    ):
        return None, _REASON_VARIABLE_SET_MISMATCH

    for name in current_variable_by_name:
        variable = current_variable_by_name[name]
        space_reason = _check_variable_space(variable, str(parameters[name]))
        if space_reason is not None:
            return None, space_reason

    raw_metrics = row.get("metrics")
    if not isinstance(raw_metrics, dict):
        return None, _REASON_MISSING_REQUIRED_METRIC
    metric_values: dict[str, float] = {}
    for metric_name in current_metric_names:
        raw_value = raw_metrics.get(metric_name)
        if raw_value is None:
            return None, _REASON_MISSING_REQUIRED_METRIC
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            return None, _REASON_INVALID_NUMERIC_VALUE
        value = float(raw_value)
        if not math.isfinite(value):
            return None, _REASON_INVALID_NUMERIC_VALUE
        metric_values[metric_name] = value

    old_status = row.get("status")
    if old_status not in _COMPLETED_OLD_STATUSES:
        return None, _REASON_FAILED_OR_INCOMPLETE_RUN

    evaluation = evaluate_candidate_objective(
        current_metrics, current_optimizer, metric_values
    )
    if evaluation.status == _STATUS_METRIC_FAILED:
        # native_turbo phrases a missing-current-metric failure as
        # "metric <name> missing"; any other metric_failed here is a
        # non-finite value/objective. This is coupled to that phrasing because
        # ObjectiveEvaluation exposes only free-text issues.
        if any("missing" in issue for issue in evaluation.issues):
            return None, _REASON_MISSING_REQUIRED_METRIC
        return None, _REASON_INVALID_NUMERIC_VALUE

    residuals = _constraint_residuals(current_metrics, metric_values)
    observation = AcceptedObservation(
        source_label=label,
        source_path=display_path,
        source_evaluation_index=_coerce_int(row.get("evaluation_index")),
        source_run_id=_coerce_str(row.get("run_id")),
        parameters={name: str(parameters[name]) for name in current_variable_by_name},
        metrics={name: metric_values[name] for name in current_metric_names},
        objective=evaluation.objective,
        fom=evaluation.fom,
        constraint_penalty=evaluation.constraint_penalty,
        constraint_residuals=residuals,
        status=evaluation.status,
        issues=list(evaluation.issues),
    )
    return observation, None


def _check_variable_space(variable: object, value: str) -> str | None:
    kind = variable.kind
    if kind == VariableKind.INTEGER or kind == "integer":
        return _check_integer_space(variable, value)
    return _check_continuous_space(variable, value)


def _check_integer_space(variable: object, value: str) -> str | None:
    try:
        lower = _parse_whole_number(variable.lower)
        upper = _parse_whole_number(variable.upper)
        step = _parse_whole_number(variable.step)
        numeric_value = _parse_whole_number(value)
    except ValueError:
        return _REASON_INVALID_NUMERIC_VALUE
    if not (lower <= numeric_value <= upper):
        return _REASON_OUT_OF_CURRENT_SPACE
    if step != 0 and (numeric_value - lower) % step != 0:
        return _REASON_OUT_OF_CURRENT_SPACE
    return None


def _check_continuous_space(variable: object, value: str) -> str | None:
    lower = _parse_decimal_unit(variable.lower)
    upper = _parse_decimal_unit(variable.upper)
    step = _parse_decimal_unit(variable.step)
    numeric_value = _parse_decimal_unit(value)
    if lower is None or upper is None or step is None or numeric_value is None:
        return _REASON_INVALID_NUMERIC_VALUE
    var_unit = lower[1]
    if numeric_value[1] != var_unit:
        return _REASON_OUT_OF_CURRENT_SPACE
    low, high, stride, candidate = lower[0], upper[0], step[0], numeric_value[0]
    if not (low <= candidate <= high):
        return _REASON_OUT_OF_CURRENT_SPACE
    if stride != 0 and (candidate - low) % stride != 0:
        return _REASON_OUT_OF_CURRENT_SPACE
    return None


def _parse_whole_number(raw: str) -> int:
    if not _INTEGER_RE.match(raw):
        raise ValueError(f"not a whole number: {raw!r}")
    return int(raw)


def _parse_decimal_unit(raw: str) -> tuple[Decimal, str] | None:
    match = _CONTINUOUS_RE.match(raw)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value"))
    except InvalidOperation:
        return None
    return value, match.group("unit") or ""


def _constraint_residuals(
    current_metrics: MetricsConfig, metric_values: dict[str, float]
) -> list[float]:
    residuals: list[float] = []
    for constraint in current_metrics.constraints:
        metric_value = metric_values.get(constraint.metric)
        threshold = _parse_constraint_threshold(constraint.value)
        if metric_value is None or threshold is None:
            residuals.append(0.0)
            continue
        if constraint.op in (ConstraintOp.LT, ConstraintOp.LE):
            residuals.append(float(metric_value) - threshold)
        else:
            residuals.append(threshold - float(metric_value))
    return residuals


def _parse_constraint_threshold(raw: str) -> float | None:
    parsed = _parse_decimal_unit(raw)
    if parsed is not None:
        return float(parsed[0])
    try:
        return float(raw)
    except ValueError:
        return None


def _apply_observation_cap(
    results: list[_SourceResult], max_observations: int | None
) -> tuple[list[AcceptedObservation], list[int]]:
    flat: list[tuple[float, int, int, int]] = []
    for source_index, result in enumerate(results):
        if result.source_level_rejected:
            continue
        for position, observation in enumerate(result.accepted):
            flat.append(
                (
                    observation.objective,
                    source_index,
                    _eval_sort_key(observation.source_evaluation_index),
                    position,
                )
            )

    if max_observations is None or len(flat) <= max_observations:
        kept = [
            observation
            for result in results
            if not result.source_level_rejected
            for observation in result.accepted
        ]
        return kept, [0] * len(results)

    flat.sort()
    keep_keys = {(item[1], item[3]) for item in flat[:max_observations]}
    kept: list[AcceptedObservation] = []
    overflow = [0] * len(results)
    for source_index, result in enumerate(results):
        for position, observation in enumerate(result.accepted):
            if (source_index, position) in keep_keys:
                kept.append(observation)
            else:
                overflow[source_index] += 1
    return kept, overflow


def _eval_sort_key(evaluation_index: int | None) -> int:
    if isinstance(evaluation_index, bool):
        return 0
    if isinstance(evaluation_index, int):
        return evaluation_index
    return 0


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _coerce_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bump(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


def _write_reports(project_dir: Path, audit: HistoryWarmStartAudit) -> None:
    json_path = project_dir / HISTORY_WARM_START_AUDIT_RELATIVE
    md_path = project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(_audit_to_payload(audit), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_audit_to_markdown(audit), encoding="utf-8")


def _audit_to_payload(audit: HistoryWarmStartAudit) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "enabled": audit.enabled,
        "status": audit.status,
        "sources": [_source_to_payload(source) for source in audit.sources],
        "accepted_observation_count": audit.accepted_observation_count,
        "rejected_observation_count": audit.rejected_observation_count,
        "openbox_transfer_learning": {
            "enabled": audit.openbox_transfer_learning.enabled,
            "source_count": audit.openbox_transfer_learning.source_count,
            "accepted_observation_count": audit.openbox_transfer_learning.accepted_observation_count,
            "warm_start_strategy": audit.openbox_transfer_learning.warm_start_strategy,
            "applied_to_advisor": audit.openbox_transfer_learning.applied_to_advisor,
        },
        "accepted_observations": [
            _accepted_to_payload(observation) for observation in audit.accepted_observations
        ],
        "issues": list(audit.issues),
    }


def _source_to_payload(source: HistoryWarmStartSourceAudit) -> dict[str, object]:
    return {
        "label": source.label,
        "path": source.path,
        "status": source.status,
        "candidate_trace_count": source.candidate_trace_count,
        "accepted_observation_count": source.accepted_observation_count,
        "rejected_observation_count": source.rejected_observation_count,
        "rejection_reasons": dict(source.rejection_reasons),
        "issues": list(source.issues),
    }


def _accepted_to_payload(observation: AcceptedObservation) -> dict[str, object]:
    return {
        "source_label": observation.source_label,
        "source_path": observation.source_path,
        "source_evaluation_index": observation.source_evaluation_index,
        "source_run_id": observation.source_run_id,
        "parameters": dict(observation.parameters),
        "metrics": dict(observation.metrics),
        "objective": observation.objective,
        "fom": observation.fom,
        "constraint_penalty": observation.constraint_penalty,
        "constraint_residuals": list(observation.constraint_residuals),
        "status": observation.status,
        "issues": list(observation.issues),
    }


def _audit_to_markdown(audit: HistoryWarmStartAudit) -> str:
    lines = ["# History Warm-Start Audit", ""]
    lines.append(f"Status: {audit.status}")
    lines.append(f"Enabled: {'true' if audit.enabled else 'false'}")
    lines.append(f"Accepted observations: {audit.accepted_observation_count}")
    lines.append(f"Rejected observations: {audit.rejected_observation_count}")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source in audit.sources:
        label = source.label if source.label is not None else source.path
        lines.append(
            f"- {label}: {source.status}, "
            f"candidates={source.candidate_trace_count}, "
            f"accepted={source.accepted_observation_count}, "
            f"rejected={source.rejected_observation_count}"
        )
    lines.append("")
    lines.append("## Issues")
    lines.append("")
    for issue in audit.issues:
        lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Task 4: OpenBox adapter (accepted audit rows -> OpenBox history/configs)
# ---------------------------------------------------------------------------

_APPLICATION_MODE_DISABLED = "disabled"
_APPLICATION_MODE_NO_ACCEPTED = "no_accepted_observations"
_APPLICATION_MODE_TRANSFER = "transfer_learning_history"
_APPLICATION_MODE_INITIAL_CONFIGS = "initial_configurations_from_history"
_APPLICATION_MODE_NOT_APPLIED = "not_applied"
_NOT_APPLIED_REJECTED_BY_OPENBOX = "history_object_rejected_by_openbox"


@dataclass(frozen=True)
class WarmStartAdapterResult:
    audit: HistoryWarmStartAudit
    transfer_learning_history: list[object]
    initial_configurations: list[object]
    accepted_observation_count: int
    applied_observation_count: int
    application_mode: str
    not_applied_reason: str | None
    warm_start_strategy: str | None


def build_warm_start_openbox_adapter(
    project_dir: Path,
    bundle: ContractBundle,
    *,
    space: object,
    observation_factory: Callable[..., object],
    history_factory: Callable[..., object],
    config_builder: Callable[[dict[str, str]], object],
    initial_config_provider: Callable[..., object] | None,
    random_seed: int,
    initial_trials: int | None,
    initialization: str | None,
    num_constraints: int,
) -> WarmStartAdapterResult:
    """Convert accepted audit observations into OpenBox-native objects.

    The OpenBox factories are injected so this is unit-testable without the
    real OpenBox library. No OpenBox import lives in this module.
    """
    audit = audit_history_warm_start(project_dir, bundle)
    config = bundle.history_warm_start
    if config is None or not config.history_warm_start.enabled:
        return WarmStartAdapterResult(
            audit=audit,
            transfer_learning_history=[],
            initial_configurations=[],
            accepted_observation_count=audit.accepted_observation_count,
            applied_observation_count=0,
            application_mode=_APPLICATION_MODE_DISABLED,
            not_applied_reason=None,
            warm_start_strategy=None,
        )

    strategy = config.history_warm_start.warm_start_strategy
    if audit.accepted_observation_count == 0:
        return WarmStartAdapterResult(
            audit=audit,
            transfer_learning_history=[],
            initial_configurations=[],
            accepted_observation_count=0,
            applied_observation_count=0,
            application_mode=_APPLICATION_MODE_NO_ACCEPTED,
            not_applied_reason=None,
            warm_start_strategy=strategy,
        )

    # Group accepted observations by source, preserving acceptance order, so
    # each source maps to exactly one OpenBox History.
    grouped: dict[str, list[AcceptedObservation]] = {}
    for observation in audit.accepted_observations:
        grouped.setdefault(observation.source_path, []).append(observation)

    histories: list[object] = []
    applied = 0
    for observations in grouped.values():
        history = history_factory(config_space=space, num_constraints=num_constraints)
        for accepted in observations:
            configuration = config_builder(accepted.parameters)
            observation = observation_factory(
                config=configuration,
                objectives=[accepted.objective],
                constraints=list(accepted.constraint_residuals),
                extra_info={
                    "history_warm_start": True,
                    "source_path": accepted.source_path,
                    "source_label": accepted.source_label,
                    "source_run_id": accepted.source_run_id,
                    "source_evaluation_index": accepted.source_evaluation_index,
                    "status": accepted.status,
                },
            )
            try:
                history.update_observation(observation)
            except ValueError:
                # OpenBox rejected this observation (invalid for its history);
                # skip it and continue with the remaining observations.
                continue
            applied += 1
        histories.append(history)

    if applied == 0:
        return WarmStartAdapterResult(
            audit=audit,
            transfer_learning_history=[],
            initial_configurations=[],
            accepted_observation_count=audit.accepted_observation_count,
            applied_observation_count=0,
            application_mode=_APPLICATION_MODE_NOT_APPLIED,
            not_applied_reason=_NOT_APPLIED_REJECTED_BY_OPENBOX,
            warm_start_strategy=strategy,
        )

    if num_constraints == 0:
        # Direct transfer history is only supported by OpenBox for unconstrained
        # single-objective problems.
        return WarmStartAdapterResult(
            audit=audit,
            transfer_learning_history=histories,
            initial_configurations=[],
            accepted_observation_count=audit.accepted_observation_count,
            applied_observation_count=applied,
            application_mode=_APPLICATION_MODE_TRANSFER,
            not_applied_reason=None,
            warm_start_strategy=strategy,
        )

    # Constrained problem: OpenBox.check_setup() rejects transfer history, so
    # extract initial configurations from the built histories using OpenBox's own
    # InitialConfigProvider and pass those instead.
    if initial_config_provider is None:
        raise RuntimeError(
            "initial_config_provider is required for constrained warm-start "
            "initial-configuration extraction"
        )
    import numpy as np  # local: only needed for the constrained extraction rng

    init_num = (
        initial_trials
        if initial_trials is not None
        else max(2 * len(bundle.variables.variables), 1)
    )
    provider = initial_config_provider(
        config_space=space,
        init_num=init_num,
        init_strategy=initialization or "sobol",
        transfer_learning_history=histories,
        warm_start_strategy=strategy,
        rng=np.random.RandomState(random_seed),
    )
    # Keep only the warm-start-extracted configurations; InitialConfigProvider
    # also fills its queue with OpenBox-generated sobol/random fallback configs
    # which must not be labeled as warm-start.
    extracted = [
        config
        for config, source in zip(provider.config_queue, provider.config_sources)
        if source == "warm_start"
    ]
    return WarmStartAdapterResult(
        audit=audit,
        transfer_learning_history=[],
        initial_configurations=extracted,
        accepted_observation_count=audit.accepted_observation_count,
        applied_observation_count=applied,
        application_mode=_APPLICATION_MODE_INITIAL_CONFIGS,
        not_applied_reason=None,
        warm_start_strategy=strategy,
    )
