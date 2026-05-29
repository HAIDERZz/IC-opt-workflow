import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from tests.report_helpers import write_pass_reports


runner = CliRunner()


def test_cli_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_init_and_validate(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"

    init_result = runner.invoke(app, ["init", str(project_dir)])
    validate_result = runner.invoke(app, ["validate", str(project_dir)])

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "validation passed" in validate_result.stdout


def test_cli_package_and_approve(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    package_result = runner.invoke(app, ["package", str(project_dir)])
    write_pass_reports(project_dir)
    approve_result = runner.invoke(app, ["approve", str(project_dir)])

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert package_result.exit_code == 0
    assert "execution_package/execution_manifest.json" in package_result.stdout
    assert approve_result.exit_code == 0
    assert instruction["decision"] == "approve_first_real_run"
