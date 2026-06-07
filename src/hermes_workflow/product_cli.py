from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_flow import optimize_project
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.optimizer_task_package import build_optimizer_execution_task_package
from hermes_workflow.package import build_execution_package
from hermes_workflow.product_doctor import (
    ProductDoctorReport,
    run_product_doctor,
)


CADENCE_CSHRC_ENV_VAR = "IC_OPT_CADENCE_CSHRC"
PROJECT_CADENCE_CSHRC = Path("cadence_env.csh")
USER_CADENCE_CSHRC = Path("~/.ic-opt/cadence_env.csh")
CONTINUATION_SURROGATE_TYPE = "prf"
CONTINUATION_ACQ_TYPE = "eic"
CONTINUATION_ACQ_OPTIMIZER_TYPE = "local_random"

app = typer.Typer(
    add_completion=False,
    help="Product entrypoint for IC optimizer workflows.",
    no_args_is_help=True,
)


def _exit_with_error(exc: Exception) -> NoReturn:
    typer.echo(str(exc))
    raise typer.Exit(code=1)


def _resolve_cadence_cshrc(project_dir: Path, explicit: Path | None) -> Path:
    candidates: list[tuple[str, Path]] = []
    if explicit is not None:
        candidates.append(("--cadence-cshrc", explicit))
    candidates.append(("PROJECT_DIR/cadence_env.csh", project_dir / PROJECT_CADENCE_CSHRC))
    env_value = os.environ.get(CADENCE_CSHRC_ENV_VAR)
    if env_value:
        candidates.append((CADENCE_CSHRC_ENV_VAR, Path(env_value)))
    candidates.append(("~/.ic-opt/cadence_env.csh", USER_CADENCE_CSHRC))

    for source, path in candidates:
        resolved = path.expanduser()
        if resolved.is_file():
            return resolved
        if explicit is not None and source == "--cadence-cshrc":
            raise ValueError(f"--cadence-cshrc does not exist or is not a file: {resolved}")

    raise ValueError(
        "Cadence cshrc was not found. Provide --cadence-cshrc PATH, create "
        "PROJECT_DIR/cadence_env.csh, set IC_OPT_CADENCE_CSHRC, or create "
        "~/.ic-opt/cadence_env.csh."
    )


def _find_cadence_cshrc_for_doctor(project_dir: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser()
    for path in _cadence_cshrc_candidates(project_dir):
        resolved = path.expanduser()
        if resolved.is_file():
            return resolved
    return None


def _cadence_cshrc_candidates(project_dir: Path) -> list[Path]:
    candidates = [project_dir / PROJECT_CADENCE_CSHRC]
    env_value = os.environ.get(CADENCE_CSHRC_ENV_VAR)
    if env_value:
        candidates.append(Path(env_value))
    candidates.append(USER_CADENCE_CSHRC)
    return candidates


@app.command()
def main(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory containing opt_requirement.md."),
    ],
    real: Annotated[
        bool,
        typer.Option("--real", help="Run the approved real optimizer route."),
    ] = False,
    dry_orchestration: Annotated[
        bool,
        typer.Option(
            "--dry-orchestration",
            help="Run offline gates and stop before real tools.",
        ),
    ] = False,
    doctor: Annotated[
        bool,
        typer.Option(
            "--doctor",
            help="Run lightweight project/environment diagnostics and exit.",
        ),
    ] = False,
    max_evals: Annotated[
        int,
        typer.Option("--max-evals", min=1, help="OpenBox real evaluation budget."),
    ] = 100,
    continue_evals: Annotated[
        int | None,
        typer.Option(
            "--continue",
            min=1,
            help="Add this many real evaluations to an existing optimizer run.",
        ),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option("--batch-size", min=1, help="OpenBox suggestion batch size."),
    ] = None,
    parallel_jobs: Annotated[
        int | None,
        typer.Option(
            "--parallel-jobs",
            min=1,
            help="Maximum concurrently launched Spectre runs.",
        ),
    ] = None,
    cadence_cshrc: Annotated[
        Path | None,
        typer.Option(
            "--cadence-cshrc",
            help=(
                "User/project Cadence cshrc. If omitted, ic-opt checks "
                "PROJECT_DIR/cadence_env.csh, IC_OPT_CADENCE_CSHRC, then "
                "~/.ic-opt/cadence_env.csh."
            ),
        ),
    ] = None,
    execution_agent: Annotated[
        str,
        typer.Option(
            "--execution-agent",
            help="Execution mode: direct or claude.",
        ),
    ] = "direct",
) -> None:
    try:
        if doctor:
            report = run_product_doctor(
                project_dir,
                cadence_cshrc=_find_cadence_cshrc_for_doctor(project_dir, cadence_cshrc),
            )
            _print_doctor_report(report)
            if report.status != "pass":
                raise typer.Exit(code=1)
            return
        resolved_cadence_cshrc = _resolve_cadence_cshrc(project_dir, cadence_cshrc)
        if continue_evals is not None:
            _continue_project(
                project_dir,
                additional_evals=continue_evals,
                dry_orchestration=dry_orchestration,
                batch_size=batch_size,
                parallel_jobs=parallel_jobs,
                cadence_cshrc=resolved_cadence_cshrc,
            )
            return
        report = optimize_project(
            project_dir,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            cadence_cshrc=resolved_cadence_cshrc,
            execution_agent=execution_agent,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        _exit_with_error(exc)

    if report.status == "pass":
        typer.echo("optimizer flow completed")
        typer.echo(f"report: {report.report_path.relative_to(project_dir)}")
        if report.stopped_before is not None:
            typer.echo(f"stopped before: {report.stopped_before}")
        if report.recommended_run_id is not None:
            typer.echo(f"recommended: {report.recommended_run_id}")
        if report.user_decision_required:
            typer.echo("user decision required: true")
        return

    typer.echo("optimizer flow failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/optimizer_flow_run_report.json")
    raise typer.Exit(code=1)


def _continue_project(
    project_dir: Path,
    *,
    additional_evals: int,
    dry_orchestration: bool,
    batch_size: int | None,
    parallel_jobs: int | None,
    cadence_cshrc: Path,
) -> None:
    project_root = Path(project_dir)
    if additional_evals < 1:
        raise ValueError("--continue must be >= 1")
    _ensure_base_execution_manifest(project_root)

    if dry_orchestration:
        package = build_optimizer_execution_task_package(
            project_root,
            max_evals=None,
            additional_evals=additional_evals,
            cadence_cshrc=cadence_cshrc,
            parallel=True,
            optimizer_backend="openbox",
            continuation=True,
        )
        typer.echo("optimizer continuation orchestration completed")
        typer.echo(f"task: {package.task_path.relative_to(project_root)}")
        typer.echo(f"manifest: {package.manifest_path.relative_to(project_root)}")
        return

    result = run_openbox_real_optimization(
        project_root,
        max_evals=None,
        additional_evals=additional_evals,
        continue_from_existing=True,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        cadence_cshrc=cadence_cshrc,
        surrogate_type=CONTINUATION_SURROGATE_TYPE,
        acq_type=CONTINUATION_ACQ_TYPE,
        acq_optimizer_type=CONTINUATION_ACQ_OPTIMIZER_TYPE,
    )
    _run_continuation_closeout(project_root)

    typer.echo(
        "optimizer continuation completed: "
        f"{result.evaluation_count} cumulative evaluations"
    )
    if result.report_path is not None:
        typer.echo(f"report: {result.report_path.relative_to(project_root)}")
    if result.evaluations_path is not None:
        typer.echo(f"evaluations: {result.evaluations_path.relative_to(project_root)}")
    decision = generate_optimizer_decision_report(project_root)
    if decision.status != "pass":
        raise ValueError("decide-optimizer-run failed after continuation")
    if decision.recommended_run_id is not None:
        typer.echo(f"recommended: {decision.recommended_run_id}")
    typer.echo("decision: reports/optimizer_decision_report.md")


def _ensure_base_execution_manifest(project_dir: Path) -> None:
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    if not manifest_path.exists():
        build_execution_package(project_dir)


def _run_continuation_closeout(project_dir: Path) -> None:
    acceptance = check_optimizer_run(project_dir)
    if getattr(acceptance, "status", None) != "accepted":
        raise ValueError("check-optimizer-run failed after continuation")
    completion = summarize_optimizer_run(project_dir)
    if getattr(completion, "status", None) != "pass":
        raise ValueError("summarize-optimizer-run failed after continuation")
    finalized = finalize_optimizer_run(project_dir)
    if getattr(finalized, "status", None) != "pass":
        raise ValueError("finalize-optimizer-run failed after continuation")
    insight = generate_optimizer_insight_report(project_dir)
    if getattr(insight, "status", None) != "pass":
        raise ValueError("visualize-optimizer-run failed after continuation")


def _print_doctor_report(report: ProductDoctorReport) -> None:
    typer.echo(f"ic-opt doctor {report.status}")
    for check in report.checks:
        label = {
            "pass": "PASS",
            "warning": "WARN",
            "fail": "FAIL",
        }.get(check.status, check.status.upper())
        typer.echo(f"{label} {check.name}: {check.detail}")
    if report.report_path is not None:
        try:
            typer.echo(f"report: {report.report_path.relative_to(Path(report.project_dir))}")
        except ValueError:
            typer.echo(f"report: {report.report_path}")
