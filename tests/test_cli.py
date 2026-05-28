from typer.testing import CliRunner

from hermes_workflow.cli import app


runner = CliRunner()


def test_cli_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
