from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    return project_dir


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")


def _approve_project(project_dir: Path) -> None:
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_real_run_rejects_missing_supervisor_instruction(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    _write_template(project_dir)

    with pytest.raises(FileNotFoundError, match="supervisor instruction is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_reject_instruction(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "reject_first_real_run",
                "reason": "not ready",
                "allowed_actions": [],
                "forbidden_actions": ["run_standalone_spectre_optimizer"],
                "approved_config_hashes": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(ValueError, match="first real run is not approved"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_missing_execution_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _write_template(project_dir)
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps({"decision": "approve_first_real_run"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="execution manifest is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_config_drift_after_approval(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    variables_path = project_dir / "config" / "variables.yaml"
    variables_path.write_text(
        variables_path.read_text(encoding="utf-8").replace(
            'upper: "12"', 'upper: "14"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="immutable config drift detected: config/variables.yaml"
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_missing_approved_hashes(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved without hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor instruction is missing approved_config_hashes",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_hash_mismatch(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    manifest = build_execution_package(
        project_dir,
        created_at_utc="2026-05-31T00:00:00Z",
    )
    approved_hashes = dict(manifest.payload["immutable_config_files"])
    approved_hashes["config/variables.yaml"] = "not-the-approved-hash"
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved with wrong hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
                "approved_config_hashes": approved_hashes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor approved config hashes do not match execution manifest",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()
