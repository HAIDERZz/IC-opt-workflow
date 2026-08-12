"""Local optimizer continuation entrypoint.

Reuses the existing closeout helper exposed by ``remote_optimizer_flow`` so the
local ``ic-opt PROJECT --real --continue N`` route runs the exact same
sequence that the remote variant runs (selected backend -> check -> summarize
-> finalize -> insight -> decision -> flow report).

Product continuation only forwards the CLI continuation budget delta. All
optimizer strategy, backend details, batch size, and parallel-jobs values are
resolved from the project's requirement-backed
``config/optimizer.yaml`` by the backend resolver.
"""

from __future__ import annotations

from pathlib import Path

from hermes_workflow.native_turbo import run_batch_native_turbo_optimization
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_flow import (
    OptimizerFlowReport,
    _backend_from_project_strategy,
)
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.remote_optimizer_flow import run_continuation_closeout
from hermes_workflow.validate import (
    assert_valid_project,
    local_model_file_is_readable,
)


def continue_local_project(
    project_dir: Path,
    *,
    additional_evals: int,
    cadence_cshrc: Path,
) -> OptimizerFlowReport:
    """Continue the optimizer backend selected by the project requirement."""
    if additional_evals < 1:
        raise ValueError("additional_evals must be >= 1")
    project_root = Path(project_dir)
    bundle = assert_valid_project(
        project_root,
        model_file_is_readable=local_model_file_is_readable,
    )
    if bundle.optimizer is None:
        raise ValueError("continuation requires an optimize workflow")
    backend = _backend_from_project_strategy(
        project_root,
        backend="openbox",
        strategy=None,
    )

    def local_openbox(project: Path, **_kwargs: object) -> object:
        return run_openbox_real_optimization(
            project,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            batch_size=None,
            parallel_jobs=None,
            cadence_cshrc=cadence_cshrc,
            strategy=None,
            surrogate_type=None,
            acq_type=None,
            acq_optimizer_type=None,
            initial_trials=None,
        )

    def local_native_turbo(project: Path, **_kwargs: object) -> object:
        return run_batch_native_turbo_optimization(
            project,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            cadence_cshrc=cadence_cshrc,
            transport_mode="local",
        )

    optimizer_fn = local_native_turbo if backend == "native_turbo" else local_openbox
    run_step_name = (
        "run-native-turbo-real"
        if backend == "native_turbo"
        else "run-openbox-real"
    )
    return run_continuation_closeout(
        project_root,
        optimizer_fn=optimizer_fn,
        backend=backend,
        run_step_name=run_step_name,
        check_fn=check_optimizer_run,
        summarize_fn=summarize_optimizer_run,
        finalize_fn=finalize_optimizer_run,
        insight_fn=generate_optimizer_insight_report,
        decision_fn=generate_optimizer_decision_report,
        additional_evals=additional_evals,
        batch_size=None,
        parallel_jobs=None,
    )
