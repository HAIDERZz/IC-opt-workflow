from __future__ import annotations

import json
from pathlib import Path

import yaml


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _approved_variable_names(project_dir: Path) -> dict[str, bool]:
    """Derive the approved-variable status from the project's own config.

    The helper must not hardcode one release template's variable names; it
    reports every variable declared in ``config/variables.yaml`` as templated.
    """
    variables_path = Path(project_dir) / "config" / "variables.yaml"
    if not variables_path.exists():
        return {}
    payload = yaml.safe_load(variables_path.read_text(encoding="utf-8")) or {}
    variables = payload.get("variables") if isinstance(payload, dict) else None
    if not isinstance(variables, list):
        return {}
    return {
        str(variable["name"]): True
        for variable in variables
        if isinstance(variable, dict) and "name" in variable
    }


def write_pass_reports(project_dir: Path) -> None:
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": _approved_variable_names(project_dir),
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
