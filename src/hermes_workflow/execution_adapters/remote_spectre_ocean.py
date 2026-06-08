from __future__ import annotations

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
) -> AdapterRunResult:
    context = load_adapter_context(project_dir, run_id=run_id)
    script_path = Path(context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_dir = remote_ref.remote_project_dir / "runs" / "real" / run_id
    runner.upload_tree(context.run_dir, remote_run_dir)

    remote_input_dir = remote_run_dir / "netlist"
    spectre_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {remote_cadence_cshrc}; cd {remote_input_dir}; "
            f"spectre -64 +preset=aps +mt={context.request.spectre.get('threads_per_run', 1)} "
            f"-format psfxl -raw ../psf input.scs"
        )
    )
    spectre_result = runner.run(spectre_command)
    if spectre_result.return_code != 0:
        return _write_remote_failure(context, "spectre command failed")

    ocean_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {remote_cadence_cshrc}; cd {remote_ref.remote_project_dir}; "
            f"ocean -nograph -restore {remote_run_dir / 'metrics' / 'metric_probe.ocn'}"
        )
    )
    ocean_result = runner.run(ocean_command)
    if ocean_result.return_code != 0:
        return _write_remote_failure(context, "ocean command failed")

    runner.download_tree(remote_run_dir / "metrics", context.metrics_dir)
    result = _write_remote_success_manifests(context)
    runner.upload(context.run_dir / "result_manifest.json", remote_run_dir / "result_manifest.json")
    runner.upload(
        context.metrics_dir / "metric_result_manifest.json",
        remote_run_dir / "metrics" / "metric_result_manifest.json",
    )
    return result


def _write_remote_failure(context: Any, notes: str) -> AdapterRunResult:
    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_path = context.run_dir / "result_manifest.json"
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "status": "failed",
        "started_at_utc": started,
        "completed_at_utc": started,
        "backend": "remote_spectre_ocean",
        "notes": notes,
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "status": "succeeded",
        "started_at_utc": completed,
        "completed_at_utc": completed,
        "backend": "remote_spectre_ocean",
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
