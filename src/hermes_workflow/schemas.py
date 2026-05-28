from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_name(value: str, label: str) -> str:
    if not NAME_RE.match(value):
        raise ValueError(f"{label} must match [A-Za-z_][A-Za-z0-9_]*")
    return value


class VariableKind(StrEnum):
    INTEGER = "integer"
    CONTINUOUS_STEP = "continuous_step"


class ConstraintOp(StrEnum):
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"


class ObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class SpectrePreset(StrEnum):
    CX = "cx"
    AX = "ax"
    MX = "mx"
    LX = "lx"
    VX = "vx"


class OptimizerAlgorithm(StrEnum):
    TURBO = "turbo"
    RANDOM = "random"


class InitializationMethod(StrEnum):
    SOBOL = "sobol"
    LATIN_HYPERCUBE = "latin_hypercube"
    RANDOM = "random"


class ProjectInfo(StrictModel):
    name: str
    description: str = ""
    backend: Literal["maestro_exported_spectre_deck"]

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "project.name")


class TestbenchConfig(StrictModel):
    virtuoso_library: str
    cell: str
    design_view: str
    maestro_view: str
    test_name: str
    corner: str


class NetlistConfig(StrictModel):
    source: Literal["existing_maestro_setup"]
    export_method: Literal["maeCreateNetlistForCorner"]
    exported_input_scs: str
    template_scs: str


class SafetyConfig(StrictModel):
    immutable_after_package: Literal[True]
    require_hermes_approval_before_real_run: Literal[True]
    allow_maestro_setup_modification: Literal[False]
    allow_only_variable_templating: Literal[True]


class ProjectConfig(StrictModel):
    schema_version: Literal["1.0"]
    project: ProjectInfo
    testbench: TestbenchConfig
    netlist: NetlistConfig
    safety: SafetyConfig


class VariableSpec(StrictModel):
    name: str
    kind: VariableKind
    lower: str
    upper: str
    step: str

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "variable name")


class VariablesConfig(StrictModel):
    schema_version: Literal["1.0"]
    variables: list[VariableSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _variable_names_are_unique(self) -> "VariablesConfig":
        names = [variable.name for variable in self.variables]
        if len(names) != len(set(names)):
            raise ValueError("variable names must be unique")
        return self


class MetricSpec(StrictModel):
    name: str
    unit: str
    maestro_formula: str
    required_signals: list[str]

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "metric name")

    @field_validator("required_signals")
    @classmethod
    def _required_signals_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("required_signals must not be empty")
        return value


class ConstraintSpec(StrictModel):
    metric: str
    op: ConstraintOp
    value: str

    @field_validator("metric")
    @classmethod
    def _metric_is_identifier(cls, value: str) -> str:
        return validate_name(value, "constraint metric")


class ObjectiveSpec(StrictModel):
    direction: ObjectiveDirection
    expression: str


class MetricsConfig(StrictModel):
    schema_version: Literal["1.0"]
    metrics: list[MetricSpec] = Field(min_length=1)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    objective: ObjectiveSpec

    @model_validator(mode="after")
    def _metric_names_are_unique(self) -> "MetricsConfig":
        names = [metric.name for metric in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("metric names must be unique")
        return self


class SpectreSettings(StrictModel):
    engine: Literal["spectre_x"]
    preset: SpectrePreset
    output_format: Literal["psfascii"]
    parallel_jobs: int = Field(ge=1)
    timeout_s: int = Field(gt=0)
    require_license_check: bool
    keep_failed_runs: bool
    keep_successful_runs: bool


class SpectreConfig(StrictModel):
    schema_version: Literal["1.0"]
    spectre: SpectreSettings


class OptimizerSettings(StrictModel):
    algorithm: OptimizerAlgorithm
    initialization: InitializationMethod
    max_evaluations: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    random_seed: int
    failure_penalty: float = Field(gt=0)
    deduplicate_candidates: Literal[True]


class OptimizerConfig(StrictModel):
    schema_version: Literal["1.0"]
    optimizer: OptimizerSettings
