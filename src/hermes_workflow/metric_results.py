from __future__ import annotations

import json
import math
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hermes_workflow.package import sha256_file
from hermes_workflow.reports import (
    CheckedMetricResult,
    MetricResultCheckFlags,
    MetricResultCheckReport,
    MetricResultCheckStatus,
    MetricResultStatus,
    RealRunResultStatus,
)
from hermes_workflow.result_handoff import ResultManifest
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
SPECTRE_NETLIST_DIR = "netlist"
METRIC_RESULT_REPORT = "reports/metric_result_check_report.json"
METRIC_REQUEST_NAME = "metric_extraction_request.json"
METRIC_RESULT_MANIFEST_NAME = "metrics/metric_result_manifest.json"
METRIC_BACKEND = "spectre_ocean_batch"
OCEAN_MODE = "nograph_replay"
FINITE_TEXT_FAILURES = {"", "nil", "NaN", "Inf", "-Inf"}


class OceanExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    return_code: int
    attempts: int = Field(default=1, ge=1)
    return_codes: list[int] = Field(default_factory=list)
    script_file: str
    script_sha256: str
    log_file: str
    scalar_output_file: str


class MetricResultEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: MetricResultStatus
    value: object = None
    value_text: str | None = None
    unit: str
    result: str | None = None
    expression: str
    expression_sha256: str
    expression_source: str
    issues: list[str] = Field(default_factory=list)


class ChildMetricResultReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    testbench: str
    metric_result_manifest: str
    status: MetricResultStatus
    metrics: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class MetricResultManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    candidate_id: str
    backend: str
    status: MetricResultStatus
    request_file: str
    request_sha256: str
    psf_dir: str
    ocean: OceanExecution
    metrics: list[MetricResultEntry]
    child_metric_results: list[ChildMetricResultReference] = Field(default_factory=list)
    command_trace: dict | None = None
    issues: list[str] = Field(default_factory=list)


class PreparedRealRunManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    run_id: str
    status: str
    candidate_id: str
    rendered_input_scs: str
    rendered_input_sha256: str
    metric_extraction_request: str
    metric_extraction_request_sha256: str
    spectre: dict


class MetricRequestOcean(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    script_file: str
    log_file: str
    scalar_output_file: str


class MetricRequestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    unit: str
    required_signals: list[str] = Field(default_factory=list)
    result: str | None = None
    expression: str
    expression_sha256: str
    expression_source: str
    source_reference: str
    expected_value_type: str
    nil_policy: str
    non_finite_policy: str


class MetricExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    candidate_id: str
    backend: str
    prepared_input_scs: str
    prepared_input_sha256: str
    expected_psf_dir: str
    spectre: dict
    ocean: MetricRequestOcean
    metrics: list[MetricRequestEntry]
    forbidden_actions: list[str] = Field(default_factory=list)


def check_metric_results(
    project_dir: Path,
    *,
    run_id: str | None = None,
    persist_report: bool = True,
) -> MetricResultCheckReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _project_path(bundle, run_relative)
    default_request_relative = f"{run_relative}/{METRIC_REQUEST_NAME}"
    default_result_relative = f"{run_relative}/{METRIC_RESULT_MANIFEST_NAME}"
    report_path = _project_path(bundle, METRIC_RESULT_REPORT)
    if persist_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    checks = MetricResultCheckFlags()
    prepared_payload = _load_json(
        run_dir / "real_run_manifest.json",
        "real run manifest",
        issues,
    )
    prepared = _validate_real_run_manifest(prepared_payload, issues)
    request_payload = _load_json(
        run_dir / METRIC_REQUEST_NAME,
        "metric extraction request",
        issues,
    )
    request = _validate_metric_request(request_payload, issues)
    handoff_payload = _load_json(run_dir / "result_manifest.json", "result manifest", issues)
    handoff = _validate_result_manifest(handoff_payload, checks, issues)
    result_relative = _declared_metric_result_manifest(
        bundle,
        selected_run_id,
        handoff,
        default_result_relative,
        issues,
    )
    result_path = _safe_run_path(
        bundle,
        selected_run_id,
        result_relative,
        issues,
        label="metric_result_manifest path",
    )
    manifest_payload = None
    if result_path is not None:
        manifest_payload = _load_json(result_path, "metric result manifest", issues)

    manifest: MetricResultManifest | None = None
    if manifest_payload is not None:
        try:
            manifest = MetricResultManifest.model_validate(manifest_payload)
            checks.metric_manifest_ok = True
        except ValidationError:
            issues.append("metric result manifest is invalid")

    metrics: dict[str, CheckedMetricResult] = {}
    candidate_id: str | None = None
    backend: str | None = None
    psf_dir: str | None = None
    if (
        prepared is not None
        and request is not None
        and handoff is not None
        and manifest is not None
    ):
        candidate_id = manifest.candidate_id
        backend = manifest.backend
        psf_dir = manifest.psf_dir
        _validate_manifest(
            bundle,
            selected_run_id,
            prepared,
            request,
            handoff,
            manifest,
            result_relative,
            checks,
            issues,
            metrics,
        )

    report = MetricResultCheckReport(
        schema_version="1.0",
        status=MetricResultCheckStatus.FAIL if issues else MetricResultCheckStatus.PASS,
        run_id=selected_run_id,
        candidate_id=candidate_id,
        backend=backend,
        request_file=default_request_relative,
        metric_result_manifest=result_relative,
        psf_dir=psf_dir,
        metrics=metrics,
        checks=checks,
        issues=issues,
    )
    if persist_report:
        report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report


def _validate_real_run_manifest(
    payload: dict | None,
    issues: list[str],
) -> PreparedRealRunManifest | None:
    if payload is None:
        return None
    try:
        return PreparedRealRunManifest.model_validate(payload)
    except ValidationError:
        issues.append("real run manifest is invalid")
        return None


def _validate_metric_request(
    payload: dict | None,
    issues: list[str],
) -> MetricExtractionRequest | None:
    if payload is None:
        return None
    try:
        return MetricExtractionRequest.model_validate(payload)
    except ValidationError:
        issues.append("metric extraction request is invalid")
        return None


def _validate_result_manifest(
    payload: dict | None,
    checks: MetricResultCheckFlags,
    issues: list[str],
) -> ResultManifest | None:
    if payload is None:
        return None
    try:
        handoff = ResultManifest.model_validate(payload)
    except ValidationError:
        issues.append("result manifest is invalid")
        return None
    if handoff.status == RealRunResultStatus.SUCCEEDED:
        checks.result_manifest_ok = True
    else:
        issues.append("simulator result is not succeeded")
    return handoff


def _declared_metric_result_manifest(
    bundle: ContractBundle,
    run_id: str,
    handoff: ResultManifest | None,
    default_relative: str,
    issues: list[str],
) -> str:
    if handoff is None:
        return default_relative
    if handoff.metric_result_manifest is None:
        issues.append("result manifest is missing metric_result_manifest")
        return default_relative
    if handoff.metric_result_manifest != default_relative:
        issues.append("metric_result_manifest path does not match expected path")
    if (
        _safe_run_path(
            bundle,
            run_id,
            handoff.metric_result_manifest,
            issues,
            label="metric_result_manifest path",
        )
        is None
    ):
        return handoff.metric_result_manifest
    return handoff.metric_result_manifest


def _validate_manifest(
    bundle: ContractBundle,
    run_id: str,
    prepared: PreparedRealRunManifest,
    request: MetricExtractionRequest,
    handoff: ResultManifest,
    manifest: MetricResultManifest,
    loaded_manifest_relative: str,
    checks: MetricResultCheckFlags,
    issues: list[str],
    metrics: dict[str, CheckedMetricResult],
) -> None:
    identity_ok = True
    if handoff.metric_result_manifest != loaded_manifest_relative:
        identity_ok = False
        issues.append(
            "metric_result_manifest path does not match loaded metric result manifest"
        )
    if manifest.run_id != run_id:
        identity_ok = False
        issues.append("metric result run_id does not match requested run_id")
    if manifest.candidate_id != request.candidate_id:
        identity_ok = False
        issues.append("metric result candidate_id does not match request")
    if manifest.candidate_id != handoff.candidate_id:
        identity_ok = False
        issues.append("metric result candidate_id does not match result manifest")
    if manifest.backend != request.backend:
        identity_ok = False
        issues.append("metric backend does not match request")
    if manifest.backend != METRIC_BACKEND:
        identity_ok = False
        issues.append(f"metric backend is invalid: {manifest.backend}")
    if request.run_id != run_id:
        identity_ok = False
        issues.append("metric request run_id does not match requested run_id")
    if request.candidate_id != handoff.candidate_id:
        identity_ok = False
        issues.append("metric request candidate_id does not match result manifest")
    if request.backend != METRIC_BACKEND:
        identity_ok = False
        issues.append(f"metric request backend is invalid: {request.backend}")
    expected_request_file = f"{REAL_RUN_ROOT}/{run_id}/{METRIC_REQUEST_NAME}"
    if manifest.request_file != expected_request_file:
        identity_ok = False
        issues.append("metric request_file does not match result manifest request")
    if prepared.metric_extraction_request != expected_request_file:
        identity_ok = False
        issues.append("metric request path does not match prepared manifest")
    if prepared.run_id != run_id:
        identity_ok = False
        issues.append("real run manifest run_id does not match requested run_id")
    if prepared.status != "prepared":
        identity_ok = False
        issues.append("real run package is not prepared")
    if prepared.candidate_id != request.candidate_id:
        identity_ok = False
        issues.append("metric request candidate_id does not match prepared manifest")
    if manifest.psf_dir != request.expected_psf_dir:
        identity_ok = False
        issues.append("metric psf_dir does not match request")
    if handoff.result_data is None:
        identity_ok = False
        issues.append("result manifest is missing result_data")
    elif handoff.result_data.kind != "spectre_psf":
        identity_ok = False
        issues.append(f"result_data kind is invalid: {handoff.result_data.kind}")
    elif manifest.psf_dir != handoff.result_data.psf_dir:
        identity_ok = False
        issues.append("metric psf_dir does not match result manifest")
    if manifest.ocean.mode != OCEAN_MODE:
        identity_ok = False
        issues.append(f"ocean mode is invalid: {manifest.ocean.mode}")
    if manifest.ocean.return_code != 0:
        identity_ok = False
        issues.append(f"ocean return_code is not zero: {manifest.ocean.return_code}")
    ocean_return_codes = manifest.ocean.return_codes or [manifest.ocean.return_code]
    if manifest.ocean.attempts != len(ocean_return_codes):
        identity_ok = False
        issues.append("ocean attempts does not match return_codes")
    if ocean_return_codes[-1] != manifest.ocean.return_code:
        identity_ok = False
        issues.append("ocean final return_code does not match return_codes")
    if not _validate_prepared_input_identity(bundle, run_id, prepared, request, handoff, issues):
        identity_ok = False

    request_path = _safe_run_path(bundle, run_id, manifest.request_file, issues)
    if request_path is not None and request_path.exists():
        current_request_sha256 = sha256_file(request_path)
        if manifest.request_sha256 == current_request_sha256:
            checks.request_hash_ok = True
        else:
            issues.append("metric request hash mismatch")
        if prepared.metric_extraction_request_sha256 != current_request_sha256:
            issues.append("metric extraction request hash does not match prepared manifest")
    else:
        issues.append("metric request hash mismatch")

    script_path = _safe_run_path(bundle, run_id, manifest.ocean.script_file, issues)
    if script_path is not None and script_path.exists():
        if manifest.ocean.script_sha256 != sha256_file(script_path):
            issues.append("ocean script hash mismatch")

    _validate_artifact_paths(
        bundle,
        run_id,
        handoff,
        manifest,
        checks,
        issues,
        prechecked_paths=[script_path],
    )
    metric_identity_ok = _validate_metric_entries(
        request,
        manifest,
        checks,
        issues,
        metrics,
    )

    if identity_ok and metric_identity_ok and not _has_identity_issue(issues):
        checks.metric_identity_ok = True


def _validate_artifact_paths(
    bundle: ContractBundle,
    run_id: str,
    handoff: ResultManifest,
    manifest: MetricResultManifest,
    checks: MetricResultCheckFlags,
    issues: list[str],
    *,
    prechecked_paths: list[Path | None],
) -> None:
    path_values = [
        manifest.request_file,
        manifest.psf_dir,
        manifest.ocean.log_file,
        manifest.ocean.scalar_output_file,
    ]
    resolved = [
        _safe_run_path(bundle, run_id, path_value, issues) for path_value in path_values
    ]
    path_values.append(manifest.ocean.script_file)
    resolved.extend(prechecked_paths)
    if handoff.result_data is not None:
        path_values.extend([handoff.result_data.psf_dir, handoff.result_data.spectre_out])
    for path_value in handoff.artifact_files:
        path_values.append(path_value)
    resolved.extend(
        _safe_run_path(bundle, run_id, path_value, issues)
        for path_value in path_values[len(resolved) :]
    )
    all_paths_ok = True
    for path_value, path in zip(path_values, resolved, strict=True):
        if path is None:
            all_paths_ok = False
        elif not path.exists():
            all_paths_ok = False
            issues.append(f"metric artifact is missing: {path_value}")
    checks.artifact_paths_ok = all_paths_ok


def _validate_prepared_input_identity(
    bundle: ContractBundle,
    run_id: str,
    prepared: PreparedRealRunManifest,
    request: MetricExtractionRequest,
    handoff: ResultManifest,
    issues: list[str],
) -> bool:
    identity_ok = True
    expected_input_scs = f"{REAL_RUN_ROOT}/{run_id}/{SPECTRE_NETLIST_DIR}/input.scs"
    if prepared.rendered_input_scs != expected_input_scs:
        identity_ok = False
        issues.append("prepared input path does not match expected path")
    if request.prepared_input_scs != prepared.rendered_input_scs:
        identity_ok = False
        issues.append("metric request prepared_input_scs does not match prepared manifest")
    if request.prepared_input_sha256 != prepared.rendered_input_sha256:
        identity_ok = False
        issues.append(
            "metric request prepared_input_sha256 does not match prepared manifest"
        )
    if handoff.prepared_input_scs != prepared.rendered_input_scs:
        identity_ok = False
        issues.append("result prepared_input_scs does not match prepared manifest")
    if handoff.prepared_input_sha256 != prepared.rendered_input_sha256:
        identity_ok = False
        issues.append("result prepared_input_sha256 does not match prepared manifest")

    prepared_path = _safe_run_path(bundle, run_id, expected_input_scs, issues)
    if prepared_path is None:
        return False
    if not prepared_path.exists():
        issues.append(f"prepared input file is missing: {expected_input_scs}")
        return False
    if sha256_file(prepared_path) != prepared.rendered_input_sha256:
        issues.append("prepared input file hash mismatch")
        return False
    return identity_ok


def _validate_metric_entries(
    request: MetricExtractionRequest,
    manifest: MetricResultManifest,
    checks: MetricResultCheckFlags,
    issues: list[str],
    metrics: dict[str, CheckedMetricResult],
) -> bool:
    identity_ok = True
    formula_ok = True
    scalar_ok = True
    if manifest.status != MetricResultStatus.SUCCEEDED:
        scalar_ok = False
        issues.append("metric result manifest status is not succeeded")
    request_metrics = {metric.name: metric for metric in request.metrics}
    result_names = [metric.name for metric in manifest.metrics]
    duplicate_names = sorted(
        name for name, count in Counter(result_names).items() if count > 1
    )
    for name in duplicate_names:
        identity_ok = False
        issues.append(f"duplicate metric in metric results: {name}")
    result_metrics = {}
    for metric in manifest.metrics:
        result_metrics.setdefault(metric.name, metric)

    for name in sorted(set(request_metrics) - set(result_metrics)):
        identity_ok = False
        issues.append(f"requested metric is missing from metric results: {name}")
    for name in sorted(set(result_metrics) - set(request_metrics)):
        identity_ok = False
        issues.append(f"unrequested metric in metric results: {name}")

    for name in sorted(set(request_metrics) & set(result_metrics)):
        request_metric = request_metrics[name]
        result_metric = result_metrics[name]
        request_expression_sha256 = _expression_sha256(request_metric.expression)
        result_expression_sha256 = _expression_sha256(result_metric.expression)
        if request_metric.expression_sha256 != request_expression_sha256:
            formula_ok = False
            issues.append(f"metric {name} request expression hash is invalid")
        if result_metric.expression_sha256 != result_expression_sha256:
            formula_ok = False
            issues.append(f"metric {name} expression hash is invalid")
        if result_metric.expression != request_metric.expression:
            formula_ok = False
            issues.append(f"metric {name} expression does not match request")
        if result_metric.expression_sha256 != request_metric.expression_sha256:
            formula_ok = False
            issues.append(f"metric {name} expression hash does not match request")
        if result_metric.unit != request_metric.unit:
            identity_ok = False
            issues.append(f"metric {name} unit does not match request")
        if result_metric.result != request_metric.result:
            identity_ok = False
            issues.append(f"metric {name} result selector does not match request")
        if result_metric.expression_source != request_metric.expression_source:
            identity_ok = False
            issues.append(f"metric {name} expression source does not match request")
        if result_metric.status != MetricResultStatus.SUCCEEDED:
            scalar_ok = False
            issues.append(f"metric {name} did not succeed")
        numeric_value = _json_number_value(result_metric.value)
        if numeric_value is None and result_metric.value is not None:
            scalar_ok = False
            issues.append(f"metric {name} value is not a JSON number")
        if numeric_value is None or not math.isfinite(numeric_value):
            scalar_ok = False
            issues.append(f"metric {name} value is not finite")
        if result_metric.value_text is None or result_metric.value_text in (
            FINITE_TEXT_FAILURES
        ):
            scalar_ok = False
            issues.append(f"metric {name} value_text is not a finite scalar")
        elif "srrWave" in result_metric.value_text:
            scalar_ok = False
            issues.append(f"metric {name} value_text looks like a waveform object")
        metrics[name] = CheckedMetricResult(
            status=result_metric.status,
            value=numeric_value,
            value_text=result_metric.value_text,
            unit=result_metric.unit,
            expression_sha256=result_metric.expression_sha256,
        )

    checks.formula_hashes_ok = formula_ok
    checks.scalar_values_ok = scalar_ok
    return identity_ok


def _json_number_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _expression_sha256(expression: str) -> str:
    return sha256(expression.encode("utf-8")).hexdigest()


def _has_identity_issue(issues: list[str]) -> bool:
    identity_fragments = (
        "run_id",
        "candidate_id",
        "backend",
        "request_file",
        "metric request path",
        "psf_dir",
        "unit does not match",
        "result selector",
        "expression source",
        "metric_result_manifest path",
        "duplicate metric",
        "requested metric",
        "unrequested metric",
        "result_data",
        "real run manifest",
        "prepared manifest",
        "prepared_input",
        "prepared input",
    )
    return any(any(fragment in issue for fragment in identity_fragments) for issue in issues)


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
    *,
    label: str = "metric artifact path",
) -> Path | None:
    path = PurePosixPath(relative_path)
    run_prefix = PurePosixPath(REAL_RUN_ROOT) / run_id
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(run_prefix):
        issues.append(f"{label} is unsafe: {relative_path}")
        return None
    return bundle.project_dir / Path(*path.parts)


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"metric result check path must be project-relative and safe: {relative_path}"
        )
    return bundle.project_dir / Path(*path.parts)
