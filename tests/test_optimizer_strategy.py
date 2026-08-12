import pytest

from hermes_workflow.optimizer_strategy import (
    OpenBoxAdvancedSettings,
    OptimizerStrategyName,
    OptimizerStrategyRequest,
    resolve_optimizer_strategy,
)
from hermes_workflow.schemas import OptimizerAlgorithm


def test_openbox_default_resolves_to_openbox_auto() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=None,
            openbox=None,
            turbo=None,
            variable_count=4,
        )
    )

    assert resolved.requested_strategy is OptimizerStrategyName.OPENBOX_AUTO
    assert resolved.backend == "openbox"
    assert resolved.surrogate_type == "auto"
    assert resolved.acq_type == "auto"
    assert resolved.acq_optimizer_type == "auto"
    assert resolved.initial_trials == 8
    assert resolved.model_based is True


def test_openbox_gp_eic_resolves_expected_openbox_settings() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=OptimizerStrategyName.OPENBOX_GP_EIC,
            openbox=None,
            turbo=None,
            variable_count=10,
        )
    )

    assert resolved.requested_strategy is OptimizerStrategyName.OPENBOX_GP_EIC
    assert resolved.backend == "openbox"
    assert resolved.surrogate_type == "gp"
    assert resolved.acq_type == "eic"
    assert resolved.acq_optimizer_type == "random_scipy"
    assert resolved.initial_trials == 20


def test_openbox_prf_eic_resolves_expected_openbox_settings() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=OptimizerStrategyName.OPENBOX_PRF_EIC,
            openbox=None,
            turbo=None,
            variable_count=11,
        )
    )

    assert resolved.requested_strategy is OptimizerStrategyName.OPENBOX_PRF_EIC
    assert resolved.backend == "openbox"
    assert resolved.surrogate_type == "prf"
    assert resolved.acq_type == "eic"
    assert resolved.acq_optimizer_type == "local_random"
    assert resolved.initial_trials == 22


def test_turbo_default_resolves_to_turbo_trust_region() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.TURBO,
            strategy=None,
            openbox=None,
            turbo=None,
            variable_count=5,
        )
    )

    assert resolved.requested_strategy is OptimizerStrategyName.TURBO_TRUST_REGION
    assert resolved.backend == "native_turbo"
    assert resolved.snap_to_step is True
    assert resolved.duplicate_handling == "resample"
    assert resolved.model_based is True


def test_random_baseline_resolves_expected_backend() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.RANDOM,
            strategy=OptimizerStrategyName.RANDOM_BASELINE,
            openbox=None,
            turbo=None,
            variable_count=3,
        )
    )

    assert resolved.requested_strategy is OptimizerStrategyName.RANDOM_BASELINE
    assert resolved.backend == "random_baseline"
    assert resolved.model_based is False
    assert resolved.to_dict() == {
        "requested_strategy": "random_baseline",
        "backend": "random_baseline",
        "model_based": False,
        "surrogate_type": None,
        "acq_type": None,
        "acq_optimizer_type": None,
        "initial_trials": None,
        "snap_to_step": None,
        "duplicate_handling": None,
    }


def test_openbox_advanced_settings_override_preset() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=OptimizerStrategyName.OPENBOX_AUTO,
            openbox=OpenBoxAdvancedSettings(
                surrogate_type="lightgbm",
                acq_type="pi",
                acq_optimizer_type="local_random",
                initial_trials=7,
            ),
            turbo=None,
            variable_count=2,
        )
    )

    assert resolved.surrogate_type == "lightgbm"
    assert resolved.acq_type == "pi"
    assert resolved.acq_optimizer_type == "local_random"
    assert resolved.initial_trials == 7


@pytest.mark.parametrize(
    ("strategy", "openbox", "field", "required"),
    [
        (
            OptimizerStrategyName.OPENBOX_GP_EIC,
            OpenBoxAdvancedSettings(surrogate_type="prf"),
            "surrogate_type",
            "gp",
        ),
        (
            OptimizerStrategyName.OPENBOX_GP_EIC,
            OpenBoxAdvancedSettings(acq_type="pi"),
            "acq_type",
            "eic",
        ),
        (
            OptimizerStrategyName.OPENBOX_GP_EIC,
            OpenBoxAdvancedSettings(acq_optimizer_type="local_random"),
            "acq_optimizer_type",
            "random_scipy",
        ),
        (
            OptimizerStrategyName.OPENBOX_PRF_EIC,
            OpenBoxAdvancedSettings(surrogate_type="gp"),
            "surrogate_type",
            "prf",
        ),
        (
            OptimizerStrategyName.OPENBOX_PRF_EIC,
            OpenBoxAdvancedSettings(acq_type="pi"),
            "acq_type",
            "eic",
        ),
        (
            OptimizerStrategyName.OPENBOX_PRF_EIC,
            OpenBoxAdvancedSettings(acq_optimizer_type="random_scipy"),
            "acq_optimizer_type",
            "local_random",
        ),
    ],
)
def test_named_openbox_preset_rejects_conflicting_advanced_settings(
    strategy: OptimizerStrategyName,
    openbox: OpenBoxAdvancedSettings,
    field: str,
    required: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=rf"{strategy.value}.*{field}.*{required}",
    ):
        resolve_optimizer_strategy(
            OptimizerStrategyRequest(
                algorithm=OptimizerAlgorithm.OPENBOX,
                strategy=strategy,
                openbox=openbox,
                turbo=None,
                variable_count=4,
            )
        )


@pytest.mark.parametrize("raw_strategy", ["openbox_eic", "openbox-eic"])
def test_openbox_eic_is_rejected_as_strategy_name(raw_strategy: str) -> None:
    with pytest.raises(ValueError, match="eic is an acquisition function"):
        OptimizerStrategyName.from_user_value(raw_strategy)
