from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import RemoteSshRunner, quote_remote_path
from hermes_workflow.requirement_intake import parse_requirement_text


@dataclass(frozen=True)
class RemoteDoctorReport:
    status: str
    ssh_profile: str
    remote_project_dir: str
    remote_report_path: str
    local_report_path: Path
    checks: dict[str, dict[str, str]]
    issues: list[str]


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

    _record_command_check(
        checks, issues, "ssh", ssh.run("true"),
        f"verify: ssh {ref.ssh_profile} true",
    )
    if issues:
        return _write_doctor(ref, ssh, local_report_path, checks, issues)

    _record_command_check(
        checks,
        issues,
        "remote_project_dir",
        ssh.run(f"test -d {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory exists",
    )
    _record_command_check(
        checks,
        issues,
        "remote_project_writable",
        ssh.run(f"test -w {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory is writable",
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

    cshrc_path = (
        PurePosixPath(str(cadence_cshrc))
        if cadence_cshrc is not None
        else ref.remote_project_dir / "cadence_env.csh"
    )
    _record_command_check(
        checks,
        issues,
        "cadence_cshrc",
        ssh.run(f"test -f {quote_remote_path(cshrc_path)}"),
        f"cadence cshrc exists: {cshrc_path}",
    )
    _record_command_check(
        checks,
        issues,
        "spectre_ocean",
        ssh.run(
            "csh -fc "
            + quote_remote_path(
                f"source {cshrc_path}; which spectre; which ocean"
            )
        ),
        "spectre and ocean are available after sourcing cshrc",
    )
    return _write_doctor(ref, ssh, local_report_path, checks, issues)


def _record_command_check(
    checks: dict[str, dict[str, str]],
    issues: list[str],
    name: str,
    result: Any,
    description: str,
) -> None:
    if result.return_code == 0:
        checks[name] = {"status": "pass", "message": description}
    else:
        message = f"{description} failed: {result.stderr.strip()}"
        checks[name] = {"status": "fail", "message": message}
        issues.append(message)


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
) -> RemoteDoctorReport:
    status = "pass" if not issues else "fail"
    payload = {
        "schema_version": "1.0",
        "status": status,
        "ssh_profile": ref.ssh_profile,
        "remote_project_dir": str(ref.remote_project_dir),
        "checks": checks,
        "issues": issues,
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
    )
