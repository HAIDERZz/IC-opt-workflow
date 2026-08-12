from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.health import write_preflight_health
from hermes_workflow.native_turbo import run_batch_native_turbo_optimization
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from hermes_workflow.optimizer_decision import generate_optimizer_decision_report
from hermes_workflow.optimizer_finalize import finalize_optimizer_run
from hermes_workflow.optimizer_insights import generate_optimizer_insight_report
from hermes_workflow.optimizer_strategy import (
    OptimizerStrategyName,
    OptimizerStrategyRequest,
    resolve_optimizer_strategy,
)
from hermes_workflow.optimizer_task_package import build_optimizer_execution_task_package
from hermes_workflow.package import build_execution_package
from hermes_workflow.project_readiness import check_project_ready
from hermes_workflow.requirement_intake import (
    check_requirement,
    prepare_from_requirement,
)
from hermes_workflow.product_doctor import run_product_doctor
from hermes_workflow.validate import assert_valid_project, validate_project_files

REPORT_RELATIVE = Path("reports/optimizer_flow_run_report.json")


def _backend_for_strategy(strategy_name: OptimizerStrategyName) -> str:
    return (
        "native_turbo"
        if strategy_name is OptimizerStrategyName.TURBO_TRUST_REGION
        else "openbox"
    )


def _backend_from_explicit_strategy(backend: str, strategy: str | None) -> str:
    if strategy is None:
        return backend
    return _backend_for_strategy(OptimizerStrategyName.from_user_value(strategy))


def _backend_from_project_strategy(
    project_dir: Path,
    *,
    backend: str,
    strategy: str | None,
) -> str:
    if strategy is not None:
        return _backend_from_explicit_strategy(backend, strategy)
    if not (project_dir / "config" / "optimizer.yaml").exists():
        return backend
    bundle = assert_valid_project(project_dir)
    settings = bundle.optimizer.optimizer
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=settings.algorithm,
            strategy=settings.strategy,
            openbox=settings.openbox,
            turbo=settings.turbo,
            variable_count=len(bundle.variables.variables),
        )
    )
    # The diagnostic random baseline is implemented by the OpenBox backend;
    # native TuRBO is the only separate execution backend.
    return "native_turbo" if resolved.backend == "native_turbo" else "openbox"


@dataclass(frozen=True)
class OptimizerFlowStep:
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class OptimizerFlowReport:
    status: str
    project_dir: str
    backend: str
    real: bool
    dry_orchestration: bool
    max_evals: int | None
    batch_size: int | None
    parallel_jobs: int | None
    steps: list[OptimizerFlowStep]
    user_decision_required: bool
    recommended_run_id: str | None = None
    recommended_action: str | None = None
    stopped_before: str | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None


@dataclass(frozen=True)
class OptimizerFlowServices:
    check_requirement: Callable[[Path], Any] = check_requirement
    prepare_from_requirement: Callable[[Path], Any] = prepare_from_requirement
    validate_project_files: Callable[[Path], Any] = validate_project_files
    check_project_ready: Callable[[Path], Any] = check_project_ready
    build_execution_package: Callable[[Path], Any] = build_execution_package
    prepare_netlist: Callable[[Path], Any] = prepare_netlist
    run_dry_run: Callable[[Path], Any] = run_dry_run
    write_preflight_health: Callable[[Path], Any] = write_preflight_health
    decide_first_real_run: Callable[[Path], Any] = decide_first_real_run
    build_optimizer_execution_task_package: Callable[..., Any] = (
        build_optimizer_execution_task_package
    )
    run_openbox_real_optimization: Callable[..., Any] = run_openbox_real_optimization
    run_batch_native_turbo_optimization: Callable[..., Any] = (
        run_batch_native_turbo_optimization
    )
    check_optimizer_run: Callable[[Path], Any] = check_optimizer_run
    summarize_optimizer_run: Callable[[Path], Any] = summarize_optimizer_run
    finalize_optimizer_run: Callable[[Path], Any] = finalize_optimizer_run
    generate_optimizer_insight_report: Callable[[Path], Any] = (
        generate_optimizer_insight_report
    )
    generate_optimizer_decision_report: Callable[[Path], Any] = (
        generate_optimizer_decision_report
    )
    run_product_doctor: Callable[..., Any] = run_product_doctor


def optimize_project(
    project_dir: str | Path,
    *,
    real: bool,
    cadence_cshrc: Path | None,
    dry_orchestration: bool = False,
    max_evals: int | None = None,
    batch_size: int | None = None,
    parallel_jobs: int | None = None,
    backend: str = "openbox",
    strategy: str | None = None,
    services: OptimizerFlowServices | None = None,
) -> OptimizerFlowReport:
    project_root = Path(project_dir)
    service = services or OptimizerFlowServices()
    steps: list[OptimizerFlowStep] = []
    issues: list[str] = []
    warnings: list[str] = []
    recommended_run_id: str | None = None
    recommended_action: str | None = None
    stopped_before: str | None = None
    user_decision_required = False
    execution_backend = _backend_from_explicit_strategy(backend, strategy)

    try:
        _validate_options(
            real=real,
            cadence_cshrc=cadence_cshrc,
            max_evals=max_evals,
            backend=execution_backend,
        )
        _run_step(
            steps,
            "check-requirement",
            lambda: service.check_requirement(project_root),
            _expect_optimize_requirement,
        )
        if real:
            doctor_report = service.run_product_doctor(
                project_root,
                cadence_cshrc=cadence_cshrc,
            )
            if doctor_report.status != "pass":
                raise ValueError(
                    "doctor failed: " + "; ".join(doctor_report.issues)
                )
        _run_step(
            steps,
            "prepare-from-requirement",
            lambda: service.prepare_from_requirement(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "validate",
            lambda: service.validate_project_files(project_root),
            _expect_ok,
        )
        _run_step(
            steps,
            "check-project-ready",
            lambda: service.check_project_ready(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        execution_backend = _backend_from_project_strategy(
            project_root,
            backend=backend,
            strategy=strategy,
        )
        _validate_options(
            real=real,
            cadence_cshrc=cadence_cshrc,
            max_evals=max_evals,
            backend=execution_backend,
        )
        _run_step(
            steps,
            "package",
            lambda: service.build_execution_package(project_root),
            _expect_success,
        )
        _run_step(
            steps,
            "prepare-netlist",
            lambda: service.prepare_netlist(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "dry-run",
            lambda: service.run_dry_run(project_root),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "preflight-health",
            lambda: service.write_preflight_health(project_root),
            lambda result: _expect_status(result, "healthy"),
        )
        _run_step(
            steps,
            "approve",
            lambda: service.decide_first_real_run(project_root),
            _expect_approval,
        )
        _run_step(
        steps,
        "package-optimizer-task",
            lambda: service.build_optimizer_execution_task_package(
                project_root,
                cadence_cshrc=cadence_cshrc,
                parallel=True,
            optimizer_backend=execution_backend,
            strategy=strategy,
            ),
            _expect_success,
        )

        dry_stopped_before = (
            "run-native-turbo-real"
            if execution_backend == "native_turbo"
            else "run-openbox-real"
        )
        if dry_orchestration:
            return _write_report(
            project_root,
            _report(
                project_root,
                status="pass",
                backend=execution_backend,
                    real=real,
                    dry_orchestration=dry_orchestration,
                max_evals=max_evals,
                batch_size=batch_size,
                parallel_jobs=parallel_jobs,
                steps=steps,
                user_decision_required=False,
                stopped_before=dry_stopped_before,
                issues=issues,
                warnings=warnings,
            ),
            )

        if execution_backend == "native_turbo":
            _run_step(
                steps,
                "run-native-turbo-real",
                lambda: service.run_batch_native_turbo_optimization(
                    project_root,
                    max_evals=max_evals,
                    parallel_jobs=parallel_jobs,
                    cadence_cshrc=cadence_cshrc,
                ),
                _expect_success,
            )
        else:
            _run_step(
                steps,
                "run-openbox-real",
                lambda: service.run_openbox_real_optimization(
                    project_root,
                    max_evals=max_evals,
                    batch_size=batch_size,
                    parallel_jobs=parallel_jobs,
                    cadence_cshrc=cadence_cshrc,
                    **({"strategy": strategy} if strategy is not None else {}),
                ),
                _expect_success,
            )
        _run_step(
            steps,
            "check-optimizer-run",
            lambda: service.check_optimizer_run(
                project_root,
                expected_backend=execution_backend,
            ),
            lambda result: _expect_status(result, "accepted"),
        )
        _run_step(
            steps,
            "summarize-optimizer-run",
            lambda: service.summarize_optimizer_run(
                project_root,
                expected_backend=execution_backend,
            ),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "finalize-optimizer-run",
            lambda: service.finalize_optimizer_run(
                project_root,
                expected_backend=execution_backend,
            ),
            lambda result: _expect_status(result, "pass"),
        )
        _run_step(
            steps,
            "visualize-optimizer-run",
            lambda: service.generate_optimizer_insight_report(
                project_root,
                expected_backend=execution_backend,
            ),
            lambda result: _expect_status(result, "pass"),
        )
        decision = _run_step(
            steps,
            "decide-optimizer-run",
            lambda: service.generate_optimizer_decision_report(
                project_root,
                expected_backend=execution_backend,
            ),
            lambda result: _expect_status(result, "pass"),
        )
        recommended_run_id = _string_attr(decision, "recommended_run_id")
        recommended_action = _string_attr(decision, "recommended_action")
        user_decision_required = True
    except Exception as exc:
        issues.append(str(exc))
        report = _report(
            project_root,
            status="fail",
                backend=execution_backend,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            steps=steps,
            user_decision_required=False,
            stopped_before=stopped_before,
            issues=issues,
            warnings=warnings,
        )
        _write_report(project_root, report)
        raise

    return _write_report(
        project_root,
        _report(
            project_root,
            status="pass",
            backend=execution_backend,
            real=real,
            dry_orchestration=dry_orchestration,
            max_evals=max_evals,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            steps=steps,
            user_decision_required=user_decision_required,
            recommended_run_id=recommended_run_id,
            recommended_action=recommended_action,
            stopped_before=stopped_before,
        issues=issues,
            warnings=warnings,
        ),
    )


def _validate_options(
    *,
    real: bool,
    cadence_cshrc: Path | None,
    max_evals: int | None,
    backend: str,
) -> None:
    if not real:
        raise ValueError("optimize requires --real; fake optimize is not supported")
    if backend not in {"openbox", "native_turbo"}:
        raise ValueError("optimize backend must be openbox or native_turbo")
    if max_evals is not None and max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if cadence_cshrc is None:
        raise ValueError("--cadence-cshrc is required")


def _run_step(
    steps: list[OptimizerFlowStep],
    name: str,
    action: Callable[[], Any],
    validate: Callable[[Any], str | None],
) -> Any:
    try:
        result = action()
        issue = validate(result)
    except Exception as exc:
        steps.append(OptimizerFlowStep(name=name, status="fail", detail=str(exc)))
        raise ValueError(f"{name} failed: {exc}") from exc
    if issue is not None:
        steps.append(OptimizerFlowStep(name=name, status="fail", detail=issue))
        raise ValueError(f"{name} failed: {issue}")
    steps.append(OptimizerFlowStep(name=name, status="pass", detail=_detail(result)))
    return result


def _expect_success(_result: Any) -> str | None:
    return None


def _expect_ok(result: Any) -> str | None:
    if getattr(result, "ok", False):
        return None
    return _issues_detail(result) or "status is not ok"


def _expect_status(result: Any, expected: str) -> str | None:
    status = _status_value(getattr(result, "status", None))
    if status == expected:
        return None
    return _issues_detail(result) or f"status is {status or 'unknown'}, expected {expected}"


def _expect_optimize_requirement(result: Any) -> str | None:
    status_issue = _expect_status(result, "pass")
    if status_issue is not None:
        return status_issue
    workflow_mode = getattr(result, "workflow_mode", "optimize")
    if workflow_mode != "optimize":
        return (
            "optimize requires workflow mode 'optimize'; "
            f"got {workflow_mode!r}"
        )
    return None


def _expect_approval(result: Any) -> str | None:
    if isinstance(result, dict) and result.get("decision") == "approve_first_real_run":
        return None
    return "approval decision is not approve_first_real_run"


def _status_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    enum_value = getattr(value, "value", None)
    return enum_value if isinstance(enum_value, str) else ""


def _issues_detail(result: Any) -> str:
    issues = getattr(result, "issues", None)
    if isinstance(issues, list) and issues:
        return "; ".join(str(issue) for issue in issues)
    return ""


def _detail(result: Any) -> str:
    for attr in (
        "report_path",
        "markdown_path",
        "manifest_path",
        "task_path",
        "path",
        "evaluation_count",
        "recommended_run_id",
    ):
        value = getattr(result, attr, None)
        if value is not None:
            return f"{attr}={value}"
    if isinstance(result, dict) and "decision" in result:
        return f"decision={result['decision']}"
    return ""


def _string_attr(result: Any, attr: str) -> str | None:
    value = getattr(result, attr, None)
    return value if isinstance(value, str) and value else None


def _report(
    project_root: Path,
    *,
    status: str,
    backend: str,
    real: bool,
    dry_orchestration: bool,
    max_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
    steps: list[OptimizerFlowStep],
    user_decision_required: bool,
    recommended_run_id: str | None = None,
    recommended_action: str | None = None,
    stopped_before: str | None = None,
    issues: list[str],
    warnings: list[str],
) -> OptimizerFlowReport:
    return OptimizerFlowReport(
        status=status,
        project_dir=str(project_root),
        backend=backend,
        real=real,
        dry_orchestration=dry_orchestration,
        max_evals=max_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        steps=list(steps),
        user_decision_required=user_decision_required,
        recommended_run_id=recommended_run_id,
        recommended_action=recommended_action,
        stopped_before=stopped_before,
        issues=list(issues),
        warnings=list(warnings),
        report_path=project_root / REPORT_RELATIVE,
    )


def _write_report(project_root: Path, report: OptimizerFlowReport) -> OptimizerFlowReport:
    report_path = project_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    payload["steps"] = [asdict(step) for step in report.steps]
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return report
