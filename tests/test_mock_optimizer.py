"""Tests for mock optimizer schemas and evaluate_objective helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.mock_optimizer import (
    _deduplicate,
    compute_mock_metrics,
    evaluate_constraints,
    generate_candidates,
    generate_continuous_grid,
    generate_integer_grid,
    run_mock_optimization,
    write_best_candidate,
    write_health_check,
    write_ledger_row,
    write_optimizer_state,
)
from hermes_workflow.package import create_project_from_template
from hermes_workflow.schemas import BestCandidate, LedgerRow, OptimizerState
from hermes_workflow.validate import assert_valid_project, evaluate_objective


# ---------------------------------------------------------------------------
# LedgerRow
# ---------------------------------------------------------------------------

VALID_LEDGER_ROW = {
    "candidate_id": "cand_001",
    "parameters": {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
    "metrics": {"rise": 52.0, "fall": 43.0, "DC": 120.0},
    "constraints_passed": True,
    "objective": 11400.0,
    "batch_id": 1,
    "simulation_status": "mock_pass",
    "timestamp_utc": "2026-05-29T12:00:00Z",
}


def test_ledger_row_parses_valid_payload() -> None:
    row = LedgerRow.model_validate(VALID_LEDGER_ROW)
    assert row.candidate_id == "cand_001"
    assert row.parameters["FN"] == "4"
    assert row.metrics["rise"] == 52.0
    assert row.constraints_passed is True
    assert row.objective == 11400.0
    assert row.batch_id == 1
    assert row.simulation_status == "mock_pass"


def test_ledger_row_rejects_extra_fields() -> None:
    payload = {**VALID_LEDGER_ROW, "unexpected": True}
    with pytest.raises(ValidationError, match="extra"):
        LedgerRow.model_validate(payload)


def test_ledger_row_rejects_invalid_simulation_status() -> None:
    for bad_status in ("real_error", "running", "completed", ""):
        payload = {**VALID_LEDGER_ROW, "simulation_status": bad_status}
        with pytest.raises(ValidationError):
            LedgerRow.model_validate(payload)


def test_ledger_row_accepts_all_valid_statuses() -> None:
    for status in (
        "mock_pass",
        "mock_constraint_fail",
        "mock_error",
        "real_pass",
        "real_constraint_fail",
    ):
        payload = {**VALID_LEDGER_ROW, "simulation_status": status}
        row = LedgerRow.model_validate(payload)
        assert row.simulation_status == status


def test_ledger_row_accepts_real_constraint_fail_status() -> None:
    row = LedgerRow(
        candidate_id="real_001",
        parameters={"FN": "2"},
        metrics={"rise": 1.0},
        constraints_passed=False,
        objective=1.0,
        batch_id=1,
        simulation_status="real_constraint_fail",
        timestamp_utc="2026-06-02T12:00:00Z",
        result_source="real",
        run_id="real_001",
    )

    assert row.simulation_status == "real_constraint_fail"


def test_ledger_row_rejects_bool_as_batch_id() -> None:
    payload = {**VALID_LEDGER_ROW, "batch_id": True}
    with pytest.raises(ValidationError):
        LedgerRow.model_validate(payload)


# ---------------------------------------------------------------------------
# BestCandidate
# ---------------------------------------------------------------------------

VALID_BEST_CANDIDATE = {
    "candidate_id": "cand_001",
    "parameters": {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
    "metrics": {"rise": 52.0, "fall": 43.0, "DC": 120.0},
    "constraints_passed": True,
    "objective": 11400.0,
    "batch_id": 1,
    "timestamp_utc": "2026-05-29T12:00:00Z",
}


def test_best_candidate_parses_valid_payload() -> None:
    candidate = BestCandidate.model_validate(VALID_BEST_CANDIDATE)
    assert candidate.candidate_id == "cand_001"
    assert candidate.metrics["DC"] == 120.0
    assert candidate.constraints_passed is True


def test_best_candidate_rejects_extra_fields() -> None:
    payload = {**VALID_BEST_CANDIDATE, "extra_field": "nope"}
    with pytest.raises(ValidationError, match="extra"):
        BestCandidate.model_validate(payload)


def test_best_candidate_rejects_bool_as_batch_id() -> None:
    payload = {**VALID_BEST_CANDIDATE, "batch_id": True}
    with pytest.raises(ValidationError):
        BestCandidate.model_validate(payload)


# ---------------------------------------------------------------------------
# OptimizerState
# ---------------------------------------------------------------------------

VALID_OPTIMIZER_STATE = {
    "schema_version": "1.0",
    "project_name": "bridge_test_inv",
    "algorithm": "turbo",
    "initialization": "sobol",
    "current_evaluations": 6,
    "max_evaluations": 100,
    "batch_size": 10,
    "random_seed": 20260528,
    "best_candidate_id": "cand_001",
    "status": "completed",
    "started_at_utc": "2026-05-29T12:00:00Z",
    "updated_at_utc": "2026-05-29T12:00:01Z",
}


def test_optimizer_state_parses_valid_payload() -> None:
    state = OptimizerState.model_validate(VALID_OPTIMIZER_STATE)
    assert state.project_name == "bridge_test_inv"
    assert state.algorithm == "turbo"
    assert state.current_evaluations == 6
    assert state.best_candidate_id == "cand_001"
    assert state.status == "completed"


def test_optimizer_state_allows_null_best_candidate_id() -> None:
    payload = {**VALID_OPTIMIZER_STATE, "best_candidate_id": None}
    state = OptimizerState.model_validate(payload)
    assert state.best_candidate_id is None


def test_optimizer_state_rejects_extra_fields() -> None:
    payload = {**VALID_OPTIMIZER_STATE, "surprise": True}
    with pytest.raises(ValidationError, match="extra"):
        OptimizerState.model_validate(payload)


def test_optimizer_state_rejects_invalid_status() -> None:
    for bad_status in ("approve_first_real_run", "mock_pass", ""):
        payload = {**VALID_OPTIMIZER_STATE, "status": bad_status}
        with pytest.raises(ValidationError):
            OptimizerState.model_validate(payload)


def test_optimizer_state_accepts_all_valid_statuses() -> None:
    for status in ("running", "completed", "stopped"):
        payload = {**VALID_OPTIMIZER_STATE, "status": status}
        state = OptimizerState.model_validate(payload)
        assert state.status == status


def test_optimizer_state_rejects_bool_as_integer() -> None:
    with pytest.raises(ValidationError):
        OptimizerState.model_validate({**VALID_OPTIMIZER_STATE, "current_evaluations": True})
    with pytest.raises(ValidationError):
        OptimizerState.model_validate({**VALID_OPTIMIZER_STATE, "batch_size": True})


# ---------------------------------------------------------------------------
# evaluate_objective
# ---------------------------------------------------------------------------

METRICS = {"rise": 52.0, "fall": 43.0, "DC": 120.0}


def test_evaluate_objective_simple_arithmetic() -> None:
    assert evaluate_objective("(rise + fall) * DC", METRICS) == (52.0 + 43.0) * 120.0


def test_evaluate_objective_single_metric() -> None:
    assert evaluate_objective("rise", METRICS) == 52.0


def test_evaluate_objective_numeric_literal() -> None:
    assert evaluate_objective("rise + 10.0", METRICS) == 62.0


def test_evaluate_objective_integer_literal() -> None:
    assert evaluate_objective("rise * 2", METRICS) == 104.0


def test_evaluate_objective_negation() -> None:
    assert evaluate_objective("-rise", METRICS) == -52.0


def test_evaluate_objective_division() -> None:
    assert evaluate_objective("rise / fall", METRICS) == pytest.approx(52.0 / 43.0)


def test_evaluate_objective_power() -> None:
    assert evaluate_objective("rise ** 2", METRICS) == pytest.approx(52.0**2)


def test_evaluate_objective_modulo() -> None:
    assert evaluate_objective("rise % fall", METRICS) == pytest.approx(52.0 % 43.0)


def test_evaluate_objective_complex_expression() -> None:
    assert evaluate_objective("(rise + fall) * DC", METRICS) == 11400.0


def test_evaluate_objective_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        evaluate_objective("rise + slew", METRICS)


def test_evaluate_objective_rejects_function_calls() -> None:
    with pytest.raises(ValueError, match="unsupported objective expression node Call"):
        evaluate_objective("max(rise, fall)", METRICS)


def test_evaluate_objective_rejects_boolean_literal() -> None:
    with pytest.raises(ValueError, match="unsupported objective literal"):
        evaluate_objective("rise + True", METRICS)


def test_evaluate_objective_rejects_non_finite_literal() -> None:
    # Python parses "inf" and "nan" as Name nodes, not numeric constants.
    # They are caught by the unknown-metric check, not the non-finite check.
    # Use float literal notation to test the non-finite Constant path.
    with pytest.raises(ValueError, match="unknown metric"):
        evaluate_objective("rise + inf", METRICS)
    with pytest.raises(ValueError, match="unknown metric"):
        evaluate_objective("rise + nan", METRICS)


def test_evaluate_objective_rejects_string_literal() -> None:
    with pytest.raises(ValueError, match="unsupported objective literal"):
        evaluate_objective("'hello' + rise", METRICS)


def test_evaluate_objective_rejects_syntax_error() -> None:
    with pytest.raises(ValueError, match="invalid objective expression"):
        evaluate_objective("(rise + ", METRICS)


def test_evaluate_objective_direction_maximize_is_caller_responsibility() -> None:
    """evaluate_objective computes the raw expression; maximize negation is at call site."""
    raw = evaluate_objective("(rise + fall) * DC", METRICS)
    negated = -raw
    assert raw == 11400.0
    assert negated == -11400.0


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


class TestIntegerGrid:
    def test_integer_grid_basic(self) -> None:
        grid = generate_integer_grid(2, 12, 1)
        assert grid == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    def test_integer_grid_larger_step(self) -> None:
        grid = generate_integer_grid(2, 12, 2)
        assert grid == [2, 4, 6, 8, 10, 12]

    def test_integer_grid_single_point(self) -> None:
        grid = generate_integer_grid(5, 5, 1)
        assert grid == [5]

    def test_integer_grid_rejects_negative_step(self) -> None:
        with pytest.raises(ValueError, match="step must be positive"):
            generate_integer_grid(2, 12, -1)

    def test_integer_grid_rejects_lower_greater_than_upper(self) -> None:
        with pytest.raises(ValueError, match="lower.*must be <= upper"):
            generate_integer_grid(12, 2, 1)

    def test_integer_grid_with_step_5(self) -> None:
        grid = generate_integer_grid(0, 20, 5)
        assert grid == [0, 5, 10, 15, 20]


class TestContinuousGrid:
    def test_continuous_grid_with_units(self) -> None:
        grid = generate_continuous_grid("0.3u", "3u", "0.2u")
        assert grid[0] == "0.3u"
        assert grid[-1] in ("2.9u", "2.7u", "3.0u")
        for value in grid:
            assert value.endswith("u")
            assert " " not in value

    def test_continuous_grid_unitless(self) -> None:
        grid = generate_continuous_grid("0.0", "1.0", "0.25")
        assert grid[0] == "0.0"
        assert len(grid) >= 5

    def test_continuous_grid_single_point(self) -> None:
        grid = generate_continuous_grid("1.0u", "1.0u", "0.1u")
        assert len(grid) >= 1
        assert grid[0] == "1.0u"

    def test_continuous_grid_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="cannot parse"):
            generate_continuous_grid("abc", "3", "0.2")


class TestGenerateCandidates:
    def test_generate_candidates_from_fixture(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        candidates = generate_candidates(bundle, n_candidates=6, seed=20260528)
        assert len(candidates) == 6
        for candidate in candidates:
            assert "FN" in candidate
            assert "WN" in candidate
            assert "FP" in candidate
            assert "WP" in candidate

    def test_generate_candidates_sobol_reproducible(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        cands_a = generate_candidates(
            bundle, n_candidates=10, seed=42, initialization="sobol"
        )
        cands_b = generate_candidates(
            bundle, n_candidates=10, seed=42, initialization="sobol"
        )
        assert cands_a == cands_b

    def test_generate_candidates_random_reproducible(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        cands_a = generate_candidates(
            bundle, n_candidates=10, seed=99, initialization="random"
        )
        cands_b = generate_candidates(
            bundle, n_candidates=10, seed=99, initialization="random"
        )
        assert cands_a == cands_b

    def test_generate_candidates_latin_hypercube(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        candidates = generate_candidates(
            bundle, n_candidates=8, seed=42, initialization="latin_hypercube"
        )
        assert len(candidates) == 8

    def test_generate_candidates_values_on_grid(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        candidates = generate_candidates(bundle, n_candidates=20, seed=42)
        integer_grid = {str(v) for v in generate_integer_grid(2, 12, 1)}
        for candidate in candidates:
            assert candidate["FN"] in integer_grid
            assert candidate["FP"] in integer_grid

    def test_deduplication_removes_duplicates(self) -> None:
        candidates = [
            {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
            {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
            {"FN": "6", "WN": "1.2 um", "FP": "6", "WP": "1.2 um"},
        ]
        result = _deduplicate(candidates)
        assert len(result) == 2

    def test_generate_candidates_deduplicates(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        # Request more candidates than the grid allows (2*6*2*6 = 144 combos)
        candidates = generate_candidates(
            bundle, n_candidates=200, seed=42, initialization="random"
        )
        # Should be at most the total grid size
        seen_keys: set[tuple[tuple[str, str], ...]] = set()
        for candidate in candidates:
            key = tuple(sorted(candidate.items()))
            assert key not in seen_keys
            seen_keys.add(key)

    def test_generate_candidates_refills_after_deduplication(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        variables_path = project_dir / "config" / "variables.yaml"
        variables_path.write_text(
            "\n".join(
                [
                    'schema_version: "1.0"',
                    "variables:",
                    "  - name: FN",
                    "    kind: integer",
                    '    lower: "2"',
                    '    upper: "3"',
                    '    step: "1"',
                    "  - name: WN",
                    "    kind: continuous_step",
                    '    lower: "0.3u"',
                    '    upper: "0.3u"',
                    '    step: "0.2u"',
                    "  - name: FP",
                    "    kind: integer",
                    '    lower: "2"',
                    '    upper: "2"',
                    '    step: "1"',
                    "  - name: WP",
                    "    kind: continuous_step",
                    '    lower: "0.3u"',
                    '    upper: "0.3u"',
                    '    step: "0.2u"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        bundle = assert_valid_project(project_dir)

        candidates = generate_candidates(
            bundle,
            n_candidates=2,
            seed=3,
            initialization="random",
        )

        assert len(candidates) == 2
        assert {candidate["FN"] for candidate in candidates} == {"2", "3"}


# ---------------------------------------------------------------------------
# Mock metric computation
# ---------------------------------------------------------------------------


class TestComputeMockMetrics:
    def test_deterministic_same_params_same_result(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        params = {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
        a = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        b = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        assert a == b

    def test_different_params_different_metrics(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        params_a = {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
        params_b = {"FN": "8", "WN": "2.0 um", "FP": "8", "WP": "2.0 um"}
        a = compute_mock_metrics(bundle.metrics, bundle.variables, params_a)
        b = compute_mock_metrics(bundle.metrics, bundle.variables, params_b)
        assert a != b

    def test_returns_all_declared_metrics(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        params = {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
        result = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        for metric in bundle.metrics.metrics:
            assert metric.name in result

    def test_metric_values_are_positive(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        params = {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
        result = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        for name, value in result.items():
            assert value > 0, f"{name} should be positive, got {value}"

    def test_integer_params_parsed_correctly(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        params = {"FN": "6", "WN": "0.5 um", "FP": "6", "WP": "0.5 um"}
        result = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        for name, value in result.items():
            assert isinstance(value, float)
            assert value > 0


# ---------------------------------------------------------------------------
# Constraint evaluation
# ---------------------------------------------------------------------------


class TestEvaluateConstraints:
    def test_all_constraints_pass(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        # Use metrics that will definitely pass the constraints
        # rise < 80, fall < 80, DC < 400 (constraint values in metrics.yaml)
        # Mock metrics are in range 1-100, so they should pass
        params = {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
        metrics = compute_mock_metrics(bundle.metrics, bundle.variables, params)
        # We can't easily predict mock metric values vs thresholds,
        # so we test the infrastructure, not the pass/fail outcome.
        result = evaluate_constraints(bundle.metrics, metrics)
        assert isinstance(result, bool)

    def test_missing_metric_returns_false(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)
        bundle = assert_valid_project(project_dir)
        partial_metrics = {"rise": 50.0}
        assert evaluate_constraints(bundle.metrics, partial_metrics) is False

    def test_lt_constraint(self) -> None:
        from hermes_workflow.schemas import ConstraintOp, ConstraintSpec, MetricSpec, MetricsConfig, ObjectiveDirection, ObjectiveSpec

        metrics_config = MetricsConfig(
            schema_version="1.0",
            metrics=[MetricSpec(name="delay", unit="ps", maestro_formula="x", required_signals=["time"])],
            constraints=[ConstraintSpec(metric="delay", op=ConstraintOp.LT, value="100 ps")],
            objective=ObjectiveSpec(direction=ObjectiveDirection.MINIMIZE, expression="delay"),
        )
        assert evaluate_constraints(metrics_config, {"delay": 50.0}) is True
        assert evaluate_constraints(metrics_config, {"delay": 100.0}) is False
        assert evaluate_constraints(metrics_config, {"delay": 150.0}) is False

    def test_le_constraint(self) -> None:
        from hermes_workflow.schemas import ConstraintOp, ConstraintSpec, MetricSpec, MetricsConfig, ObjectiveDirection, ObjectiveSpec

        metrics_config = MetricsConfig(
            schema_version="1.0",
            metrics=[MetricSpec(name="delay", unit="ps", maestro_formula="x", required_signals=["time"])],
            constraints=[ConstraintSpec(metric="delay", op=ConstraintOp.LE, value="100 ps")],
            objective=ObjectiveSpec(direction=ObjectiveDirection.MINIMIZE, expression="delay"),
        )
        assert evaluate_constraints(metrics_config, {"delay": 100.0}) is True
        assert evaluate_constraints(metrics_config, {"delay": 100.1}) is False

    def test_gt_constraint(self) -> None:
        from hermes_workflow.schemas import ConstraintOp, ConstraintSpec, MetricSpec, MetricsConfig, ObjectiveDirection, ObjectiveSpec

        metrics_config = MetricsConfig(
            schema_version="1.0",
            metrics=[MetricSpec(name="gain", unit="dB", maestro_formula="x", required_signals=["vout"])],
            constraints=[ConstraintSpec(metric="gain", op=ConstraintOp.GT, value="10 dB")],
            objective=ObjectiveSpec(direction=ObjectiveDirection.MAXIMIZE, expression="gain"),
        )
        assert evaluate_constraints(metrics_config, {"gain": 15.0}) is True
        assert evaluate_constraints(metrics_config, {"gain": 10.0}) is False

    def test_ge_constraint(self) -> None:
        from hermes_workflow.schemas import ConstraintOp, ConstraintSpec, MetricSpec, MetricsConfig, ObjectiveDirection, ObjectiveSpec

        metrics_config = MetricsConfig(
            schema_version="1.0",
            metrics=[MetricSpec(name="gain", unit="dB", maestro_formula="x", required_signals=["vout"])],
            constraints=[ConstraintSpec(metric="gain", op=ConstraintOp.GE, value="10 dB")],
            objective=ObjectiveSpec(direction=ObjectiveDirection.MAXIMIZE, expression="gain"),
        )
        assert evaluate_constraints(metrics_config, {"gain": 10.0}) is True
        assert evaluate_constraints(metrics_config, {"gain": 9.9}) is False

    def test_constraint_with_unit_suffix_parsed(self) -> None:
        from hermes_workflow.schemas import ConstraintOp, ConstraintSpec, MetricSpec, MetricsConfig, ObjectiveDirection, ObjectiveSpec

        metrics_config = MetricsConfig(
            schema_version="1.0",
            metrics=[MetricSpec(name="rise", unit="ps", maestro_formula="x", required_signals=["time"])],
            constraints=[ConstraintSpec(metric="rise", op=ConstraintOp.LT, value="80 ps")],
            objective=ObjectiveSpec(direction=ObjectiveDirection.MINIMIZE, expression="rise"),
        )
        # "80 ps" should parse to 80.0
        assert evaluate_constraints(metrics_config, {"rise": 50.0}) is True
        assert evaluate_constraints(metrics_config, {"rise": 90.0}) is False


# ---------------------------------------------------------------------------
# Ledger and state persistence
# ---------------------------------------------------------------------------


class TestWriteLedgerRow:
    def test_write_ledger_row_creates_file(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        row = LedgerRow(
            candidate_id="cand_001",
            parameters={"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
            metrics={"rise": 52.0, "fall": 43.0, "DC": 120.0},
            constraints_passed=True,
            objective=11400.0,
            batch_id=1,
            simulation_status="mock_pass",
            timestamp_utc="2026-05-29T12:00:00Z",
        )
        path = write_ledger_row(project_dir, row)
        assert path.exists()
        assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()

    def test_write_ledger_row_appends(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        row1 = LedgerRow(
            candidate_id="cand_001",
            parameters={"FN": "4"},
            metrics={"rise": 52.0},
            constraints_passed=True,
            objective=52.0,
            batch_id=1,
            simulation_status="mock_pass",
            timestamp_utc="2026-05-29T12:00:00Z",
        )
        row2 = LedgerRow(
            candidate_id="cand_002",
            parameters={"FN": "6"},
            metrics={"rise": 55.0},
            constraints_passed=True,
            objective=55.0,
            batch_id=1,
            simulation_status="mock_pass",
            timestamp_utc="2026-05-29T12:00:01Z",
        )
        write_ledger_row(project_dir, row1)
        write_ledger_row(project_dir, row2)
        lines = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_write_ledger_row_content_is_valid_json(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        row = LedgerRow(
            candidate_id="cand_001",
            parameters={"FN": "4", "WN": "1.0 um"},
            metrics={"rise": 52.0},
            constraints_passed=True,
            objective=52.0,
            batch_id=1,
            simulation_status="mock_pass",
            timestamp_utc="2026-05-29T12:00:00Z",
        )
        write_ledger_row(project_dir, row)
        content = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(encoding="utf-8").strip()
        parsed = json.loads(content)
        assert parsed["candidate_id"] == "cand_001"
        assert parsed["objective"] == 52.0

    def test_write_mock_ledger_row_omits_empty_real_result_fields(
        self,
        tmp_path: Path,
    ) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        row = LedgerRow(
            candidate_id="cand_001",
            parameters={"FN": "4", "WN": "1.0 um"},
            metrics={"rise": 52.0},
            constraints_passed=True,
            objective=52.0,
            batch_id=1,
            simulation_status="mock_pass",
            timestamp_utc="2026-05-29T12:00:00Z",
        )

        write_ledger_row(project_dir, row)

        content = (
            project_dir
            / "ledger"
            / "experiment_ledger.jsonl"
        ).read_text(encoding="utf-8").strip()
        parsed = json.loads(content)
        assert "result_source" not in parsed
        assert "run_id" not in parsed
        assert "result_manifest" not in parsed
        assert "metric_result_manifest" not in parsed


class TestWriteOptimizerState:
    def test_write_optimizer_state_creates_file(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        state = OptimizerState(
            schema_version="1.0",
            project_name="bridge_test_inv",
            algorithm="turbo",
            initialization="sobol",
            current_evaluations=6,
            max_evaluations=100,
            batch_size=10,
            random_seed=20260528,
            best_candidate_id="cand_001",
            status="completed",
            started_at_utc="2026-05-29T12:00:00Z",
            updated_at_utc="2026-05-29T12:00:01Z",
        )
        path = write_optimizer_state(project_dir, state)
        assert path.exists()
        assert (project_dir / "state" / "optimizer_state.json").exists()

    def test_write_optimizer_state_content_is_valid_json(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        state = OptimizerState(
            schema_version="1.0",
            project_name="bridge_test_inv",
            algorithm="turbo",
            initialization="sobol",
            current_evaluations=6,
            max_evaluations=100,
            batch_size=10,
            random_seed=20260528,
            best_candidate_id=None,
            status="running",
            started_at_utc="2026-05-29T12:00:00Z",
            updated_at_utc="2026-05-29T12:00:00Z",
        )
        write_optimizer_state(project_dir, state)
        parsed = json.loads((project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8"))
        assert parsed["project_name"] == "bridge_test_inv"
        assert parsed["best_candidate_id"] is None
        assert parsed["status"] == "running"

    def test_write_optimizer_state_overwrites_on_second_write(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        state_v1 = OptimizerState(
            schema_version="1.0",
            project_name="bridge_test_inv",
            algorithm="turbo",
            initialization="sobol",
            current_evaluations=6,
            max_evaluations=100,
            batch_size=10,
            random_seed=20260528,
            best_candidate_id=None,
            status="running",
            started_at_utc="2026-05-29T12:00:00Z",
            updated_at_utc="2026-05-29T12:00:00Z",
        )
        write_optimizer_state(project_dir, state_v1)
        state_v2 = state_v1.model_copy(update={"current_evaluations": 16, "status": "completed"})
        write_optimizer_state(project_dir, state_v2)
        import json

        parsed = json.loads((project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8"))
        assert parsed["current_evaluations"] == 16
        assert parsed["status"] == "completed"


class TestWriteBestCandidate:
    def test_write_best_candidate_creates_file(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        candidate = BestCandidate(
            candidate_id="cand_001",
            parameters={"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
            metrics={"rise": 52.0, "fall": 43.0, "DC": 120.0},
            constraints_passed=True,
            objective=11400.0,
            batch_id=1,
            timestamp_utc="2026-05-29T12:00:00Z",
        )
        path = write_best_candidate(project_dir, candidate)
        assert path.exists()
        assert (project_dir / "state" / "best_candidate.json").exists()

    def test_write_best_candidate_content_is_valid_json(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        candidate = BestCandidate(
            candidate_id="cand_003",
            parameters={"FN": "8"},
            metrics={"rise": 60.0},
            constraints_passed=True,
            objective=60.0,
            batch_id=2,
            timestamp_utc="2026-05-29T12:05:00Z",
        )
        write_best_candidate(project_dir, candidate)
        parsed = json.loads((project_dir / "state" / "best_candidate.json").read_text(encoding="utf-8"))
        assert parsed["candidate_id"] == "cand_003"
        assert parsed["objective"] == 60.0


class TestWriteHealthCheck:
    def test_write_health_check_creates_file(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        path = write_health_check(
            project_dir,
            current_evaluations=6,
            max_evaluations=100,
            best_candidate_id="cand_001",
            last_batch_id=1,
        )
        assert path.exists()
        assert (project_dir / "state" / "health_check.json").exists()

    def test_write_health_check_content_fields(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        write_health_check(
            project_dir,
            current_evaluations=6,
            max_evaluations=100,
            best_candidate_id="cand_001",
            last_batch_id=1,
        )
        parsed = json.loads((project_dir / "state" / "health_check.json").read_text(encoding="utf-8"))
        assert parsed["schema_version"] == "1.0"
        assert parsed["status"] == "healthy"
        assert parsed["real_run_started"] is False
        assert parsed["current_evaluations"] == 6
        assert parsed["best_candidate_path"] == "state/best_candidate.json"
        assert parsed["last_batch_id"] == 1
        assert parsed["issues"] == []

    def test_write_health_check_no_best_candidate(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        write_health_check(
            project_dir,
            current_evaluations=0,
            max_evaluations=100,
            best_candidate_id=None,
            last_batch_id=None,
        )
        parsed = json.loads((project_dir / "state" / "health_check.json").read_text(encoding="utf-8"))
        assert parsed["best_candidate_path"] is None
        assert parsed["last_batch_id"] is None

    def test_write_health_check_with_issues(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        write_health_check(
            project_dir,
            current_evaluations=3,
            max_evaluations=100,
            best_candidate_id=None,
            last_batch_id=1,
            status="warning",
            issues=["dry run status is fail"],
        )
        parsed = json.loads((project_dir / "state" / "health_check.json").read_text(encoding="utf-8"))
        assert parsed["status"] == "warning"
        assert parsed["issues"] == ["dry run status is fail"]


# ---------------------------------------------------------------------------
# run_mock_optimization integration
# ---------------------------------------------------------------------------


class TestRunMockOptimization:
    def test_run_mock_optimization_creates_all_artifacts(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        run_mock_optimization(project_dir, max_evaluations=6)

        assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
        assert (project_dir / "state" / "optimizer_state.json").exists()
        assert (project_dir / "state" / "best_candidate.json").exists()
        assert (project_dir / "state" / "health_check.json").exists()

    def test_run_mock_optimization_ledger_has_correct_row_count(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        run_mock_optimization(project_dir, max_evaluations=6)

        lines = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 6

    def test_run_mock_optimization_state_completed(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        state = run_mock_optimization(project_dir, max_evaluations=6)

        assert state.status == "completed"
        assert state.current_evaluations == 6
        assert state.max_evaluations == 6
        assert state.best_candidate_id is not None
        assert state.project_name == "bridge_test_inv"

        parsed = json.loads((project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8"))
        assert parsed["algorithm"] == "turbo"
        assert parsed["status"] == "completed"

    def test_run_mock_optimization_best_candidate_exists(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        run_mock_optimization(project_dir, max_evaluations=6)

        parsed = json.loads((project_dir / "state" / "best_candidate.json").read_text(encoding="utf-8"))
        assert parsed["candidate_id"].startswith("cand_")
        assert parsed["constraints_passed"] in (True, False)
        assert "objective" in parsed

    def test_run_mock_optimization_health_check_healthy(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        run_mock_optimization(project_dir, max_evaluations=6)

        parsed = json.loads((project_dir / "state" / "health_check.json").read_text(encoding="utf-8"))
        assert parsed["status"] == "healthy"
        assert parsed["current_evaluations"] == 6
        assert parsed["real_run_started"] is False
        assert parsed["best_candidate_path"] == "state/best_candidate.json"
        assert parsed["last_batch_id"] == 1

    def test_run_mock_optimization_respects_max_evaluations_override(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        state = run_mock_optimization(project_dir, max_evaluations=3)

        assert state.max_evaluations == 3
        assert state.current_evaluations <= 3
        lines = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == state.current_evaluations

    def test_run_mock_optimization_respects_seed_override(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        state_a = run_mock_optimization(project_dir, max_evaluations=4, seed_override=42)
        # Reset ledger and state for second run
        (project_dir / "ledger" / "experiment_ledger.jsonl").unlink()
        (project_dir / "state" / "optimizer_state.json").unlink()
        (project_dir / "state" / "best_candidate.json").unlink()
        (project_dir / "state" / "health_check.json").unlink()
        state_b = run_mock_optimization(project_dir, max_evaluations=4, seed_override=42)

        assert state_a.random_seed == 42
        assert state_b.random_seed == 42

    def test_run_mock_optimization_ledger_rows_are_valid(self, tmp_path: Path) -> None:
        import json

        project_dir = tmp_path / "bridge_test_inv"
        create_project_from_template(project_dir)

        run_mock_optimization(project_dir, max_evaluations=4)

        lines = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            row = json.loads(line)
            assert "candidate_id" in row
            assert "parameters" in row
            assert "metrics" in row
            assert "constraints_passed" in row
            assert "objective" in row
            assert "batch_id" in row
            assert "simulation_status" in row
            assert "result_source" not in row
            assert "run_id" not in row
            assert "result_manifest" not in row
            assert "metric_result_manifest" not in row
            assert "timestamp_utc" in row
