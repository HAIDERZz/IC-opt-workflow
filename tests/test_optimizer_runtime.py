from __future__ import annotations

import sys
from pathlib import Path

import hermes_workflow
from hermes_workflow.native_turbo import DEFAULT_TURBO_PATH
from hermes_workflow.optimizer_runtime import check_controller_optimizer_runtime


def _optimizer_sections(
    *,
    algorithm: str,
    strategy: str,
    initialization: str = "latin_hypercube",
) -> dict[str, object]:
    return {
        "Optimizer Settings": {
            "algorithm": algorithm,
            "strategy": strategy,
            "initialization": initialization,
            "max_evaluations": 100,
        },
        "Design Variables": [{"name": "x"}],
    }


def test_controller_optimizer_runtime_checks_native_sobol_dependencies() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    original_sys_path = list(sys.path)

    def load_dependency(module: str, attributes: tuple[str, ...]) -> object:
        calls.append((module, attributes))
        assert str(DEFAULT_TURBO_PATH) in sys.path
        return object()

    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="turbo",
            strategy="turbo_trust_region",
            initialization="sobol",
        ),
        workflow_mode="optimize",
        dependency_loader=load_dependency,
    )

    assert report["status"] == "pass"
    assert report["resolved_backend"] == "native_turbo"
    assert report["initialization"] == "sobol"
    assert report["turbo_path"] == str(DEFAULT_TURBO_PATH)
    assert calls == [
        ("turbo", ("Turbo1",)),
        (
            "turbo.utils",
            ("latin_hypercube", "from_unit_cube", "to_unit_cube"),
        ),
        ("numpy", ()),
        ("torch", ()),
        ("gpytorch", ()),
        ("threadpoolctl", ("threadpool_info",)),
        ("scipy.stats.qmc", ("Sobol",)),
    ]
    assert sys.path == original_sys_path


def test_controller_optimizer_runtime_native_latin_skips_scipy_sobol() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="turbo",
            strategy="turbo_trust_region",
        ),
        workflow_mode="optimize",
        dependency_loader=lambda module, attributes: calls.append(
            (module, attributes)
        ),
    )

    assert report["status"] == "pass"
    assert not any(module == "scipy.stats.qmc" for module, _ in calls)


def test_controller_optimizer_runtime_checks_real_openbox_contract() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="openbox",
            strategy="openbox_gp_eic",
            initialization="sobol",
        ),
        workflow_mode="optimize",
        dependency_loader=lambda module, attributes: calls.append(
            (module, attributes)
        ),
    )

    assert report["status"] == "pass"
    assert report["resolved_backend"] == "openbox"
    assert report["turbo_path"] is None
    assert calls == [
        ("hermes_workflow.openbox_backend", ("_load_openbox",)),
        ("openbox", ("Advisor", "Observation", "space")),
        ("openbox.core.initial_config", ("InitialConfigProvider",)),
        ("openbox.utils.history", ("History",)),
    ]


def test_controller_optimizer_runtime_random_baseline_checks_hermes_backend() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="random",
            strategy="random_baseline",
        ),
        workflow_mode="optimize",
        dependency_loader=lambda module, attributes: calls.append(
            (module, attributes)
        ),
    )

    assert report["status"] == "pass"
    assert report["resolved_backend"] == "random_baseline"
    assert calls == [
        (
            "hermes_workflow.openbox_backend",
            ("_create_random_baseline_advisor",),
        )
    ]


def test_controller_optimizer_runtime_fix_run_is_explicitly_skipped() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    report = check_controller_optimizer_runtime(
        {},
        workflow_mode="fix_run",
        dependency_loader=lambda module, attributes: calls.append(
            (module, attributes)
        ),
    )

    assert report["status"] == "skipped"
    assert report["resolved_backend"] is None
    assert "does not use an optimizer" in report["detail"]
    assert calls == []


def test_controller_optimizer_runtime_reports_each_missing_dependency() -> None:
    def load_dependency(module: str, _attributes: tuple[str, ...]) -> object:
        if module in {"gpytorch", "threadpoolctl"}:
            raise ModuleNotFoundError(module)
        return object()

    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="turbo",
            strategy="turbo_trust_region",
            initialization="sobol",
        ),
        workflow_mode="optimize",
        dependency_loader=load_dependency,
    )

    assert report["status"] == "fail"
    assert [check["name"] for check in report["checks"] if check["status"] == "fail"] == [
        "gpytorch",
        "threadpoolctl",
    ]
    assert report["issues"] == [
        "gpytorch import failed: gpytorch",
        "threadpoolctl import failed: threadpoolctl",
    ]


def test_controller_optimizer_runtime_reports_current_process_module_sources() -> None:
    report = check_controller_optimizer_runtime(
        _optimizer_sections(
            algorithm="openbox",
            strategy="openbox_auto",
        ),
        workflow_mode="optimize",
    )

    hermes_backend = next(
        check
        for check in report["checks"]
        if check["name"] == "hermes_workflow.openbox_backend"
    )
    assert report["status"] == "pass"
    assert Path(hermes_backend["module_file"]).resolve().parent == Path(
        hermes_workflow.__file__
    ).resolve().parent
