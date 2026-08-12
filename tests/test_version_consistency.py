"""Guard against the three release version sources drifting apart.

VERSION, pyproject.toml's [project].version, and hermes_workflow.__version__
are all hand-maintained. A release that bumps one and forgets the others
ships an internally inconsistent package, so this test fails loudly instead.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import hermes_workflow

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = r"\d+\.\d+\.\d+"


def _pyproject_version() -> str:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return payload["project"]["version"]


def test_version_sources_agree() -> None:
    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject_version = _pyproject_version()
    package_version = hermes_workflow.__version__

    assert version_file == pyproject_version == package_version, (
        f"version mismatch: VERSION={version_file!r} "
        f"pyproject.toml [project].version={pyproject_version!r} "
        f"hermes_workflow.__version__={package_version!r}"
    )


def test_version_matches_semantic_format() -> None:
    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert re.fullmatch(VERSION_PATTERN, version_file), (
        f"VERSION content {version_file!r} does not match X.Y.Z"
    )
