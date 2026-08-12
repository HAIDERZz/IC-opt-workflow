from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hermes_workflow.approvals import (
    decide_continuation_real_run,
    decide_first_real_run,
    decide_fix_run_real_run,
)
from tests.project_factory import (
    create_generic_project,
    create_packaged_generic_project,
)
from tests.report_helpers import write_json, write_pass_reports


def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return tuple(variable["name"] for variable in payload["variables"])


def _create_project(tmp_path: Path, *, name: str = "approval_project") -> Path:
    return create_generic_project(tmp_path, name=name)


def _create_packaged_project(
    tmp_path: Path,
    *,
    name: str = "approval_project",
    created_at_utc: str = "2026-05-28T00:00:00Z",
) -> Path:
    return create_packaged_generic_project(
        tmp_path,
        name=name,
        created_at_utc=created_at_utc,
    )


def _create_packaged_fix_run_project(
    tmp_path: Path,
    *,
    name: str = "fix_run_approval_project",
    created_at_utc: str = "2026-06-16T00:00:00Z",
) -> Path:
    return create_packaged_generic_project(
        tmp_path,
        name=name,
        workflow_mode="fix_run",
        created_at_utc=created_at_utc,
    )


def _write_pass_reports(project_dir: Path) -> None:
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))


def _write_netlist_pass_report(project_dir: Path) -> None:
    approved_variables = {name: True for name in _variable_names(project_dir)}
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": approved_variables,
            "analysis_statements": ["tran", "dc"],
            "forbidden_setup_changes_detected": False,
            "issues": [],
        },
    )


def _write_dry_run_pass_report(project_dir: Path) -> None:
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


def test_approval_gate_writes_approve_instruction(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    instruction_path = project_dir / "supervisor_instruction.json"
    payload = json.loads(instruction_path.read_text(encoding="utf-8"))
    assert instruction["decision"] == "approve_first_real_run"
    assert payload["decision"] == "approve_first_real_run"
    assert payload["reason"] == "config validation and preflight reports passed"
    assert "run_standalone_spectre_optimizer" in payload["allowed_actions"]
    assert payload["approved_config_hashes"]["config/project_config.yaml"]


def test_fix_run_approval_does_not_require_optimizer_preflight_reports(
    tmp_path: Path,
) -> None:
    project_dir = _create_packaged_fix_run_project(
        tmp_path,
        name="fix_run_approval_project",
    )

    instruction = decide_fix_run_real_run(
        project_dir,
        created_at_utc="2026-06-16T00:10:00Z",
    )

    assert instruction["decision"] == "approve_first_real_run"
    assert instruction["reason"] == "fix-run config validation passed"
    assert "prepare_fixed_candidate_real_run" in instruction["allowed_actions"]
    assert "run_standalone_spectre_optimizer" in instruction["forbidden_actions"]
    assert not (project_dir / "reports" / "dry_run_report.json").exists()


def test_approval_gate_writes_reject_instruction_when_preflight_fails(
    tmp_path: Path,
) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)
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


def test_approval_gate_rejects_missing_execution_manifest(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    instruction_path = project_dir / "supervisor_instruction.json"
    payload = json.loads(instruction_path.read_text(encoding="utf-8"))
    assert instruction["decision"] == "reject_first_real_run"
    assert instruction["reason"] == "execution manifest is missing"
    assert instruction["approved_config_hashes"] == {}
    assert payload == instruction


def test_approval_gate_rejects_invalid_project_config(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)
    (project_dir / "config" / "variables.yaml").unlink()

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "config/variables.yaml" in instruction["reason"]
    assert "required config file is missing" in instruction["reason"]
    assert instruction["approved_config_hashes"]["config/project_config.yaml"]


def test_approval_gate_rejects_invalid_execution_manifest(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "execution manifest is invalid" in instruction["reason"]
    assert instruction["approved_config_hashes"] == {}


def test_approval_gate_rejects_manifest_missing_config_hashes(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest_payload["immutable_config_files"]
    write_json(manifest_path, manifest_payload)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "execution manifest is missing immutable_config_files" in instruction["reason"]
    assert instruction["approved_config_hashes"] == {}


def test_approval_gate_rejects_health_report_with_real_run_started(
    tmp_path: Path,
) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_pass_reports(project_dir)
    (project_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text("{}\n", encoding="utf-8")
    health_path = project_dir / "state" / "health_check.json"
    health_payload = json.loads(health_path.read_text(encoding="utf-8"))
    health_payload["status"] = "error"
    health_payload["real_run_started"] = True
    health_payload["issues"] = [
        "pre-approval real-run artifact exists: ledger/experiment_ledger.jsonl"
    ]
    write_json(health_path, health_payload)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "health status is error" in instruction["reason"]
    assert "real run already started before approval" in instruction["reason"]
    assert (
        "pre-approval real-run artifact exists: ledger/experiment_ledger.jsonl"
        in instruction["reason"]
    )


def test_approval_gate_rejects_missing_preflight_reports(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_dry_run_pass_report(project_dir)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "required preflight reports missing:" in instruction["reason"]
    assert "reports/netlist_preparation_report.json" in instruction["reason"]
    assert "state/health_check.json" in instruction["reason"]
    assert "reports/dry_run_report.json" not in instruction["reason"]


def test_approval_gate_rejects_missing_health_check(tmp_path: Path) -> None:
    project_dir = _create_packaged_project(tmp_path)
    _write_netlist_pass_report(project_dir)
    _write_dry_run_pass_report(project_dir)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "required preflight reports missing:" in instruction["reason"]
    assert "state/health_check.json" in instruction["reason"]
    assert "reports/netlist_preparation_report.json" not in instruction["reason"]


def test_approval_gate_preserves_strict_loading_for_malformed_present_report(
    tmp_path: Path,
) -> None:
    project_dir = _create_packaged_project(tmp_path)
    (project_dir / "reports").mkdir(parents=True, exist_ok=True)
    (project_dir / "reports" / "netlist_preparation_report.json").write_text(
        "not-valid-json", encoding="utf-8"
    )
    (project_dir / "reports" / "dry_run_report.json").write_text("{}", encoding="utf-8")
    (project_dir / "state").mkdir(parents=True, exist_ok=True)
    (project_dir / "state" / "health_check.json").write_text("{}", encoding="utf-8")

    with pytest.raises((json.JSONDecodeError, ValueError)):
        decide_first_real_run(
            project_dir,
            created_at_utc="2026-05-28T00:10:00Z",
        )


def test_approval_gate_handles_missing_project_dir_for_instruction(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "nonexistent"
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )
    assert instruction["decision"] == "reject_first_real_run"
    assert (project_dir / "supervisor_instruction.json").exists()


def test_optimizer_approval_still_requires_preflight_reports(tmp_path: Path) -> None:
    """Optimizer mode must keep its full preflight gate even after the
    fix-run approval was added. This locks in that the fix did not
    weaken the optimizer path."""
    project_dir = _create_packaged_project(
        tmp_path,
        name="optimizer_preflight_regression",
        created_at_utc="2026-06-16T00:00:00Z",
    )
    # Intentionally do NOT call _write_pass_reports -- preflight is missing.

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-16T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "required preflight reports missing" in instruction["reason"]
    assert "reports/dry_run_report.json" in instruction["reason"]
    assert "state/health_check.json" in instruction["reason"]


def test_fix_run_approval_uses_distinct_allowed_actions(tmp_path: Path) -> None:
    """fix-run approval must NOT grant the optimizer-only action
    ``run_standalone_spectre_optimizer``; it must grant the fix-run-only
    action ``prepare_fixed_candidate_real_run``."""
    project_dir = _create_packaged_fix_run_project(
        tmp_path,
        name="fix_run_distinct_actions",
    )

    instruction = decide_fix_run_real_run(
        project_dir,
        created_at_utc="2026-06-16T00:10:00Z",
    )

    assert instruction["decision"] == "approve_first_real_run"
    assert "prepare_fixed_candidate_real_run" in instruction["allowed_actions"]
    assert "run_standalone_spectre_optimizer" not in instruction["allowed_actions"]
    assert "run_standalone_spectre_optimizer" in instruction["forbidden_actions"]


def test_continuation_approval_approves_without_preflight_reports(
    tmp_path: Path,
) -> None:
    """Continuation rebuilds its controller cache from the frozen snapshot, so
    the optimizer preflight reports are replaced by prior-history acceptance
    and must not be required for the continuation approval."""
    project_dir = _create_packaged_project(
        tmp_path,
        name="continuation_approval_project",
    )

    instruction = decide_continuation_real_run(
        project_dir,
        created_at_utc="2026-08-12T00:10:00Z",
    )

    instruction_path = project_dir / "supervisor_instruction.json"
    payload = json.loads(instruction_path.read_text(encoding="utf-8"))
    assert instruction["decision"] == "approve_first_real_run"
    assert payload["decision"] == "approve_first_real_run"
    assert instruction["reason"] == "continuation config validation passed"
    assert "run_standalone_spectre_optimizer" in instruction["allowed_actions"]
    assert payload["approved_config_hashes"]["config/project_config.yaml"]
    assert not (project_dir / "reports" / "dry_run_report.json").exists()


def test_continuation_approval_rejects_manifest_missing_config_hashes(
    tmp_path: Path,
) -> None:
    project_dir = _create_packaged_project(
        tmp_path,
        name="continuation_reject_project",
    )
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest_payload["immutable_config_files"]
    write_json(manifest_path, manifest_payload)

    instruction = decide_continuation_real_run(
        project_dir,
        created_at_utc="2026-08-12T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "execution manifest is missing immutable_config_files" in instruction["reason"]
    assert "run_standalone_spectre_optimizer" in instruction["forbidden_actions"]
