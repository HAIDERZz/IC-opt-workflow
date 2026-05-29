from __future__ import annotations

import hashlib
import itertools
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from hermes_workflow.schemas import OptimizerState, VariableKind
from hermes_workflow.validate import (
    CONTINUOUS_RE,
    ContractBundle,
    assert_valid_project,
    evaluate_objective,
)

try:
    from scipy.stats.qmc import LatinHypercube as ScipyLatinHypercube
    from scipy.stats.qmc import Sobol as ScipySobol

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def generate_integer_grid(lower: int, upper: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    if lower > upper:
        raise ValueError(f"lower ({lower}) must be <= upper ({upper})")
    return list(range(lower, upper + 1, step))


def generate_continuous_grid(lower_raw: str, upper_raw: str, step_raw: str) -> list[str]:
    parsed = _parse_continuous_triple(lower_raw, upper_raw, step_raw)
    (lower, lower_unit), (upper, _upper_unit), (step, _step_unit) = parsed

    # Format a grid value, re-attaching the unit suffix if present.
    def fmt(value: Decimal) -> str:
        # Remove trailing zeros for clean output, but keep at least one decimal
        # place if the original had decimals.
        text = f"{value:f}"
        if lower_unit:
            return f"{text} {lower_unit}"
        return text

    values: list[str] = []
    current = lower
    while current <= upper:
        values.append(fmt(current))
        current = current + step
    return values


def generate_candidates(
    bundle: ContractBundle,
    n_candidates: int,
    *,
    seed: int = 20260528,
    initialization: str | None = None,
) -> list[dict[str, str]]:
    if initialization is None:
        initialization = bundle.optimizer.optimizer.initialization.value
    variables = bundle.variables.variables
    grid_by_name: dict[str, list[str]] = {}
    for variable in variables:
        if variable.kind == VariableKind.INTEGER:
            grid_by_name[variable.name] = [
                str(v)
                for v in generate_integer_grid(
                    int(variable.lower), int(variable.upper), int(variable.step)
                )
            ]
        else:
            grid_by_name[variable.name] = generate_continuous_grid(
                variable.lower, variable.upper, variable.step
            )

    target = min(n_candidates, _count_grid_combinations(grid_by_name))
    candidates = _deduplicate(
        _sample_grid(grid_by_name, n_candidates, seed, initialization)
    )
    if len(candidates) < target:
        candidates = _fill_unique_candidates(candidates, grid_by_name, target)
    return candidates[:target]


def compute_mock_metrics(
    metrics_config: object,
    variables_config: object,
    parameters: dict[str, str],
) -> dict[str, float]:
    from hermes_workflow.schemas import MetricsConfig, VariablesConfig

    if not isinstance(metrics_config, MetricsConfig):
        raise TypeError(f"Expected MetricsConfig, got {type(metrics_config).__name__}")
    if not isinstance(variables_config, VariablesConfig):
        raise TypeError(f"Expected VariablesConfig, got {type(variables_config).__name__}")

    param_numeric: dict[str, float] = {}
    for variable in variables_config.variables:
        raw_value = parameters[variable.name]
        if variable.kind == VariableKind.INTEGER:
            param_numeric[variable.name] = float(raw_value)
        else:
            parsed = _parse_continuous(raw_value)
            if parsed is not None:
                param_numeric[variable.name], _unit = parsed
            else:
                param_numeric[variable.name] = float(raw_value)

    result: dict[str, float] = {}
    for metric in metrics_config.metrics:
        h = hashlib.sha256(f"{metric.name}:{sorted(param_numeric.items())}".encode())
        h_bytes = h.digest()
        value = int.from_bytes(h_bytes[:8], "big") / (2**64)
        # Map [0, 1) to a sensible range: 1.0 to 100.0, then offset by metric name hash.
        name_offset = int.from_bytes(
            hashlib.sha256(metric.name.encode()).digest()[:2], "big"
        )
        result[metric.name] = 1.0 + value * 99.0 + (name_offset % 50) * 0.1
    return result


def evaluate_constraints(
    metrics_config: object,
    computed_metrics: dict[str, float],
) -> bool:
    from hermes_workflow.schemas import MetricsConfig

    if not isinstance(metrics_config, MetricsConfig):
        raise TypeError(f"Expected MetricsConfig, got {type(metrics_config).__name__}")

    for constraint in metrics_config.constraints:
        metric_value = computed_metrics.get(constraint.metric)
        if metric_value is None:
            return False
        threshold = _parse_constraint_value(constraint.value)
        if threshold is None:
            return False
        if not _check_constraint(metric_value, constraint.op, threshold):
            return False
    return True


def write_ledger_row(project_dir: Path, row: object) -> Path:
    from hermes_workflow.schemas import LedgerRow

    if not isinstance(row, LedgerRow):
        raise TypeError(f"Expected LedgerRow, got {type(row).__name__}")
    ledger_dir = project_dir / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / "experiment_ledger.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(row.model_dump_json() + "\n")
    return path


def write_optimizer_state(project_dir: Path, state: object) -> Path:
    from hermes_workflow.schemas import OptimizerState

    if not isinstance(state, OptimizerState):
        raise TypeError(f"Expected OptimizerState, got {type(state).__name__}")
    state_dir = project_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "optimizer_state.json"
    path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def write_best_candidate(project_dir: Path, candidate: object) -> Path:
    from hermes_workflow.schemas import BestCandidate

    if not isinstance(candidate, BestCandidate):
        raise TypeError(f"Expected BestCandidate, got {type(candidate).__name__}")
    state_dir = project_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "best_candidate.json"
    path.write_text(candidate.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def write_health_check(
    project_dir: Path,
    *,
    current_evaluations: int,
    max_evaluations: int,
    best_candidate_id: str | None,
    last_batch_id: int | None,
    status: str = "healthy",
    real_run_started: bool = False,
    issues: list[str] | None = None,
) -> Path:
    state_dir = project_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "status": status,
        "real_run_started": real_run_started,
        "current_evaluations": current_evaluations,
        "best_candidate_path": (
            "state/best_candidate.json" if best_candidate_id is not None else None
        ),
        "last_batch_id": last_batch_id,
        "issues": issues or [],
    }
    path = state_dir / "health_check.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def run_mock_optimization(
    project_dir: Path,
    *,
    max_evaluations: int | None = None,
    seed_override: int | None = None,
) -> OptimizerState:
    from hermes_workflow.schemas import BestCandidate, LedgerRow, ObjectiveDirection

    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    optimizer = bundle.optimizer.optimizer
    metrics_config = bundle.metrics
    variables_config = bundle.variables

    effective_max = max_evaluations if max_evaluations is not None else optimizer.max_evaluations
    seed = seed_override if seed_override is not None else optimizer.random_seed
    initialization = optimizer.initialization.value
    direction = metrics_config.objective.direction

    candidates = generate_candidates(
        bundle,
        n_candidates=effective_max,
        seed=seed,
        initialization=initialization,
    )
    n_actual = len(candidates)

    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    batch_size = optimizer.batch_size

    running_state = OptimizerState(
        schema_version="1.0",
        project_name=bundle.project_config.project.name,
        algorithm=optimizer.algorithm.value,
        initialization=initialization,
        current_evaluations=0,
        max_evaluations=effective_max,
        batch_size=batch_size,
        random_seed=seed,
        best_candidate_id=None,
        status="running",
        started_at_utc=started_at,
        updated_at_utc=started_at,
    )
    write_optimizer_state(project_dir, running_state)

    best_candidate: BestCandidate | None = None
    best_objective: float | None = None

    for i, params in enumerate(candidates):
        computed_metrics = compute_mock_metrics(metrics_config, variables_config, params)
        raw_objective = evaluate_objective_from_config(metrics_config, computed_metrics)
        objective_value = -raw_objective if direction == ObjectiveDirection.MAXIMIZE else raw_objective
        constraints_passed = evaluate_constraints(metrics_config, computed_metrics)
        simulation_status = "mock_pass" if constraints_passed else "mock_constraint_fail"
        batch_id = (i // batch_size) + 1 if batch_size > 0 else 1

        row = LedgerRow(
            candidate_id=f"cand_{i + 1:03d}",
            parameters=params,
            metrics=computed_metrics,
            constraints_passed=constraints_passed,
            objective=objective_value,
            batch_id=batch_id,
            simulation_status=simulation_status,
            timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        write_ledger_row(project_dir, row)

        if best_objective is None or objective_value < best_objective:
            best_objective = objective_value
            best_candidate = BestCandidate(
                candidate_id=row.candidate_id,
                parameters=params,
                metrics=computed_metrics,
                constraints_passed=constraints_passed,
                objective=objective_value,
                batch_id=batch_id,
                timestamp_utc=row.timestamp_utc,
            )

    if best_candidate is not None:
        write_best_candidate(project_dir, best_candidate)
        best_id = best_candidate.candidate_id
    else:
        best_id = None

    completed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    state = OptimizerState(
        schema_version="1.0",
        project_name=bundle.project_config.project.name,
        algorithm=optimizer.algorithm.value,
        initialization=initialization,
        current_evaluations=n_actual,
        max_evaluations=effective_max,
        batch_size=batch_size,
        random_seed=seed,
        best_candidate_id=best_id,
        status="completed",
        started_at_utc=started_at,
        updated_at_utc=completed_at,
    )
    write_optimizer_state(project_dir, state)
    write_health_check(
        project_dir,
        current_evaluations=n_actual,
        max_evaluations=effective_max,
        best_candidate_id=best_id,
        last_batch_id=(
            ((n_actual - 1) // batch_size) + 1
            if batch_size > 0 and n_actual > 0
            else None
        ),
    )
    return state


def evaluate_objective_from_config(
    metrics_config: object, computed_metrics: dict[str, float]
) -> float:
    from hermes_workflow.schemas import MetricsConfig

    if not isinstance(metrics_config, MetricsConfig):
        raise TypeError(f"Expected MetricsConfig, got {type(metrics_config).__name__}")
    return evaluate_objective(metrics_config.objective.expression, computed_metrics)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_continuous_triple(
    lower_raw: str, upper_raw: str, step_raw: str
) -> tuple[tuple[Decimal, str], tuple[Decimal, str], tuple[Decimal, str]]:
    lower_parsed = _parse_continuous(lower_raw)
    upper_parsed = _parse_continuous(upper_raw)
    step_parsed = _parse_continuous(step_raw)
    if lower_parsed is None or upper_parsed is None or step_parsed is None:
        raise ValueError(
            f"cannot parse continuous values: {lower_raw}, {upper_raw}, {step_raw}"
        )
    return lower_parsed, upper_parsed, step_parsed


def _parse_continuous(raw: str) -> tuple[Decimal, str] | None:
    match = CONTINUOUS_RE.match(raw)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value"))
    except Exception:
        return None
    return value, match.group("unit") or ""


def _parse_constraint_value(value_raw: str) -> float | None:
    parsed = _parse_continuous(value_raw)
    if parsed is not None:
        return float(parsed[0])
    try:
        return float(value_raw)
    except ValueError:
        return None


def _check_constraint(metric_value: float, op: object, threshold: float) -> bool:
    from hermes_workflow.schemas import ConstraintOp

    if not isinstance(op, ConstraintOp):
        raise TypeError(f"Expected ConstraintOp, got {type(op).__name__}")
    if op == ConstraintOp.LT:
        return metric_value < threshold
    if op == ConstraintOp.LE:
        return metric_value <= threshold
    if op == ConstraintOp.GT:
        return metric_value > threshold
    if op == ConstraintOp.GE:
        return metric_value >= threshold
    return False


def _sample_grid(
    grid_by_name: dict[str, list[str]],
    n_candidates: int,
    seed: int,
    initialization: str,
) -> list[dict[str, str]]:
    import numpy as np

    variable_names = sorted(grid_by_name.keys())

    if initialization == "sobol" and _HAS_SCIPY:
        sampler = ScipySobol(d=len(variable_names), scramble=True, seed=seed)
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            raw_samples = sampler.random(n_candidates)
    elif initialization == "latin_hypercube" and _HAS_SCIPY:
        sampler = ScipyLatinHypercube(d=len(variable_names), seed=seed)
        raw_samples = sampler.random(n_candidates)
    else:
        rng = np.random.default_rng(seed)
        raw_samples = rng.random((n_candidates, len(variable_names)))

    candidates: list[dict[str, str]] = []
    for row in raw_samples:
        candidate: dict[str, str] = {}
        for i, name in enumerate(variable_names):
            grid = grid_by_name[name]
            idx = min(int(row[i] * len(grid)), len(grid) - 1)
            candidate[name] = grid[idx]
        candidates.append(candidate)

    return candidates


def _count_grid_combinations(grid_by_name: dict[str, list[str]]) -> int:
    total = 1
    for grid in grid_by_name.values():
        total *= len(grid)
    return total


def _fill_unique_candidates(
    candidates: list[dict[str, str]],
    grid_by_name: dict[str, list[str]],
    target: int,
) -> list[dict[str, str]]:
    seen = {tuple(sorted(candidate.items())) for candidate in candidates}
    result = list(candidates)
    variable_names = sorted(grid_by_name.keys())

    for values in itertools.product(*(grid_by_name[name] for name in variable_names)):
        candidate = dict(zip(variable_names, values, strict=True))
        key = tuple(sorted(candidate.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
        if len(result) >= target:
            break
    return result


def _deduplicate(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    result: list[dict[str, str]] = []
    for candidate in candidates:
        key = tuple(sorted(candidate.items()))
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result
