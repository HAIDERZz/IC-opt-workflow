from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)


SCHEMA_VERSION = "1.0"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NonEmptyStr = Annotated[str, Field(min_length=1)]
StrictFiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_name(value: str, label: str) -> str:
    if not NAME_RE.match(value):
        raise ValueError(f"{label} must match [A-Za-z_][A-Za-z0-9_]*")
    return value


def validate_fixed_bool(value: bool, expected: bool, label: str) -> bool:
    if value is not expected:
        raise ValueError(f"{label} must be {str(expected).lower()}")
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


class ResultSource(StrEnum):
    MOCK = "mock"
    REAL = "real"


class OceanExpressionSource(StrEnum):
    USER_APPROVED = "user_approved"
    MAESTRO_OUTPUT_APPROVED = "maestro_output_approved"
    DIRECT_PLOT_APPROVED = "direct_plot_approved"


class OceanExpectedValueType(StrEnum):
    REAL_SCALAR = "real_scalar"


class FailPolicy(StrEnum):
    FAIL = "fail"


class SpectrePreset(StrEnum):
    CX = "cx"
    AX = "ax"
    MX = "mx"
    LX = "lx"
    VX = "vx"


class OptimizerAlgorithm(StrEnum):
    TURBO = "turbo"
    OPENBOX = "openbox"
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
    virtuoso_library: NonEmptyStr
    cell: NonEmptyStr
    design_view: NonEmptyStr
    maestro_view: NonEmptyStr
    test_name: NonEmptyStr
    corner: NonEmptyStr


class NamedTestbenchConfig(TestbenchConfig):
    id: str
    maestro_point_root: NonEmptyStr

    @field_validator("id")
    @classmethod
    def _id_is_identifier(cls, value: str) -> str:
        return validate_name(value, "testbench id")


class TestbenchesConfig(StrictModel):
    schema_version: Literal["1.0"]
    testbenches: list[NamedTestbenchConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _testbench_ids_are_unique(self) -> "TestbenchesConfig":
        ids = [testbench.id for testbench in self.testbenches]
        if len(ids) != len(set(ids)):
            raise ValueError("testbench ids must be unique")
        return self


class ProcessCorner(StrictModel):
    id: str
    model_section: str | None = None
    model_file: str | None = None
    variables: dict[str, str] | None = None
    description: str | None = None

    @field_validator("id")
    @classmethod
    def _id_is_identifier(cls, value: str) -> str:
        return validate_name(value, "corner id")


class ProcessCornerConfig(StrictModel):
    schema_version: Literal["1.0"]
    objective_policy: Literal["nominal", "worst_case"]
    constraint_policy: Literal["nominal", "all_corners"]
    corners: list[ProcessCorner] = Field(min_length=1)

    @model_validator(mode="after")
    def _corner_ids_are_unique(self) -> "ProcessCornerConfig":
        ids = [corner.id for corner in self.corners]
        if len(ids) != len(set(ids)):
            raise ValueError("corner ids must be unique")
        return self


class NetlistConfig(StrictModel):
    source: Literal["existing_maestro_setup"]
    export_method: Literal["maeCreateNetlistForCorner"]
    exported_input_scs: NonEmptyStr
    template_scs: NonEmptyStr


class SafetyConfig(StrictModel):
    immutable_after_package: StrictBool
    require_hermes_approval_before_real_run: StrictBool
    allow_maestro_setup_modification: StrictBool
    allow_only_variable_templating: StrictBool

    @field_validator(
        "immutable_after_package",
        "require_hermes_approval_before_real_run",
        "allow_only_variable_templating",
    )
    @classmethod
    def _value_must_be_true(cls, value: bool) -> bool:
        return validate_fixed_bool(value, True, "safety value")

    @field_validator("allow_maestro_setup_modification")
    @classmethod
    def _value_must_be_false(cls, value: bool) -> bool:
        return validate_fixed_bool(value, False, "safety value")


class ProjectConfig(StrictModel):
    schema_version: Literal["1.0"]
    project: ProjectInfo
    testbench: TestbenchConfig
    netlist: NetlistConfig
    safety: SafetyConfig


class VariableSpec(StrictModel):
    name: str
    kind: VariableKind
    lower: NonEmptyStr
    upper: NonEmptyStr
    step: NonEmptyStr

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


class OceanMetricSpec(StrictModel):
    expression: NonEmptyStr
    result: NonEmptyStr | None = None
    expression_source: OceanExpressionSource
    source_reference: NonEmptyStr
    expected_value_type: OceanExpectedValueType
    nil_policy: FailPolicy
    non_finite_policy: FailPolicy

    @field_validator("expression")
    @classmethod
    def _expression_has_no_template_placeholders(cls, value: str) -> str:
        if "{{" in value or "}}" in value:
            raise ValueError("ocean.expression must not contain template placeholders")
        return value


class MetricSpec(StrictModel):
    name: str
    unit: NonEmptyStr
    maestro_formula: NonEmptyStr
    testbench: str | None = None
    required_signals: list[NonEmptyStr] = Field(default_factory=list)
    ocean: OceanMetricSpec | None = None

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "metric name")

    @field_validator("testbench")
    @classmethod
    def _testbench_is_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_name(value, "metric testbench")


class ConstraintSpec(StrictModel):
    metric: str
    op: ConstraintOp
    value: NonEmptyStr

    @field_validator("metric")
    @classmethod
    def _metric_is_identifier(cls, value: str) -> str:
        return validate_name(value, "constraint metric")


class ObjectiveSpec(StrictModel):
    direction: ObjectiveDirection
    expression: NonEmptyStr


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
    output_format: Literal["psfascii", "psfxl"]
    threads_per_run: StrictInt = Field(default=10, ge=1)
    parallel_jobs: StrictInt = Field(ge=1)
    timeout_s: StrictInt = Field(gt=0)
    require_license_check: StrictBool
    keep_failed_runs: StrictBool
    keep_successful_runs: StrictBool


class SpectreConfig(StrictModel):
    schema_version: Literal["1.0"]
    spectre: SpectreSettings


class OptimizerSettings(StrictModel):
    algorithm: OptimizerAlgorithm
    initialization: InitializationMethod
    max_evaluations: StrictInt = Field(ge=1)
    batch_size: StrictInt = Field(ge=1)
    random_seed: StrictInt
    optimizer_cpu_threads: StrictInt = Field(default=4, ge=1)
    failure_penalty: StrictFloat = Field(gt=0)
    deduplicate_candidates: StrictBool

    @field_validator("deduplicate_candidates")
    @classmethod
    def _deduplicate_candidates_must_be_true(cls, value: bool) -> bool:
        return validate_fixed_bool(value, True, "deduplicate_candidates")


class OptimizerConfig(StrictModel):
    schema_version: Literal["1.0"]
    optimizer: OptimizerSettings


class LedgerRow(StrictModel):
    candidate_id: str
    parameters: dict[str, str]
    metrics: dict[str, StrictFiniteFloat]
    constraints_passed: StrictBool
    objective: StrictFiniteFloat
    batch_id: StrictInt
    simulation_status: str
    timestamp_utc: str
    result_source: ResultSource | None = None
    run_id: str | None = None
    result_manifest: str | None = None
    metric_result_manifest: str | None = None

    @field_validator("simulation_status")
    @classmethod
    def _status_is_recognized(cls, value: str) -> str:
        allowed = {
            "mock_pass",
            "mock_constraint_fail",
            "mock_error",
            "real_pass",
            "real_constraint_fail",
        }
        if value not in allowed:
            raise ValueError(f"simulation_status must be one of {allowed}")
        return value


class BestCandidate(StrictModel):
    candidate_id: str
    parameters: dict[str, str]
    metrics: dict[str, StrictFiniteFloat]
    constraints_passed: StrictBool
    objective: StrictFiniteFloat
    batch_id: StrictInt
    timestamp_utc: str


class OptimizerState(StrictModel):
    schema_version: Literal["1.0"]
    project_name: str
    algorithm: str
    initialization: str
    current_evaluations: StrictInt
    max_evaluations: StrictInt
    batch_size: StrictInt
    random_seed: StrictInt
    best_candidate_id: str | None
    status: str
    started_at_utc: str
    updated_at_utc: str

    @field_validator("status")
    @classmethod
    def _status_is_recognized(cls, value: str) -> str:
        allowed = {"running", "completed", "stopped"}
        if value not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return value
