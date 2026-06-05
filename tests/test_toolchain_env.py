import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.toolchain_env import PythonProbeResult, check_toolchain_environment


runner = CliRunner()


def test_check_toolchain_environment_passes_with_injected_probe(tmp_path: Path) -> None:
    venv = tmp_path / "openbox-venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    python_path = bin_dir / "python"
    hermes_script = bin_dir / "hermes-workflow"
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    hermes_script.write_text("#!/bin/sh\n", encoding="utf-8")
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# cadence\n", encoding="utf-8")

    def probe(_python_path: Path, _script: str, _timeout_s: int) -> PythonProbeResult:
        return PythonProbeResult(
            return_code=0,
            stdout='{"python_executable": "/fake/python"}',
            stderr="",
        )

    report = check_toolchain_environment(
        openbox_venv=venv,
        cadence_cshrc=cadence_cshrc,
        probe_runner=probe,
    )

    assert report["status"] == "pass"
    assert report["openbox_venv"] == str(venv)
    assert report["cadence_cshrc"] == str(cadence_cshrc)
    assert report["issues"] == []
    assert {check["name"]: check["status"] for check in report["checks"]} == {
        "openbox_venv_exists": "pass",
        "openbox_python_exists": "pass",
        "hermes_workflow_script_exists": "pass",
        "cadence_cshrc_exists": "pass",
        "openbox_and_hermes_import": "pass",
    }


def test_check_toolchain_environment_fails_when_import_probe_fails(
    tmp_path: Path,
) -> None:
    venv = tmp_path / "openbox-venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "hermes-workflow").write_text("#!/bin/sh\n", encoding="utf-8")
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# cadence\n", encoding="utf-8")

    def probe(_python_path: Path, _script: str, _timeout_s: int) -> PythonProbeResult:
        return PythonProbeResult(
            return_code=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'openbox'",
        )

    report = check_toolchain_environment(
        openbox_venv=venv,
        cadence_cshrc=cadence_cshrc,
        probe_runner=probe,
    )

    assert report["status"] == "fail"
    assert "OpenBox/Hermes import probe failed" in report["issues"]


def test_check_toolchain_env_cli_writes_report(tmp_path: Path, monkeypatch) -> None:
    venv = tmp_path / "openbox-venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "hermes-workflow").write_text("#!/bin/sh\n", encoding="utf-8")
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# cadence\n", encoding="utf-8")
    report_path = tmp_path / "toolchain_environment_report.json"

    def probe(_python_path: Path, _script: str, _timeout_s: int) -> PythonProbeResult:
        return PythonProbeResult(
            return_code=0,
            stdout='{"python_executable": "/fake/python"}',
            stderr="",
        )

    monkeypatch.setattr("hermes_workflow.toolchain_env._run_python_probe", probe)

    result = runner.invoke(
        app,
        [
            "check-toolchain-env",
            "--openbox-venv",
            str(venv),
            "--cadence-cshrc",
            str(cadence_cshrc),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "toolchain environment check passed" in result.stdout
    assert str(report_path) in result.stdout
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"


def test_check_toolchain_env_cli_fails_for_missing_venv(tmp_path: Path) -> None:
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# cadence\n", encoding="utf-8")
    report_path = tmp_path / "failed_toolchain_environment_report.json"

    result = runner.invoke(
        app,
        [
            "check-toolchain-env",
            "--openbox-venv",
            str(tmp_path / "missing-venv"),
            "--cadence-cshrc",
            str(cadence_cshrc),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 1
    assert "toolchain environment check failed" in result.stdout
    assert "openbox_venv_exists missing" in result.stdout
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
