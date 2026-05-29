from pathlib import Path
from typing import Annotated

import typer

from hermes_workflow import __version__
from hermes_workflow.approvals import decide_first_real_run
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


def _exit_with_error(exc: Exception) -> None:
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
        return
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
        return
    typer.echo(report.format())
    if not report.ok:
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
        return
    typer.echo(str(manifest.path.relative_to(project_dir)))


@app.command("approve")
def approve_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with Claude preflight reports."),
    ],
) -> None:
    try:
        instruction = decide_first_real_run(project_dir)
    except OSError as exc:
        _exit_with_error(exc)
        return
    typer.echo(instruction["decision"])
    if instruction["decision"] != "approve_first_real_run":
        raise typer.Exit(code=1)
