from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hermes_workflow.metric_results import MetricResultManifest
from hermes_workflow.package import sha256_file
from hermes_workflow.reports import MetricResultStatus, RealRunResultStatus
from hermes_workflow.result_handoff import ResultManifest
from hermes_workflow.validate import assert_valid_project

REAL_RUN_ROOT = "runs/real"
DEFAULT_RUN_ID = "real_001"
REPORT_RELATIVE = "reports/multi_testbench_aggregation_report.json"
AGGREGATE_TIMESTAMP = "2026-06-06T00:40:00Z"


class ChildAggregationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    testbench: str
    result_status: RealRunResultStatus
    metric_status: MetricResultStatus | None = None
    metrics: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class MultiTestbenchAggregationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    status: str
    run_id: str
    candidate_id: str | None
    result_manifest: str
    metric_result_manifest: str
    child_statuses: list[ChildAggregationStatus]
    issues: list[str] = Field(default_factory=list)


def aggregate_multi_testbench_run(
    project_dir: Path,
    *,
    run_id: str = DEFAULT_RUN_ID,
    completed_at_utc: str = AGGREGATE_TIMESTAMP,
) -> MultiTestbenchAggregationReport:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    if bundle.testbenches is None:
        raise ValueError("multi-testbench aggregation requires config/testbenches.yaml")

    run_prefix = f"{REAL_RUN_ROOT}/{run_id}"
    run_dir = _project_path(project_dir, run_prefix)
    prepared = _load_json(run_dir / "real_run_manifest.json")
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    candidate_id = str(prepared["candidate_id"])
    child_statuses: list[ChildAggregationStatus] = []
    child_results: list[dict] = []
    child_metric_results: list[dict] = []
    aggregate_metrics: list[dict] = []
    issues: list[str] = []
    real_failed = False
    metric_failed = False

    for testbench in bundle.testbenches.testbenches:
        expected_metric_names = [
            metric.name
            for metric in bundle.metrics.metrics
            if metric.testbench == testbench.id
        ]
        child = _load_child_handoff(
            project_dir,
            run_id=run_id,
            testbench_id=testbench.id,
            expected_metric_names=expected_metric_names,
        )
        child_statuses.append(child.status)
        child_results.append(child.result_reference)
        if child.metric_reference is not None:
            child_metric_results.append(child.metric_reference)
        aggregate_metrics.extend(child.metrics)
        issues.extend(child.status.issues)
        if child.real_failed:
            real_failed = True
        if child.metric_failed:
            metric_failed = True

    requested_metric_names = [metric["name"] for metric in request["metrics"]]
    aggregate_metric_names = [metric["name"] for metric in aggregate_metrics]
    for name in requested_metric_names:
        if name not in aggregate_metric_names:
            metric_failed = True
            issues.append(f"requested metric is missing from child results: {name}")

    result_status = (
        RealRunResultStatus.FAILED if real_failed else RealRunResultStatus.SUCCEEDED
    )
    metric_status = (
        MetricResultStatus.FAILED
        if real_failed or metric_failed
        else MetricResultStatus.SUCCEEDED
    )
    status = (
        "real_check_failed"
        if real_failed
        else "metric_check_failed"
        if metric_failed
        else "succeeded"
    )

    _write_aggregate_artifacts(
        project_dir=project_dir,
        run_id=run_id,
        prepared=prepared,
        request=request,
        request_path=request_path,
        result_status=result_status,
        metric_status=metric_status,
        aggregate_metrics=aggregate_metrics,
        child_results=child_results,
        child_metric_results=child_metric_results,
        issues=issues,
        completed_at_utc=completed_at_utc,
    )
    report = MultiTestbenchAggregationReport(
        schema_version="1.0",
        status=status,
        run_id=run_id,
        candidate_id=candidate_id,
        result_manifest=f"{run_prefix}/result_manifest.json",
        metric_result_manifest=f"{run_prefix}/metrics/metric_result_manifest.json",
        child_statuses=child_statuses,
        issues=issues,
    )
    _write_json(project_dir / REPORT_RELATIVE, report.model_dump(mode="json"))
    return report


class _LoadedChild(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: ChildAggregationStatus
    result_reference: dict
    metric_reference: dict | None
    metrics: list[dict]
    real_failed: bool
    metric_failed: bool


def _load_child_handoff(
    project_dir: Path,
    *,
    run_id: str,
    testbench_id: str,
    expected_metric_names: list[str],
) -> _LoadedChild:
    child_prefix = f"{REAL_RUN_ROOT}/{run_id}/testbenches/{testbench_id}"
    child_dir = _project_path(project_dir, child_prefix)
    result_relative = f"{child_prefix}/result_manifest.json"
    result_payload = _load_json_or_issue(child_dir / "result_manifest.json")
    issues: list[str] = []
    metrics: list[dict] = []
    metric_reference: dict | None = None
    metric_status: MetricResultStatus | None = None
    real_failed = False
    metric_failed = False

    result: ResultManifest | None = None
    if result_payload is None:
        real_failed = True
        issues.append(f"child result manifest is missing: {testbench_id}")
    else:
        try:
            result = ResultManifest.model_validate(result_payload)
        except ValidationError:
            real_failed = True
            issues.append(f"child result manifest is invalid: {testbench_id}")
        else:
            if result.status != RealRunResultStatus.SUCCEEDED:
                real_failed = True
                issues.append(f"child result is not succeeded: {testbench_id}")

    metric_relative = (
        result.metric_result_manifest
        if result is not None and result.metric_result_manifest is not None
        else f"{child_prefix}/metrics/metric_result_manifest.json"
    )
    metric_payload = _load_json_or_issue(_project_path(project_dir, metric_relative))
    manifest: MetricResultManifest | None = None
    if metric_payload is None:
        metric_failed = True
        issues.append(f"child metric result manifest is missing: {testbench_id}")
    else:
        try:
            manifest = MetricResultManifest.model_validate(metric_payload)
        except ValidationError:
            metric_failed = True
            issues.append(f"child metric result manifest is invalid: {testbench_id}")
        else:
            metric_status = manifest.status
            if manifest.status != MetricResultStatus.SUCCEEDED:
                metric_failed = True
                issues.extend(manifest.issues)

    child_metric_names: list[str] = []
    if manifest is not None:
        metrics_by_name = {
            metric.name: metric.model_dump(mode="json") for metric in manifest.metrics
        }
        for name in expected_metric_names:
            metric = metrics_by_name.get(name)
            if metric is None:
                metric_failed = True
                issues.append(f"child metric is missing: {testbench_id}/{name}")
                continue
            child_metric_names.append(name)
            metrics.append(metric)
            if metric["status"] != MetricResultStatus.SUCCEEDED:
                metric_failed = True

    result_status = (
        result.status if result is not None else RealRunResultStatus.FAILED
    )
    result_reference = {
        "testbench": testbench_id,
        "result_manifest": result_relative,
        "status": result_status,
        "metric_result_manifest": metric_relative,
        "issues": issues,
    }
    if manifest is not None:
        metric_reference = {
            "testbench": testbench_id,
            "metric_result_manifest": metric_relative,
            "status": manifest.status,
            "metrics": child_metric_names,
            "issues": manifest.issues,
        }

    return _LoadedChild(
        status=ChildAggregationStatus(
            testbench=testbench_id,
            result_status=result_status,
            metric_status=metric_status,
            metrics=child_metric_names,
            issues=issues,
        ),
        result_reference=result_reference,
        metric_reference=metric_reference,
        metrics=metrics,
        real_failed=real_failed,
        metric_failed=metric_failed,
    )


def _write_aggregate_artifacts(
    *,
    project_dir: Path,
    run_id: str,
    prepared: dict,
    request: dict,
    request_path: Path,
    result_status: RealRunResultStatus,
    metric_status: MetricResultStatus,
    aggregate_metrics: list[dict],
    child_results: list[dict],
    child_metric_results: list[dict],
    issues: list[str],
    completed_at_utc: str,
) -> None:
    run_prefix = f"{REAL_RUN_ROOT}/{run_id}"
    run_dir = _project_path(project_dir, run_prefix)
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    script_path = metrics_dir / "metric_probe.ocn"
    ocean_log_path = metrics_dir / "ocean.log"
    scalar_path = metrics_dir / "ocean_scalars.tsv"
    spectre_out_path = psf_dir / "spectre.out"
    spectre_log_path = run_dir / "spectre.log"
    script_path.write_text("; aggregate metric manifest\n", encoding="utf-8")
    ocean_log_path.write_text("aggregate ocean log\n", encoding="utf-8")
    scalar_path.write_text(_scalar_output_text(aggregate_metrics), encoding="utf-8")
    spectre_out_path.write_text("aggregate multi-testbench spectre output\n", encoding="utf-8")
    spectre_log_path.write_text("aggregate multi-testbench spectre log\n", encoding="utf-8")

    metric_manifest_relative = f"{run_prefix}/metrics/metric_result_manifest.json"
    result_manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": prepared["candidate_id"],
        "status": result_status,
        "started_at_utc": prepared["created_at_utc"],
        "completed_at_utc": completed_at_utc,
        "simulator": {
            "engine": prepared["spectre"]["engine"],
            "preset": prepared["spectre"]["preset"],
            "output_format": prepared["spectre"]["output_format"],
            "threads_per_run": prepared["spectre"]["threads_per_run"],
            "timeout_s": prepared["spectre"]["timeout_s"],
            "command_label": "multi_testbench_aggregate",
        },
        "prepared_input_scs": prepared["rendered_input_scs"],
        "prepared_input_sha256": prepared["rendered_input_sha256"],
        "log_file": f"{run_prefix}/spectre.log",
        "artifact_files": [
            f"{run_prefix}/psf/spectre.out",
            f"{run_prefix}/metrics/metric_probe.ocn",
            f"{run_prefix}/metrics/ocean.log",
            f"{run_prefix}/metrics/ocean_scalars.tsv",
            metric_manifest_relative,
        ],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": request["expected_psf_dir"],
            "spectre_out": f"{run_prefix}/psf/spectre.out",
        },
        "metric_result_manifest": metric_manifest_relative,
        "child_results": child_results,
        "notes": "Aggregated from per-testbench child result manifests.",
    }
    metric_manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": prepared["candidate_id"],
        "backend": request["backend"],
        "status": metric_status,
        "request_file": f"{run_prefix}/metric_extraction_request.json",
        "request_sha256": sha256_file(request_path),
        "psf_dir": request["expected_psf_dir"],
        "ocean": {
            "mode": request["ocean"]["mode"],
            "return_code": 0,
            "attempts": 1,
            "return_codes": [0],
            "script_file": request["ocean"]["script_file"],
            "script_sha256": sha256_file(script_path),
            "log_file": request["ocean"]["log_file"],
            "scalar_output_file": request["ocean"]["scalar_output_file"],
        },
        "metrics": aggregate_metrics,
        "child_metric_results": child_metric_results,
        "issues": issues,
    }
    _write_json(run_dir / "result_manifest.json", result_manifest)
    _write_json(metrics_dir / "metric_result_manifest.json", metric_manifest)


def _scalar_output_text(metrics: list[dict]) -> str:
    lines = ["metric\tstatus\tvalue_text"]
    for metric in metrics:
        lines.append(
            f"{metric['name']}\t{metric['status']}\t{metric.get('value_text') or ''}"
        )
    return "\n".join(lines) + "\n"


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _load_json_or_issue(path: Path) -> dict | None:
    if not path.exists():
        return None
    return _load_json(path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _project_path(project_dir: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"project path must be project-relative and safe: {relative_path}")
    return project_dir / Path(*path.parts)
