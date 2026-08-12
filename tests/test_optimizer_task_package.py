import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_task_package import (
    build_optimizer_execution_task_package,
)
from tests.project_factory import create_generic_project


runner = CliRunner()

PROJECT_NAME = "optimizer_task_project"
MAX_EVALUATIONS = 100
BATCH_SIZE = 10
PARALLEL_JOBS = 10
CADENCE_CSHRC = Path("/opt/ic-opt/cadence_env.csh")


def _create_optimizer_project(
    tmp_path: Path,
    *,
    name: str = PROJECT_NAME,
    max_evaluations: int = MAX_EVALUATIONS,
    batch_size: int = BATCH_SIZE,
    parallel_jobs: int = PARALLEL_JOBS,
) -> Path:
    return create_generic_project(
        tmp_path,
        name=name,
        max_evaluations=max_evaluations,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
    )


def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _set_optimizer_settings(
    project_dir: Path,
    *,
    algorithm: str | None = None,
    strategy: str | None = None,
) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    settings = payload["optimizer"]
    if algorithm is not None:
        settings["algorithm"] = algorithm
    if strategy is not None:
        settings["strategy"] = strategy
    _write_yaml(optimizer_path, payload)


def _set_implicit_optimizer_algorithm(project_dir: Path, algorithm: str) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    settings = payload["optimizer"]
    settings["algorithm"] = algorithm
    settings.pop("strategy", None)
    _write_yaml(optimizer_path, payload)


def _optimizer_settings(project_dir: Path) -> dict:
    return _read_yaml(project_dir / "config" / "optimizer.yaml")["optimizer"]


def _spectre_settings(project_dir: Path) -> dict:
    return _read_yaml(project_dir / "config" / "spectre.yaml")["spectre"]


def test_optimizer_task_package_does_not_label_parallel_jobs_as_spectre_setting(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    optimizer = _optimizer_settings(project_dir)
    spectre = _spectre_settings(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    # parallel_jobs must not be inside the Spectre settings dict.
    assert "parallel_jobs" not in manifest_payload["spectre_settings"]

    # Scheduler block exposes candidate parallelism contract.
    assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
    assert manifest_payload["scheduler"]["batch_size"] == optimizer["batch_size"]
    assert manifest_payload["scheduler"]["inside_candidate_execution"] == "serial"

    # Top-level fields kept for backward compatibility.
    assert manifest_payload["parallel_jobs"] == spectre["parallel_jobs"]
    assert manifest_payload["batch_size"] == optimizer["batch_size"]

    # Rendered task text has a Scheduler Settings section.
    assert "## Scheduler Settings" in task_text

    # Spectre/OCEAN Settings Audit section must NOT mention parallel_jobs.
    audit_start = task_text.index("## Spectre/OCEAN Settings Audit")
    next_section = task_text.index("\n## ", audit_start + 1)
    audit_slice = task_text[audit_start:next_section]
    assert "parallel_jobs" not in audit_slice


def test_build_optimizer_execution_task_package_writes_task_and_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    optimizer = _optimizer_settings(project_dir)
    spectre = _spectre_settings(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
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
    assert "--max-evals" not in task_text
    assert "Command exit status alone is not acceptance evidence" in task_text
    assert "Manifest-level audit is required" in task_text
    assert "hermes-workflow optimizer-status" in task_text
    assert "threads_per_run" in task_text
    assert "parallel_jobs" in task_text
    assert "ledger/experiment_ledger.jsonl" in task_text
    assert manifest_payload["schema_version"] == "1.0"
    assert manifest_payload["backend"] == "native_turbo"
    assert manifest_payload["created_at_utc"] == "2026-06-04T00:00:00Z"
    assert manifest_payload["max_evals"] == optimizer["max_evaluations"]
    assert manifest_payload["parallel"] is True
    assert manifest_payload["cadence_cshrc"] == str(CADENCE_CSHRC.resolve())
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "run-native-turbo",
        str(project_dir.resolve()),
        "--parallel",
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    assert manifest_payload["spectre_settings"]["threads_per_run"] == spectre["threads_per_run"]
    assert "parallel_jobs" not in manifest_payload["spectre_settings"]
    assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
    required_artifacts = manifest_payload["required_returned_artifacts"]
    assert "reports/native_turbo_optimizer_report.json" in required_artifacts
    assert "reports/optimizer_effectiveness_audit.json" in required_artifacts
    assert "reports/native_turbo_optimizer_evaluations.jsonl" in required_artifacts
    assert "state/optimizer_state.json" in required_artifacts
    assert "ledger/experiment_ledger.jsonl" in required_artifacts
    assert "reports/optimizer_finalize_report.json" in required_artifacts
    assert manifest_payload["audit_commands"] == [
        [
            "hermes-workflow",
            command_name,
            str(project_dir.resolve()),
            "--expected-backend",
            "native_turbo",
        ]
        for command_name in (
            "check-optimizer-run",
            "summarize-optimizer-run",
            "finalize-optimizer-run",
            "optimizer-status",
        )
    ]


def test_build_optimizer_execution_task_package_writes_openbox_backend(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")
    optimizer = _optimizer_settings(project_dir)
    spectre = _spectre_settings(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="openbox",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert "run-openbox-real" in task_text
    assert "run-native-turbo" not in task_text
    assert "--max-evals" not in task_text
    assert "--batch-size" not in task_text
    assert "--parallel-jobs" not in task_text
    assert "OpenBox must be installed" in task_text
    assert "report a dependency blocker" in task_text
    assert "Do not silently fall back to TuRBO" in task_text
    assert "hermes-workflow check-optimizer-run" in task_text
    assert "hermes-workflow summarize-optimizer-run" in task_text
    assert "hermes-workflow optimizer-status" in task_text
    assert "reports/optimizer_run_report.json" in task_text
    assert "reports/optimizer_evaluations.jsonl" in task_text

    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["batch_size"] == optimizer["batch_size"]
    assert manifest_payload["parallel_jobs"] == spectre["parallel_jobs"]
    assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "run-openbox-real",
        str(project_dir.resolve()),
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    required_artifacts = manifest_payload["required_returned_artifacts"]
    assert "reports/optimizer_run_report.json" in required_artifacts
    assert "reports/optimizer_evaluations.jsonl" in required_artifacts
    assert "state/optimizer_state.json" in required_artifacts
    assert "ledger/experiment_ledger.jsonl" in required_artifacts
    assert "reports/optimizer_finalize_report.json" in required_artifacts


def test_build_optimizer_execution_task_package_rejects_backend_mismatch_with_turbo(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_optimizer_settings(project_dir, algorithm="turbo", strategy="turbo_trust_region")

    with pytest.raises(
        ValueError,
        match="optimizer_backend openbox does not match project backend native_turbo",
    ):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
            optimizer_backend="openbox",
            created_at_utc="2026-06-04T00:00:00Z",
        )


def test_build_optimizer_execution_task_package_rejects_backend_mismatch_with_openbox(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_optimizer_settings(project_dir, algorithm="openbox", strategy="openbox_prf_eic")

    with pytest.raises(
        ValueError,
        match="optimizer_backend native_turbo does not match project backend openbox",
    ):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
            optimizer_backend="native_turbo",
            created_at_utc="2026-06-04T00:00:00Z",
        )


def test_build_optimizer_execution_task_package_writes_openbox_continuation(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")
    optimizer = _optimizer_settings(project_dir)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="openbox",
        continuation=True,
        additional_evals=12,
        created_at_utc="2026-06-05T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert "continue-openbox-real" in task_text
    assert "run-openbox-real" not in task_text
    assert "--additional-evals 12" in task_text
    assert "existing accepted optimizer traces" in task_text
    assert "check-toolchain-env" in task_text
    assert "/tmp/ic_auto_opt_openbox_spike/.venv" not in task_text
    assert "finalize-optimizer-run" in task_text
    assert "non-sandbox" in task_text
    assert "reports/optimizer_run_acceptance_report.json" in task_text
    assert "reports/optimizer_completion_report.json" in task_text
    assert "reports/optimizer_finalize_report.json" in task_text
    assert "reports/optimizer_insight_report.md" in task_text
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["continuation"] is True
    assert manifest_payload["additional_evals"] == 12
    assert manifest_payload["max_evals"] == optimizer["max_evaluations"]
    assert manifest_payload["toolchain_check_command"] == [
        "hermes-workflow",
        "check-toolchain-env",
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "continue-openbox-real",
        str(project_dir.resolve()),
        "--additional-evals",
        "12",
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    assert "--parallel-jobs" not in manifest_payload["command"]
    assert [
        "hermes-workflow",
        "finalize-optimizer-run",
        str(project_dir.resolve()),
        "--expected-backend",
        "openbox",
    ] in manifest_payload["audit_commands"]
    assert [
        "hermes-workflow",
        "optimizer-status",
        str(project_dir.resolve()),
        "--expected-backend",
        "openbox",
    ] in manifest_payload["audit_commands"]
    assert "reports/optimizer_finalize_report.json" in manifest_payload[
        "required_returned_artifacts"
    ]


def test_build_optimizer_execution_task_package_writes_native_continuation(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="native_turbo",
        continuation=True,
        additional_evals=4,
    )

    assert package.payload["backend"] == "native_turbo"
    assert package.payload["continuation"] is True
    assert package.payload["additional_evals"] == 4
    assert package.payload["command"] == [
        "ic-opt",
        str(project_dir.resolve()),
        "--real",
        "--continue",
        "4",
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    task_text = package.task_path.read_text(encoding="utf-8")
    assert "ic-opt" in task_text
    assert "--continue 4" in task_text


def test_optimizer_task_continuation_rejects_enabled_history_before_writing(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_optimizer_settings(
        project_dir,
        algorithm="openbox",
        strategy="openbox_auto",
    )
    _write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "/previous/project"}],
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="history warm-start cannot be combined with continuation",
    ):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
            optimizer_backend="openbox",
            continuation=True,
            additional_evals=3,
        )

    assert not (
        project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md"
    ).exists()


def test_optimizer_task_package_rejects_fix_run_before_writing(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, workflow_mode="fix_run")

    with pytest.raises(
        ValueError,
        match="optimizer task package requires an optimize workflow",
    ):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
        )

    assert not (
        project_dir / "execution_package" / "OPTIMIZER_EXECUTION_TASK.md"
    ).exists()
    assert not (
        project_dir
        / "execution_package"
        / "optimizer_execution_manifest.json"
    ).exists()
    assert not (
        project_dir
        / "execution_package"
        / "optimizer_execution_manifest.json"
    ).exists()


def test_optimizer_task_continuation_requires_additional_evaluations(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    with pytest.raises(ValueError, match="additional_evals is required"):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
            optimizer_backend="openbox",
            continuation=True,
        )


def test_optimizer_task_explicit_openbox_venv_is_preserved(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")
    execution_venv = tmp_path / "portable-openbox-venv"

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="openbox",
        openbox_venv=execution_venv,
    )

    resolved_venv = str(execution_venv.resolve())
    assert package.payload["openbox_venv"] == resolved_venv
    assert package.payload["toolchain_check_command"] == [
        "hermes-workflow",
        "check-toolchain-env",
        "--openbox-venv",
        resolved_venv,
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    assert resolved_venv in package.task_path.read_text(encoding="utf-8")


def test_optimizer_task_rejects_openbox_venv_for_native_backend(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)

    with pytest.raises(ValueError, match="openbox_venv is only valid"):
        build_optimizer_execution_task_package(
            project_dir,
            cadence_cshrc=CADENCE_CSHRC,
            optimizer_backend="native_turbo",
            openbox_venv=tmp_path / "unused-venv",
        )


def test_package_optimizer_task_cli_writes_task_and_manifest(tmp_path: Path) -> None:
    project_dir = _create_optimizer_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
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
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
            "--backend",
            "openbox",
            "--strategy",
            "openbox_gp_eic",
        ],
    )

    assert result.exit_code == 0
    manifest_path = project_dir / "execution_package" / "optimizer_execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["strategy"] == "openbox_gp_eic"
    assert manifest_payload["command"][1] == "run-openbox-real"
    strategy_index = manifest_payload["command"].index("--strategy")
    assert manifest_payload["command"][strategy_index : strategy_index + 2] == [
        "--strategy",
        "openbox_gp_eic",
    ]


def test_package_optimizer_task_cli_uses_implicit_openbox_backend_for_fresh_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_payload = json.loads(
        (
            project_dir
            / "execution_package"
            / "optimizer_execution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["strategy"] is None
    assert manifest_payload["command"][1] == "run-openbox-real"
    assert [
        "hermes-workflow",
        "check-optimizer-run",
        str(project_dir.resolve()),
        "--expected-backend",
        "openbox",
    ] in manifest_payload["audit_commands"]


def test_package_optimizer_task_cli_uses_implicit_openbox_backend_for_continuation(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--continuation",
            "--additional-evals",
            "6",
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_payload = json.loads(
        (
            project_dir
            / "execution_package"
            / "optimizer_execution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["strategy"] is None
    assert manifest_payload["command"] == [
        "hermes-workflow",
        "continue-openbox-real",
        str(project_dir.resolve()),
        "--additional-evals",
        "6",
        "--cadence-cshrc",
        str(CADENCE_CSHRC.resolve()),
    ]
    assert "reports/optimizer_run_report.json" in manifest_payload[
        "required_returned_artifacts"
    ]


def test_package_optimizer_task_cli_uses_openbox_for_implicit_random_baseline(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "random")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_payload = json.loads(
        (
            project_dir
            / "execution_package"
            / "optimizer_execution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest_payload["backend"] == "openbox"
    assert manifest_payload["strategy"] is None
    assert manifest_payload["command"][1] == "run-openbox-real"
    assert [
        "hermes-workflow",
        "optimizer-status",
        str(project_dir.resolve()),
        "--expected-backend",
        "openbox",
    ] in manifest_payload["audit_commands"]


def test_package_optimizer_task_cli_writes_openbox_continuation_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--backend",
            "openbox",
            "--continuation",
            "--additional-evals",
            "7",
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_path = project_dir / "execution_package" / "optimizer_execution_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["continuation"] is True
    assert manifest_payload["additional_evals"] == 7
    assert manifest_payload["command"][1] == "continue-openbox-real"
    assert manifest_payload["command"][3:5] == ["--additional-evals", "7"]


def test_package_optimizer_task_cli_rejects_backend_mismatch_for_continuation(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--backend",
            "native-turbo",
            "--continuation",
            "--additional-evals",
            "7",
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 1
    assert (
        "optimizer_backend native_turbo does not match project backend openbox"
        in result.output
    )
    assert not (
        project_dir / "execution_package" / "optimizer_execution_manifest.json"
    ).exists()


def test_package_optimizer_task_cli_writes_native_continuation_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--continuation",
            "--additional-evals",
            "5",
            "--cadence-cshrc",
            str(CADENCE_CSHRC),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest_path = (
        project_dir / "execution_package" / "optimizer_execution_manifest.json"
    )
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["backend"] == "native_turbo"
    assert manifest_payload["command"][:5] == [
        "ic-opt",
        str(project_dir.resolve()),
        "--real",
        "--continue",
        "5",
    ]


def test_optimizer_task_package_uses_absolute_shell_safe_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_dir = Path(PROJECT_NAME)
    create_generic_project(
        Path("."),
        name=PROJECT_NAME,
        max_evaluations=MAX_EVALUATIONS,
        batch_size=BATCH_SIZE,
        parallel_jobs=PARALLEL_JOBS,
    )
    cadence_cshrc = tmp_path / "cadence env.csh"

    package = build_optimizer_execution_task_package(
        project_dir,
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
    project_dir = _create_optimizer_project(tmp_path)

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    required_behavior = task_text.split("## Required Behavior", 1)[1].split(
        "## Spectre/OCEAN Settings Audit",
        1,
    )[0]
    forbidden_actions = task_text.split("## Forbidden Actions", 1)[1]

    assert "hand-pick" not in required_behavior
    assert "parse PSF" not in required_behavior
    assert "rewrite OCEAN" not in required_behavior
    assert "Do not hand-pick candidate points." in forbidden_actions
    assert "Do not parse PSF in Python." in forbidden_actions
    assert "Do not rewrite OCEAN formulas." in forbidden_actions


def test_optimizer_execution_task_keeps_openbox_fallback_in_required_behavior(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="openbox",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    required_behavior = task_text.split("## Required Behavior", 1)[1].split(
        "## Spectre/OCEAN Settings Audit",
        1,
    )[0]

    assert "Do not silently fall back to TuRBO" in required_behavior
    assert "Do not hand-pick candidate points." not in required_behavior


def test_build_openbox_task_package_includes_optimizer_strategy(
    tmp_path: Path,
) -> None:
    project_dir = _create_optimizer_project(tmp_path)
    _set_implicit_optimizer_algorithm(project_dir, "openbox")

    package = build_optimizer_execution_task_package(
        project_dir,
        cadence_cshrc=CADENCE_CSHRC,
        optimizer_backend="openbox",
        strategy="openbox_prf_eic",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    task_text = package.task_path.read_text(encoding="utf-8")
    manifest_payload = package.payload

    assert "--strategy openbox_prf_eic" in task_text
    assert "Requested optimizer strategy: `openbox_prf_eic`" in task_text
    assert "Do not silently switch optimizer backend." in task_text
    assert "reports/optimizer_effectiveness_audit.json" in task_text
    assert manifest_payload["strategy"] == "openbox_prf_eic"
    command = manifest_payload["command"]
    assert command[:3] == [
        "hermes-workflow",
        "run-openbox-real",
        str(project_dir.resolve()),
    ]
    strategy_index = command.index("--strategy")
    assert command[strategy_index : strategy_index + 2] == [
        "--strategy",
        "openbox_prf_eic",
    ]
    assert (
        "reports/optimizer_effectiveness_audit.json"
        in manifest_payload["required_returned_artifacts"]
    )
