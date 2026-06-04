import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_task_package import (
    build_optimizer_execution_task_package,
)
from hermes_workflow.package import create_project_from_template


runner = CliRunner()


def test_build_optimizer_execution_task_package_writes_task_and_manifest(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=100,
        cadence_cshrc=Path("/home/zzchen/cadence_ic231_env.csh"),
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_path = project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md"
    manifest_path = (
        project_dir / "execution_package" / "optimizer_execution_manifest.json"
    )
    task_text = task_path.read_text(encoding="utf-8")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert package.task_path == task_path
    assert package.manifest_path == manifest_path
    assert "run-native-turbo" in task_text
    assert "--parallel" in task_text
    assert "--max-evals 100" in task_text
    assert "Command exit status alone is not acceptance evidence" in task_text
    assert "Manifest-level audit is required" in task_text
    assert "threads_per_run" in task_text
    assert "parallel_jobs" in task_text
    assert "ledger/experiment_ledger.jsonl" in task_text
    assert manifest_payload["schema_version"] == "1.0"
    assert manifest_payload["created_at_utc"] == "2026-06-04T00:00:00Z"
    assert manifest_payload["max_evals"] == 100
    assert manifest_payload["parallel"] is True
    assert manifest_payload["cadence_cshrc"] == "/home/zzchen/cadence_ic231_env.csh"
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "run-native-turbo",
        str(project_dir),
        "--parallel",
        "--max-evals",
        "100",
        "--cadence-cshrc",
        "/home/zzchen/cadence_ic231_env.csh",
    ]
    assert manifest_payload["spectre_settings"]["threads_per_run"] == 10
    assert manifest_payload["spectre_settings"]["parallel_jobs"] == 10
    assert manifest_payload["required_returned_artifacts"] == [
        "reports/native_turbo_optimizer_report.json",
        "reports/native_turbo_optimizer_evaluations.jsonl",
        "state/optimizer_state.json",
        "ledger/experiment_ledger.jsonl",
    ]


def test_package_optimizer_task_cli_writes_task_and_manifest(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--max-evals",
            "100",
            "--cadence-cshrc",
            "/home/zzchen/cadence_ic231_env.csh",
            "--parallel",
        ],
    )

    assert result.exit_code == 0
    assert "execution_package/OPTIMIZER_EXECUTION_TASK.md" in result.stdout
    assert "execution_package/optimizer_execution_manifest.json" in result.stdout
    assert (project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md").exists()
    assert (
        project_dir / "execution_package" / "optimizer_execution_manifest.json"
    ).exists()
