from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterRunResult,
    load_adapter_context,
    render_ocean_replay_script,
)
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import quote_remote_path


def run_remote_spectre_ocean_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    testbench_id: str | None = None,
) -> AdapterRunResult:
    context = load_adapter_context(project_dir, run_id=run_id, testbench_id=testbench_id)
    script_path = Path(context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_base = remote_ref.remote_project_dir / "runs" / "real" / run_id
    if testbench_id is not None:
        remote_run_dir = remote_run_base / "testbenches" / testbench_id
    else:
        remote_run_dir = remote_run_base
    runner.upload_tree(context.run_dir, remote_run_dir)

    remote_input_dir = remote_run_dir / "netlist"
    spectre_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {quote_remote_path(remote_cadence_cshrc)}; cd {quote_remote_path(remote_input_dir)}; "
            f"spectre -64 +preset=aps +mt={context.request.spectre.get('threads_per_run', 1)} "
            f"-format psfxl -raw ../psf input.scs"
        )
    )
    spectre_result = runner.run(spectre_command)
    if spectre_result.return_code != 0:
        return _write_remote_failure(context, "spectre command failed", runner=runner, remote_run_dir=remote_run_dir)

    ocean_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {quote_remote_path(remote_cadence_cshrc)}; cd {quote_remote_path(remote_ref.remote_project_dir)}; "
            f"ocean -nograph -restore {quote_remote_path(remote_run_dir / 'metrics' / 'metric_probe.ocn')}"
        )
    )
    ocean_result = runner.run(ocean_command)
    if ocean_result.return_code != 0:
        return _write_remote_failure(context, "ocean command failed", runner=runner, remote_run_dir=remote_run_dir)

    runner.download_tree(remote_run_dir / "metrics", context.metrics_dir)
    result = _write_remote_success_manifests(context)
    runner.upload(context.run_dir / "result_manifest.json", remote_run_dir / "result_manifest.json")
    runner.upload(
        context.metrics_dir / "metric_result_manifest.json",
        remote_run_dir / "metrics" / "metric_result_manifest.json",
    )
    return result


def _write_remote_failure(context: Any, notes: str, *, runner: Any, remote_run_dir: PurePosixPath) -> AdapterRunResult:
    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_path = context.run_dir / "result_manifest.json"
    spectre_stderr = f"{context.run_relative}/spectre.stderr"
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "status": "failed",
        "started_at_utc": started,
        "completed_at_utc": started,
        "simulator": {
            "engine": "spectre",
            "preset": str(context.request.spectre.get("preset", "aps")),
            "output_format": str(context.request.spectre.get("output_format", "psfxl")),
            "threads_per_run": int(context.request.spectre.get("threads_per_run", 1)),
            "timeout_s": int(context.request.spectre.get("timeout_s", 3600)),
            "command_label": "remote_spectre_run",
        },
        "prepared_input_scs": context.prepared.rendered_input_scs,
        "prepared_input_sha256": context.prepared.rendered_input_sha256,
        "log_file": spectre_stderr,
        "artifact_files": [],
        "result_data": None,
        "metric_result_manifest": None,
        "notes": notes,
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runner.upload(result_path, remote_run_dir / "result_manifest.json")
    return AdapterRunResult(
        status="failed",
        run_id=context.run_id,
        result_manifest_path=result_path,
        metric_result_manifest_path=None,
        issues=[notes],
    )


def _write_remote_success_manifests(context: Any) -> AdapterRunResult:
    from hermes_workflow.execution_adapters.spectre_ocean import (
        METRIC_RESULT_MANIFEST_NAME,
        parse_ocean_scalars,
    )

    completed = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_path = context.run_dir / "result_manifest.json"
    spectre_out = f"{context.run_relative}/psf/spectre.out"
    metric_manifest_relative = f"{context.run_relative}/metrics/{METRIC_RESULT_MANIFEST_NAME}"
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "status": "succeeded",
        "started_at_utc": completed,
        "completed_at_utc": completed,
        "simulator": {
            "engine": "spectre",
            "preset": str(context.request.spectre.get("preset", "aps")),
            "output_format": str(context.request.spectre.get("output_format", "psfxl")),
            "threads_per_run": int(context.request.spectre.get("threads_per_run", 1)),
            "timeout_s": int(context.request.spectre.get("timeout_s", 3600)),
            "command_label": "remote_spectre_run",
        },
        "prepared_input_scs": context.prepared.rendered_input_scs,
        "prepared_input_sha256": context.prepared.rendered_input_sha256,
        "log_file": spectre_out,
        "artifact_files": [spectre_out],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": context.request.expected_psf_dir,
            "spectre_out": spectre_out,
        },
        "metric_result_manifest": metric_manifest_relative,
        "notes": "remote spectre and ocean completed",
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Write metric result manifest
    scalar_path = context.metrics_dir / "ocean_scalars.tsv"
    issues: list[str] = []
    try:
        scalar_rows = parse_ocean_scalars(scalar_path)
    except Exception as exc:
        scalar_rows = {}
        issues.append(str(exc))

    metrics = []
    for request_metric in context.request.metrics:
        row = scalar_rows.get(request_metric.name)
        if row is None:
            metrics.append({
                "name": request_metric.name,
                "status": "failed",
                "value": None,
                "value_text": None,
                "unit": request_metric.unit,
                "result": request_metric.result,
                "expression": request_metric.expression,
                "expression_sha256": request_metric.expression_sha256,
                "expression_source": request_metric.expression_source,
                "issues": ["metric missing from ocean scalar output"],
            })
            issues.append(f"metric {request_metric.name} missing from ocean scalar output")
            continue
        metric_issues = []
        if row.status != "pass":
            metric_issues.append(row.message or "ocean metric evaluation failed")
        metric_status = "succeeded" if not metric_issues else "failed"
        metrics.append({
            "name": request_metric.name,
            "status": metric_status,
            "value": row.value if metric_status == "succeeded" else None,
            "value_text": row.value_text if metric_status == "succeeded" else None,
            "unit": request_metric.unit,
            "result": request_metric.result,
            "expression": request_metric.expression,
            "expression_sha256": request_metric.expression_sha256,
            "expression_source": request_metric.expression_source,
            "issues": metric_issues,
        })

    extra_metrics = sorted(set(scalar_rows) - {metric.name for metric in context.request.metrics})
    issues.extend(f"unrequested metric in ocean scalar output: {name}" for name in extra_metrics)

    metric_manifest_path = context.metrics_dir / METRIC_RESULT_MANIFEST_NAME
    metric_payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "backend": "remote_spectre_ocean",
        "status": "succeeded" if not issues else "failed",
        "request_file": context.prepared.metric_extraction_request,
        "request_sha256": context.prepared.metric_extraction_request_sha256,
        "psf_dir": context.request.expected_psf_dir,
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0,
            "attempts": 1,
            "return_codes": [0],
            "script_file": context.request.ocean.script_file,
            "script_sha256": _sha256_text(render_ocean_replay_script(context)),
            "log_file": context.request.ocean.log_file,
            "scalar_output_file": context.request.ocean.scalar_output_file,
        },
        "metrics": metrics,
        "issues": issues,
    }
    metric_manifest_path.write_text(
        json.dumps(metric_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return AdapterRunResult(
        status="succeeded" if not issues else "failed",
        run_id=context.run_id,
        result_manifest_path=result_path,
        metric_result_manifest_path=metric_manifest_path,
        issues=issues,
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_remote_multi_testbench_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
) -> AdapterRunResult:
    from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run
    from hermes_workflow.validate import assert_valid_project

    bundle = assert_valid_project(project_dir)
    if bundle.testbenches is None:
        raise RuntimeError("run_remote_multi_testbench_adapter called without testbenches config")

    issues: list[str] = []
    for testbench in bundle.testbenches.testbenches:
        result = run_remote_spectre_ocean_adapter(
            project_dir,
            run_id=run_id,
            remote_ref=remote_ref,
            remote_cadence_cshrc=remote_cadence_cshrc,
            runner=runner,
            testbench_id=testbench.id,
        )
        if result.status != "succeeded":
            message = "; ".join(result.issues) or result.status
            issues.append(f"{testbench.id}: {message}")

    aggregate_report = aggregate_multi_testbench_run(project_dir, run_id=run_id)

    remote_run_dir = remote_ref.remote_project_dir / "runs" / "real" / run_id
    run_dir = project_dir / "runs" / "real" / run_id
    runner.upload(run_dir / "result_manifest.json", remote_run_dir / "result_manifest.json")
    runner.upload(
        run_dir / "metrics" / "metric_result_manifest.json",
        remote_run_dir / "metrics" / "metric_result_manifest.json",
    )

    if issues:
        return AdapterRunResult(
            status="failed",
            run_id=run_id,
            result_manifest_path=run_dir / "result_manifest.json",
            metric_result_manifest_path=run_dir / "metrics" / "metric_result_manifest.json",
            issues=issues,
        )
    return AdapterRunResult(
        status=aggregate_report.status if aggregate_report.status == "succeeded" else "failed",
        run_id=run_id,
        result_manifest_path=run_dir / "result_manifest.json",
        metric_result_manifest_path=run_dir / "metrics" / "metric_result_manifest.json",
        issues=list(aggregate_report.issues),
    )
