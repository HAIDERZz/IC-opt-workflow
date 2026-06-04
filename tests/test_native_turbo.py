from __future__ import annotations

import math
from pathlib import Path

from hermes_workflow.native_turbo import (
    evaluate_candidate_objective,
    load_native_turbo_contract,
    quantize_candidate,
)
from hermes_workflow.package import create_project_from_template
from hermes_workflow.schemas import (
    ConstraintOp,
    ConstraintSpec,
    MetricSpec,
    MetricsConfig,
    ObjectiveDirection,
    ObjectiveSpec,
    OptimizerAlgorithm,
    OptimizerConfig,
    OptimizerSettings,
    InitializationMethod,
    VariableKind,
    VariableSpec,
    VariablesConfig,
)


def _optimizer_config() -> OptimizerConfig:
    return OptimizerConfig(
        schema_version="1.0",
        optimizer=OptimizerSettings(
            algorithm=OptimizerAlgorithm.TURBO,
            initialization=InitializationMethod.SOBOL,
            max_evaluations=100,
            batch_size=1,
            random_seed=20260528,
            failure_penalty=1000.0,
            deduplicate_candidates=True,
        ),
    )


def _metrics_config(
    *,
    direction: ObjectiveDirection = ObjectiveDirection.MINIMIZE,
) -> MetricsConfig:
    return MetricsConfig(
        schema_version="1.0",
        metrics=[
            MetricSpec(
                name="delay",
                unit="ps",
                maestro_formula="delay",
                required_signals=["/out"],
            ),
            MetricSpec(
                name="gain",
                unit="dB",
                maestro_formula="gain",
                required_signals=["/out"],
            ),
        ],
        constraints=[
            ConstraintSpec(metric="delay", op=ConstraintOp.LE, value="100 ps"),
            ConstraintSpec(metric="gain", op=ConstraintOp.GE, value="10 dB"),
        ],
        objective=ObjectiveSpec(direction=direction, expression="delay / gain"),
    )


def test_load_native_turbo_contract_reads_existing_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    contract = load_native_turbo_contract(project_dir)

    assert [variable.name for variable in contract.variables.variables] == [
        "FN",
        "WN",
        "FP",
        "WP",
    ]
    assert contract.optimizer.optimizer.failure_penalty > 0
    assert contract.metrics.objective.expression


def test_quantize_candidate_snaps_and_formats_approved_variables() -> None:
    variables = VariablesConfig(
        schema_version="1.0",
        variables=[
            VariableSpec(
                name="FN",
                kind=VariableKind.INTEGER,
                lower="2",
                upper="12",
                step="1",
            ),
            VariableSpec(
                name="WN",
                kind=VariableKind.CONTINUOUS_STEP,
                lower="0.3u",
                upper="2.0u",
                step="0.1u",
            ),
        ],
    )

    assert quantize_candidate(variables, [11.6, 1.94]) == {"FN": "12", "WN": "1.9u"}
    assert quantize_candidate(variables, [0.0, 3.0]) == {"FN": "2", "WN": "2u"}


def test_missing_metric_returns_failure_penalty() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 50.0},
    )

    assert result.status == "metric_failed"
    assert result.objective == 1000.0
    assert result.fom is None
    assert result.constraints_passed is False
    assert result.issues == ["metric gain missing"]


def test_non_finite_metric_returns_failure_penalty() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": math.nan, "gain": 20.0},
    )

    assert result.status == "metric_failed"
    assert result.objective == 1000.0
    assert result.issues == ["metric delay non_finite"]


def test_constraint_violation_returns_penalty_plus_normalized_score() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 110.0, "gain": 5.0},
    )

    assert result.status == "constraint_failed"
    assert result.constraints_passed is False
    assert result.fom == 22.0
    assert result.constraint_penalty == 0.26
    assert result.objective == 1000.26
    assert result.issues == [
        "constraint delay le 100 ps violated by 110.0",
        "constraint gain ge 10 dB violated by 5.0",
    ]


def test_feasible_minimize_candidate_returns_fom() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 50.0, "gain": 20.0},
    )

    assert result.status == "feasible"
    assert result.constraints_passed is True
    assert result.fom == 2.5
    assert result.objective == 2.5
    assert result.constraint_penalty == 0.0
    assert result.issues == []


def test_feasible_maximize_candidate_returns_negative_fom_for_minimizer() -> None:
    metrics_config = _metrics_config(direction=ObjectiveDirection.MAXIMIZE)

    small_fom = evaluate_candidate_objective(
        metrics_config,
        _optimizer_config(),
        {"delay": 80.0, "gain": 40.0},
    )
    large_fom = evaluate_candidate_objective(
        metrics_config,
        _optimizer_config(),
        {"delay": 50.0, "gain": 10.0},
    )

    assert small_fom.fom == 2.0
    assert large_fom.fom == 5.0
    assert small_fom.objective == -2.0
    assert large_fom.objective == -5.0
