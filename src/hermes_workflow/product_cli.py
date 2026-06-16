from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Annotated, NoReturn

import typer

from hermes_workflow.diagnostics import parse_diagnostics, format_diagnostics_for_cli
from hermes_workflow.optimizer_continuation_flow import continue_local_project
from hermes_workflow.optimizer_flow import optimize_project
from hermes_workflow.product_doctor import run_product_doctor
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_optimizer_flow import (
    continue_remote_project,
    optimize_remote_project,
)
from hermes_workflow.remote_project import RemoteProjectRef

CADENCE_CSHRC_ENV_VAR = "IC_OPT_CADENCE_CSHRC"
PROJECT_CADENCE_CSHRC = Path("cadence_env.csh")
USER_CADENCE_CSHRC = Path("~/.ic-opt/cadence_env.csh")

app = typer.Typer(
    add_completion=False,
    help="Product entrypoint for IC optimizer workflows.",
    no_args_is_help=True,
)


def _exit_with_error(exc: Exception) -> NoReturn:
    message = str(exc)
    if "Cadence cshrc was not found" in message:
        structured = [
            {
                "code": "CADENCE_CSHRC_MISSING",
                "severity": "error",
                "stage": "requirement",
                "component": "product_cli",
                "message": "Cadence cshrc was not found.",
                "detail": message,
                "likely_cause": (
                    "No usable Cadence environment file was found from project file "
                    "or known locations."
                ),
                "recommended_action": (
                    "Provide --cadence-cshrc PATH, set IC_OPT_CADENCE_CSHRC, or "
                    "create ~/.ic-opt/cadence_env.csh."
                ),
            }
        ]
        for line in format_diagnostics_for_cli(parse_diagnostics(structured)):
            typer.echo(line)
        typer.echo(message)
        raise typer.Exit(code=1)
    if "remote mode requires --doctor, --real, or --continue" in message:
        typer.echo(message)
        typer.echo("Use --doctor, --real, or --continue to pick a valid workflow mode.")
        raise typer.Exit(code=1)
    typer.echo(message)
    raise typer.Exit(code=1)


def _print_report_issues(report: object) -> None:
    structured_issues = parse_diagnostics(getattr(report, "structured_issues", []))
    if structured_issues:
        for line in format_diagnostics_for_cli(structured_issues):
            typer.echo(line)
        return

    issues = getattr(report, "issues", None)
    if not isinstance(issues, list):
        return
    for issue in issues:
        typer.echo(str(issue))


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
            raise ValueError(
                f"--cadence-cshrc does not exist or is not a file: {resolved}"
            )

    raise ValueError(
        "Cadence cshrc was not found. Provide --cadence-cshrc PATH, create "
        "PROJECT_DIR/cadence_env.csh, set IC_OPT_CADENCE_CSHRC, or create "
        "~/.ic-opt/cadence_env.csh."
    )


def _resolve_cadence_cshrc_for_doctor(project_dir: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser()
    try:
        return _resolve_cadence_cshrc(project_dir, explicit)
    except ValueError:
        return None

def _echo_report_path(project_dir: Path, report_path: Path | None) -> None:
    if report_path is None:
        return
    try:
        typer.echo(f"report: {report_path.relative_to(project_dir)}")
    except ValueError:
        typer.echo(f"report: {report_path}")

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
    ssh_profile: Annotated[
        str | None,
        typer.Option("--ssh-profile", help="OpenSSH profile for remote Linux EDA server."),
    ] = None,
    doctor: Annotated[
        bool,
        typer.Option("--doctor", help="Check project/tool readiness without running Spectre."),
    ] = False,
    continue_evals: Annotated[
        int | None,
        typer.Option("--continue", min=1, help="Continue an existing optimization by N evaluations."),
    ] = None,
) -> None:
    if ssh_profile is not None:
        ref = RemoteProjectRef(
            ssh_profile=ssh_profile,
            remote_project_dir=PurePosixPath(project_dir.as_posix()),
        )
        if doctor:
            report = run_remote_doctor(ref, cadence_cshrc=cadence_cshrc)
            if report.status == "pass":
                typer.echo("doctor completed")
                typer.echo("transport: remote")
                typer.echo(f"remote report: {report.remote_report_path}")
                typer.echo(f"local report: {report.local_report_path}")
                _print_report_issues(report)
                return
            typer.echo("doctor failed")
            typer.echo("transport: remote")
            _print_report_issues(report)
            typer.echo(f"local report: {report.local_report_path}")
            raise typer.Exit(code=1)
        if continue_evals is not None:
            if not real:
                _exit_with_error(
                    ValueError("--continue requires --real")
                )
            remote_cshrc = (
                PurePosixPath(str(cadence_cshrc))
                if cadence_cshrc is not None
                else ref.remote_project_dir / "cadence_env.csh"
            )
            try:
                report = continue_remote_project(
                    ref,
                    additional_evals=continue_evals,
                    remote_cadence_cshrc=remote_cshrc,
                    batch_size=None,
                    parallel_jobs=None,
                    strategy=None,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                _exit_with_error(exc)
            if report.status == "pass":
                typer.echo("remote continuation completed")
                if report.recommended_run_id is not None:
                    typer.echo(f"recommended: {report.recommended_run_id}")
                typer.echo(f"local report: {report.report_path}")
                return
            _print_report_issues(report)
            raise typer.Exit(code=1)
        if real:
            remote_cshrc = (
                PurePosixPath(str(cadence_cshrc))
                if cadence_cshrc is not None
                else ref.remote_project_dir / "cadence_env.csh"
            )
            try:
                report = optimize_remote_project(
                    ref,
                    real=True,
                    remote_cadence_cshrc=remote_cshrc,
                    max_evals=None,
                    batch_size=None,
                    parallel_jobs=None,
                    strategy=None,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                _exit_with_error(exc)
            if report.status == "pass":
                typer.echo("remote optimizer flow completed")
                if report.recommended_run_id is not None:
                    typer.echo(f"recommended: {report.recommended_run_id}")
                typer.echo(f"local report: {report.report_path}")
                typer.echo(
                    f"remote report: {ref.remote_project_dir / 'reports' / 'optimizer_decision_report.md'}"
                )
                return
            _print_report_issues(report)
            raise typer.Exit(code=1)
        _exit_with_error(
            ValueError("remote mode requires --doctor, --real, or --continue N")
        )

    if doctor:
        report = run_product_doctor(
            project_dir,
            cadence_cshrc=_resolve_cadence_cshrc_for_doctor(project_dir, cadence_cshrc),
        )
        if report.status == "pass":
            typer.echo("doctor completed")
            typer.echo("transport: local")
            _echo_report_path(project_dir, report.report_path)
            for warning in getattr(report, "warnings", []):
                typer.echo(f"warning: {warning}")
            return
        typer.echo("doctor failed")
        typer.echo("transport: local")
        _print_report_issues(report)
        _echo_report_path(project_dir, report.report_path)
        raise typer.Exit(code=1)

    try:
        resolved_cadence_cshrc = _resolve_cadence_cshrc(project_dir, cadence_cshrc)
    except (OSError, RuntimeError, ValueError) as exc:
        _exit_with_error(exc)

    if continue_evals is not None:
        if not real:
            _exit_with_error(ValueError("--continue requires --real"))
        try:
            report = continue_local_project(
                project_dir,
                additional_evals=continue_evals,
                cadence_cshrc=resolved_cadence_cshrc,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            _exit_with_error(exc)
        if report.status == "pass":
            typer.echo("continuation completed")
            _echo_report_path(project_dir, report.report_path)
            if getattr(report, "recommended_run_id", None) is not None:
                typer.echo(f"recommended: {report.recommended_run_id}")
            return
        typer.echo("continuation failed")
        _print_report_issues(report)
        _echo_report_path(project_dir, report.report_path)
        raise typer.Exit(code=1)

    try:
        report = optimize_project(
            project_dir,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=None,
            batch_size=None,
            parallel_jobs=None,
            cadence_cshrc=resolved_cadence_cshrc,
            strategy=None,
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
    _print_report_issues(report)
    typer.echo("report: reports/optimizer_flow_run_report.json")
    raise typer.Exit(code=1)
