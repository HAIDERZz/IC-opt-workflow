from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.health import write_preflight_health
from hermes_workflow.reports import HealthCheck, HealthStatus
from tests.project_factory import create_generic_project


def _load_health(project_dir: Path) -> HealthCheck:
    payload = json.loads(
        (project_dir / "state" / "health_check.json").read_text(encoding="utf-8")
    )
    return HealthCheck.model_validate(payload)


def test_write_preflight_health_writes_healthy_payload(tmp_path: Path) -> None:
    project_dir = create_generic_project(tmp_path)

    report = write_preflight_health(project_dir)

    persisted = _load_health(project_dir)
    assert report == persisted
    assert report.schema_version == "1.0"
    assert report.status == HealthStatus.HEALTHY
    assert report.real_run_started is False
    assert report.current_evaluations == 0
    assert report.best_candidate_path is None
    assert report.last_batch_id is None
    assert report.issues == []


def test_write_preflight_health_fails_closed_for_real_run_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "state" / "best_candidate.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "state" / "optimizer_state.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    report = write_preflight_health(project_dir)

    persisted = _load_health(project_dir)
    assert report == persisted
    assert report.status == HealthStatus.ERROR
    assert report.real_run_started is True
    assert report.best_candidate_path == "state/best_candidate.json"
    assert (
        "pre-approval real-run artifact exists: ledger/experiment_ledger.jsonl"
        in report.issues
    )
    assert (
        "pre-approval real-run artifact exists: state/best_candidate.json"
        in report.issues
    )
    assert (
        "pre-approval real-run artifact exists: state/optimizer_state.json"
        in report.issues
    )
    assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert (project_dir / "state" / "best_candidate.json").exists()
    assert (project_dir / "state" / "optimizer_state.json").exists()


def test_write_preflight_health_does_not_fabricate_report_for_invalid_config(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)
    (project_dir / "config" / "variables.yaml").unlink()

    with pytest.raises(ValueError, match="config/variables.yaml"):
        write_preflight_health(project_dir)

    assert not (project_dir / "state" / "health_check.json").exists()
