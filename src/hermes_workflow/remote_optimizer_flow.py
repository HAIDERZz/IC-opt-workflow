from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Callable

from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_multi_testbench_adapter,
    run_remote_spectre_ocean_adapter,
)
from hermes_workflow.native_turbo import run_batch_native_turbo_optimization
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_artifacts import (
    EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_EVALUATIONS_RELATIVE,
)
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_flow import (
    OptimizerFlowReport,
    OptimizerFlowServices,
    optimize_project,
)
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.package import build_execution_package, sha256_file
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.real_run import RUN_ID_RE
from hermes_workflow.requirement_intake import (
    RequirementIntakeReport,
    RequirementPreparationReport,
)
from hermes_workflow.remote_ssh import RemoteSshRunner, quote_remote_path
from hermes_workflow.run_retention import apply_remote_run_retention
from hermes_workflow.validate import assert_valid_project


def _wrap_with_remote_retention(
    inner_adapter: Callable[..., Any],
    *,
    local_project: Path,
    ref: RemoteProjectRef,
    runner: Any,
) -> Callable[..., Any]:
    """Wrap an inner remote adapter so retention runs once after it returns.

    Retention is applied per ``run_id`` based on the inner adapter's result
    status (or any raised exception). On exception, retention still runs and
    the original exception is re-raised. Retention failures are appended to
    the result's ``issues`` list when the inner adapter returned successfully.
    """

    def wrapped(local_project_arg: Path, *args: Any, **kwargs: Any) -> Any:
        run_id = kwargs.get("run_id")
        if run_id is None and args:
            run_id = args[0]
        adapter_exc: BaseException | None = None
        result: Any = None
        try:
            result = inner_adapter(local_project_arg, *args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — must still run retention.
            adapter_exc = exc

        run_succeeded = (
            adapter_exc is None
            and getattr(result, "status", None) == "succeeded"
        )
        candidate_id: str | None = None
        if result is not None:
            cand = getattr(result, "candidate_id", None)
            if isinstance(cand, str):
                candidate_id = cand

        try:
            decision = apply_remote_run_retention(
                local_project,
                remote_ref=ref,
                runner=runner,
                run_id=str(run_id) if run_id is not None else "",
                candidate_id=candidate_id,
                run_succeeded=run_succeeded,
            )
        except Exception as exc:  # noqa: BLE001 — surface but do not crash.
            if adapter_exc is None and result is not None:
                issues = getattr(result, "issues", None)
                if isinstance(issues, list):
                    issues.append(f"remote run retention raised: {exc}")
            decision = None

        if (
            decision is not None
            and decision.remote_action == "failed"
            and adapter_exc is None
            and result is not None
        ):
            issues = getattr(result, "issues", None)
            if isinstance(issues, list):
                issues.extend(decision.issues)

        if adapter_exc is not None:
            raise adapter_exc
        return result

    return wrapped


def _remote_product_doctor_already_passed(
    project_dir: Path,
    *,
    cadence_cshrc: Path | None = None,
) -> SimpleNamespace:
    """Remote real flow is gated by remote doctor before local optimization."""

    return SimpleNamespace(
        status="pass",
        project_dir=str(project_dir),
        checks=[],
        issues=[],
        warnings=[],
        structured_issues=[],
        cadence_cshrc=str(cadence_cshrc) if cadence_cshrc is not None else None,
    )


def optimize_remote_project(
    ref: RemoteProjectRef,
    *,
    real: bool,
    remote_cadence_cshrc: PurePosixPath,
    max_evals: int | None,
    batch_size: int | None,
    parallel_jobs: int | None,
    strategy: str | None = None,
    cache_root: Path | None = None,
    runner: Any | None = None,
    doctor_report: Any | None = None,
    attempt_started: bool = False,
) -> OptimizerFlowReport:
    if not real:
        raise ValueError("remote optimize requires --real")
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    if not attempt_started:
        _archive_remote_flow_report(ref, ssh)
    doctor = doctor_report or run_remote_doctor(
        ref,
        runner=ssh,
        cadence_cshrc=remote_cadence_cshrc,
        cache_root=cache_root,
    )
    if doctor.status != "pass":
        raise ValueError("remote doctor failed: " + "; ".join(doctor.issues))
    prepared = prepare_remote_project_cache(
        ref,
        runner=ssh,
        cache_root=cache_root,
        persist_snapshot=True,
    )
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))
    prepared_mode = getattr(
        getattr(prepared, "requirement_report", None),
        "workflow_mode",
        "optimize",
    )
    if prepared_mode != "optimize":
        raise ValueError(
            "remote workflow mode changed between doctor and prepare: "
            f"expected 'optimize', got {prepared_mode!r}"
        )

    def selected_adapter(local_project: Path, run_id: str, cadence_cshrc: Path) -> object:
        bundle = assert_valid_project(local_project)
        if (
            bundle.testbenches is not None
            or getattr(bundle, "process_corners", None) is not None
        ):
            inner = run_remote_multi_testbench_adapter
        else:
            inner = run_remote_spectre_ocean_adapter

        def call_inner(local_project_arg: Path, *args: object, **kwargs: object) -> object:
            return inner(
                local_project_arg,
                run_id=kwargs.get("run_id", run_id),
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            )

        wrapped = _wrap_with_remote_retention(
            call_inner,
            local_project=local_project,
            ref=ref,
            runner=ssh,
        )
        return wrapped(local_project, run_id=run_id, cadence_cshrc=cadence_cshrc)

    def remote_openbox(project_dir: Path, **kwargs: object):
        return run_openbox_real_optimization(
            project_dir,
            adapter=selected_adapter,
            transport_mode="remote",
            **kwargs,
        )

    def remote_native_turbo(project_dir: Path, **kwargs: object):
        return run_batch_native_turbo_optimization(
            project_dir,
            adapter=selected_adapter,
            transport_mode="remote",
            **kwargs,
        )

    def snapshot_check_requirement(_project_dir: Path) -> RequirementIntakeReport:
        return prepared.requirement_report

    def snapshot_prepare_from_requirement(
        _project_dir: Path,
    ) -> RequirementPreparationReport:
        return prepared.preparation_report

    services = OptimizerFlowServices(
        check_requirement=snapshot_check_requirement,
        prepare_from_requirement=snapshot_prepare_from_requirement,
        run_openbox_real_optimization=remote_openbox,
        run_batch_native_turbo_optimization=remote_native_turbo,
        run_product_doctor=_remote_product_doctor_already_passed,
    )
    try:
        report = optimize_project(
            prepared.cache_dir,
            real=True,
            dry_orchestration=False,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            strategy=strategy,
            cadence_cshrc=Path(remote_cadence_cshrc.as_posix()),
            services=services,
        )
    except Exception as exc:
        _publish_failure_preserving_primary(
            ref,
            prepared.cache_dir,
            ssh,
            exc,
            step_name="run-remote-optimizer",
            note_prefix="Additionally failed to sync remote failure evidence",
        )
        raise
    _publish_success_or_active_fail(ref, prepared.cache_dir, ssh)
    return report


def continue_remote_project(
    ref: RemoteProjectRef,
    *,
    additional_evals: int,
    remote_cadence_cshrc: PurePosixPath,
    batch_size: int | None,
    parallel_jobs: int | None,
    strategy: str | None = None,
    cache_root: Path | None = None,
    runner: Any | None = None,
) -> OptimizerFlowReport:
    if additional_evals < 1:
        raise ValueError("additional_evals must be >= 1")
    if strategy is not None:
        raise ValueError(
            "--continue continuation uses requirement strategy; remove --strategy"
        )
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    _archive_remote_flow_report(ref, ssh)
    prepared = prepare_remote_project_cache(
        ref,
        runner=ssh,
        cache_root=cache_root,
        frozen_snapshot=True,
    )
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))
    _sync_remote_history_to_cache(ref, prepared.cache_dir, ssh)

    project_root = prepared.cache_dir
    evaluations_path = project_root / "reports" / "optimizer_evaluations.jsonl"
    if not evaluations_path.is_file() or evaluations_path.stat().st_size == 0:
        raise ValueError(
            "cannot continue without optimizer history: "
            f"{evaluations_path} is missing or empty"
        )
    _ensure_execution_manifest(project_root)

    def remote_openbox(project_dir: Path, **kwargs: object) -> object:
        bundle = assert_valid_project(project_dir)

        def selected_adapter(local_project: Path, run_id: str, cadence_cshrc: Path) -> object:
            if (
                bundle.testbenches is not None
                or getattr(bundle, "process_corners", None) is not None
            ):
                inner = run_remote_multi_testbench_adapter
            else:
                inner = run_remote_spectre_ocean_adapter

            def call_inner(local_project_arg: Path, *args: object, **kwargs: object) -> object:
                return inner(
                    local_project_arg,
                    run_id=kwargs.get("run_id", run_id),
                    remote_ref=ref,
                    remote_cadence_cshrc=remote_cadence_cshrc,
                    runner=ssh,
                )

            wrapped = _wrap_with_remote_retention(
                call_inner,
                local_project=local_project,
                ref=ref,
                runner=ssh,
            )
            return wrapped(local_project, run_id=run_id, cadence_cshrc=cadence_cshrc)

        return run_openbox_real_optimization(
            project_dir,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            adapter=selected_adapter,
            transport_mode="remote",
            strategy=None,
            surrogate_type=None,
            acq_type=None,
            acq_optimizer_type=None,
            initial_trials=None,
        )

    try:
        report = _run_continuation_closeout(
            project_root,
            openbox_fn=remote_openbox,
            check_fn=check_optimizer_run,
            summarize_fn=summarize_optimizer_run,
            finalize_fn=finalize_optimizer_run,
            insight_fn=generate_optimizer_insight_report,
            decision_fn=generate_optimizer_decision_report,
            additional_evals=additional_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
        )
    except Exception as exc:
        _publish_failure_preserving_primary(
            ref,
            project_root,
            ssh,
            exc,
            step_name="continue-remote-optimizer",
            note_prefix=(
                "Additionally failed to sync remote continuation failure evidence"
            ),
        )
        raise
    _publish_success_or_active_fail(ref, project_root, ssh)
    return report


def _sync_remote_history_to_cache(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Download remote ledger/, state/, reports/, and execution_package/ if they exist."""
    for subdir in ("ledger", "state", "reports", "execution_package"):
        local_dir = cache_dir / subdir
        remote_dir = ref.remote_project_dir / subdir
        probe = ssh.run(f"test -d {quote_remote_path(remote_dir)}")
        if probe.return_code not in {0, 1}:
            raise RuntimeError(
                f"Failed to probe remote history subdir '{subdir}': "
                f"exit={probe.return_code}: {probe.stderr.strip()}"
            )
        if local_dir.exists():
            shutil.rmtree(local_dir)
        if probe.return_code == 0:
            local_dir.mkdir(parents=True, exist_ok=True)
            try:
                ssh.download_tree(remote_dir, local_dir)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to sync remote history subdir '{subdir}': {exc}"
                ) from exc


def _archive_remote_flow_report(ref: RemoteProjectRef, ssh: Any) -> None:
    """Remove a stale pass marker from the active path without discarding it."""
    run = getattr(ssh, "run", None)
    if not callable(run):
        # Lightweight service doubles may replace every remote operation.
        return
    current = ref.remote_project_dir / _REPORT_RELATIVE
    previous = current.with_name("optimizer_flow_run_report.previous.json")
    run(
        f"if test -f {quote_remote_path(current)}; then mv -f -- "
        f"{quote_remote_path(current)} {quote_remote_path(previous)}; fi",
        check=True,
    )


def begin_remote_optimizer_attempt(
    ref: RemoteProjectRef,
    *,
    runner: Any | None = None,
) -> None:
    """Invalidate any previous active optimizer result before real preflight."""
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    _archive_remote_flow_report(ref, ssh)


def _mark_local_flow_report_failed(
    cache_dir: Path,
    cause: Exception,
    *,
    step_name: str,
) -> None:
    """Turn a local flow report into durable fail evidence for publication."""
    report_path = cache_dir / _REPORT_RELATIVE
    payload: dict[str, Any] = {}
    if report_path.is_file():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            payload = loaded

    issue = f"{step_name} failed: {cause}"
    raw_issues = payload.get("issues")
    issues = list(raw_issues) if isinstance(raw_issues, list) else []
    if issue not in issues:
        issues.append(issue)

    failure_step = {"name": step_name, "status": "fail", "detail": str(cause)}
    raw_steps = payload.get("steps")
    steps = list(raw_steps) if isinstance(raw_steps, list) else []
    if failure_step not in steps:
        steps.append(failure_step)

    payload.update(
        {
            "schema_version": "1.0",
            "status": "fail",
            "project_dir": payload.get("project_dir", str(cache_dir)),
            "real": payload.get("real", True),
            "issues": issues,
            "steps": steps,
            "stopped_before": step_name,
            "user_decision_required": False,
            "recommended_run_id": None,
            "recommended_action": None,
            "report_path": _REPORT_RELATIVE.as_posix(),
        }
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _publish_failure_preserving_primary(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
    primary_exc: Exception,
    *,
    step_name: str,
    note_prefix: str,
) -> None:
    """Best-effort active fail publication without replacing the root error."""
    secondary_errors: list[str] = []
    try:
        _mark_local_flow_report_failed(
            cache_dir,
            primary_exc,
            step_name=step_name,
        )
    except Exception as exc:  # noqa: BLE001 - preserve the primary exception.
        secondary_errors.append(f"mark local flow report: {exc}")
    try:
        _normalize_remote_artifact_paths(ref, cache_dir)
    except Exception as exc:  # noqa: BLE001 - still attempt active fail marker.
        secondary_errors.append(f"normalize remote artifacts: {exc}")
    try:
        _sync_failure_evidence_to_remote(ref, cache_dir, ssh)
    except Exception as exc:  # noqa: BLE001 - preserve the primary exception.
        secondary_errors.append(f"publish failure evidence: {exc}")
    if secondary_errors:
        primary_exc.add_note(note_prefix + ": " + "; ".join(secondary_errors))


def _publish_success_or_active_fail(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Publish pass evidence, converting any final-sync error into active fail."""
    try:
        _normalize_remote_artifact_paths(ref, cache_dir)
        _sync_cache_reports_to_remote(ref, cache_dir, ssh)
    except Exception as exc:
        _publish_failure_preserving_primary(
            ref,
            cache_dir,
            ssh,
            exc,
            step_name="publish-remote-evidence",
            note_prefix="Additionally failed to publish active remote failure report",
        )
        raise


def _normalize_remote_artifact_paths(
    ref: RemoteProjectRef,
    cache_dir: Path,
) -> None:
    """Rewrite durable remote reports/packages so they never expose Controller paths."""
    controller_root = str(cache_dir.resolve())
    remote_root = ref.remote_project_dir.as_posix()

    def normalize_json_value(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(controller_root, remote_root)
        if isinstance(value, list):
            return [normalize_json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                key: normalize_json_value(item)
                for key, item in value.items()
            }
        return value

    artifacts: list[Path] = [cache_dir / _REPORT_RELATIVE]
    execution_dir = cache_dir / "execution_package"
    if execution_dir.is_dir():
        artifacts.extend(
            path
            for path in execution_dir.rglob("*")
            if path.is_file() and path.suffix in {".json", ".md"}
        )
    for artifact in artifacts:
        if not artifact.is_file():
            continue
        text = artifact.read_text(encoding="utf-8")
        if artifact.suffix == ".json":
            payload = json.loads(text)
            normalized_payload = normalize_json_value(payload)
            if normalized_payload != payload:
                artifact.write_text(
                    json.dumps(normalized_payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            continue
        normalized = text.replace(controller_root, remote_root)
        if normalized != text:
            artifact.write_text(normalized, encoding="utf-8")


def _sync_failure_evidence_to_remote(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Publish a fail report even when a partial run cannot pass completeness checks."""
    flow_report = cache_dir / _REPORT_RELATIVE
    if not flow_report.is_file():
        raise RuntimeError(f"remote failure report is missing: {flow_report}")
    try:
        flow_payload = json.loads(flow_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"remote failure report is invalid: {exc}") from exc
    if flow_payload.get("status") != "fail":
        raise RuntimeError("refusing to publish non-fail report as failure evidence")

    errors: list[str] = []
    for subdir in ("ledger", "state", "execution_package"):
        local_dir = cache_dir / subdir
        if not local_dir.is_dir():
            continue
        try:
            ssh.upload_tree(local_dir, ref.remote_project_dir / subdir)
        except Exception as exc:  # noqa: BLE001 - still publish the fail marker.
            errors.append(f"{subdir} upload failed: {exc}")

    reports_dir = cache_dir / "reports"
    if reports_dir.is_dir():
        try:
            ssh.upload_tree(
                reports_dir,
                ref.remote_project_dir / "reports",
                exclude=_REPORT_RELATIVE.name,
            )
        except Exception as exc:  # noqa: BLE001 - still publish the fail marker.
            errors.append(f"reports upload failed: {exc}")
    try:
        ssh.upload(flow_report, ref.remote_project_dir / _REPORT_RELATIVE)
    except Exception as exc:  # noqa: BLE001 - combine all publication failures.
        errors.append(f"flow failure report upload failed: {exc}")

    if errors:
        raise RuntimeError("remote failure evidence sync failed: " + "; ".join(errors))


def _sync_cache_reports_to_remote(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Publish Controller artifacts, with the overall flow report last."""
    _sync_parent_run_manifests_to_remote(ref, cache_dir, ssh)

    for subdir in ("ledger", "state", "execution_package"):
        local_dir = cache_dir / subdir
        if local_dir.is_dir():
            remote_dir = ref.remote_project_dir / subdir
            ssh.upload_tree(local_dir, remote_dir)

    reports_dir = cache_dir / "reports"
    if reports_dir.is_dir():
        ssh.upload_tree(
            reports_dir,
            ref.remote_project_dir / "reports",
            exclude=_REPORT_RELATIVE.name,
        )

    flow_report = cache_dir / _REPORT_RELATIVE
    if flow_report.is_file():
        ssh.upload(flow_report, ref.remote_project_dir / _REPORT_RELATIVE)


@dataclass(frozen=True)
class _ManifestPublication:
    local_path: Path
    relative_path: PurePosixPath
    payload: dict[str, Any]


@dataclass(frozen=True)
class _RemoteRunInventory:
    checksums: dict[PurePosixPath, str]
    referenced_artifacts: set[PurePosixPath]


@dataclass(frozen=True)
class _ExpectedRemoteRuns:
    history_run_ids: set[str]
    retained_run_ids: set[str]


def _artifact_run_id(relative: PurePosixPath) -> str | None:
    parts = relative.parts
    if len(parts) < 4 or parts[:2] != ("runs", "real"):
        return None
    run_id = parts[2]
    return run_id if RUN_ID_RE.fullmatch(run_id) else None


def _load_existing_remote_run_inventory(cache_dir: Path) -> _RemoteRunInventory:
    reports_dir = cache_dir / "reports"
    checksum_path = reports_dir / "remote_run_artifacts.sha256"
    paths_path = reports_dir / "remote_run_artifact_paths.txt"
    checksums: dict[PurePosixPath, str] = {}
    if checksum_path.is_file():
        for line_number, raw_line in enumerate(
            checksum_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw_line:
                continue
            digest, separator, raw_relative = raw_line.partition("  ")
            relative = PurePosixPath(raw_relative)
            if (
                separator != "  "
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                or relative.is_absolute()
                or ".." in relative.parts
                or _artifact_run_id(relative) is None
            ):
                raise RuntimeError(
                    "existing remote run checksum inventory is invalid at "
                    f"line {line_number}: {raw_line!r}"
                )
            existing = checksums.get(relative)
            if existing is not None and existing != digest:
                raise RuntimeError(
                    f"conflicting checksum inventory entry: {relative}"
                )
            checksums[relative] = digest

    referenced_artifacts: set[PurePosixPath] = set()
    if paths_path.is_file():
        for line_number, raw_line in enumerate(
            paths_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw_line:
                continue
            relative = PurePosixPath(raw_line)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or _artifact_run_id(relative) is None
            ):
                raise RuntimeError(
                    "existing remote run path inventory is invalid at "
                    f"line {line_number}: {raw_line!r}"
                )
            referenced_artifacts.add(relative)
    return _RemoteRunInventory(checksums, referenced_artifacts)


def _expected_remote_runs(cache_dir: Path) -> _ExpectedRemoteRuns | None:
    evaluations_path = next(
        (
            cache_dir / relative
            for relative in (
                EVALUATIONS_RELATIVE,
                LEGACY_NATIVE_EVALUATIONS_RELATIVE,
            )
            if (cache_dir / relative).is_file()
        ),
        None,
    )
    if evaluations_path is None:
        return None
    history_run_ids: set[str] = set()
    retained_run_ids: set[str] = set()
    rows = evaluations_path.read_text(encoding="utf-8").splitlines()
    if not any(row.strip() for row in rows):
        raise RuntimeError("optimizer evaluation history is empty")
    for line_number, raw_line in enumerate(rows, start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"optimizer evaluation history is invalid at line {line_number}: {exc}"
            ) from exc
        run_id = payload.get("run_id") if isinstance(payload, dict) else None
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise RuntimeError(
                "optimizer evaluation history has invalid run_id at "
                f"line {line_number}: {run_id!r}"
            )
        history_run_ids.add(run_id)

        decision_path = cache_dir / "state" / "run_retention" / f"{run_id}.json"
        remote_action: object = None
        if decision_path.is_file():
            try:
                decision = json.loads(decision_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"run retention decision is invalid: {decision_path}: {exc}"
                ) from exc
            if not isinstance(decision, dict) or decision.get("run_id") != run_id:
                raise RuntimeError(
                    f"run retention decision does not match {run_id}: {decision_path}"
                )
            remote_action = decision.get("remote_action")
        if remote_action not in {"deleted", "missing"}:
            retained_run_ids.add(run_id)
    return _ExpectedRemoteRuns(history_run_ids, retained_run_ids)


def _sync_parent_run_manifests_to_remote(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Publish and verify parent/child run evidence before the flow marker."""
    runs_dir = cache_dir / "runs" / "real"
    existing_inventory = _load_existing_remote_run_inventory(cache_dir)
    expected_runs = _expected_remote_runs(cache_dir)
    run_dirs = (
        sorted(path for path in runs_dir.iterdir() if path.is_dir())
        if runs_dir.is_dir()
        else []
    )
    local_run_ids = {path.name for path in run_dirs}
    invalid_local_ids = sorted(
        run_id for run_id in local_run_ids if not RUN_ID_RE.fullmatch(run_id)
    )
    if invalid_local_ids:
        raise RuntimeError(
            "local real run directories have invalid IDs: "
            + ", ".join(invalid_local_ids)
        )

    prior_parent_run_ids = {
        run_id
        for relative in existing_inventory.checksums
        if (run_id := _artifact_run_id(relative)) is not None
        and relative.parts == ("runs", "real", run_id, "result_manifest.json")
    }
    if expected_runs is not None:
        unknown_local = local_run_ids - expected_runs.history_run_ids
        if unknown_local:
            raise RuntimeError(
                "local runs are absent from optimizer evaluation history: "
                + ", ".join(sorted(unknown_local))
            )
        retained_local_ids = local_run_ids & expected_runs.retained_run_ids
        historical_run_ids = (
            expected_runs.retained_run_ids - retained_local_ids
        )
        missing_run_ids = historical_run_ids - prior_parent_run_ids
        if missing_run_ids:
            raise RuntimeError(
                "expected retained remote runs are missing from Controller evidence: "
                + ", ".join(sorted(missing_run_ids))
            )
        run_dirs = [path for path in run_dirs if path.name in retained_local_ids]
    else:
        historical_run_ids = prior_parent_run_ids - local_run_ids

    prior_inventory = _RemoteRunInventory(
        checksums={
            relative: digest
            for relative, digest in existing_inventory.checksums.items()
            if _artifact_run_id(relative) in historical_run_ids
        },
        referenced_artifacts={
            relative
            for relative in existing_inventory.referenced_artifacts
            if _artifact_run_id(relative) in historical_run_ids
        },
    )
    if expected_runs is None and not run_dirs and not prior_inventory.checksums:
        return

    parent_runs: list[tuple[Path, PurePosixPath]] = []
    parent_results: dict[str, _ManifestPublication] = {}
    child_results: dict[str, _ManifestPublication] = {}
    metric_manifests: dict[str, _ManifestPublication] = {}
    parent_metric_keys: set[str] = set()
    referenced_artifacts: set[PurePosixPath] = set()

    for run_dir in run_dirs:
        result_manifest = run_dir / "result_manifest.json"
        if not result_manifest.is_file():
            raise RuntimeError(
                "cannot publish incomplete remote parent run manifests: "
                + result_manifest.relative_to(cache_dir).as_posix()
            )
        remote_run_dir = ref.remote_project_dir / "runs" / "real" / run_dir.name
        parent_runs.append((run_dir, remote_run_dir))

        parent = _load_manifest_publication(cache_dir, result_manifest)
        parent_results[parent.relative_path.as_posix()] = parent
        referenced_artifacts.update(
            _existing_manifest_references(cache_dir, parent.payload)
        )

        metric_reference = parent.payload.get("metric_result_manifest")
        conventional_metric = run_dir / "metrics" / "metric_result_manifest.json"
        if isinstance(metric_reference, str) and metric_reference:
            metric_path = _project_artifact_path(
                cache_dir,
                metric_reference,
                label="parent metric result manifest",
            )
            if not metric_path.is_file():
                if parent.payload.get("status") == "succeeded":
                    raise RuntimeError(
                        "referenced parent metric result manifest is missing: "
                        f"{metric_reference}"
                    )
            else:
                metric = _load_manifest_publication(cache_dir, metric_path)
                metric_manifests[metric.relative_path.as_posix()] = metric
                parent_metric_keys.add(metric.relative_path.as_posix())
                referenced_artifacts.update(
                    _existing_manifest_references(cache_dir, metric.payload)
                )
        elif conventional_metric.is_file():
            metric = _load_manifest_publication(cache_dir, conventional_metric)
            metric_manifests[metric.relative_path.as_posix()] = metric
            parent_metric_keys.add(metric.relative_path.as_posix())
            referenced_artifacts.update(
                _existing_manifest_references(cache_dir, metric.payload)
            )

        raw_children = parent.payload.get("child_results", [])
        if not isinstance(raw_children, list):
            raise RuntimeError(
                f"parent child_results must be a list: {parent.relative_path}"
            )
        for raw_child in raw_children:
            if not isinstance(raw_child, dict):
                raise RuntimeError(
                    f"parent child_results entry must be an object: "
                    f"{parent.relative_path}"
                )
            child_result_reference = raw_child.get("result_manifest")
            if not isinstance(child_result_reference, str) or not child_result_reference:
                raise RuntimeError(
                    f"parent child result reference is invalid: {parent.relative_path}"
                )
            child_result_path = _project_artifact_path(
                cache_dir,
                child_result_reference,
                label="child result manifest",
            )
            if not child_result_path.is_file():
                raise RuntimeError(
                    "referenced child result manifest is missing: "
                    f"{child_result_reference}"
                )
            if not child_result_path.is_relative_to(run_dir):
                raise RuntimeError(
                    "referenced child result manifest escapes its parent run: "
                    f"{child_result_reference}"
                )
            child = _load_manifest_publication(cache_dir, child_result_path)
            child_results[child.relative_path.as_posix()] = child
            referenced_artifacts.update(
                _existing_manifest_references(cache_dir, child.payload)
            )

            child_metric_reference = raw_child.get("metric_result_manifest")
            if not isinstance(child_metric_reference, str) or not child_metric_reference:
                continue
            child_metric_path = _project_artifact_path(
                cache_dir,
                child_metric_reference,
                label="child metric result manifest",
            )
            if not child_metric_path.is_file():
                if raw_child.get("status") == "succeeded":
                    raise RuntimeError(
                        "referenced child metric result manifest is missing: "
                        f"{child_metric_reference}"
                    )
                # Aggregation records the conventional metric path even for a
                # result-only failed child.  It is explicitly optional in that
                # state, so remove every repeated occurrence collected from
                # parent/aggregate traces instead of demanding a phantom file.
                referenced_artifacts.discard(
                    PurePosixPath(child_metric_reference)
                )
                continue
            child_metric = _load_manifest_publication(cache_dir, child_metric_path)
            metric_manifests[child_metric.relative_path.as_posix()] = child_metric
            referenced_artifacts.update(
                _existing_manifest_references(cache_dir, child_metric.payload)
            )

    # Parent aggregate artifacts do not exist remotely until Controller-side
    # aggregation completes.  Publish their dependencies but leave every
    # result_manifest.json completion marker for the ordered phases below.
    for run_dir, remote_run_dir in parent_runs:
        active_result = remote_run_dir / "result_manifest.json"
        previous_result = remote_run_dir / "result_manifest.previous.json"
        ssh.run(
            f"mkdir -p {quote_remote_path(remote_run_dir)} && "
            f"if test -f {quote_remote_path(active_result)}; then mv -f -- "
            f"{quote_remote_path(active_result)} "
            f"{quote_remote_path(previous_result)}; fi",
            check=True,
        )
        for entry in sorted(run_dir.iterdir()):
            if entry.name in {"result_manifest.json", "testbenches", "corners"}:
                continue
            remote_entry = remote_run_dir / entry.name
            if entry.is_dir():
                exclude = (
                    "metric_result_manifest.json"
                    if entry.name == "metrics"
                    else None
                )
                ssh.upload_tree(entry, remote_entry, exclude=exclude)
            elif entry.is_file():
                ssh.upload(entry, remote_entry)

    # Child manifests are published atomically by each remote adapter invocation.
    # Re-upload only Controller-generated parent manifests here; the complete
    # parent/child inventory below verifies every child manifest in place and
    # fails closed if an earlier transport operation was lost or corrupted.
    # Publish every parent metric before any parent result completion marker.
    for publication in sorted(
        (
            publication
            for key, publication in metric_manifests.items()
            if key in parent_metric_keys
        ),
        key=lambda item: item.relative_path.as_posix(),
    ):
        remote_path = ref.remote_project_dir / publication.relative_path
        remote_metrics_dir = remote_path.parent
        ssh.run(
            f"mkdir -p {quote_remote_path(remote_metrics_dir)}",
            check=True,
        )
        ssh.upload(publication.local_path, remote_path)

    staged_parent_results: dict[PurePosixPath, PurePosixPath] = {}
    for publication in sorted(
        parent_results.values(),
        key=lambda item: item.relative_path.as_posix(),
    ):
        active_relative = publication.relative_path
        pending_relative = active_relative.with_name(
            "result_manifest.pending.json"
        )
        ssh.upload(
            publication.local_path,
            ref.remote_project_dir / pending_relative,
        )
        staged_parent_results[active_relative] = pending_relative

    all_manifests = {
        **metric_manifests,
        **child_results,
        **parent_results,
    }
    referenced_artifacts.update(
        publication.relative_path for publication in all_manifests.values()
    )
    _write_and_verify_remote_run_inventory(
        ref,
        cache_dir,
        ssh,
        manifests=all_manifests,
        referenced_artifacts=referenced_artifacts,
        prior_inventory=prior_inventory,
        staged_parent_results=staged_parent_results,
    )


def _load_manifest_publication(
    cache_dir: Path,
    local_path: Path,
) -> _ManifestPublication:
    try:
        payload = json.loads(local_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"run manifest is invalid: {local_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"run manifest must contain an object: {local_path}")
    relative = PurePosixPath(local_path.relative_to(cache_dir).as_posix())
    return _ManifestPublication(local_path, relative, payload)


def _project_artifact_path(
    cache_dir: Path,
    relative_path: str,
    *,
    label: str,
) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise RuntimeError(f"{label} must stay within the project: {relative_path}")
    return cache_dir.joinpath(*relative.parts)


def _existing_manifest_references(
    _cache_dir: Path,
    payload: object,
) -> set[PurePosixPath]:
    references: set[PurePosixPath] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, str) or not value.startswith("runs/"):
            return
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"run artifact reference escapes project: {value}")
        # The remote project, not the Controller cache, is the publication
        # authority.  Keep references that are absent locally so the checked
        # remote existence pass can fail closed instead of silently omitting
        # them from the inventory.
        references.add(relative)

    visit(payload)
    return references


def _write_and_verify_remote_run_inventory(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
    *,
    manifests: dict[str, _ManifestPublication],
    referenced_artifacts: set[PurePosixPath],
    prior_inventory: _RemoteRunInventory,
    staged_parent_results: dict[PurePosixPath, PurePosixPath],
) -> None:
    reports_dir = cache_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    checksum_path = reports_dir / "remote_run_artifacts.sha256"
    paths_path = reports_dir / "remote_run_artifact_paths.txt"
    checksums = dict(prior_inventory.checksums)
    checksums.update(
        {
            publication.relative_path: sha256_file(publication.local_path)
            for publication in manifests.values()
        }
    )
    final_references = set(prior_inventory.referenced_artifacts)
    final_references.update(referenced_artifacts)
    final_references.update(checksums)

    def write_checksum_file(
        path: Path,
        entries: dict[PurePosixPath, str],
    ) -> None:
        path.write_text(
            "".join(
                f"{digest}  {relative.as_posix()}\n"
                for relative, digest in sorted(
                    entries.items(),
                    key=lambda item: item[0].as_posix(),
                )
            ),
            encoding="utf-8",
        )

    def write_paths_file(path: Path, entries: set[PurePosixPath]) -> None:
        path.write_text(
            "".join(
                f"{relative.as_posix()}\n"
                for relative in sorted(entries, key=PurePosixPath.as_posix)
            ),
            encoding="utf-8",
        )

    write_checksum_file(checksum_path, checksums)
    write_paths_file(paths_path, final_references)

    verification_checksum_path = checksum_path
    verification_paths_path = paths_path
    verification_checksums = checksums
    if staged_parent_results:
        precommit_dir = cache_dir / ".remote_sync"
        precommit_dir.mkdir(parents=True, exist_ok=True)
        verification_checksum_path = precommit_dir / (
            "remote_run_artifacts.precommit.sha256"
        )
        verification_paths_path = precommit_dir / (
            "remote_run_artifact_paths.precommit.txt"
        )
        verification_checksums = {
            staged_parent_results.get(relative, relative): digest
            for relative, digest in checksums.items()
        }
        verification_references = {
            staged_parent_results.get(relative, relative)
            for relative in final_references
        }
        write_checksum_file(verification_checksum_path, verification_checksums)
        write_paths_file(verification_paths_path, verification_references)

    remote_reports_dir = ref.remote_project_dir / "reports"
    ssh.run(f"mkdir -p {quote_remote_path(remote_reports_dir)}", check=True)
    inventory_files = dict.fromkeys(
        (
            checksum_path,
            paths_path,
            verification_checksum_path,
            verification_paths_path,
        )
    )
    for local_path in inventory_files:
        remote_path = remote_reports_dir / local_path.name
        ssh.upload(local_path, remote_path)

    def verify_remote_inventory(
        remote_checksum_name: str,
        remote_paths_name: str,
        *,
        has_checksums: bool,
    ) -> None:
        if has_checksums:
            ssh.run(
                f"cd {quote_remote_path(ref.remote_project_dir)} && "
                "sha256sum -c -- "
                f"{quote_remote_path(PurePosixPath('reports') / remote_checksum_name)}",
                check=True,
            )
        ssh.run(
            f"cd {quote_remote_path(ref.remote_project_dir)} && "
            "missing=0; while IFS= read -r artifact; do "
            "if ! test -e \"$artifact\"; then "
            "echo \"missing remote artifact: $artifact\" >&2; missing=1; fi; "
            f"done < {quote_remote_path(PurePosixPath('reports') / remote_paths_name)}; "
            "test \"$missing\" -eq 0",
            check=True,
        )

    verify_remote_inventory(
        verification_checksum_path.name,
        verification_paths_path.name,
        has_checksums=bool(verification_checksums),
    )
    for active_relative, pending_relative in sorted(
        staged_parent_results.items(),
        key=lambda item: item[0].as_posix(),
    ):
        ssh.run(
            f"mv -f -- "
            f"{quote_remote_path(ref.remote_project_dir / pending_relative)} "
            f"{quote_remote_path(ref.remote_project_dir / active_relative)}",
            check=True,
        )
    if staged_parent_results:
        verify_remote_inventory(
            checksum_path.name,
            paths_path.name,
            has_checksums=bool(checksums),
        )
        ssh.run(
            f"rm -f -- "
            f"{quote_remote_path(remote_reports_dir / verification_checksum_path.name)} "
            f"{quote_remote_path(remote_reports_dir / verification_paths_path.name)}",
            check=True,
        )


def _ensure_execution_manifest(project_dir: Path) -> None:
    """Build execution package only if the manifest is missing."""
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    if not manifest_path.exists():
        build_execution_package(project_dir)


_REPORT_RELATIVE = Path("reports/optimizer_flow_run_report.json")


def run_continuation_closeout(
    project_root: Path,
    *,
    openbox_fn: Callable[..., Any],
    check_fn: Callable[[Path], Any],
    summarize_fn: Callable[[Path], Any],
    finalize_fn: Callable[[Path], Any],
    insight_fn: Callable[[Path], Any],
    decision_fn: Callable[[Path], Any],
    additional_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
) -> OptimizerFlowReport:
    """Public alias for the continuation closeout helper.

    Exposed so non-remote entrypoints (e.g. local continuation) can reuse the
    exact closeout sequence without depending on the leading underscore symbol.
    """
    return _run_continuation_closeout(
        project_root,
        openbox_fn=openbox_fn,
        check_fn=check_fn,
        summarize_fn=summarize_fn,
        finalize_fn=finalize_fn,
        insight_fn=insight_fn,
        decision_fn=decision_fn,
        additional_evals=additional_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
    )


def _run_continuation_closeout(
    project_root: Path,
    *,
    openbox_fn: Callable[..., Any],
    check_fn: Callable[[Path], Any],
    summarize_fn: Callable[[Path], Any],
    finalize_fn: Callable[[Path], Any],
    insight_fn: Callable[[Path], Any],
    decision_fn: Callable[[Path], Any],
    additional_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
) -> OptimizerFlowReport:
    """Run openbox continuation + closeout services, mirroring optimize_project structure."""
    steps: list[_FlowStep] = []
    issues: list[str] = []
    warnings: list[str] = []
    recommended_run_id: str | None = None
    recommended_action: str | None = None

    try:
        _run_step(
            steps,
            "run-openbox-real",
            lambda: openbox_fn(project_root),
            _expect_success,
        )
        _run_step(
            steps,
            "check-optimizer-run",
            lambda: check_fn(project_root),
            lambda result: _expect_status(result, "accepted"),
        )
        _run_step(
            steps,
            "summarize-optimizer-run",
            lambda: summarize_fn(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "finalize-optimizer-run",
            lambda: finalize_fn(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "visualize-optimizer-run",
            lambda: insight_fn(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        decision = _run_step(
            steps,
            "decide-optimizer-run",
            lambda: decision_fn(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        recommended_run_id = _string_attr(decision, "recommended_run_id")
        recommended_action = _string_attr(decision, "recommended_action")
    except Exception as exc:
        issues.append(str(exc))
        report = _flow_report(
            project_root,
            status="fail",
            max_evals=additional_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            steps=steps,
            user_decision_required=False,
            issues=issues,
            warnings=warnings,
        )
        _write_flow_report(project_root, report)
        raise

    report = _flow_report(
        project_root,
        status="pass",
        max_evals=additional_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        steps=steps,
        user_decision_required=True,
        recommended_run_id=recommended_run_id,
        recommended_action=recommended_action,
        issues=issues,
        warnings=warnings,
    )
    return _write_flow_report(project_root, report)


@dataclass(frozen=True)
class _FlowStep:
    name: str
    status: str
    detail: str = ""


def _run_step(
    steps: list[_FlowStep],
    name: str,
    action: Callable[[], Any],
    validate: Callable[[Any], str | None],
) -> Any:
    try:
        result = action()
        issue = validate(result)
    except Exception as exc:
        steps.append(_FlowStep(name=name, status="fail", detail=str(exc)))
        raise ValueError(f"{name} failed: {exc}") from exc
    if issue is not None:
        steps.append(_FlowStep(name=name, status="fail", detail=issue))
        raise ValueError(f"{name} failed: {issue}")
    steps.append(_FlowStep(name=name, status="pass", detail=_detail(result)))
    return result


def _expect_success(_result: Any) -> str | None:
    return None


def _expect_status(result: Any, expected: str) -> str | None:
    status = getattr(result, "status", None)
    if isinstance(status, str) and status == expected:
        return None
    issues = getattr(result, "issues", None)
    if isinstance(issues, list) and issues:
        return "; ".join(str(i) for i in issues)
    return f"status is {status or 'unknown'}, expected {expected}"


def _string_attr(result: Any, attr: str) -> str | None:
    value = getattr(result, attr, None)
    return value if isinstance(value, str) and value else None


def _detail(result: Any) -> str:
    for attr in (
        "report_path",
        "markdown_path",
        "manifest_path",
        "evaluation_count",
        "recommended_run_id",
    ):
        value = getattr(result, attr, None)
        if value is not None:
            return f"{attr}={value}"
    return ""


def _flow_report(
    project_root: Path,
    *,
    status: str,
    max_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
    steps: list[_FlowStep],
    user_decision_required: bool,
    recommended_run_id: str | None = None,
    recommended_action: str | None = None,
    issues: list[str],
    warnings: list[str],
) -> OptimizerFlowReport:
    return OptimizerFlowReport(
        status=status,
        project_dir=str(project_root),
        backend="openbox",
        real=True,
        dry_orchestration=False,
        max_evals=max_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        steps=list(steps),
        user_decision_required=user_decision_required,
        recommended_run_id=recommended_run_id,
        recommended_action=recommended_action,
        issues=list(issues),
        warnings=list(warnings),
        report_path=project_root / _REPORT_RELATIVE,
    )


def _write_flow_report(project_root: Path, report: OptimizerFlowReport) -> OptimizerFlowReport:
    report_path = project_root / _REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = _REPORT_RELATIVE.as_posix()
    payload["steps"] = [asdict(step) for step in report.steps]
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return report
