from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.optimizer_report_interpretation import (
    build_history_reuse_summary,
    build_tradeoff_interpretation_summary,
)


def _row(
    run_id: str,
    *,
    status: str,
    objective: float,
    gain: float,
    bw: float,
    nf: float,
    w: str,
) -> dict:
    return {
        "run_id": run_id,
        "evaluation_index": int(run_id.removeprefix("real_")),
        "status": status,
        "objective": objective,
        "parameters": {"W": w},
        "metrics": {"gain": gain, "BW": bw, "NF": nf},
        "issues": [],
    }


def test_tradeoff_summary_marks_broad_pareto_front_as_low_selectivity() -> None:
    traces = [
        _row("real_001", status="feasible", objective=1.0, gain=10, bw=20e9, nf=11.5, w="1u"),
        _row("real_002", status="feasible", objective=2.0, gain=12, bw=18e9, nf=11.4, w="1.2u"),
        _row("real_003", status="constraint_failed", objective=1000000.0, gain=3, bw=18e9, nf=13.0, w="0.8u"),
    ]
    metric_contract = {
        "constraints": [
            {"metric": "gain", "op": "gt", "value": "4"},
            {"metric": "BW", "op": "gt", "value": "19e9"},
            {"metric": "NF", "op": "lt", "value": "12"},
        ]
    }
    pareto_summary = {
        "status": "available",
        "eligible_count": 3,
        "front_count": 3,
        "dominated_count": 0,
        "metric_directions": {"gain": "maximize", "BW": "maximize", "NF": "minimize"},
    }

    summary = build_tradeoff_interpretation_summary(
        traces=traces,
        metric_contract=metric_contract,
        pareto_summary=pareto_summary,
    )

    assert summary["status"] == "available"
    assert summary["front_selectivity"]["ratio"] == 1.0
    assert summary["front_selectivity"]["usefulness"] == "low"
    assert "not a useful ranking" in summary["front_selectivity"]["message"]
    assert summary["constraint_blockers"] == [
        {"metric": "BW", "failed_count": 2},
        {"metric": "gain", "failed_count": 1},
        {"metric": "NF", "failed_count": 1},
    ]
    assert [row["run_id"] for row in summary["feasible_candidates"]] == [
        "real_001",
        "real_002",
    ]


def test_tradeoff_summary_preserves_not_available_pareto_status() -> None:
    summary = build_tradeoff_interpretation_summary(
        traces=[],
        metric_contract={},
        pareto_summary={
            "status": "not_available",
            "reason": "fewer than two inferred trade-off metrics",
            "eligible_count": 0,
            "front_count": 0,
        },
    )

    assert summary == {
        "status": "not_available",
        "mode": "scripted_factual_summary",
        "confidence_boundary": "facts_and_rule_based_notes_only",
        "reason": "fewer than two inferred trade-off metrics",
        "front_selectivity": {
            "eligible_count": 0,
            "front_count": 0,
            "ratio": 0.0,
            "usefulness": "not_available",
            "message": "Report-layer trade-off analysis is not available: fewer than two inferred trade-off metrics.",
        },
        "constraint_blockers": [],
        "feasible_candidates": [],
        "metric_extremes": [],
    }


def test_tradeoff_summary_metric_extremes_include_failed_constraints() -> None:
    traces = [
        _row("real_001", status="feasible", objective=2.0, gain=10, bw=20e9, nf=11.5, w="1u"),
        _row("real_002", status="constraint_failed", objective=1_000_000.0, gain=15, bw=17e9, nf=13.0, w="2u"),
    ]
    metric_contract = {
        "constraints": [
            {"metric": "gain", "op": "gt", "value": "4"},
            {"metric": "BW", "op": "gt", "value": "19e9"},
            {"metric": "NF", "op": "lt", "value": "12"},
        ]
    }
    pareto_summary = {
        "eligible_count": 2,
        "front_count": 1,
        "metric_directions": {"gain": "maximize", "BW": "maximize", "NF": "minimize"},
    }

    summary = build_tradeoff_interpretation_summary(
        traces=traces,
        metric_contract=metric_contract,
        pareto_summary=pareto_summary,
    )

    gain_extreme = next(item for item in summary["metric_extremes"] if item["metric"] == "gain")
    assert gain_extreme["run_id"] == "real_002"
    assert gain_extreme["failed_constraints"] == ["BW", "NF"]
    rendered = repr(summary).lower()
    assert "caused" not in rendered
    assert "recommend" not in rendered


def _write_history_audit(project_dir: Path) -> None:
    audit_payload = {
        "status": "completed",
        "accepted_observation_count": 2,
        "rejected_observation_count": 1,
        "application_mode": "initial_configurations_from_history",
        "applied_observation_count": 2,
        "openbox_transfer_learning": {"applied_to_advisor": True},
        "accepted_observations": [
            {
                "source_run_id": "real_010",
                "source_path": "/old/project",
                "parameters": {"W": "1u", "F": "24"},
                "status": "feasible",
            },
            {
                "source_run_id": "real_011",
                "source_path": "/old/project",
                "parameters": {"W": "2u", "F": "28"},
                "status": "constraint_failed",
            },
        ],
    }
    audit_path = project_dir / "reports" / "history_warm_start_audit.json"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(json.dumps(audit_payload), encoding="utf-8")


def test_history_reuse_summary_reports_repeated_current_points(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _write_history_audit(project_dir)
    traces = [
        {
            "run_id": "real_001",
            "status": "feasible",
            "objective": 1.0,
            "parameters": {"F": "24", "W": "1u"},
            "metrics": {},
        },
        {
            "run_id": "real_002",
            "status": "metric_check_failed",
            "objective": 1_000_000.0,
            "parameters": {"F": "20", "W": "1u"},
            "metrics": {},
        },
    ]
    history_summary = {
        "status": "available",
        "application_mode": "initial_configurations_from_history",
        "accepted_observation_count": 2,
        "applied_observation_count": 2,
        "applied_to_advisor": True,
        "source": "reports/optimizer_run_report.json",
    }

    summary = build_history_reuse_summary(project_dir, traces, history_summary)

    assert summary["status"] == "available"
    assert summary["application_mode"] == "initial_configurations_from_history"
    assert summary["accepted_observation_count"] == 2
    assert summary["rejected_observation_count"] == 1
    assert summary["repeated_current_point_count"] == 1
    assert summary["repeated_current_status_counts"] == {"feasible": 1}
    assert summary["best_candidate_reused_history"] is True
    assert summary["source_paths"] == ["/old/project"]
    assert summary["interpretation"] == (
        "History evidence was applied; repeated current points are exact parameter matches, not proof of optimizer improvement."
    )


def test_history_reuse_summary_missing_audit_is_available_with_zero_repeats(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    traces = [
        {
            "run_id": "real_001",
            "status": "feasible",
            "objective": 1.0,
            "parameters": {"W": "1u"},
        }
    ]
    history_summary = {
        "status": "available",
        "application_mode": "transfer_learning_history",
        "accepted_observation_count": 4,
        "applied_observation_count": 4,
        "applied_to_advisor": True,
    }

    summary = build_history_reuse_summary(project_dir, traces, history_summary)

    assert summary["status"] == "available"
    assert summary["repeated_current_point_count"] == 0
    assert summary["repeated_current_status_counts"] == {}
    assert summary["best_candidate_reused_history"] is False


def test_history_reuse_summary_missing_history_is_not_available(tmp_path: Path) -> None:
    summary = build_history_reuse_summary(tmp_path, [], {"status": "not_available"})

    assert summary["status"] == "not_available"
