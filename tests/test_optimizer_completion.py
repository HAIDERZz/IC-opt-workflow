import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_completion import summarize_optimizer_run
from tests.real_run_smoke_helpers import create_approved_real_project


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _trace_row(
    *,
    evaluation_index: int,
    run_id: str,
    status: str,
    objective: float,
) -> dict:
    return {
        "batch_id": f"batch_{((evaluation_index - 1) // 2) + 1:03d}",
        "batch_size": 2,
        "batch_slot": (evaluation_index - 1) % 2,
        "batch_worker_count": 2,
        "constraint_penalty": 0.0,
        "evaluation_index": evaluation_index,
        "fom": 1.0 / objective,
        "issues": [],
        "max_parallel_jobs": 10,
        "metric_result_manifest": (
            f"runs/real/{run_id}/metrics/metric_result_manifest.json"
        ),
        "metrics": {"rise": 1e-10, "fall": 1e-10, "DC": 1e-3},
        "objective": objective,
        "parallel_jobs": 10,
        "parameters": {
            "FN": str(2 + evaluation_index),
            "WN": f"{evaluation_index / 10:.1f}u",
        },
        "raw_x": [float(evaluation_index), evaluation_index / 10],
        "result_manifest": f"runs/real/{run_id}/result_manifest.json",
        "run_id": run_id,
        "selection_phase": "initialization" if evaluation_index <= 4 else "turbo",
        "status": status,
        "threads_per_run": 10,
    }


def _write_accepted_optimizer_project(
    tmp_path: Path,
    *,
    accepted: bool = True,
    rows: list[dict] | None = None,
    variables: list[dict] | None = None,
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    trace_rows = rows or [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=9.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=8.0,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="constraint_failed",
            objective=7.0,
        ),
        _trace_row(
            evaluation_index=4,
            run_id="real_004",
            status="feasible",
            objective=6.0,
        ),
        _trace_row(
            evaluation_index=5,
            run_id="real_005",
            status="feasible",
            objective=5.0,
        ),
        _trace_row(
            evaluation_index=6,
            run_id="real_006",
            status="feasible",
            objective=4.0,
        ),
    ]
    best_trace = min(trace_rows, key=lambda row: row["objective"])
    _write_json(
        project_dir / "reports" / "optimizer_run_acceptance_report.json",
        {
            "best_candidate": best_trace,
            "evaluation_count": len(trace_rows),
            "issues": [] if accepted else ["acceptance failed"],
            "metric_manifest_count": len(trace_rows),
            "report_path": "reports/optimizer_run_acceptance_report.json",
            "result_manifest_count": len(trace_rows),
            "schema_version": "1.0",
            "settings": {
                "output_format": "psfxl",
                "parallel_jobs": 10,
                "preset": "ax",
                "threads_per_run": 10,
            },
            "status": "accepted" if accepted else "rejected",
            "status_counts": {
                status: sum(row["status"] == status for row in trace_rows)
                for status in {row["status"] for row in trace_rows}
            },
            "warnings": [],
        },
    )
    _write_json(
        project_dir / "reports" / "native_turbo_optimizer_report.json",
        {
            "batch_summary": {
                "batch_count": 3,
                "max_batch_worker_count": 2,
                "status_counts": {
                    status: sum(row["status"] == status for row in trace_rows)
                    for status in {row["status"] for row in trace_rows}
                },
            },
            "best_candidate": best_trace,
            "evaluation_count": len(trace_rows),
            "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
            "issues": [],
            "schema_version": "1.0",
            "status": "completed",
        },
    )
    _write_jsonl(
        project_dir / "reports" / "native_turbo_optimizer_evaluations.jsonl",
        trace_rows,
    )
    _write_yaml(
        project_dir / "config" / "variables.yaml",
        {
            "schema_version": "1.0",
            "variables": variables
            or [
                {
                    "kind": "integer",
                    "lower": "2",
                    "name": "FN",
                    "step": "1",
                    "upper": "13",
                },
                {
                    "kind": "continuous_step",
                    "lower": "0.1u",
                    "name": "WN",
                    "step": "0.1u",
                    "upper": "2.0u",
                },
            ],
        },
    )
    _write_yaml(
        project_dir / "config" / "optimizer.yaml",
        {
            "schema_version": "1.0",
            "optimizer": {
                "algorithm": "turbo",
                "batch_size": 2,
                "deduplicate_candidates": True,
                "failure_penalty": 1000000.0,
                "initialization": "sobol",
                "max_evaluations": 6,
                "random_seed": 20260528,
            },
        },
    )
    return project_dir


class FakeAdvisorForCompletion:
    def __init__(self) -> None:
        self._batches = [
            [
                {"F": 22, "W": 0.8, "L": 40, "VB_LO": 300},
                {"F": 24, "W": 1.0, "L": 30, "VB_LO": 340},
            ],
            [
                {"F": 26, "W": 1.2, "L": 40, "VB_LO": 360},
                {"F": 28, "W": 0.6, "L": 30, "VB_LO": 380},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def test_summarize_optimizer_run_reads_backend_neutral_report(
    tmp_path: Path,
) -> None:
    from hermes_workflow.openbox_backend import run_openbox_fake_optimization
    from hermes_workflow.optimizer_acceptance import check_optimizer_run

    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForCompletion(),
    )
    check_optimizer_run(project_dir)

    report = summarize_optimizer_run(project_dir)

    assert report.status == "pass"
    assert report.evaluation_count == 4
    assert report.best_observed is not None


def test_summarize_optimizer_run_loads_accepted_run(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    report = summarize_optimizer_run(project_dir)

    assert report.status == "pass"
    assert report.evaluation_count == 6
    assert report.best_observed["run_id"] == "real_006"
    assert report.status_counts == {"constraint_failed": 2, "feasible": 4}
    assert report.global_optimum_claim is False
    assert report.report_path == (
        project_dir / "reports" / "optimizer_completion_report.json"
    )


def test_summarize_optimizer_run_recommends_continue_when_recent_best_improves(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    report = summarize_optimizer_run(project_dir)

    assert report.decision == "continue_more_evals"
    assert report.improvement["recent_best_improved"] is True
    assert report.continuation["recommended"] is True
    assert report.continuation["suggested_additional_evals"] == 20
    assert report.continuation["recent_best_improved"] is True
    assert report.continuation["plateau_detected"] is False
    assert report.continuation["feasible_ratio"] == 4 / 6
    assert any("recent window" in reason for reason in report.reasons)


def test_summarize_optimizer_run_reports_plateau_when_recent_best_stalls(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="feasible",
            objective=1.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            objective=1.1,
        ),
        _trace_row(
            evaluation_index=3,
            run_id="real_003",
            status="feasible",
            objective=1.2,
        ),
        _trace_row(
            evaluation_index=4,
            run_id="real_004",
            status="feasible",
            objective=1.3,
        ),
        _trace_row(
            evaluation_index=5,
            run_id="real_005",
            status="feasible",
            objective=1.4,
        ),
        _trace_row(
            evaluation_index=6,
            run_id="real_006",
            status="feasible",
            objective=1.5,
        ),
    ]
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)

    report = summarize_optimizer_run(project_dir)

    assert report.decision == "accept_best_observed"
    assert report.continuation["recommended"] is False
    assert report.continuation["suggested_additional_evals"] == 0
    assert report.continuation["plateau_detected"] is True
    assert report.continuation["recent_best_improved"] is False


def test_summarize_optimizer_run_recommends_accept_when_trace_exhausts_space(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(evaluation_index=1, run_id="real_001", status="feasible", objective=2.0),
        _trace_row(evaluation_index=2, run_id="real_002", status="feasible", objective=1.0),
    ]
    project_dir = _write_accepted_optimizer_project(
        tmp_path,
        rows=rows,
        variables=[
            {
                "kind": "integer",
                "lower": "1",
                "name": "FN",
                "step": "1",
                "upper": "2",
            }
        ],
    )

    report = summarize_optimizer_run(project_dir)

    assert report.decision == "accept_best_observed"
    assert report.global_optimum_claim is True
    assert report.search_space["estimated_discrete_combinations"] == 2
    assert report.search_space["evaluated_fraction"] == 1.0


def test_summarize_optimizer_run_recommends_exhaustive_when_space_is_small(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(evaluation_index=1, run_id="real_001", status="feasible", objective=3.0),
        _trace_row(evaluation_index=2, run_id="real_002", status="feasible", objective=2.0),
        _trace_row(evaluation_index=3, run_id="real_003", status="feasible", objective=1.0),
    ]
    project_dir = _write_accepted_optimizer_project(
        tmp_path,
        rows=rows,
        variables=[
            {
                "kind": "integer",
                "lower": "1",
                "name": "FN",
                "step": "1",
                "upper": "7",
            }
        ],
    )

    report = summarize_optimizer_run(project_dir)

    assert report.decision == "switch_to_exhaustive_sweep"
    assert report.global_optimum_claim is False
    assert report.search_space["estimated_discrete_combinations"] == 7


def test_summarize_optimizer_run_recommends_stop_when_no_feasible_candidate_exists(
    tmp_path: Path,
) -> None:
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="constraint_failed",
            objective=3.0,
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="metric_check_failed",
            objective=1000000.0,
        ),
    ]
    project_dir = _write_accepted_optimizer_project(tmp_path, rows=rows)

    report = summarize_optimizer_run(project_dir)

    assert report.decision == "stop_for_user_review"
    assert any("no feasible" in reason for reason in report.reasons)


def test_summarize_optimizer_run_fails_when_acceptance_rejected(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path, accepted=False)

    report = summarize_optimizer_run(project_dir)

    assert report.status == "fail"
    assert report.decision == "stop_for_user_review"
    assert any("not accepted" in issue for issue in report.issues)


def test_summarize_optimizer_run_cli_writes_report(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    result = CliRunner().invoke(app, ["summarize-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "optimizer completion decision: continue_more_evals" in result.output
    assert "report: reports/optimizer_completion_report.json" in result.output
    assert (project_dir / "reports" / "optimizer_completion_report.json").is_file()


def test_summarize_optimizer_run_cli_fails_when_run_is_rejected(
    tmp_path: Path,
) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path, accepted=False)

    result = CliRunner().invoke(app, ["summarize-optimizer-run", str(project_dir)])

    assert result.exit_code == 1
    assert "optimizer completion decision failed" in result.output
    assert "optimizer acceptance report status is not accepted" in result.output
