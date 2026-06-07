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
        cadence_cshrc=Path("/path/to/cadence_env.csh"),
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
    assert "hermes-workflow optimizer-status" in task_text
    assert "threads_per_run" in task_text
    assert "parallel_jobs" in task_text
    assert "ledger/experiment_ledger.jsonl" in task_text
    assert manifest_payload["schema_version"] == "1.0"
    assert manifest_payload["backend"] == "native_turbo"
    assert manifest_payload["created_at_utc"] == "2026-06-04T00:00:00Z"
    assert manifest_payload["max_evals"] == 100
    assert manifest_payload["parallel"] is True
    assert manifest_payload["cadence_cshrc"] == "/path/to/cadence_env.csh"
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "run-native-turbo",
        str(project_dir),
        "--parallel",
        "--max-evals",
        "100",
        "--cadence-cshrc",
        "/path/to/cadence_env.csh",
    ]
    assert manifest_payload["spectre_settings"]["threads_per_run"] == 10
    assert manifest_payload["spectre_settings"]["parallel_jobs"] == 10
    required_artifacts = manifest_payload["required_returned_artifacts"]
    assert "reports/native_turbo_optimizer_report.json" in required_artifacts
    assert "reports/native_turbo_optimizer_evaluations.jsonl" in required_artifacts
    assert "state/optimizer_state.json" in required_artifacts
    assert "ledger/experiment_ledger.jsonl" in required_artifacts
    assert "reports/optimizer_finalize_report.json" in required_artifacts
    assert manifest_payload["audit_commands"] == [
        ["hermes-workflow", "check-optimizer-run", str(project_dir)],
        ["hermes-workflow", "summarize-optimizer-run", str(project_dir)],
        ["hermes-workflow", "finalize-optimizer-run", str(project_dir)],
        ["hermes-workflow", "optimizer-status", str(project_dir)],
    ]


def test_build_optimizer_execution_task_package_writes_openbox_backend(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=100,
        cadence_cshrc=Path("/path/to/cadence_env.csh"),
        optimizer_backend="openbox",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert "run-openbox-real" in task_text
    assert "run-native-turbo" not in task_text
    assert "--max-evals 100" in task_text
    assert "--batch-size 10" in task_text
    assert "--parallel-jobs 10" in task_text
    assert "OpenBox must be installed" in task_text
    assert "report a dependency blocker" in task_text
    assert "Do not silently fall back to TuRBO" in task_text
    assert "hermes-workflow check-optimizer-run" in task_text
    assert "hermes-workflow summarize-optimizer-run" in task_text
    assert "hermes-workflow optimizer-status" in task_text
    assert "reports/optimizer_run_report.json" in task_text
    assert "reports/optimizer_evaluations.jsonl" in task_text

    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["batch_size"] == 10
    assert manifest_payload["parallel_jobs"] == 10
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "run-openbox-real",
        str(project_dir),
        "--max-evals",
        "100",
        "--batch-size",
        "10",
        "--parallel-jobs",
        "10",
        "--cadence-cshrc",
        "/path/to/cadence_env.csh",
    ]
    required_artifacts = manifest_payload["required_returned_artifacts"]
    assert "reports/optimizer_run_report.json" in required_artifacts
    assert "reports/optimizer_evaluations.jsonl" in required_artifacts
    assert "state/optimizer_state.json" in required_artifacts
    assert "ledger/experiment_ledger.jsonl" in required_artifacts
    assert "reports/optimizer_finalize_report.json" in required_artifacts


def test_build_optimizer_execution_task_package_writes_openbox_continuation(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=None,
        additional_evals=50,
        cadence_cshrc=Path("/path/to/cadence_env.csh"),
        optimizer_backend="openbox",
        continuation=True,
        created_at_utc="2026-06-05T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert "continue-openbox-real" in task_text
    assert "run-openbox-real" not in task_text
    assert "--additional-evals 50" in task_text
    assert "existing accepted optimizer traces" in task_text
    assert "check-toolchain-env" in task_text
    assert ".venv" in task_text
    assert "finalize-optimizer-run" in task_text
    assert "non-sandbox" in task_text
    assert "reports/optimizer_run_acceptance_report.json" in task_text
    assert "reports/optimizer_completion_report.json" in task_text
    assert "reports/optimizer_finalize_report.json" in task_text
    assert "reports/optimizer_insight_report.md" in task_text
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["continuation"] is True
    assert manifest_payload["additional_evals"] == 50
    assert manifest_payload["max_evals"] is None
    assert manifest_payload["toolchain_check_command"] == [
        "hermes-workflow",
        "check-toolchain-env",
        "--openbox-venv",
        ".venv",
        "--cadence-cshrc",
        "/path/to/cadence_env.csh",
    ]
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "continue-openbox-real",
        str(project_dir),
        "--additional-evals",
        "50",
        "--batch-size",
        "10",
        "--cadence-cshrc",
        "/path/to/cadence_env.csh",
    ]
    assert "--parallel-jobs" not in manifest_payload["command"]
    assert [
        "hermes-workflow",
        "finalize-optimizer-run",
        str(project_dir),
    ] in manifest_payload["audit_commands"]
    assert [
        "hermes-workflow",
        "optimizer-status",
        str(project_dir),
    ] in manifest_payload["audit_commands"]
    assert "reports/optimizer_finalize_report.json" in manifest_payload[
        "required_returned_artifacts"
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
            "/path/to/cadence_env.csh",
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


def test_package_optimizer_task_cli_writes_openbox_manifest(tmp_path: Path) -> None:
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
            "/path/to/cadence_env.csh",
            "--backend",
            "openbox",
        ],
    )

    assert result.exit_code == 0
    manifest_path = project_dir / "execution_package" / "optimizer_execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["command"][1] == "run-openbox-real"


def test_package_optimizer_task_cli_writes_openbox_continuation_manifest(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--backend",
            "openbox",
            "--continuation",
            "--additional-evals",
            "50",
            "--cadence-cshrc",
            "/path/to/cadence_env.csh",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_path = project_dir / "execution_package" / "optimizer_execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["continuation"] is True
    assert manifest_payload["additional_evals"] == 50
    assert manifest_payload["command"][1] == "continue-openbox-real"


def test_optimizer_task_package_uses_absolute_shell_safe_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_dir = Path("bridge_test_inv")
    create_project_from_template(project_dir)
    cadence_cshrc = tmp_path / "cadence env.csh"

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=100,
        cadence_cshrc=cadence_cshrc,
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert manifest_payload["project_dir"] == str(project_dir.resolve())
    assert manifest_payload["cadence_cshrc"] == str(cadence_cshrc.resolve())
    assert manifest_payload["command"][2] == str(project_dir.resolve())
    assert manifest_payload["command"][-1] == str(cadence_cshrc.resolve())
    assert f"'{cadence_cshrc.resolve()}'" in task_text


def test_optimizer_execution_task_keeps_forbidden_actions_in_forbidden_section(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=100,
        cadence_cshrc=Path("/path/to/cadence_env.csh"),
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    required_behavior = task_text.split("## Required Behavior", 1)[1].split(
        "## Spectre/OCEAN Settings Audit",
        1,
    )[0]
    forbidden_actions = task_text.split("## Forbidden Actions", 1)[1]

    assert "Claude Code" not in task_text
    assert "hand-pick" not in required_behavior
    assert "parse PSF" not in required_behavior
    assert "rewrite OCEAN" not in required_behavior
    assert "Do not hand-pick candidate points." in forbidden_actions
    assert "Do not parse PSF in Python." in forbidden_actions
    assert "Do not rewrite OCEAN formulas." in forbidden_actions


def test_optimizer_execution_task_keeps_openbox_fallback_in_required_behavior(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        max_evals=100,
        cadence_cshrc=Path("/path/to/cadence_env.csh"),
        optimizer_backend="openbox",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    required_behavior = task_text.split("## Required Behavior", 1)[1].split(
        "## Spectre/OCEAN Settings Audit",
        1,
    )[0]

    assert "Do not silently fall back to TuRBO" in required_behavior
    assert "Do not hand-pick candidate points." not in required_behavior
