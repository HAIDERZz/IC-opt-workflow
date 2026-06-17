from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.doctor_readiness import (
    RealRunDirFacts,
    build_doctor_semantic_summaries,
    build_optimizer_progress_summary,
    is_incomplete_real_run_dir,
)
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import RemoteSshRunner, quote_remote_path
from hermes_workflow.requirement_intake import RequirementIntakeReport, parse_requirement_text
from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity
from hermes_workflow.license_probe import (
    LicenseProbeReport,
    run_license_probe_skipped,
    run_remote_license_probe,
    write_license_probe_report,
)


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
    transport: dict[str, Any]
    requirement_summary: dict[str, Any]
    evaluation_matrix: dict[str, Any]
    optimizer_summary: dict[str, Any]
    resource_summary: dict[str, Any]
    dirty_state: dict[str, Any]
    optimizer_progress_summary: dict[str, Any]
    license_probe: dict[str, Any] = None


def run_remote_doctor(
    ref: RemoteProjectRef,
    *,
    runner: RemoteSshRunner | Any | None = None,
    cadence_cshrc: PurePosixPath | str | None = None,
    cache_root: Path | None = None,
    cli_max_evals: int | None = None,
) -> RemoteDoctorReport:
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    local_report_path = cache_dir / "reports" / "ic_opt_doctor_report.json"
    local_report_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, str]] = {}
    issues: list[str] = []
    structured_issues: list[Diagnostic] = []
    requirement_sections: dict[str, Any] = {}
    transport = {
        "mode": "remote",
        "ssh_profile": ref.ssh_profile,
        "remote_project_dir": str(ref.remote_project_dir),
    }

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
        return _write_doctor(
            ref,
            ssh,
            local_report_path,
            checks,
            issues,
            structured_issues,
            transport=transport,
            requirement_sections=requirement_sections,
            cli_max_evals=cli_max_evals,
        )

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
        requirement_sections = dict(req_report.sections) if isinstance(
            req_report.sections, dict
        ) else {}
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

    # License probe: check require_license_check from requirement sections
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    license_probe_report = _check_remote_license_probe(
        ssh,
        cshrc_path,
        requirement_sections,
        checks,
        issues,
        structured_issues,
        cache_dir=cache_dir,
    )
    return _write_doctor(
        ref,
        ssh,
        local_report_path,
        checks,
        issues,
        structured_issues,
        transport=transport,
        requirement_sections=requirement_sections,
        license_probe_report=license_probe_report,
        cli_max_evals=cli_max_evals,
    )


def _check_remote_license_probe(
    ssh: Any,
    cshrc_path: PurePosixPath,
    requirement_sections: dict[str, Any],
    checks: dict[str, dict[str, str]],
    issues: list[str],
    structured_issues: list[Diagnostic],
    *,
    cache_dir: Path,
) -> LicenseProbeReport | None:
    """Run remote license probe if ``require_license_check`` is true."""
    spectre_settings = requirement_sections.get("Spectre Settings")
    require = False
    if isinstance(spectre_settings, dict):
        require = bool(spectre_settings.get("require_license_check", False))

    if not require:
        report = run_license_probe_skipped(execution_mode="remote")
        checks["license_probe"] = {
            "status": "skipped",
            "message": "require_license_check is false",
        }
        write_license_probe_report(cache_dir, report)
        return report

    try:
        report = run_remote_license_probe(ssh, cshrc_path)
    except Exception as exc:
        report = LicenseProbeReport(
            status="fail",
            execution_mode="remote",
            require_license_check=True,
            issues=[f"remote license probe raised exception: {exc}"],
        )

    write_license_probe_report(cache_dir, report)

    if report.status == "pass":
        checks["license_probe"] = {
            "status": "pass",
            "message": "remote license environment probe passed",
        }
    else:
        detail = "; ".join(report.issues) if report.issues else "remote license environment probe failed"
        checks["license_probe"] = {"status": "fail", "message": detail}
        issues.append(f"license_probe: {detail}")
        structured_issues.append(
            Diagnostic(
                code="LICENSE_PROBE_FAILED",
                severity=DiagnosticSeverity.ERROR,
                stage="remote_ssh",
                component="remote_doctor",
                message="Remote license probe failed",
                detail=detail,
                likely_cause="Spectre or license server not available after sourcing cadence cshrc",
                recommended_action="Verify cadence_env.csh sets up spectre and license paths correctly on the remote host",
                evidence=[str(cshrc_path)],
            )
        )
    return report


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

    if req_report.workflow_mode == "fix_run":
        checks["parallel_jobs"] = {
            "status": "warn",
            "message": (
                f"remote fix-run child_parallelism (Spectre Settings.parallel_jobs)={parallel_jobs} is high; "
                "this is the scheduler-level number of testbench/corner child runs inside one fixed point; "
                "fixed points remain serial; start around 4-8 to avoid SSH server limits"
            ),
        }
    else:
        checks["parallel_jobs"] = {
            "status": "warn",
            "message": (
                f"remote candidate_parallelism (Spectre Settings.parallel_jobs)={parallel_jobs} is high; "
                "this is the scheduler-level number of candidates running concurrently, "
                "not a Spectre child-runtime setting; "
                "normal remote multi-testbench runs should start around 4-8 to avoid SSH server limits"
            ),
        }
    if structured_issues is not None:
        if req_report.workflow_mode == "fix_run":
            message = (
                f"remote fix-run child_parallelism (Spectre Settings.parallel_jobs)={parallel_jobs} is high."
            )
            detail = (
                "fix-run child_parallelism is the scheduler-level number of "
                "testbench/corner child runs inside one fixed point; fixed points remain serial. "
                "High values can increase SSH connection pressure and may trigger remote transport errors."
            )
            likely_cause = (
                "Remote fix-run child concurrency exceeds typical safe ranges for multi-testbench runs."
            )
            recommended_action = (
                "Set Spectre Settings.parallel_jobs (fix-run child_parallelism) to values around "
                "4 to 8 for remote fix-run projects."
            )
        else:
            message = (
                f"remote candidate_parallelism (Spectre Settings.parallel_jobs)={parallel_jobs} is high."
            )
            detail = (
                "candidate_parallelism is the scheduler-level number of optimizer candidates "
                "evaluated concurrently; high values can increase SSH connection pressure and may "
                "trigger remote transport errors. Testbenches/corners inside one candidate always run serially."
            )
            likely_cause = (
                "Remote candidate concurrency exceeds typical safe ranges for multi-testbench runs."
            )
            recommended_action = (
                "Set Spectre Settings.parallel_jobs (candidate_parallelism) to values around 4 to 8 "
                "for remote multi-testbench runs."
            )
        structured_issues.append(
            Diagnostic(
                code="REMOTE_PARALLELISM_HIGH",
                severity=DiagnosticSeverity.WARN,
                stage="remote_ssh",
                component="remote_doctor",
                message=message,
                detail=detail,
                likely_cause=likely_cause,
                recommended_action=recommended_action,
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
    *,
    transport: dict[str, Any],
    requirement_sections: dict[str, Any],
    cli_max_evals: int | None,
    license_probe_report: LicenseProbeReport | None = None,
) -> RemoteDoctorReport:
    requirement_summary, evaluation_matrix, optimizer_summary, resource_summary, semantic_diagnostics = (
        build_doctor_semantic_summaries(
            requirement_sections, cli_max_evals=cli_max_evals
        )
    )
    for diagnostic in semantic_diagnostics:
        structured_issues.append(diagnostic)
        if diagnostic.severity is DiagnosticSeverity.ERROR:
            message = diagnostic.detail or diagnostic.message
            checks[diagnostic.code.lower()] = {
                "status": "fail",
                "message": message,
            }
            issues.append(f"{diagnostic.code}: {message}")
    dirty_state, dirty_diagnostics = _build_remote_dirty_state(ref, ssh)
    structured_issues.extend(dirty_diagnostics)
    cache_dir = local_report_path.parent.parent
    requirement_max_evaluations: int | None = None
    if isinstance(optimizer_summary, dict):
        candidate = optimizer_summary.get("max_evaluations")
        if isinstance(candidate, int):
            requirement_max_evaluations = candidate
    optimizer_progress_summary, progress_diagnostics = build_optimizer_progress_summary(
        cache_dir,
        requirement_max_evaluations=requirement_max_evaluations,
    )
    for diagnostic in progress_diagnostics:
        structured_issues.append(diagnostic)
        if diagnostic.severity is DiagnosticSeverity.ERROR:
            message = diagnostic.detail or diagnostic.message
            checks[diagnostic.code.lower()] = {
                "status": "fail",
                "message": message,
            }
            issues.append(f"{diagnostic.code}: {message}")
    status = "pass" if not issues else "fail"
    license_probe_dict = license_probe_report.to_dict() if license_probe_report else {}
    payload = {
        "schema_version": "1.0",
        "status": status,
        "ssh_profile": ref.ssh_profile,
        "remote_project_dir": str(ref.remote_project_dir),
        "checks": checks,
        "issues": issues,
        "structured_issues": [diagnostic.model_dump() for diagnostic in structured_issues],
        "transport": transport,
        "requirement_summary": requirement_summary,
        "evaluation_matrix": evaluation_matrix,
        "optimizer_summary": optimizer_summary,
        "resource_summary": resource_summary,
        "dirty_state": dirty_state,
        "optimizer_progress_summary": optimizer_progress_summary,
        "license_probe": license_probe_dict,
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
        transport=transport,
        requirement_summary=requirement_summary,
        evaluation_matrix=evaluation_matrix,
        optimizer_summary=optimizer_summary,
        resource_summary=resource_summary,
        dirty_state=dirty_state,
        optimizer_progress_summary=optimizer_progress_summary,
        license_probe=license_probe_dict,
    )


def _build_remote_dirty_state(
    ref: RemoteProjectRef,
    ssh: Any,
) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Inspect remote project for dirty/interrupted state via SSH probes.

    Doctor only checks file presence; it does not download remote artifacts.
    Optimizer history alone is not a warning. Candidate run directories that
    lack any candidate-level completion artifact are surfaced as
    INCOMPLETE_REAL_RUN warnings via the shared classifier.
    """
    project = ref.remote_project_dir
    diagnostics: list[Diagnostic] = []
    has_runs = _remote_path_exists(ssh, project / "runs" / "real", kind="dir")
    incomplete_runs: list[str] = []
    if has_runs:
        runs_root = project / "runs" / "real"
        listing = ssh.run(
            f"ls -1 {quote_remote_path(runs_root)} 2>/dev/null"
        )
        if listing.return_code == 0:
            for name in (line.strip() for line in listing.stdout.splitlines()):
                if not name:
                    continue
                run_dir = runs_root / name
                facts = _remote_real_run_dir_facts(ssh, run_dir)
                if is_incomplete_real_run_dir(facts):
                    incomplete_runs.append(name)
    has_incomplete_real_run = bool(incomplete_runs)
    if has_incomplete_real_run:
        for name in incomplete_runs:
            diagnostics.append(
                Diagnostic(
                    code="INCOMPLETE_REAL_RUN",
                    severity=DiagnosticSeverity.WARN,
                    stage="doctor",
                    component="remote_doctor",
                    message=f"Incomplete real run directory detected: {name}.",
                    detail=(
                        "The remote candidate run directory has neither a "
                        "candidate-level result manifest "
                        "(result_manifest.json or "
                        "metrics/metric_result_manifest.json) nor a legacy "
                        "optimizer-level report; the previous run may have "
                        "been interrupted before finalizing."
                    ),
                    likely_cause=(
                        "The previous remote real candidate evaluation did "
                        "not finalize before exiting."
                    ),
                    recommended_action=(
                        "Inspect the remote candidate run directory before "
                        "starting a fresh real run."
                    ),
                    evidence=[f"runs/real/{name}"],
                )
            )
    has_execution_package = _remote_path_exists(
        ssh, project / "execution_package", kind="dir"
    )
    has_optimizer_state = _remote_path_exists(
        ssh, project / "state" / "optimizer_state.json", kind="file"
    )
    has_optimizer_run_report = _remote_path_exists(
        ssh, project / "reports" / "optimizer_run_report.json", kind="file"
    )
    has_optimizer_evaluations = _remote_path_exists(
        ssh, project / "reports" / "optimizer_evaluations.jsonl", kind="file"
    )
    summary = {
        "has_runs": has_runs,
        "has_incomplete_real_run": has_incomplete_real_run,
        "has_execution_package": has_execution_package,
        "has_optimizer_state": has_optimizer_state,
        "has_optimizer_run_report": has_optimizer_run_report,
        "has_optimizer_evaluations": has_optimizer_evaluations,
    }
    return summary, diagnostics


def _remote_path_exists(ssh: Any, remote_path: PurePosixPath, *, kind: str) -> bool:
    flag = "-d" if kind == "dir" else "-f"
    try:
        result = ssh.run(f"test {flag} {quote_remote_path(remote_path)}")
    except Exception:
        return False
    return result.return_code == 0


def _remote_real_run_dir_facts(
    ssh: Any, run_dir: PurePosixPath
) -> RealRunDirFacts:
    """Probe one remote candidate run directory and return shared facts.

    Mirrors :func:`hermes_workflow.doctor_readiness._local_real_run_dir_facts`
    so local and remote doctor use the same classification semantics.
    """
    return RealRunDirFacts(
        name=run_dir.name,
        has_result_manifest=_remote_path_exists(
            ssh, run_dir / "result_manifest.json", kind="file"
        ),
        has_metric_result_manifest=_remote_path_exists(
            ssh,
            run_dir / "metrics" / "metric_result_manifest.json",
            kind="file",
        ),
        has_optimizer_run_report=(
            _remote_path_exists(
                ssh,
                run_dir / "reports" / "optimizer_run_report.json",
                kind="file",
            )
            or _remote_path_exists(
                ssh, run_dir / "optimizer_run_report.json", kind="file"
            )
        ),
        has_optimizer_completion_report=(
            _remote_path_exists(
                ssh,
                run_dir / "reports" / "optimizer_completion_report.json",
                kind="file",
            )
            or _remote_path_exists(
                ssh,
                run_dir / "optimizer_completion_report.json",
                kind="file",
            )
        ),
        has_candidate_marker=(
            _remote_path_exists(
                ssh, run_dir / "candidate_request.json", kind="file"
            )
            or _remote_path_exists(
                ssh, run_dir / "candidate.json", kind="file"
            )
        ),
    )
