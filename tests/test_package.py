import json
from hashlib import sha256
from importlib import resources
from pathlib import Path

import pytest

from hermes_workflow.package import (
    CONFIG_FILE_NAMES,
    TemplateError,
    build_execution_package,
    create_project_from_template,
)
from hermes_workflow.validate import validate_project_files


def test_create_project_from_template_writes_expected_tree(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"

    create_project_from_template(project_dir)

    assert (project_dir / "TASK.md").exists()
    assert (project_dir / "METRICS.md").exists()
    assert (project_dir / "config" / "project_config.yaml").exists()
    assert (project_dir / "netlists" / "exported").is_dir()
    assert (project_dir / "netlists" / "templates").is_dir()
    assert (project_dir / "execution_package").is_dir()
    assert (project_dir / "reports").is_dir()
    assert validate_project_files(project_dir).ok is True


def test_create_project_from_template_preserves_gitkeep_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    expected_gitkeep_files = [
        "netlists/exported/.gitkeep",
        "netlists/templates/.gitkeep",
        "src/.gitkeep",
        "execution_package/.gitkeep",
        "ledger/.gitkeep",
        "state/.gitkeep",
        "reports/.gitkeep",
    ]

    create_project_from_template(project_dir)

    for relative_path in expected_gitkeep_files:
        assert (project_dir / relative_path).is_file()


def test_create_project_from_template_refuses_non_empty_destination(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    project_dir.mkdir()
    (project_dir / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(
        TemplateError,
        match="destination already exists and is not empty",
    ):
        create_project_from_template(project_dir)


def test_create_project_from_template_force_recreates_destination(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    project_dir.mkdir()
    stale_file = project_dir / "stale.txt"
    stale_file.write_text("remove me", encoding="utf-8")

    create_project_from_template(project_dir, force=True)

    assert not stale_file.exists()
    assert (project_dir / "TASK.md").exists()
    assert validate_project_files(project_dir).ok is True


def test_create_project_from_template_rejects_file_destination(tmp_path: Path) -> None:
    project_file = tmp_path / "bridge_test_inv"
    project_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(
        TemplateError,
        match="destination exists and is not a directory",
    ):
        create_project_from_template(project_file)


def test_project_template_is_packaged_with_hermes_workflow() -> None:
    template = resources.files("hermes_workflow").joinpath(
        "templates",
        "spectre_maestro_project",
    )

    assert template.is_dir()
    assert template.joinpath("TASK.md").is_file()


def test_build_execution_package_copies_config_and_records_hashes(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    manifest = build_execution_package(
        project_dir,
        created_at_utc="2026-05-28T00:00:00Z",
    )

    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest.path == manifest_path
    assert manifest_payload["schema_version"] == "1.0"
    assert manifest_payload["project_name"] == "bridge_test_inv"
    assert manifest_payload["created_at_utc"] == "2026-05-28T00:00:00Z"
    for file_name in CONFIG_FILE_NAMES:
        copied_config = project_dir / "execution_package" / "config" / file_name
        source_config = project_dir / "config" / file_name
        expected_hash = sha256(source_config.read_bytes()).hexdigest()

        assert copied_config.read_text(encoding="utf-8") == source_config.read_text(
            encoding="utf-8"
        )
        assert (
            manifest_payload["immutable_config_files"][f"config/{file_name}"]
            == expected_hash
        )


def test_build_execution_package_refuses_existing_manifest(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")

    with pytest.raises(FileExistsError, match="execution package already exists"):
        build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")


def test_build_execution_package_reports_missing_config_file(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    (project_dir / "config" / "optimizer.yaml").unlink()

    with pytest.raises(ValueError, match="config/optimizer.yaml"):
        build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")
