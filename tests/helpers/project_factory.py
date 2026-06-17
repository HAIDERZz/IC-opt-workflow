"""Generic, release-template-independent project factory for tests.

Product tests must not depend on the packaged release template (Mixer/NF_3G).
This helper builds a minimal, internally-consistent project with *arbitrary*
variables, metrics, constraints, objective, optimizer and Spectre settings, so
generic optimizer / dry-run / real-run / result-recording tests can exercise the
pipeline without coupling to one specific release example.

The defaults are deliberately generic (``v0``/``v1`` variables, a single
``score`` metric) and are NOT the release template; every aspect is overridable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_VARIABLES: list[dict[str, str]] = [
    {"name": "v0", "kind": "integer", "lower": "1", "upper": "4", "step": "1"},
    {
        "name": "v1",
        "kind": "continuous_step",
        "lower": "1u",
        "upper": "2u",
        "step": "0.2u",
    },
]

DEFAULT_METRICS: list[dict[str, Any]] = [
    {"name": "score", "unit": "u", "maestro_formula": "score"},
]


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def build_project(
    destination: Path,
    *,
    variables: list[dict[str, Any]] | None = None,
    metrics: list[dict[str, Any]] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    objective: dict[str, Any] | None = None,
    optimizer: dict[str, Any] | None = None,
    spectre: dict[str, Any] | None = None,
    project_config: dict[str, Any] | None = None,
    project_name: str = "generic_test_project",
) -> Path:
    """Create a minimal valid project tree with arbitrary contract contents.

    The written project is pipeline-ready: consistent config files plus a
    netlist template carrying a placeholder for every declared variable and a
    minimal exported input deck, so it passes ``assert_valid_project`` and the
    real-run/dry-run pipelines.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    selected_variables = variables if variables is not None else DEFAULT_VARIABLES
    selected_metrics = metrics if metrics is not None else DEFAULT_METRICS
    metric_names = [metric["name"] for metric in selected_metrics]
    selected_constraints = constraints if constraints is not None else []
    if objective is None:
        selected_objective: dict[str, Any] = {
            "direction": "minimize",
            "expression": metric_names[0],
        }
    else:
        selected_objective = objective

    config_dir = destination / "config"
    _write_yaml(
        config_dir / "project_config.yaml",
        project_config
        or {
            "schema_version": "1.0",
            "project": {
                "name": project_name,
                "description": "Generic release-template-independent test project.",
                "backend": "maestro_exported_spectre_deck",
            },
            "testbench": {
                "virtuoso_library": "Virtuoso_Bridge_test",
                "cell": "GenericCell",
                "design_view": "maestro",
                "maestro_view": "maestro",
                "test_name": "Generic_Test",
                "corner": "Nominal",
            },
            "netlist": {
                "source": "existing_maestro_setup",
                "export_method": "maeCreateNetlistForCorner",
                "exported_input_scs": "netlists/exported/input.scs",
                "template_scs": "netlists/templates/template.scs",
            },
            "safety": {
                "immutable_after_package": True,
                "require_hermes_approval_before_real_run": True,
                "allow_maestro_setup_modification": False,
                "allow_only_variable_templating": True,
            },
        },
    )
    _write_yaml(
        config_dir / "variables.yaml",
        {"schema_version": "1.0", "variables": selected_variables},
    )
    _write_yaml(
        config_dir / "metrics.yaml",
        {
            "schema_version": "1.0",
            "metrics": selected_metrics,
            "constraints": selected_constraints,
            "objective": selected_objective,
        },
    )
    _write_yaml(
        config_dir / "optimizer.yaml",
        {"schema_version": "1.0", "optimizer": optimizer or _default_optimizer()},
    )
    _write_yaml(
        config_dir / "spectre.yaml",
        {"schema_version": "1.0", "spectre": spectre or _default_spectre()},
    )

    netlist_template = destination / "netlists" / "templates" / "template.scs"
    netlist_template.parent.mkdir(parents=True, exist_ok=True)
    placeholder_tokens: list[str] = []
    for variable in selected_variables:
        name = str(variable["name"])
        placeholder_tokens.append(name + "={{" + name + "}}")
    placeholders = " ".join(placeholder_tokens)
    netlist_template.write_text(
        "simulator lang=spectre\n"
        f"parameters {placeholders}\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )
    exported_input = destination / "netlists" / "exported" / "input.scs"
    exported_input.parent.mkdir(parents=True, exist_ok=True)
    exported_input.write_text("simulator lang=spectre\n", encoding="utf-8")

    return destination


def _default_optimizer() -> dict[str, Any]:
    return {
        "algorithm": "openbox",
        "strategy": "openbox_auto",
        "initialization": "sobol",
        "max_evaluations": 12,
        "batch_size": 4,
        "random_seed": 7,
        "optimizer_cpu_threads": 4,
        "failure_penalty": 1000000.0,
        "deduplicate_candidates": True,
    }


def _default_spectre() -> dict[str, Any]:
    return {
        "engine": "spectre_x",
        "preset": "ax",
        "output_format": "psfxl",
        "threads_per_run": 10,
        "parallel_jobs": 4,
        "timeout_s": 3600,
        "require_license_check": True,
        "keep_failed_runs": True,
        "keep_successful_runs": True,
    }


def variable_names(project_dir: Path) -> list[str]:
    """Read declared variable names back from a built project's config."""
    payload = yaml.safe_load(
        (Path(project_dir) / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return [variable["name"] for variable in payload["variables"]]


def write_template_for_project(project_dir: Path) -> Path:
    """Write a netlist template whose placeholders match the project variables.

    Generic tests must not hardcode one circuit's variable names. This derives
    the ``parameters`` line from the project's declared variables so the
    rendered candidate deck is always consistent with whatever config the
    project carries (release template or otherwise).
    """
    names = variable_names(project_dir)
    placeholders = " ".join(name + "={{" + name + "}}" for name in names)
    template_path = Path(project_dir) / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\n"
        f"parameters {placeholders}\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )
    return template_path


def metric_names(project_dir: Path) -> list[str]:
    """Read declared metric names back from a built project's config."""
    payload = yaml.safe_load(
        (Path(project_dir) / "config" / "metrics.yaml").read_text(encoding="utf-8")
    )
    return [metric["name"] for metric in payload["metrics"]]
