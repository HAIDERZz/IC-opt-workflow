"""Run retention policy core for local and remote candidate run directories.

Policy fields (`keep_failed_runs`, `keep_successful_runs`) live under the
validated Spectre Settings in `opt_requirement.md`. This module reads those
settings, classifies a candidate's outcome as ``successful`` or ``failed``, and
deletes only the candidate's own real-run directory when the policy says so.
A per-run decision report is always written under ``state/run_retention/``.

Constraint-failed candidates with valid metric scalars are SUCCESSFUL
observations for retention purposes; the optimizer was able to use them.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.real_run import RUN_ID_RE
from hermes_workflow.remote_ssh import quote_remote_path
from hermes_workflow.validate import assert_valid_project


SCHEMA_VERSION = "1.0"
DECISION_REPORT_DIR = "state/run_retention"
POLICY_SOURCE = "Spectre Settings"
_REAL_RUN_ROOT = "runs/real"

# Local action values.
_LOCAL_KEPT = "kept"
_LOCAL_DELETED = "deleted"
_LOCAL_MISSING = "missing"
_LOCAL_FAILED = "failed"

# Remote action values.
_REMOTE_KEPT = "kept"
_REMOTE_DELETED = "deleted"
_REMOTE_MISSING = "missing"
_REMOTE_FAILED = "failed"
_REMOTE_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class RunRetentionPolicy:
    keep_failed_runs: bool
    keep_successful_runs: bool
    source: str = POLICY_SOURCE


@dataclass(frozen=True)
class RunRetentionDecision:
    schema_version: str
    run_id: str
    candidate_id: str | None
    run_status: str
    policy_source: str
    keep_failed_runs: bool
    keep_successful_runs: bool
    local_action: str
    remote_action: str
    local_run_dir: str
    remote_run_dir: str | None
    issues: list[str] = field(default_factory=list)
    decided_at_utc: str = ""


def load_run_retention_policy(project_dir: Path) -> RunRetentionPolicy:
    """Read the retention policy from the validated requirement bundle."""
    bundle = assert_valid_project(Path(project_dir))
    spectre = bundle.spectre.spectre
    return RunRetentionPolicy(
        keep_failed_runs=bool(spectre.keep_failed_runs),
        keep_successful_runs=bool(spectre.keep_successful_runs),
    )


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"unsafe run_id rejected by run retention: {run_id!r}; "
            f"expected pattern matching {RUN_ID_RE.pattern}"
        )


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_run_dir_for(project_dir: Path, run_id: str) -> Path:
    return Path(project_dir) / _REAL_RUN_ROOT / run_id


def _decision_report_path(project_dir: Path, run_id: str) -> Path:
    return Path(project_dir) / DECISION_REPORT_DIR / f"{run_id}.json"


def _decision_to_payload(decision: RunRetentionDecision) -> dict[str, Any]:
    return {
        "schema_version": decision.schema_version,
        "run_id": decision.run_id,
        "candidate_id": decision.candidate_id,
        "run_status": decision.run_status,
        "policy_source": decision.policy_source,
        "keep_failed_runs": decision.keep_failed_runs,
        "keep_successful_runs": decision.keep_successful_runs,
        "local_action": decision.local_action,
        "remote_action": decision.remote_action,
        "local_run_dir": decision.local_run_dir,
        "remote_run_dir": decision.remote_run_dir,
        "issues": list(decision.issues),
        "decided_at_utc": decision.decided_at_utc,
    }


def _payload_to_decision(payload: dict[str, Any]) -> RunRetentionDecision:
    return RunRetentionDecision(
        schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
        run_id=str(payload["run_id"]),
        candidate_id=payload.get("candidate_id"),
        run_status=str(payload["run_status"]),
        policy_source=str(payload.get("policy_source", POLICY_SOURCE)),
        keep_failed_runs=bool(payload["keep_failed_runs"]),
        keep_successful_runs=bool(payload["keep_successful_runs"]),
        local_action=str(payload["local_action"]),
        remote_action=str(payload["remote_action"]),
        local_run_dir=str(payload["local_run_dir"]),
        remote_run_dir=payload.get("remote_run_dir"),
        issues=list(payload.get("issues") or []),
        decided_at_utc=str(payload.get("decided_at_utc", "")),
    )


def _write_decision_report(project_dir: Path, decision: RunRetentionDecision) -> None:
    report_path = _decision_report_path(project_dir, decision.run_id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _decision_to_payload(decision)
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_existing_decision(
    project_dir: Path, run_id: str
) -> RunRetentionDecision | None:
    path = _decision_report_path(project_dir, run_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _payload_to_decision(payload)


def apply_local_run_retention(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None,
    run_succeeded: bool,
    policy: RunRetentionPolicy | None = None,
    now_utc: str | None = None,
) -> RunRetentionDecision:
    """Apply retention to the local candidate run directory and write a decision.

    Reads any existing decision report (e.g. one written by
    ``apply_remote_run_retention`` when remote retention runs first) and
    preserves its ``remote_action``, ``remote_run_dir``, and prior ``issues``.
    Falls back to a fresh ``remote_action="not_applicable"`` decision when no
    earlier report exists.
    """
    project_dir = Path(project_dir)
    _validate_run_id(run_id)

    resolved_policy = policy or load_run_retention_policy(project_dir)
    local_run_dir = _local_run_dir_for(project_dir, run_id)
    run_status = "successful" if run_succeeded else "failed"
    keep_for_status = (
        resolved_policy.keep_successful_runs
        if run_succeeded
        else resolved_policy.keep_failed_runs
    )

    new_issues: list[str] = []
    if not local_run_dir.exists():
        local_action = _LOCAL_MISSING
    elif keep_for_status:
        local_action = _LOCAL_KEPT
    else:
        try:
            shutil.rmtree(local_run_dir)
            local_action = _LOCAL_DELETED
        except Exception as exc:  # noqa: BLE001 — surface any deletion failure.
            local_action = _LOCAL_FAILED
            new_issues.append(
                f"local rmtree of {local_run_dir} failed: {exc}"
            )

    existing = _read_existing_decision(project_dir, run_id)
    if existing is None:
        decision = RunRetentionDecision(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            candidate_id=candidate_id,
            run_status=run_status,
            policy_source=resolved_policy.source,
            keep_failed_runs=resolved_policy.keep_failed_runs,
            keep_successful_runs=resolved_policy.keep_successful_runs,
            local_action=local_action,
            remote_action=_REMOTE_NOT_APPLICABLE,
            local_run_dir=str(local_run_dir),
            remote_run_dir=None,
            issues=list(new_issues),
            decided_at_utc=now_utc or _now_utc(),
        )
    else:
        # An earlier writer (typically remote retention) already produced a
        # report for this run_id. Preserve the other side's fields and the
        # earlier classification; only this call's local_action/local_run_dir
        # and any new issues are merged in.
        merged_issues = list(existing.issues) + list(new_issues)
        decision = RunRetentionDecision(
            schema_version=existing.schema_version,
            run_id=existing.run_id,
            candidate_id=existing.candidate_id or candidate_id,
            run_status=existing.run_status,
            policy_source=existing.policy_source,
            keep_failed_runs=existing.keep_failed_runs,
            keep_successful_runs=existing.keep_successful_runs,
            local_action=local_action,
            remote_action=existing.remote_action,
            local_run_dir=str(local_run_dir),
            remote_run_dir=existing.remote_run_dir,
            issues=merged_issues,
            decided_at_utc=existing.decided_at_utc or (now_utc or _now_utc()),
        )
    _write_decision_report(project_dir, decision)
    return decision


def _validate_remote_target(
    remote_run_dir: PurePosixPath, remote_project_dir: PurePosixPath, run_id: str
) -> None:
    """Defense-in-depth checks before issuing any remote rm."""
    project_str = str(remote_project_dir)
    target_str = str(remote_run_dir)
    if not target_str.startswith(project_str.rstrip("/") + "/"):
        raise ValueError(
            f"remote run dir {target_str!r} is not under remote project "
            f"dir {project_str!r}"
        )
    if remote_run_dir == remote_project_dir:
        raise ValueError("remote run dir must not equal remote project dir")
    if re.search(r"[\*\?\[\]\{\}]", run_id):
        raise ValueError(
            f"unsafe run_id with glob characters rejected: {run_id!r}"
        )


def apply_remote_run_retention(
    project_dir: Path,
    *,
    remote_ref: Any,
    runner: Any,
    run_id: str,
    candidate_id: str | None,
    run_succeeded: bool,
    policy: RunRetentionPolicy | None = None,
    now_utc: str | None = None,
) -> RunRetentionDecision:
    """Apply retention to the remote candidate run directory.

    Reads any existing local decision report (written by
    ``apply_local_run_retention``) and updates the ``remote_run_dir``,
    ``remote_action``, and ``issues`` fields, then rewrites the report.
    Falls back to a fresh decision when no local report exists yet.
    """
    project_dir = Path(project_dir)
    _validate_run_id(run_id)

    resolved_policy = policy or load_run_retention_policy(project_dir)
    remote_project_dir: PurePosixPath = remote_ref.remote_project_dir
    remote_run_dir = remote_project_dir / "runs" / "real" / run_id
    _validate_remote_target(remote_run_dir, remote_project_dir, run_id)

    keep_for_status = (
        resolved_policy.keep_successful_runs
        if run_succeeded
        else resolved_policy.keep_failed_runs
    )
    run_status = "successful" if run_succeeded else "failed"
    new_issues: list[str] = []

    if keep_for_status:
        remote_action = _REMOTE_KEPT
    else:
        try:
            probe = runner.run(f"test -d {quote_remote_path(remote_run_dir)}")
            return_code = getattr(probe, "return_code", None)
            if return_code != 0:
                remote_action = _REMOTE_MISSING
            else:
                runner.run(
                    f"rm -rf -- {quote_remote_path(remote_run_dir)}",
                    check=True,
                )
                remote_action = _REMOTE_DELETED
        except Exception as exc:  # noqa: BLE001 — surface any remote failure.
            remote_action = _REMOTE_FAILED
            new_issues.append(
                f"remote rm of {remote_run_dir.as_posix()} failed: {exc}"
            )

    existing = _read_existing_decision(project_dir, run_id)
    if existing is None:
        local_run_dir = _local_run_dir_for(project_dir, run_id)
        decision = RunRetentionDecision(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            candidate_id=candidate_id,
            run_status=run_status,
            policy_source=resolved_policy.source,
            keep_failed_runs=resolved_policy.keep_failed_runs,
            keep_successful_runs=resolved_policy.keep_successful_runs,
            local_action=_LOCAL_KEPT,
            remote_action=remote_action,
            local_run_dir=str(local_run_dir),
            remote_run_dir=remote_run_dir.as_posix(),
            issues=list(new_issues),
            decided_at_utc=now_utc or _now_utc(),
        )
    else:
        merged_issues = list(existing.issues) + list(new_issues)
        decision = RunRetentionDecision(
            schema_version=existing.schema_version,
            run_id=existing.run_id,
            candidate_id=existing.candidate_id or candidate_id,
            run_status=existing.run_status,
            policy_source=existing.policy_source,
            keep_failed_runs=existing.keep_failed_runs,
            keep_successful_runs=existing.keep_successful_runs,
            local_action=existing.local_action,
            remote_action=remote_action,
            local_run_dir=existing.local_run_dir,
            remote_run_dir=remote_run_dir.as_posix(),
            issues=merged_issues,
            decided_at_utc=existing.decided_at_utc or (now_utc or _now_utc()),
        )
    _write_decision_report(project_dir, decision)
    return decision
