from importlib import resources
from pathlib import Path

import pytest

from hermes_workflow.package import TemplateError, create_project_from_template
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
