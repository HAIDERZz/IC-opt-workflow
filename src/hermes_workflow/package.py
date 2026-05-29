from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path


TEMPLATE_PACKAGE = "hermes_workflow"
TEMPLATE_PATH = ("templates", "spectre_maestro_project")


class TemplateError(RuntimeError):
    pass


def _copy_template_tree(destination: Path) -> None:
    template = resources.files(TEMPLATE_PACKAGE).joinpath(*TEMPLATE_PATH)
    if not template.is_dir():
        raise TemplateError("project template is not packaged")

    for item in template.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        elif item.name != ".gitkeep":
            target.write_bytes(item.read_bytes())


def _copy_resource_directory(source: resources.abc.Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        elif item.name != ".gitkeep":
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
