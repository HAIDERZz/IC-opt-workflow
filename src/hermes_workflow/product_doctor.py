from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity
from hermes_workflow.doctor_readiness import (
    build_dirty_state_summary,
    build_doctor_semantic_summaries,
    build_optimizer_progress_summary,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.optimizer_artifacts import REPORT_RELATIVE as OPTIMIZER_REPORT_RELATIVE
from hermes_workflow.project_readiness import check_project_ready
from hermes_workflow.real_result_record import LEDGER_PATH, OPTIMIZER_STATE_PATH
from hermes_workflow.requirement_intake import (
    check_requirement,
    prepare_from_requirement,
)
from hermes_workflow.license_probe import (
    LicenseProbeReport,
    run_license_probe_skipped,
    run_local_license_probe,
    write_license_probe_report,
)
from hermes_workflow.toolchain_env import check_toolchain_environment


REPORT_RELATIVE = Path("reports/ic_opt_doctor_report.json")


@dataclass(frozen=True)
class ProductDoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ProductDoctorReport:
    status: str
    project_dir: str
    checks: list[ProductDoctorCheck]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structured_issues: list[Diagnostic] = field(default_factory=list)
    transport: dict[str, Any] = field(default_factory=dict)
    requirement_summary: dict[str, Any] = field(default_factory=dict)
    evaluation_matrix: dict[str, Any] = field(default_factory=dict)
    optimizer_summary: dict[str, Any] = field(default_factory=dict)
    resource_summary: dict[str, Any] = field(default_factory=dict)
    dirty_state: dict[str, Any] = field(default_factory=dict)
    optimizer_progress_summary: dict[str, Any] = field(default_factory=dict)
    license_probe: dict[str, Any] = field(default_factory=dict)
    report_path: Path | None = None


@dataclass(frozen=True)
class ProductDoctorServices:
    check_requirement: Callable[[Path], Any] = check_requirement
    prepare_from_requirement: Callable[[Path], Any] = prepare_from_requirement
    check_project_ready: Callable[[Path], Any] = check_project_ready
    check_toolchain_environment: Callable[..., dict[str, Any]] = (
        check_toolchain_environment
    )
    check_license: Callable[..., LicenseProbeReport] = run_local_license_probe


def run_product_doctor(
    project_dir: str | Path,
    *,
    cadence_cshrc: Path | None,
    openbox_venv: Path | None = None,
    services: ProductDoctorServices | None = None,
    cli_max_evals: int | None = None,
) -> ProductDoctorReport:
    project_root = Path(project_dir)
    service = services or ProductDoctorServices()
    checks: list[ProductDoctorCheck] = []
    issues: list[str] = []
    warnings: list[str] = []
    structured_issues: list[Diagnostic] = []

    transport = {
        "mode": "local",
        "ssh_profile": None,
        "project_dir": str(project_root),
    }

    if not project_root.exists():
        _add(checks, issues, "project_directory", "fail", "project directory is missing")
        return _report(
            project_root,
            checks,
            issues,
            warnings,
            structured_issues,
            transport=transport,
            requirement_summary={},
            evaluation_matrix={},
            optimizer_summary={},
            resource_summary={},
            dirty_state={},
            optimizer_progress_summary={},
            license_probe={},
            write=False,
        )
    if not project_root.is_dir():
        _add(checks, issues, "project_directory", "fail", "project path is not a directory")
        return _report(
            project_root,
            checks,
            issues,
            warnings,
            structured_issues,
            transport=transport,
            requirement_summary={},
            evaluation_matrix={},
            optimizer_summary={},
            resource_summary={},
            dirty_state={},
            optimizer_progress_summary={},
            license_probe={},
            write=False,
        )
    _add(checks, issues, "project_directory", "pass", "project directory exists")

    requirement_ok, requirement_sections = _check_requirement(
        project_root, service, checks, issues
    )
    cadence_ok = _check_cadence_cshrc(cadence_cshrc, checks, issues)
    license_probe_report = _check_license_probe(
        project_root,
        requirement_sections,
        cadence_cshrc=cadence_cshrc if cadence_ok else None,
        service=service,
        checks=checks,
        issues=issues,
    )
    _check_toolchain(
        project_root,
        service,
        checks,
        issues,
        openbox_venv=openbox_venv or Path(sys.prefix),
        cadence_cshrc=cadence_cshrc if cadence_ok else None,
    )

    prepare_ok = False
    if requirement_ok:
        prepare_ok = _prepare_project(project_root, service, checks, issues)
    else:
        _add(
            checks,
            issues,
            "prepare_from_requirement",
            "fail",
            "skipped because opt_requirement.md is not valid",
        )

    if prepare_ok:
        _check_project_ready(project_root, service, checks, issues, warnings)
    else:
        _add(
            checks,
            issues,
            "project_ready",
            "fail",
            "skipped because project preparation failed",
        )

    _check_continuation_artifacts(project_root, checks, issues, warnings)

    requirement_summary, evaluation_matrix, optimizer_summary, resource_summary, semantic_diagnostics = (
        build_doctor_semantic_summaries(requirement_sections, cli_max_evals=cli_max_evals)
    )
    structured_issues.extend(semantic_diagnostics)
    for diagnostic in semantic_diagnostics:
        if diagnostic.severity is DiagnosticSeverity.ERROR:
            _add(
                checks,
                issues,
                diagnostic.code.lower(),
                "fail",
                diagnostic.detail or diagnostic.message,
            )
    dirty_state, dirty_diagnostics = build_dirty_state_summary(project_root)
    structured_issues.extend(dirty_diagnostics)
    for diagnostic in dirty_diagnostics:
        warnings.append(f"{diagnostic.code}: {diagnostic.message}")

    requirement_max_evaluations: int | None = None
    if isinstance(optimizer_summary, dict):
        candidate = optimizer_summary.get("max_evaluations")
        if isinstance(candidate, int):
            requirement_max_evaluations = candidate
    optimizer_progress_summary, progress_diagnostics = build_optimizer_progress_summary(
        project_root,
        requirement_max_evaluations=requirement_max_evaluations,
    )
    structured_issues.extend(progress_diagnostics)
    for diagnostic in progress_diagnostics:
        if diagnostic.severity is DiagnosticSeverity.ERROR:
            _add(
                checks,
                issues,
                diagnostic.code.lower(),
                "fail",
                diagnostic.detail or diagnostic.message,
            )

    return _report(
        project_root,
        checks,
        issues,
        warnings,
        structured_issues,
        transport=transport,
        requirement_summary=requirement_summary,
        evaluation_matrix=evaluation_matrix,
        optimizer_summary=optimizer_summary,
        resource_summary=resource_summary,
        dirty_state=dirty_state,
        optimizer_progress_summary=optimizer_progress_summary,
        license_probe=license_probe_report.to_dict() if license_probe_report else {},
        write=True,
    )


def _check_requirement(
    project_root: Path,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
) -> tuple[bool, dict[str, Any]]:
    try:
        result = service.check_requirement(project_root)
    except Exception as exc:
        _add(checks, issues, "requirement", "fail", str(exc))
        return False, {}
    sections = getattr(result, "sections", None)
    if not isinstance(sections, dict):
        sections = {}
    if getattr(result, "status", None) == "pass":
        _add(checks, issues, "requirement", "pass", "opt_requirement.md parsed")
        return True, sections
    detail = _issues_detail(getattr(result, "issues", []))
    _add(checks, issues, "requirement", "fail", detail or "requirement intake failed")
    return False, sections


def _check_cadence_cshrc(
    cadence_cshrc: Path | None,
    checks: list[ProductDoctorCheck],
    issues: list[str],
) -> bool:
    if cadence_cshrc is None:
        _add(checks, issues, "cadence_cshrc", "fail", "cadence_env.csh was not found")
        return False
    if cadence_cshrc.is_file():
        _add(checks, issues, "cadence_cshrc", "pass", str(cadence_cshrc))
        return True
    _add(
        checks,
        issues,
        "cadence_cshrc",
        "fail",
        f"Cadence cshrc does not exist: {cadence_cshrc}",
    )
    return False


def _check_license_probe(
    project_root: Path,
    requirement_sections: dict[str, Any],
    *,
    cadence_cshrc: Path | None,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
) -> LicenseProbeReport | None:
    """Run license probe if ``require_license_check`` is true."""
    spectre_settings = requirement_sections.get("Spectre Settings")
    require = False
    if isinstance(spectre_settings, dict):
        require = bool(spectre_settings.get("require_license_check", False))

    if not require:
        report = run_license_probe_skipped(execution_mode="local")
        _add(checks, issues, "license_probe", "skipped", "require_license_check is false")
        write_license_probe_report(project_root, report)
        return report

    if cadence_cshrc is None:
        report = LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            issues=["cadence cshrc is missing; cannot run license probe"],
        )
        _add(checks, issues, "license_probe", "fail", "cadence cshrc is missing; cannot run license probe")
        write_license_probe_report(project_root, report)
        return report

    try:
        report = service.check_license(cadence_cshrc)
    except Exception as exc:
        report = LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            issues=[f"license probe raised exception: {exc}"],
        )

    write_license_probe_report(project_root, report)

    if report.status == "pass":
        _add(checks, issues, "license_probe", "pass", "license environment probe passed")
    else:
        detail = "; ".join(report.issues) if report.issues else "license environment probe failed"
        _add(checks, issues, "license_probe", "fail", detail)
    return report


def _check_toolchain(
    project_root: Path,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
    *,
    openbox_venv: Path,
    cadence_cshrc: Path | None,
) -> None:
    if cadence_cshrc is None:
        _add(
            checks,
            issues,
            "toolchain_environment",
            "fail",
            "skipped because Cadence cshrc is missing",
        )
        return
    try:
        payload = service.check_toolchain_environment(
            openbox_venv=openbox_venv,
            cadence_cshrc=cadence_cshrc,
            report_path=project_root / "reports" / "toolchain_env_report.json",
        )
    except Exception as exc:
        _add(checks, issues, "toolchain_environment", "fail", str(exc))
        return
    if payload.get("status") == "pass":
        _add(
            checks,
            issues,
            "toolchain_environment",
            "pass",
            "OpenBox/Hermes imports and Cadence cshrc path passed",
        )
        return
    detail = _issues_detail(payload.get("issues", []))
    _add(
        checks,
        issues,
        "toolchain_environment",
        "fail",
        detail or "toolchain environment check failed",
    )


def _prepare_project(
    project_root: Path,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
) -> bool:
    try:
        result = service.prepare_from_requirement(project_root)
    except Exception as exc:
        _add(checks, issues, "prepare_from_requirement", "fail", str(exc))
        return False
    if getattr(result, "status", None) == "pass":
        _add(
            checks,
            issues,
            "prepare_from_requirement",
            "pass",
            "config and netlist bundle preparation passed",
        )
        return True
    detail = _issues_detail(getattr(result, "issues", []))
    _add(
        checks,
        issues,
        "prepare_from_requirement",
        "fail",
        detail or "project preparation failed",
    )
    return False


def _check_project_ready(
    project_root: Path,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
    warnings: list[str],
) -> None:
    try:
        result = service.check_project_ready(project_root)
    except Exception as exc:
        _add(checks, issues, "project_ready", "fail", str(exc))
        return
    if getattr(result, "status", None) == "pass":
        readiness = (
            "ready_for_continuation_or_closeout_review"
            if _has_optimizer_history(project_root)
            else getattr(result, "readiness", "ready")
        )
        _add(checks, issues, "project_ready", "pass", str(readiness))
        for warning in getattr(result, "warnings", []):
            warnings.append(str(warning))
        return
    detail = _issues_detail(getattr(result, "issues", []))
    _add(checks, issues, "project_ready", "fail", detail or "project is not ready")


def _check_continuation_artifacts(
    project_root: Path,
    checks: list[ProductDoctorCheck],
    issues: list[str],
    warnings: list[str],
) -> None:
    state_paths = [
        project_root / LEDGER_PATH,
        project_root / OPTIMIZER_STATE_PATH,
    ]
    if not _has_optimizer_history(project_root):
        detail = "no optimizer history yet; continuation is not expected before first run"
        checks.append(ProductDoctorCheck("continuation_artifacts", "warning", detail))
        warnings.append(detail)
        return

    missing = [path.relative_to(project_root).as_posix() for path in state_paths if not path.exists()]
    if missing:
        _add(
            checks,
            issues,
            "continuation_artifacts",
            "fail",
            "missing " + ", ".join(missing),
        )
        return
    _add(
        checks,
        issues,
        "continuation_artifacts",
        "pass",
        "optimizer history and continuation state are present",
    )


def _has_optimizer_history(project_root: Path) -> bool:
    optimizer_paths = [
        project_root / OPTIMIZER_REPORT_RELATIVE,
        project_root / EVALUATIONS_RELATIVE,
    ]
    return any(path.exists() for path in optimizer_paths)


def _report(
    project_root: Path,
    checks: list[ProductDoctorCheck],
    issues: list[str],
    warnings: list[str],
    structured_issues: list[Diagnostic],
    *,
    transport: dict[str, Any],
    requirement_summary: dict[str, Any],
    evaluation_matrix: dict[str, Any],
    optimizer_summary: dict[str, Any],
    resource_summary: dict[str, Any],
    dirty_state: dict[str, Any],
    optimizer_progress_summary: dict[str, Any],
    license_probe: dict[str, Any],
    write: bool,
) -> ProductDoctorReport:
    report_path = project_root / REPORT_RELATIVE if write else None
    report = ProductDoctorReport(
        status="fail" if issues else "pass",
        project_dir=str(project_root),
        checks=list(checks),
        issues=list(issues),
        warnings=list(warnings),
        structured_issues=list(structured_issues),
        transport=transport,
        requirement_summary=requirement_summary,
        evaluation_matrix=evaluation_matrix,
        optimizer_summary=optimizer_summary,
        resource_summary=resource_summary,
        dirty_state=dirty_state,
        optimizer_progress_summary=optimizer_progress_summary,
        license_probe=license_probe,
        report_path=report_path,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        payload["schema_version"] = "1.0"
        payload["report_path"] = REPORT_RELATIVE.as_posix()
        payload["structured_issues"] = [
            diagnostic.model_dump() for diagnostic in structured_issues
        ]
        report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    return report


def _add(
    checks: list[ProductDoctorCheck],
    issues: list[str],
    name: str,
    status: str,
    detail: str,
) -> None:
    checks.append(ProductDoctorCheck(name=name, status=status, detail=detail))
    if status == "fail":
        issues.append(f"{name}: {detail}")


def _issues_detail(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(issue) for issue in value if str(issue))
    if isinstance(value, str):
        return value
    return ""
