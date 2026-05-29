from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_pass_reports(project_dir: Path) -> None:
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": {
                "FN": True,
                "WN": True,
                "FP": True,
                "WP": True,
            },
            "analysis_statements": ["tran", "dc"],
            "forbidden_setup_changes_detected": False,
            "issues": [],
        },
    )
    write_json(
        project_dir / "reports" / "dry_run_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "rendered_candidate_scs": "runs/dry_run/input.scs",
            "placeholder_check": {
                "unresolved_placeholders": [],
                "unexpected_template_variables": [],
            },
            "metrics_import_ok": True,
            "mock_metrics_ok": True,
            "objective_ok": True,
            "constraints_ok": True,
            "ledger_write_ok": True,
            "state_write_ok": True,
            "issues": [],
        },
    )
    write_json(
        project_dir / "state" / "health_check.json",
        {
            "schema_version": "1.0",
            "status": "healthy",
            "real_run_started": False,
            "current_evaluations": 0,
            "best_candidate_path": None,
            "last_batch_id": None,
            "issues": [],
        },
    )
