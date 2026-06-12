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
from hermes_workflow.remote_ssh import RemoteCommandResult, quote_remote_path


def _configured_corner_ids(bundle: Any) -> list[str | None]:
    process_corners = getattr(bundle, "process_corners", None)
    if process_corners is None:
        return [None]
    corners = process_corners.corners
    if len(corners) == 1:
        return [None]
    return [corner.id for corner in corners]


def run_remote_spectre_ocean_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    testbench_id: str | None = None,
    corner_id: str | None = None,
) -> AdapterRunResult:
    context = load_adapter_context(
        project_dir, run_id=run_id, testbench_id=testbench_id, corner_id=corner_id
    )
    script_path = _project_relative_path(context.project_dir, context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_base = remote_ref.remote_project_dir / "runs" / "real" / run_id
    if testbench_id is not None:
        remote_run_dir = remote_run_base / "testbenches" / testbench_id
        if corner_id is not None:
            remote_run_dir = remote_run_dir / "corners" / corner_id
    else:
        remote_run_dir = remote_run_base
    try:
        runner.upload_tree(context.run_dir, remote_run_dir)
    except Exception as exc:
        return _write_remote_failure(
            context,
            f"upload run directory failed: {exc}",
            runner=runner,
            remote_run_dir=remote_run_dir,
        )

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
    try:
        spectre_result = runner.run(spectre_command)
    except Exception as exc:
        (context.run_dir / SPECTRE_STDOUT_NAME).write_text(
            f"spectre command failed with exception: {exc}\n",
            encoding="utf-8",
        )
        (context.run_dir / SPECTRE_STDERR_NAME).write_text(
            f"spectre command failed with exception: {exc}\n",
            encoding="utf-8",
        )
        return _write_remote_failure(
            context,
            "spectre command failed",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=[f"spectre command exception: {exc}"],
        )

    # Write spectre diagnostics locally from captured output and upload to
    # remote so that failure paths always have diagnostic artifacts available.
    (context.run_dir / SPECTRE_STDOUT_NAME).write_text(
        spectre_result.stdout, encoding="utf-8",
    )
    (context.run_dir / SPECTRE_STDERR_NAME).write_text(
        spectre_result.stderr, encoding="utf-8",
    )
    _safe_upload(
        runner,
        context.run_dir / SPECTRE_STDOUT_NAME,
        remote_run_dir / SPECTRE_STDOUT_NAME,
        prefix="spectre stdout",
    )
    _safe_upload(
        runner,
        context.run_dir / SPECTRE_STDERR_NAME,
        remote_run_dir / SPECTRE_STDERR_NAME,
        prefix="spectre stderr",
    )

    if spectre_result.return_code != 0:
        return _write_remote_failure(context, "spectre command failed", runner=runner, remote_run_dir=remote_run_dir)

    # Download Spectre artifacts: psf/
    try:
        runner.download_tree(remote_run_dir / "psf", context.psf_dir)
    except Exception as exc:
        return _write_remote_failure(
            context,
            "psf directory download failed",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=[f"psf download exception: {exc}"],
        )

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
    ocean_result: RemoteCommandResult | None = None
    for _attempt in range(OCEAN_MAX_ATTEMPTS):
        try:
            ocean_result = runner.run(ocean_command)
            ocean_return_codes.append(ocean_result.return_code)
            if ocean_result.return_code == 0:
                break
        except Exception as exc:
            ocean_return_codes.append(1)
            ocean_result = RemoteCommandResult(
                1,
                "",
                f"ocean command failed with exception: {exc}",
                ["ssh", remote_ref.ssh_profile, ocean_command],
            )
            break

    # Download OCEAN artifacts regardless of return code, matching local
    # adapter behaviour where the metric manifest records the failure.
    if ocean_result is None:
        return _write_remote_failure(
            context,
            "ocean command produced no result",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=["ocean command produced no result"],
        )
    try:
        runner.download_tree(remote_run_dir / "metrics", context.metrics_dir)
    except Exception as exc:
        return _write_remote_failure(
            context,
            "ocean metric download failed",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=[f"ocean metric download exception: {exc}"],
        )

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
    _safe_upload(
        runner,
        context.metrics_dir / OCEAN_STDOUT_NAME,
        remote_run_dir / "metrics" / OCEAN_STDOUT_NAME,
        prefix="ocean stdout",
    )
    _safe_upload(
        runner,
        context.metrics_dir / OCEAN_STDERR_NAME,
        remote_run_dir / "metrics" / OCEAN_STDERR_NAME,
        prefix="ocean stderr",
    )

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
    _safe_upload(
        runner,
        result_manifest_path,
        remote_run_dir / RESULT_MANIFEST_NAME,
        prefix="result manifest",
    )
    _safe_upload(
        runner,
        metric_result.path,
        remote_run_dir / "metrics" / METRIC_RESULT_MANIFEST_NAME,
        prefix="metric result manifest",
    )

    status = "succeeded" if metric_result.status == "succeeded" else "failed"
    return AdapterRunResult(
        status=status,
        run_id=context.run_id,
        result_manifest_path=result_manifest_path,
        metric_result_manifest_path=metric_result.path,
        issues=metric_result.issues,
    )


def _safe_upload(
    runner: Any,
    local_path: Path,
    remote_path: PurePosixPath | str,
    *,
    prefix: str,
    issues: list[str] | None = None,
) -> None:
    try:
        runner.upload(local_path, remote_path)
    except Exception as exc:
        if issues is not None:
            issues.append(f"failed to upload {prefix}: {exc}")


def _write_remote_failure(
    context: Any,
    notes: str,
    *,
    runner: Any,
    remote_run_dir: PurePosixPath,
    extra_issues: list[str] | None = None,
) -> AdapterRunResult:
    """Write a failed result manifest using the shared local helper and upload it."""
    issues = [notes]
    if extra_issues:
        issues.extend(extra_issues)
    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_path = write_spectre_result_manifest(
        context,
        status="failed",
        started_at_utc=started,
        completed_at_utc=started,
        include_metric_manifest=False,
        notes=notes,
    )
    _safe_upload(
        runner,
        result_path,
        remote_run_dir / RESULT_MANIFEST_NAME,
        prefix="result manifest",
        issues=issues,
    )
    return AdapterRunResult(
        status="failed",
        run_id=context.run_id,
        result_manifest_path=result_path,
        metric_result_manifest_path=None,
        issues=issues,
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
    corner_ids = _configured_corner_ids(bundle)
    for testbench in bundle.testbenches.testbenches:
        for corner_id in corner_ids:
            result = run_remote_spectre_ocean_adapter(
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=runner,
                testbench_id=testbench.id,
                corner_id=corner_id,
            )
            if result.status != "succeeded":
                message = "; ".join(result.issues) or result.status
                label = testbench.id if corner_id is None else f"{testbench.id}/{corner_id}"
                issues.append(f"{label}: {message}")

    aggregate_report = aggregate_multi_testbench_run(project_dir, run_id=run_id)

    remote_run_dir = remote_ref.remote_project_dir / "runs" / "real" / run_id
    run_dir = project_dir / "runs" / "real" / run_id
    _safe_upload(
        runner,
        run_dir / "result_manifest.json",
        remote_run_dir / "result_manifest.json",
        prefix="parent result manifest",
    )
    _safe_upload(
        runner,
        run_dir / "metrics" / "metric_result_manifest.json",
        remote_run_dir / "metrics" / "metric_result_manifest.json",
        prefix="parent metric result manifest",
    )

    if issues:
        return AdapterRunResult(
            status="failed",
            run_id=run_id,
            result_manifest_path=run_dir / "result_manifest.json",
            metric_result_manifest_path=run_dir / "metrics" / "metric_result_manifest.json",
            issues=issues,
        )
    aggregate_failed = aggregate_report.status in {
        "real_check_failed",
        "metric_check_failed",
    }
    return AdapterRunResult(
        status="failed" if aggregate_failed else "succeeded",
        run_id=run_id,
        result_manifest_path=run_dir / "result_manifest.json",
        metric_result_manifest_path=run_dir / "metrics" / "metric_result_manifest.json",
        issues=list(aggregate_report.issues) if aggregate_failed else [],
    )
