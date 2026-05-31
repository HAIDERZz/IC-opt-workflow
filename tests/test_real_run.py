from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow import real_run
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
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


def test_prepare_real_run_writes_first_real_run_package(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:20:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    rendered = (run_dir / "input.scs").read_text(encoding="utf-8")
    candidate = _load_json(run_dir / "candidate.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")

    assert package.run_id == "real_001"
    assert package.run_dir == run_dir
    assert package.rendered_input_scs == run_dir / "input.scs"
    assert package.candidate_path == run_dir / "candidate.json"
    assert package.manifest_path == run_dir / "real_run_manifest.json"
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "FN=2" in rendered
    assert "WN=0.3 um" in rendered
    assert "FP=2" in rendered
    assert "WP=0.3 um" in rendered
    assert candidate == {
        "schema_version": "1.0",
        "candidate_id": "real_001",
        "source": "lower_bound_first_real_run",
        "parameters": {
            "FN": "2",
            "WN": "0.3 um",
            "FP": "2",
            "WP": "0.3 um",
        },
    }
    assert manifest["schema_version"] == "1.0"
    assert manifest["run_id"] == "real_001"
    assert manifest["project_name"] == "bridge_test_inv"
    assert manifest["created_at_utc"] == "2026-05-31T00:20:00Z"
    assert manifest["status"] == "prepared"
    assert manifest["supervisor_decision"] == "approve_first_real_run"
    assert manifest["template_scs"] == "netlists/templates/template.scs"
    assert manifest["rendered_input_scs"] == "runs/real/real_001/input.scs"
    assert manifest["candidate_file"] == "runs/real/real_001/candidate.json"
    assert manifest["candidate_id"] == "real_001"
    assert manifest["candidate_source"] == "lower_bound_first_real_run"
    assert manifest["template_sha256"] == sha256_file(
        project_dir / "netlists" / "templates" / "template.scs"
    )
    assert manifest["rendered_input_sha256"] == sha256_file(run_dir / "input.scs")
    assert manifest["approved_config_hashes"]["config/project_config.yaml"]
    assert manifest["spectre"] == {
        "engine": "spectre_x",
        "preset": "ax",
        "output_format": "psfascii",
        "parallel_jobs": 10,
        "timeout_s": 3600,
    }
    assert "modify_maestro_setup" in manifest["forbidden_actions"]
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_prepare_real_run_accepts_valid_custom_run_id(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        run_id="real_007",
        created_at_utc="2026-05-31T00:20:00Z",
    )

    manifest = _load_json(
        project_dir / "runs" / "real" / "real_007" / "real_run_manifest.json"
    )
    assert package.run_id == "real_007"
    assert manifest["run_id"] == "real_007"
    assert manifest["candidate_id"] == "real_007"
    assert manifest["rendered_input_scs"] == "runs/real/real_007/input.scs"


def test_prepare_real_run_rejects_placeholder_candidate_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    def placeholder_candidate(_bundle, run_id: str) -> dict:
        return {
            "schema_version": "1.0",
            "candidate_id": run_id,
            "source": "lower_bound_first_real_run",
            "parameters": {
                "FN": "{{WN}}",
                "WN": "0.3 um",
                "FP": "2",
                "WP": "0.3 um",
            },
        }

    monkeypatch.setattr(real_run, "_lower_bound_candidate", placeholder_candidate)

    with pytest.raises(
        ValueError,
        match="candidate parameter values must not contain placeholders: FN",
    ):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()
