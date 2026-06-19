from __future__ import annotations

from hermes_workflow.optimizer_html_report import render_optimizer_insight_html


def _full_payload() -> dict:
    return {
        "status": "pass",
        "evaluation_count": 40,
        "status_counts": {"feasible": 2, "constraint_failed": 24},
        "best_observed": {
            "run_id": "real_022",
            "status": "feasible",
            "objective": -0.037,
            "parameters": {"F": "28", "W": "0.8u"},
            "metrics": {"BW": 20.8e9, "MAX_GAIN": 4.07, "NF_3G": 11.83},
            "metric_result_manifest": "runs/real/real_022/metrics/metric_result_manifest.json",
        },
        "pareto_tradeoff_summary": {
            "status": "available",
            "eligible_count": 26,
            "front_count": 24,
            "dominated_count": 2,
        },
        "tradeoff_interpretation_summary": {
            "status": "available",
            "front_selectivity": {
                "eligible_count": 26,
                "front_count": 24,
                "ratio": 0.923,
                "usefulness": "low",
                "message": (
                    "The raw-metric Pareto front is broad and is not a useful "
                    "ranking by itself."
                ),
            },
            "constraint_blockers": [{"metric": "BW", "failed_count": 16}],
            "feasible_candidates": [
                {
                    "run_id": "real_022",
                    "objective": -0.037,
                    "parameters": {"F": "28", "W": "0.8u"},
                    "metrics": {"BW": 20.8e9, "MAX_GAIN": 4.07},
                }
            ],
            "metric_extremes": [
                {
                    "metric": "BW",
                    "direction": "maximize",
                    "run_id": "real_034",
                    "status": "constraint_failed",
                    "value": 23.25e9,
                    "parameters": {"F": "28", "W": "0.6u"},
                    "failed_constraints": ["MAX_GAIN"],
                }
            ],
        },
        "history_warm_start": {
            "status": "available",
            "application_mode": "initial_configurations_from_history",
            "accepted_observation_count": 64,
            "applied_observation_count": 8,
            "applied_to_advisor": True,
            "audit": "reports/history_warm_start_audit.json",
        },
        "history_reuse_summary": {
            "status": "available",
            "repeated_current_point_count": 16,
            "repeated_current_status_counts": {"feasible": 2, "constraint_failed": 8},
            "best_candidate_reused_history": True,
            "interpretation": (
                "History evidence was applied; repeated current points are exact "
                "parameter matches, not proof of optimizer improvement."
            ),
        },
        "space_compression_advisory": {
            "status": "available",
            "eligible_count": 26,
            "feasible_count": 2,
            "method": "r_boundary",
            "confidence": "low",
            "suggestions": [
                {
                    "variable": "VB_LO",
                    "original_display": {"lower": "150m", "upper": "350m"},
                    "suggested_display": {"lower": "150m", "upper": "330m"},
                    "compression_ratio": 0.9,
                }
            ],
        },
        "advanced_surrogate_visualization": {"status": "not_available"},
        "plots": {
            "convergence": "reports/optimizer_visuals/convergence.png",
            "status_distribution": "reports/optimizer_visuals/status_distribution.png",
        },
    }


def test_render_optimizer_insight_html_contains_required_sections() -> None:
    payload = {
        "status": "pass",
        "evaluation_count": 3,
        "status_counts": {"feasible": 2, "constraint_failed": 1},
        "best_observed": {
            "run_id": "real_002",
            "objective": -2.0,
            "parameters": {"W": "2u"},
        },
        "pareto_tradeoff_summary": {
            "status": "available",
            "front_count": 1,
            "front_candidates": [
                {
                    "run_id": "real_001",
                    "metrics": {"gain": 10.0, "power": 1.0},
                    "parameters": {"W": "1u"},
                }
            ],
        },
        "space_compression_advisory": {
            "status": "available",
            "confidence": "low",
            "suggestions": [
                {
                    "variable": "W",
                    "suggested_display": {"lower": "1u", "upper": "2u"},
                    "compression_ratio": 0.25,
                }
            ],
        },
        "openbox": {"history_warm_start": {"status": "applied"}},
        "advanced_surrogate_visualization": {
            "status": "generated",
            "html_path": "reports/openbox.html",
        },
        "plots": {},
    }

    html = render_optimizer_insight_html(payload)

    assert "<!doctype html>" in html.lower()
    assert "Optimizer Insight Report" in html
    assert "Report-layer Pareto" in html
    assert "Space Compression Advisory" in html
    assert "History Warm-start" in html
    assert "OpenBox Advanced Visualization" in html
    assert "real_002" in html
    assert "real_001" in html
    assert "optimizer mode unchanged" in html
    assert "advisory only" in html


def test_render_optimizer_insight_html_escapes_payload_values() -> None:
    payload = {
        "status": "pass",
        "evaluation_count": 1,
        "status_counts": {},
        "best_observed": {
            "run_id": "<script>alert(1)</script>",
            "objective": 1.0,
            "parameters": {"W": "<bad>"},
        },
        "pareto_tradeoff_summary": {"status": "not_available"},
        "space_compression_advisory": {"status": "not_available"},
        "advanced_surrogate_visualization": {},
        "plots": {},
    }

    html = render_optimizer_insight_html(payload)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;bad&gt;" in html


# ---------------------------------------------------------------------------
# Task 4: readable HTML redesign tests
# ---------------------------------------------------------------------------


def test_html_includes_readable_best_point_metrics() -> None:
    html = render_optimizer_insight_html(_full_payload())

    assert "Best point metrics" in html
    assert "MAX_GAIN" in html
    assert "4.07" in html
    assert "NF_3G" in html


def test_html_includes_broad_front_warning_without_json_fields() -> None:
    html = render_optimizer_insight_html(_full_payload())

    assert "The raw-metric Pareto front is broad" in html
    assert "constraint_blockers" not in html
    assert "metric_extremes" not in html
    assert "front_selectivity" not in html


def test_html_includes_not_available_tradeoff_message() -> None:
    payload = _full_payload()
    payload["tradeoff_interpretation_summary"] = {
        "status": "not_available",
        "front_selectivity": {
            "eligible_count": 0,
            "front_count": 0,
            "ratio": 0.0,
            "usefulness": "not_available",
            "message": (
                "Report-layer trade-off analysis is not available: fewer than two "
                "inferred trade-off metrics."
            ),
        },
        "constraint_blockers": [],
        "feasible_candidates": [],
        "metric_extremes": [],
    }

    html = render_optimizer_insight_html(payload)

    assert "Report-layer trade-off analysis is not available" in html
    assert "not_available" in html


def test_html_includes_readable_history_reuse_without_json_fields() -> None:
    html = render_optimizer_insight_html(_full_payload())

    assert "History evidence was applied" in html
    assert "repeated_current_point_count" not in html
    assert "repeated_current_status_counts" not in html


def test_html_includes_large_plot_gallery() -> None:
    html = render_optimizer_insight_html(_full_payload())

    assert "plot-gallery" in html
    assert "minmax(min(100%, 520px), 1fr)" in html
    assert "min-height: 320px" in html


def test_html_includes_debug_artifacts_section() -> None:
    html = render_optimizer_insight_html(_full_payload())

    assert "Debug artifacts" in html or "Raw evidence" in html
    assert "optimizer_insight_report.json" in html
    assert "history_warm_start_audit.json" in html
    # Artifact index must not be a raw JSON block as its main body.
    assert "<pre>" not in html.split("Debug artifacts")[1].split("</section>")[0] if "Debug artifacts" in html else True
