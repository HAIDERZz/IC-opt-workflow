from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.reports import REQUIRED_PREFLIGHT_REPORT_PATHS, load_preflight_reports
from hermes_workflow.validate import validate_project_files


def decide_first_real_run(
    project_dir: Path,
    *,
    created_at_utc: str | None = None,
) -> dict:
    project_dir = Path(project_dir)
    created_at = created_at_utc or (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    validation_report = validate_project_files(project_dir)
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"

    if not manifest_path.exists():
        instruction = _reject(created_at, "execution manifest is missing", {})
        return _write_instruction(project_dir, instruction)

    approved_hashes, manifest_error = _load_approved_config_hashes(manifest_path)
    if manifest_error is not None:
        instruction = _reject(created_at, manifest_error, {})
        return _write_instruction(project_dir, instruction)

    if not validation_report.ok:
        instruction = _reject(created_at, validation_report.format(), approved_hashes)
        return _write_instruction(project_dir, instruction)

    missing_reports = _missing_preflight_report_files(project_dir)
    if missing_reports:
        instruction = _reject(
            created_at,
            f"required preflight reports missing: {', '.join(missing_reports)}",
            approved_hashes,
        )
        return _write_instruction(project_dir, instruction)

    preflight = load_preflight_reports(project_dir)
    if not preflight.ready:
        instruction = _reject(created_at, "; ".join(preflight.messages), approved_hashes)
        return _write_instruction(project_dir, instruction)

    instruction = {
        "schema_version": "1.0",
        "created_at_utc": created_at,
        "decision": "approve_first_real_run",
        "reason": "config validation and preflight reports passed",
        "allowed_actions": ["run_standalone_spectre_optimizer"],
        "forbidden_actions": [
            "modify_maestro_setup",
            "modify_immutable_config_files",
            "change_variable_bounds",
            "change_objective_or_constraints",
        ],
        "approved_config_hashes": approved_hashes,
    }
    return _write_instruction(project_dir, instruction)


def _reject(created_at_utc: str, reason: str, approved_hashes: dict[str, str]) -> dict:
    return {
        "schema_version": "1.0",
        "created_at_utc": created_at_utc,
        "decision": "reject_first_real_run",
        "reason": reason,
        "allowed_actions": [
            "write_escalation_report",
            "revise_execution_package_after_hermes_instruction",
        ],
        "forbidden_actions": ["run_standalone_spectre_optimizer"],
        "approved_config_hashes": approved_hashes,
    }


def _load_approved_config_hashes(path: Path) -> tuple[dict[str, str], str | None]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"execution manifest is invalid: {exc.msg}"

    if not isinstance(manifest, dict):
        return {}, "execution manifest is invalid: expected JSON object"

    approved_hashes = manifest.get("immutable_config_files")
    if not isinstance(approved_hashes, dict):
        return {}, "execution manifest is missing immutable_config_files"
    return approved_hashes, None


def _missing_preflight_report_files(project_dir: Path) -> list[str]:
    return [
        rel_path
        for rel_path in REQUIRED_PREFLIGHT_REPORT_PATHS
        if not (project_dir / rel_path).exists()
    ]


def _write_instruction(project_dir: Path, instruction: dict) -> dict:
    path = Path(project_dir) / "supervisor_instruction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(instruction, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return instruction
