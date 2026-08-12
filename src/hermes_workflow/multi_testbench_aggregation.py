from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hermes_workflow.metric_results import MetricResultManifest
from hermes_workflow.native_turbo import evaluate_candidate_objective
from hermes_workflow.package import sha256_file
from hermes_workflow.reports import MetricResultStatus, RealRunResultStatus
from hermes_workflow.result_handoff import ResultManifest
from hermes_workflow.validate import assert_valid_project

REAL_RUN_ROOT = "runs/real"
DEFAULT_RUN_ID = "real_001"
DEFAULT_TESTBENCH_ID = "default_testbench"
REPORT_RELATIVE = "reports/multi_testbench_aggregation_report.json"


class ChildAggregationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    testbench: str
    corner: str | None = None
    result_status: RealRunResultStatus
    metric_status: MetricResultStatus
    metrics: list[str]
    issues: list[str]


class MultiTestbenchAggregationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    status: str
    run_id: str
    candidate_id: str
    result_manifest: str
    metric_result_manifest: str
    child_statuses: list[ChildAggregationStatus]
    constraint_policy: str = "nominal"
    objective_policy: str = "nominal"
    worst_corner: str | None = None
    selected_corner: str | None = None
    corner_objectives: dict[str, float] = Field(default_factory=dict)
    corner_status_counts: dict[str, int] = Field(default_factory=dict)
    corner_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class _LoadedChild(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: ChildAggregationStatus
    result_reference: dict
    metric_reference: dict | None
    command_trace: dict | None = None
    metrics: list[dict]
    real_failed: bool
    metric_failed: bool


@dataclass(frozen=True)
class _CornerAggregate:
    metrics_by_name: dict[str, float]
    metric_rows: list[dict]
    real_failed: bool
    metric_failed: bool


def aggregate_multi_testbench_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
) -> MultiTestbenchAggregationReport:
    project_dir = Path(project_dir)
    selected_run_id = run_id or DEFAULT_RUN_ID
    aggregate_started_at_utc = _utc_now()
    bundle = assert_valid_project(project_dir)

    corner_ids, objective_policy, constraint_policy = _configured_corner_ids(bundle)
    nominal_corner = _nominal_corner_key(corner_ids)
    run_prefix = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _project_path(project_dir, run_prefix)
    prepared = _load_json(run_dir / "real_run_manifest.json")
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    candidate_id = str(request.get("candidate_id", selected_run_id))

    child_statuses: list[ChildAggregationStatus] = []
    child_results: list[dict] = []
    child_metric_results: list[dict] = []
    child_command_traces: list[dict] = []
    issues: list[str] = []
    corner_aggregates: dict[str, _CornerAggregate] = {}
    real_failed = False
    metric_failed = False

    for corner_id in corner_ids:
        corner_key = _corner_key(corner_id)
        metrics_by_name: dict[str, float] = {}
        metric_rows: list[dict] = []
        corner_real_failed = False
        corner_metric_failed = False

        for testbench_id, testbench_label, expected_metric_names in _aggregation_testbench_specs(
            bundle
        ):
            child = _load_child_handoff(
                project_dir,
                run_id=selected_run_id,
                testbench_id=testbench_id,
                testbench_label=testbench_label,
                corner_id=corner_id,
                expected_metric_names=expected_metric_names,
            )
            child_statuses.append(child.status)
            child_results.append(child.result_reference)
            if child.metric_reference is not None:
                child_metric_results.append(child.metric_reference)
            if child.command_trace is not None:
                child_command_traces.append(child.command_trace)
            issues.extend(child.status.issues)
            corner_real_failed = corner_real_failed or child.real_failed
            corner_metric_failed = corner_metric_failed or child.metric_failed
            for metric_row in child.metrics:
                metric_rows.append(metric_row)
                if (
                    metric_row.get("status") == "succeeded"
                    and metric_row.get("value") is not None
                ):
                    metrics_by_name[str(metric_row["name"])] = float(metric_row["value"])

        corner_aggregates[corner_key] = _CornerAggregate(
            metrics_by_name=metrics_by_name,
            metric_rows=metric_rows,
            real_failed=corner_real_failed,
            metric_failed=corner_metric_failed,
        )
        real_failed = real_failed or corner_real_failed
        metric_failed = metric_failed or corner_metric_failed

    selected_corner = nominal_corner
    worst_corner: str | None = None
    corner_objectives: dict[str, float] = {}
    corner_statuses: dict[str, str] = {}
    aggregate_metrics = list(corner_aggregates[nominal_corner].metric_rows)

    if real_failed:
        aggregate_status = "real_check_failed"
        result_status = RealRunResultStatus.FAILED
        metric_status = MetricResultStatus.FAILED
    else:
        result_status = RealRunResultStatus.SUCCEEDED
        metric_status = MetricResultStatus.SUCCEEDED
        aggregate_status = "succeeded"

        if metric_failed:
            aggregate_status = "metric_check_failed"
            metric_status = MetricResultStatus.FAILED
        else:
            for corner_key, corner in corner_aggregates.items():
                evaluation = evaluate_candidate_objective(
                    bundle.metrics,
                    bundle.optimizer,
                    corner.metrics_by_name,
                )
                corner_statuses[corner_key] = evaluation.status
                if evaluation.status == "metric_failed":
                    aggregate_status = "metric_check_failed"
                    metric_status = MetricResultStatus.FAILED
                    metric_failed = True
                    issues.extend(
                        [f"{corner_key}: {issue}" for issue in evaluation.issues]
                    )
                else:
                    corner_objectives[corner_key] = float(evaluation.objective)

            if not metric_failed:
                constraint_corners = (
                    [nominal_corner]
                    if constraint_policy == "nominal"
                    else list(corner_aggregates)
                )
                violating_corners = [
                    corner_key
                    for corner_key in constraint_corners
                    if corner_statuses.get(corner_key) == "constraint_failed"
                ]
                if violating_corners:
                    aggregate_status = "constraint_failed"
                    selected_corner = max(
                        violating_corners,
                        key=lambda corner_key: corner_objectives[corner_key],
                    )
                    worst_corner = selected_corner
                else:
                    objective_corners = (
                        [nominal_corner]
                        if objective_policy == "nominal"
                        else list(corner_objectives)
                    )
                    selected_corner = max(
                        objective_corners,
                        key=lambda corner_key: corner_objectives[corner_key],
                    )
                    if objective_policy == "worst_case":
                        worst_corner = selected_corner

                aggregate_metrics = list(corner_aggregates[selected_corner].metric_rows)

    aggregate_completed_at_utc = _utc_now()
    _write_aggregate_artifacts(
        project_dir=project_dir,
        run_id=selected_run_id,
        prepared=prepared,
        request=request,
        request_path=request_path,
        result_status=result_status,
        metric_status=metric_status,
        aggregate_metrics=aggregate_metrics,
        child_results=child_results,
        child_metric_results=child_metric_results,
        child_command_traces=child_command_traces,
        issues=issues,
        aggregate_started_at_utc=aggregate_started_at_utc,
        aggregate_completed_at_utc=aggregate_completed_at_utc,
    )

    report = MultiTestbenchAggregationReport(
        schema_version="1.0",
        status=aggregate_status,
        run_id=selected_run_id,
        candidate_id=candidate_id,
        result_manifest=f"{run_prefix}/result_manifest.json",
        metric_result_manifest=f"{run_prefix}/metrics/metric_result_manifest.json",
        child_statuses=child_statuses,
        constraint_policy=constraint_policy,
        objective_policy=objective_policy,
        worst_corner=worst_corner,
        selected_corner=selected_corner,
        corner_objectives=corner_objectives,
        corner_status_counts=dict(Counter(corner_statuses.values())),
        corner_metrics={
            corner_key: dict(corner.metrics_by_name)
            for corner_key, corner in corner_aggregates.items()
        },
        issues=issues,
    )
    _write_json(project_dir / REPORT_RELATIVE, report.model_dump(mode="json"))
    _write_json(
        project_dir / "runs" / "real" / selected_run_id / "multi_testbench_aggregation_report.json",
        report.model_dump(mode="json"),
    )
    return report


def _load_child_handoff(
    project_dir: Path,
    *,
    run_id: str,
    testbench_id: str | None,
    testbench_label: str,
    corner_id: str | None,
    expected_metric_names: list[str],
) -> _LoadedChild:
    child_prefix = f"{REAL_RUN_ROOT}/{run_id}"
    if testbench_id is not None:
        child_prefix = f"{child_prefix}/testbenches/{testbench_id}"
    if corner_id is not None:
        child_prefix = f"{child_prefix}/corners/{corner_id}"
    label = _child_label(testbench_label, corner_id)
    result_relative = f"{child_prefix}/result_manifest.json"
    result_payload = _load_json(project_dir / result_relative)
    issues: list[str] = []
    metrics: list[dict] = []
    metric_status = MetricResultStatus.FAILED
    real_failed = False
    metric_failed = False

    result: ResultManifest | None = None
    if result_payload is None:
        real_failed = True
        issues.append(f"child result manifest is missing: {label}")
    else:
        try:
            result = ResultManifest.model_validate(result_payload)
        except ValidationError:
            real_failed = True
            issues.append(f"child result manifest is invalid: {label}")
        else:
            if result.status != RealRunResultStatus.SUCCEEDED:
                real_failed = True
                issues.append(f"child result is not succeeded: {label}")

    metric_relative = (
        result.metric_result_manifest
        if result is not None and result.metric_result_manifest
        else f"{child_prefix}/metrics/metric_result_manifest.json"
    )
    metric_payload = _load_json(project_dir / metric_relative)

    manifest: MetricResultManifest | None = None
    if metric_payload is None:
        metric_failed = True
        issues.append(f"child metric result manifest is missing: {label}")
    else:
        try:
            manifest = MetricResultManifest.model_validate(metric_payload)
        except ValidationError:
            metric_failed = True
            issues.append(f"child metric result manifest is invalid: {label}")
        else:
            metric_status = manifest.status
            if manifest.status != MetricResultStatus.SUCCEEDED:
                metric_failed = True
                issues.append(f"child metric result is not succeeded: {label}")
            else:
                metric_names = {
                    metric.name: metric.model_dump(mode="json")
                    for metric in manifest.metrics
                }
                for name in expected_metric_names:
                    metric_row = metric_names.get(name)
                    if metric_row is None:
                        metric_failed = True
                        issues.append(
                            f"requested metric is missing from child results: {name}"
                        )
                        continue
                    metrics.append(metric_row)

    result_status = (
        result.status if result is not None else RealRunResultStatus.FAILED
    )
    child_metric_names = [str(metric.get("name", "")) for metric in metrics]
    result_reference = {
        "testbench": testbench_label,
        "result_manifest": result_relative,
        "status": result_status,
        "metric_result_manifest": metric_relative,
        "issues": issues,
    }
    metric_reference = (
        {
            "testbench": testbench_label,
            "metric_result_manifest": metric_relative,
            "status": manifest.status,
            "metrics": child_metric_names,
            "issues": manifest.issues,
        }
        if manifest is not None
        else None
    )
    command_trace = _build_child_command_trace_reference(
        testbench=testbench_label,
        result_manifest=result_relative,
        metric_result_manifest=metric_relative,
        result_payload=result_payload,
        metric_payload=metric_payload,
    )
    return _LoadedChild(
        status=ChildAggregationStatus(
            testbench=testbench_label,
            corner=corner_id,
            result_status=result_status,
            metric_status=metric_status,
            metrics=child_metric_names,
            issues=issues,
        ),
        result_reference=result_reference,
        metric_reference=metric_reference,
        command_trace=command_trace,
        metrics=metrics,
        real_failed=real_failed,
        metric_failed=metric_failed,
    )


def _build_child_command_trace_reference(
    *,
    testbench: str,
    result_manifest: str,
    metric_result_manifest: str,
    result_payload: dict | None,
    metric_payload: dict | None,
) -> dict | None:
    result_trace = (
        result_payload.get("command_trace") if isinstance(result_payload, dict) else None
    )
    metric_trace = (
        metric_payload.get("command_trace") if isinstance(metric_payload, dict) else None
    )
    if not isinstance(result_trace, dict) and not isinstance(metric_trace, dict):
        return None
    child: dict = {
        "testbench": testbench,
        "result_manifest": result_manifest,
        "metric_result_manifest": metric_result_manifest,
    }
    if isinstance(result_trace, dict):
        child["result"] = result_trace
    if isinstance(metric_trace, dict):
        child["metric"] = metric_trace
    return child


def _build_aggregate_command_trace(child_command_traces: list[dict]) -> dict | None:
    if not child_command_traces:
        return None
    execution_modes = sorted(
        {
            str(trace.get("result", trace.get("metric", {})).get("execution_mode"))
            for trace in child_command_traces
            if isinstance(trace.get("result", trace.get("metric", {})), dict)
            and trace.get("result", trace.get("metric", {})).get("execution_mode")
            is not None
        }
    )
    execution_mode = execution_modes[0] if len(execution_modes) == 1 else "mixed"
    return {
        "schema_version": "1.0",
        "execution_mode": execution_mode,
        "aggregate": {
            "kind": "multi_testbench_parent",
            "children": child_command_traces,
        },
    }


def _write_aggregate_artifacts(
    project_dir: Path,
    *,
    run_id: str,
    prepared: dict,
    request: dict,
    request_path: Path,
    result_status: RealRunResultStatus,
    metric_status: MetricResultStatus,
    aggregate_metrics: list[dict],
    child_results: list[dict],
    child_metric_results: list[dict],
    child_command_traces: list[dict],
    issues: list[str],
    aggregate_started_at_utc: str,
    aggregate_completed_at_utc: str,
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

    script_path.write_text("aggregate metric probe\n", encoding="utf-8")
    ocean_log_path.write_text("aggregate ocean log\n", encoding="utf-8")
    scalar_path.write_text(_scalar_output_text(aggregate_metrics), encoding="utf-8")
    spectre_out_path.write_text("aggregate spectre output\n", encoding="utf-8")
    spectre_log_path.write_text("aggregate spectre log\n", encoding="utf-8")

    prepared_input_relative = str(prepared.get("rendered_input_scs", f"{run_prefix}/netlist/input.scs"))
    prepared_input_path = _project_path(project_dir, prepared_input_relative)
    candidate_id = str(request.get("candidate_id", run_id))
    metric_manifest_relative = f"{run_prefix}/metrics/metric_result_manifest.json"

    result_manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "status": result_status.value,
        "started_at_utc": aggregate_started_at_utc,
        "completed_at_utc": aggregate_completed_at_utc,
        "simulator": _aggregate_simulator_metadata(prepared=prepared, request=request),
        "prepared_input_scs": prepared_input_relative,
        "prepared_input_sha256": sha256_file(prepared_input_path),
        "log_file": f"{run_prefix}/spectre.log",
        "artifact_files": [
            f"{run_prefix}/psf",
            f"{run_prefix}/psf/spectre.out",
            f"{run_prefix}/metrics/ocean.log",
            f"{run_prefix}/metrics/ocean_scalars.tsv",
        ],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": f"{run_prefix}/psf",
            "spectre_out": f"{run_prefix}/psf/spectre.out",
        },
        "metric_result_manifest": metric_manifest_relative,
        "child_results": child_results,
        "notes": "; ".join(issues),
    }
    if result_status == RealRunResultStatus.FAILED:
        result_manifest["notes"] = "; ".join(issues) or "aggregate child execution failed"

    metric_manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "backend": "spectre_ocean_batch",
        "status": metric_status.value,
        "request_file": request_path.relative_to(project_dir).as_posix(),
        "request_sha256": sha256_file(request_path),
        "psf_dir": f"{run_prefix}/psf",
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0 if metric_status == MetricResultStatus.SUCCEEDED else 1,
            "attempts": 1,
            "return_codes": [0 if metric_status == MetricResultStatus.SUCCEEDED else 1],
            "script_file": f"{run_prefix}/metrics/metric_probe.ocn",
            "script_sha256": sha256_file(script_path),
            "log_file": f"{run_prefix}/metrics/ocean.log",
            "scalar_output_file": f"{run_prefix}/metrics/ocean_scalars.tsv",
        },
        "metrics": aggregate_metrics,
        "child_metric_results": child_metric_results,
        "issues": issues if metric_status == MetricResultStatus.FAILED else [],
    }
    aggregate_command_trace = _build_aggregate_command_trace(child_command_traces)
    if aggregate_command_trace is not None:
        result_manifest["command_trace"] = aggregate_command_trace
        metric_manifest["command_trace"] = aggregate_command_trace

    _write_json(run_dir / "result_manifest.json", result_manifest)
    _write_json(metrics_dir / "metric_result_manifest.json", metric_manifest)


def _scalar_output_text(metrics: list[dict]) -> str:
    lines = ["metric\tstatus\tvalue_text"]
    for metric in metrics:
        lines.append(
            f"{metric['name']}\t{metric['status']}\t{metric.get('value_text') or ''}"
        )
    return "\n".join(lines) + "\n"


def _aggregate_simulator_metadata(*, prepared: dict, request: dict) -> dict:
    spectre: dict = {}
    prepared_spectre = prepared.get("spectre")
    if isinstance(prepared_spectre, dict):
        spectre.update(prepared_spectre)
    request_spectre = request.get("spectre")
    if isinstance(request_spectre, dict):
        spectre.update(request_spectre)
    return {
        "engine": str(spectre.get("engine", "spectre_x")),
        "preset": str(spectre.get("preset", "ax")),
        "output_format": str(spectre.get("output_format", "psfxl")),
        "threads_per_run": int(spectre.get("threads_per_run", 10)),
        "timeout_s": int(spectre.get("timeout_s", 3600)),
        "command_label": "multi_testbench_aggregate",
    }


def _aggregation_testbench_specs(
    bundle,
) -> list[tuple[str | None, str, list[str]]]:
    if bundle.testbenches is None:
        return [
            (
                None,
                DEFAULT_TESTBENCH_ID,
                [metric.name for metric in bundle.metrics.metrics if metric.testbench is None],
            )
        ]
    return [
        (
            testbench.id,
            testbench.id,
            [metric.name for metric in bundle.metrics.metrics if metric.testbench == testbench.id],
        )
        for testbench in bundle.testbenches.testbenches
    ]


def _configured_corner_ids(bundle) -> tuple[list[str | None], str, str]:
    process_corners = getattr(bundle, "process_corners", None)
    if process_corners is None:
        return [None], "nominal", "nominal"
    corner_ids = [corner.id for corner in process_corners.corners]
    if (
        process_corners.objective_policy == "nominal"
        and "nominal" not in corner_ids
    ):
        raise ValueError(
            "process_corners objective_policy=nominal requires a corner with "
            "id=nominal"
        )
    return (
        corner_ids,
        process_corners.objective_policy,
        process_corners.constraint_policy,
    )


def _nominal_corner_key(corner_ids: list[str | None]) -> str:
    keys = [_corner_key(corner_id) for corner_id in corner_ids]
    return "nominal" if "nominal" in keys else keys[0]


def _corner_key(corner_id: str | None) -> str:
    return corner_id or "nominal"


def _child_label(testbench_id: str, corner_id: str | None) -> str:
    return testbench_id if corner_id is None else f"{testbench_id}/{corner_id}"


def _project_path(project_dir: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay within project: {relative_path}")
    return project_dir / Path(*path.parts)


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
