from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import math

import pytest
from typer.testing import CliRunner

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.cli import app
from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run
from hermes_workflow.openbox_backend import (
    OPENBOX_ADVANCED_VISUALIZATION_MANIFEST_RELATIVE,
    OPENBOX_EFFECTIVENESS_AUDIT_RELATIVE,
    _build_openbox_space,
    _create_advisor,
    run_openbox_fake_optimization,
    run_openbox_real_optimization,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.validate import assert_valid_project
from tests.real_run_smoke_helpers import (
    TEMPLATE_TEXT,
    create_approved_real_project,
)
from tests.report_helpers import write_pass_reports
from tests.test_multi_testbench_aggregation import (
    _create_ready_multi_corner_multi_testbench_project,
    _write_corner_child_handoff,
)


class FakeAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self._batches = [
            [
                {"F": 22, "W": 0.8, "L": 40, "VB_LO": 300},
                {"F": 24, "W": 1.0, "L": 30, "VB_LO": 340},
            ],
            [
                {"F": 26, "W": 1.2, "L": 40, "VB_LO": 360},
                {"F": 28, "W": 0.6, "L": 30, "VB_LO": 380},
            ],
        ]

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


def _metrics_config(payload: dict):
    from hermes_workflow.schemas import MetricsConfig

    return MetricsConfig.model_validate(payload)


def test_fake_metric_observation_is_metric_generic_and_constraint_aware() -> None:
    """The fake evaluator must not hardcode one circuit's metrics: it must
    emit a deterministic value for every declared metric and satisfy any
    declared constraint by default."""
    from hermes_workflow.openbox_backend import _fake_metric_observation

    metrics_config = _metrics_config(
        {
            "schema_version": "1.0",
            "metrics": [
                {"name": "gain_db", "unit": "dB", "maestro_formula": "gain"},
                {"name": "power_mw", "unit": "mW", "maestro_formula": "pwr"},
                {"name": "phase_margin", "unit": "deg", "maestro_formula": "pm"},
            ],
            "constraints": [
                {"metric": "gain_db", "op": "ge", "value": "10"},
                {"metric": "power_mw", "op": "le", "value": "5"},
            ],
            "objective": {"direction": "maximize", "expression": "gain_db"},
        }
    )

    observation = _fake_metric_observation({"x": "1", "y": "2"}, metrics_config)
    metrics = observation.metrics

    assert set(metrics) == {"gain_db", "power_mw", "phase_margin"}
    assert metrics["gain_db"] >= 10.0
    assert metrics["power_mw"] <= 5.0
    assert all(math.isfinite(value) for value in metrics.values())
    # Deterministic: same parameters -> identical values.
    assert (
        _fake_metric_observation({"x": "1", "y": "2"}, metrics_config).metrics
        == metrics
    )


def test_fake_metric_observation_supports_release_template_metric() -> None:
    """The metric-generic evaluator still serves the release template metric."""
    from hermes_workflow.openbox_backend import _fake_metric_observation

    metrics_config = _metrics_config(
        {
            "schema_version": "1.0",
            "metrics": [{"name": "NF_3G", "unit": "dB", "maestro_formula": "nf"}],
            "constraints": [{"metric": "NF_3G", "op": "lt", "value": "9 dB"}],
            "objective": {"direction": "minimize", "expression": "NF_3G"},
        }
    )

    metrics = _fake_metric_observation(
        {"F": "20", "W": "0.6u"}, metrics_config
    ).metrics

    assert set(metrics) == {"NF_3G"}
    assert metrics["NF_3G"] < 9.0


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
    def __init__(self, *, fail: bool = False, partial: bool = False) -> None:
        super().__init__()
        self.history = FakeOpenBoxHistory(fail=fail, partial=partial)

    def get_history(self) -> FakeOpenBoxHistory:
        return self.history


class ContinuationAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self.seen_prior_before_suggest = False
        self._batches = [
            [
                {"F": 22, "W": 0.8, "L": 40, "VB_LO": 300},
                {"F": 30, "W": 1.2, "L": 40, "VB_LO": 400},
            ],
            [
                {"F": 28, "W": 0.6, "L": 30, "VB_LO": 380},
            ],
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
    def __init__(self) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self.calls = 0

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        self.calls += 1
        if self.calls == 1:
            return [
                {"F": 30, "W": 1.2, "L": 40, "VB_LO": 400},
                {"F": 22, "W": 0.8, "L": 40, "VB_LO": 300},
            ][:batch_size]
        return [{"F": 22, "W": 0.8, "L": 40, "VB_LO": 300}][:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        self.updated_observations.extend(observations)
        assert observations


class SequentialAdvisor:
    def __init__(self, *, start: int = 0) -> None:
        self.index = start
        self.updated_observations: list[object] = []

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        suggestions: list[dict[str, float]] = []
        for _slot in range(batch_size):
            value = self.index
            self.index += 1
            suggestions.append(
                {
                    "F": 20 + 2 * (value % 6),
                    "W": 0.6 + 0.2 * (value % 4),
                    "L": 30 + 10 * (value % 2),
                    "VB_LO": 280 + 20 * (value % 7),
                }
            )
        return suggestions

    def update_observations(self, observations: list[object]) -> None:
        self.updated_observations.extend(observations)
        assert observations


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


def create_approved_real_project_with_optimizer_max(
    tmp_path: Path,
    max_evaluations: int,
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_text = optimizer_path.read_text(encoding="utf-8").replace(
        "max_evaluations: 30",
        f"max_evaluations: {max_evaluations}",
    )
    optimizer_path.write_text(optimizer_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


def test_openbox_space_uses_effective_grid_upper(tmp_path: Path) -> None:
    bundle = assert_valid_project(create_approved_real_project(tmp_path))

    space = _build_openbox_space(bundle.variables, FakeSpaceModule)
    by_name = {variable.name: variable for variable in space.variables}

    assert by_name["W"].upper == 1.2
    assert by_name["L"].upper == 40.0
    assert by_name["VB_LO"].upper == 400.0
    assert by_name["F"].upper == 30
    assert list(by_name) == ["F", "W", "L", "VB_LO"]


def test_openbox_fake_runner_writes_backend_neutral_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    result = run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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
    assert rows[0]["parameters"]["W"].endswith("u")
    assert rows[0]["parameters"]["VB_LO"].endswith("m")
    assert rows[0]["result_manifest"] is None
    assert rows[0]["metric_result_manifest"] is None
    assert rows[0]["batch_id"] == "batch_001"


def test_openbox_fake_runner_applies_optimizer_cpu_thread_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as module

    project_dir = create_approved_real_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "optimizer_cpu_threads: 32",
            "optimizer_cpu_threads: 3",
        ),
        encoding="utf-8",
    )
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )

    assert calls
    assert all(call[0] == 3 for call in calls)
    assert any(call[1].get("set_environment") is True for call in calls)


def test_openbox_runner_writes_advanced_visualization_artifact(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    advisor = VisualizingAdvisor()

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
    advisor = VisualizingAdvisor(fail=True)

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
    advisor = VisualizingAdvisor(partial=True)

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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    advisor = ContinuationAdvisor()

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
        "F": "30",
        "W": "1.2u",
        "L": "40n",
        "VB_LO": "400m",
    }


def test_openbox_fake_continuation_stops_after_partial_unique_batch(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    advisor = ExhaustingContinuationAdvisor()

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
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=45,
        batch_size=5,
        advisor_factory=lambda _space, _seed: SequentialAdvisor(),
    )
    advisor = SequentialAdvisor(start=45)

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
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        initial_trials=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    advisor = ContinuationAdvisor()

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
    text = optimizer_path.read_text(encoding="utf-8")
    if "  strategy:" in text:
        lines = [
            f"  strategy: {strategy}" if line.startswith("  strategy:") else line
            for line in text.splitlines()
        ]
        text = "\n".join(lines) + "\n"
    else:
        text = text.replace("  algorithm: openbox", f"  algorithm: openbox\n  strategy: {strategy}", 1)
    if nested_openbox:
        nested_lines = ["  openbox:"]
        for key, value in nested_openbox.items():
            nested_lines.append(f"    {key}: {value}")
        text = text.rstrip() + "\n" + "\n".join(nested_lines) + "\n"
    optimizer_path.write_text(text, encoding="utf-8")


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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(),
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(),
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(),
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
    class MissingLAdvisor:
        def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
            assert batch_size == 1
            return [{"F": 20, "W": 0.6, "VB_LO": 280}]

        def update_observations(self, observations: list[object]) -> None:
            raise AssertionError("must fail before observation update")

    try:
        run_openbox_fake_optimization(
            create_approved_real_project(tmp_path),
            max_evals=1,
            batch_size=1,
            advisor_factory=lambda _space, _seed: MissingLAdvisor(),
        )
    except ValueError as exc:
        assert "missing variable L" in str(exc)
    else:
        raise AssertionError("expected missing L to fail")


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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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
    assert rows[0]["threads_per_run"] == 10
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
        advisor_factory=lambda _space, _seed: SequentialAdvisor(start=1),
        adapter=adapter,
    )
    state = json.loads(
        (project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "completed"
    advisor = SequentialAdvisor(start=9)

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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
        strategy="openbox_gp_eic",
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        "initial_trials": 8,
    }


def test_run_openbox_real_optimization_applies_config_strategy_preset(
    tmp_path: Path,
) -> None:
    from tests.real_run_smoke_helpers import (
        write_fake_metric_result_manifest,
        write_fake_result_manifest,
    )

    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_text = optimizer_path.read_text(encoding="utf-8").replace(
        "  strategy: openbox_prf_eic",
        "  strategy: openbox_gp_eic",
        1,
    )
    optimizer_path.write_text(optimizer_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")

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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
        adapter=adapter,
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
    assert report["openbox"]["resolved_strategy"] == {
        "surrogate_type": "gp",
        "acq_type": "eic",
        "acq_optimizer_type": "random_scipy",
        "initial_trials": 8,
    }


def test_run_openbox_fake_optimization_prefers_explicit_overrides_over_strategy_preset(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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
        "initial_trials": 8,
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
        lambda: (CapturingAdvisor, object, FakeSpaceModule),
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

    class MultiTestbenchAdvisor:
        def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
            assert batch_size == 1
            return [{"FN": 4, "WN": 0.5, "FP": 4, "WP": 1.1}]

        def update_observations(self, observations: list[object]) -> None:
            assert observations

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
        advisor_factory=lambda _space, _seed: MultiTestbenchAdvisor(),
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

    Templates ship with batch_size=10 and parallel_jobs=10, so we replace those
    exact lines. Also strip any prepared/request `parallel_jobs` from the spectre
    block of `runs/real/real_001/real_run_manifest.json` and
    `metric_extraction_request.json` so the test reaches the scheduler value via
    config (`bundle.spectre.spectre.parallel_jobs`), not via runtime metadata.
    """

    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_text = optimizer_path.read_text(encoding="utf-8").replace(
        "batch_size: 10",
        f"batch_size: {batch_size}",
    )
    optimizer_path.write_text(optimizer_text, encoding="utf-8")

    spectre_path = project_dir / "config" / "spectre.yaml"
    spectre_text = spectre_path.read_text(encoding="utf-8").replace(
        "parallel_jobs: 10",
        f"parallel_jobs: {parallel_jobs}",
    )
    spectre_path.write_text(spectre_text, encoding="utf-8")

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
                advisor_factory=lambda _space, _seed: FakeAdvisor(),
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
    spectre_path = project_dir / "config" / "spectre.yaml"
    text = spectre_path.read_text(encoding="utf-8")
    text = text.replace(
        "keep_failed_runs: true",
        f"keep_failed_runs: {str(keep_failed_runs).lower()}",
    )
    text = text.replace(
        "keep_successful_runs: true",
        f"keep_successful_runs: {str(keep_successful_runs).lower()}",
    )
    spectre_path.write_text(text, encoding="utf-8")


def _create_approved_real_project_with_keep_flags(
    tmp_path: Path,
    *,
    keep_failed_runs: bool,
    keep_successful_runs: bool,
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _set_keep_flags_for_retention(
        project_dir,
        keep_failed_runs=keep_failed_runs,
        keep_successful_runs=keep_successful_runs,
    )
    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


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

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"NF_3G": 6.0},
        )

    candidate = NativeTurboBatchCandidate(
        evaluation_index=1,
        run_id="real_001",
        candidate_id="candidate_000001",
        batch_id="batch_001",
        batch_slot=0,
        batch_size=1,
        selection_phase="initialization",
        raw_x=[24.0, 0.8, 40.0, 320.0],
        parameters={"F": "24", "W": "0.8u", "L": "40n", "VB_LO": "320m"},
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

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"NF_3G": 6.0},
        )

    candidate = NativeTurboBatchCandidate(
        evaluation_index=1,
        run_id="real_001",
        candidate_id="candidate_000001",
        batch_id="batch_001",
        batch_slot=0,
        batch_size=1,
        selection_phase="initialization",
        raw_x=[24.0, 0.8, 40.0, 320.0],
        parameters={"F": "24", "W": "0.8u", "L": "40n", "VB_LO": "320m"},
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


def _make_split_openbox_traces():
    from hermes_workflow.native_turbo import NativeTurboEvaluationTrace

    traces: list[NativeTurboEvaluationTrace] = []
    for index in range(7):
        traces.append(
            NativeTurboEvaluationTrace(
                evaluation_index=index + 1,
                run_id=f"real_{index + 1:03d}",
                selection_phase="initialization",
                raw_x=[float(index), 0.5],
                parameters={"FN": str(index + 2), "WN": "0.5u"},
                status="constraint_failed",
                objective=1001.0,
                fom=1.0,
                constraint_penalty=1.0,
                metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
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
                parameters={"FN": str(index + 9), "WN": "0.5u"},
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
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as handle:
        for index in range(7):
            handle.write(
                json.dumps(
                    {
                        "candidate_id": f"real_{index + 1:03d}",
                        "parameters": {"FN": "2"},
                        "metrics": {"rise": 1.0e-12},
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
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    text = optimizer_path.read_text(encoding="utf-8")
    text = text.replace("max_evaluations: 30", f"max_evaluations: {value}")
    optimizer_path.write_text(text, encoding="utf-8")


def test_write_openbox_reports_syncs_optimizer_progress_state(tmp_path: Path) -> None:
    from hermes_workflow.native_turbo import NativeTurboRunResult
    from hermes_workflow.openbox_backend import (
        OpenBoxBatchRunSettings,
        write_openbox_reports,
    )

    project_dir = create_approved_real_project(tmp_path)
    _set_optimizer_max_evals_openbox(project_dir, 10)
    _write_seven_ledger_rows_openbox(project_dir)
    traces = _make_split_openbox_traces()
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    cont = report["openbox"]["continuation"]
    assert cont["enabled"] is False
    assert cont["continuation_requested"] is False
    assert "budget_source" not in cont


def test_openbox_continuation_does_not_modify_opt_requirement_md(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )
    requirement_path = project_dir / "opt_requirement.md"
    assert requirement_path.is_file(), "test prerequisite: opt_requirement.md must exist"
    before = requirement_path.read_bytes()
    run_openbox_fake_optimization(
        project_dir,
        additional_evals=2,
        batch_size=2,
        continue_from_existing=True,
        advisor_factory=lambda _space, _seed: ContinuationAdvisor(),
    )
    after = requirement_path.read_bytes()
    assert before == after


def _set_optimizer_initialization(
    project_dir: Path,
    *,
    initialization: str,
    algorithm: str = "openbox",
) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    body = [
        'schema_version: "1.0"',
        '',
        'optimizer:',
        f'  algorithm: {algorithm}',
        f'  initialization: {initialization}',
        '  max_evaluations: 4',
        '  batch_size: 2',
        '  random_seed: 20260528',
        '  optimizer_cpu_threads: 4',
        '  failure_penalty: 1000000.0',
        '  deduplicate_candidates: true',
    ]
    optimizer_path.write_text("\n".join(body) + "\n", encoding="utf-8")


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
        lambda: (_CapturingAdvisor, _Observation, fake_sp),
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
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
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

    run_openbox_fake_optimization(
        project_dir,
        max_evals=2,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )

    audit_path = project_dir / "reports" / "optimizer_effectiveness_audit.json"
    assert audit_path.exists(), "optimizer_effectiveness_audit.json must exist"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert "runtime_thread_limits" in audit
