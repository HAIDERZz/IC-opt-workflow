from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.history_warm_start import (
    HISTORY_WARM_START_AUDIT_MD_RELATIVE,
    HISTORY_WARM_START_AUDIT_RELATIVE,
    audit_history_warm_start,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.validate import assert_valid_project
from tests.project_factory import create_generic_project, write_yaml

NO_ACCEPTED_ISSUE = (
    "history warm-start has no accepted observations; "
    "OpenBox will start without transfer history"
)

# Current-project contract produced by create_generic_project():
#   variables: VAR_INT (integer 1..5 step 1), VAR_WIDTH (continuous_step 0.1u..0.5u step 0.1u)
#   metrics:   metric_gain, metric_power
#   objective: maximize (metric_gain - metric_power)
#   constraint: metric_power lt 1e-3 W
_VAR_INT = {"name": "VAR_INT", "kind": "integer", "lower": "1", "upper": "5", "step": "1"}
_VAR_WIDTH = {
    "name": "VAR_WIDTH",
    "kind": "continuous_step",
    "lower": "0.1u",
    "upper": "0.5u",
    "step": "0.1u",
}
_EXTRA_VAR = {"name": "EXTRA", "kind": "integer", "lower": "0", "upper": "10", "step": "1"}


def _write_evaluations(project_dir: Path, rows: list[str]) -> None:
    """Write raw JSONL lines (allows injecting malformed rows)."""
    path = project_dir / EVALUATIONS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in rows), encoding="utf-8")


def _current_project_with_warm_start(
    tmp_path: Path,
    sources: list[dict[str, object]],
    *,
    enabled: bool = True,
    max_observations: int | None = None,
) -> tuple[Path, object]:
    project_dir = create_generic_project(tmp_path, name="current_project")
    settings: dict[str, object] = {
        "enabled": enabled,
        "sources": sources,
        "warm_start_strategy": "topk",
    }
    if max_observations is not None:
        settings["max_observations"] = max_observations
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {"schema_version": "1.0", "history_warm_start": settings},
    )
    bundle = assert_valid_project(project_dir)
    return project_dir, bundle


def _matching_source(tmp_path: Path, rows: list[str], name: str = "source_project") -> Path:
    source = create_generic_project(tmp_path, name=name)
    _write_evaluations(source, rows)
    return source


def _audit_matching_source(
    tmp_path: Path, rows: list[str], **kwargs: object
) -> object:
    source = _matching_source(tmp_path, rows)
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}], **kwargs
    )
    return audit_history_warm_start(project_dir, bundle)


def _params(int_value: str = "2", width_value: str = "0.3u") -> dict[str, str]:
    return {"VAR_INT": int_value, "VAR_WIDTH": width_value}


def _metrics(gain: float = 1.0, power: float = 0.0005) -> dict[str, float]:
    return {"metric_gain": gain, "metric_power": power}


def _row(
    *,
    parameters: dict[str, str] | None = None,
    metrics: dict[str, float] | None = None,
    status: str = "feasible",
    evaluation_index: int = 1,
    run_id: str = "real_001",
    objective: float = 0.0,
) -> str:
    return json.dumps(
        {
            "parameters": parameters if parameters is not None else _params(),
            "metrics": metrics if metrics is not None else _metrics(),
            "status": status,
            "evaluation_index": evaluation_index,
            "run_id": run_id,
            "objective": objective,
        }
    )


def _overwrite_source_variables(source: Path, variables: list[dict[str, str]]) -> None:
    write_yaml(
        source / "config" / "variables.yaml",
        {"schema_version": "1.0", "variables": variables},
    )


def _matching_metric_gain() -> dict[str, object]:
    return {
        "name": "metric_gain",
        "unit": "V/V",
        "maestro_formula": 'value(v("/OUT") 1n)',
        "required_signals": ["/OUT"],
        "ocean": {
            "expression": 'value(v("/OUT") 1n)',
            "result": "tran",
            "expression_source": "user_approved",
            "source_reference": "test_factory:generic:metric_gain",
            "expected_value_type": "real_scalar",
            "nil_policy": "fail",
            "non_finite_policy": "fail",
        },
    }


def _matching_metric_power() -> dict[str, object]:
    return {
        "name": "metric_power",
        "unit": "W",
        "maestro_formula": 'value(i("/VDD") 1n)',
        "required_signals": ["/VDD"],
        "ocean": {
            "expression": 'value(i("/VDD") 1n)',
            "result": "tran",
            "expression_source": "user_approved",
            "source_reference": "test_factory:generic:metric_power",
            "expected_value_type": "real_scalar",
            "nil_policy": "fail",
            "non_finite_policy": "fail",
        },
    }


def _overwrite_source_metrics(source: Path, metrics: list[dict[str, object]]) -> None:
    write_yaml(
        source / "config" / "metrics.yaml",
        {
            "schema_version": "1.0",
            "metrics": metrics,
            "constraints": [{"metric": "metric_power", "op": "lt", "value": "1e-3 W"}],
            "objective": {
                "direction": "maximize",
                "expression": "metric_gain - metric_power",
            },
        },
    )


def _source_with_overwrites(
    tmp_path: Path,
    *,
    variables: list[dict[str, str]] | None = None,
    metrics: list[dict[str, object]] | None = None,
    rows: list[str] | None = None,
) -> Path:
    source = create_generic_project(tmp_path, name="source_project")
    if variables is not None:
        _overwrite_source_variables(source, variables)
    if metrics is not None:
        _overwrite_source_metrics(source, metrics)
    if rows is not None:
        _write_evaluations(source, rows)
    return source


# ---------------------------------------------------------------------------
# Task 2 regression: disabled modes and source-level failures
# ---------------------------------------------------------------------------


def test_missing_warm_start_config_returns_disabled(tmp_path: Path) -> None:
    project_dir = create_generic_project(tmp_path, name="current_project")
    bundle = assert_valid_project(project_dir)

    audit = audit_history_warm_start(project_dir, bundle)

    assert audit.enabled is False
    assert audit.status == "disabled"
    assert audit.sources == []
    assert audit.accepted_observation_count == 0
    assert audit.rejected_observation_count == 0
    assert audit.accepted_observations == []
    assert audit.openbox_transfer_learning.enabled is False
    assert audit.openbox_transfer_learning.warm_start_strategy is None
    assert audit.issues == []

    json_path = project_dir / HISTORY_WARM_START_AUDIT_RELATIVE
    md_path = project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "disabled"
    assert payload["enabled"] is False
    assert payload["openbox_transfer_learning"]["enabled"] is False


def test_disabled_warm_start_returns_disabled(tmp_path: Path) -> None:
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": "/tmp/ignored_source", "label": "ignored"}],
        enabled=False,
    )

    audit = audit_history_warm_start(project_dir, bundle)

    assert audit.enabled is False
    assert audit.status == "disabled"
    assert audit.sources == []
    assert audit.openbox_transfer_learning.enabled is False
    assert (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).exists()
    assert (project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE).exists()


def test_relative_source_path_resolves_relative_to_current_project(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, name="current_project")
    source_dir = create_generic_project(project_dir, name="prev_round")
    _write_evaluations(source_dir, [_row()])
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "prev_round", "label": "round1"}],
                "warm_start_strategy": "topk",
            },
        },
    )
    bundle = assert_valid_project(project_dir)

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.path == str((project_dir / "prev_round").resolve())
    assert source.candidate_trace_count == 1
    assert source.accepted_observation_count == 1


def test_missing_source_path_creates_source_path_missing(tmp_path: Path) -> None:
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(tmp_path / "does_not_exist"), "label": "missing"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any("source_path_missing" in issue for issue in source.issues)
    assert source.candidate_trace_count == 0
    assert source.rejected_observation_count == 0


def test_invalid_source_project_creates_source_not_valid_project(
    tmp_path: Path,
) -> None:
    not_a_project = tmp_path / "not_a_project"
    not_a_project.mkdir()
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(not_a_project), "label": "bad"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any(
        "source_not_valid_project" in issue for issue in source.issues
    )
    assert source.candidate_trace_count == 0


def test_source_missing_evaluations_creates_missing_optimizer_evaluations(
    tmp_path: Path,
) -> None:
    source_dir = create_generic_project(tmp_path, name="source_project")
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any(
        "missing_optimizer_evaluations" in issue for issue in source.issues
    )
    assert source.candidate_trace_count == 0


def test_malformed_jsonl_row_is_counted_and_does_not_abort_source(
    tmp_path: Path,
) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [
            _row(evaluation_index=1),
            "{not valid json",
            _row(evaluation_index=2),
        ],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["invalid_optimizer_evaluations"] == 1
    # Source was not aborted: both valid rows were read and accepted.
    assert source.candidate_trace_count == 3
    assert source.accepted_observation_count == 2
    assert source.rejected_observation_count == 1
    assert source.status == "accepted"


# ---------------------------------------------------------------------------
# Task 3: compatibility and re-evaluation
# ---------------------------------------------------------------------------


def test_matching_source_accepts_rows(tmp_path: Path) -> None:
    audit = _audit_matching_source(tmp_path, [_row(objective=99999.0)])

    source = audit.sources[0]
    assert source.status == "accepted"
    assert source.candidate_trace_count == 1
    assert source.accepted_observation_count == 1
    assert source.rejected_observation_count == 0
    assert source.rejection_reasons == {}

    assert audit.status == "completed"
    assert audit.accepted_observation_count == 1
    assert NO_ACCEPTED_ISSUE not in audit.issues

    observation = audit.accepted_observations[0]
    assert observation.source_label == "round1"
    assert observation.source_evaluation_index == 1
    assert observation.source_run_id == "real_001"
    assert observation.parameters == {"VAR_INT": "2", "VAR_WIDTH": "0.3u"}
    assert observation.metrics == {"metric_gain": 1.0, "metric_power": 0.0005}
    assert observation.status == "feasible"
    assert observation.fom == pytest.approx(0.9995)
    assert observation.objective == pytest.approx(-0.9995)
    assert observation.objective != 99999.0
    assert observation.constraint_residuals == [pytest.approx(-0.0005)]
    assert observation.issues == []


def test_extra_source_variable_rejects_source(tmp_path: Path) -> None:
    source = _source_with_overwrites(
        tmp_path,
        variables=[_VAR_INT, _VAR_WIDTH, _EXTRA_VAR],
        rows=[_row()],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}]
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source_audit = audit.sources[0]
    assert source_audit.status == "rejected"
    assert any("variable_set_mismatch" in issue for issue in source_audit.issues)
    assert source_audit.candidate_trace_count == 0
    assert audit.accepted_observations == []


def test_missing_source_variable_rejects_source(tmp_path: Path) -> None:
    source = _source_with_overwrites(
        tmp_path,
        variables=[_VAR_INT],
        rows=[_row()],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}]
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source_audit = audit.sources[0]
    assert source_audit.status == "rejected"
    assert any("variable_set_mismatch" in issue for issue in source_audit.issues)
    assert source_audit.candidate_trace_count == 0


def test_row_parameter_key_mismatch_rejects_row(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [
            _row(parameters={"VAR_INT": "2"}),  # missing VAR_WIDTH
            _row(parameters={"VAR_INT": "2", "VAR_WIDTH": "0.3u", "EXTRA": "1"}),
        ],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["variable_set_mismatch"] == 2
    assert source.candidate_trace_count == 2
    assert source.accepted_observation_count == 0
    assert source.rejected_observation_count == 2


def test_out_of_range_row_rejected(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(parameters=_params(int_value="99"))],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["out_of_current_space"] == 1
    assert source.accepted_observation_count == 0


def test_off_grid_row_rejected(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(parameters=_params(width_value="0.35u"))],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["out_of_current_space"] == 1
    assert source.accepted_observation_count == 0


def test_unparsable_parameter_rejected(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(parameters=_params(int_value="not_a_number"))],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["invalid_numeric_value"] == 1
    assert source.accepted_observation_count == 0


def test_missing_metric_rejected(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(metrics={"metric_power": 0.0005})],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["missing_required_metric"] == 1
    assert source.accepted_observation_count == 0


def test_metric_definition_mismatch_rejects_source(tmp_path: Path) -> None:
    mismatched_gain = {**_matching_metric_gain(), "unit": "mV/mV"}
    source = _source_with_overwrites(
        tmp_path,
        metrics=[mismatched_gain, _matching_metric_power()],
        rows=[_row()],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}]
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source_audit = audit.sources[0]
    assert source_audit.status == "rejected"
    assert any(
        "metric_definition_mismatch" in issue for issue in source_audit.issues
    )
    assert source_audit.candidate_trace_count == 0


@pytest.mark.parametrize(
    "ocean_overrides",
    [
        {"expression": 'value(v("/OUT") 2n)'},
        {"result": "dc"},
        {"source_reference": "different:reference"},
    ],
)
def test_metric_ocean_field_mismatch_rejects_source(
    tmp_path: Path, ocean_overrides: dict[str, object]
) -> None:
    base_gain = _matching_metric_gain()
    ocean = {**base_gain["ocean"], **ocean_overrides}
    mismatched_gain = {**base_gain, "ocean": ocean}
    source = _source_with_overwrites(
        tmp_path,
        metrics=[mismatched_gain, _matching_metric_power()],
        rows=[_row()],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}]
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source_audit = audit.sources[0]
    assert source_audit.status == "rejected"
    assert any(
        "metric_definition_mismatch" in issue for issue in source_audit.issues
    )


def test_non_finite_metric_rejected(tmp_path: Path) -> None:
    # 1e309 overflows to +inf when parsed by json.loads.
    non_finite_line = (
        '{"parameters": {"VAR_INT": "2", "VAR_WIDTH": "0.3u"}, '
        '"metrics": {"metric_gain": 1.0, "metric_power": 1e309}, '
        '"status": "feasible", "evaluation_index": 1, "run_id": "real_001"}'
    )
    audit = _audit_matching_source(tmp_path, [non_finite_line])

    source = audit.sources[0]
    assert source.rejection_reasons["invalid_numeric_value"] == 1
    assert source.accepted_observation_count == 0


def test_old_failed_status_rejected(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(status="metric_failed")],
    )

    source = audit.sources[0]
    assert source.rejection_reasons["failed_or_incomplete_run"] == 1
    assert source.accepted_observation_count == 0


def test_objective_recomputed_from_current_config(tmp_path: Path) -> None:
    audit = _audit_matching_source(tmp_path, [_row(objective=99999.0)])

    observation = audit.accepted_observations[0]
    # Current objective = -(metric_gain - metric_power); the old row objective
    # (99999) must be ignored.
    assert observation.objective == pytest.approx(-0.9995)
    assert observation.objective != 99999.0


def test_constraint_failed_row_with_complete_metrics_accepted(tmp_path: Path) -> None:
    audit = _audit_matching_source(
        tmp_path,
        [_row(metrics=_metrics(power=0.002))],  # power > 1e-3 -> constraint violated
    )

    source = audit.sources[0]
    assert source.accepted_observation_count == 1
    observation = audit.accepted_observations[0]
    assert observation.status == "constraint_failed"
    assert observation.fom == pytest.approx(0.998)
    assert observation.objective == pytest.approx(1000001.0)


def test_constraint_residuals_follow_sign_convention(tmp_path: Path) -> None:
    # Feasible: power 0.0005 < 0.001 -> residual (lt) = value - threshold < 0.
    feasible = _audit_matching_source(tmp_path, [_row(metrics=_metrics(power=0.0005))])
    assert feasible.accepted_observations[0].constraint_residuals == [
        pytest.approx(-0.0005)
    ]

    # Violated: power 0.002 > 0.001 -> residual = 0.001 > 0.
    violated = _audit_matching_source(tmp_path, [_row(metrics=_metrics(power=0.002))])
    assert violated.accepted_observations[0].constraint_residuals == [
        pytest.approx(0.001)
    ]


def test_max_observations_keeps_best_and_records_overflow(tmp_path: Path) -> None:
    # Two feasible rows; recomputed objectives -0.9995 (best) and -0.4995.
    audit = _audit_matching_source(
        tmp_path,
        [
            _row(metrics=_metrics(gain=1.0, power=0.0005), evaluation_index=1),
            _row(metrics=_metrics(gain=0.5, power=0.0005), evaluation_index=2),
        ],
        max_observations=1,
    )

    source = audit.sources[0]
    assert source.accepted_observation_count == 1
    assert source.rejection_reasons["max_observations_exceeded"] == 1
    assert source.rejected_observation_count == 1

    assert audit.accepted_observation_count == 1
    assert len(audit.accepted_observations) == 1
    # Lower recomputed objective is retained.
    assert audit.accepted_observations[0].objective == pytest.approx(-0.9995)


# ---------------------------------------------------------------------------
# Task 2 regression: report contents
# ---------------------------------------------------------------------------


def test_reports_contain_expected_status_counts_issues(tmp_path: Path) -> None:
    source = _matching_source(tmp_path, [_row(evaluation_index=1), _row(evaluation_index=2)])
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path, sources=[{"path": str(source), "label": "round1"}]
    )
    audit_history_warm_start(project_dir, bundle)

    payload = json.loads(
        (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "1.0"
    assert payload["enabled"] is True
    assert payload["status"] == "completed"
    assert payload["accepted_observation_count"] == 2
    assert payload["rejected_observation_count"] == 0
    assert payload["sources"][0]["accepted_observation_count"] == 2
    assert len(payload["accepted_observations"]) == 2
    assert NO_ACCEPTED_ISSUE not in payload["issues"]

    markdown = (
        project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    ).read_text(encoding="utf-8")
    assert "Status: completed" in markdown
    assert "Accepted observations: 2" in markdown
    assert "Rejected observations: 0" in markdown
