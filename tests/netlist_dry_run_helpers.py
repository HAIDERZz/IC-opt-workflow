"""Shared generic netlist/dry-run preflight helpers.

These helpers back ``tests/test_netlists.py`` and ``tests/test_dry_run.py``. They
build projects with ``tests/project_factory.py`` (never the packaged release
template) and derive approved variable names from ``config/variables.yaml``, so
the preflight contracts are exercised without coupling to any circuit-specific
template contents.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.project_factory import create_generic_project


def create_preflight_project(tmp_path: Path) -> Path:
    return create_generic_project(tmp_path)


def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    names = [variable["name"] for variable in payload["variables"]]
    assert len(names) == 2
    return names[0], names[1]


def top_level_parameters_line(
    project_dir: Path,
    *,
    include_first: bool = True,
    include_second: bool = True,
    duplicate_first: bool = False,
    whitespace_units: bool = False,
    extra: str = "temperature=27",
) -> str:
    first, second = variable_names(project_dir)
    parts = ["parameters", extra]
    if include_first:
        parts.append(f"{first}=4")
    if include_second:
        parts.append(f"{second}=0.6 u" if whitespace_units else f"{second}=0.6u")
    line = " ".join(parts)
    if duplicate_first:
        line += f"\nparameters {first}=5"
    return line


def exported_deck(
    project_dir: Path,
    *,
    parameter_line: str | None = None,
    body: str = "tran tran stop=10n\n",
) -> str:
    return "simulator lang=spectre\n" + (
        parameter_line or top_level_parameters_line(project_dir)
    ) + "\n" + body


def project_with_exported_input(tmp_path: Path, deck_text: str) -> Path:
    project_dir = create_preflight_project(tmp_path)
    input_path = project_dir / "netlists" / "exported" / "input.scs"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(deck_text, encoding="utf-8")
    return project_dir


def template_text(
    project_dir: Path,
    *,
    omit_first: bool = False,
    omit_second: bool = False,
    unexpected: str | None = None,
    malformed: str | None = None,
) -> str:
    first, second = variable_names(project_dir)
    parts = ["parameters"]
    if not omit_first:
        parts.append(f"{first}={{{{{first}}}}}")
    if not omit_second:
        parts.append(f"{second}={{{{{second}}}}}")
    if unexpected is not None:
        parts.append(f"{unexpected}={{{{{unexpected}}}}}")
    if malformed is not None:
        parts.append(f"BAD={{{{ {malformed} }}}}")
    return "simulator lang=spectre\n" + " ".join(parts) + "\ntran tran stop=10n\n"


def project_with_template(tmp_path: Path, text: str | None = None) -> Path:
    project_dir = create_preflight_project(tmp_path)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text or template_text(project_dir), encoding="utf-8")
    return project_dir


def assign_all_metrics_to_testbench(project_dir: Path, testbench_id: str) -> None:
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    for metric in payload.get("metrics", []):
        metric["testbench"] = testbench_id
    metrics_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
