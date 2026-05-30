import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hermes_workflow import __version__
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.health import write_preflight_health
from hermes_workflow.mock_optimizer import run_mock_optimization
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.package import (
    TemplateError,
    build_execution_package,
    create_project_from_template,
)
from hermes_workflow.validate import validate_project_files


app = typer.Typer(help="Hermes file-contract workflow tools.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the package version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    return None


def _exit_with_error(exc: Exception) -> NoReturn:
    typer.echo(str(exc))
    raise typer.Exit(code=1)


@app.command("init")
def init_command(
    destination: Annotated[Path, typer.Argument(help="Project directory to create.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite files inside an existing project directory."),
    ] = False,
) -> None:
    try:
        project_dir = create_project_from_template(destination, force=force)
    except TemplateError as exc:
        _exit_with_error(exc)
    typer.echo(str(project_dir))


@app.command("validate")
def validate_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory containing config/*.yaml."),
    ],
) -> None:
    try:
        report = validate_project_files(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(report.format())
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("prepare-netlist")
def prepare_netlist_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with exported netlists/input.scs."),
    ],
) -> None:
    try:
        report = prepare_netlist(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("netlist preparation passed")
        return

    typer.echo("netlist preparation failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/netlist_preparation_report.json")
    raise typer.Exit(code=1)


@app.command("dry-run")
def dry_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with netlists/templates/template.scs."),
    ],
) -> None:
    try:
        report = run_dry_run(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("dry run passed")
        return

    typer.echo("dry run failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/dry_run_report.json")
    raise typer.Exit(code=1)


@app.command("preflight-health")
def preflight_health_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with validated config/*.yaml."),
    ],
) -> None:
    try:
        report = write_preflight_health(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "healthy":
        typer.echo("preflight health passed")
        return

    typer.echo("preflight health failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: state/health_check.json")
    raise typer.Exit(code=1)


@app.command("package")
def package_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory to package for Claude Code."),
    ],
) -> None:
    try:
        manifest = build_execution_package(project_dir)
    except (FileExistsError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(str(manifest.path.relative_to(project_dir)))


@app.command("approve")
def approve_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with preflight reports."),
    ],
) -> None:
    try:
        instruction = decide_first_real_run(project_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(instruction["decision"])
    if instruction["decision"] != "approve_first_real_run":
        raise typer.Exit(code=1)


@app.command("mock-run")
def mock_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with validated config/*.yaml."),
    ],
    max_evaluations: Annotated[
        int | None,
        typer.Option(
            "--max-evaluations",
            help="Override max_evaluations from optimizer.yaml.",
        ),
    ] = None,
) -> None:
    try:
        state = run_mock_optimization(project_dir, max_evaluations=max_evaluations)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(f"mock optimization completed: {state.current_evaluations}/{state.max_evaluations} evaluations")
    typer.echo(f"best candidate: {state.best_candidate_id or 'none'}")
