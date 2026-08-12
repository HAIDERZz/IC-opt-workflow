"""Shared candidate parameter validation for intake, project checks, and runs."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Sequence

from hermes_workflow.schemas import VariableKind, VariablesConfig

CONTINUOUS_VALUE_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s*(?P<unit>\S+))?\s*$"
)


def quantize_candidate(
    variables_config: VariablesConfig,
    raw_values: Sequence[float],
) -> dict[str, str]:
    """Snap a raw optimizer vector to the approved variable grid."""

    variables = variables_config.variables
    if len(raw_values) != len(variables):
        raise ValueError(
            f"expected {len(variables)} raw values, got {len(raw_values)}"
        )

    parameters: dict[str, str] = {}
    for variable, raw in zip(variables, raw_values, strict=True):
        if variable.kind == VariableKind.INTEGER:
            lower = int(variable.lower)
            upper = int(variable.upper)
            step = int(variable.step)
            offset = round((float(raw) - lower) / step)
            max_offset = (upper - lower) // step
            value = lower + _clamp_int(offset, 0, max_offset) * step
            parameters[variable.name] = str(value)
        else:
            lower, unit = _parse_continuous_candidate(variable.lower)
            upper, upper_unit = _parse_continuous_candidate(variable.upper)
            step, step_unit = _parse_continuous_candidate(variable.step)
            if upper_unit != unit or step_unit != unit:
                raise ValueError(
                    f"variable {variable.name} uses inconsistent units"
                )
            offset = round((Decimal(str(raw)) - lower) / step)
            max_offset = int((upper - lower) / step)
            value = lower + Decimal(_clamp_int(offset, 0, max_offset)) * step
            parameters[variable.name] = f"{value.normalize():f}{unit}"
    return parameters


def assert_candidate_parameters_match_variables(
    variables: VariablesConfig,
    parameters: dict[str, str],
) -> None:
    """Require a complete, in-bounds, step-aligned candidate assignment."""
    expected_names = [variable.name for variable in variables.variables]
    if set(parameters) != set(expected_names):
        raise ValueError("candidate parameters must match variables.yaml")
    for variable in variables.variables:
        raw_value = parameters[variable.name]
        if not isinstance(raw_value, str):
            raise ValueError(f"{variable.name} value must be a string")
        if variable.kind == VariableKind.INTEGER:
            _assert_integer_candidate(
                variable.name,
                raw_value,
                variable.lower,
                variable.upper,
                variable.step,
            )
        elif variable.kind == VariableKind.CONTINUOUS_STEP:
            _assert_continuous_candidate(
                variable.name,
                raw_value,
                variable.lower,
                variable.upper,
                variable.step,
            )
        else:
            raise ValueError(
                f"{variable.name} kind is unsupported: {variable.kind}"
            )


def _assert_integer_candidate(
    name: str,
    raw_value: str,
    lower_raw: str,
    upper_raw: str,
    step_raw: str,
) -> None:
    try:
        value = int(raw_value)
        lower = int(lower_raw)
        upper = int(upper_raw)
        step = int(step_raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if str(value) != raw_value:
        raise ValueError(f"{name} must be an integer")
    if value < lower or value > upper:
        raise ValueError(f"{name} is outside approved bounds")
    if step <= 0 or (value - lower) % step != 0:
        raise ValueError(f"{name} is not aligned to approved step")


def _parse_continuous_candidate(raw: str) -> tuple[Decimal, str]:
    if raw != raw.strip():
        raise ValueError("value must use compact Spectre-safe formatting")
    match = CONTINUOUS_VALUE_RE.match(raw)
    if match is None:
        raise ValueError("value must be numeric with an optional unit suffix")
    if match.group("unit") and match.start("unit") > match.end("value"):
        raise ValueError("value must use a Spectre-safe attached unit suffix")
    try:
        return Decimal(match.group("value")), match.group("unit") or ""
    except InvalidOperation as exc:
        raise ValueError(
            "value must be numeric with an optional unit suffix"
        ) from exc


def _assert_continuous_candidate(
    name: str,
    raw_value: str,
    lower_raw: str,
    upper_raw: str,
    step_raw: str,
) -> None:
    try:
        value, value_unit = _parse_continuous_candidate(raw_value)
    except ValueError as exc:
        if "compact Spectre-safe formatting" in str(exc):
            raise ValueError(
                f"{name} must use compact Spectre-safe formatting"
            ) from exc
        if "attached unit suffix" in str(exc):
            raise ValueError(
                f"{name} must use a Spectre-safe attached unit suffix"
            ) from exc
        raise ValueError(
            f"{name} must be numeric with an optional unit suffix"
        ) from exc
    lower, lower_unit = _parse_continuous_candidate(lower_raw)
    upper, upper_unit = _parse_continuous_candidate(upper_raw)
    step, step_unit = _parse_continuous_candidate(step_raw)
    if len({value_unit, lower_unit, upper_unit, step_unit}) != 1:
        raise ValueError(f"{name} unit suffix must match variables.yaml")
    if value < lower or value > upper:
        raise ValueError(f"{name} is outside approved bounds")
    if step <= 0 or (value - lower) % step != 0:
        raise ValueError(f"{name} is not aligned to approved step")


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))
