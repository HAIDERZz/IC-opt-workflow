from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from pathlib import Path

from hermes_workflow.validate import assert_valid_project


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
    return ExecutionManifest(path=manifest_path, payload=payload)
