from __future__ import annotations

import shlex
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.execution_adapters.spectre_ocean import (
    METRIC_RESULT_MANIFEST_NAME,
    OCEAN_MAX_ATTEMPTS,
    OCEAN_STDERR_NAME,
    OCEAN_STDOUT_NAME,
    RESULT_MANIFEST_NAME,
    SPECTRE_STDERR_NAME,
    SPECTRE_STDOUT_NAME,
    AdapterRunResult,
    _project_relative_path,
    build_ocean_argv,
    build_spectre_argv,
    load_adapter_context,
    render_ocean_replay_script,
    write_metric_result_manifest,
    write_spectre_result_manifest,
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
    script_path = _project_relative_path(context.project_dir, context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_base = remote_ref.remote_project_dir / "runs" / "real" / run_id
    if testbench_id is not None:
        remote_run_dir = remote_run_base / "testbenches" / testbench_id
    else:
        remote_run_dir = remote_run_base
    runner.upload_tree(context.run_dir, remote_run_dir)

    remote_input_dir = remote_run_dir / "netlist"
    spectre_argv = build_spectre_argv(context)
    spectre_cmd_body = " ".join(shlex.quote(a) for a in spectre_argv)
    spectre_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {quote_remote_path(remote_cadence_cshrc)}; "
            f"cd {quote_remote_path(remote_input_dir)}; "
            f"{spectre_cmd_body}"
        )
    )
    spectre_result = runner.run(spectre_command)

    # Write spectre diagnostics locally from captured output and upload to
    # remote so that failure paths always have diagnostic artifacts available.
    (context.run_dir / SPECTRE_STDOUT_NAME).write_text(
        spectre_result.stdout, encoding="utf-8",
    )
    (context.run_dir / SPECTRE_STDERR_NAME).write_text(
        spectre_result.stderr, encoding="utf-8",
    )
    runner.upload(context.run_dir / SPECTRE_STDOUT_NAME, remote_run_dir / SPECTRE_STDOUT_NAME)
    runner.upload(context.run_dir / SPECTRE_STDERR_NAME, remote_run_dir / SPECTRE_STDERR_NAME)

    if spectre_result.return_code != 0:
        return _write_remote_failure(context, "spectre command failed", runner=runner, remote_run_dir=remote_run_dir)

    # Download Spectre artifacts: psf/
    runner.download_tree(remote_run_dir / "psf", context.psf_dir)

    # Validate required Spectre artifacts exist locally
    if not context.psf_dir.is_dir():
        return _write_remote_failure(context, "psf directory missing after download", runner=runner, remote_run_dir=remote_run_dir)
    if not (context.psf_dir / "spectre.out").is_file():
        return _write_remote_failure(context, "psf/spectre.out missing after download", runner=runner, remote_run_dir=remote_run_dir)

    ocean_argv = build_ocean_argv(context)
    ocean_cmd_body = " ".join(shlex.quote(a) for a in ocean_argv)
    ocean_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {quote_remote_path(remote_cadence_cshrc)}; "
            f"cd {quote_remote_path(remote_ref.remote_project_dir)}; "
            f"{ocean_cmd_body}"
        )
    )

    # Retry OCEAN up to OCEAN_MAX_ATTEMPTS, matching local adapter semantics.
    ocean_return_codes: list[int] = []
    for _attempt in range(OCEAN_MAX_ATTEMPTS):
        ocean_result = runner.run(ocean_command)
        ocean_return_codes.append(ocean_result.return_code)
        if ocean_result.return_code == 0:
            break

    # Download OCEAN artifacts regardless of return code, matching local
    # adapter behaviour where the metric manifest records the failure.
    runner.download_tree(remote_run_dir / "metrics", context.metrics_dir)

    # Write ocean diagnostics locally from the LAST attempt (the one that
    # determined success/failure) and upload to remote.  Written after
    # download_tree so that the captured output is not overwritten by the
    # download of remote artifacts.
    context.metrics_dir.mkdir(parents=True, exist_ok=True)
    (context.metrics_dir / OCEAN_STDOUT_NAME).write_text(
        ocean_result.stdout, encoding="utf-8",
    )
    (context.metrics_dir / OCEAN_STDERR_NAME).write_text(
        ocean_result.stderr, encoding="utf-8",
    )
    runner.upload(context.metrics_dir / OCEAN_STDOUT_NAME, remote_run_dir / "metrics" / OCEAN_STDOUT_NAME)
    runner.upload(context.metrics_dir / OCEAN_STDERR_NAME, remote_run_dir / "metrics" / OCEAN_STDERR_NAME)

    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed = started

    # Write metric result manifest first (records ocean failure if rc != 0).
    # write_metric_result_manifest handles missing ocean_scalars.tsv gracefully
    # by recording AdapterPreconditionError in the manifest issues, matching
    # local adapter semantics.
    metric_result = write_metric_result_manifest(
        context,
        ocean_return_code=ocean_result.return_code,
        ocean_return_codes=ocean_return_codes,
    )

    # Result manifest always says "succeeded" when spectre succeeded,
    # matching local adapter semantics.
    result_manifest_path = write_spectre_result_manifest(
        context,
        status="succeeded",
        started_at_utc=started,
        completed_at_utc=completed,
        include_metric_manifest=True,
        notes="spectre command completed",
    )

    # Upload both manifests back to remote.
    runner.upload(result_manifest_path, remote_run_dir / RESULT_MANIFEST_NAME)
    runner.upload(
        metric_result.path,
        remote_run_dir / "metrics" / METRIC_RESULT_MANIFEST_NAME,
    )

    status = "succeeded" if metric_result.status == "succeeded" else "failed"
    return AdapterRunResult(
        status=status,
        run_id=context.run_id,
        result_manifest_path=result_manifest_path,
        metric_result_manifest_path=metric_result.path,
        issues=metric_result.issues,
    )


def _write_remote_failure(context: Any, notes: str, *, runner: Any, remote_run_dir: PurePosixPath) -> AdapterRunResult:
    """Write a failed result manifest using the shared local helper and upload it."""
    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_path = write_spectre_result_manifest(
        context,
        status="failed",
        started_at_utc=started,
        completed_at_utc=started,
        include_metric_manifest=False,
        notes=notes,
    )
    runner.upload(result_path, remote_run_dir / RESULT_MANIFEST_NAME)
    return AdapterRunResult(
        status="failed",
        run_id=context.run_id,
        result_manifest_path=result_path,
        metric_result_manifest_path=None,
        issues=[notes],
    )


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
