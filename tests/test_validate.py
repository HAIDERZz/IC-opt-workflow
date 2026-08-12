from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes_workflow.schemas import MetricsConfig, SpectreConfig
from hermes_workflow.validate import (
    assert_valid_project,
    evaluate_objective,
    validate_project_files,
)
from tests.project_factory import create_generic_project


FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "bridge_test_inv"


def copy_fixture_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    shutil.copytree(FIXTURE_PROJECT, project_dir)
    return project_dir


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_valid_project_files_pass(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)

    report = validate_project_files(project_dir)

    assert report.ok is True
    assert report.issues == []
    assert report.format() == "validation passed"
    assert_valid_project(project_dir)


def test_batch_size_must_not_exceed_spectre_parallel_jobs(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = read_yaml(optimizer_path)
    payload["optimizer"]["batch_size"] = 11
    write_yaml(optimizer_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.message == "optimizer.batch_size must be <= spectre.parallel_jobs"
        for issue in report.issues
    )


def test_objective_expression_allows_safe_math_functions(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "min(max(rise, fall), ln(DC))"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is True


def test_objective_expression_rejects_unknown_function_calls(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "abs(rise)"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "unsupported objective function abs" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_bare_function_name(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "ln"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective function ln must be called" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_unknown_metric_names(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "(rise + slew) * DC"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective references unknown metric slew" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_boolean_literals(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "rise + True"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "unsupported objective literal True" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_non_finite_literals(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "rise + 1e309"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective numeric literals must be finite" in issue.message
        for issue in report.issues
    )


def test_objective_expression_rejects_integer_literal_outside_float_range(
    tmp_path: Path,
) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "1" + ("0" * 400)
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective numeric literals must be finite" in issue.message
        for issue in report.issues
    )


@pytest.mark.parametrize(
    "expression",
    ["ln(-1)", "(-1) ** 0.5", "1 / 0", "1e308 * 1e308"],
)
def test_objective_expression_rejects_invalid_constant_result(
    tmp_path: Path,
    expression: str,
) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = expression
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "objective constant expression is invalid" in issue.message
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("expression", "metrics"),
    [
        ("ln(metric)", {"metric": -1.0}),
        ("metric ** 0.5", {"metric": -1.0}),
        ("1 / metric", {"metric": 0.0}),
        ("metric + 1", {"metric": None}),
    ],
)
def test_evaluate_objective_normalizes_domain_and_type_errors(
    expression: str,
    metrics: dict[str, float | None],
) -> None:
    with pytest.raises(ValueError):
        evaluate_objective(expression, metrics)  # type: ignore[arg-type]


def test_netlist_paths_must_stay_under_expected_directories(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    project_config_path = project_dir / "config" / "project_config.yaml"
    payload = read_yaml(project_config_path)
    payload["netlist"]["exported_input_scs"] = "../input.scs"
    write_yaml(project_config_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "netlist.exported_input_scs must stay under netlists/exported/"
        in issue.message
        for issue in report.issues
    )


def test_continuous_step_accepts_attached_unit_suffixes(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["lower"] = "0.3um"
    payload["variables"][1]["upper"] = "3um"
    payload["variables"][1]["step"] = "0.2um"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is True
    assert report.issues == []


def test_continuous_step_rejects_whitespace_unit_suffixes(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["lower"] = "0.3 um"
    payload["variables"][1]["upper"] = "3 um"
    payload["variables"][1]["step"] = "0.2 um"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "WN lower must use a Spectre-safe attached unit suffix" in issue.message
        for issue in report.issues
    )


def test_continuous_step_allows_off_grid_upper_bound(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["lower"] = "0.3u"
    payload["variables"][1]["upper"] = "1.0u"
    payload["variables"][1]["step"] = "0.2u"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is True
    assert report.issues == []


def test_continuous_step_units_must_match(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["step"] = "200n"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "WN lower, upper, and step unit suffixes must match" in issue.message
        for issue in report.issues
    )


def test_metrics_config_accepts_approved_ocean_formula() -> None:
    payload = {
        "schema_version": "1.0",
        "metrics": [
            {
                "name": "rise",
                "unit": "s",
                "maestro_formula": 'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")',
                "required_signals": ["/VOUT"],
                "ocean": {
                    "expression": 'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")',
                    "result": "tran",
                    "expression_source": "user_approved",
                    "source_reference": "maestro_output:rise",
                    "expected_value_type": "real_scalar",
                    "nil_policy": "fail",
                    "non_finite_policy": "fail",
                },
            }
        ],
        "constraints": [],
        "objective": {
            "direction": "minimize",
            "expression": "rise",
        },
    }

    config = MetricsConfig.model_validate(payload)

    assert config.metrics[0].ocean is not None
    assert config.metrics[0].ocean.result == "tran"
    assert config.metrics[0].ocean.expression_source == "user_approved"


@pytest.mark.parametrize(
    ("ocean_overrides", "expected_message"),
    [
        ({"expression": ""}, "String should have at least 1 character"),
        ({"expected_value_type": "waveform"}, "Input should be 'real_scalar'"),
        ({"nil_policy": "allow"}, "Input should be 'fail'"),
        ({"non_finite_policy": "allow"}, "Input should be 'fail'"),
        ({"expression_source": "agent_discovered"}, "Input should be"),
        (
            {"expression": 'value(VT("{{VOUT}}") 1n)'},
            "ocean.expression must not contain template placeholders",
        ),
    ],
)
def test_metrics_config_rejects_invalid_ocean_formula_policy(
    ocean_overrides: dict,
    expected_message: str,
) -> None:
    ocean = {
        "expression": 'value(VT("/VOUT") 1n)',
        "result": "tran",
        "expression_source": "user_approved",
        "source_reference": "maestro_output:rise",
        "expected_value_type": "real_scalar",
        "nil_policy": "fail",
        "non_finite_policy": "fail",
    }
    ocean.update(ocean_overrides)
    payload = {
        "schema_version": "1.0",
        "metrics": [
            {
                "name": "rise",
                "unit": "s",
                "maestro_formula": 'value(VT("/VOUT") 1n)',
                "required_signals": ["/VOUT"],
                "ocean": ocean,
            }
        ],
        "constraints": [],
        "objective": {"direction": "minimize", "expression": "rise"},
    }

    with pytest.raises(ValidationError, match=expected_message):
        MetricsConfig.model_validate(payload)


def test_spectre_config_accepts_psfxl_for_ocean_backend() -> None:
    config = SpectreConfig.model_validate(
        {
            "schema_version": "1.0",
            "spectre": {
                "engine": "spectre_x",
                "preset": "ax",
                "output_format": "psfxl",
                "threads_per_run": 10,
                "parallel_jobs": 10,
                "timeout_s": 3600,
                "require_license_check": True,
                "keep_failed_runs": True,
                "keep_successful_runs": True,
            },
        }
    )

    assert config.spectre.output_format == "psfxl"


def _make_fix_run_project(tmp_path: Path) -> Path:
    """Copy the optimizer fixture and convert it into fix-run shape:
    delete optimizer-only configs, add workflow.yaml + fixed_points.yaml +
    waveform_exports.yaml."""
    project_dir = copy_fixture_project(tmp_path)
    (project_dir / "config" / "optimizer.yaml").unlink()
    (project_dir / "config" / "metrics.yaml").unlink()
    (project_dir / "config" / "workflow.yaml").write_text(
        "schema_version: '1.0'\nmode: fix_run\nstarting_run_id: real_001\n",
        encoding="utf-8",
    )
    variables_path = project_dir / "config" / "variables.yaml"
    variables = read_yaml(variables_path)
    parameters = {var["name"]: str(var["lower"]) for var in variables["variables"]}
    fixed_points_payload = {
        "schema_version": "1.0",
        "points": [
            {"candidate_id": "user_point_001", "parameters": parameters},
        ],
    }
    write_yaml(project_dir / "config" / "fixed_points.yaml", fixed_points_payload)
    waveform_payload = {
        "schema_version": "1.0",
        "exports": [
            {
                "name": "nf_pnoise",
                "expression": 'getData("NF" ?result "pnoise")',
                "output_format": "csv",
                "nil_policy": "fail",
            },
        ],
    }
    write_yaml(project_dir / "config" / "waveform_exports.yaml", waveform_payload)
    return project_dir


def _add_two_testbenches(project_dir: Path) -> None:
    write_yaml(
        project_dir / "config" / "testbenches.yaml",
        {
            "schema_version": "1.0",
            "testbenches": [
                {
                    "id": "cg_nf",
                    "maestro_point_root": "/remote/cg_nf",
                    "virtuoso_library": "test_lib",
                    "cell": "Mixer",
                    "design_view": "schematic",
                    "maestro_view": "maestro",
                    "test_name": "CG_NF",
                    "corner": "tt",
                },
                {
                    "id": "iip3",
                    "maestro_point_root": "/remote/iip3",
                    "virtuoso_library": "test_lib",
                    "cell": "Mixer",
                    "design_view": "schematic",
                    "maestro_view": "maestro",
                    "test_name": "IIP3",
                    "corner": "tt",
                },
            ],
        },
    )


def test_validate_optimizer_project_still_requires_metrics_yaml(tmp_path: Path) -> None:
    """Optimizer mode (no workflow.yaml) must keep treating metrics.yaml as
    required. Removing it must produce a validation issue. Locks in the
    B-FIXRUN-03 regression direction."""
    project_dir = copy_fixture_project(tmp_path)
    (project_dir / "config" / "metrics.yaml").unlink()

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "metrics.yaml" in issue.file and "missing" in issue.message
        for issue in report.issues
    )


def test_validate_optimizer_project_still_requires_optimizer_yaml(
    tmp_path: Path,
) -> None:
    """Optimizer mode (no workflow.yaml) must keep treating optimizer.yaml
    as required."""
    project_dir = copy_fixture_project(tmp_path)
    (project_dir / "config" / "optimizer.yaml").unlink()

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "optimizer.yaml" in issue.file and "missing" in issue.message
        for issue in report.issues
    )


def test_validate_fix_run_project_accepts_no_optimizer_or_metrics_yaml(
    tmp_path: Path,
) -> None:
    """Fix-run mode (workflow.yaml mode=fix_run) is allowed to omit
    optimizer.yaml and metrics.yaml as long as fixed_points.yaml exists
    and at least one of metrics.yaml/waveform_exports.yaml exists."""
    project_dir = _make_fix_run_project(tmp_path)

    report = validate_project_files(project_dir)

    assert report.ok is True, report.format()


def test_validate_fix_run_project_requires_metrics_or_waveform_exports(
    tmp_path: Path,
) -> None:
    """Fix-run mode must still require at least one of metrics.yaml or
    waveform_exports.yaml. Removing both must fail validation."""
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "waveform_exports.yaml").unlink()

    report = validate_project_files(project_dir)

    assert report.ok is False
    issue_text = report.format()
    assert (
        "metrics.yaml" in issue_text or "waveform_exports.yaml" in issue_text
    )


def test_validate_fix_run_project_accepts_metrics_only(tmp_path: Path) -> None:
    """Fix-run with metrics.yaml but no waveform_exports.yaml is OK."""
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "waveform_exports.yaml").unlink()
    # Restore metrics.yaml from the optimizer fixture
    optimizer_fixture = FIXTURE_PROJECT / "config" / "metrics.yaml"
    shutil.copy2(optimizer_fixture, project_dir / "config" / "metrics.yaml")
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics = read_yaml(metrics_path)
    metrics["constraints"] = []
    metrics["objective"] = None
    write_yaml(metrics_path, metrics)

    report = validate_project_files(project_dir)

    assert report.ok is True, report.format()


def test_validate_single_testbench_rejects_metric_route(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "waveform_exports.yaml").unlink()
    shutil.copy2(
        FIXTURE_PROJECT / "config" / "metrics.yaml",
        project_dir / "config" / "metrics.yaml",
    )
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics = read_yaml(metrics_path)
    metrics["constraints"] = []
    metrics["objective"] = None
    metrics["metrics"][0]["testbench"] = "ignored_route"
    write_yaml(metrics_path, metrics)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "metrics[0].testbench"
        and "must not declare testbench for a single-testbench project"
        in issue.message
        for issue in report.issues
    )


@pytest.mark.parametrize("route", [None, "typo"])
def test_validate_multi_testbench_requires_valid_waveform_route(
    tmp_path: Path,
    route: str | None,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    _add_two_testbenches(project_dir)
    waveform_path = project_dir / "config" / "waveform_exports.yaml"
    payload = read_yaml(waveform_path)
    if route is None:
        payload["exports"][0].pop("testbench", None)
    else:
        payload["exports"][0]["testbench"] = route
    write_yaml(waveform_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "exports[0].testbench"
        and (
            "must declare testbench" in issue.message
            or "references unknown testbench typo" in issue.message
        )
        for issue in report.issues
    )


def test_validate_multi_testbench_requires_measurement_for_each_testbench(
    tmp_path: Path,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    _add_two_testbenches(project_dir)
    waveform_path = project_dir / "config" / "waveform_exports.yaml"
    payload = read_yaml(waveform_path)
    payload["exports"][0]["testbench"] = "cg_nf"
    write_yaml(waveform_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/testbenches.yaml"
        and issue.path == "testbenches[1].id"
        and "testbench iip3 must have at least one routed metric or waveform export"
        in issue.message
        for issue in report.issues
    )


def test_validate_multi_testbench_combines_metric_and_waveform_routes(
    tmp_path: Path,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    _add_two_testbenches(project_dir)
    waveform_path = project_dir / "config" / "waveform_exports.yaml"
    waveforms = read_yaml(waveform_path)
    waveforms["exports"][0]["testbench"] = "cg_nf"
    write_yaml(waveform_path, waveforms)

    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics = read_yaml(FIXTURE_PROJECT / "config" / "metrics.yaml")
    metrics["metrics"] = [metrics["metrics"][0]]
    metrics["metrics"][0]["testbench"] = "iip3"
    metrics["constraints"] = []
    metrics["objective"] = None
    write_yaml(metrics_path, metrics)

    report = validate_project_files(project_dir)

    assert report.ok is True, report.format()


@pytest.mark.parametrize(
    ("parameter", "value", "expected"),
    [
        ("FN", "99", "outside approved bounds"),
        ("FN", "2.5", "must be an integer"),
        ("WN", "0.35u", "is not aligned to approved step"),
        ("WN", "0.3n", "unit suffix"),
    ],
)
def test_validate_fixed_points_against_variable_contract(
    tmp_path: Path,
    parameter: str,
    value: str,
    expected: str,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    fixed_path = project_dir / "config" / "fixed_points.yaml"
    payload = read_yaml(fixed_path)
    payload["points"][0]["parameters"][parameter] = value
    write_yaml(fixed_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "points[0].parameters" and expected in issue.message
        for issue in report.issues
    )


def test_validate_fixed_point_requires_complete_parameter_set(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    fixed_path = project_dir / "config" / "fixed_points.yaml"
    payload = read_yaml(fixed_path)
    payload["points"][0]["parameters"].pop("FN")
    write_yaml(fixed_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "points[0].parameters"
        and "candidate parameters must match variables.yaml" in issue.message
        for issue in report.issues
    )


def test_validate_fix_run_rejects_run_id_range_overflow(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    workflow_path = project_dir / "config" / "workflow.yaml"
    workflow = read_yaml(workflow_path)
    workflow["starting_run_id"] = "real_999"
    write_yaml(workflow_path, workflow)
    fixed_path = project_dir / "config" / "fixed_points.yaml"
    fixed = read_yaml(fixed_path)
    fixed["points"].append(
        {"candidate_id": "user_point_002", "parameters": fixed["points"][0]["parameters"]}
    )
    write_yaml(fixed_path, fixed)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("would exceed real_999" in issue.message for issue in report.issues)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("80e-12 Hz", "unit 'Hz' does not match metric unit 's'"),
        ("80e-12", "finite numeric threshold followed by unit 's'"),
        ("NaN s", "finite numeric threshold followed by unit 's'"),
    ],
)
def test_validate_constraint_value_and_unit(
    tmp_path: Path,
    value: str,
    expected: str,
) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics = read_yaml(metrics_path)
    metrics["constraints"][0]["value"] = value
    write_yaml(metrics_path, metrics)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "constraints[0].value"
        and expected in issue.message
        for issue in report.issues
    )


def test_validate_metric_result_selector_is_safe_identifier(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics = read_yaml(metrics_path)
    metrics["metrics"][0]["ocean"]["result"] = 'tran);system("touch /tmp/x")'
    write_yaml(metrics_path, metrics)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == "metrics.0.ocean.result"
        and "ocean.result must match" in issue.message
        for issue in report.issues
    )


def test_validate_fix_run_rejects_unused_objective_and_constraints(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "waveform_exports.yaml").unlink()
    shutil.copy2(
        FIXTURE_PROJECT / "config" / "metrics.yaml",
        project_dir / "config" / "metrics.yaml",
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("objective is not supported for fix_run" in issue.message for issue in report.issues)
    assert any("constraints are not supported for fix_run" in issue.message for issue in report.issues)


@pytest.mark.parametrize(
    ("field", "value"),
    [("objective_policy", "worst_case"), ("constraint_policy", "all_corners")],
)
def test_validate_fix_run_rejects_unused_corner_aggregation_policy(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    payload = {
        "schema_version": "1.0",
        "objective_policy": "nominal",
        "constraint_policy": "nominal",
        "corners": [{"id": "nominal"}],
    }
    payload[field] = value
    write_yaml(project_dir / "config" / "process_corners.yaml", payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.path == field
        and f"{field} must be nominal for fix_run workflow" in issue.message
        for issue in report.issues
    )


def test_nominal_corner_policy_requires_explicit_nominal_corner_id(
    tmp_path: Path,
) -> None:
    project_dir = copy_fixture_project(tmp_path)
    write_yaml(
        project_dir / "config" / "process_corners.yaml",
        {
            "schema_version": "1.0",
            "objective_policy": "nominal",
            "constraint_policy": "all_corners",
            "corners": [{"id": "tt"}, {"id": "ss"}],
        },
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        "nominal policy requires a corner with id 'nominal'" in issue.message
        for issue in report.issues
    )


def test_validate_project_files_uses_injected_model_file_checker(
    tmp_path: Path,
) -> None:
    project_dir = copy_fixture_project(tmp_path)
    remote_model = "/remote/pdk/models/device.scs"
    write_yaml(
        project_dir / "config" / "process_corners.yaml",
        {
            "schema_version": "1.0",
            "objective_policy": "worst_case",
            "constraint_policy": "all_corners",
            "corners": [{"id": "external_model", "model_file": remote_model}],
        },
    )
    checked: list[str] = []

    structural_report = validate_project_files(project_dir)
    local_report = validate_project_files(
        project_dir,
        model_file_is_readable=lambda path: Path(path).is_file(),
    )
    remote_report = validate_project_files(
        project_dir,
        model_file_is_readable=lambda path: checked.append(path) is None,
    )

    assert structural_report.ok is True, structural_report.format()
    assert local_report.ok is False
    assert any(
        issue.path == "corners[0].model_file"
        and "missing or unreadable" in issue.message
        for issue in local_report.issues
    )
    assert remote_report.ok is True, remote_report.format()
    assert checked == [remote_model]


def test_validate_fix_run_loads_workflow_and_fixed_points_into_bundle(
    tmp_path: Path,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)

    bundle = assert_valid_project(project_dir)

    assert bundle.workflow is not None
    assert bundle.workflow.mode == "fix_run"
    assert bundle.fixed_points is not None
    assert bundle.fixed_points.points[0].candidate_id == "user_point_001"


def test_validate_fix_run_requires_workflow_yaml(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "workflow.yaml").unlink()

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/workflow.yaml"
        and issue.message == "workflow.yaml is required when fixed_points.yaml is present"
        for issue in report.issues
    )


def test_validate_workflow_rejects_unknown_mode(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    workflow_path = project_dir / "config" / "workflow.yaml"
    workflow = read_yaml(workflow_path)
    workflow["mode"] = "characterize"
    write_yaml(workflow_path, workflow)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/workflow.yaml"
        and issue.path == "mode"
        and "Input should be 'optimize' or 'fix_run'" in issue.message
        for issue in report.issues
    )


def test_validate_workflow_rejects_invalid_yaml(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    (project_dir / "config" / "workflow.yaml").write_text(
        "schema_version: '1.0'\nmode: [\n",
        encoding="utf-8",
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/workflow.yaml"
        and issue.message.startswith("invalid YAML:")
        for issue in report.issues
    )


def test_validate_optimize_rejects_fixed_points_yaml(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables = read_yaml(project_dir / "config" / "variables.yaml")
    parameters = {var["name"]: str(var["lower"]) for var in variables["variables"]}
    write_yaml(
        project_dir / "config" / "fixed_points.yaml",
        {
            "schema_version": "1.0",
            "points": [
                {"candidate_id": "unexpected_point", "parameters": parameters}
            ],
        },
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/fixed_points.yaml"
        and issue.message == "fixed_points.yaml is not supported for optimize workflow"
        for issue in report.issues
    )


def test_validate_optimize_rejects_waveform_exports_yaml(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    write_yaml(
        project_dir / "config" / "waveform_exports.yaml",
        {
            "schema_version": "1.0",
            "exports": [
                {
                    "name": "unexpected_export",
                    "testbench": "cg_nf",
                    "expression": 'getData("NF" ?result "pnoise")',
                    "output_format": "csv",
                    "nil_policy": "fail",
                }
            ],
        },
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/waveform_exports.yaml"
        and issue.message
        == "waveform_exports.yaml is not supported for optimize workflow"
        for issue in report.issues
    )


def test_validate_fix_run_rejects_optimizer_yaml(tmp_path: Path) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    shutil.copy2(
        FIXTURE_PROJECT / "config" / "optimizer.yaml",
        project_dir / "config" / "optimizer.yaml",
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/optimizer.yaml"
        and issue.message == "optimizer.yaml is not supported for fix_run workflow"
        for issue in report.issues
    )


def test_validate_fix_run_rejects_disabled_history_warm_start_yaml(
    tmp_path: Path,
) -> None:
    project_dir = _make_fix_run_project(tmp_path)
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {"enabled": False, "sources": []},
        },
    )

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.file == "config/history_warm_start.yaml"
        and issue.message
        == "history_warm_start.yaml is not supported for fix_run workflow"
        for issue in report.issues
    )


def test_assert_valid_project_loads_history_warm_start(tmp_path: Path) -> None:
    project_dir = create_generic_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer = read_yaml(optimizer_path)
    optimizer["optimizer"].update(
        {
            "algorithm": "openbox",
            "strategy": "openbox_auto",
        }
    )
    write_yaml(optimizer_path, optimizer)
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "/tmp/old_project", "label": "round1"}],
                "max_observations": 200,
                "warm_start_strategy": "topk",
            },
        },
    )

    bundle = assert_valid_project(project_dir)

    assert bundle.history_warm_start is not None
    settings = bundle.history_warm_start.history_warm_start
    assert settings.enabled is True
    assert settings.sources[0].path == "/tmp/old_project"
    assert settings.sources[0].label == "round1"
    assert settings.max_observations == 200
    assert settings.warm_start_strategy == "topk"


def test_assert_valid_project_rejects_enabled_history_warm_start_for_turbo(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer = read_yaml(optimizer_path)
    optimizer["optimizer"].update(
        {
            "algorithm": "turbo",
            "strategy": "turbo_trust_region",
            "openbox": None,
            "turbo": {
                "snap_to_step": True,
                "duplicate_handling": "resample",
            },
        }
    )
    write_yaml(optimizer_path, optimizer)
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "/tmp/old_project"}],
            },
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            "history_warm_start.enabled=true requires the OpenBox optimizer "
            "backend; resolved backend is native_turbo"
        ),
    ):
        assert_valid_project(project_dir)


def test_assert_valid_project_allows_disabled_history_warm_start_for_turbo(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer = read_yaml(optimizer_path)
    optimizer["optimizer"].update(
        {
            "algorithm": "turbo",
            "strategy": "turbo_trust_region",
            "openbox": None,
            "turbo": {
                "snap_to_step": True,
                "duplicate_handling": "resample",
            },
        }
    )
    write_yaml(optimizer_path, optimizer)
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": False,
                "sources": [],
            },
        },
    )

    bundle = assert_valid_project(project_dir)

    assert bundle.history_warm_start is not None
    assert bundle.history_warm_start.history_warm_start.enabled is False


def test_assert_valid_project_rejects_enabled_history_warm_start_for_fix_run(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, workflow_mode="fix_run")
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "/tmp/old_project"}],
            },
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            "history_warm_start.enabled=true is only supported for "
            "optimize workflow"
        ),
    ):
        assert_valid_project(project_dir)


def test_assert_valid_project_without_history_warm_start_is_none(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)

    bundle = assert_valid_project(project_dir)

    assert bundle.history_warm_start is None
