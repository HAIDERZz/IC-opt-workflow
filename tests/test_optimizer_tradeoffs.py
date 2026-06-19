from __future__ import annotations

from hermes_workflow.optimizer_tradeoffs import build_pareto_tradeoff_summary


def test_pareto_tradeoff_requires_two_inferred_metric_directions() -> None:
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"W": "1u"},
            "metrics": {"gain": 12.0, "phase": 60.0},
            "objective": -12.0,
            "constraint_penalty": 0.0,
        }
    ]
    metric_contract = {
        "constraints": [{"metric": "gain", "op": "ge", "value": "10"}],
    }

    summary = build_pareto_tradeoff_summary(traces, metric_contract)

    assert summary["status"] == "not_available"
    assert summary["reason"] == "fewer than two trade-off metrics have inferred directions"
    assert summary["optimizer_mode_changed"] is False
    assert summary["metric_directions"] == {"gain": "maximize"}
    assert summary["unscored_metrics"] == ["phase"]


def test_pareto_tradeoff_computes_feasible_non_dominated_front() -> None:
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"W": "1u"},
            "metrics": {"gain": 10.0, "power": 1.0},
            "objective": -1.0,
            "constraint_penalty": 0.0,
        },
        {
            "evaluation_index": 2,
            "run_id": "real_002",
            "status": "feasible",
            "parameters": {"W": "2u"},
            "metrics": {"gain": 12.0, "power": 1.5},
            "objective": -2.0,
            "constraint_penalty": 0.0,
        },
        {
            "evaluation_index": 3,
            "run_id": "real_003",
            "status": "feasible",
            "parameters": {"W": "3u"},
            "metrics": {"gain": 9.0, "power": 1.2},
            "objective": -0.5,
            "constraint_penalty": 0.0,
        },
    ]
    metric_contract = {
        "constraints": [
            {"metric": "gain", "op": "ge", "value": "9"},
            {"metric": "power", "op": "le", "value": "2"},
        ],
    }

    summary = build_pareto_tradeoff_summary(traces, metric_contract)

    assert summary["status"] == "available"
    assert summary["mode"] == "report_layer_raw_metric_tradeoff"
    assert summary["optimizer_mode_changed"] is False
    assert summary["source"] == "existing_optimizer_raw_metrics"
    assert summary["openbox_utility"] == "openbox.utils.multi_objective.get_pareto_front"
    assert summary["metric_directions"] == {"gain": "maximize", "power": "minimize"}
    assert summary["eligible_count"] == 3
    assert summary["front_count"] == 2
    assert summary["dominated_count"] == 1
    assert [row["run_id"] for row in summary["front_candidates"]] == [
        "real_001",
        "real_002",
    ]


def test_pareto_tradeoff_skips_rows_missing_required_metrics() -> None:
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"W": "1u"},
            "metrics": {"gain": 10.0, "power": 1.0},
        },
        {
            "evaluation_index": 2,
            "run_id": "real_002",
            "status": "failed",
            "parameters": {"W": "2u"},
            "metrics": {"gain": 12.0},
        },
    ]
    metric_contract = {
        "constraints": [
            {"metric": "gain", "op": "ge", "value": "9"},
            {"metric": "power", "op": "le", "value": "2"},
        ],
    }

    summary = build_pareto_tradeoff_summary(traces, metric_contract)

    assert summary["status"] == "not_available"
    assert summary["reason"] == "fewer than two eligible rows contain all trade-off metrics"
    assert summary["eligible_count"] == 1
