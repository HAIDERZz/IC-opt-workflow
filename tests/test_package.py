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


def test_build_execution_package_writes_execution_task(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")

    task_text = (project_dir / "execution_package" / "EXECUTION_TASK.md").read_text(
        encoding="utf-8"
    )
    assert "# Claude Code Execution Task" in task_text
    assert "Project: `bridge_test_inv`" in task_text
    assert "Backend: `maestro_exported_spectre_deck`" in task_text
    assert "Spectre X preset: `ax`" in task_text
    assert "`FN`, `WN`, `FP`, `WP`" in task_text
    assert (
        "Hermes may template only these variables in `netlists/templates/template.scs`"
        in task_text
    )
    assert "Do not modify Maestro setup" in task_text
    assert (
        "Template only approved variables when Hermes prepares "
        "`netlists/templates/template.scs`"
    ) in task_text
    assert (
        "Wait for `supervisor_instruction.json` before the first real Spectre run"
        in task_text
    )
    assert "Export or place the Spectre deck at `netlists/exported/input.scs`" in task_text
    assert "Do not write `reports/netlist_preparation_report.json`" in task_text
    assert "Do not write `reports/dry_run_report.json`" in task_text
    assert "Do not write `state/health_check.json`" in task_text
    assert "hermes-workflow prepare-netlist PROJECT_DIR" in task_text
    assert "hermes-workflow dry-run PROJECT_DIR" in task_text
    assert "hermes-workflow preflight-health PROJECT_DIR" in task_text
    assert "hermes-workflow approve PROJECT_DIR" in task_text
    assert "Only template these variables in the exported Spectre deck" not in task_text
    assert "Write `reports/netlist_preparation_report.json`" not in task_text


def test_build_execution_package_keeps_preflight_report_manifest_paths(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")

    manifest_payload = json.loads(
        (project_dir / "execution_package" / "execution_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest_payload["required_preflight_reports"] == [
        "reports/netlist_preparation_report.json",
        "reports/dry_run_report.json",
        "state/health_check.json",
    ]


def test_build_execution_package_cleans_up_on_failure_and_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil as _shutil

    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    execution_dir = project_dir / "execution_package"
    original_copy2 = _shutil.copy2

    call_count = 0

    def failing_copy2(src, dst, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise OSError("simulated copy failure")
        return original_copy2(src, dst, **kwargs)

    monkeypatch.setattr(_shutil, "copy2", failing_copy2)

    with pytest.raises(OSError, match="simulated copy failure"):
        build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")

    assert not execution_dir.exists(), "execution_package should be cleaned up"

    monkeypatch.undo()
    manifest = build_execution_package(
        project_dir, created_at_utc="2026-05-28T00:00:00Z"
    )
    assert manifest.path.exists()
    for file_name in CONFIG_FILE_NAMES:
        assert (execution_dir / "config" / file_name).exists()
