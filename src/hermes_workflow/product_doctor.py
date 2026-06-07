from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.optimizer_artifacts import REPORT_RELATIVE as OPTIMIZER_REPORT_RELATIVE
from hermes_workflow.project_readiness import check_project_ready
from hermes_workflow.real_result_record import LEDGER_PATH, OPTIMIZER_STATE_PATH
from hermes_workflow.requirement_intake import (
    check_requirement,
    prepare_from_requirement,
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
    report_path: Path | None = None


@dataclass(frozen=True)
class ProductDoctorServices:
    check_requirement: Callable[[Path], Any] = check_requirement
    prepare_from_requirement: Callable[[Path], Any] = prepare_from_requirement
    check_project_ready: Callable[[Path], Any] = check_project_ready
    check_toolchain_environment: Callable[..., dict[str, Any]] = (
        check_toolchain_environment
    )


def run_product_doctor(
    project_dir: str | Path,
    *,
    cadence_cshrc: Path | None,
    openbox_venv: Path | None = None,
    services: ProductDoctorServices | None = None,
) -> ProductDoctorReport:
    project_root = Path(project_dir)
    service = services or ProductDoctorServices()
    checks: list[ProductDoctorCheck] = []
    issues: list[str] = []
    warnings: list[str] = []

    if not project_root.exists():
        _add(checks, issues, "project_directory", "fail", "project directory is missing")
        return _report(project_root, checks, issues, warnings, write=False)
    if not project_root.is_dir():
        _add(checks, issues, "project_directory", "fail", "project path is not a directory")
        return _report(project_root, checks, issues, warnings, write=False)
    _add(checks, issues, "project_directory", "pass", "project directory exists")

    requirement_ok = _check_requirement(project_root, service, checks, issues)
    cadence_ok = _check_cadence_cshrc(cadence_cshrc, checks, issues)
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
    return _report(project_root, checks, issues, warnings, write=True)


def _check_requirement(
    project_root: Path,
    service: ProductDoctorServices,
    checks: list[ProductDoctorCheck],
    issues: list[str],
) -> bool:
    try:
        result = service.check_requirement(project_root)
    except Exception as exc:
        _add(checks, issues, "requirement", "fail", str(exc))
        return False
    if getattr(result, "status", None) == "pass":
        _add(checks, issues, "requirement", "pass", "opt_requirement.md parsed")
        return True
    detail = _issues_detail(getattr(result, "issues", []))
    _add(checks, issues, "requirement", "fail", detail or "requirement intake failed")
    return False


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
        readiness = getattr(result, "readiness", "ready")
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
    optimizer_paths = [
        project_root / OPTIMIZER_REPORT_RELATIVE,
        project_root / EVALUATIONS_RELATIVE,
    ]
    state_paths = [
        project_root / LEDGER_PATH,
        project_root / OPTIMIZER_STATE_PATH,
    ]
    any_optimizer_history = any(path.exists() for path in optimizer_paths)
    if not any_optimizer_history:
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


def _report(
    project_root: Path,
    checks: list[ProductDoctorCheck],
    issues: list[str],
    warnings: list[str],
    *,
    write: bool,
) -> ProductDoctorReport:
    report_path = project_root / REPORT_RELATIVE if write else None
    report = ProductDoctorReport(
        status="fail" if issues else "pass",
        project_dir=str(project_root),
        checks=list(checks),
        issues=list(issues),
        warnings=list(warnings),
        report_path=report_path,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        payload["schema_version"] = "1.0"
        payload["report_path"] = REPORT_RELATIVE.as_posix()
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
