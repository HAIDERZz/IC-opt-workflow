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
