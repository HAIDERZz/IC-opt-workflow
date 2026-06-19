from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes_workflow.schemas import MetricsConfig, SpectreConfig
from hermes_workflow.validate import assert_valid_project, validate_project_files


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
                "testbench": "cg_nf",
                "expression": 'getData("NF" ?result "pnoise")',
                "output_format": "csv",
                "nil_policy": "fail",
            },
        ],
    }
    write_yaml(project_dir / "config" / "waveform_exports.yaml", waveform_payload)
    return project_dir


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

    report = validate_project_files(project_dir)

    assert report.ok is True, report.format()
