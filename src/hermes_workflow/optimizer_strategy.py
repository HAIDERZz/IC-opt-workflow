from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .schemas import (
    OpenBoxOptimizerSettings,
    OptimizerAlgorithm,
    OptimizerStrategy as OptimizerStrategyName,
    TurboOptimizerSettings,
)


ResolvedBackend = Literal["openbox", "native_turbo", "random_baseline"]


OpenBoxAdvancedSettings = OpenBoxOptimizerSettings
TurboAdvancedSettings = TurboOptimizerSettings


@dataclass(frozen=True)
class OptimizerStrategyRequest:
    algorithm: OptimizerAlgorithm
    strategy: OptimizerStrategyName | None
    openbox: OpenBoxAdvancedSettings | None
    turbo: TurboAdvancedSettings | None
    variable_count: int


@dataclass(frozen=True)
class ResolvedOptimizerStrategy:
    requested_strategy: OptimizerStrategyName
    backend: ResolvedBackend
    model_based: bool
    surrogate_type: str | None = None
    acq_type: str | None = None
    acq_optimizer_type: str | None = None
    initial_trials: int | None = None
    snap_to_step: bool | None = None
    duplicate_handling: str | None = None

    def to_dict(self) -> dict[str, object | None]:
        return {
            "requested_strategy": self.requested_strategy.value,
            "backend": self.backend,
            "model_based": self.model_based,
            "surrogate_type": self.surrogate_type,
            "acq_type": self.acq_type,
            "acq_optimizer_type": self.acq_optimizer_type,
            "initial_trials": self.initial_trials,
            "snap_to_step": self.snap_to_step,
            "duplicate_handling": self.duplicate_handling,
        }


OPENBOX_STRATEGY_PRESETS: dict[OptimizerStrategyName, dict[str, object]] = {
    OptimizerStrategyName.OPENBOX_AUTO: {
        "surrogate_type": "auto",
        "acq_type": "auto",
        "acq_optimizer_type": "auto",
        "initial_trials": "auto",
    },
    OptimizerStrategyName.OPENBOX_GP_EIC: {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        "initial_trials": "auto",
    },
    OptimizerStrategyName.OPENBOX_PRF_EIC: {
        "surrogate_type": "prf",
        "acq_type": "eic",
        "acq_optimizer_type": "local_random",
        "initial_trials": "auto",
    },
}


def resolve_optimizer_strategy(
    request: OptimizerStrategyRequest,
) -> ResolvedOptimizerStrategy:
    strategy = request.strategy or _default_strategy_for_algorithm(request.algorithm)
    _validate_request_compatibility(request, strategy)

    if strategy in OPENBOX_STRATEGY_PRESETS:
        openbox = request.openbox or OpenBoxAdvancedSettings()
        preset = OPENBOX_STRATEGY_PRESETS[strategy]
        if strategy is not OptimizerStrategyName.OPENBOX_AUTO:
            for field in ("surrogate_type", "acq_type", "acq_optimizer_type"):
                requested = getattr(openbox, field)
                required = str(preset[field])
                if requested is not None and requested != required:
                    raise ValueError(
                        f"optimizer.strategy {strategy.value} requires "
                        f"optimizer.openbox.{field}={required}; got {requested}"
                    )
        initial_trials = openbox.initial_trials
        if initial_trials is None:
            initial_trials = preset["initial_trials"]
        return ResolvedOptimizerStrategy(
            requested_strategy=strategy,
            backend="openbox",
            model_based=True,
            surrogate_type=openbox.surrogate_type or str(preset["surrogate_type"]),
            acq_type=openbox.acq_type or str(preset["acq_type"]),
            acq_optimizer_type=openbox.acq_optimizer_type
            or str(preset["acq_optimizer_type"]),
            initial_trials=_resolve_initial_trials(
                initial_trials,
                variable_count=request.variable_count,
            ),
        )

    if strategy is OptimizerStrategyName.TURBO_TRUST_REGION:
        turbo = request.turbo or TurboAdvancedSettings()
        return ResolvedOptimizerStrategy(
            requested_strategy=strategy,
            backend="native_turbo",
            model_based=True,
            snap_to_step=turbo.snap_to_step,
            duplicate_handling=turbo.duplicate_handling,
        )

    if strategy is OptimizerStrategyName.RANDOM_BASELINE:
        return ResolvedOptimizerStrategy(
            requested_strategy=strategy,
            backend="random_baseline",
            model_based=False,
        )

    raise ValueError(f"unsupported optimizer strategy: {strategy.value}")


def _default_strategy_for_algorithm(
    algorithm: OptimizerAlgorithm,
) -> OptimizerStrategyName:
    if algorithm is OptimizerAlgorithm.OPENBOX:
        return OptimizerStrategyName.OPENBOX_AUTO
    if algorithm is OptimizerAlgorithm.TURBO:
        return OptimizerStrategyName.TURBO_TRUST_REGION
    if algorithm is OptimizerAlgorithm.RANDOM:
        return OptimizerStrategyName.RANDOM_BASELINE
    raise ValueError(f"unsupported optimizer algorithm: {algorithm.value}")


def _validate_request_compatibility(
    request: OptimizerStrategyRequest,
    strategy: OptimizerStrategyName,
) -> None:
    if strategy in OPENBOX_STRATEGY_PRESETS:
        if request.algorithm is not OptimizerAlgorithm.OPENBOX:
            raise ValueError(
                f"optimizer.strategy {strategy.value} requires "
                "optimizer.algorithm=openbox"
            )
        if request.turbo is not None:
            raise ValueError("optimizer.turbo requires optimizer.algorithm=turbo")
        return

    if strategy is OptimizerStrategyName.TURBO_TRUST_REGION:
        if request.algorithm is not OptimizerAlgorithm.TURBO:
            raise ValueError(
                "optimizer.strategy turbo_trust_region requires "
                "optimizer.algorithm=turbo"
            )
        if request.openbox is not None:
            raise ValueError("optimizer.openbox requires optimizer.algorithm=openbox")
        return

    if strategy is OptimizerStrategyName.RANDOM_BASELINE:
        if request.algorithm is not OptimizerAlgorithm.RANDOM:
            raise ValueError(
                "optimizer.strategy random_baseline requires "
                "optimizer.algorithm=random"
            )
        if request.openbox is not None:
            raise ValueError("optimizer.openbox requires optimizer.algorithm=openbox")
        if request.turbo is not None:
            raise ValueError("optimizer.turbo requires optimizer.algorithm=turbo")
        return

    raise ValueError(f"unsupported optimizer strategy: {strategy.value}")


def _resolve_initial_trials(
    value: int | Literal["auto"],
    *,
    variable_count: int,
) -> int:
    if value == "auto":
        return max(2 * variable_count, 1)
    return value
