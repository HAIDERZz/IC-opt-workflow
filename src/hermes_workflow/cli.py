import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hermes_workflow import __version__
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.health import write_preflight_health
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.mock_optimizer import run_mock_optimization
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.native_turbo import (
    run_batch_native_turbo_optimization,
    run_native_turbo_optimization,
)
from hermes_workflow.openbox_backend import (
    run_openbox_fake_optimization,
    run_openbox_real_optimization,
)
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_suggestion import suggest_candidate_request
from hermes_workflow.optimizer_task_package import (
    build_optimizer_execution_task_package,
)
from hermes_workflow.package import (
    TemplateError,
    build_execution_package,
    create_project_from_template,
)
from hermes_workflow.real_run import (
    prepare_candidate_real_run,
    prepare_next_real_run,
    prepare_real_run,
)
from hermes_workflow.real_run_recovery import (
    assess_real_run_recovery,
    prepare_real_run_retry,
    resolve_real_run_failure,
)
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.result_handoff import check_real_run
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


def _recovery_report_fingerprint(project_dir: Path) -> tuple[int, int] | None:
    report_path = project_dir / "reports" / "real_run_recovery_report.json"
    try:
        stat = report_path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _exit_with_recovery_report(
    exc: Exception,
    project_dir: Path,
    previous_report: tuple[int, int] | None,
) -> NoReturn:
    typer.echo(str(exc))
    report_path = project_dir / "reports" / "real_run_recovery_report.json"
    if _recovery_report_fingerprint(project_dir) != previous_report:
        typer.echo("report: reports/real_run_recovery_report.json")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise typer.Exit(code=1)
        issues = report.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if isinstance(issue, str):
                    typer.echo(issue)
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


@app.command("package-optimizer-task")
def package_optimizer_task_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with approved real-tool contracts."),
    ],
    max_evals: Annotated[
        int,
        typer.Option("--max-evals", help="Optimizer evaluation budget for the task."),
    ],
    cadence_cshrc: Annotated[
        Path,
        typer.Option("--cadence-cshrc", help="Cadence cshrc to source for execution."),
    ],
    parallel: Annotated[
        bool,
        typer.Option(
            "--parallel/--sequential",
            help="Whether the execution agent should use batch parallel mode.",
        ),
    ] = True,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            help="Optimizer backend for the execution task: native-turbo or openbox.",
        ),
    ] = "native-turbo",
) -> None:
    try:
        package = build_optimizer_execution_task_package(
            project_dir,
            max_evals=max_evals,
            cadence_cshrc=cadence_cshrc,
            parallel=parallel,
            optimizer_backend=backend,
        )
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(str(package.task_path.relative_to(project_dir)))
    typer.echo(str(package.manifest_path.relative_to(project_dir)))


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


@app.command("prepare-real-run")
def prepare_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with approve_first_real_run instruction."
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Real-run package id such as real_001.",
        ),
    ] = None,
) -> None:
    try:
        package = prepare_real_run(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")


@app.command("prepare-next-real-run")
def prepare_next_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with at least one recorded checked real result."
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Optional next real-run package id such as real_002.",
        ),
    ] = None,
) -> None:
    try:
        package = prepare_next_real_run(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("next real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")
    typer.echo(f"candidate: {package.candidate_path.relative_to(project_dir)}")


@app.command("prepare-candidate-real-run")
def prepare_candidate_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with at least one recorded checked real result."
        ),
    ],
    candidate_file: Annotated[
        Path,
        typer.Option(
            "--candidate-file",
            help="JSON file containing one explicit optimizer candidate request.",
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Optional candidate real-run package id such as real_002.",
        ),
    ] = None,
) -> None:
    try:
        package = prepare_candidate_real_run(
            project_dir,
            candidate_file=candidate_file,
            run_id=run_id,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("candidate real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")
    typer.echo(f"candidate: {package.candidate_path.relative_to(project_dir)}")
    typer.echo(
        "candidate request: "
        f"{package.run_dir.relative_to(project_dir) / 'candidate_request.json'}"
    )


@app.command("suggest-candidate")
def suggest_candidate_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with checked optimizer ledger/state."),
    ],
    candidate_id: Annotated[
        str | None,
        typer.Option("--candidate-id", help="Optional candidate id for the request."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional candidate request output path."),
    ] = None,
) -> None:
    try:
        result = suggest_candidate_request(
            project_dir,
            candidate_id=candidate_id,
            output_path=output,
        )
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(f"candidate request written: {result.output_path}")
    typer.echo(f"candidate id: {result.candidate_id}")
    typer.echo(f"selection mode: {result.selection_mode}")


@app.command("assess-real-run-recovery")
def assess_real_run_recovery_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a real-run package."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Real-run package id such as real_002."),
    ],
) -> None:
    try:
        report = assess_real_run_recovery(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run recovery assessed")
    typer.echo(f"run: runs/real/{report.run_id}")
    typer.echo(f"classification: {report.classification.value}")
    if report.recommended_action is not None:
        typer.echo(f"recommended: {report.recommended_action.value}")
    typer.echo("report: reports/real_run_recovery_report.json")
    if report.status.value != "pass":
        for issue in report.issues:
            typer.echo(issue)
        raise typer.Exit(code=1)


@app.command("prepare-real-run-retry")
def prepare_real_run_retry_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a failed real-run package."),
    ],
    failed_run_id: Annotated[
        str,
        typer.Option("--failed-run-id", help="Failed real-run id such as real_002."),
    ],
    retry_run_id: Annotated[
        str | None,
        typer.Option("--retry-run-id", help="Optional retry real-run id."),
    ] = None,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Supervisor reason for retry."),
    ] = "supervisor requested retry",
) -> None:
    previous_report = _recovery_report_fingerprint(project_dir)
    try:
        retry = prepare_real_run_retry(
            project_dir,
            failed_run_id=failed_run_id,
            retry_run_id=retry_run_id,
            reason=reason,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_recovery_report(exc, project_dir, previous_report)
    typer.echo("real run retry package prepared")
    typer.echo(f"failed run: runs/real/{retry.failed_run_id}")
    typer.echo(f"retry run: runs/real/{retry.run_id}")
    typer.echo(f"decision: {retry.decision_path.relative_to(project_dir)}")
    typer.echo(f"manifest: {retry.package.manifest_path.relative_to(project_dir)}")


@app.command("resolve-real-run-failure")
def resolve_real_run_failure_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a failed real-run package."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Real-run package id such as real_002."),
    ],
    decision: Annotated[
        str,
        typer.Option(
            "--decision",
            help=(
                "Recovery decision: abandon_candidate, stop_workflow, "
                "or revise_contracts."
            ),
        ),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Supervisor reason for this decision."),
    ],
) -> None:
    previous_report = _recovery_report_fingerprint(project_dir)
    try:
        report = resolve_real_run_failure(
            project_dir,
            run_id=run_id,
            decision=decision,
            reason=reason,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_recovery_report(exc, project_dir, previous_report)
    typer.echo("real run failure resolved")
    typer.echo(f"run: runs/real/{report.run_id}")
    typer.echo(f"decision: {decision}")
    typer.echo(f"classification: {report.classification.value}")
    typer.echo(f"decision_file: runs/real/{report.run_id}/recovery_decision.json")


@app.command("check-real-run")
def check_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a returned real-run result manifest."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Real-run package id such as real_001.",
        ),
    ] = None,
) -> None:
    try:
        report = check_real_run(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("real run handoff check passed")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo(f"result: {report.result_manifest}")
        typer.echo("report: reports/real_run_check_report.json")
        return

    typer.echo("real run handoff check failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/real_run_check_report.json")
    raise typer.Exit(code=1)


@app.command("check-metric-results")
def check_metric_results_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with returned OCEAN metric result artifacts."
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Real-run package id such as real_001.",
        ),
    ] = None,
) -> None:
    try:
        report = check_metric_results(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("metric result check passed")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo("report: reports/metric_result_check_report.json")
        return

    typer.echo("metric result check failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/metric_result_check_report.json")
    raise typer.Exit(code=1)


@app.command("check-optimizer-run")
def check_optimizer_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with completed optimizer artifacts."),
    ],
) -> None:
    try:
        report = check_optimizer_run(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status == "accepted":
        typer.echo("optimizer run accepted")
        typer.echo("report: reports/optimizer_run_acceptance_report.json")
        return

    typer.echo("optimizer run rejected")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/optimizer_run_acceptance_report.json")
    raise typer.Exit(code=1)


@app.command("summarize-optimizer-run")
def summarize_optimizer_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with accepted optimizer artifacts."),
    ],
) -> None:
    try:
        report = summarize_optimizer_run(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status == "pass":
        typer.echo(f"optimizer completion decision: {report.decision}")
        typer.echo(f"confidence: {report.confidence}")
        typer.echo(f"global optimum claim: {str(report.global_optimum_claim).lower()}")
        typer.echo("report: reports/optimizer_completion_report.json")
        return

    typer.echo("optimizer completion decision failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/optimizer_completion_report.json")
    raise typer.Exit(code=1)


@app.command("run-openbox-fake")
def run_openbox_fake_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with optimizer config artifacts."),
    ],
    max_evals: Annotated[
        int,
        typer.Option("--max-evals", min=1, help="Fake OpenBox evaluation budget."),
    ] = 40,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, help="Fake OpenBox suggestion batch size."),
    ] = 4,
) -> None:
    try:
        result = run_openbox_fake_optimization(
            project_dir,
            max_evals=max_evals,
            batch_size=batch_size,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(
        f"openbox fake optimizer completed: {result.evaluation_count} evaluations"
    )
    if result.report_path is not None:
        typer.echo(f"report: {result.report_path.relative_to(project_dir)}")
    if result.evaluations_path is not None:
        typer.echo(f"evaluations: {result.evaluations_path.relative_to(project_dir)}")


@app.command("run-openbox-real")
def run_openbox_real_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with approved real-tool contracts."),
    ],
    max_evals: Annotated[
        int | None,
        typer.Option("--max-evals", min=1, help="OpenBox real evaluation budget."),
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
            help="Optional Cadence cshrc sourced before running the adapter.",
        ),
    ] = None,
) -> None:
    try:
        result = run_openbox_real_optimization(
            project_dir,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            cadence_cshrc=cadence_cshrc,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(
        f"openbox real optimization completed: {result.evaluation_count} evaluations"
    )
    if result.report_path is not None:
        typer.echo(f"report: {result.report_path.relative_to(project_dir)}")
    if result.evaluations_path is not None:
        typer.echo(f"evaluations: {result.evaluations_path.relative_to(project_dir)}")


@app.command("record-real-result")
def record_real_result_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with checked real result artifacts."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Real-run package id such as real_001."),
    ] = None,
) -> None:
    try:
        report = record_real_result(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("real result recorded")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo(f"ledger: {report.ledger_path}")
        typer.echo(f"state: {report.optimizer_state_path}")
        typer.echo("report: reports/real_result_record_report.json")
        return

    typer.echo("real result record failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/real_result_record_report.json")
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


@app.command("run-native-turbo")
def run_native_turbo_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with approved real-tool contracts."),
    ],
    max_evals: Annotated[
        int | None,
        typer.Option("--max-evals", help="Override optimizer evaluation budget."),
    ] = None,
    cadence_cshrc: Annotated[
        Path | None,
        typer.Option(
            "--cadence-cshrc",
            help="Optional Cadence cshrc sourced before running the adapter.",
        ),
    ] = None,
    parallel: Annotated[
        bool,
        typer.Option(
            "--parallel/--sequential",
            help="Evaluate TuRBO batches in parallel.",
        ),
    ] = False,
) -> None:
    try:
        runner = (
            run_batch_native_turbo_optimization
            if parallel
            else run_native_turbo_optimization
        )
        result = runner(
            project_dir,
            max_evals=max_evals,
            cadence_cshrc=cadence_cshrc,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(
        f"native turbo optimization completed: {result.evaluation_count} evaluations"
    )
    if result.report_path is not None:
        typer.echo(f"report: {result.report_path.relative_to(project_dir)}")
    if result.evaluations_path is not None:
        typer.echo(f"evaluations: {result.evaluations_path.relative_to(project_dir)}")
