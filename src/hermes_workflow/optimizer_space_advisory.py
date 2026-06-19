from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from ConfigSpace import Configuration, ConfigurationSpace
from ConfigSpace.hyperparameters import (
    UniformFloatHyperparameter,
    UniformIntegerHyperparameter,
)
from openbox.compressor import Compressor, create_steps_from_strings
from openbox.utils.constants import SUCCESS
from openbox.utils.history import History, Observation

_MODE = "openbox_compressor_dry_run"
_INSUFFICIENT_ROWS_REASON = "fewer than three eligible finite-objective rows"
_NO_COMPRESSED_RANGES_REASON = "OpenBox compressor produced no compressed ranges"


def build_space_compression_advisory(
    project_dir: str | Path,
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    project_root = Path(project_dir)
    variables = _load_variables(project_root)
    eligible_rows = [
        row
        for row in traces
        if _finite_float(row.get("objective")) is not None
        and isinstance(row.get("parameters"), dict)
        and _parameters_inside_space(row["parameters"], variables)
    ]
    if len(eligible_rows) < 3:
        return {
            "status": "not_available",
            "mode": _MODE,
            "advisory_only": True,
            "applied_to_optimizer": False,
            "reason": _INSUFFICIENT_ROWS_REASON,
            "eligible_count": len(eligible_rows),
        }

    config_space = _config_space_from_variables(variables)
    history = _history_from_rows(eligible_rows, config_space, variables)
    steps = create_steps_from_strings(
        ["d_none", "r_boundary", "p_none"],
        step_params={"r_boundary": {"top_ratio": 0.3, "sigma": 2.0}},
    )
    compressor = Compressor(config_space=config_space, steps=steps)
    compressor.compress_space(space_history=[history], source_similarities={0: 1.0})
    suggestions = _suggestions_from_step_info(steps, variables)
    feasible_count = sum(1 for row in eligible_rows if row.get("status") == "feasible")
    return {
        "status": "available" if suggestions else "not_available",
        "mode": _MODE,
        "advisory_only": True,
        "applied_to_optimizer": False,
        "method": "r_boundary",
        "eligible_count": len(eligible_rows),
        "feasible_count": feasible_count,
        "confidence": _confidence(len(eligible_rows), feasible_count),
        "suggestions": suggestions,
        "reason": None if suggestions else _NO_COMPRESSED_RANGES_REASON,
    }


def _load_variables(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "config" / "variables.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("variables"), list):
        raise ValueError("config/variables.yaml must contain variables")
    return [item for item in payload["variables"] if isinstance(item, dict)]


def _config_space_from_variables(variables: list[dict[str, Any]]) -> ConfigurationSpace:
    config_space = ConfigurationSpace()
    for variable in variables:
        name = str(variable["name"])
        lower = _parse_number(variable["lower"])
        upper = _parse_number(variable["upper"])
        if lower is None or upper is None:
            raise ValueError(f"variable {name} has non-numeric lower/upper")
        if variable.get("kind") == "integer":
            hyperparameter = UniformIntegerHyperparameter(
                name, lower=int(lower), upper=int(upper)
            )
        else:
            hyperparameter = UniformFloatHyperparameter(
                name, lower=float(lower), upper=float(upper)
            )
        config_space.add_hyperparameter(hyperparameter)
    return config_space


def _history_from_rows(
    rows: list[dict[str, Any]],
    config_space: ConfigurationSpace,
    variables: list[dict[str, Any]],
) -> History:
    history = History(
        task_id="optimizer_space_advisory",
        num_objectives=1,
        num_constraints=0,
        config_space=config_space,
    )
    variable_names = [str(variable["name"]) for variable in variables]
    for row in rows:
        values = {
            name: _parse_variable_value(row["parameters"][name], variable)
            for name, variable in zip(variable_names, variables, strict=True)
        }
        objective = _finite_float(row.get("objective"))
        if objective is None or any(value is None for value in values.values()):
            continue
        config = Configuration(config_space, values=values)
        history.update_observation(
            Observation(
                config=config,
                objectives=[objective],
                trial_state=SUCCESS,
                elapsed_time=0.0,
            )
        )
    return history


def _parameters_inside_space(
    parameters: dict[str, Any],
    variables: list[dict[str, Any]],
) -> bool:
    for variable in variables:
        name = variable.get("name")
        if not isinstance(name, str) or name not in parameters:
            return False
        value = _parse_variable_value(parameters[name], variable)
        lower = _parse_number(variable.get("lower"))
        upper = _parse_number(variable.get("upper"))
        if value is None or lower is None or upper is None:
            return False
        if value < lower or value > upper:
            return False
    return True


def _suggestions_from_step_info(
    steps: list[Any], variables: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    variable_by_name = {str(variable["name"]): variable for variable in variables}
    suggestions: list[dict[str, Any]] = []
    for step in steps:
        info = step.get_step_info()
        compression_info = info.get("compression_info")
        if not isinstance(compression_info, dict):
            continue
        compressed_params = compression_info.get("compressed_params")
        if not isinstance(compressed_params, list):
            continue
        for item in compressed_params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            compressed_range = item.get("compressed_range")
            original_range = item.get("original_range")
            ratio = item.get("compression_ratio")
            if not isinstance(name, str) or name not in variable_by_name:
                continue
            if not _is_pair(compressed_range) or not _is_pair(original_range):
                continue
            suggestions.append(
                {
                    "variable": name,
                    "original_range": [float(original_range[0]), float(original_range[1])],
                    "suggested_range": [float(compressed_range[0]), float(compressed_range[1])],
                    "original_display": {
                        "lower": str(variable_by_name[name]["lower"]),
                        "upper": str(variable_by_name[name]["upper"]),
                    },
                    "suggested_display": {
                        "lower": _format_si(float(compressed_range[0])),
                        "upper": _format_si(float(compressed_range[1])),
                    },
                    "compression_ratio": float(ratio),
                }
            )
    return suggestions


def _is_pair(value: Any) -> bool:
    return isinstance(value, list | tuple) and len(value) == 2


def _parse_variable_value(value: Any, variable: dict[str, Any]) -> int | float | None:
    parsed = _parse_number(value)
    if parsed is None:
        return None
    if variable.get("kind") != "integer":
        return parsed
    if not parsed.is_integer():
        return None
    return int(parsed)


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        result = float(value)
        return result if math.isfinite(result) else None
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    units = {
        "meg": 1e6,
        "g": 1e9,
        "k": 1e3,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
    }
    for suffix, multiplier in sorted(units.items(), key=lambda item: -len(item[0])):
        if text.endswith(suffix):
            try:
                result = float(text[: -len(suffix)]) * multiplier
            except ValueError:
                return None
            return result if math.isfinite(result) else None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _format_si(value: float) -> str:
    magnitude = abs(value)
    if magnitude != 0 and magnitude < 1e-9:
        return f"{value / 1e-12:.6g}p"
    if magnitude != 0 and magnitude < 1e-6:
        return f"{value / 1e-9:.6g}n"
    if magnitude != 0 and magnitude < 1e-3:
        return f"{value / 1e-6:.6g}u"
    if magnitude != 0 and magnitude < 1:
        return f"{value / 1e-3:.6g}m"
    return f"{value:.6g}"


def _confidence(eligible_count: int, feasible_count: int) -> str:
    if eligible_count >= 20 and feasible_count >= 8:
        return "high"
    if eligible_count >= 8 and feasible_count >= 3:
        return "medium"
    return "low"
