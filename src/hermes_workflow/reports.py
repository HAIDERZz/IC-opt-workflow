from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


REQUIRED_PREFLIGHT_REPORT_PATHS = (
    "reports/netlist_preparation_report.json",
    "reports/dry_run_report.json",
    "state/health_check.json",
)


class StrictReport(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PassFail(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


class RealRunCheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class RealRunResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MetricResultCheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class MetricResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RealResultRecordStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class NetlistPreparationReport(StrictReport):
    schema_version: str
    status: PassFail
    exported_input_scs: str
    template_scs: str
    approved_variables_template_status: dict[str, bool]
    analysis_statements: list[str]
    forbidden_setup_changes_detected: bool
    issues: list[str] = Field(default_factory=list)


class PlaceholderCheck(StrictReport):
    unresolved_placeholders: list[str] = Field(default_factory=list)
    unexpected_template_variables: list[str] = Field(default_factory=list)


class DryRunReport(StrictReport):
    schema_version: str
    status: PassFail
    rendered_candidate_scs: str
    placeholder_check: PlaceholderCheck
    metrics_import_ok: bool
    mock_metrics_ok: bool
    objective_ok: bool
    constraints_ok: bool
    ledger_write_ok: bool
    state_write_ok: bool
    issues: list[str] = Field(default_factory=list)


class HealthCheck(StrictReport):
    schema_version: str
    status: HealthStatus
    real_run_started: bool
    current_evaluations: int = Field(ge=0)
    best_candidate_path: str | None
    last_batch_id: int | None
    issues: list[str] = Field(default_factory=list)


class RealRunCheckFlags(StrictReport):
    prepared_manifest_ok: bool = False
    candidate_ok: bool = False
    result_manifest_ok: bool = False
    prepared_input_hash_ok: bool = False
    artifact_paths_ok: bool = False


class RealRunCheckReport(StrictReport):
    schema_version: str
    status: RealRunCheckStatus
    run_id: str
    candidate_id: str | None
    result_status: RealRunResultStatus | None
    real_run_manifest: str
    result_manifest: str
    prepared_input_scs: str | None
    log_file: str | None
    artifact_files: list[str] = Field(default_factory=list)
    checks: RealRunCheckFlags
    issues: list[str] = Field(default_factory=list)


class MetricResultCheckFlags(StrictReport):
    request_hash_ok: bool = False
    result_manifest_ok: bool = False
    metric_manifest_ok: bool = False
    metric_identity_ok: bool = False
    formula_hashes_ok: bool = False
    scalar_values_ok: bool = False
    artifact_paths_ok: bool = False


class CheckedMetricResult(StrictReport):
    status: MetricResultStatus
    value: float | None
    value_text: str | None
    unit: str
    expression_sha256: str


class MetricResultCheckReport(StrictReport):
    schema_version: str
    status: MetricResultCheckStatus
    run_id: str
    candidate_id: str | None
    backend: str | None
    request_file: str
    metric_result_manifest: str
    psf_dir: str | None
    metrics: dict[str, CheckedMetricResult] = Field(default_factory=dict)
    checks: MetricResultCheckFlags
    issues: list[str] = Field(default_factory=list)


class RealResultRecordFlags(StrictReport):
    real_run_check_ok: bool = False
    metric_result_check_ok: bool = False
    candidate_ok: bool = False
    duplicate_ok: bool = False
    objective_ok: bool = False
    constraints_ok: bool = False
    ledger_write_ok: bool = False
    state_write_ok: bool = False


class RealResultRecordReport(StrictReport):
    schema_version: str
    status: RealResultRecordStatus
    run_id: str
    candidate_id: str | None
    ledger_path: str
    optimizer_state_path: str
    best_candidate_path: str | None
    checks: RealResultRecordFlags
    issues: list[str] = Field(default_factory=list)


class PreflightReports(BaseModel):
    netlist_preparation: NetlistPreparationReport
    dry_run: DryRunReport
    health_check: HealthCheck
    messages: list[str] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.messages


def load_preflight_reports(project_dir: Path) -> PreflightReports:
    project_dir = Path(project_dir)
    netlist = _load_json_model(
        project_dir / "reports" / "netlist_preparation_report.json",
        NetlistPreparationReport,
    )
    dry_run = _load_json_model(
        project_dir / "reports" / "dry_run_report.json",
        DryRunReport,
    )
    health = _load_json_model(project_dir / "state" / "health_check.json", HealthCheck)

    messages: list[str] = []
    if netlist.status != PassFail.PASS:
        messages.append(f"netlist preparation status is {netlist.status.value}")
    if netlist.forbidden_setup_changes_detected:
        messages.append("netlist preparation detected forbidden setup changes")
    for variable, templated in sorted(
        netlist.approved_variables_template_status.items()
    ):
        if not templated:
            messages.append(f"approved variable {variable} was not templated")
    messages.extend(netlist.issues)

    if dry_run.status != PassFail.PASS:
        messages.append(f"dry run status is {dry_run.status.value}")
    if dry_run.placeholder_check.unresolved_placeholders:
        messages.append("dry run has unresolved placeholders")
    if dry_run.placeholder_check.unexpected_template_variables:
        messages.append("dry run has unexpected template variables")
    for field_name in [
        "metrics_import_ok",
        "mock_metrics_ok",
        "objective_ok",
        "constraints_ok",
        "ledger_write_ok",
        "state_write_ok",
    ]:
        if not getattr(dry_run, field_name):
            messages.append(f"dry run check failed: {field_name}")
    messages.extend(dry_run.issues)

    if health.status != HealthStatus.HEALTHY:
        messages.append(f"health status is {health.status.value}")
    if health.real_run_started:
        messages.append("real run already started before approval")
    messages.extend(health.issues)

    return PreflightReports(
        netlist_preparation=netlist,
        dry_run=dry_run,
        health_check=health,
        messages=messages,
    )


def _load_json_model(path: Path, model_type: type[StrictReport]) -> StrictReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return model_type.model_validate(payload)
