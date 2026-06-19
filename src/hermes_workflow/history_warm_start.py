"""History warm-start audit reader and report skeleton.

Task 2 scope: read configured previous-project sources, inspect their optimizer
evaluation history files, and write deterministic audit reports. No variable or
metric compatibility, no objective re-evaluation, and no OpenBox integration
exists here yet. Every syntactically valid evaluation row is counted as a
candidate trace and rejected with the temporary reason
``compatibility_not_evaluated``; that decision is replaced by real compatibility
checks in Task 3.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.schemas import HistoryWarmStartConfig, HistoryWarmStartSource
from hermes_workflow.validate import ContractBundle, validate_project_files

HISTORY_WARM_START_AUDIT_RELATIVE = Path("reports/history_warm_start_audit.json")
HISTORY_WARM_START_AUDIT_MD_RELATIVE = Path("reports/history_warm_start_audit.md")

_SCHEMA_VERSION = "1.0"
_STATUS_DISABLED = "disabled"
_STATUS_COMPLETED = "completed"
_SOURCE_ACCEPTED = "accepted"
_SOURCE_REJECTED = "rejected"

# Per-row rejection reasons (Task 2). Task 3 adds real compatibility decisions.
_REASON_COMPATIBILITY_NOT_EVALUATED = "compatibility_not_evaluated"
_REASON_INVALID_OPTIMIZER_EVALUATIONS = "invalid_optimizer_evaluations"

# Source-level rejection reasons.
_REASON_SOURCE_PATH_MISSING = "source_path_missing"
_REASON_SOURCE_NOT_VALID_PROJECT = "source_not_valid_project"
_REASON_MISSING_OPTIMIZER_EVALUATIONS = "missing_optimizer_evaluations"

_NO_ACCEPTED_OBSERVATIONS_ISSUE = (
    "history warm-start has no accepted observations; "
    "OpenBox will start without transfer history"
)


@dataclass(frozen=True)
class OpenBoxTransferLearningAudit:
    enabled: bool
    source_count: int
    accepted_observation_count: int
    warm_start_strategy: str | None
    applied_to_advisor: bool


@dataclass(frozen=True)
class HistoryWarmStartSourceAudit:
    label: str | None
    path: str
    status: str
    candidate_trace_count: int
    accepted_observation_count: int
    rejected_observation_count: int
    rejection_reasons: dict[str, int]
    issues: list[str]


@dataclass(frozen=True)
class HistoryWarmStartAudit:
    enabled: bool
    status: str
    sources: list[HistoryWarmStartSourceAudit]
    accepted_observation_count: int
    rejected_observation_count: int
    openbox_transfer_learning: OpenBoxTransferLearningAudit
    issues: list[str]


def audit_history_warm_start(
    project_dir: Path, bundle: ContractBundle
) -> HistoryWarmStartAudit:
    """Audit configured history warm-start sources and write JSON/Markdown reports.

    Reports are written on every call, including when warm-start is disabled.
    """
    config = bundle.history_warm_start
    if config is None or not config.history_warm_start.enabled:
        audit = _disabled_audit()
    else:
        audit = _enabled_audit(project_dir, config)

    _write_reports(project_dir, audit)
    return audit


def _disabled_audit() -> HistoryWarmStartAudit:
    return HistoryWarmStartAudit(
        enabled=False,
        status=_STATUS_DISABLED,
        sources=[],
        accepted_observation_count=0,
        rejected_observation_count=0,
        openbox_transfer_learning=OpenBoxTransferLearningAudit(
            enabled=False,
            source_count=0,
            accepted_observation_count=0,
            warm_start_strategy=None,
            applied_to_advisor=False,
        ),
        issues=[],
    )


def _enabled_audit(project_dir: Path, config: HistoryWarmStartConfig) -> HistoryWarmStartAudit:
    settings = config.history_warm_start
    source_audits = [
        _audit_source(project_dir, source) for source in settings.sources
    ]
    accepted = sum(source.accepted_observation_count for source in source_audits)
    rejected = sum(source.rejected_observation_count for source in source_audits)
    issues: list[str] = []
    if accepted == 0:
        issues.append(_NO_ACCEPTED_OBSERVATIONS_ISSUE)

    return HistoryWarmStartAudit(
        enabled=True,
        status=_STATUS_COMPLETED,
        sources=source_audits,
        accepted_observation_count=accepted,
        rejected_observation_count=rejected,
        openbox_transfer_learning=OpenBoxTransferLearningAudit(
            enabled=True,
            source_count=len(settings.sources),
            accepted_observation_count=accepted,
            warm_start_strategy=settings.warm_start_strategy,
            applied_to_advisor=False,
        ),
        issues=issues,
    )


def _audit_source(
    project_dir: Path, source: HistoryWarmStartSource
) -> HistoryWarmStartSourceAudit:
    raw_path = Path(source.path)
    resolved = raw_path if raw_path.is_absolute() else project_dir / raw_path
    resolved = resolved.resolve()
    display_path = str(resolved)

    if not resolved.exists():
        return _source_level_rejection(
            source.label,
            display_path,
            f"{_REASON_SOURCE_PATH_MISSING}: source path does not exist: {display_path}",
        )
    # Task 2 treats "valid project" as passing full structural validation.
    # This is intentionally strict; Task 3 may relax it to a lighter structural
    # check so prior-round projects with benign config drift can still
    # contribute evaluation rows.
    if not validate_project_files(resolved).ok:
        return _source_level_rejection(
            source.label,
            display_path,
            f"{_REASON_SOURCE_NOT_VALID_PROJECT}: source is not a valid project: {display_path}",
        )

    evaluations_path = resolved / EVALUATIONS_RELATIVE
    if not evaluations_path.exists():
        return _source_level_rejection(
            source.label,
            display_path,
            (
                f"{_REASON_MISSING_OPTIMIZER_EVALUATIONS}: source project has no "
                f"optimizer evaluations at {EVALUATIONS_RELATIVE}: {display_path}"
            ),
        )

    return _read_evaluation_rows(source.label, display_path, evaluations_path)


def _source_level_rejection(
    label: str | None, path: str, issue: str
) -> HistoryWarmStartSourceAudit:
    # Source-level failures are recorded in ``issues`` (the reason keyword is
    # embedded there); ``rejection_reasons`` is reserved for per-observation
    # counts so that its values always sum to ``rejected_observation_count``.
    return HistoryWarmStartSourceAudit(
        label=label,
        path=path,
        status=_SOURCE_REJECTED,
        candidate_trace_count=0,
        accepted_observation_count=0,
        rejected_observation_count=0,
        rejection_reasons={},
        issues=[issue],
    )


def _read_evaluation_rows(
    label: str | None, path: str, evaluations_path: Path
) -> HistoryWarmStartSourceAudit:
    candidate_trace_count = 0
    accepted = 0
    rejected = 0
    rejection_reasons: dict[str, int] = {}

    text = evaluations_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            rejected += 1
            rejection_reasons[_REASON_INVALID_OPTIMIZER_EVALUATIONS] = (
                rejection_reasons.get(_REASON_INVALID_OPTIMIZER_EVALUATIONS, 0) + 1
            )
            continue
        if not isinstance(payload, dict):
            rejected += 1
            rejection_reasons[_REASON_INVALID_OPTIMIZER_EVALUATIONS] = (
                rejection_reasons.get(_REASON_INVALID_OPTIMIZER_EVALUATIONS, 0) + 1
            )
            continue
        # Valid evaluation row. Task 2 has no compatibility work yet, so every
        # candidate trace is rejected with the temporary reason below.
        candidate_trace_count += 1
        rejected += 1
        rejection_reasons[_REASON_COMPATIBILITY_NOT_EVALUATED] = (
            rejection_reasons.get(_REASON_COMPATIBILITY_NOT_EVALUATED, 0) + 1
        )

    status = _SOURCE_ACCEPTED if accepted > 0 else _SOURCE_REJECTED
    return HistoryWarmStartSourceAudit(
        label=label,
        path=path,
        status=status,
        candidate_trace_count=candidate_trace_count,
        accepted_observation_count=accepted,
        rejected_observation_count=rejected,
        rejection_reasons=rejection_reasons,
        issues=[],
    )


def _write_reports(project_dir: Path, audit: HistoryWarmStartAudit) -> None:
    json_path = project_dir / HISTORY_WARM_START_AUDIT_RELATIVE
    md_path = project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(_audit_to_payload(audit), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_audit_to_markdown(audit), encoding="utf-8")


def _audit_to_payload(audit: HistoryWarmStartAudit) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "enabled": audit.enabled,
        "status": audit.status,
        "sources": [_source_to_payload(source) for source in audit.sources],
        "accepted_observation_count": audit.accepted_observation_count,
        "rejected_observation_count": audit.rejected_observation_count,
        "openbox_transfer_learning": {
            "enabled": audit.openbox_transfer_learning.enabled,
            "source_count": audit.openbox_transfer_learning.source_count,
            "accepted_observation_count": audit.openbox_transfer_learning.accepted_observation_count,
            "warm_start_strategy": audit.openbox_transfer_learning.warm_start_strategy,
            "applied_to_advisor": audit.openbox_transfer_learning.applied_to_advisor,
        },
        "issues": list(audit.issues),
    }


def _source_to_payload(source: HistoryWarmStartSourceAudit) -> dict[str, object]:
    return {
        "label": source.label,
        "path": source.path,
        "status": source.status,
        "candidate_trace_count": source.candidate_trace_count,
        "accepted_observation_count": source.accepted_observation_count,
        "rejected_observation_count": source.rejected_observation_count,
        "rejection_reasons": dict(source.rejection_reasons),
        "issues": list(source.issues),
    }


def _audit_to_markdown(audit: HistoryWarmStartAudit) -> str:
    lines = ["# History Warm-Start Audit", ""]
    lines.append(f"Status: {audit.status}")
    lines.append(f"Enabled: {'true' if audit.enabled else 'false'}")
    lines.append(f"Accepted observations: {audit.accepted_observation_count}")
    lines.append(f"Rejected observations: {audit.rejected_observation_count}")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source in audit.sources:
        label = source.label if source.label is not None else source.path
        lines.append(
            f"- {label}: {source.status}, "
            f"candidates={source.candidate_trace_count}, "
            f"accepted={source.accepted_observation_count}, "
            f"rejected={source.rejected_observation_count}"
        )
    lines.append("")
    lines.append("## Issues")
    lines.append("")
    for issue in audit.issues:
        lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"
