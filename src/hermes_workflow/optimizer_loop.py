from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.optimizer_suggestion import suggest_candidate_request
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_candidate_real_run
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealResultRecordStatus,
    RealRunCheckStatus,
)
from hermes_workflow.result_handoff import check_real_run


ADAPTER_SUCCEEDED = "succeeded"
RECORDED = "recorded"
ADAPTER_FAILED = "adapter_failed"
RESULT_CHECK_FAILED = "result_check_failed"
METRIC_CHECK_FAILED = "metric_check_failed"
RECORD_FAILED = "record_failed"

AdapterRunner = Callable[[Path, str], "OptimizerLoopAdapterResult"]


@dataclass(frozen=True)
class OptimizerLoopAdapterResult:
    status: str
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizerLoopCycleReport:
    status: str
    candidate_id: str
    run_id: str
    candidate_request: Path
    issues: tuple[str, ...] = ()


def run_single_optimizer_cycle(
    project_dir: Path,
    *,
    adapter_runner: AdapterRunner,
    candidate_id: str | None = None,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    recorded_at_utc: str | None = None,
) -> OptimizerLoopCycleReport:
    project_dir = Path(project_dir)
    selected_candidate_id = candidate_id or _next_candidate_id(project_dir)
    selected_run_id = run_id or _next_run_id(project_dir)
    suggestion = suggest_candidate_request(
        project_dir,
        candidate_id=selected_candidate_id,
        created_at_utc=created_at_utc,
    )
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=suggestion.output_path,
        run_id=selected_run_id,
        created_at_utc=created_at_utc,
    )

    adapter_result = adapter_runner(project_dir, package.run_id)
    if adapter_result.status != ADAPTER_SUCCEEDED:
        return OptimizerLoopCycleReport(
            status=ADAPTER_FAILED,
            candidate_id=suggestion.candidate_id,
            run_id=package.run_id,
            candidate_request=suggestion.output_path,
            issues=adapter_result.issues or (adapter_result.status,),
        )

    real_report = check_real_run(project_dir, run_id=package.run_id)
    if real_report.status != RealRunCheckStatus.PASS:
        return OptimizerLoopCycleReport(
            status=RESULT_CHECK_FAILED,
            candidate_id=suggestion.candidate_id,
            run_id=package.run_id,
            candidate_request=suggestion.output_path,
            issues=tuple(real_report.issues),
        )

    metric_report = check_metric_results(project_dir, run_id=package.run_id)
    if metric_report.status != MetricResultCheckStatus.PASS:
        return OptimizerLoopCycleReport(
            status=METRIC_CHECK_FAILED,
            candidate_id=suggestion.candidate_id,
            run_id=package.run_id,
            candidate_request=suggestion.output_path,
            issues=tuple(metric_report.issues),
        )

    record_report = record_real_result(
        project_dir,
        run_id=package.run_id,
        recorded_at_utc=recorded_at_utc,
    )
    if record_report.status != RealResultRecordStatus.PASS:
        return OptimizerLoopCycleReport(
            status=RECORD_FAILED,
            candidate_id=suggestion.candidate_id,
            run_id=package.run_id,
            candidate_request=suggestion.output_path,
            issues=tuple(record_report.issues),
        )

    return OptimizerLoopCycleReport(
        status=RECORDED,
        candidate_id=suggestion.candidate_id,
        run_id=package.run_id,
        candidate_request=suggestion.output_path,
    )


def _next_candidate_id(project_dir: Path) -> str:
    baseline = _current_evaluations(project_dir) + 1
    return (
        f"candidate_"
        f"{_next_numeric_suffix(project_dir, 'candidate_requests', 'candidate_', baseline):06d}"
    )


def _next_run_id(project_dir: Path) -> str:
    return f"real_{_next_numeric_suffix(project_dir, 'runs/real', 'real_', 1):03d}"


def _next_numeric_suffix(
    project_dir: Path,
    relative_dir: str,
    prefix: str,
    baseline: int,
) -> int:
    used = set()
    directory = project_dir / relative_dir
    if directory.exists():
        pattern = re.compile(rf"^{re.escape(prefix)}([0-9]+)")
        for path in directory.iterdir():
            match = pattern.match(path.stem)
            if match:
                used.add(int(match.group(1)))
    if prefix == "candidate_":
        used.update(_ledger_candidate_numbers(project_dir))
    index = baseline
    while index in used:
        index += 1
    return index


def _current_evaluations(project_dir: Path) -> int:
    state_path = project_dir / "state" / "optimizer_state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    value = payload.get("current_evaluations", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _ledger_candidate_numbers(project_dir: Path) -> set[int]:
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    if not ledger_path.exists():
        return set()
    numbers = set()
    pattern = re.compile(r"^candidate_([0-9]+)$")
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        candidate_id = payload.get("candidate_id")
        if isinstance(candidate_id, str):
            match = pattern.match(candidate_id)
            if match:
                numbers.add(int(match.group(1)))
    return numbers
