from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from hermes_workflow.cli import (
    CONTINUATION_ACQ_OPTIMIZER_TYPE,
    CONTINUATION_ACQ_TYPE,
    CONTINUATION_SURROGATE_TYPE,
)
from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_multi_testbench_adapter,
    run_remote_spectre_ocean_adapter,
)
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_flow import (
    OptimizerFlowReport,
    OptimizerFlowServices,
    optimize_project,
)
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.package import build_execution_package
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.validate import assert_valid_project
from hermes_workflow.remote_ssh import RemoteSshRunner


def optimize_remote_project(
    ref: RemoteProjectRef,
    *,
    real: bool,
    remote_cadence_cshrc: PurePosixPath,
    max_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
    cache_root: Path | None = None,
    runner: Any | None = None,
) -> OptimizerFlowReport:
    if not real:
        raise ValueError("remote optimize requires --real")
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    doctor = run_remote_doctor(
        ref,
        runner=ssh,
        cadence_cshrc=remote_cadence_cshrc,
        cache_root=cache_root,
    )
    if doctor.status != "pass":
        raise ValueError("remote doctor failed: " + "; ".join(doctor.issues))
    prepared = prepare_remote_project_cache(ref, runner=ssh, cache_root=cache_root)
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))

    def remote_openbox(project_dir: Path, **kwargs: object):
        bundle = assert_valid_project(project_dir)

        def selected_adapter(local_project: Path, run_id: str, cadence_cshrc: Path) -> object:
            if bundle.testbenches is not None or getattr(bundle, "process_corners", None) is not None:
                return run_remote_multi_testbench_adapter(
                    local_project,
                    run_id=run_id,
                    remote_ref=ref,
                    remote_cadence_cshrc=remote_cadence_cshrc,
                    runner=ssh,
                )
            return run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            )

        return run_openbox_real_optimization(
            project_dir,
            adapter=selected_adapter,
            **kwargs,
        )

    services = OptimizerFlowServices(run_openbox_real_optimization=remote_openbox)
    report = optimize_project(
        prepared.cache_dir,
        real=True,
        dry_orchestration=False,
        max_evals=max_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        cadence_cshrc=Path("remote-cadence-env.csh"),
        execution_agent="direct",
        services=services,
    )
    _sync_cache_reports_to_remote(ref, prepared.cache_dir, ssh)
    return report


def continue_remote_project(
    ref: RemoteProjectRef,
    *,
    additional_evals: int,
    remote_cadence_cshrc: PurePosixPath,
    batch_size: int | None,
    parallel_jobs: int | None,
    cache_root: Path | None = None,
    runner: Any | None = None,
) -> OptimizerFlowReport:
    if additional_evals < 1:
        raise ValueError("additional_evals must be >= 1")
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    prepared = prepare_remote_project_cache(ref, runner=ssh, cache_root=cache_root)
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))
    _sync_remote_history_to_cache(ref, prepared.cache_dir, ssh)

    project_root = prepared.cache_dir
    _ensure_execution_manifest(project_root)

    def remote_openbox(project_dir: Path, **kwargs: object) -> object:
        bundle = assert_valid_project(project_dir)

        def selected_adapter(local_project: Path, run_id: str, cadence_cshrc: Path) -> object:
            if bundle.testbenches is not None:
                return run_remote_multi_testbench_adapter(
                    local_project,
                    run_id=run_id,
                    remote_ref=ref,
                    remote_cadence_cshrc=remote_cadence_cshrc,
                    runner=ssh,
                )
            return run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            )

        return run_openbox_real_optimization(
            project_dir,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            adapter=selected_adapter,
            surrogate_type=CONTINUATION_SURROGATE_TYPE,
            acq_type=CONTINUATION_ACQ_TYPE,
            acq_optimizer_type=CONTINUATION_ACQ_OPTIMIZER_TYPE,
        )

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
    _sync_cache_reports_to_remote(ref, project_root, ssh)
    return report


def _sync_remote_history_to_cache(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Download remote ledger/, state/, reports/, and execution_package/ if they exist."""
    for subdir in ("ledger", "state", "reports", "execution_package"):
        remote_dir = ref.remote_project_dir / subdir
        if ssh.exists(remote_dir):
            local_dir = cache_dir / subdir
            local_dir.mkdir(parents=True, exist_ok=True)
            try:
                ssh.download_tree(remote_dir, local_dir)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to sync remote history subdir '{subdir}': {exc}"
                ) from exc


def _sync_cache_reports_to_remote(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Upload local reports/, ledger/, state/, and execution_package/ back to remote."""
    for subdir in ("reports", "ledger", "state", "execution_package"):
        local_dir = cache_dir / subdir
        if local_dir.is_dir():
            remote_dir = ref.remote_project_dir / subdir
            ssh.upload_tree(local_dir, remote_dir)


def _ensure_execution_manifest(project_dir: Path) -> None:
    """Build execution package only if the manifest is missing."""
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    if not manifest_path.exists():
        build_execution_package(project_dir)


_REPORT_RELATIVE = Path("reports/optimizer_flow_run_report.json")


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
        execution_agent="direct",
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
