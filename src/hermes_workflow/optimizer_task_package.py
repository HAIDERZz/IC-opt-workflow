from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.native_turbo import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from hermes_workflow.real_result_record import LEDGER_PATH, OPTIMIZER_STATE_PATH
from hermes_workflow.validate import assert_valid_project


TASK_FILE_NAME = "OPTIMIZER_EXECUTION_TASK.md"
MANIFEST_FILE_NAME = "optimizer_execution_manifest.json"
REQUIRED_RETURNED_ARTIFACTS = [
    str(REPORT_RELATIVE),
    str(EVALUATIONS_RELATIVE),
    OPTIMIZER_STATE_PATH,
    LEDGER_PATH,
]


@dataclass(frozen=True)
class OptimizerExecutionTaskPackage:
    task_path: Path
    manifest_path: Path
    payload: dict


def build_optimizer_execution_task_package(
    project_dir: Path,
    *,
    max_evals: int,
    cadence_cshrc: Path,
    parallel: bool = True,
    created_at_utc: str | None = None,
) -> OptimizerExecutionTaskPackage:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")

    project_dir = Path(project_dir)
    cadence_cshrc = Path(cadence_cshrc)
    bundle = assert_valid_project(project_dir)
    execution_dir = project_dir / "execution_package"
    execution_dir.mkdir(parents=True, exist_ok=True)

    command = _command(project_dir, max_evals, cadence_cshrc, parallel)
    spectre = bundle.spectre.spectre
    spectre_settings = {
        "preset": spectre.preset.value,
        "threads_per_run": spectre.threads_per_run,
        "parallel_jobs": spectre.parallel_jobs,
        "output_format": spectre.output_format,
        "timeout_s": spectre.timeout_s,
    }
    payload = {
        "schema_version": "1.0",
        "created_at_utc": created_at_utc or _created_at_utc(),
        "project_name": bundle.project_config.project.name,
        "project_dir": str(project_dir),
        "command": command,
        "max_evals": max_evals,
        "parallel": parallel,
        "cadence_cshrc": str(cadence_cshrc),
        "spectre_settings": spectre_settings,
        "required_returned_artifacts": list(REQUIRED_RETURNED_ARTIFACTS),
    }

    task_path = execution_dir / TASK_FILE_NAME
    manifest_path = execution_dir / MANIFEST_FILE_NAME
    task_path.write_text(_render_task(payload), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return OptimizerExecutionTaskPackage(
        task_path=task_path,
        manifest_path=manifest_path,
        payload=payload,
    )


def _created_at_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _command(
    project_dir: Path,
    max_evals: int,
    cadence_cshrc: Path,
    parallel: bool,
) -> list[str]:
    command = ["hermes-workflow", "run-native-turbo", str(project_dir)]
    command.append("--parallel" if parallel else "--sequential")
    command.extend(["--max-evals", str(max_evals)])
    command.extend(["--cadence-cshrc", str(cadence_cshrc)])
    return command


def _render_task(payload: dict) -> str:
    command = " ".join(payload["command"])
    settings = payload["spectre_settings"]
    artifacts = "\n".join(
        f"- `{artifact}`" for artifact in payload["required_returned_artifacts"]
    )
    return f"""# Optimizer Execution Agent Task

Project: `{payload["project_name"]}`
Project directory: `{payload["project_dir"]}`
Created at UTC: `{payload["created_at_utc"]}`

## Command

```bash
{command}
```

## Required Behavior

- Use native `Turbo1.optimize()` through `run-native-turbo`.
- Preserve native Maestro/ADE exported netlist structure.
- Command exit status alone is not acceptance evidence.
- Manifest-level audit is required for any real-tool run.

## Spectre/OCEAN Settings Audit

- `preset`: `{settings["preset"]}`
- `threads_per_run`: `{settings["threads_per_run"]}`
- `parallel_jobs`: `{settings["parallel_jobs"]}`
- `output_format`: `{settings["output_format"]}`
- `timeout_s`: `{settings["timeout_s"]}`

## Required Returned Artifacts

{artifacts}

## Forbidden Actions

- Do not hand-pick candidate points.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not change approved metric formulas.
- Do not flatten or replace the native Maestro/ADE netlist layout.
- Do not commit raw Cadence artifacts.
"""
