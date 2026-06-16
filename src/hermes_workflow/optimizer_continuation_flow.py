"""Local optimizer continuation entrypoint.

Reuses the existing closeout helper exposed by ``remote_optimizer_flow`` so the
local ``ic-opt PROJECT --real --continue N`` route runs the exact same
sequence that the remote variant runs (openbox -> check -> summarize ->
finalize -> insight -> decision -> flow report).

Product continuation only forwards the CLI continuation budget delta. All
optimizer strategy, OpenBox surrogate/acquisition details, batch size, and
parallel-jobs values are resolved from the project's requirement-backed
``config/optimizer.yaml`` by the backend resolver.
"""

from __future__ import annotations

from pathlib import Path

from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_flow import OptimizerFlowReport
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.remote_optimizer_flow import run_continuation_closeout
from hermes_workflow.validate import assert_valid_project


def continue_local_project(
    project_dir: Path,
    *,
    additional_evals: int,
    cadence_cshrc: Path,
) -> OptimizerFlowReport:
    """Run the local OpenBox continuation closeout for a real project."""
    if additional_evals < 1:
        raise ValueError("additional_evals must be >= 1")
    project_root = Path(project_dir)
    assert_valid_project(project_root)

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

    return run_continuation_closeout(
        project_root,
        openbox_fn=local_openbox,
        check_fn=check_optimizer_run,
        summarize_fn=summarize_optimizer_run,
        finalize_fn=finalize_optimizer_run,
        insight_fn=generate_optimizer_insight_report,
        decision_fn=generate_optimizer_decision_report,
        additional_evals=additional_evals,
        batch_size=None,
        parallel_jobs=None,
    )
