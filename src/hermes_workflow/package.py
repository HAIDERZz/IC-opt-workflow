from __future__ import annotations

import shutil
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "spectre_maestro_project"


class TemplateError(RuntimeError):
    pass


def create_project_from_template(destination: Path, *, force: bool = False) -> Path:
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()) and not force:
        raise TemplateError("destination already exists and is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_DIR, destination, dirs_exist_ok=True)
    return destination
