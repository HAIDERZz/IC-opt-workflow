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
    TestbenchesConfig as BenchesConfigModel,
    VariablesConfig,
)


FIXTURE_CONFIG = (
    Path(__file__).parent.parent
    / "src"
    / "hermes_workflow"
    / "templates"
    / "spectre_maestro_project"
    / "config"
)


def load_yaml(file_name: str) -> dict:
    return yaml.safe_load((FIXTURE_CONFIG / file_name).read_text(encoding="utf-8"))


def test_schema_models_parse_confirmed_contracts() -> None:
    project = ProjectConfig.model_validate(load_yaml("project_config.yaml"))
    variables = VariablesConfig.model_validate(load_yaml("variables.yaml"))
    metrics = MetricsConfig.model_validate(load_yaml("metrics.yaml"))
    spectre = SpectreConfig.model_validate(load_yaml("spectre.yaml"))
    optimizer = OptimizerConfig.model_validate(load_yaml("optimizer.yaml"))

    assert project.project.name == "mixer_cg_nf_opt"
    assert [variable.name for variable in variables.variables] == [
        "F",
        "W",
        "L",
        "VB_LO",
    ]
    assert [metric.name for metric in metrics.metrics] == ["NF_3G"]
    assert spectre.spectre.engine == "spectre_x"
    assert spectre.spectre.preset is SpectrePreset.AX
    assert optimizer.optimizer.algorithm is OptimizerAlgorithm.OPENBOX


def test_variables_reject_duplicate_names() -> None:
    payload = load_yaml("variables.yaml")
    payload["variables"][1]["name"] = "F"

    with pytest.raises(ValidationError, match="variable names must be unique"):
        VariablesConfig.model_validate(payload)


def test_metrics_allow_empty_required_signals() -> None:
    payload = load_yaml("metrics.yaml")
    payload["metrics"][0]["required_signals"] = []

    metrics = MetricsConfig.model_validate(payload)

    assert metrics.metrics[0].required_signals == []


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


def test_spectre_rejects_psfascii_output_format() -> None:
    payload = load_yaml("spectre.yaml")
    payload["spectre"]["output_format"] = "psfascii"

    with pytest.raises(ValidationError, match="psfxl"):
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


def test_optimizer_rejects_non_string_strategy_as_validation_error() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "openbox"
    payload["optimizer"]["strategy"] = 1

    with pytest.raises(ValidationError, match="optimizer.strategy must be a string"):
        OptimizerConfig.model_validate(payload)


def test_optimizer_accepts_cpu_thread_limit() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["optimizer_cpu_threads"] = 3

    optimizer = OptimizerConfig.model_validate(payload)

    assert optimizer.optimizer.optimizer_cpu_threads == 3


def test_optimizer_rejects_invalid_cpu_thread_limit() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["optimizer_cpu_threads"] = 0

    with pytest.raises(ValidationError):
        OptimizerConfig.model_validate(payload)


def test_optimizer_accepts_openbox_algorithm() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "openbox"

    optimizer = OptimizerConfig.model_validate(payload)

    assert optimizer.optimizer.algorithm is OptimizerAlgorithm.OPENBOX


def test_optimizer_accepts_openbox_strategy_settings() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "openbox"
    payload["optimizer"]["strategy"] = "openbox_gp_eic"
    payload["optimizer"]["openbox"] = {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        "initial_trials": "auto",
    }

    optimizer = OptimizerConfig.model_validate(payload)

    assert optimizer.optimizer.strategy.value == "openbox_gp_eic"
    assert optimizer.optimizer.openbox is not None
    assert optimizer.optimizer.openbox.initial_trials == "auto"


def test_optimizer_accepts_turbo_strategy_settings() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "turbo"
    payload["optimizer"]["strategy"] = "turbo_trust_region"
    payload["optimizer"]["turbo"] = {
        "snap_to_step": True,
        "duplicate_handling": "resample",
    }

    optimizer = OptimizerConfig.model_validate(payload)

    assert optimizer.optimizer.strategy.value == "turbo_trust_region"
    assert optimizer.optimizer.turbo is not None
    assert optimizer.optimizer.turbo.duplicate_handling == "resample"


def test_optimizer_rejects_incompatible_strategy_for_algorithm() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "turbo"
    payload["optimizer"]["strategy"] = "openbox_gp_eic"

    with pytest.raises(
        ValidationError,
        match="optimizer.strategy openbox_gp_eic requires optimizer.algorithm=openbox",
    ):
        OptimizerConfig.model_validate(payload)


def test_optimizer_rejects_openbox_eic_strategy_alias() -> None:
    payload = load_yaml("optimizer.yaml")
    payload["optimizer"]["algorithm"] = "openbox"
    payload["optimizer"]["strategy"] = "openbox_eic"

    with pytest.raises(ValidationError, match="eic is an acquisition function"):
        OptimizerConfig.model_validate(payload)


def test_testbenches_config_rejects_duplicate_ids() -> None:
    payload = {
        "schema_version": "1.0",
        "testbenches": [
            {
                "id": "cg_nf",
                "maestro_point_root": "/tmp/cg_nf",
                "virtuoso_library": "MixerLib",
                "cell": "Mixer",
                "design_view": "schematic",
                "maestro_view": "maestro",
                "test_name": "CG_NF_Test",
                "corner": "Nominal",
            },
            {
                "id": "cg_nf",
                "maestro_point_root": "/tmp/iip3",
                "virtuoso_library": "MixerLib",
                "cell": "Mixer",
                "design_view": "schematic",
                "maestro_view": "maestro",
                "test_name": "IIP3_Test",
                "corner": "Nominal",
            },
        ],
    }

    with pytest.raises(ValidationError, match="testbench ids must be unique"):
        BenchesConfigModel.model_validate(payload)
