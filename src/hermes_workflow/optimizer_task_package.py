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
from hermes_workflow.optimizer_strategy import (
    OptimizerStrategyRequest,
    resolve_optimizer_strategy,
)
from hermes_workflow.optimizer_strategy import OptimizerStrategyName
from hermes_workflow.real_result_record import LEDGER_PATH, OPTIMIZER_STATE_PATH
from hermes_workflow.validate import assert_valid_project


TASK_FILE_NAME = "OPTIMIZER_EXECUTION_TASK.md"
MANIFEST_FILE_NAME = "optimizer_execution_manifest.json"
NATIVE_TURBO_BACKEND = "native_turbo"
OPENBOX_BACKEND = "openbox"
NATIVE_TURBO_REQUIRED_RETURNED_ARTIFACTS = [
    str(NATIVE_TURBO_REPORT_RELATIVE),
    str(NATIVE_TURBO_EVALUATIONS_RELATIVE),
    "reports/optimizer_effectiveness_audit.json",
    OPTIMIZER_STATE_PATH,
    LEDGER_PATH,
]
OPENBOX_REQUIRED_RETURNED_ARTIFACTS = [
    str(OPTIMIZER_REPORT_RELATIVE),
    str(OPTIMIZER_EVALUATIONS_RELATIVE),
    "reports/optimizer_effectiveness_audit.json",
    OPTIMIZER_STATE_PATH,
    LEDGER_PATH,
]
SUPERVISOR_CLOSEOUT_ARTIFACTS = [
    "reports/optimizer_run_acceptance_report.json",
    "reports/optimizer_completion_report.json",
    "reports/optimizer_finalize_report.json",
    "reports/optimizer_insight_report.json",
    "reports/optimizer_insight_report.md",
    "reports/optimizer_visuals/*.svg",
]
HISTORY_CONTINUATION_CONFLICT = (
    "history warm-start cannot be combined with continuation; use continuation "
    "for same-project budget extension, or start a new project for history "
    "warm-start"
)


def _effective_strategy_value(
    optimizer_settings: object,
    strategy: str | None,
) -> str | None:
    if strategy is not None:
        return OptimizerStrategyName.from_user_value(strategy).value
    configured_strategy = getattr(optimizer_settings, "strategy", None)
    if configured_strategy is None:
        return None
    return OptimizerStrategyName.from_user_value(configured_strategy).value


def _resolved_project_backend(
    optimizer_settings: object,
    *,
    strategy: str | None,
    variable_count: int,
) -> str:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=optimizer_settings.algorithm,
            strategy=(
                OptimizerStrategyName.from_user_value(strategy)
                if strategy is not None
                else optimizer_settings.strategy
            ),
            openbox=optimizer_settings.openbox,
            turbo=optimizer_settings.turbo,
            variable_count=variable_count,
        )
    )
    return (
        NATIVE_TURBO_BACKEND
        if resolved.backend == NATIVE_TURBO_BACKEND
        else OPENBOX_BACKEND
    )


@dataclass(frozen=True)
class OptimizerExecutionTaskPackage:
    task_path: Path
    manifest_path: Path
    payload: dict


def build_optimizer_execution_task_package(
    project_dir: Path,
    *,
    cadence_cshrc: Path,
    parallel: bool = True,
    optimizer_backend: str | None = None,
    strategy: str | None = None,
    continuation: bool = False,
    additional_evals: int | None = None,
    openbox_venv: Path | None = None,
    created_at_utc: str | None = None,
) -> OptimizerExecutionTaskPackage:
    project_dir = Path(project_dir).resolve()
    cadence_cshrc = Path(cadence_cshrc).expanduser().resolve()
    bundle = assert_valid_project(project_dir)
    if bundle.optimizer is None:
        raise ValueError("optimizer task package requires an optimize workflow")
    optimizer_settings = bundle.optimizer.optimizer
    effective_strategy = _effective_strategy_value(optimizer_settings, strategy)
    backend = _resolved_project_backend(
        optimizer_settings,
        strategy=effective_strategy,
        variable_count=len(bundle.variables.variables),
    )
    if optimizer_backend is not None:
        requested_backend = _normalize_backend(optimizer_backend)
        if requested_backend != backend:
            raise ValueError(
                f"optimizer_backend {requested_backend} does not match project "
                f"backend {backend}"
            )
    resolved_openbox_venv = (
        Path(openbox_venv).expanduser().resolve()
        if openbox_venv is not None
        else None
    )
    if resolved_openbox_venv is not None and backend != OPENBOX_BACKEND:
        raise ValueError("openbox_venv is only valid for the openbox backend")
    if (
        continuation
        and bundle.history_warm_start is not None
        and bundle.history_warm_start.history_warm_start.enabled
    ):
        raise ValueError(HISTORY_CONTINUATION_CONFLICT)
    max_evals = bundle.optimizer.optimizer.max_evaluations
    _validate_budget(
        backend=backend,
        max_evals=max_evals,
        additional_evals=additional_evals,
        continuation=continuation,
    )
    execution_dir = project_dir / "execution_package"
    execution_dir.mkdir(parents=True, exist_ok=True)

    spectre = bundle.spectre.spectre
    batch_size = bundle.optimizer.optimizer.batch_size if parallel else 1
    parallel_jobs = spectre.parallel_jobs if parallel else 1
    command = _command(
        project_dir,
        cadence_cshrc,
        parallel,
        backend=backend,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        continuation=continuation,
        strategy=effective_strategy,
        additional_evals=additional_evals,
    )
    spectre_settings = {
        "preset": spectre.preset.value,
        "threads_per_run": spectre.threads_per_run,
        "output_format": spectre.output_format,
        "timeout_s": spectre.timeout_s,
    }
    scheduler_settings = {
        "candidate_parallelism": parallel_jobs,
        "batch_size": batch_size,
        "inside_candidate_execution": "serial",
    }
    audit_commands = [
        [
            "hermes-workflow",
            command_name,
            str(project_dir),
            "--expected-backend",
            backend,
        ]
        for command_name in (
            "check-optimizer-run",
            "summarize-optimizer-run",
            "finalize-optimizer-run",
            "optimizer-status",
        )
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
        "additional_evals": additional_evals,
        "continuation": continuation,
        "strategy": effective_strategy,
        "parallel": parallel,
        "batch_size": batch_size,
        "parallel_jobs": parallel_jobs,
        "cadence_cshrc": str(cadence_cshrc),
        "openbox_venv": (
            str(resolved_openbox_venv)
            if resolved_openbox_venv is not None
            else None
        ),
        "spectre_settings": spectre_settings,
        "scheduler": scheduler_settings,
        "required_returned_artifacts": _required_returned_artifacts(backend),
        "toolchain_check_command": _toolchain_check_command(
            backend,
            cadence_cshrc,
            resolved_openbox_venv,
        ),
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


def _validate_budget(
    *,
    backend: str,
    max_evals: int | None,
    additional_evals: int | None,
    continuation: bool,
) -> None:
    if max_evals is None:
        raise ValueError("max_evals is required")
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if continuation:
        if additional_evals is None:
            raise ValueError("additional_evals is required for continuation")
        if additional_evals < 1:
            raise ValueError("additional_evals must be >= 1")
        return
    if additional_evals is not None:
        raise ValueError("additional_evals is only valid for continuation")


def _required_returned_artifacts(backend: str) -> list[str]:
    base: list[str]
    if backend == OPENBOX_BACKEND:
        base = list(OPENBOX_REQUIRED_RETURNED_ARTIFACTS)
    else:
        base = list(NATIVE_TURBO_REQUIRED_RETURNED_ARTIFACTS)
    return base + list(SUPERVISOR_CLOSEOUT_ARTIFACTS)


def _toolchain_check_command(
    backend: str,
    cadence_cshrc: Path,
    openbox_venv: Path | None,
) -> list[str] | None:
    if backend != OPENBOX_BACKEND:
        return None
    command = [
        "hermes-workflow",
        "check-toolchain-env",
    ]
    if openbox_venv is not None:
        command.extend(["--openbox-venv", str(openbox_venv)])
    command.extend(["--cadence-cshrc", str(cadence_cshrc)])
    return command


def _command(
    project_dir: Path,
    cadence_cshrc: Path,
    parallel: bool,
    *,
    backend: str,
    batch_size: int,
    parallel_jobs: int,
    continuation: bool,
    strategy: str | None,
    additional_evals: int | None,
) -> list[str]:
    if backend == OPENBOX_BACKEND:
        if continuation:
            command = ["hermes-workflow", "continue-openbox-real", str(project_dir)]
            command.extend(["--additional-evals", str(additional_evals)])
        else:
            command = ["hermes-workflow", "run-openbox-real", str(project_dir)]
        if strategy:
            command.extend(["--strategy", strategy])
        command.extend(["--cadence-cshrc", str(cadence_cshrc)])
        return command

    if continuation:
        return [
            "ic-opt",
            str(project_dir),
            "--real",
            "--continue",
            str(additional_evals),
            "--cadence-cshrc",
            str(cadence_cshrc),
        ]

    command = ["hermes-workflow", "run-native-turbo", str(project_dir)]
    command.append("--parallel" if parallel else "--sequential")
    command.extend(["--cadence-cshrc", str(cadence_cshrc)])
    return command


def _render_task(payload: dict) -> str:
    command = shlex.join(payload["command"])
    audit_commands = "\n".join(
        f"```bash\n{shlex.join(audit_command)}\n```"
        for audit_command in payload["audit_commands"]
    )
    settings = payload["spectre_settings"]
    scheduler = payload["scheduler"]
    artifacts = "\n".join(
        f"- `{artifact}`" for artifact in payload["required_returned_artifacts"]
    )
    required_behavior = _required_behavior(payload)
    continuation_note = _continuation_note(payload)
    toolchain_gate = _toolchain_gate(payload)
    execution_environment = _execution_environment(payload)
    strategy_note = (
        f"Requested optimizer strategy: `{payload['strategy']}`\n"
        "Do not silently switch optimizer backend.\n"
        if payload.get("strategy")
        else ""
    )
    return f"""# Optimizer Execution Agent Task

Project: `{payload["project_name"]}`
Project directory: `{payload["project_dir"]}`
Created at UTC: `{payload["created_at_utc"]}`
{strategy_note}
{toolchain_gate}
{execution_environment}

## Command

```bash
{command}
```

## Audit Commands

Run these after optimizer execution:

{audit_commands}

## Required Behavior

{required_behavior}
{continuation_note}
- Preserve native Maestro/ADE exported netlist structure.
- Command exit status alone is not acceptance evidence.
- Manifest-level audit is required for any real-tool run.

## Spectre/OCEAN Settings Audit

- `preset`: `{settings["preset"]}`
- `threads_per_run`: `{settings["threads_per_run"]}`
- `output_format`: `{settings["output_format"]}`
- `timeout_s`: `{settings["timeout_s"]}`

## Scheduler Settings

Scheduler parallelism controls how many optimizer candidates run concurrently.
Testbenches and corners inside one candidate always run serially; this is not a
Spectre child-runtime knob.

- `candidate_parallelism`: `{scheduler["candidate_parallelism"]}` (parallel_jobs)
- `batch_size`: `{scheduler["batch_size"]}`
- `inside_candidate_execution`: `{scheduler["inside_candidate_execution"]}`

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


def _required_behavior(payload: dict) -> str:
    backend = payload["backend"]
    if backend == OPENBOX_BACKEND:
        command_name = (
            "continue-openbox-real" if payload.get("continuation") else "run-openbox-real"
        )
        return "\n".join(
            [
                f"- Use OpenBox ask-and-tell through `{command_name}`.",
                "- OpenBox must be installed and importable in the execution environment.",
                "- If OpenBox is unavailable, report a dependency blocker.",
                "- Do not silently fall back to TuRBO or manually choose candidates.",
            ]
        )
    command_name = "ic-opt --continue" if payload.get("continuation") else "run-native-turbo"
    return (
        "- Use native `Turbo1.optimize()` through "
        f"`{command_name}` without switching optimizer backend."
    )


def _continuation_note(payload: dict) -> str:
    if not payload.get("continuation"):
        return ""
    return (
        "- This is a continuation task: load existing accepted optimizer traces "
        "and evaluate only the requested additional candidates.\n"
    )


def _toolchain_gate(payload: dict) -> str:
    command = payload.get("toolchain_check_command")
    if not command:
        return ""
    return f"""
## Toolchain Gate

Run this before OpenBox real execution:

```bash
{shlex.join(command)}
```
"""


def _execution_environment(payload: dict) -> str:
    if payload["backend"] != OPENBOX_BACKEND:
        return ""
    venv_instruction = (
        "- Put the explicitly selected OpenBox execution venv first in `PATH`:\n"
        f"  `{payload['openbox_venv']}`."
        if payload.get("openbox_venv")
        else (
            "- Use the Python environment that provides the invoked "
            "`hermes-workflow`; no packaging-machine venv path is assumed."
        )
    )
    return f"""
## Execution Environment

- Source Cadence cshrc before the optimizer command:
  `{payload["cadence_cshrc"]}`.
{venv_instruction}
- Set `MPLCONFIGDIR` to a writable `/tmp` directory.
- Run real OpenBox/Spectre/OCEAN execution through a non-sandbox or escalated
  command path.
"""
