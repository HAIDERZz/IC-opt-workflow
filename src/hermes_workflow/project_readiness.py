from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.validate import validate_project_files


REPORT_RELATIVE = Path("reports/project_readiness_report.json")
REQUIRED_CONFIGS = (
    "project_config.yaml",
    "variables.yaml",
    "metrics.yaml",
    "spectre.yaml",
    "optimizer.yaml",
)
FIX_RUN_REQUIRED_CONFIGS = (
    "project_config.yaml",
    "variables.yaml",
    "spectre.yaml",
    "fixed_points.yaml",
)


@dataclass(frozen=True)
class ProjectReadinessReport:
    status: str
    readiness: str
    core_ready: bool
    final_summary_ready: bool
    checks: list[dict[str, str]]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None


def check_project_ready(project_dir: str | Path) -> ProjectReadinessReport:
    project_root = Path(project_dir)
    checks: list[dict[str, str]] = []
    issues: list[str] = []
    warnings: list[str] = []

    if not project_root.exists():
        _add_check(checks, "project_directory", "fail", "project directory is missing")
        issues.append("project directory is missing")
        return _write_report(project_root, checks, issues, warnings)
    _add_check(checks, "project_directory", "pass", "project directory exists")

    _check_requirement(project_root, checks, issues)
    _check_configs(project_root, checks, issues)
    _check_contract_validation(project_root, checks, issues)
    _check_netlists(project_root, checks, issues)
    _check_final_reports(project_root, checks, warnings)

    return _write_report(project_root, checks, issues, warnings)


def _check_requirement(
    project_root: Path,
    checks: list[dict[str, str]],
    issues: list[str],
) -> None:
    requirement_files = sorted(project_root.glob("opt_requirement*.md"))
    if not requirement_files:
        _add_check(checks, "requirement", "fail", "no opt_requirement*.md file found")
        issues.append("no opt_requirement*.md file found")
        return
    names = ", ".join(path.name for path in requirement_files)
    _add_check(checks, "requirement", "pass", f"found {names}")


def _check_configs(
    project_root: Path,
    checks: list[dict[str, str]],
    issues: list[str],
) -> None:
    workflow_mode = _workflow_mode(project_root)
    required_configs = (
        FIX_RUN_REQUIRED_CONFIGS
        if workflow_mode == "fix_run"
        else REQUIRED_CONFIGS
    )
    missing: list[str] = []
    for file_name in required_configs:
        rel_path = Path("config") / file_name
        if not (project_root / rel_path).exists():
            missing.append(rel_path.as_posix())
            issues.append(f"missing required config file: {rel_path.as_posix()}")
    if workflow_mode == "fix_run" and not (
        (project_root / "config" / "metrics.yaml").exists()
        or (project_root / "config" / "waveform_exports.yaml").exists()
    ):
        rel_path = "config/metrics.yaml or config/waveform_exports.yaml"
        missing.append(rel_path)
        issues.append(f"missing required config file: {rel_path}")
    if missing:
        _add_check(
            checks,
            "config_files",
            "fail",
            "missing " + ", ".join(missing),
        )
        return
    _add_check(checks, "config_files", "pass", "required config files are present")


def _workflow_mode(project_root: Path) -> str:
    if (project_root / "config" / "fixed_points.yaml").exists():
        return "fix_run"
    workflow_path = project_root / "config" / "workflow.yaml"
    if not workflow_path.exists():
        return "optimize"
    try:
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return "optimize"
    if not isinstance(payload, dict):
        return "optimize"
    mode = payload.get("mode")
    return str(mode) if mode is not None else "optimize"


def _check_contract_validation(
    project_root: Path,
    checks: list[dict[str, str]],
    issues: list[str],
) -> None:
    report = validate_project_files(project_root)
    if report.ok:
        _add_check(checks, "contract_validation", "pass", "contract validation passed")
        return
    _add_check(checks, "contract_validation", "fail", "contract validation failed")
    issues.extend(report.format().splitlines())


def _check_netlists(
    project_root: Path,
    checks: list[dict[str, str]],
    issues: list[str],
) -> None:
    testbench_ids = _testbench_ids(project_root)
    if testbench_ids:
        missing: list[str] = []
        for testbench_id in testbench_ids:
            base = Path("netlists") / "testbenches" / testbench_id
            for rel_path in (
                base / "exported" / "input.scs",
                base / "templates" / "template.scs",
            ):
                if not (project_root / rel_path).exists():
                    missing.append(rel_path.as_posix())
        if missing:
            _add_check(
                checks,
                "multi_testbench_netlists",
                "fail",
                "missing " + ", ".join(missing),
            )
            issues.extend(f"missing netlist artifact: {path}" for path in missing)
            return
        _add_check(
            checks,
            "multi_testbench_netlists",
            "pass",
            f"{len(testbench_ids)} testbench netlist bundles are ready",
        )
        return

    missing_single = [
        rel_path.as_posix()
        for rel_path in (
            Path("netlists/exported/input.scs"),
            Path("netlists/templates/template.scs"),
        )
        if not (project_root / rel_path).exists()
    ]
    if missing_single:
        _add_check(checks, "single_testbench_netlist", "fail", "missing " + ", ".join(missing_single))
        issues.extend(f"missing netlist artifact: {path}" for path in missing_single)
        return
    _add_check(checks, "single_testbench_netlist", "pass", "single testbench netlist is ready")


def _check_final_reports(
    project_root: Path,
    checks: list[dict[str, str]],
    warnings: list[str],
) -> None:
    final_summary = project_root / "reports" / "optimizer_final_summary.json"
    if not final_summary.exists():
        _add_check(
            checks,
            "optimizer_final_summary",
            "warning",
            "final optimizer summary is not present yet",
        )
        warnings.append("final optimizer summary is not present yet")
        return
    payload = _load_json(final_summary)
    if payload.get("status") == "pass":
        accepted = payload.get("accepted_run_id") or "unknown"
        _add_check(
            checks,
            "optimizer_final_summary",
            "pass",
            f"final optimizer summary accepts {accepted}",
        )
        return
    _add_check(
        checks,
        "optimizer_final_summary",
        "warning",
        "final optimizer summary is present but not passing",
    )
    warnings.append("final optimizer summary is present but not passing")


def _write_report(
    project_root: Path,
    checks: list[dict[str, str]],
    issues: list[str],
    warnings: list[str],
) -> ProjectReadinessReport:
    final_summary_ready = any(
        check["name"] == "optimizer_final_summary" and check["status"] == "pass"
        for check in checks
    )
    core_ready = not issues
    if not core_ready:
        readiness = "needs_setup"
    elif final_summary_ready:
        readiness = "ready_for_closeout_review"
    else:
        readiness = "ready_for_first_run"

    report = ProjectReadinessReport(
        status="pass" if core_ready else "fail",
        readiness=readiness,
        core_ready=core_ready,
        final_summary_ready=final_summary_ready,
        checks=checks,
        issues=issues,
        warnings=warnings,
        report_path=project_root / REPORT_RELATIVE,
    )
    report_path = project_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _testbench_ids(project_root: Path) -> list[str]:
    payload = _load_yaml(project_root / "config" / "testbenches.yaml")
    testbenches = payload.get("testbenches")
    if not isinstance(testbenches, list):
        return []
    ids: list[str] = []
    for entry in testbenches:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.append(entry["id"])
    return ids


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _add_check(
    checks: list[dict[str, str]],
    name: str,
    status: str,
    detail: str,
) -> None:
    checks.append({"name": name, "status": status, "detail": detail})
