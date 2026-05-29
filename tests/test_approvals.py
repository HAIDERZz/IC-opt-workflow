from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from tests.report_helpers import write_json, write_pass_reports


def test_approval_gate_writes_approve_instruction(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")
    write_pass_reports(project_dir)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    instruction_path = project_dir / "supervisor_instruction.json"
    payload = json.loads(instruction_path.read_text(encoding="utf-8"))
    assert instruction["decision"] == "approve_first_real_run"
    assert payload["decision"] == "approve_first_real_run"
    assert "run_standalone_spectre_optimizer" in payload["allowed_actions"]
    assert payload["approved_config_hashes"]["config/project_config.yaml"]


def test_approval_gate_writes_reject_instruction_when_preflight_fails(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")
    write_pass_reports(project_dir)
    dry_run_path = project_dir / "reports" / "dry_run_report.json"
    dry_run_payload = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run_payload["status"] = "fail"
    dry_run_payload["issues"] = ["mock metric failed"]
    write_json(dry_run_path, dry_run_payload)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "dry run status is fail" in instruction["reason"]
    assert "mock metric failed" in instruction["reason"]
