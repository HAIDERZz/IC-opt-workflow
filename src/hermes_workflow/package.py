from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from pathlib import Path

from hermes_workflow.validate import ContractBundle, assert_valid_project


TEMPLATE_PACKAGE = "hermes_workflow"
TEMPLATE_PATH = ("templates", "spectre_maestro_project")
CONFIG_FILE_NAMES = [
    "project_config.yaml",
    "variables.yaml",
    "metrics.yaml",
    "spectre.yaml",
    "optimizer.yaml",
]


class TemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionManifest:
    path: Path
    payload: dict


def _copy_template_tree(destination: Path) -> None:
    template = resources.files(TEMPLATE_PACKAGE).joinpath(*TEMPLATE_PATH)
    if not template.is_dir():
        raise TemplateError("project template is not packaged")

    for item in template.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        else:
            target.write_bytes(item.read_bytes())


def _copy_resource_directory(source: resources.abc.Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        else:
            target.write_bytes(item.read_bytes())


def create_project_from_template(destination: Path, *, force: bool = False) -> Path:
    destination = Path(destination)
    if destination.exists() and not destination.is_dir():
        raise TemplateError("destination exists and is not a directory")
    if destination.exists() and force:
        shutil.rmtree(destination)
    elif destination.exists() and any(destination.iterdir()):
        raise TemplateError("destination already exists and is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    _copy_template_tree(destination)
    return destination


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def render_execution_task(project_dir: Path, manifest_payload: dict) -> str:
    return _render_execution_task(assert_valid_project(project_dir), manifest_payload)


def _render_execution_task(bundle: ContractBundle, manifest_payload: dict) -> str:
    variable_names = ", ".join(
        f"`{variable.name}`" for variable in bundle.variables.variables
    )
    metric_lines = "\n".join(
        f"- `{metric.name}` [{metric.unit}]: `{metric.maestro_formula}`"
        for metric in bundle.metrics.metrics
    )
    constraint_lines = "\n".join(
        f"- `{constraint.metric}` {constraint.op.value} `{constraint.value}`"
        for constraint in bundle.metrics.constraints
    )
    hash_lines = "\n".join(
        f"- `{path}`: `{digest}`"
        for path, digest in sorted(manifest_payload["immutable_config_files"].items())
    )
    return f"""# Claude Code Execution Task

Project: `{bundle.project_config.project.name}`
Backend: `{bundle.project_config.project.backend}`
Created at UTC: `{manifest_payload["created_at_utc"]}`

## Scope

Use `virtuoso-bridge-lite` skills only for tool-side actions. Inspect or export the configured Maestro testbench, then export or place the Spectre deck at `netlists/exported/input.scs`. Do not run deterministic preflight or a real Spectre optimization before Hermes approval.

## Testbench

- Virtuoso library: `{bundle.project_config.testbench.virtuoso_library}`
- Cell: `{bundle.project_config.testbench.cell}`
- Design view: `{bundle.project_config.testbench.design_view}`
- Maestro view: `{bundle.project_config.testbench.maestro_view}`
- Test name: `{bundle.project_config.testbench.test_name}`
- Corner: `{bundle.project_config.testbench.corner}`

## Allowed Variables

Only template these variables in the exported Spectre deck: {variable_names}

## Metrics

{metric_lines}

## Constraints

{constraint_lines}

## Objective

- Direction: `{bundle.metrics.objective.direction.value}`
- Expression: `{bundle.metrics.objective.expression}`

## Spectre Policy

- Engine: `spectre_x`
- Spectre X preset: `{bundle.spectre.spectre.preset.value}`
- Output format: `{bundle.spectre.spectre.output_format}`
- Candidate-level parallel jobs: `{bundle.spectre.spectre.parallel_jobs}`
- Per-candidate timeout seconds: `{bundle.spectre.spectre.timeout_s}`

## Execution Agent Responsibilities

- Preserve Maestro setup: analyses, model includes, simulator options, save options, corners, constraints, objective, variable bounds, and variable step sizes.
- Export or place the Spectre deck at `netlists/exported/input.scs`.
- Do not template variables directly.
- Do not write `reports/netlist_preparation_report.json`.
- Do not write `reports/dry_run_report.json`.
- Do not write `state/health_check.json`.
- Stop after export and wait for Hermes deterministic preflight.

## Hermes Preflight Commands

Hermes will run these commands from the supervisor side:

```bash
hermes-workflow prepare-netlist PROJECT_DIR
hermes-workflow dry-run PROJECT_DIR
hermes-workflow preflight-health PROJECT_DIR
hermes-workflow approve PROJECT_DIR
```

## Safety Rules

- Do not modify Maestro setup.
- Do not change analysis statements, model includes, simulator options, save options, constraints, objective, variable bounds, or variable step sizes.
- Template only approved variables when Hermes prepares `template.scs`.
- Wait for `supervisor_instruction.json` before the first real Spectre run.

## Immutable Config Hashes

{hash_lines}
"""


def build_execution_package(
    project_dir: Path,
    *,
    created_at_utc: str | None = None,
) -> ExecutionManifest:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    execution_dir = project_dir / "execution_package"
    config_destination = execution_dir / "config"
    manifest_path = execution_dir / "execution_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"execution package already exists: {manifest_path}")

    execution_dir.mkdir(parents=True, exist_ok=True)
    config_destination.mkdir(parents=True, exist_ok=True)

    immutable_hashes: dict[str, str] = {}
    for file_name in CONFIG_FILE_NAMES:
        source = project_dir / "config" / file_name
        destination = config_destination / file_name
        shutil.copy2(source, destination)
        immutable_hashes[f"config/{file_name}"] = sha256_file(source)

    created_at = created_at_utc or (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    payload = {
        "schema_version": "1.0",
        "project_name": bundle.project_config.project.name,
        "created_at_utc": created_at,
        "source_project_dir": str(project_dir.resolve()),
        "immutable_config_files": immutable_hashes,
        "required_preflight_reports": [
            "reports/netlist_preparation_report.json",
            "reports/dry_run_report.json",
            "state/health_check.json",
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    task_text = _render_execution_task(bundle, payload)
    (execution_dir / "EXECUTION_TASK.md").write_text(task_text, encoding="utf-8")
    return ExecutionManifest(path=manifest_path, payload=payload)
