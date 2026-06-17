from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.optimizer_progress_state import (
    build_optimizer_progress_state,
    sync_optimizer_progress_state,
)
from hermes_workflow.package import create_project_from_template
from tests.report_helpers import write_json


def _ten_traces_seven_recorded_three_failed() -> list[dict[str, object]]:
    traces: list[dict[str, object]] = []
    for index in range(7):
        traces.append(
            {
                "evaluation_index": index + 1,
                "run_id": f"real_{index + 1:03d}",
                "status": "constraint_failed",
                "objective": 1.0,
            }
        )
    for index in range(3):
        traces.append(
            {
                "evaluation_index": 7 + index + 1,
                "run_id": f"real_{7 + index + 1:03d}",
                "status": "metric_check_failed",
                "objective": 1.0,
            }
        )
    return traces


def _set_optimizer_max_evaluations(project_dir: Path, max_evaluations: int) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    text = optimizer_path.read_text(encoding="utf-8")
    text = text.replace("max_evaluations: 30", f"max_evaluations: {max_evaluations}")
    optimizer_path.write_text(text, encoding="utf-8")


def _write_artifacts_for_progress(
    project_dir: Path,
    *,
    report_status: str = "completed",
    evaluation_count: int = 10,
    ledger_rows: int = 7,
    traces: list[dict[str, object]] | None = None,
) -> None:
    traces = traces if traces is not None else _ten_traces_seven_recorded_three_failed()
    write_json(
        project_dir / "reports" / "optimizer_run_report.json",
        {
            "schema_version": "1.0",
            "status": report_status,
            "evaluation_count": evaluation_count,
            "best_candidate": None,
            "evaluations": "reports/optimizer_evaluations.jsonl",
            "issues": [],
        },
    )
    evaluations_path = project_dir / "reports" / "optimizer_evaluations.jsonl"
    evaluations_path.parent.mkdir(parents=True, exist_ok=True)
    with evaluations_path.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, sort_keys=True) + "\n")
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as handle:
        for index in range(ledger_rows):
            handle.write(
                json.dumps(
                    {
                        "candidate_id": f"real_{index + 1:03d}",
                        "parameters": {"FN": "2"},
                        "metrics": {"rise": 1.0e-12},
                        "constraints_passed": False,
                        "objective": 1.0,
                        "batch_id": 1,
                        "simulation_status": "real_pass",
                        "timestamp_utc": "2026-06-14T00:00:00Z",
                        "result_source": "real",
                        "run_id": f"real_{index + 1:03d}",
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def test_build_optimizer_progress_state_for_10_attempts_7_recorded_3_failed() -> None:
    state = build_optimizer_progress_state(
        project_name="bridge_test_inv",
        algorithm="openbox",
        initialization="lhs",
        max_evaluations=10,
        batch_size=2,
        random_seed=7,
        attempted_count=10,
        recorded_observation_count=7,
        status_counts={"constraint_failed": 7, "metric_check_failed": 3},
        report_status="completed",
        completed_early=False,
        best_candidate_id=None,
        started_at_utc=None,
        now_utc="2026-06-14T00:00:00Z",
    )
    assert state.current_evaluations == 10
    assert state.recorded_observation_count == 7
    assert state.failed_evaluation_count == 3
    assert state.status_counts == {"constraint_failed": 7, "metric_check_failed": 3}
    assert state.progress_source == "reports/optimizer_evaluations.jsonl"
    assert state.best_candidate_id is None
    assert state.status == "completed"


def test_build_optimizer_progress_state_status_running_when_attempted_below_budget() -> None:
    state = build_optimizer_progress_state(
        project_name="bridge_test_inv",
        algorithm="openbox",
        initialization="lhs",
        max_evaluations=10,
        batch_size=2,
        random_seed=7,
        attempted_count=4,
        recorded_observation_count=3,
        status_counts={"constraint_failed": 3, "metric_check_failed": 1},
        report_status="completed",
        completed_early=False,
        best_candidate_id=None,
        started_at_utc=None,
        now_utc="2026-06-14T00:00:00Z",
    )
    assert state.status == "running"
    assert state.current_evaluations == 4
    assert state.failed_evaluation_count == 1


def test_build_optimizer_progress_state_status_completed_when_completed_early_under_budget() -> None:
    state = build_optimizer_progress_state(
        project_name="bridge_test_inv",
        algorithm="openbox",
        initialization="lhs",
        max_evaluations=10,
        batch_size=2,
        random_seed=7,
        attempted_count=6,
        recorded_observation_count=4,
        status_counts={"constraint_failed": 4, "metric_check_failed": 2},
        report_status="completed",
        completed_early=True,
        best_candidate_id=None,
        started_at_utc=None,
        now_utc="2026-06-14T00:00:00Z",
    )
    assert state.status == "completed"


def test_build_optimizer_progress_state_preserves_existing_best_candidate_id() -> None:
    state = build_optimizer_progress_state(
        project_name="bridge_test_inv",
        algorithm="openbox",
        initialization="lhs",
        max_evaluations=10,
        batch_size=2,
        random_seed=7,
        attempted_count=10,
        recorded_observation_count=7,
        status_counts={"feasible": 1, "constraint_failed": 6, "metric_check_failed": 3},
        report_status="completed",
        completed_early=False,
        best_candidate_id="real_005",
        started_at_utc=None,
        now_utc="2026-06-14T00:00:00Z",
    )
    assert state.best_candidate_id == "real_005"


def test_build_optimizer_progress_state_status_counts_match_traces() -> None:
    state = build_optimizer_progress_state(
        project_name="bridge_test_inv",
        algorithm="turbo",
        initialization="lhs",
        max_evaluations=10,
        batch_size=2,
        random_seed=7,
        attempted_count=10,
        recorded_observation_count=7,
        status_counts={"constraint_failed": 7, "metric_check_failed": 3},
        report_status="completed",
        completed_early=False,
        best_candidate_id=None,
        started_at_utc=None,
        now_utc="2026-06-14T00:00:00Z",
    )
    assert state.status_counts == {
        "constraint_failed": 7,
        "metric_check_failed": 3,
    }


def test_sync_optimizer_progress_state_reads_artifacts_and_writes_state(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _set_optimizer_max_evaluations(project_dir, 10)
    _write_artifacts_for_progress(project_dir)

    state_path = sync_optimizer_progress_state(project_dir)
    assert state_path == project_dir / "state" / "optimizer_state.json"

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["current_evaluations"] == 10
    assert payload["recorded_observation_count"] == 7
    assert payload["failed_evaluation_count"] == 3
    assert payload["status_counts"] == {
        "constraint_failed": 7,
        "metric_check_failed": 3,
    }
    assert payload["progress_source"] == "reports/optimizer_evaluations.jsonl"
    assert payload["best_candidate_id"] is None
    assert payload["status"] == "completed"

    assert not (project_dir / "state" / "best_candidate.json").exists()

    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_lines = [
        line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(ledger_lines) == 7


def test_sync_optimizer_progress_state_preserves_existing_started_at_utc(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _set_optimizer_max_evaluations(project_dir, 10)
    _write_artifacts_for_progress(project_dir)
    state_dir = project_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        state_dir / "optimizer_state.json",
        {
            "schema_version": "1.0",
            "project_name": "bridge_test_inv",
            "algorithm": "turbo",
            "initialization": "lhs",
            "current_evaluations": 0,
            "max_evaluations": 10,
            "batch_size": 2,
            "random_seed": 7,
            "best_candidate_id": None,
            "status": "running",
            "started_at_utc": "2026-06-13T00:00:00Z",
            "updated_at_utc": "2026-06-13T00:00:00Z",
        },
    )

    state_path = sync_optimizer_progress_state(project_dir)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["started_at_utc"] == "2026-06-13T00:00:00Z"
