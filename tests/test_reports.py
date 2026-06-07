from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.reports import load_preflight_reports
from tests.report_helpers import write_json, write_pass_reports


def test_load_preflight_reports_accepts_pass_reports(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    write_pass_reports(project_dir)

    reports = load_preflight_reports(project_dir)

    assert reports.ready is True
    assert reports.messages == []


def test_load_preflight_reports_rejects_failed_dry_run(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    write_pass_reports(project_dir)
    dry_run_path = project_dir / "reports" / "dry_run_report.json"
    payload = json.loads(dry_run_path.read_text(encoding="utf-8"))
    payload["status"] = "fail"
    payload["issues"] = ["objective evaluation failed"]
    write_json(dry_run_path, payload)

    reports = load_preflight_reports(project_dir)

    assert reports.ready is False
    assert "dry run status is fail" in reports.messages
    assert "objective evaluation failed" in reports.messages
