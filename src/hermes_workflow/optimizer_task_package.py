from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.native_turbo import (
    EVALUATIONS_RELATIVE as NATIVE_TURBO_EVALUATIONS_RELATIVE,
)
from hermes_workflow.native_turbo import (
    REPORT_RELATIVE as NATIVE_TURBO_REPORT_RELATIVE,
)
from hermes_workflow.optimizer_artifacts import (
    EVALUATIONS_RELATIVE as OPTIMIZER_EVALUATIONS_RELATIVE,
)
from hermes_workflow.optimizer_artifacts import REPORT_RELATIVE as OPTIMIZER_REPORT_RELATIVE
from hermes_workflow.real_result_record import LEDGER_PATH, OPTIMIZER_STATE_PATH
from hermes_workflow.validate import assert_valid_project


TASK_FILE_NAME = "OPTIMIZER_EXECUTION_TASK.md"
MANIFEST_FILE_NAME = "optimizer_execution_manifest.json"
NATIVE_TURBO_BACKEND = "native_turbo"
OPENBOX_BACKEND = "openbox"
NATIVE_TURBO_REQUIRED_RETURNED_ARTIFACTS = [
    str(NATIVE_TURBO_REPORT_RELATIVE),
    str(NATIVE_TURBO_EVALUATIONS_RELATIVE),
    OPTIMIZER_STATE_PATH,
    LEDGER_PATH,
]
OPENBOX_REQUIRED_RETURNED_ARTIFACTS = [
    str(OPTIMIZER_REPORT_RELATIVE),
    str(OPTIMIZER_EVALUATIONS_RELATIVE),
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
    optimizer_backend: str = NATIVE_TURBO_BACKEND,
    created_at_utc: str | None = None,
) -> OptimizerExecutionTaskPackage:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")

    project_dir = Path(project_dir).resolve()
    cadence_cshrc = Path(cadence_cshrc).expanduser().resolve()
    backend = _normalize_backend(optimizer_backend)
    bundle = assert_valid_project(project_dir)
    execution_dir = project_dir / "execution_package"
    execution_dir.mkdir(parents=True, exist_ok=True)

    spectre = bundle.spectre.spectre
    batch_size = bundle.optimizer.optimizer.batch_size if parallel else 1
    parallel_jobs = spectre.parallel_jobs if parallel else 1
    command = _command(
        project_dir,
        max_evals,
        cadence_cshrc,
        parallel,
        backend=backend,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
    )
    spectre_settings = {
        "preset": spectre.preset.value,
        "threads_per_run": spectre.threads_per_run,
        "parallel_jobs": spectre.parallel_jobs,
        "output_format": spectre.output_format,
        "timeout_s": spectre.timeout_s,
    }
    audit_commands = [
        ["hermes-workflow", "check-optimizer-run", str(project_dir)],
        ["hermes-workflow", "summarize-optimizer-run", str(project_dir)],
    ]
    payload = {
        "schema_version": "1.0",
        "backend": backend,
        "created_at_utc": created_at_utc or _created_at_utc(),
        "project_name": bundle.project_config.project.name,
        "project_dir": str(project_dir),
        "command": command,
        "audit_commands": audit_commands,
        "max_evals": max_evals,
        "parallel": parallel,
        "batch_size": batch_size,
        "parallel_jobs": parallel_jobs,
        "cadence_cshrc": str(cadence_cshrc),
        "spectre_settings": spectre_settings,
        "required_returned_artifacts": _required_returned_artifacts(backend),
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


def _normalize_backend(backend: str) -> str:
    normalized = backend.strip().replace("-", "_")
    if normalized not in {NATIVE_TURBO_BACKEND, OPENBOX_BACKEND}:
        raise ValueError("optimizer_backend must be native_turbo or openbox")
    return normalized


def _required_returned_artifacts(backend: str) -> list[str]:
    if backend == OPENBOX_BACKEND:
        return list(OPENBOX_REQUIRED_RETURNED_ARTIFACTS)
    return list(NATIVE_TURBO_REQUIRED_RETURNED_ARTIFACTS)


def _command(
    project_dir: Path,
    max_evals: int,
    cadence_cshrc: Path,
    parallel: bool,
    *,
    backend: str,
    batch_size: int,
    parallel_jobs: int,
) -> list[str]:
    if backend == OPENBOX_BACKEND:
        command = ["hermes-workflow", "run-openbox-real", str(project_dir)]
        command.extend(["--max-evals", str(max_evals)])
        command.extend(["--batch-size", str(batch_size)])
        command.extend(["--parallel-jobs", str(parallel_jobs)])
        command.extend(["--cadence-cshrc", str(cadence_cshrc)])
        return command

    command = ["hermes-workflow", "run-native-turbo", str(project_dir)]
    command.append("--parallel" if parallel else "--sequential")
    command.extend(["--max-evals", str(max_evals)])
    command.extend(["--cadence-cshrc", str(cadence_cshrc)])
    return command


def _render_task(payload: dict) -> str:
    command = shlex.join(payload["command"])
    audit_commands = "\n".join(
        f"```bash\n{shlex.join(audit_command)}\n```"
        for audit_command in payload["audit_commands"]
    )
    settings = payload["spectre_settings"]
    artifacts = "\n".join(
        f"- `{artifact}`" for artifact in payload["required_returned_artifacts"]
    )
    required_behavior = _required_behavior(payload["backend"])
    return f"""# Optimizer Execution Agent Task

Project: `{payload["project_name"]}`
Project directory: `{payload["project_dir"]}`
Created at UTC: `{payload["created_at_utc"]}`

## Command

```bash
{command}
```

## Audit Commands

Run these after optimizer execution:

{audit_commands}

## Required Behavior

{required_behavior}
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


def _required_behavior(backend: str) -> str:
    if backend == OPENBOX_BACKEND:
        return "\n".join(
            [
                "- Use OpenBox ask-and-tell through `run-openbox-real`.",
                "- OpenBox must be installed and importable in the execution environment.",
                "- If OpenBox is unavailable, report a dependency blocker.",
                "- Do not silently fall back to TuRBO or manually choose candidates.",
            ]
        )
    return "- Use native `Turbo1.optimize()` through `run-native-turbo`."
