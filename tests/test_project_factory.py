from __future__ import annotations

import json
from pathlib import Path

import yaml

from hermes_workflow.validate import assert_valid_project, validate_project_files
from tests.project_factory import (
    create_approved_generic_project,
    create_generic_project,
    create_packaged_generic_project,
)


def test_create_generic_project_is_valid_and_template_independent(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path)

    assert project_dir.name == "generic_project"
    assert validate_project_files(project_dir).ok is True
    assert_valid_project(project_dir)
    variables = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    variable_names = [entry["name"] for entry in variables["variables"]]
    assert variable_names == ["VAR_INT", "VAR_WIDTH"]
    assert "bridge_test_inv" not in (
        project_dir / "config" / "project_config.yaml"
    ).read_text(encoding="utf-8")


def test_create_packaged_generic_project_writes_execution_manifest(
    tmp_path: Path,
) -> None:
    project_dir = create_packaged_generic_project(tmp_path)

    manifest = json.loads(
        (
            project_dir / "execution_package" / "execution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["project_name"] == "generic_project"
    assert "config/variables.yaml" in manifest["immutable_config_files"]


def test_create_approved_generic_project_approves_first_real_run(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_generic_project(tmp_path)

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert instruction["decision"] == "approve_first_real_run"
    report = json.loads(
        (project_dir / "reports" / "netlist_preparation_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["approved_variables_template_status"] == {
        "VAR_INT": True,
        "VAR_WIDTH": True,
    }
