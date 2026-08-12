"""Shared optimizer progress-state contract.

Builds and persists ``state/optimizer_state.json`` from the optimizer report
and trace artifacts so attempted/recorded/failed counts agree across local
and remote runs. The ledger remains the source of usable observations only;
this module never writes synthetic ledger rows.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from hermes_workflow.mock_optimizer import write_optimizer_state
from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts
from hermes_workflow.schemas import OptimizerState
from hermes_workflow.validate import assert_valid_project


OPTIMIZER_STATE_RELATIVE = Path("state/optimizer_state.json")
BEST_CANDIDATE_RELATIVE = Path("state/best_candidate.json")
LEDGER_RELATIVE = Path("ledger/experiment_ledger.jsonl")
PROGRESS_SOURCE_DEFAULT = "reports/optimizer_evaluations.jsonl"


def build_optimizer_progress_state(
    *,
    project_name: str,
    algorithm: str,
    initialization: str,
    max_evaluations: int,
    batch_size: int,
    random_seed: int,
    attempted_count: int,
    recorded_observation_count: int,
    status_counts: dict[str, int],
    report_status: str,
    completed_early: bool,
    best_candidate_id: str | None,
    started_at_utc: str | None,
    now_utc: str,
    progress_source: str = PROGRESS_SOURCE_DEFAULT,
) -> OptimizerState:
    """Build an ``OptimizerState`` from optimizer-trace counts.

    Counting rules:

    - ``current_evaluations = attempted_count``.
    - ``recorded_observation_count`` is the ledger row count.
    - ``failed_evaluation_count = max(0, attempted_count - recorded_observation_count)``.
    - ``status`` is ``completed`` when the report has finished and either the
      attempted count reached the budget or the optimizer completed early.
    """
    failed_count = max(0, int(attempted_count) - int(recorded_observation_count))
    if (
        report_status == "completed"
        and (attempted_count >= max_evaluations or completed_early)
    ):
        status = "completed"
    else:
        status = "running"
    return OptimizerState(
        schema_version="1.0",
        project_name=project_name,
        algorithm=algorithm,
        initialization=initialization,
        current_evaluations=int(attempted_count),
        max_evaluations=int(max_evaluations),
        batch_size=int(batch_size),
        random_seed=int(random_seed),
        best_candidate_id=best_candidate_id,
        status=status,
        started_at_utc=started_at_utc or now_utc,
        updated_at_utc=now_utc,
        recorded_observation_count=int(recorded_observation_count),
        failed_evaluation_count=failed_count,
        status_counts={key: int(value) for key, value in status_counts.items()},
        progress_source=progress_source,
    )


def sync_optimizer_progress_state(
    project_dir: Path,
    *,
    expected_backend: str | None = None,
) -> Path:
    """Re-derive ``state/optimizer_state.json`` from on-disk artifacts."""
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    optimizer_settings = bundle.optimizer.optimizer

    artifact_issues: list[str] = []
    artifacts = load_optimizer_artifacts(
        project_dir,
        issues=artifact_issues,
        expected_backend=expected_backend,
    )
    if expected_backend is not None and artifact_issues:
        raise ValueError(
            "cannot synchronize optimizer progress from mismatched artifacts: "
            + "; ".join(artifact_issues)
        )
    report = artifacts.report or {}
    traces = artifacts.traces or []

    report_count_raw = report.get("evaluation_count")
    report_count = int(report_count_raw) if isinstance(report_count_raw, int) else None
    trace_count = len(traces)
    if report_count is not None and trace_count > 0 and report_count != trace_count:
        attempted_count = max(report_count, trace_count)
    elif report_count is not None:
        attempted_count = max(report_count, trace_count)
    else:
        attempted_count = trace_count

    status_counts: dict[str, int] = dict(
        Counter(
            trace.get("status")
            for trace in traces
            if isinstance(trace.get("status"), str)
        )
    )

    ledger_count = _count_ledger_rows(project_dir)

    report_status_value = report.get("status")
    report_status = (
        report_status_value if isinstance(report_status_value, str) else ""
    )

    completed_early = False
    openbox_section = report.get("openbox")
    if isinstance(openbox_section, dict):
        continuation = openbox_section.get("continuation")
        if isinstance(continuation, dict):
            completed_early = bool(continuation.get("completed_early", False))

    progress_source = artifacts.evaluations_relative.as_posix()
    started_at_utc = _existing_started_at_utc(project_dir)
    best_candidate_id = _existing_best_candidate_id(project_dir)
    now_utc = _now_utc_iso()

    state = build_optimizer_progress_state(
        project_name=bundle.project_config.project.name,
        algorithm=optimizer_settings.algorithm.value,
        initialization=optimizer_settings.initialization.value,
        max_evaluations=optimizer_settings.max_evaluations,
        batch_size=optimizer_settings.batch_size,
        random_seed=optimizer_settings.random_seed,
        attempted_count=attempted_count,
        recorded_observation_count=ledger_count,
        status_counts=status_counts,
        report_status=report_status,
        completed_early=completed_early,
        best_candidate_id=best_candidate_id,
        started_at_utc=started_at_utc,
        now_utc=now_utc,
        progress_source=progress_source,
    )
    return write_optimizer_state(project_dir, state)


def _count_ledger_rows(project_dir: Path) -> int:
    ledger_path = project_dir / LEDGER_RELATIVE
    if not ledger_path.exists():
        return 0
    count = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _existing_started_at_utc(project_dir: Path) -> str | None:
    state_path = project_dir / OPTIMIZER_STATE_RELATIVE
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    started_at = payload.get("started_at_utc")
    return started_at if isinstance(started_at, str) else None


def _existing_best_candidate_id(project_dir: Path) -> str | None:
    best_path = project_dir / BEST_CANDIDATE_RELATIVE
    if not best_path.exists():
        return None
    try:
        payload = json.loads(best_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    candidate_id = payload.get("candidate_id")
    return candidate_id if isinstance(candidate_id, str) else None


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
