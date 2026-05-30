from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.reports import HealthCheck, HealthStatus
from hermes_workflow.validate import assert_valid_project


REAL_RUN_ARTIFACTS = (
    "ledger/experiment_ledger.jsonl",
    "state/optimizer_state.json",
    "state/best_candidate.json",
)


def write_preflight_health(project_dir: Path) -> HealthCheck:
    project_dir = Path(project_dir)
    assert_valid_project(project_dir)

    detected = [
        relative_path
        for relative_path in REAL_RUN_ARTIFACTS
        if (project_dir / relative_path).exists()
    ]
    report = HealthCheck(
        schema_version="1.0",
        status=HealthStatus.ERROR if detected else HealthStatus.HEALTHY,
        real_run_started=bool(detected),
        current_evaluations=0,
        best_candidate_path=(
            "state/best_candidate.json"
            if (project_dir / "state" / "best_candidate.json").exists()
            else None
        ),
        last_batch_id=None,
        issues=[
            f"pre-approval real-run artifact exists: {relative_path}"
            for relative_path in detected
        ],
    )
    _write_health(project_dir, report)
    return report


def _write_health(project_dir: Path, report: HealthCheck) -> None:
    report_path = project_dir / "state" / "health_check.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
