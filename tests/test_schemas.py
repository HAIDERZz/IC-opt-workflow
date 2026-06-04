from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes_workflow.schemas import (
    OptimizerAlgorithm,
    MetricsConfig,
    OptimizerConfig,
    ProjectConfig,
    SpectreConfig,
    SpectrePreset,
    VariablesConfig,
)


FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "bridge_test_inv" / "config"


def load_yaml(file_name: str) -> dict:
    return yaml.safe_load((FIXTURE_CONFIG / file_name).read_text(encoding="utf-8"))


def test_schema_models_parse_confirmed_contracts() -> None:
    project = ProjectConfig.model_validate(load_yaml("project_config.yaml"))
    variables = VariablesConfig.model_validate(load_yaml("variables.yaml"))
    metrics = MetricsConfig.model_validate(load_yaml("metrics.yaml"))
    spectre = SpectreConfig.model_validate(load_yaml("spectre.yaml"))
    optimizer = OptimizerConfig.model_validate(load_yaml("optimizer.yaml"))

    assert project.project.name == "bridge_test_inv"
    assert [variable.name for variable in variables.variables] == ["FN", "WN", "FP", "WP"]
    assert [metric.name for metric in metrics.metrics] == ["rise", "fall", "DC"]
    assert spectre.spectre.engine == "spectre_x"
    assert spectre.spectre.preset is SpectrePreset.AX
    assert optimizer.optimizer.algorithm is OptimizerAlgorithm.TURBO


def test_variables_reject_duplicate_names() -> None:
    payload = load_yaml("variables.yaml")
    payload["variables"][1]["name"] = "FN"

    with pytest.raises(ValidationError, match="variable names must be unique"):
        VariablesConfig.model_validate(payload)


def test_metrics_reject_empty_required_signals() -> None:
    payload = load_yaml("metrics.yaml")
    payload["metrics"][0]["required_signals"] = []

    with pytest.raises(ValidationError, match="required_signals must not be empty"):
        MetricsConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit", ""),
        ("maestro_formula", "   "),
    ],
)
def test_metrics_reject_empty_required_strings(field: str, value: str) -> None:
    payload = load_yaml("metrics.yaml")
    payload["metrics"][0][field] = value

    with pytest.raises(ValidationError):
        MetricsConfig.model_validate(payload)


def test_metrics_reject_empty_required_signal_names() -> None:
    payload = load_yaml("metrics.yaml")
    payload["metrics"][0]["required_signals"] = [""]

    with pytest.raises(ValidationError):
        MetricsConfig.model_validate(payload)


def test_spectre_rejects_non_spectre_x_engine() -> None:
    payload = load_yaml("spectre.yaml")
    payload["spectre"]["engine"] = "aps"

    with pytest.raises(ValidationError):
        SpectreConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parallel_jobs", "10"),
        ("threads_per_run", "10"),
        ("timeout_s", "3600"),
        ("keep_successful_runs", "false"),
    ],
)
def test_spectre_rejects_coerced_scalar_types(field: str, value: str) -> None:
    payload = load_yaml("spectre.yaml")
    payload["spectre"][field] = value

    with pytest.raises(ValidationError):
        SpectreConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("immutable_after_package", 1),
        ("allow_maestro_setup_modification", 0),
    ],
)
def test_project_safety_rejects_numeric_boolean_literals(
    field: str, value: int
) -> None:
    payload = load_yaml("project_config.yaml")
    payload["safety"][field] = value

    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(payload)


def test_optimizer_rejects_numeric_boolean_literal() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["deduplicate_candidates"] = 1

    with pytest.raises(ValidationError):
        OptimizerConfig.model_validate(payload)
