from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hermes_workflow.optimizer_flow import optimize_project


CADENCE_CSHRC_ENV_VAR = "IC_OPT_CADENCE_CSHRC"
PROJECT_CADENCE_CSHRC = Path("cadence_env.csh")
USER_CADENCE_CSHRC = Path("~/.ic-opt/cadence_env.csh")

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
    max_evals: Annotated[
        int,
        typer.Option("--max-evals", min=1, help="OpenBox real evaluation budget."),
    ] = 100,
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
        resolved_cadence_cshrc = _resolve_cadence_cshrc(project_dir, cadence_cshrc)
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
