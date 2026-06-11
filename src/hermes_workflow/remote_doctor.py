from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import RemoteSshRunner, quote_remote_path
from hermes_workflow.requirement_intake import RequirementIntakeReport, parse_requirement_text
from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity


@dataclass(frozen=True)
class RemoteDoctorReport:
    status: str
    ssh_profile: str
    remote_project_dir: str
    remote_report_path: str
    local_report_path: Path
    checks: dict[str, dict[str, str]]
    issues: list[str]
    structured_issues: list[Diagnostic]


def run_remote_doctor(
    ref: RemoteProjectRef,
    *,
    runner: RemoteSshRunner | Any | None = None,
    cadence_cshrc: PurePosixPath | str | None = None,
    cache_root: Path | None = None,
) -> RemoteDoctorReport:
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    local_report_path = cache_dir / "reports" / "ic_opt_doctor_report.json"
    local_report_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, str]] = {}
    issues: list[str] = []
    structured_issues: list[Diagnostic] = []

    _record_command_check(
        checks,
        issues,
        structured_issues,
        "ssh",
        ssh.run("true"),
        f"verify: ssh {ref.ssh_profile} true",
        evidence=[str(ref.remote_project_dir)],
        failure_code="SSH_LOGIN_FAILED",
        failure_detail=f"Unable to authenticate or execute remote commands with ssh profile {ref.ssh_profile}.",
    )
    if issues:
        return _write_doctor(ref, ssh, local_report_path, checks, issues, structured_issues)

    _record_command_check(
        checks,
        issues,
        structured_issues,
        "remote_project_dir",
        ssh.run(f"test -d {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory exists",
        evidence=[str(ref.remote_project_dir)],
        failure_code="REMOTE_PROJECT_MISSING",
        failure_detail=f"Remote project directory {ref.remote_project_dir} is missing.",
        failure_action="Create the project directory on the remote host.",
    )
    _record_command_check(
        checks,
        issues,
        structured_issues,
        "remote_project_writable",
        ssh.run(f"test -w {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory is writable",
        evidence=[str(ref.remote_project_dir)],
        failure_code="REMOTE_PROJECT_NOT_WRITABLE",
        failure_detail=(
            f"Remote project directory {ref.remote_project_dir} is not writable."
        ),
        failure_action="Fix permissions on the remote project directory.",
    )

    requirement_text = _read_required_remote_text(
        ssh,
        ref.remote_project_dir / "opt_requirement.md",
        checks,
        issues,
        "opt_requirement",
    )
    constraints_text = _read_optional_remote_text(
        ssh, ref.remote_project_dir / "constraints.md"
    )
    if requirement_text is not None:
        req_report = parse_requirement_text(
            requirement_text,
            constraints_text=constraints_text,
            maestro_input_exists=lambda path: ssh.run(
                f"test -f {quote_remote_path(path)}"
            ).return_code
            == 0,
        )
        checks["requirement"] = {
            "status": req_report.status,
            "message": "; ".join(req_report.issues) if req_report.issues else "requirement is valid",
        }
        issues.extend(req_report.issues)
        structured_issues.extend(req_report.structured_issues)
        _record_parallel_jobs_warning(
            checks,
            req_report,
            structured_issues=structured_issues,
            evidence=[str(ref.remote_project_dir / "opt_requirement.md")],
        )

    cshrc_path = (
        PurePosixPath(str(cadence_cshrc))
        if cadence_cshrc is not None
        else ref.remote_project_dir / "cadence_env.csh"
    )
    _record_command_check(
        checks,
        issues,
        structured_issues,
        "cadence_cshrc",
        ssh.run(f"test -f {quote_remote_path(cshrc_path)}"),
        f"cadence cshrc exists: {cshrc_path}",
        evidence=[str(cshrc_path)],
        failure_code="CADENCE_CSHRC_MISSING",
        failure_detail=f"Required cadence cshrc is missing at {cshrc_path}.",
        failure_action=(
            "Provide --cadence-cshrc path or create cadence_env.csh in "
            "the remote project root."
        ),
    )
    _record_command_check(
        checks,
        issues,
        structured_issues,
        "spectre_ocean",
        ssh.run(
            "csh -fc "
            + quote_remote_path(
                f"source {quote_remote_path(cshrc_path)}; which spectre; which ocean"
            )
        ),
        "spectre and ocean are available after sourcing cshrc",
        evidence=[str(cshrc_path)],
        failure_code="CADENCE_TOOL_MISSING",
        failure_detail="Unable to locate spectre or ocean after sourcing cadence cshrc.",
        failure_action=(
            "Update cadence_env.csh so which spectre and which ocean resolve on the remote host."
        ),
    )
    return _write_doctor(ref, ssh, local_report_path, checks, issues, structured_issues)


def _record_parallel_jobs_warning(
    checks: dict[str, dict[str, str]],
    req_report: RequirementIntakeReport,
    *,
    structured_issues: list[Diagnostic] | None = None,
    evidence: list[str] | None = None,
) -> None:
    spectre = req_report.sections.get("Spectre Settings")
    if not isinstance(spectre, dict):
        return

    parallel_jobs = spectre.get("parallel_jobs")
    if not isinstance(parallel_jobs, int) or parallel_jobs <= 8:
        return

    checks["parallel_jobs"] = {
        "status": "warn",
        "message": (
            f"remote parallel_jobs={parallel_jobs} is high; "
            "normal remote multi-testbench runs should start around 4-8 to avoid SSH server limits"
        ),
    }
    if structured_issues is not None:
        structured_issues.append(
            Diagnostic(
                code="REMOTE_PARALLELISM_HIGH",
                severity=DiagnosticSeverity.WARN,
                stage="remote_ssh",
                component="remote_doctor",
                message=f"remote parallel_jobs={parallel_jobs} is high.",
                detail=(
                    "High parallel_jobs values can increase SSH connection pressure and may "
                    "trigger remote transport errors."
                ),
                likely_cause=(
                    "Remote candidate concurrency exceeds typical safe ranges for multi-testbench runs."
                ),
                recommended_action=(
                    "Try --parallel-jobs values around 4 to 8 for remote multi-testbench runs."
                ),
                evidence=(evidence or []),
            )
        )


def _record_command_check(
    checks: dict[str, dict[str, str]],
    issues: list[str],
    structured_issues: list[Diagnostic],
    name: str,
    result: Any,
    description: str,
    evidence: list[str] | None = None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
    failure_action: str | None = None,
) -> None:
    if result.return_code == 0:
        checks[name] = {"status": "pass", "message": description}
    else:
        message = f"{description} failed: {result.stderr.strip()}"
        checks[name] = {"status": "fail", "message": message}
        issues.append(message)
        if failure_code is not None:
            structured_issues.append(
                Diagnostic(
                    code=failure_code,
                    severity=DiagnosticSeverity.ERROR,
                    stage="remote_ssh",
                    component="remote_doctor",
                    message=description,
                    detail=failure_detail or message,
                    likely_cause=message,
                    recommended_action=(
                        failure_action
                        or "Retry doctor after fixing the remote setup."
                    ),
                    evidence=evidence or [name],
                )
            )


def _read_required_remote_text(
    ssh: Any,
    remote_path: PurePosixPath,
    checks: dict[str, dict[str, str]],
    issues: list[str],
    check_name: str,
) -> str | None:
    try:
        text = ssh.read_text(remote_path)
        checks[check_name] = {"status": "pass", "message": f"{remote_path} exists"}
        return text
    except Exception as exc:
        message = f"{remote_path} is missing or unreadable: {exc}"
        checks[check_name] = {"status": "fail", "message": message}
        issues.append(message)
        return None


def _read_optional_remote_text(
    ssh: Any,
    remote_path: PurePosixPath,
) -> str | None:
    try:
        return ssh.read_text(remote_path)
    except Exception:
        return None


def _write_doctor(
    ref: RemoteProjectRef,
    ssh: Any,
    local_report_path: Path,
    checks: dict[str, dict[str, str]],
    issues: list[str],
    structured_issues: list[Diagnostic],
) -> RemoteDoctorReport:
    status = "pass" if not issues else "fail"
    payload = {
        "schema_version": "1.0",
        "status": status,
        "ssh_profile": ref.ssh_profile,
        "remote_project_dir": str(ref.remote_project_dir),
        "checks": checks,
        "issues": issues,
        "structured_issues": [diagnostic.model_dump() for diagnostic in structured_issues],
    }
    report_json = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    # Write to remote
    ssh.mkdir(ref.remote_reports_dir)
    ssh.write_text(ref.remote_doctor_report, report_json)

    # Write to local cache
    local_report_path.parent.mkdir(parents=True, exist_ok=True)
    local_report_path.write_text(report_json, encoding="utf-8")

    return RemoteDoctorReport(
        status=status,
        ssh_profile=ref.ssh_profile,
        remote_project_dir=str(ref.remote_project_dir),
        remote_report_path=str(ref.remote_doctor_report),
        local_report_path=local_report_path,
        checks=checks,
        issues=issues,
        structured_issues=structured_issues,
    )
