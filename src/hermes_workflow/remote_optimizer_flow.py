from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_spectre_ocean_adapter,
)
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_flow import (
    OptimizerFlowReport,
    OptimizerFlowServices,
    optimize_project,
)
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
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
        return run_openbox_real_optimization(
            project_dir,
            adapter=lambda local_project, run_id, cadence_cshrc: run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            ),
            **kwargs,
        )

    services = OptimizerFlowServices(run_openbox_real_optimization=remote_openbox)
    return optimize_project(
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

    def remote_openbox(project_dir: Path, **kwargs: object):
        return run_openbox_real_optimization(
            project_dir,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            adapter=lambda local_project, run_id, cadence_cshrc: run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            ),
        )

    services = OptimizerFlowServices(run_openbox_real_optimization=remote_openbox)
    report = optimize_project(
        prepared.cache_dir,
        real=True,
        dry_orchestration=False,
        max_evals=additional_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        cadence_cshrc=Path("remote-cadence-env.csh"),
        execution_agent="direct",
        services=services,
    )
    _sync_cache_reports_to_remote(ref, prepared.cache_dir, ssh)
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
            except Exception:
                pass  # Best-effort: continuation works even if some dirs are missing


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
