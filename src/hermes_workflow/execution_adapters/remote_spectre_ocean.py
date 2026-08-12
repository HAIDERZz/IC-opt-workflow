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
    WAVEFORM_EXPORT_MANIFEST_NAME,
    AdapterRunResult,
    _build_command_trace,
    _build_waveform_export_results,
    _project_relative_path,
    _write_waveform_export_manifest,
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
    return [corner.id for corner in process_corners.corners]


def _build_remote_command_trace(
    context: Any,
    *,
    remote_project_dir: PurePosixPath,
    remote_run_dir: PurePosixPath,
    ocean_return_code: int = 0,
    ocean_return_codes: list[int] | None = None,
    include_ocean: bool = True,
) -> dict:
    trace = _build_command_trace(
        context,
        execution_mode="remote",
        ocean_return_code=ocean_return_code,
        ocean_return_codes=ocean_return_codes,
        include_ocean=include_ocean,
    )
    trace["spectre"]["cwd"] = str(remote_run_dir / "netlist")
    if include_ocean:
        trace["ocean"]["cwd"] = str(remote_project_dir)
    return trace


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
    transfer_issues: list[str] = []
    script_path = _project_relative_path(context.project_dir, context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_base = remote_ref.remote_project_dir / "runs" / "real" / run_id
    if testbench_id is not None:
        remote_run_dir = remote_run_base / "testbenches" / testbench_id
    else:
        remote_run_dir = remote_run_base
    if corner_id is not None:
        remote_run_dir = remote_run_dir / "corners" / corner_id
    try:
        runner.upload_tree(context.run_dir, remote_run_dir, replace=True)
    except Exception as exc:
        upload_trace = _build_remote_command_trace(
            context,
            remote_project_dir=remote_ref.remote_project_dir,
            remote_run_dir=remote_run_dir,
            include_ocean=False,
        )
        return _write_remote_failure(
            context,
            f"upload run directory failed: {exc}",
            runner=runner,
            remote_run_dir=remote_run_dir,
            command_trace=upload_trace,
        )

    remote_input_dir = remote_run_dir / "netlist"
    timeout_s = int(context.request.spectre.get("timeout_s", 3600))
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
    spectre_trace = _build_remote_command_trace(
        context,
        remote_project_dir=remote_ref.remote_project_dir,
        remote_run_dir=remote_run_dir,
        include_ocean=False,
    )
    try:
        spectre_result = runner.run(spectre_command, timeout_s=timeout_s)
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
            command_trace=spectre_trace,
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
        issues=transfer_issues,
    )
    _safe_upload(
        runner,
        context.run_dir / SPECTRE_STDERR_NAME,
        remote_run_dir / SPECTRE_STDERR_NAME,
        prefix="spectre stderr",
        issues=transfer_issues,
    )

    if spectre_result.return_code != 0:
        return _write_remote_failure(
            context,
            "spectre command failed",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=transfer_issues,
            command_trace=spectre_trace,
        )

    # Download Spectre artifacts: psf/
    try:
        runner.download_tree(remote_run_dir / "psf", context.psf_dir)
    except Exception as exc:
        return _write_remote_failure(
            context,
            "psf directory download failed",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=transfer_issues + [f"psf download exception: {exc}"],
            command_trace=spectre_trace,
        )

    # Validate required Spectre artifacts exist locally
    if not context.psf_dir.is_dir():
        return _write_remote_failure(
            context,
            "psf directory missing after download",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=transfer_issues,
            command_trace=spectre_trace,
        )
    if not (context.psf_dir / "spectre.out").is_file():
        return _write_remote_failure(
            context,
            "psf/spectre.out missing after download",
            runner=runner,
            remote_run_dir=remote_run_dir,
            extra_issues=transfer_issues,
            command_trace=spectre_trace,
        )

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
            ocean_result = runner.run(ocean_command, timeout_s=timeout_s)
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
            command_trace=spectre_trace,
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
            command_trace=spectre_trace,
        )

    # Download waveform CSV files from metrics/waveforms/ if they exist.
    # Missing waveform artifacts are not an error -- they may not be
    # configured for this run.
    try:
        runner.download_tree(
            remote_run_dir / "metrics" / "waveforms",
            context.metrics_dir / "waveforms",
        )
    except Exception:
        pass  # graceful: waveform directory may not exist

    # Download waveform export manifest if it exists.
    try:
        runner.download(
            remote_run_dir / "metrics" / WAVEFORM_EXPORT_MANIFEST_NAME,
            context.metrics_dir / WAVEFORM_EXPORT_MANIFEST_NAME,
        )
    except Exception:
        pass  # graceful: waveform manifest may not exist

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
        issues=transfer_issues,
    )
    _safe_upload(
        runner,
        context.metrics_dir / OCEAN_STDERR_NAME,
        remote_run_dir / "metrics" / OCEAN_STDERR_NAME,
        prefix="ocean stderr",
        issues=transfer_issues,
    )

    started = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed = started

    # Build full command_trace with both spectre and ocean for the
    # success/OCEAN-failure manifest paths.
    full_trace = _build_remote_command_trace(
        context,
        remote_project_dir=remote_ref.remote_project_dir,
        remote_run_dir=remote_run_dir,
        ocean_return_code=ocean_result.return_code,
        ocean_return_codes=ocean_return_codes,
    )

    # Write metric result manifest first (records ocean failure if rc != 0).
    # write_metric_result_manifest handles missing ocean_scalars.tsv gracefully
    # by recording AdapterPreconditionError in the manifest issues, matching
    # local adapter semantics.
    metric_result = write_metric_result_manifest(
        context,
        ocean_return_code=ocean_result.return_code,
        ocean_return_codes=ocean_return_codes,
        command_trace=full_trace,
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
        command_trace=full_trace,
    )

    # Upload dependency manifests before publishing result_manifest.json,
    # which is the remote completion marker for this child run.
    _safe_upload(
        runner,
        metric_result.path,
        remote_run_dir / "metrics" / METRIC_RESULT_MANIFEST_NAME,
        prefix="metric result manifest",
        issues=transfer_issues,
    )

    # Waveform export manifest: the remote OCEAN replay never writes this
    # Python-side artifact. If waveform exports are configured and the
    # manifest was not produced on (or downloaded from) the remote, generate
    # it locally by reusing the same helper the local adapter uses, so the
    # manifest schema cannot drift between local and remote. The CSV files
    # were already downloaded into metrics/waveforms/.
    local_waveform_manifest = context.metrics_dir / WAVEFORM_EXPORT_MANIFEST_NAME
    if (
        context.request.waveform_exports
        and not local_waveform_manifest.is_file()
    ):
        ocean_failed = ocean_result.return_code != 0
        waveform_results = _build_waveform_export_results(
            context, ocean_failed=ocean_failed,
        )
        _write_waveform_export_manifest(
            context, waveform_results, command_trace=full_trace,
        )

    # Upload the waveform export manifest (downloaded or locally generated)
    # back to the remote so the remote project tree is self-consistent.
    if local_waveform_manifest.is_file():
        _safe_upload(
            runner,
            local_waveform_manifest,
            remote_run_dir / "metrics" / WAVEFORM_EXPORT_MANIFEST_NAME,
            prefix="waveform export manifest",
            issues=transfer_issues,
        )

    if not transfer_issues:
        _safe_upload(
            runner,
            result_manifest_path,
            remote_run_dir / RESULT_MANIFEST_NAME,
            prefix="result manifest",
            issues=transfer_issues,
        )
    if transfer_issues:
        result_manifest_path = write_spectre_result_manifest(
            context,
            status="failed",
            started_at_utc=started,
            completed_at_utc=completed,
            include_metric_manifest=True,
            notes="remote artifact upload failed: " + "; ".join(transfer_issues),
            command_trace=full_trace,
        )
        _safe_upload(
            runner,
            result_manifest_path,
            remote_run_dir / RESULT_MANIFEST_NAME,
            prefix="failed result manifest",
            issues=transfer_issues,
        )

    issues = list(metric_result.issues)
    issues.extend(transfer_issues)
    status = (
        "succeeded"
        if metric_result.status == "succeeded" and not transfer_issues
        else "failed"
    )
    return AdapterRunResult(
        status=status,
        run_id=context.run_id,
        result_manifest_path=result_manifest_path,
        metric_result_manifest_path=metric_result.path,
        issues=issues,
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
        message = f"failed to upload {prefix}: {exc}"
        if issues is None:
            raise RuntimeError(message) from exc
        issues.append(message)


def _write_remote_failure(
    context: Any,
    notes: str,
    *,
    runner: Any,
    remote_run_dir: PurePosixPath,
    extra_issues: list[str] | None = None,
    command_trace: dict | None = None,
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
        command_trace=command_trace,
    )
    publication_issues: list[str] = []
    for local_path, remote_path, prefix in (
        (
            context.run_dir / SPECTRE_STDOUT_NAME,
            remote_run_dir / SPECTRE_STDOUT_NAME,
            "spectre stdout",
        ),
        (
            context.run_dir / SPECTRE_STDERR_NAME,
            remote_run_dir / SPECTRE_STDERR_NAME,
            "spectre stderr",
        ),
    ):
        if local_path.is_file():
            _safe_upload(
                runner,
                local_path,
                remote_path,
                prefix=prefix,
                issues=publication_issues,
            )
    issues.extend(publication_issues)
    if not publication_issues:
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
    issues: list[str] = []
    corner_ids = _configured_corner_ids(bundle)
    testbench_ids = (
        [testbench.id for testbench in bundle.testbenches.testbenches]
        if bundle.testbenches is not None
        else [None]
    )
    for testbench_id in testbench_ids:
        for corner_id in corner_ids:
            result = run_remote_spectre_ocean_adapter(
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=runner,
                testbench_id=testbench_id,
                corner_id=corner_id,
            )
            if result.status != "succeeded":
                message = "; ".join(result.issues) or result.status
                label = (
                    (testbench_id or "default_testbench")
                    if corner_id is None
                    else (
                        f"{testbench_id}/{corner_id}"
                        if testbench_id is not None
                        else corner_id
                    )
                )
                issues.append(f"{label}: {message}")

    aggregate_report = aggregate_multi_testbench_run(project_dir, run_id=run_id)

    run_dir = project_dir / "runs" / "real" / run_id

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
