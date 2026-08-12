"""Pydantic models for the fix-run simulation workflow."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from hermes_workflow.schemas import (
    NonEmptyStr,
    StrictModel,
    validate_fixed_bool,
    validate_name,
)

RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
SAFE_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


WorkflowMode = Literal["optimize", "fix_run"]


class WorkflowSettings(StrictModel):
    schema_version: str
    mode: WorkflowMode
    starting_run_id: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value

    @field_validator("starting_run_id")
    @classmethod
    def _starting_run_id_matches_pattern(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not RUN_ID_RE.match(value):
            raise ValueError(
                "starting_run_id must match real_[0-9]{3} "
                "(first version reuses real_NNN IDs)"
            )
        return value

    @model_validator(mode="after")
    def _starting_run_id_matches_workflow(self) -> "WorkflowSettings":
        if self.mode == "optimize":
            if self.starting_run_id is not None:
                raise ValueError(
                    "starting_run_id is not supported for optimize workflow mode"
                )
            return self
        if self.starting_run_id is None:
            self.starting_run_id = "real_001"
        return self


class FixedPoint(StrictModel):
    candidate_id: str
    parameters: dict[str, str] = Field(min_length=1)

    @field_validator("candidate_id")
    @classmethod
    def _candidate_id_is_safe(cls, value: str) -> str:
        if not value or not SAFE_CANDIDATE_ID_RE.match(value):
            raise ValueError("candidate_id must be a safe identifier")
        return value


class FixedPointsConfig(StrictModel):
    schema_version: str
    points: list[FixedPoint] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value

    @model_validator(mode="after")
    def _candidate_ids_are_unique(self) -> "FixedPointsConfig":
        candidate_ids = [point.candidate_id for point in self.points]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id values must be unique")
        return self


class WaveformExport(StrictModel):
    name: str
    testbench: str | None = None
    expression: NonEmptyStr
    output_format: Literal["csv"]
    nil_policy: Literal["fail"] = "fail"

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "waveform export name")

    @field_validator("testbench")
    @classmethod
    def _testbench_is_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_name(value, "waveform export testbench")

    @field_validator("expression")
    @classmethod
    def _expression_is_safe(cls, value: str) -> str:
        if "outfile(" in value:
            raise ValueError("expression must not contain outfile(")
        if "system(" in value:
            raise ValueError("expression must not contain system(")
        if "{{" in value:
            raise ValueError("expression must not contain template placeholders")
        return value


class WaveformExportsConfig(StrictModel):
    schema_version: str
    exports: list[WaveformExport] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value

    @model_validator(mode="after")
    def _export_names_are_unique(self) -> "WaveformExportsConfig":
        names = [export.name for export in self.exports]
        if len(names) != len(set(names)):
            raise ValueError("waveform export names must be unique")
        return self


def fix_run_id_range_issue(
    workflow: WorkflowSettings | None,
    fixed_points: FixedPointsConfig | None,
) -> str | None:
    """Return an issue when sequential fixed-point IDs would exceed real_999."""
    if (
        workflow is None
        or workflow.mode != "fix_run"
        or workflow.starting_run_id is None
        or fixed_points is None
    ):
        return None
    first = int(workflow.starting_run_id.rsplit("_", 1)[1])
    last = first + len(fixed_points.points) - 1
    if last > 999:
        return (
            f"starting_run_id {workflow.starting_run_id} with "
            f"{len(fixed_points.points)} fixed points would exceed real_999"
        )
    return None


class WaveformExportResult(StrictModel):
    name: str
    expression: str
    expression_sha256: str
    output_format: str
    csv_path: str
    status: Literal["pass", "fail"]
    issues: list[str] = Field(default_factory=list)


class WaveformExportManifest(StrictModel):
    schema_version: str
    workflow_mode: str
    run_id: str
    candidate_id: str
    testbench_id: str
    corner_id: str
    model_section: str
    corner_variables: dict[str, str]
    parameters: dict[str, str]
    exports: list[WaveformExportResult]
    psf_dir: str
    ocean_log: str
    command_trace: dict | None = None

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value


class ChildRunIssue(StrictModel):
    testbench_id: str | None = None
    corner_id: str | None = None
    message: str


class FixRunPointReport(StrictModel):
    candidate_id: str
    run_id: str
    testbench_corner_count: int
    scalar_metric_manifest_paths: list[str]
    waveform_export_manifest_paths: list[str]
    csv_artifact_paths: list[str]
    issues: list[str]
    child_issues: list[ChildRunIssue] = Field(default_factory=list)


class FixRunReport(StrictModel):
    schema_version: str
    workflow_mode: str
    status: str
    points: list[FixRunPointReport]
    optimizer_state_created: bool
    optimizer_decision_report_created: bool

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value

    @field_validator("optimizer_state_created")
    @classmethod
    def _optimizer_state_created_must_be_false(cls, value: bool) -> bool:
        return validate_fixed_bool(value, False, "optimizer_state_created")

    @field_validator("optimizer_decision_report_created")
    @classmethod
    def _optimizer_decision_report_created_must_be_false(cls, value: bool) -> bool:
        return validate_fixed_bool(value, False, "optimizer_decision_report_created")
