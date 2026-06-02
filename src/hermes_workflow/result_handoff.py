from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from hermes_workflow.package import sha256_file
from hermes_workflow.reports import (
    RealRunCheckFlags,
    RealRunCheckReport,
    RealRunCheckStatus,
    RealRunResultStatus,
)
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
UTC_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
REPORT_RELATIVE = "reports/real_run_check_report.json"


class ResultSimulator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    preset: str
    command_label: str


class ResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    psf_dir: str
    spectre_out: str


class ResultManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    candidate_id: str
    status: RealRunResultStatus
    started_at_utc: str
    completed_at_utc: str
    simulator: ResultSimulator
    prepared_input_scs: str
    prepared_input_sha256: str
    log_file: str
    artifact_files: list[str]
    result_data: ResultData | None = None
    metric_result_manifest: str | None = None
    notes: str | None = None

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def _validate_utc_timestamp(cls, value: str) -> str:
        if not UTC_TIMESTAMP_RE.match(value):
            raise ValueError("timestamp must use UTC ISO format without microseconds")
        return value


def check_real_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
    persist_report: bool = True,
) -> RealRunCheckReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _project_path(bundle, run_relative)
    prepared_relative = f"{run_relative}/real_run_manifest.json"
    result_relative = f"{run_relative}/result_manifest.json"
    report_path = _project_path(bundle, REPORT_RELATIVE)
    if persist_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    checks = RealRunCheckFlags()
    prepared = _load_json(run_dir / "real_run_manifest.json", "real run manifest", issues)
    candidate = _load_json(run_dir / "candidate.json", "candidate file", issues)
    result_payload = _load_json(run_dir / "result_manifest.json", "result manifest", issues)

    result: ResultManifest | None = None
    if prepared and prepared.get("status") == "prepared":
        checks.prepared_manifest_ok = True
    elif prepared:
        issues.append("real run package is not prepared")
    if candidate:
        checks.candidate_ok = True
    if result_payload:
        try:
            result = ResultManifest.model_validate(result_payload)
            checks.result_manifest_ok = True
        except ValidationError:
            invalid_status = result_payload.get("status")
            allowed_statuses = {status.value for status in RealRunResultStatus}
            if invalid_status not in allowed_statuses:
                issues.append(f"result status is invalid: {invalid_status}")
            else:
                issues.append("result manifest is invalid")

    candidate_id: str | None = None
    result_status: RealRunResultStatus | None = None
    prepared_input_scs: str | None = None
    log_file: str | None = None
    artifact_files: list[str] = []

    if prepared and candidate and result:
        candidate_id = result.candidate_id
        result_status = result.status
        prepared_input_scs = result.prepared_input_scs
        log_file = result.log_file
        artifact_files = result.artifact_files
        _validate_cross_references(
            bundle,
            selected_run_id,
            prepared,
            candidate,
            result,
            issues,
            checks,
        )

    report = _build_report(
        run_id=selected_run_id,
        candidate_id=candidate_id,
        result_status=result_status,
        prepared_relative=prepared_relative,
        result_relative=result_relative,
        prepared_input_scs=prepared_input_scs,
        log_file=log_file,
        artifact_files=artifact_files,
        checks=checks,
        issues=issues,
    )
    if persist_report:
        _write_report(report_path, report)
    return report


def _validate_cross_references(
    bundle: ContractBundle,
    run_id: str,
    prepared: dict,
    candidate: dict,
    result: ResultManifest,
    issues: list[str],
    checks: RealRunCheckFlags,
) -> None:
    if result.run_id != run_id:
        issues.append("result run_id does not match requested run_id")
    if result.candidate_id != prepared.get("candidate_id"):
        issues.append("result candidate_id does not match prepared candidate")
    if result.candidate_id != candidate.get("candidate_id"):
        issues.append("result candidate_id does not match candidate file")
    if result.prepared_input_scs != prepared.get("rendered_input_scs"):
        issues.append("result prepared_input_scs does not match prepared manifest")

    hash_matches_manifest = result.prepared_input_sha256 == prepared.get(
        "rendered_input_sha256"
    )
    if not hash_matches_manifest:
        issues.append("prepared input hash mismatch")

    prepared_path = _safe_run_path(bundle, run_id, result.prepared_input_scs, issues)
    if prepared_path is not None and hash_matches_manifest:
        expected_hash = str(prepared.get("rendered_input_sha256"))
        if prepared_path.exists() and sha256_file(prepared_path) == expected_hash:
            checks.prepared_input_hash_ok = True
        else:
            issues.append("prepared input hash mismatch")

    artifact_paths = [result.log_file, *result.artifact_files]
    if result.result_data is not None:
        if result.result_data.kind != "spectre_psf":
            issues.append(f"result_data kind is invalid: {result.result_data.kind}")
        artifact_paths.extend(
            [result.result_data.psf_dir, result.result_data.spectre_out]
        )
    if result.metric_result_manifest is not None:
        artifact_paths.append(result.metric_result_manifest)

    resolved_artifacts = [
        _safe_run_path(bundle, run_id, artifact_path, issues)
        for artifact_path in artifact_paths
    ]
    missing = [
        artifact_path
        for artifact_path, resolved in zip(artifact_paths, resolved_artifacts, strict=True)
        if resolved is not None and not resolved.exists()
    ]
    for artifact_path in missing:
        issues.append(f"result artifact is missing: {artifact_path}")
    if all(path is not None and path.exists() for path in resolved_artifacts):
        checks.artifact_paths_ok = True


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_json(path: Path, label: str, issues: list[str]) -> dict | None:
    if not path.exists():
        issues.append(f"{label} is missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append(f"{label} is invalid")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label} is invalid")
        return None
    return payload


def _safe_run_path(
    bundle: ContractBundle,
    run_id: str,
    relative_path: str,
    issues: list[str],
) -> Path | None:
    path = PurePosixPath(relative_path)
    run_prefix = PurePosixPath(REAL_RUN_ROOT) / run_id
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(run_prefix):
        issues.append(f"result artifact path is unsafe: {relative_path}")
        return None
    return bundle.project_dir / Path(*path.parts)


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"real-run check path must be project-relative and safe: {relative_path}"
        )
    return bundle.project_dir / Path(*path.parts)


def _build_report(
    *,
    run_id: str,
    candidate_id: str | None,
    result_status: RealRunResultStatus | None,
    prepared_relative: str,
    result_relative: str,
    prepared_input_scs: str | None,
    log_file: str | None,
    artifact_files: list[str],
    checks: RealRunCheckFlags,
    issues: list[str],
) -> RealRunCheckReport:
    return RealRunCheckReport(
        schema_version="1.0",
        status=RealRunCheckStatus.FAIL if issues else RealRunCheckStatus.PASS,
        run_id=run_id,
        candidate_id=candidate_id,
        result_status=result_status,
        real_run_manifest=prepared_relative,
        result_manifest=result_relative,
        prepared_input_scs=prepared_input_scs,
        log_file=log_file,
        artifact_files=artifact_files,
        checks=checks,
        issues=issues,
    )


def _write_report(path: Path, report: RealRunCheckReport) -> None:
    path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
