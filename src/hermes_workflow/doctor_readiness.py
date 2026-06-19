from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, load_optimizer_artifacts
from hermes_workflow.optimizer_artifacts import REPORT_RELATIVE as OPTIMIZER_REPORT_RELATIVE
from hermes_workflow.optimizer_strategy import (
    OptimizerStrategyRequest,
    resolve_optimizer_strategy,
)
from hermes_workflow.real_result_record import OPTIMIZER_STATE_PATH
from hermes_workflow.schemas import (
    OpenBoxOptimizerSettings,
    OptimizerAlgorithm,
    OptimizerStrategy,
    TurboOptimizerSettings,
)


LEDGER_RELATIVE = Path("ledger/experiment_ledger.jsonl")


def build_requirement_summary(sections: dict[str, Any]) -> dict[str, Any]:
    """Summarize requirement sections for doctor reporting.

    Returns testbench/corner counts, child-run matrix size, and the
    objective/constraint policies. Pure: does not parse files or run tools.
    """
    testbench_count, has_multi_testbench = _testbench_count(sections)
    process_corners = sections.get("Process Corners")
    has_process_corners = isinstance(process_corners, dict)
    if has_process_corners:
        corners = process_corners.get("corners", [])
        corner_count = len(corners) if isinstance(corners, list) else 1
        objective_policy = str(process_corners.get("objective_policy", "worst_case"))
        constraint_policy = str(process_corners.get("constraint_policy", "all_corners"))
    else:
        corner_count = 1
        objective_policy = "nominal"
        constraint_policy = "nominal"
    return {
        "has_multi_testbench": has_multi_testbench,
        "testbench_count": testbench_count,
        "has_process_corners": has_process_corners,
        "corner_count": corner_count,
        "objective_policy": objective_policy,
        "constraint_policy": constraint_policy,
        "child_runs_per_candidate": testbench_count * corner_count,
        "inside_candidate_execution": "serial",
    }


def build_evaluation_matrix_summary(sections: dict[str, Any]) -> dict[str, Any]:
    """Summarize the candidate evaluation matrix for doctor reporting."""
    requirement = build_requirement_summary(sections)
    spectre = sections.get("Spectre Settings")
    parallel_jobs: int | None = None
    if isinstance(spectre, dict):
        value = spectre.get("parallel_jobs")
        if isinstance(value, int):
            parallel_jobs = value
    return {
        "candidate_parallelism": parallel_jobs,
        "testbench_count": requirement["testbench_count"],
        "corner_count": requirement["corner_count"],
        "child_runs_per_candidate": requirement["child_runs_per_candidate"],
        "inside_candidate_execution": "serial",
    }


def build_optimizer_summary(
    *,
    optimizer_section: dict[str, Any],
    variable_count: int,
    cli_max_evals: int | None,
) -> dict[str, Any]:
    """Summarize requested vs resolved optimizer strategy for doctor reporting.

    Uses the same strategy resolver as the real optimizer flow. The budget
    source field reports whether ``max_evaluations`` came from a CLI override,
    the generated config, or a built-in fallback.
    """
    algorithm_value = optimizer_section.get("algorithm")
    if not isinstance(algorithm_value, str):
        raise ValueError("optimizer.algorithm must be a string")
    algorithm = OptimizerAlgorithm(algorithm_value)

    strategy_value = optimizer_section.get("strategy")
    strategy: OptimizerStrategy | None
    if strategy_value is None:
        strategy = None
    else:
        strategy = OptimizerStrategy.from_user_value(strategy_value)

    openbox_section = optimizer_section.get("openbox")
    openbox_settings: OpenBoxOptimizerSettings | None
    if isinstance(openbox_section, dict):
        openbox_settings = OpenBoxOptimizerSettings.model_validate(openbox_section)
    else:
        openbox_settings = None

    turbo_section = optimizer_section.get("turbo")
    turbo_settings: TurboOptimizerSettings | None
    if isinstance(turbo_section, dict):
        turbo_settings = TurboOptimizerSettings.model_validate(turbo_section)
    else:
        turbo_settings = None

    request = OptimizerStrategyRequest(
        algorithm=algorithm,
        strategy=strategy,
        openbox=openbox_settings,
        turbo=turbo_settings,
        variable_count=max(variable_count, 1),
    )
    resolved = resolve_optimizer_strategy(request)

    config_max_evals = optimizer_section.get("max_evaluations")
    if cli_max_evals is not None:
        max_evaluations: int | None = int(cli_max_evals)
        max_evaluations_source = "cli"
    elif isinstance(config_max_evals, int):
        max_evaluations = config_max_evals
        max_evaluations_source = "config"
    else:
        max_evaluations = None
        max_evaluations_source = "default"

    return {
        "algorithm": algorithm.value,
        "requested_strategy": resolved.requested_strategy.value,
        "resolved_backend": resolved.backend,
        "model_based": resolved.model_based,
        "surrogate_type": resolved.surrogate_type,
        "acq_type": resolved.acq_type,
        "acq_optimizer_type": resolved.acq_optimizer_type,
        "initial_trials": resolved.initial_trials,
        "snap_to_step": resolved.snap_to_step,
        "duplicate_handling": resolved.duplicate_handling,
        "max_evaluations": max_evaluations,
        "max_evaluations_source": max_evaluations_source,
    }


def build_run_retention_summary(
    spectre_section: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize the run retention policy for doctor reporting.

    Reads ``keep_failed_runs`` and ``keep_successful_runs`` from the
    requirement Spectre Settings section and exposes the static cleanup
    scope and decision-report paths so users can see the active policy
    before a real run starts.
    """
    keep_failed_runs: bool | None = None
    keep_successful_runs: bool | None = None
    if isinstance(spectre_section, dict):
        if isinstance(spectre_section.get("keep_failed_runs"), bool):
            keep_failed_runs = bool(spectre_section["keep_failed_runs"])
        if isinstance(spectre_section.get("keep_successful_runs"), bool):
            keep_successful_runs = bool(spectre_section["keep_successful_runs"])
    return {
        "keep_failed_runs": keep_failed_runs,
        "keep_successful_runs": keep_successful_runs,
        "cleanup_scope": "runs/real/<run_id>",
        "decision_reports": "state/run_retention/<run_id>.json",
    }


def build_resource_summary(
    *,
    spectre_section: dict[str, Any] | None,
    optimizer_section: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize resource settings for doctor reporting."""
    parallel_jobs: int | None = None
    threads_per_run: int | None = None
    if isinstance(spectre_section, dict):
        if isinstance(spectre_section.get("parallel_jobs"), int):
            parallel_jobs = int(spectre_section["parallel_jobs"])
        if isinstance(spectre_section.get("threads_per_run"), int):
            threads_per_run = int(spectre_section["threads_per_run"])
    optimizer_cpu_threads: int | None = None
    if isinstance(optimizer_section, dict):
        if isinstance(optimizer_section.get("optimizer_cpu_threads"), int):
            optimizer_cpu_threads = int(optimizer_section["optimizer_cpu_threads"])
    return {
        "parallel_jobs": parallel_jobs,
        "threads_per_run": threads_per_run,
        "optimizer_cpu_threads": optimizer_cpu_threads,
        "run_retention": build_run_retention_summary(spectre_section),
    }


def build_dirty_state_summary(
    project_dir: Path,
) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Summarize potentially confusing project state before a real run.

    Returns ``(summary, diagnostics)`` where diagnostics are warnings about
    interrupted or inconsistent run artifacts. Optimizer history alone is not
    a warning; only candidate run directories that lack any candidate-level
    completion artifact are flagged.
    """
    project_dir = Path(project_dir)
    diagnostics: list[Diagnostic] = []
    runs_dir = project_dir / "runs" / "real"
    has_runs = runs_dir.is_dir() and any(runs_dir.iterdir())
    incomplete_runs: list[Path] = []
    if has_runs:
        for run in sorted(runs_dir.iterdir()):
            if not run.is_dir():
                continue
            facts = _local_real_run_dir_facts(run)
            if is_incomplete_real_run_dir(facts):
                incomplete_runs.append(run)
    has_incomplete_real_run = bool(incomplete_runs)
    if has_incomplete_real_run:
        for run in incomplete_runs:
            diagnostics.append(
                Diagnostic(
                    code="INCOMPLETE_REAL_RUN",
                    severity=DiagnosticSeverity.WARN,
                    stage="doctor",
                    component="doctor_readiness",
                    message=f"Incomplete real run directory detected: {run.name}.",
                    detail=(
                        "The candidate run directory has neither a "
                        "candidate-level result manifest "
                        "(result_manifest.json or "
                        "metrics/metric_result_manifest.json) nor a legacy "
                        "optimizer-level report; the previous run may have "
                        "been interrupted before finalizing."
                    ),
                    likely_cause=(
                        "The previous real candidate evaluation did not "
                        "finalize before exiting."
                    ),
                    recommended_action=(
                        "Inspect the candidate run directory before starting "
                        "a fresh real run. Move or remove it once you have "
                        "copied any needed artifacts."
                    ),
                    evidence=[str(run.relative_to(project_dir))],
                )
            )
    has_execution_package = (project_dir / "execution_package").is_dir()
    has_optimizer_state = (project_dir / OPTIMIZER_STATE_PATH).is_file()
    has_optimizer_run_report = (project_dir / OPTIMIZER_REPORT_RELATIVE).is_file()
    has_optimizer_evaluations = (project_dir / EVALUATIONS_RELATIVE).is_file()

    summary = {
        "has_runs": has_runs,
        "has_incomplete_real_run": has_incomplete_real_run,
        "has_execution_package": has_execution_package,
        "has_optimizer_state": has_optimizer_state,
        "has_optimizer_run_report": has_optimizer_run_report,
        "has_optimizer_evaluations": has_optimizer_evaluations,
    }
    return summary, diagnostics


def build_doctor_semantic_summaries(
    sections: dict[str, Any],
    *,
    cli_max_evals: int | None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[Diagnostic],
]:
    """Compute the shared doctor semantic summaries.

    Returns ``(requirement_summary, evaluation_matrix, optimizer_summary,
    resource_summary, diagnostics)``. ``diagnostics`` includes any error-level
    issues encountered while resolving optimizer strategy or budget; callers
    must surface them as failures rather than silently dropping them.
    """
    diagnostics: list[Diagnostic] = []
    if not sections:
        return {}, {}, {}, {}, diagnostics
    requirement_summary = build_requirement_summary(sections)
    evaluation_matrix = build_evaluation_matrix_summary(sections)
    optimizer_section = sections.get("Optimizer Settings")
    optimizer_summary: dict[str, Any] = {}
    if isinstance(optimizer_section, dict):
        variables = sections.get("Design Variables", [])
        variable_count = len(variables) if isinstance(variables, list) else 0
        try:
            optimizer_summary = build_optimizer_summary(
                optimizer_section=optimizer_section,
                variable_count=variable_count,
                cli_max_evals=cli_max_evals,
            )
        except (ValueError, TypeError) as exc:
            diagnostics.append(
                Diagnostic(
                    code="OPTIMIZER_STRATEGY_INVALID",
                    severity=DiagnosticSeverity.ERROR,
                    stage="doctor",
                    component="doctor_readiness",
                    message="Optimizer strategy resolution failed.",
                    detail=str(exc),
                    likely_cause=(
                        "optimizer.algorithm or optimizer.strategy in "
                        "opt_requirement.md is invalid or incompatible."
                    ),
                    recommended_action=(
                        "Use a valid optimizer.algorithm and a compatible "
                        "optimizer.strategy (openbox_auto, openbox_gp_eic, "
                        "openbox_prf_eic, turbo_trust_region, or "
                        "random_baseline)."
                    ),
                    evidence=["opt_requirement.md:Optimizer Settings"],
                )
            )
    spectre_section = sections.get("Spectre Settings")
    spectre_dict = spectre_section if isinstance(spectre_section, dict) else None
    optimizer_dict = optimizer_section if isinstance(optimizer_section, dict) else None
    resource_summary = build_resource_summary(
        spectre_section=spectre_dict,
        optimizer_section=optimizer_dict,
    )
    return (
        requirement_summary,
        evaluation_matrix,
        optimizer_summary,
        resource_summary,
        diagnostics,
    )


def _testbench_count(sections: dict[str, Any]) -> tuple[int, bool]:
    maestro = sections.get("Maestro Source")
    if isinstance(maestro, dict):
        testbenches = maestro.get("testbenches")
        if isinstance(testbenches, list) and testbenches:
            return len(testbenches), True
    return 1, False


def _run_dir_is_complete(run_dir: Path) -> bool:
    """Return True when the local candidate run directory looks complete.

    Thin wrapper around :func:`is_incomplete_real_run_dir` retained for
    backwards compatibility with any callers outside this module.
    """
    return not is_incomplete_real_run_dir(_local_real_run_dir_facts(run_dir))


@dataclass(frozen=True)
class RealRunDirFacts:
    """Filesystem facts about one ``runs/real/<run_id>`` candidate directory.

    Local doctor builds this from the local filesystem. Remote doctor builds
    the same shape from SSH probes. Both then call
    :func:`is_incomplete_real_run_dir`.
    """

    name: str
    has_result_manifest: bool
    has_metric_result_manifest: bool
    has_optimizer_run_report: bool
    has_optimizer_completion_report: bool
    has_candidate_marker: bool


def is_incomplete_real_run_dir(facts: RealRunDirFacts) -> bool:
    """Return True when a real-run candidate directory should warn.

    A candidate directory is COMPLETE when it carries any candidate-level
    completion artifact (result manifest, metric result manifest) or a legacy
    optimizer-level report. An empty directory is incomplete. A directory
    with only a candidate request marker but no completion artifact is
    incomplete.
    """
    if facts.has_result_manifest:
        return False
    if facts.has_metric_result_manifest:
        return False
    if facts.has_optimizer_run_report or facts.has_optimizer_completion_report:
        return False
    return True


def _local_real_run_dir_facts(run_dir: Path) -> RealRunDirFacts:
    return RealRunDirFacts(
        name=run_dir.name,
        has_result_manifest=(run_dir / "result_manifest.json").is_file(),
        has_metric_result_manifest=(
            run_dir / "metrics" / "metric_result_manifest.json"
        ).is_file(),
        has_optimizer_run_report=any(
            (
                (run_dir / "reports" / "optimizer_run_report.json").is_file(),
                (run_dir / "optimizer_run_report.json").is_file(),
            )
        ),
        has_optimizer_completion_report=any(
            (
                (run_dir / "reports" / "optimizer_completion_report.json").is_file(),
                (run_dir / "optimizer_completion_report.json").is_file(),
            )
        ),
        has_candidate_marker=any(
            (
                (run_dir / "candidate_request.json").is_file(),
                (run_dir / "candidate.json").is_file(),
            )
        ),
    )


def build_optimizer_progress_summary(
    project_dir: Path,
    *,
    requirement_max_evaluations: int | None = None,
) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Compare optimizer report/evaluations/state/ledger counts.

    Returns ``(summary, diagnostics)``. The summary always carries the same
    set of count keys (``None`` when the underlying artifact is missing).
    A single :class:`Diagnostic` with code
    ``OPTIMIZER_PROGRESS_STATE_MISMATCH`` is emitted when any present pair of
    counts disagree; missing artifacts are silent so a fresh project does
    not produce noise.
    """
    project_dir = Path(project_dir)
    artifacts = load_optimizer_artifacts(project_dir, issues=[])
    report = artifacts.report or {}
    traces = artifacts.traces or []

    report_count_value = report.get("evaluation_count")
    report_evaluation_count = (
        int(report_count_value) if isinstance(report_count_value, int) else None
    )
    evaluation_trace_count = len(traces)

    state_path = project_dir / OPTIMIZER_STATE_PATH
    state_payload: dict[str, Any] | None
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            loaded = None
        state_payload = loaded if isinstance(loaded, dict) else None
    else:
        state_payload = None

    state_current = (
        state_payload.get("current_evaluations") if state_payload else None
    )
    state_recorded = (
        state_payload.get("recorded_observation_count") if state_payload else None
    )
    state_failed = (
        state_payload.get("failed_evaluation_count") if state_payload else None
    )
    state_status_counts = (
        state_payload.get("status_counts") if state_payload else None
    )

    ledger_count = _count_ledger_rows_local(project_dir)

    summary: dict[str, Any] = {
        "report_evaluation_count": report_evaluation_count,
        "evaluation_trace_count": evaluation_trace_count,
        "state_current_evaluations": state_current,
        "state_recorded_observation_count": state_recorded,
        "ledger_row_count": ledger_count,
        "failed_evaluation_count": state_failed,
        "status_counts": state_status_counts,
    }

    diagnostics: list[Diagnostic] = []
    mismatches: list[str] = []

    def _disagree(left: Any, right: Any) -> bool:
        return left is not None and right is not None and left != right

    has_any_artifact = (
        report_evaluation_count is not None
        or evaluation_trace_count > 0
        or state_payload is not None
    )
    has_evaluations_file = (project_dir / EVALUATIONS_RELATIVE).exists()
    trace_count_for_compare: int | None = (
        evaluation_trace_count if has_evaluations_file else None
    )

    if has_any_artifact:
        if _disagree(report_evaluation_count, trace_count_for_compare):
            mismatches.append("report_evaluation_count != evaluation_trace_count")
        if _disagree(report_evaluation_count, state_current):
            mismatches.append("report_evaluation_count != state.current_evaluations")
        if _disagree(trace_count_for_compare, state_current):
            mismatches.append("evaluation_trace_count != state.current_evaluations")
        if _disagree(state_recorded, ledger_count):
            mismatches.append(
                "state.recorded_observation_count != ledger_row_count"
            )

    if mismatches:
        detail = (
            f"report={report_evaluation_count}, evaluations={evaluation_trace_count}, "
            f"state.current_evaluations={state_current}, "
            f"state.recorded_observation_count={state_recorded}, "
            f"ledger={ledger_count}"
        )
        diagnostics.append(
            Diagnostic(
                code="OPTIMIZER_PROGRESS_STATE_MISMATCH",
                severity=DiagnosticSeverity.ERROR,
                stage="doctor",
                component="doctor_readiness",
                message="Optimizer progress artifacts disagree.",
                detail=detail,
                likely_cause=(
                    "state/optimizer_state.json was written from a stale source "
                    "(for example, ledger row count) instead of the optimizer "
                    "trace artifacts."
                ),
                recommended_action=(
                    "Re-run the optimizer report writer or doctor sync to "
                    "regenerate state/optimizer_state.json from "
                    "reports/optimizer_run_report.json and "
                    "reports/optimizer_evaluations.jsonl."
                ),
                evidence=[
                    artifacts.report_relative.as_posix(),
                    artifacts.evaluations_relative.as_posix(),
                    OPTIMIZER_STATE_PATH,
                    LEDGER_RELATIVE.as_posix(),
                ],
            )
        )
    return summary, diagnostics


def _count_ledger_rows_local(project_dir: Path) -> int:
    ledger_path = project_dir / LEDGER_RELATIVE
    if not ledger_path.exists():
        return 0
    count = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count
