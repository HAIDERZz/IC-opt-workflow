from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.cli import app
from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run
from hermes_workflow.openbox_backend import (
    OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE,
    OPENBOX_EFFECTIVENESS_AUDIT_RELATIVE,
    _build_openbox_advisor,
    _build_openbox_space,
    _create_advisor,
    run_openbox_fake_optimization,
    run_openbox_real_optimization,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from hermes_workflow.history_warm_start import HISTORY_WARM_START_AUDIT_RELATIVE
from hermes_workflow.package import build_execution_package
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.validate import assert_valid_project
from tests.project_factory import create_generic_project
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    default_metric_values,
    variable_names,
)
from tests.report_helpers import write_pass_reports
from tests.test_multi_testbench_aggregation import (
    _create_ready_multi_corner_multi_testbench_project,
    _write_corner_child_handoff,
)


# ---------------------------------------------------------------------------
# Local helpers (structured YAML mutation; no template tokens)
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _set_optimizer_value(project_dir: Path, key: str, value) -> None:
    """Structured YAML mutation of a single ``optimizer.<key>`` value."""
    path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(path)
    payload["optimizer"][key] = value
    _write_yaml(path, payload)


def _set_spectre_value(project_dir: Path, key: str, value) -> None:
    """Structured YAML mutation of a single ``spectre.<key>`` value."""
    path = project_dir / "config" / "spectre.yaml"
    payload = _read_yaml(path)
    payload["spectre"][key] = value
    _write_yaml(path, payload)


def _metric_names_from_config(project_dir: Path) -> list[str]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    return [metric["name"] for metric in payload["metrics"]]


def _passing_metric_values_from_config(project_dir: Path) -> dict[str, float]:
    names = _metric_names_from_config(project_dir)
    # Two metrics: objective metric and constraint metric. The passing values
    # satisfy the objective/constraint contract (constraint metric well below
    # its ``lt`` threshold).
    return {names[0]: 1.0, names[1]: 1.0e-4}


def _constraint_failing_metric_values_from_config(project_dir: Path) -> dict[str, float]:
    names = _metric_names_from_config(project_dir)
    # Objective metric nominal; constraint metric above its ``lt`` threshold.
    return {names[0]: 1.0, names[1]: 1.0}


def _create_openbox_project(
    tmp_path: Path,
    *,
    name: str = "openbox_project",
    mutate_config=None,
    prepare: bool = True,
    **kwargs,
) -> Path:
    """Create a generic project, optionally mutate config, then
    package + approve + (optionally) prepare.

    Extra kwargs are forwarded to :func:`create_generic_project`
    (``max_evaluations``, ``batch_size``, ``parallel_jobs``).

    ``mutate_config``, if given, is called with the project dir after the
    generic project is created but BEFORE packaging, so config edits are
    captured in the approved config hashes (post-package edits would trip the
    immutable-config-drift guard).
    """
    project_dir = create_generic_project(tmp_path, name=name, **kwargs)
    if mutate_config is not None:
        mutate_config(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir, variable_names=_project_variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    if prepare:
        prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


def _project_variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    return tuple(variable["name"] for variable in payload["variables"])


def _suggestion_from_grid(
    project_dir: Path, int_value: float, width_value: float
) -> dict[str, float]:
    int_name, width_name = _project_variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}


def _advisor_batches_for_project(project_dir: Path) -> list[list[dict[str, float]]]:
    """Two batches of two suggestions each, keyed by the project's variable
    names. Mirrors :func:`advisor_batches` but kept local so this module has a
    self-contained, config-derived contract."""
    return [
        [
            _suggestion_from_grid(project_dir, 2, 0.2),
            _suggestion_from_grid(project_dir, 4, 0.4),
        ],
        [
            _suggestion_from_grid(project_dir, 3, 0.3),
            _suggestion_from_grid(project_dir, 5, 0.5),
        ],
    ]


class FakeAdvisor:
    def __init__(self, project_dir: Path) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        grid = _project_variable_grid(project_dir)
        # For generic 2-variable projects use the local advisor-batch helper
        # so this file stays self-contained after the template-coupling cleanup.
        # Projects with a different variable count (the 4-variable multi-corner
        # projects) build their batches from each variable's configured grid so
        # the suggestions stay in range without hardcoding variable names.
        if len(grid) == 2:
            self._batches = _advisor_batches_for_project(project_dir)
        else:
            self._batches = _grid_seeded_batches(grid)

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        batch = self._batches.pop(0)
        return batch[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        self.updated_observations.extend(observations)
        assert observations


class FakeOpenBoxVisualizer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.html_path = output_dir / "hermes_openbox_real.html"
        self.json_path = output_dir / "visualization_data_hermes_openbox_real.json"


class FakeOpenBoxHistory:
    def __init__(self, *, fail: bool = False, partial: bool = False) -> None:
        self.fail = fail
        self.partial = partial
        self.calls: list[dict[str, object]] = []

    def visualize_html(
        self,
        *,
        logging_dir: str,
        open_html: bool,
        show_importance: bool,
        verify_surrogate: bool,
        advisor: object,
        task_info: dict[str, object],
    ) -> FakeOpenBoxVisualizer:
        self.calls.append(
            {
                "logging_dir": logging_dir,
                "open_html": open_html,
                "show_importance": show_importance,
                "verify_surrogate": verify_surrogate,
                "advisor": advisor,
                "task_info": task_info,
            }
        )
        if self.fail:
            raise ModuleNotFoundError("No module named 'shap'")
        output_dir = Path(logging_dir) / "history" / "hermes_openbox_real"
        output_dir.mkdir(parents=True, exist_ok=True)
        visualizer = FakeOpenBoxVisualizer(output_dir)
        visualizer.html_path.write_text("<html>advanced</html>", encoding="utf-8")
        if self.partial:
            data = 'var info={"data": {"importance_data": null}};'
        else:
            data = (
                'var info={"data": {'
                '"importance_data": {"data": {}}, '
                '"pred_label_data": {"data": []}, '
                '"grade_data": {"data": []}, '
                '"cons_pred_label_data": {"data": []}'
                "}};"
            )
        visualizer.json_path.write_text(data, encoding="utf-8")
        return visualizer


class VisualizingAdvisor(FakeAdvisor):
    def __init__(
        self, project_dir: Path, *, fail: bool = False, partial: bool = False
    ) -> None:
        super().__init__(project_dir)
        self.history = FakeOpenBoxHistory(fail=fail, partial=partial)

    def get_history(self) -> FakeOpenBoxHistory:
        return self.history


class ContinuationAdvisor:
    def __init__(self, project_dir: Path) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self.seen_prior_before_suggest = False
        baseline = _advisor_batches_for_project(project_dir)
        first_prior = baseline[0][0]
        unique_a = baseline[1][0]
        unique_b = baseline[1][1]
        # First suggestion repeats a prior candidate (drives one duplicate
        # replacement); the rest are fresh unique candidates.
        self._batches = [
            [first_prior, unique_a],
            [unique_b],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        self.seen_prior_before_suggest = len(self.updated_observations) == 2
        batch = self._batches.pop(0)
        return batch[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        self.updated_observations.extend(observations)
        assert observations


class ExhaustingContinuationAdvisor:
    def __init__(self, project_dir: Path) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self.calls = 0
        self._project_dir = project_dir

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        self.calls += 1
        baseline = _advisor_batches_for_project(self._project_dir)
        first_prior = baseline[0][0]
        unique = baseline[1][0]
        if self.calls == 1:
            return [first_prior, unique][:batch_size]
        return [first_prior][:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        self.updated_observations.extend(observations)
        assert observations


class SequentialAdvisor:
    def __init__(self, project_dir: Path, *, start: int = 0) -> None:
        self.index = start
        self.updated_observations: list[object] = []
        self._grid = _project_variable_grid(project_dir)

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        suggestions: list[dict[str, float]] = []
        for slot in range(batch_size):
            value = self.index + slot
            suggestion: dict[str, float] = {}
            for offset, spec in enumerate(self._grid):
                grid = spec["grid"]
                pick = grid[(value + offset) % len(grid)]
                suggestion[spec["name"]] = pick
            suggestions.append(suggestion)
        self.index += batch_size
        return suggestions

    def update_observations(self, observations: list[object]) -> None:
        self.updated_observations.extend(observations)
        assert observations


def _project_variable_grid(project_dir: Path) -> list[dict[str, object]]:
    """Return each variable's name and the list of raw float values on its
    configured grid (lower, lower+step, ..., upper). Used to fabricate unique,
    in-range advisor suggestions keyed by the project's actual variable names,
    regardless of whether the project is the generic 2-variable variant or a
    multi-corner/multi-testbench project with more variables.
    """
    from hermes_workflow.openbox_backend import _parse_decimal_unit

    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    grid: list[dict[str, object]] = []
    for variable in payload["variables"]:
        name = variable["name"]
        kind = variable["kind"]
        if kind == "integer":
            lower = int(variable["lower"])
            upper = int(variable["upper"])
            step = int(variable["step"])
            values = [float(value) for value in range(lower, upper + 1, step)]
        else:
            lower, _unit = _parse_decimal_unit(variable["lower"])
            upper, _ = _parse_decimal_unit(variable["upper"])
            step, _ = _parse_decimal_unit(variable["step"])
            max_offset = int((upper - lower) / step)
            values = [
                float(lower + Decimal(offset) * step)
                for offset in range(max_offset + 1)
            ]
        grid.append({"name": name, "grid": values})
    return grid


def _grid_seeded_batches(
    grid: list[dict[str, object]],
) -> list[list[dict[str, float]]]:
    """Build two batches of two suggestions each from a project's variable
    grid. Used for multi-variable projects (e.g. the multi-testbench
    requirement project) so the advisor returns in-range, config-derived
    suggestions without hardcoding variable names.

    Offsets start at 1 (not 0) to avoid colliding with the prepared
    ``real_001`` candidate, which uses each variable's grid lower bound
    (offset 0). Picks four distinct, well-separated offsets so each
    suggestion is unique, clamping the upper offset to the grid length.
    """
    batches: list[list[dict[str, float]]] = []
    for batch_offsets in ((1, 3), (5, 7)):
        batch: list[dict[str, float]] = []
        for offset in batch_offsets:
            suggestion: dict[str, float] = {}
            for variable in grid:
                values = variable["grid"]
                index = min(offset, len(values) - 1)
                suggestion[variable["name"]] = values[index]
            batch.append(suggestion)
        batches.append(batch)
    return batches


class FakeVariable:
    def __init__(self, name: str, lower: object, upper: object, **kwargs) -> None:
        self.name = name
        self.lower = lower
        self.upper = upper
        self.kwargs = kwargs


class FakeSpace:
    def __init__(self) -> None:
        self.variables: list[FakeVariable] = []

    def add_variable(self, variable: FakeVariable) -> None:
        self.variables.append(variable)


class FakeSpaceModule:
    Space = FakeSpace
    Int = FakeVariable
    Real = FakeVariable


def _widen_variable_grid(project_dir: Path) -> None:
    """Widen the generic project's two-variable grid so advisor/continuation
    tests that need many unique candidates (e.g. the 45-evaluation model-replay
    cap test) have enough headroom. VAR_INT 1..100 and VAR_WIDTH 0.1u..10u give
    100x100 = 10_000 unique grid points."""
    payload = {
        "schema_version": "1.0",
        "variables": [
            {
                "name": "VAR_INT",
                "kind": "integer",
                "lower": "1",
                "upper": "100",
                "step": "1",
            },
            {
                "name": "VAR_WIDTH",
                "kind": "continuous_step",
                "lower": "0.1u",
                "upper": "10u",
                "step": "0.1u",
            },
        ],
    }
    _write_yaml(project_dir / "config" / "variables.yaml", payload)


def create_approved_real_project_with_optimizer_max(
    tmp_path: Path,
    max_evaluations: int,
) -> Path:
    def _mutate(project_dir: Path) -> None:
        _widen_variable_grid(project_dir)
        _set_optimizer_value(project_dir, "max_evaluations", max_evaluations)

    return _create_openbox_project(
        tmp_path,
        name="openbox_optimizer_max_project",
        max_evaluations=max_evaluations,
        mutate_config=_mutate,
    )


def test_openbox_space_uses_effective_grid_upper(tmp_path: Path) -> None:
    bundle = assert_valid_project(create_approved_real_project(tmp_path))

    space = _build_openbox_space(bundle.variables, FakeSpaceModule)
    by_name = {variable.name: variable for variable in space.variables}

    assert by_name["VAR_INT"].upper == 5
    assert by_name["VAR_WIDTH"].upper == 0.5
    assert list(by_name) == ["VAR_INT", "VAR_WIDTH"]


def test_openbox_fake_runner_writes_backend_neutral_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    result = run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]

    assert result.evaluation_count == 4
    assert report["backend"] == "openbox"
    assert report["execution_mode"] == "fake"
    assert report["evaluations"] == EVALUATIONS_RELATIVE.as_posix()
    assert report["batch_summary"]["status_counts"]
    assert report["openbox"]["duplicate_replacements"] == 0
    assert len(rows) == 4
    assert rows[0]["parameters"]["VAR_WIDTH"].endswith("u")
    assert "VAR_INT" in rows[0]["parameters"]
    assert rows[0]["parameters"] != rows[1]["parameters"]
    assert rows[0]["result_manifest"] is None
    assert rows[0]["metric_result_manifest"] is None
    assert rows[0]["batch_id"] == "batch_001"


def test_openbox_fake_runner_applies_optimizer_cpu_thread_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_value(project_dir, "optimizer_cpu_threads", 3)
    calls: list[tuple[int, dict[str, object]]] = []

    @contextmanager
    def fake_limits(threads: int, **kwargs):
        calls.append((threads, dict(kwargs)))
        yield

    monkeypatch.setattr(module, "optimizer_cpu_thread_limits", fake_limits)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    assert calls
    assert all(call[0] == 3 for call in calls)
    assert any(call[1].get("set_environment") is True for call in calls)


def test_openbox_runner_writes_advanced_visualization_artifact(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    advisor = VisualizingAdvisor(project_dir)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: advisor,
    )

    manifest = json.loads(
        (project_dir / OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE).read_text(
            encoding="utf-8"
        )
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))

    assert advisor.history.calls
    assert advisor.history.calls[0]["open_html"] is False
    assert advisor.history.calls[0]["show_importance"] is True
    assert advisor.history.calls[0]["verify_surrogate"] is True
    assert manifest["status"] == "generated"
    assert manifest["includes"] == [
        "objective_and_constraint_history",
        "surrogate_fit_verification",
        "parameter_importance",
    ]
    assert manifest["html_path"].endswith("hermes_openbox_real.html")
    assert manifest["json_path"].endswith("visualization_data_hermes_openbox_real.json")
    assert (project_dir / manifest["html_path"]).exists()
    assert report["openbox"]["advanced_visualization"]["status"] == "generated"
    assert report["openbox"]["advanced_visualization"]["manifest_path"] == (
        OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE.as_posix()
    )


def test_openbox_runner_records_advanced_visualization_dependency_failure(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    advisor = VisualizingAdvisor(project_dir, fail=True)

    result = run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: advisor,
    )

    manifest = json.loads(
        (project_dir / OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE).read_text(
            encoding="utf-8"
        )
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))

    assert result.evaluation_count == 2
    assert manifest["status"] == "failed"
    assert manifest["failure_kind"] == "dependency_missing"
    assert "shap" in manifest["reason"]
    assert report["status"] == "completed"
    assert report["openbox"]["advanced_visualization"]["status"] == "failed"


def test_openbox_runner_records_partial_advanced_visualization(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    advisor = VisualizingAdvisor(project_dir, partial=True)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: advisor,
    )

    manifest = json.loads(
        (project_dir / OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE).read_text(
            encoding="utf-8"
        )
    )

    assert manifest["status"] == "generated_partial"
    assert manifest["includes"] == ["objective_and_constraint_history"]
    assert "parameter importance data was not generated" in manifest["warnings"]


def test_openbox_fake_continuation_warm_starts_and_writes_cumulative_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    advisor = ContinuationAdvisor(project_dir)

    result = run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: advisor,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]

    assert advisor.seen_prior_before_suggest is True
    assert advisor.updated_batches == 2
    assert result.evaluation_count == 4
    assert report["evaluation_count"] == 4
    assert report["openbox"]["duplicate_replacements"] == 1
    assert report["openbox"]["continuation"] == {
        "enabled": True,
        "continuation_requested": True,
        "prior_evaluation_count": 2,
        "additional_evals": 2,
        "additional_evaluations_requested": 2,
        "target_total_evals": 4,
        "effective_target_evaluations": 4,
        "budget_source": "cli_continuation_delta",
    }
    assert len(rows) == 4
    assert rows[0]["evaluation_index"] == 1
    assert rows[2]["evaluation_index"] == 3
    assert rows[2]["run_id"] == "fake_003"
    assert rows[2]["batch_id"] == "batch_002"
    assert rows[2]["parameters"] == {
        "VAR_INT": "3",
        "VAR_WIDTH": "0.3u",
    }


def test_openbox_fake_continuation_stops_after_partial_unique_batch(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    advisor = ExhaustingContinuationAdvisor(project_dir)

    result = run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: advisor,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]

    assert result.evaluation_count == 3
    assert advisor.updated_batches == 2
    assert len(rows) == 3
    assert rows[-1]["run_id"] == "fake_003"
    continuation = report["openbox"]["continuation"]
    assert continuation["completed_early"] is True
    assert continuation["actual_additional_evals"] == 1
    assert continuation["unfilled_evals"] == 1
    assert "unique candidate" in continuation["completed_early_reason"]


def test_openbox_fake_continuation_caps_model_replay_observations(
    tmp_path: Path,
) -> None:
    # This exercise needs a variable grid large enough for 45 unique candidates
    # so that the model-replay cap (40) is exercised; the generic 2-variable
    # project's grid is too small, so it uses a custom project with the
    # optimizer max lifted.
    project_dir = create_approved_real_project_with_optimizer_max(
        tmp_path,
        max_evaluations=45,
    )
    run_openbox_fake_optimization(
        project_dir,
        max_evals=45,
        batch_size=5,
        advisor_factory=lambda _space, _seed: SequentialAdvisor(project_dir),
    )
    advisor = SequentialAdvisor(project_dir, start=45)

    result = run_openbox_fake_optimization(
        project_dir,
        additional_evals=1,
        batch_size=1,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: advisor,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())

    assert result.evaluation_count == 46
    assert len(advisor.updated_observations) == 41
    assert report["openbox"]["continuation"]["model_replay_evaluation_count"] == 40


def test_openbox_fake_run_writes_effectiveness_audit_and_report_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    import hermes_workflow.openbox_backend as _ob
    _values = default_metric_values(project_dir)

    def _generic(_parameters: dict[str, str]) -> object:
        return type("_FakeObs", (), {"metrics": dict(_values), "issues": []})()

    monkeypatch.setattr(_ob, "_fake_inverter_metrics", _generic)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        initial_trials=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    assert report["effectiveness_audit"] == "reports/optimizer_effectiveness_audit.json"

    audit = json.loads(
        (project_dir / report["effectiveness_audit"]).read_text(encoding="utf-8")
    )
    assert audit["schema_version"] == "1.0"
    assert audit["backend"] == "openbox"
    assert audit["requested_strategy"] == report["openbox"]["requested_strategy"]
    assert audit["resolved_strategy"] == report["openbox"]["resolved_strategy"]
    assert audit["model_replay_evaluation_count"] == 0
    assert [batch["phase"] for batch in audit["batches"]] == [
        "initialization",
        "bo",
    ]
    assert [
        (batch["history_size_before"], batch["history_size_after"])
        for batch in audit["batches"]
    ] == [(0, 2), (2, 4)]
    assert [batch["suggestion_count"] for batch in audit["batches"]] == [2, 2]
    assert [batch["evaluation_count"] for batch in audit["batches"]] == [2, 2]
    assert [batch["successful_observation_count"] for batch in audit["batches"]] == [
        2,
        2,
    ]
    assert [batch["penalty_observation_count"] for batch in audit["batches"]] == [
        0,
        0,
    ]
    assert [batch["feasible_count"] for batch in audit["batches"]] == [2, 4]
    assert [batch["replay_history_count"] for batch in audit["batches"]] == [0, 0]


def test_openbox_fake_continuation_writes_effectiveness_audit_with_replay_count(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    advisor = ContinuationAdvisor(project_dir)

    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: advisor,
    )

    audit = json.loads(
        (
            project_dir / "reports" / "optimizer_effectiveness_audit.json"
        ).read_text(encoding="utf-8")
    )

    assert audit["model_replay_evaluation_count"] == 2
    assert len(audit["batches"]) == 1
    assert audit["batches"][0]["history_size_before"] == 2
    assert audit["batches"][0]["history_size_after"] == 4
    assert audit["batches"][0]["replay_history_count"] == 2
    assert audit["batches"][0]["duplicate_replacements"] == 1


def _set_optimizer_yaml_openbox_strategy(
    project_dir: Path,
    *,
    strategy: str,
    nested_openbox: dict[str, object] | None = None,
) -> None:
    """Rewrite ``config/optimizer.yaml`` to select an OpenBox strategy preset.

    Used by continuation strategy pass-through tests so the resolver sees a
    requirement-driven strategy instead of the default TuRBO algorithm.
    """
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    payload["optimizer"]["algorithm"] = "openbox"
    payload["optimizer"]["strategy"] = strategy
    if nested_openbox:
        payload["optimizer"]["openbox"] = dict(nested_openbox)
    _write_yaml(optimizer_path, payload)


def test_openbox_fake_continuation_resolves_requirement_strategy_openbox_gp_eic(
    tmp_path: Path,
) -> None:
    """Continuation must resolve `optimizer.strategy: openbox_gp_eic` from
    requirement/config (gp / eic / random_scipy), not the old hardcoded
    PRF/EIC/local_random continuation defaults."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_yaml_openbox_strategy(project_dir, strategy="openbox_gp_eic")
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(project_dir),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"]["surrogate_type"] == "gp"
    assert report["openbox"]["resolved_strategy"]["acq_type"] == "eic"
    assert (
        report["openbox"]["resolved_strategy"]["acq_optimizer_type"] == "random_scipy"
    )
    assert (
        report["openbox"]["continuation"]["budget_source"]
        == "cli_continuation_delta"
    )


def test_openbox_fake_continuation_resolves_requirement_strategy_openbox_prf_eic(
    tmp_path: Path,
) -> None:
    """Continuation with `optimizer.strategy: openbox_prf_eic` resolves to
    prf / eic / local_random via the requirement-backed resolver, just like
    a fresh run."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_yaml_openbox_strategy(project_dir, strategy="openbox_prf_eic")
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(project_dir),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_prf_eic"
    assert report["openbox"]["resolved_strategy"]["surrogate_type"] == "prf"
    assert report["openbox"]["resolved_strategy"]["acq_type"] == "eic"
    assert (
        report["openbox"]["resolved_strategy"]["acq_optimizer_type"] == "local_random"
    )


def test_openbox_fake_continuation_preserves_nested_openbox_settings(
    tmp_path: Path,
) -> None:
    """Continuation preserves nested ``optimizer.openbox`` overrides from
    requirement/config; the CLI-side strategy detail args remain `None`."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_yaml_openbox_strategy(
        project_dir,
        strategy="openbox_gp_eic",
        nested_openbox={
            "surrogate_type": "prf",
            "acq_type": "eic",
            "acq_optimizer_type": "local_random",
            "initial_trials": 5,
        },
    )
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(project_dir),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    resolved = report["openbox"]["resolved_strategy"]
    assert resolved["surrogate_type"] == "prf"
    assert resolved["acq_type"] == "eic"
    assert resolved["acq_optimizer_type"] == "local_random"
    assert resolved["initial_trials"] == 5


def test_openbox_fake_runner_requires_openbox_when_no_advisor_is_injected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as module

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (_ for _ in ()).throw(RuntimeError("OpenBox is not installed")),
    )

    try:
        run_openbox_fake_optimization(
            create_approved_real_project(tmp_path),
            max_evals=1,
            batch_size=1,
        )
    except RuntimeError as exc:
        assert "OpenBox is not installed" in str(exc)
    else:
        raise AssertionError("expected missing OpenBox dependency error")


def test_openbox_fake_runner_requires_all_variables(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    int_name, width_name = variable_names(project_dir)

    class MissingWidthAdvisor:
        def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
            assert batch_size == 1
            return [{int_name: 2}]

        def update_observations(self, observations: list[object]) -> None:
            raise AssertionError("must fail before observation update")

    try:
        run_openbox_fake_optimization(
            project_dir,
            max_evals=1,
            batch_size=1,
            advisor_factory=lambda _space, _seed: MissingWidthAdvisor(),
        )
    except ValueError as exc:
        assert f"missing variable {width_name}" in str(exc)
    else:
        raise AssertionError(f"expected missing {width_name} to fail")


def test_run_openbox_real_optimization_uses_existing_real_candidate_path(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    adapter_calls: list[tuple[Path, str]] = []

    def adapter(project_dir: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        adapter_calls.append((project_dir, run_id))
        run_dir = project_dir / "runs" / "real" / run_id
        result_manifest = run_dir / "result_manifest.json"
        metric_manifest = run_dir / "metrics" / "metric_result_manifest.json"
        result_manifest.parent.mkdir(parents=True, exist_ok=True)
        metric_manifest.parent.mkdir(parents=True, exist_ok=True)
        from tests.real_run_smoke_helpers import (
            write_fake_metric_result_manifest,
            write_fake_result_manifest,
        )

        write_fake_result_manifest(project_dir, run_id=run_id)
        write_fake_metric_result_manifest(project_dir, run_id=run_id)

    result = run_openbox_real_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        parallel_jobs=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]
    first_candidate = json.loads(
        (project_dir / "runs" / "real" / "real_002" / "candidate.json")
        .read_text(encoding="utf-8")
    )

    assert result.evaluation_count == 2
    assert len(adapter_calls) == 2
    assert report["execution_mode"] == "real"
    assert report["openbox"]["parallel_jobs"] == 2
    assert rows[0]["parallel_jobs"] == 2
    assert rows[0]["threads_per_run"] == 2
    assert rows[0]["result_manifest"]
    assert rows[0]["metric_result_manifest"]
    assert first_candidate["requested_source"] == "openbox_optimizer"
    assert first_candidate["metadata"]["optimizer"] == "openbox"


def test_run_openbox_real_continuation_allows_completed_prior_state(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project_with_optimizer_max(
        tmp_path,
        max_evaluations=8,
    )

    def adapter(project_dir: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        from tests.real_run_smoke_helpers import (
            write_fake_metric_result_manifest,
            write_fake_result_manifest,
        )

        write_fake_result_manifest(project_dir, run_id=run_id)
        write_fake_metric_result_manifest(project_dir, run_id=run_id)

    run_openbox_real_optimization(
        project_dir,
        max_evals=8,
        batch_size=4,
        parallel_jobs=4,
        advisor_factory=lambda _space, _seed: SequentialAdvisor(project_dir),
        adapter=adapter,
    )
    state = json.loads(
        (project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "completed"
    advisor = SequentialAdvisor(project_dir, start=8)

    result = run_openbox_real_optimization(
        project_dir,
        additional_evals=1,
        continue_from_existing=True,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: advisor,
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]

    assert result.evaluation_count == 9
    assert report["openbox"]["continuation"]["prior_evaluation_count"] == 8
    assert rows[-1]["evaluation_index"] == 9
    assert rows[-1]["run_id"] == "real_010"


def test_run_openbox_real_optimization_applies_strategy_preset(
    tmp_path: Path,
) -> None:
    from tests.real_run_smoke_helpers import (
        write_fake_metric_result_manifest,
        write_fake_result_manifest,
    )

    project_dir = create_approved_real_project(tmp_path)

    def adapter(
        project_dir: Path,
        run_id: str,
        *,
        cadence_cshrc: Path | None = None,
    ) -> object:
        write_fake_result_manifest(project_dir, run_id=run_id)
        write_fake_metric_result_manifest(project_dir, run_id=run_id)
        return type("CompletedProcess", (), {"returncode": 0})()

    run_openbox_real_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        strategy="openbox_gp_eic",
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        "initial_trials": 4,
    }


def test_run_openbox_real_optimization_applies_config_strategy_preset(
    tmp_path: Path,
) -> None:
    from tests.real_run_smoke_helpers import (
        write_fake_metric_result_manifest,
        write_fake_result_manifest,
    )

    project_dir = _create_openbox_project(
        tmp_path,
        name="openbox_config_strategy_project",
        mutate_config=lambda pd: _set_optimizer_yaml_openbox_strategy(
            pd, strategy="openbox_gp_eic"
        ),
    )

    def adapter(
        project_dir: Path,
        run_id: str,
        timeout_seconds: int,
        cadence_cshrc: str | None = None,
    ) -> object:
        write_fake_result_manifest(project_dir, run_id=run_id)
        write_fake_metric_result_manifest(project_dir, run_id=run_id)
        return type("CompletedProcess", (), {"returncode": 0})()

    run_openbox_real_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        # initial_trials defaults to max(2 * num_variables, 1); the generic
        # project has two variables so this resolves to 4.
        "initial_trials": 4,
    }


def test_run_openbox_fake_optimization_prefers_explicit_overrides_over_strategy_preset(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        strategy="openbox_gp_eic",
        surrogate_type="prf",
        acq_optimizer_type="local_random",
        initial_trials=5,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "prf",
        "acq_type": "eic",
        "acq_optimizer_type": "local_random",
        "initial_trials": 5,
    }


def test_run_openbox_fake_optimization_applies_config_strategy_preset(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_yaml_openbox_strategy(project_dir, strategy="openbox_prf_eic")

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    audit = json.loads(
        (project_dir / "reports" / "optimizer_effectiveness_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["openbox"]["requested_strategy"] == "openbox_prf_eic"
    assert audit["requested_strategy"] == "openbox_prf_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "prf",
        "acq_type": "eic",
        "acq_optimizer_type": "local_random",
        "initial_trials": 4,
    }


def test_create_advisor_passes_initial_trials_into_openbox_advisor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    contract = module.load_native_turbo_contract(project_dir)
    captured: dict[str, object] = {}

    class CapturingAdvisor:
        def __init__(self, _space: object, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (CapturingAdvisor, object, object, object, FakeSpaceModule),
    )

    _create_advisor(
        project_dir,
        contract.variables,
        17,
        advisor_factory=None,
        num_constraints=len(contract.metrics.constraints),
        initial_trials=5,
        surrogate_type="gp",
        acq_type="eic",
        acq_optimizer_type="random_scipy",
    )

    assert captured["initial_trials"] == 5
    assert captured["surrogate_type"] == "gp"
    assert captured["acq_type"] == "eic"
    assert captured["acq_optimizer_type"] == "random_scipy"
    assert captured["random_state"] == 17


def test_run_openbox_real_cli_uses_dependency_gate(tmp_path: Path, monkeypatch) -> None:
    import hermes_workflow.cli as cli_module

    project_dir = create_approved_real_project(tmp_path)

    def fake_runner(
        project_dir: Path,
        *,
        max_evals: int | None,
        batch_size: int | None,
        parallel_jobs: int | None,
        cadence_cshrc: Path | None,
        strategy: str | None,
        surrogate_type: str | None,
        acq_type: str | None,
        acq_optimizer_type: str | None,
        initial_trials: int | None,
    ) -> object:
        assert max_evals is None
        assert batch_size is None
        assert parallel_jobs is None
        assert cadence_cshrc is None
        assert strategy == "openbox_gp_eic"
        assert surrogate_type == "prf"
        assert acq_type == "eic"
        assert acq_optimizer_type == "local_random"
        assert initial_trials == 5
        return type(
            "Result",
            (),
            {
                "evaluation_count": 3,
                "report_path": project_dir / REPORT_RELATIVE,
                "evaluations_path": project_dir / EVALUATIONS_RELATIVE,
            },
        )()

    monkeypatch.setattr(cli_module, "run_openbox_real_optimization", fake_runner)
    result = CliRunner().invoke(
        app,
            [
                "run-openbox-real",
                str(project_dir),
                "--strategy",
                "openbox_gp_eic",
            "--surrogate-type",
            "prf",
            "--acq-type",
            "eic",
            "--acq-optimizer-type",
            "local_random",
            "--initial-trials",
            "5",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "openbox real optimization completed: 3 evaluations" in result.output


@pytest.mark.parametrize("strategy", ["openbox_eic", "openbox-eic"])
def test_run_openbox_real_cli_rejects_openbox_eic_alias(
    tmp_path: Path,
    strategy: str,
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    result = CliRunner().invoke(
        app,
            [
                "run-openbox-real",
                str(project_dir),
                "--strategy",
                strategy,
            ],
    )

    assert result.exit_code == 1
    assert "eic is an acquisition function" in result.output
    assert "openbox_gp_eic" in result.output
    assert "openbox_prf_eic" in result.output


def test_continue_openbox_real_cli_uses_additional_evals(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.cli as cli_module

    project_dir = create_approved_real_project(tmp_path)

    def fake_runner(
        project_dir: Path,
        *,
        max_evals: int | None,
        additional_evals: int | None,
        continue_from_existing: bool,
        batch_size: int | None,
        parallel_jobs: int | None,
        cadence_cshrc: Path | None,
        strategy: str | None,
        surrogate_type: str | None,
        acq_type: str | None,
        acq_optimizer_type: str | None,
        initial_trials: int | None,
    ) -> object:
        assert max_evals is None
        assert additional_evals is None
        assert continue_from_existing is True
        assert batch_size is None
        assert parallel_jobs is None
        assert cadence_cshrc is None
        assert strategy == "openbox_gp_eic"
        assert surrogate_type == "prf"
        assert acq_type == "eic"
        assert acq_optimizer_type == "local_random"
        assert initial_trials == 6
        return type(
            "Result",
            (),
            {
                "evaluation_count": 7,
                "report_path": project_dir / REPORT_RELATIVE,
                "evaluations_path": project_dir / EVALUATIONS_RELATIVE,
            },
        )()

    monkeypatch.setattr(cli_module, "run_openbox_real_optimization", fake_runner)
    result = CliRunner().invoke(
        app,
            [
                "continue-openbox-real",
                str(project_dir),
                "--strategy",
                "openbox_gp_eic",
            "--surrogate-type",
            "prf",
            "--acq-type",
            "eic",
            "--acq-optimizer-type",
            "local_random",
            "--initial-trials",
            "6",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "openbox real continuation completed: 7 cumulative evaluations" in result.output


def test_continue_openbox_real_cli_uses_safe_defaults_and_repairs_package(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.cli as cli_module

    project_dir = create_approved_real_project(tmp_path)
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    manifest_path.unlink()
    build_calls: list[Path] = []

    def fake_build_execution_package(path: Path) -> object:
        build_calls.append(path)
        return object()

    def fake_runner(
        project_dir: Path,
        *,
        max_evals: int | None,
        additional_evals: int | None,
        continue_from_existing: bool,
        batch_size: int | None,
        parallel_jobs: int | None,
        cadence_cshrc: Path | None,
        strategy: str | None,
        surrogate_type: str | None,
        acq_type: str | None,
        acq_optimizer_type: str | None,
        initial_trials: int | None,
    ) -> object:
        assert max_evals is None
        assert additional_evals is None
        assert continue_from_existing is True
        assert strategy is None
        assert surrogate_type == "prf"
        assert acq_type == "eic"
        assert acq_optimizer_type == "local_random"
        assert initial_trials is None
        return type(
            "Result",
            (),
            {
                "evaluation_count": 108,
                "report_path": project_dir / REPORT_RELATIVE,
                "evaluations_path": project_dir / EVALUATIONS_RELATIVE,
            },
        )()

    monkeypatch.setattr(
        cli_module,
        "build_execution_package",
        fake_build_execution_package,
    )
    monkeypatch.setattr(cli_module, "run_openbox_real_optimization", fake_runner)
    result = CliRunner().invoke(
        app,
        [
            "continue-openbox-real",
            str(project_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert build_calls == [project_dir]
    assert "openbox real continuation completed: 108 cumulative evaluations" in result.output


def test_openbox_fake_random_baseline_reports_non_model_based_strategy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as openbox_module

    project_dir = create_approved_real_project(tmp_path)
    monkeypatch.setattr(
        openbox_module,
        "_load_openbox",
        lambda: (_ for _ in ()).throw(AssertionError("OpenBox should not load")),
    )

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        strategy="random_baseline",
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    audit = json.loads(
        (
            project_dir / "reports" / "optimizer_effectiveness_audit.json"
        ).read_text(encoding="utf-8")
    )

    assert report["openbox"]["requested_strategy"] == "random_baseline"
    assert report["openbox"]["resolved_strategy"]["model_based"] is False
    assert [batch["phase"] for batch in audit["batches"]] == ["random_baseline"]


def test_run_openbox_real_optimization_uses_multi_corner_aggregate_metrics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)

    def adapter(project: Path, *, run_id: str, **_kwargs: object) -> object:
        assert project == project_dir
        for corner_id, gain, iip3 in (
            ("tt", 10.0, 20.0),
            ("ff", 6.0, 4.0),
            ("ss", 12.0, 30.0),
        ):
            _write_corner_child_handoff(
                project_dir,
                run_id=run_id,
                testbench_id="cg_nf",
                corner_id=corner_id,
                metric_name="MAX_GAIN",
                value=gain,
            )
            _write_corner_child_handoff(
                project_dir,
                run_id=run_id,
                testbench_id="iip3",
                corner_id=corner_id,
                metric_name="IIP3",
                value=iip3,
            )
        aggregate_multi_testbench_run(project_dir, run_id=run_id)
        return SimpleNamespace(status="succeeded", issues=[])

    result = run_openbox_real_optimization(
        project_dir,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert result.evaluation_count == 1
    assert report["best_candidate"]["status"] == "feasible"
    assert report["best_candidate"]["metrics"] == {"MAX_GAIN": 6.0, "IIP3": 4.0}
    assert rows[0]["status"] == "feasible"
    assert rows[0]["metrics"] == {"MAX_GAIN": 6.0, "IIP3": 4.0}


class _CapturedMaxWorkers(Exception):
    """Sentinel raised by the monkeypatched evaluator factory to short-circuit
    `run_openbox_real_optimization` after the scheduler value is captured."""


def _set_config_parallelism(
    project_dir: Path,
    *,
    batch_size: int,
    parallel_jobs: int,
) -> None:
    """Update batch_size in optimizer.yaml and parallel_jobs in spectre.yaml.

    Sets the values via structured YAML so this works regardless of the project
    factory's default parallelism values. Also assert that the prepared/request
    `parallel_jobs` is absent from the spectre block of
    `runs/real/real_001/real_run_manifest.json` and
    `metric_extraction_request.json` so the test reaches the scheduler value via
    config (`bundle.spectre.spectre.parallel_jobs`), not via runtime metadata.
    """
    _set_optimizer_value(project_dir, "batch_size", batch_size)
    _set_spectre_value(project_dir, "parallel_jobs", parallel_jobs)

    # Tasks 1-2 already strip parallel_jobs from prepared/request spectre
    # contracts, but assert the runtime files do NOT contain it so this test
    # documents that the scheduler value flows from config-loaded SpectreSettings,
    # not from runtime spectre metadata.
    for run_dir in (project_dir / "runs" / "real").glob("real_*"):
        manifest_path = run_dir / "real_run_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert "parallel_jobs" not in manifest.get("spectre", {}), (
                "prepared spectre runtime contract must not carry parallel_jobs"
            )
        request_path = run_dir / "metric_extraction_request.json"
        if request_path.exists():
            request = json.loads(request_path.read_text(encoding="utf-8"))
            assert "parallel_jobs" not in request.get("spectre", {}), (
                "metric request spectre runtime contract must not carry parallel_jobs"
            )


def test_openbox_real_uses_requirement_parallel_jobs_for_candidate_workers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Lock contract: OpenBox real evaluator computes
    max_workers = min(parallel_jobs_from_config, optimizer.batch_size)
    where parallel_jobs comes from bundle.spectre.spectre.parallel_jobs
    (config-loaded SpectreSettings), not from prepared/request spectre metadata.
    """

    import hermes_workflow.openbox_backend as module

    # Schema rule (validate.py) requires optimizer.batch_size <= spectre.parallel_jobs,
    # so both cases satisfy that. The contract under test is that
    # max_workers == min(parallel_jobs, batch_size) and that the parallel_jobs
    # input arrives via bundle.spectre.spectre.parallel_jobs, not via
    # prepared/request spectre runtime metadata.
    cases = [
        # (batch_size, parallel_jobs, expected min)
        (3, 5, 3),
        (2, 4, 2),
    ]
    for batch_size, parallel_jobs, expected in cases:
        case_root = tmp_path / f"case_b{batch_size}_p{parallel_jobs}"
        case_root.mkdir()
        project_dir = create_approved_real_project(case_root)
        _set_config_parallelism(
            project_dir,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
        )

        captured: dict[str, int] = {}

        def fake_factory(
            project_dir,
            *,
            cadence_cshrc,
            max_workers,
            adapter=None,
            allow_optimizer_continuation=False,
        ):
            captured["max_workers"] = max_workers
            raise _CapturedMaxWorkers

        monkeypatch.setattr(
            module,
            "make_openbox_real_candidate_batch_evaluator",
            fake_factory,
        )

        with pytest.raises(_CapturedMaxWorkers):
            run_openbox_real_optimization(
                project_dir,
                max_evals=1,
                advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
            )

        assert captured["max_workers"] == expected, (
            f"expected min({parallel_jobs}, {batch_size}) == {expected}, "
            f"got {captured['max_workers']}"
        )


# ---------------------------------------------------------------------------
# B-06 Run retention contract integration (OpenBox batch evaluator)
# ---------------------------------------------------------------------------


def _set_keep_flags_for_retention(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    _set_spectre_value(project_dir, "keep_failed_runs", keep_failed_runs)
    _set_spectre_value(project_dir, "keep_successful_runs", keep_successful_runs)


def _create_approved_real_project_with_keep_flags(
    tmp_path: Path,
    *,
    keep_failed_runs: bool,
    keep_successful_runs: bool,
) -> Path:
    def _mutate(project_dir: Path) -> None:
        _set_keep_flags_for_retention(
            project_dir,
            keep_failed_runs=keep_failed_runs,
            keep_successful_runs=keep_successful_runs,
        )

    return _create_openbox_project(
        tmp_path,
        name="openbox_keep_flags_project",
        mutate_config=_mutate,
    )


def test_openbox_batch_evaluator_deletes_run_dir_when_keep_successful_runs_false(
    tmp_path: Path,
) -> None:
    import json as _json
    import shutil

    from hermes_workflow.native_turbo import NativeTurboBatchCandidate
    from hermes_workflow.openbox_backend import (
        make_openbox_real_candidate_batch_evaluator,
    )
    from tests.real_run_smoke_helpers import (
        write_fake_metric_result_manifest,
        write_fake_result_manifest,
    )

    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=True, keep_successful_runs=False
    )
    shutil.rmtree(project_dir / "runs")
    int_name, width_name = variable_names(project_dir)

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
        )

    candidate = NativeTurboBatchCandidate(
        evaluation_index=1,
        run_id="real_001",
        candidate_id="candidate_000001",
        batch_id="batch_001",
        batch_slot=0,
        batch_size=1,
        selection_phase="initialization",
        raw_x=[4.0, 0.5],
        parameters={int_name: "4", width_name: "0.5u"},
        replacement_issues=[],
    )

    evaluator = make_openbox_real_candidate_batch_evaluator(
        project_dir,
        cadence_cshrc=None,
        max_workers=1,
        adapter=adapter,
    )
    observations = evaluator([candidate])

    assert len(observations) == 1
    assert observations[0].status == "recorded"
    assert not (project_dir / "runs" / "real" / "real_001").exists()
    decision = _json.loads(
        (project_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["run_status"] == "successful"
    assert decision["local_action"] == "deleted"
    assert decision["candidate_id"] == "candidate_000001"


def test_openbox_batch_evaluator_keeps_run_dir_when_keep_successful_runs_true(
    tmp_path: Path,
) -> None:
    import json as _json
    import shutil

    from hermes_workflow.native_turbo import NativeTurboBatchCandidate
    from hermes_workflow.openbox_backend import (
        make_openbox_real_candidate_batch_evaluator,
    )
    from tests.real_run_smoke_helpers import (
        write_fake_metric_result_manifest,
        write_fake_result_manifest,
    )

    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=True, keep_successful_runs=True
    )
    shutil.rmtree(project_dir / "runs")
    int_name, width_name = variable_names(project_dir)

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
        )

    candidate = NativeTurboBatchCandidate(
        evaluation_index=1,
        run_id="real_001",
        candidate_id="candidate_000001",
        batch_id="batch_001",
        batch_slot=0,
        batch_size=1,
        selection_phase="initialization",
        raw_x=[4.0, 0.5],
        parameters={int_name: "4", width_name: "0.5u"},
        replacement_issues=[],
    )

    evaluator = make_openbox_real_candidate_batch_evaluator(
        project_dir,
        cadence_cshrc=None,
        max_workers=1,
        adapter=adapter,
    )
    observations = evaluator([candidate])

    assert observations[0].status == "recorded"
    assert (project_dir / "runs" / "real" / "real_001").is_dir()
    decision = _json.loads(
        (project_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["local_action"] == "kept"
    assert decision["run_status"] == "successful"


def _make_split_openbox_traces(project_dir: Path):
    from hermes_workflow.native_turbo import NativeTurboEvaluationTrace

    int_name, width_name = variable_names(project_dir)
    failing_metrics = _constraint_failing_metric_values_from_config(project_dir)

    traces: list[NativeTurboEvaluationTrace] = []
    for index in range(7):
        traces.append(
            NativeTurboEvaluationTrace(
                evaluation_index=index + 1,
                run_id=f"real_{index + 1:03d}",
                selection_phase="initialization",
                raw_x=[float(index), 0.5],
                parameters={int_name: str(index + 2), width_name: "0.5u"},
                status="constraint_failed",
                objective=1001.0,
                fom=1.0,
                constraint_penalty=1.0,
                metrics=failing_metrics,
                result_manifest=None,
                metric_result_manifest=None,
                issues=["constraint failed"],
                batch_id="batch_001",
                batch_slot=index + 1,
                batch_size=10,
                batch_worker_count=10,
                max_parallel_jobs=10,
                threads_per_run=10,
                parallel_jobs=10,
            )
        )
    for index in range(3):
        traces.append(
            NativeTurboEvaluationTrace(
                evaluation_index=8 + index,
                run_id=f"real_{8 + index:03d}",
                selection_phase="initialization",
                raw_x=[float(index + 7), 0.5],
                parameters={int_name: str(index + 9), width_name: "0.5u"},
                status="metric_check_failed",
                objective=1001.0,
                fom=None,
                constraint_penalty=0.0,
                metrics=None,
                result_manifest=None,
                metric_result_manifest=None,
                issues=["metric check failed"],
                batch_id="batch_001",
                batch_slot=index + 8,
                batch_size=10,
                batch_worker_count=10,
                max_parallel_jobs=10,
                threads_per_run=10,
                parallel_jobs=10,
            )
        )
    return traces


def _write_seven_ledger_rows_openbox(project_dir: Path) -> None:
    int_name, _width_name = variable_names(project_dir)
    failing_metrics = _constraint_failing_metric_values_from_config(project_dir)
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as handle:
        for index in range(7):
            handle.write(
                json.dumps(
                    {
                        "candidate_id": f"real_{index + 1:03d}",
                        "parameters": {int_name: "2"},
                        "metrics": {next(iter(failing_metrics)): 1.0},
                        "constraints_passed": False,
                        "objective": 1001.0,
                        "batch_id": 1,
                        "simulation_status": "real_pass",
                        "timestamp_utc": "2026-06-14T00:00:00Z",
                        "result_source": "real",
                        "run_id": f"real_{index + 1:03d}",
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def _set_optimizer_max_evals_openbox(project_dir: Path, value: int) -> None:
    _set_optimizer_value(project_dir, "max_evaluations", value)


def test_write_openbox_reports_syncs_optimizer_progress_state(tmp_path: Path) -> None:
    from hermes_workflow.native_turbo import NativeTurboRunResult
    from hermes_workflow.openbox_backend import (
        OpenBoxBatchRunSettings,
        write_openbox_reports,
    )

    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_max_evals_openbox(project_dir, 10)
    _write_seven_ledger_rows_openbox(project_dir)
    traces = _make_split_openbox_traces(project_dir)
    settings = OpenBoxBatchRunSettings(
        execution_mode="real",
        max_evals=10,
        batch_size=10,
        random_seed=20260528,
        parallel_jobs=10,
        threads_per_run=10,
        optimizer_cpu_threads=4,
        continuation_enabled=False,
        prior_evaluation_count=0,
        additional_evals=None,
        model_replay_evaluation_count=0,
        completed_early=False,
        completed_early_reason=None,
        requested_strategy="openbox_auto",
        resolved_strategy={},
    )
    write_openbox_reports(
        project_dir,
        NativeTurboRunResult(
            evaluation_count=10,
            traces=traces,
            best_trace=None,
        ),
        settings=settings,
        duplicate_replacements=0,
    )

    state_payload = json.loads(
        (project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8")
    )
    assert state_payload["current_evaluations"] == 10
    assert state_payload["recorded_observation_count"] == 7
    assert state_payload["failed_evaluation_count"] == 3
    assert state_payload["status_counts"] == {
        "constraint_failed": 7,
        "metric_check_failed": 3,
    }
    assert state_payload["status"] == "completed"
    assert state_payload["best_candidate_id"] is None
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_run_openbox_real_optimization_fails_without_history_when_continuing(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    # No reports/optimizer_evaluations.jsonl exists.
    with pytest.raises(ValueError, match=r"cannot continue without optimizer history"):
        run_openbox_real_optimization(
            project_dir,
            continue_from_existing=True,
            additional_evals=5,
            adapter=lambda *_a, **_kw: None,
        )


def test_run_openbox_fake_optimization_fails_without_history_when_continuing(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    with pytest.raises(ValueError, match=r"cannot continue without optimizer history"):
        run_openbox_fake_optimization(
            project_dir,
            continue_from_existing=True,
            additional_evals=5,
            batch_size=2,
        )


def test_openbox_fake_non_continuation_does_not_set_continuation_audit_fields(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    cont = report["openbox"]["continuation"]
    assert cont["enabled"] is False
    assert cont["continuation_requested"] is False
    assert "budget_source" not in cont


def test_openbox_continuation_does_not_modify_opt_requirement_md(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    # The generic project factory does not ship an opt_requirement.md, so seed a
    # minimal one to establish the precondition this test guards (the file must
    # exist and remain byte-identical across a continuation run).
    requirement_path = project_dir / "opt_requirement.md"
    requirement_path.write_text(
        "# opt requirement\n\nGeneric placeholder requirement.\n",
        encoding="utf-8",
    )
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    requirement_path = project_dir / "opt_requirement.md"
    assert requirement_path.is_file(), "test prerequisite: opt_requirement.md must exist"
    before = requirement_path.read_bytes()
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(project_dir),
    )
    after = requirement_path.read_bytes()
    assert before == after


def _set_optimizer_initialization(
    project_dir: Path,
    *,
    initialization: str,
    algorithm: str = "openbox",
) -> None:
    payload = {
        "schema_version": "1.0",
        "optimizer": {
            "algorithm": algorithm,
            "initialization": initialization,
            "max_evaluations": 4,
            "batch_size": 2,
            "random_seed": 20260528,
            "optimizer_cpu_threads": 4,
            "failure_penalty": 1000000.0,
            "deduplicate_candidates": True,
        },
    }
    _write_yaml(project_dir / "config" / "optimizer.yaml", payload)


@pytest.mark.parametrize(
    "initialization",
    ["sobol", "latin_hypercube", "random"],
)
def test_openbox_create_advisor_uses_requirement_initialization(
    tmp_path: Path, monkeypatch, initialization: str
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_initialization(project_dir, initialization=initialization)
    bundle = assert_valid_project(project_dir)

    captured: dict[str, object] = {}

    class _CapturingAdvisor:
        def __init__(self, space, **kwargs) -> None:
            captured.update(kwargs)

        def get_suggestions(self, batch_size):
            return []

        def update_observations(self, observations):
            return None

    class _Observation:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class _Space:
        def __init__(self) -> None:
            self.variables = []

        def add_variable(self, variable):
            self.variables.append(variable)

    fake_sp = SimpleNamespace(
        Space=_Space,
        Configuration=lambda *args, **kwargs: SimpleNamespace(
            values=kwargs.get("values")
        ),
        Real=lambda *args, **kwargs: SimpleNamespace(name=kwargs.get("name") or (args[0] if args else None)),
        Int=lambda *args, **kwargs: SimpleNamespace(name=kwargs.get("name") or (args[0] if args else None)),
    )

    monkeypatch.setattr(
        "hermes_workflow.openbox_backend._load_openbox",
        lambda: (_CapturingAdvisor, _Observation, object, object, fake_sp),
    )

    _create_advisor(
        project_dir,
        bundle.variables,
        seed=42,
        advisor_factory=None,
        num_constraints=0,
        initial_trials=4,
        surrogate_type="gp",
        acq_type="eic",
        acq_optimizer_type="random_scipy",
        initialization=initialization,
    )
    assert captured["init_strategy"] == initialization


def test_openbox_report_records_initialization(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_initialization(project_dir, initialization="latin_hypercube")
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["initialization"] == "latin_hypercube"
    assert report["openbox"]["effective_init_strategy"] == "latin_hypercube"
    audit = json.loads(
        (project_dir / OPENBOX_EFFECTIVENESS_AUDIT_RELATIVE).read_text(
            encoding="utf-8"
        )
    )
    assert audit["initialization"] == "latin_hypercube"
    assert audit["effective_init_strategy"] == "latin_hypercube"


# ---------------------------------------------------------------------------
# CPU thread limit runtime audit (B-11)
# ---------------------------------------------------------------------------


def test_openbox_fake_run_writes_runtime_thread_audit(tmp_path: Path) -> None:
    """OpenBox fake run must write optimizer_effectiveness_audit.json with
    runtime_thread_limits containing env vars and threadpoolctl state."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_value(project_dir, "optimizer_cpu_threads", 32)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    # The effectiveness audit must contain runtime_thread_limits
    audit = json.loads(
        (project_dir / OPENBOX_EFFECTIVENESS_AUDIT_RELATIVE).read_text(
            encoding="utf-8"
        )
    )
    assert "runtime_thread_limits" in audit, (
        f"runtime_thread_limits missing from effectiveness audit, "
        f"keys: {list(audit.keys())}"
    )
    rtl = audit["runtime_thread_limits"]
    assert rtl["source"] == "optimizer.optimizer_cpu_threads"
    assert rtl["requested_threads"] == 32
    assert rtl["backend"] == "openbox"
    assert rtl["execution_mode"] == "fake"
    assert rtl["process_scope"] == "local_optimizer_process"
    assert rtl["transport_mode"] == "local"
    # Env vars must show the requested thread count
    assert rtl["env_vars"]["OMP_NUM_THREADS"] == "32"
    assert rtl["env_vars"]["MKL_NUM_THREADS"] == "32"
    # threadpoolctl availability must be recorded (True or False, not absent)
    assert "available" in rtl["threadpoolctl"]
    assert "libraries" in rtl["threadpoolctl"]
    # torch availability must be recorded
    assert "available" in rtl["torch"]
    # issues list must exist
    assert isinstance(rtl["issues"], list)


def test_openbox_report_contains_runtime_thread_limits(tmp_path: Path) -> None:
    """OpenBox optimizer_run_report.json must contain runtime_thread_limits."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_value(project_dir, "optimizer_cpu_threads", 32)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert "runtime_thread_limits" in report, (
        f"runtime_thread_limits missing from report, keys: {list(report.keys())}"
    )
    rtl = report["runtime_thread_limits"]
    assert rtl["source"] == "optimizer.optimizer_cpu_threads"
    assert rtl["requested_threads"] == 32
    assert rtl["backend"] == "openbox"
    assert rtl["execution_mode"] == "fake"
    assert rtl["process_scope"] == "local_optimizer_process"
    assert rtl["transport_mode"] == "local"
    assert rtl["env_vars"]["OMP_NUM_THREADS"] == "32"


def test_openbox_separate_effectiveness_audit_file_has_runtime_thread_limits(
    tmp_path: Path,
) -> None:
    """A dedicated optimizer_effectiveness_audit.json file must exist and
    contain runtime_thread_limits."""
    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_value(project_dir, "optimizer_cpu_threads", 32)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
    )

    audit_path = project_dir / "reports" / "optimizer_effectiveness_audit.json"
    assert audit_path.exists(), "optimizer_effectiveness_audit.json must exist"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert "runtime_thread_limits" in audit


# ---------------------------------------------------------------------------
# Task 4: history warm-start OpenBox adapter
# ---------------------------------------------------------------------------


_MIXED_MODE_MESSAGE = (
    "history warm-start cannot be combined with continuation; "
    "use continuation for same-project budget extension, or start a new "
    "project for history warm-start"
)


def _write_warm_start_config(
    project_dir: Path, *, enabled: bool, sources: list[dict[str, object]]
) -> None:
    _write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": enabled,
                "sources": sources,
                "warm_start_strategy": "topk",
            },
        },
    )


def _fake_manifest_adapter() -> tuple[list[str], object]:
    runs: list[str] = []

    def adapter(project_dir: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        runs.append(run_id)
        from tests.real_run_smoke_helpers import (
            write_fake_metric_result_manifest,
            write_fake_result_manifest,
        )

        write_fake_result_manifest(project_dir, run_id=run_id)
        write_fake_metric_result_manifest(project_dir, run_id=run_id)

    return runs, adapter


def test_load_openbox_returns_five_tuple(monkeypatch) -> None:
    import hermes_workflow.openbox_backend as module

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: ("Advisor", "Observation", "History", "InitialConfigProvider", "sp"),
    )
    assert len(module._load_openbox()) == 5


def test_build_openbox_advisor_accepts_five_tuple_loader(
    tmp_path: Path, monkeypatch
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    contract = module.load_native_turbo_contract(project_dir)
    captured: dict[str, object] = {}

    class CapturingAdvisor:
        def __init__(self, _space: object, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (CapturingAdvisor, object, object, object, FakeSpaceModule),
    )

    _build_openbox_advisor(contract.variables, seed=19, num_constraints=1)

    assert captured["num_constraints"] == 1
    assert captured["random_state"] == 19


def test_create_advisor_passes_transfer_history_when_unconstrained(
    tmp_path: Path, monkeypatch
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    contract = module.load_native_turbo_contract(project_dir)
    captured: dict[str, object] = {}

    class CapturingAdvisor:
        def __init__(self, _space: object, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (CapturingAdvisor, object, object, object, FakeSpaceModule),
    )
    fake_history = object()

    _create_advisor(
        project_dir,
        contract.variables,
        11,
        advisor_factory=None,
        num_constraints=0,
        initial_trials=3,
        surrogate_type="gp",
        acq_type="eic",
        acq_optimizer_type="random_scipy",
        transfer_learning_history=[fake_history],
        warm_start_strategy="topk",
    )

    assert captured["num_constraints"] == 0
    assert captured["transfer_learning_history"] == [fake_history]
    assert captured["warm_start_strategy"] == "topk"


def test_create_advisor_passes_initial_configurations_without_transfer_history(
    tmp_path: Path, monkeypatch
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    contract = module.load_native_turbo_contract(project_dir)
    captured: dict[str, object] = {}

    class CapturingAdvisor:
        def __init__(self, _space: object, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (CapturingAdvisor, object, object, object, FakeSpaceModule),
    )
    fake_configuration = object()

    _create_advisor(
        project_dir,
        contract.variables,
        11,
        advisor_factory=None,
        num_constraints=1,
        initial_trials=3,
        surrogate_type="gp",
        acq_type="eic",
        acq_optimizer_type="random_scipy",
        transfer_learning_history=[],
        initial_configurations=[fake_configuration],
        warm_start_strategy="topk",
    )

    assert captured["num_constraints"] == 1
    assert "transfer_learning_history" not in captured
    assert "warm_start_strategy" not in captured
    assert captured["initial_configurations"] == [fake_configuration]


def test_run_openbox_real_rejects_warm_start_combined_with_continuation(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, name="current_project")
    _write_warm_start_config(
        project_dir,
        enabled=True,
        sources=[{"path": str(tmp_path / "previous_project"), "label": "round1"}],
    )

    with pytest.raises(ValueError, match=_MIXED_MODE_MESSAGE):
        run_openbox_real_optimization(project_dir, continue_from_existing=True)


def test_run_openbox_real_warm_start_runs_audit_without_real_openbox(
    tmp_path: Path, monkeypatch
) -> None:
    import hermes_workflow.openbox_backend as module

    # advisor_factory path must not load real OpenBox at all.
    monkeypatch.setattr(
        module,
        "_load_openbox",
        lambda: (_ for _ in ()).throw(AssertionError("real OpenBox must not load")),
    )
    project_dir = create_approved_real_project(tmp_path)
    _write_warm_start_config(
        project_dir,
        enabled=True,
        sources=[{"path": str(tmp_path / "missing_source"), "label": "round1"}],
    )
    _runs, adapter = _fake_manifest_adapter()

    result = run_openbox_real_optimization(
        project_dir,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )

    assert result.evaluation_count == 1
    assert (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).exists()


def test_run_openbox_real_no_config_and_disabled_warm_start_preserve_behavior(
    tmp_path: Path,
) -> None:
    _runs, adapter = _fake_manifest_adapter()

    # No warm-start config: existing behavior, no warm-start audit artifact.
    project_dir = create_approved_real_project(tmp_path)
    result = run_openbox_real_optimization(
        project_dir,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )
    assert result.evaluation_count == 1
    assert not (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).exists()

    # enabled: false: same as no-config (no warm-start audit artifact).
    disabled_dir = create_approved_real_project(tmp_path / "disabled_case")
    _write_warm_start_config(
        disabled_dir,
        enabled=False,
        sources=[{"path": str(tmp_path / "previous_project"), "label": "round1"}],
    )
    disabled_result = run_openbox_real_optimization(
        disabled_dir,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _space, _seed: FakeAdvisor(disabled_dir),
        adapter=adapter,
    )
    assert disabled_result.evaluation_count == 1
    assert not (disabled_dir / HISTORY_WARM_START_AUDIT_RELATIVE).exists()


# ---------------------------------------------------------------------------
# Task 5: history warm-start report payload integration
# ---------------------------------------------------------------------------


def _history_evaluations_row(project_dir: Path) -> str:
    """A single accepted JSONL row valid for an approved real project's contract.

    Parameters are each variable's lower bound (always in range and on grid);
    metrics are the project's passing values; old status is feasible.
    """
    variables = _read_yaml(project_dir / "config" / "variables.yaml")["variables"]
    parameters = {variable["name"]: variable["lower"] for variable in variables}
    return json.dumps(
        {
            "parameters": parameters,
            "metrics": _passing_metric_values_from_config(project_dir),
            "status": "feasible",
            "evaluation_index": 1,
            "run_id": "real_001",
        }
    )


def _write_history_evaluations(project_dir: Path, rows: list[str]) -> None:
    path = project_dir / EVALUATIONS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in rows), encoding="utf-8")


def _run_real_with_warm_start(
    project_dir: Path, *, advisor_factory: object | None = None
) -> dict:
    _runs, adapter = _fake_manifest_adapter()
    run_openbox_real_optimization(
        project_dir,
        max_evals=1,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=advisor_factory
        if advisor_factory is not None
        else (lambda _space, _seed: FakeAdvisor(project_dir)),
        adapter=adapter,
    )
    return json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))


def test_optimizer_report_includes_history_warm_start_when_enabled(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    source_dir = create_approved_real_project(tmp_path / "source")
    _write_history_evaluations(source_dir, [_history_evaluations_row(source_dir)])
    _write_warm_start_config(
        project_dir,
        enabled=True,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    payload = _run_real_with_warm_start(project_dir)

    history_payload = payload["openbox"]["history_warm_start"]
    assert history_payload["enabled"] is True
    assert history_payload["audit"] == "reports/history_warm_start_audit.json"
    assert history_payload["audit_markdown"] == "reports/history_warm_start_audit.md"
    assert history_payload["accepted_observation_count"] >= 1
    assert history_payload["application_mode"] in {
        "transfer_learning_history",
        "initial_configurations_from_history",
    }


def test_optimizer_report_omits_history_warm_start_when_no_config(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    payload = _run_real_with_warm_start(project_dir)

    assert "history_warm_start" not in payload["openbox"]


def test_optimizer_report_omits_history_warm_start_when_disabled(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _write_warm_start_config(
        project_dir,
        enabled=False,
        sources=[{"path": str(tmp_path / "previous_project"), "label": "round1"}],
    )

    payload = _run_real_with_warm_start(project_dir)

    assert "history_warm_start" not in payload["openbox"]


def test_optimizer_report_history_warm_start_zero_accepted(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    # Valid project source with no optimizer evaluations file -> source rejected
    # as missing_optimizer_evaluations -> zero accepted observations.
    source_dir = create_generic_project(tmp_path, name="warm_start_source")
    _write_warm_start_config(
        project_dir,
        enabled=True,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    payload = _run_real_with_warm_start(project_dir)

    history_payload = payload["openbox"]["history_warm_start"]
    assert history_payload["application_mode"] == "no_accepted_observations"
    assert history_payload["applied_to_advisor"] is False
    assert history_payload["accepted_observation_count"] == 0


def test_partial_and_final_report_share_history_warm_start_payload(
    tmp_path: Path, monkeypatch
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    source_dir = create_approved_real_project(tmp_path / "source")
    _write_history_evaluations(source_dir, [_history_evaluations_row(source_dir)])
    _write_warm_start_config(
        project_dir,
        enabled=True,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    captured: list[object] = []
    real_write = module.write_openbox_reports

    def recording_write(*args, **kwargs) -> object:
        captured.append(kwargs["settings"].history_warm_start)
        return real_write(*args, **kwargs)

    monkeypatch.setattr(module, "write_openbox_reports", recording_write)
    _runs, adapter = _fake_manifest_adapter()
    run_openbox_real_optimization(
        project_dir,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        advisor_factory=lambda _surface, _seed: FakeAdvisor(project_dir),
        adapter=adapter,
    )

    # At least one partial report and the final report.
    assert len(captured) >= 2
    assert all(item is not None for item in captured)
    assert all(item == captured[0] for item in captured)


def test_history_warm_start_report_payload_not_applied_mode(tmp_path: Path) -> None:
    """The report helper must project the not_applied adapter state faithfully
    (this branch is otherwise only exercised at the audit level)."""
    import hermes_workflow.openbox_backend as module
    from hermes_workflow.history_warm_start import (
        WarmStartAdapterResult,
        audit_history_warm_start,
    )

    project_dir = create_generic_project(tmp_path, name="audit_source")
    bundle = assert_valid_project(project_dir)
    base_audit = audit_history_warm_start(project_dir, bundle, write_reports=False)
    adapter = WarmStartAdapterResult(
        audit=base_audit,
        transfer_learning_history=[],
        initial_configurations=[],
        accepted_observation_count=2,
        applied_observation_count=0,
        application_mode="not_applied",
        not_applied_reason="history_object_rejected_by_openbox",
        warm_start_strategy="topk",
    )

    payload = module._history_warm_start_report_payload(adapter)

    assert payload is not None
    assert payload["application_mode"] == "not_applied"
    assert payload["applied_to_advisor"] is False
    assert payload["not_applied_reason"] == "history_object_rejected_by_openbox"
    assert payload["accepted_observation_count"] == 2
    assert payload["applied_observation_count"] == 0
    assert payload["enabled"] is True
