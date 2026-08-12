from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from hermes_workflow.doctor_readiness import build_optimizer_summary
from hermes_workflow.native_turbo import DEFAULT_TURBO_PATH


DependencyLoader = Callable[[str, tuple[str, ...]], object]


def check_controller_optimizer_runtime(
    sections: dict[str, Any],
    *,
    workflow_mode: str,
    dependency_loader: DependencyLoader | None = None,
) -> dict[str, Any]:
    """Check optimizer imports in the current Controller Python process."""

    if workflow_mode == "fix_run":
        return _report(
            status="skipped",
            workflow_mode=workflow_mode,
            resolved_backend=None,
            initialization=None,
            turbo_path=None,
            checks=[],
            issues=[],
            detail="fix_run does not use an optimizer runtime",
        )

    optimizer_section = sections.get("Optimizer Settings")
    variables = sections.get("Design Variables")
    if not isinstance(optimizer_section, dict):
        return _report(
            status="fail",
            workflow_mode=workflow_mode,
            resolved_backend=None,
            initialization=None,
            turbo_path=None,
            checks=[],
            issues=["Optimizer Settings are unavailable"],
        )

    try:
        optimizer_summary = build_optimizer_summary(
            optimizer_section=optimizer_section,
            variable_count=len(variables) if isinstance(variables, list) else 0,
            cli_max_evals=None,
        )
    except (TypeError, ValueError) as exc:
        return _report(
            status="fail",
            workflow_mode=workflow_mode,
            resolved_backend=None,
            initialization=None,
            turbo_path=None,
            checks=[],
            issues=[f"optimizer strategy resolution failed: {exc}"],
        )

    resolved_backend = str(optimizer_summary["resolved_backend"])
    initialization_value = optimizer_section.get("initialization")
    initialization = (
        initialization_value if isinstance(initialization_value, str) else None
    )
    loader = dependency_loader or _load_dependency
    dependency_specs: list[tuple[str, tuple[str, ...]]] = []
    turbo_path: Path | None = None
    if resolved_backend == "native_turbo":
        turbo_path = DEFAULT_TURBO_PATH
        dependency_specs = [
            ("turbo", ("Turbo1",)),
            (
                "turbo.utils",
                ("latin_hypercube", "from_unit_cube", "to_unit_cube"),
            ),
            ("numpy", ()),
            ("torch", ()),
            ("gpytorch", ()),
            ("threadpoolctl", ("threadpool_info",)),
        ]
        if initialization == "sobol":
            dependency_specs.append(("scipy.stats.qmc", ("Sobol",)))
    elif resolved_backend == "openbox":
        dependency_specs = [
            ("hermes_workflow.openbox_backend", ("_load_openbox",)),
            ("openbox", ("Advisor", "Observation", "space")),
            ("openbox.core.initial_config", ("InitialConfigProvider",)),
            ("openbox.utils.history", ("History",)),
        ]
    elif resolved_backend == "random_baseline":
        dependency_specs = [
            (
                "hermes_workflow.openbox_backend",
                ("_create_random_baseline_advisor",),
            )
        ]

    checks: list[dict[str, Any]] = []
    issues: list[str] = []
    with _temporary_import_path(turbo_path):
        for module, attributes in dependency_specs:
            try:
                loaded = loader(module, attributes)
            except Exception as exc:
                detail = f"{module} import failed: {exc}"
                checks.append(
                    {
                        "name": module,
                        "status": "fail",
                        "attributes": list(attributes),
                        "module_file": None,
                        "detail": detail,
                    }
                )
                issues.append(detail)
                continue
            checks.append(
                {
                    "name": module,
                    "status": "pass",
                    "attributes": list(attributes),
                    "module_file": getattr(loaded, "__file__", None),
                    "detail": "dependency is importable",
                }
            )

    return _report(
        status="pass" if not issues else "fail",
        workflow_mode=workflow_mode,
        resolved_backend=resolved_backend,
        initialization=initialization,
        turbo_path=turbo_path,
        checks=checks,
        issues=issues,
    )


def _load_dependency(module: str, attributes: tuple[str, ...]) -> object:
    loaded = importlib.import_module(module)
    for attribute in attributes:
        getattr(loaded, attribute)
    return loaded


@contextmanager
def _temporary_import_path(path: Path | None) -> Iterator[None]:
    value = str(path) if path is not None else None
    inserted = value is not None and value not in sys.path
    if inserted:
        sys.path.insert(0, value)
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(value)


def _report(
    *,
    status: str,
    workflow_mode: str,
    resolved_backend: str | None,
    initialization: str | None,
    turbo_path: Path | None,
    checks: list[dict[str, Any]],
    issues: list[str],
    detail: str | None = None,
) -> dict[str, Any]:
    if detail is None:
        if issues:
            detail = "; ".join(issues)
        elif resolved_backend is not None:
            detail = (
                f"Controller dependencies for resolved backend "
                f"{resolved_backend} are importable"
            )
            if turbo_path is not None:
                detail += f"; turbo_path={turbo_path}"
        else:
            detail = "Controller optimizer runtime was not checked"
    return {
        "schema_version": "1.0",
        "status": status,
        "workflow_mode": workflow_mode,
        "resolved_backend": resolved_backend,
        "initialization": initialization,
        "turbo_path": str(turbo_path) if turbo_path is not None else None,
        "checks": checks,
        "issues": issues,
        "detail": detail,
    }
