from __future__ import annotations

from hermes_workflow.optimizer_html_report import render_optimizer_insight_html


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
