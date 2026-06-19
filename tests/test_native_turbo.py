from __future__ import annotations

import json
import math
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.cli import app
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.native_turbo import (
    NativeTurboObservation,
    NativeTurboBatchCandidate,
    NativeTurboBatchRunner,
    NativeTurboEvaluationTrace,
    NativeTurboRunner,
    NativeTurboRunResult,
    _default_batch_turbo_factory,
    _run_default_adapter,
    evaluate_candidate_objective,
    evaluate_real_candidate,
    load_native_turbo_contract,
    make_real_candidate_batch_evaluator,
    quantize_candidate,
    run_batch_native_turbo_optimization,
    run_native_turbo_optimization,
    write_native_turbo_reports,
)
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
from hermes_workflow.requirement_intake import prepare_from_requirement
from hermes_workflow.schemas import (
    ConstraintOp,
    ConstraintSpec,
    MetricSpec,
    MetricsConfig,
    ObjectiveDirection,
    ObjectiveSpec,
    OptimizerAlgorithm,
    OptimizerConfig,
    OptimizerSettings,
    InitializationMethod,
    VariableKind,
    VariableSpec,
    VariablesConfig,
)
from tests.report_helpers import write_pass_reports
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    load_json,
    write_fake_metric_result_manifest,
    write_fake_result_manifest,
)
from tests.test_requirement_intake import _copy_multi_testbench_requirement_project


def _inject_three_corner_section(project_dir: Path) -> None:
    requirement_path = project_dir / "opt_requirement.md"
    text = requirement_path.read_text(encoding="utf-8")
    corners_section = """
## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: "0"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
```
"""
    requirement_path.write_text(
        text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist"),
        encoding="utf-8",
    )


def _create_ready_multi_corner_multi_testbench_project(tmp_path: Path) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    _inject_three_corner_section(project_dir)
    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"
    build_execution_package(project_dir, created_at_utc="2026-06-12T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-12T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    return project_dir


def _write_process_corners_config(
    project_dir: Path,
    corner_ids: list[str],
    *,
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> None:
    lines = [
        'schema_version: "1.0"',
        f"objective_policy: {objective_policy}",
        f"constraint_policy: {constraint_policy}",
        "corners:",
    ]
    for corner_id in corner_ids:
        lines.extend(
            [
                f"  - id: {corner_id}",
                f"    description: {corner_id} corner",
            ]
        )
    (project_dir / "config" / "process_corners.yaml").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _create_ready_multi_corner_single_testbench_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\n"
        "parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )
    template_text = template_path.read_text(encoding="utf-8")
    for corner_id in corner_ids:
        corner_template = (
            project_dir / "netlists" / "corners" / corner_id / "template.scs"
        )
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    return project_dir


class _FakeTurbo:
    instances: list["_FakeTurbo"] = []

    def __init__(
        self,
        *,
        f,
        lb,
        ub,
        n_init,
        max_evals,
        batch_size,
        verbose,
    ) -> None:
        self.f = f
        self.lb = lb
        self.ub = ub
        self.n_init = n_init
        self.max_evals = max_evals
        self.batch_size = batch_size
        self.verbose = verbose
        self.optimize_called = False
        self.X: list[list[float]] = []
        self.fX: list[list[float]] = []
        _FakeTurbo.instances.append(self)

    def optimize(self) -> None:
        self.optimize_called = True
        base_points = [
            [2.0, 0.3, 2.0, 0.3],
            [3.0, 0.4, 3.0, 0.4],
            [4.0, 0.5, 4.0, 0.5],
            [5.0, 0.6, 5.0, 0.6],
            [6.0, 0.7, 6.0, 0.7],
        ]
        raw_points = [point[: len(self.lb)] for point in base_points[: self.max_evals]]
        for raw in raw_points:
            self.X.append(raw)
            self.fX.append([self.f(raw)])


class _DuplicateFakeTurbo(_FakeTurbo):
    def optimize(self) -> None:
        self.optimize_called = True
        for raw in [[2.0, 0.3], [2.0, 0.3]]:
            self.X.append(raw)
            self.fX.append([self.f(raw)])


class _FakeBatchTurbo:
    instances: list["_FakeBatchTurbo"] = []

    def __init__(
        self,
        *,
        f_batch,
        lb,
        ub,
        n_init,
        max_evals,
        batch_size,
        verbose,
        initialization=None,
        random_seed=None,
    ) -> None:
        self.f_batch = f_batch
        self.lb = lb
        self.ub = ub
        self.n_init = n_init
        self.max_evals = max_evals
        self.batch_size = batch_size
        self.verbose = verbose
        self.initialization = initialization
        self.random_seed = random_seed
        self.optimize_called = False
        _FakeBatchTurbo.instances.append(self)

    def optimize(self) -> None:
        self.optimize_called = True
        base_batches = [
            [
                [2.0, 0.3, 2.0, 0.3],
                [2.1, 0.31, 2.1, 0.31],
                [2.0, 0.3, 2.0, 0.3],
            ],
            [
                [4.0, 0.7, 4.0, 0.7],
                [5.0, 0.8, 5.0, 0.8],
            ],
        ]
        self.f_batch(
            [point[: len(self.lb)] for point in base_batches[0]],
            selection_phase="initialization",
        )
        self.f_batch(
            [point[: len(self.lb)] for point in base_batches[1]],
            selection_phase="turbo_trust_region",
        )


def _variables_config() -> VariablesConfig:
    return VariablesConfig(
        schema_version="1.0",
        variables=[
            VariableSpec(
                name="FN",
                kind=VariableKind.INTEGER,
                lower="2",
                upper="12",
                step="1",
            ),
            VariableSpec(
                name="WN",
                kind=VariableKind.CONTINUOUS_STEP,
                lower="0.3u",
                upper="2.0u",
                step="0.1u",
            ),
        ],
    )


def _optimizer_config(*, batch_size: int = 1) -> OptimizerConfig:
    return OptimizerConfig(
        schema_version="1.0",
        optimizer=OptimizerSettings(
            algorithm=OptimizerAlgorithm.TURBO,
            initialization=InitializationMethod.SOBOL,
            max_evaluations=100,
            batch_size=batch_size,
            random_seed=20260528,
            failure_penalty=1000.0,
            deduplicate_candidates=True,
        ),
    )


def _metrics_config(
    *,
    direction: ObjectiveDirection = ObjectiveDirection.MINIMIZE,
) -> MetricsConfig:
    return MetricsConfig(
        schema_version="1.0",
        metrics=[
            MetricSpec(
                name="delay",
                unit="ps",
                maestro_formula="delay",
                required_signals=["/out"],
            ),
            MetricSpec(
                name="gain",
                unit="dB",
                maestro_formula="gain",
                required_signals=["/out"],
            ),
        ],
        constraints=[
            ConstraintSpec(metric="delay", op=ConstraintOp.LE, value="100 ps"),
            ConstraintSpec(metric="gain", op=ConstraintOp.GE, value="10 dB"),
        ],
        objective=ObjectiveSpec(direction=direction, expression="delay / gain"),
    )


def test_load_native_turbo_contract_reads_existing_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    contract = load_native_turbo_contract(project_dir)

    assert [variable.name for variable in contract.variables.variables] == [
        "FN",
        "WN",
        "FP",
        "WP",
    ]
    assert contract.optimizer.optimizer.failure_penalty > 0
    assert contract.metrics.objective.expression


def test_quantize_candidate_snaps_and_formats_approved_variables() -> None:
    variables = VariablesConfig(
        schema_version="1.0",
        variables=[
            VariableSpec(
                name="FN",
                kind=VariableKind.INTEGER,
                lower="2",
                upper="12",
                step="1",
            ),
            VariableSpec(
                name="WN",
                kind=VariableKind.CONTINUOUS_STEP,
                lower="0.3u",
                upper="2.0u",
                step="0.1u",
            ),
        ],
    )

    assert quantize_candidate(variables, [11.6, 1.94]) == {"FN": "12", "WN": "1.9u"}
    assert quantize_candidate(variables, [0.0, 3.0]) == {"FN": "2", "WN": "2u"}


def test_quantize_candidate_clamps_off_grid_upper_to_last_approved_step() -> None:
    variables = VariablesConfig(
        schema_version="1.0",
        variables=[
            VariableSpec(
                name="WN",
                kind=VariableKind.CONTINUOUS_STEP,
                lower="0.3u",
                upper="3u",
                step="0.2u",
            ),
        ],
    )

    assert quantize_candidate(variables, [3.0]) == {"WN": "2.9u"}
    assert quantize_candidate(variables, [3.1]) == {"WN": "2.9u"}


def test_missing_metric_returns_failure_penalty() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 50.0},
    )

    assert result.status == "metric_failed"
    assert result.objective == 1000.0
    assert result.fom is None
    assert result.constraints_passed is False
    assert result.issues == ["metric gain missing"]


def test_non_finite_metric_returns_failure_penalty() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": math.nan, "gain": 20.0},
    )

    assert result.status == "metric_failed"
    assert result.objective == 1000.0
    assert result.issues == ["metric delay non_finite"]


def test_constraint_violation_returns_penalty_plus_normalized_score() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 110.0, "gain": 5.0},
    )

    assert result.status == "constraint_failed"
    assert result.constraints_passed is False
    assert result.fom == 22.0
    assert result.constraint_penalty == 0.26
    assert result.objective == 1000.26
    assert result.issues == [
        "constraint delay le 100 ps violated by 110.0",
        "constraint gain ge 10 dB violated by 5.0",
    ]


def test_feasible_minimize_candidate_returns_fom() -> None:
    result = evaluate_candidate_objective(
        _metrics_config(),
        _optimizer_config(),
        {"delay": 50.0, "gain": 20.0},
    )

    assert result.status == "feasible"
    assert result.constraints_passed is True
    assert result.fom == 2.5
    assert result.objective == 2.5
    assert result.constraint_penalty == 0.0
    assert result.issues == []


def test_feasible_maximize_candidate_returns_negative_fom_for_minimizer() -> None:
    metrics_config = _metrics_config(direction=ObjectiveDirection.MAXIMIZE)

    small_fom = evaluate_candidate_objective(
        metrics_config,
        _optimizer_config(),
        {"delay": 80.0, "gain": 40.0},
    )
    large_fom = evaluate_candidate_objective(
        metrics_config,
        _optimizer_config(),
        {"delay": 50.0, "gain": 10.0},
    )

    assert small_fom.fom == 2.0
    assert large_fom.fom == 5.0
    assert small_fom.objective == -2.0
    assert large_fom.objective == -5.0


def test_runner_calls_turbo_optimize_and_records_phases() -> None:
    _FakeTurbo.instances.clear()
    seen: list[dict[str, str]] = []

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        seen.append(parameters)
        return NativeTurboObservation(metrics={"delay": 50.0, "gain": 20.0})

    runner = NativeTurboRunner(
        variables=_variables_config(),
        metrics=_metrics_config(),
        optimizer=_optimizer_config(),
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
    )

    result = runner.run()

    assert _FakeTurbo.instances[0].optimize_called is True
    assert _FakeTurbo.instances[0].n_init == 4
    assert seen[0] == {"FN": "2", "WN": "0.3u"}
    assert result.evaluation_count == 5
    assert [trace.selection_phase for trace in result.traces] == [
        "initialization",
        "initialization",
        "initialization",
        "initialization",
        "turbo_trust_region",
    ]


def test_runner_replaces_duplicate_quantized_candidate_before_evaluation() -> None:
    evaluated: list[dict[str, str]] = []

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        evaluated.append(parameters)
        return NativeTurboObservation(metrics={"delay": 50.0, "gain": 20.0})

    runner = NativeTurboRunner(
        variables=_variables_config(),
        metrics=_metrics_config(),
        optimizer=_optimizer_config(),
        evaluator=evaluator,
        turbo_factory=_DuplicateFakeTurbo,
        max_evals=2,
    )

    result = runner.run()

    assert evaluated == [
        {"FN": "2", "WN": "0.3u"},
        {"FN": "3", "WN": "0.3u"},
    ]
    assert result.traces[1].issues == ["duplicate candidate replaced"]


def test_runner_records_duplicate_penalty_when_no_replacement_is_allowed() -> None:
    evaluated: list[dict[str, str]] = []

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        evaluated.append(parameters)
        return NativeTurboObservation(metrics={"delay": 50.0, "gain": 20.0})

    runner = NativeTurboRunner(
        variables=_variables_config(),
        metrics=_metrics_config(),
        optimizer=_optimizer_config(),
        evaluator=evaluator,
        turbo_factory=_DuplicateFakeTurbo,
        max_evals=2,
        replacement_attempts=0,
    )

    result = runner.run()

    assert evaluated == [{"FN": "2", "WN": "0.3u"}]
    assert result.traces[1].status == "duplicate_candidate_skipped"
    assert result.traces[1].objective == 1000.0


def test_runner_stops_after_repeated_workflow_level_failures() -> None:
    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        return NativeTurboObservation(
            status="real_check_failed",
            issues=[f"no result manifest for {parameters['FN']}"],
        )

    runner = NativeTurboRunner(
        variables=_variables_config(),
        metrics=_metrics_config(),
        optimizer=_optimizer_config(),
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
        workflow_failure_limit=3,
    )

    with pytest.raises(RuntimeError, match="workflow-level failure limit reached"):
        runner.run()

    assert len(runner.traces) == 3
    assert [trace.status for trace in runner.traces] == [
        "real_check_failed",
        "real_check_failed",
        "real_check_failed",
    ]


def test_batch_runner_records_batch_metadata_and_order() -> None:
    _FakeBatchTurbo.instances.clear()
    seen_batches: list[list[dict[str, str]]] = []

    def batch_evaluator(candidates) -> list[NativeTurboObservation]:
        seen_batches.append([candidate.parameters for candidate in candidates])
        return [
            NativeTurboObservation(metrics={"delay": 50.0, "gain": 20.0})
            for _candidate in candidates
        ]

    runner = NativeTurboBatchRunner(
        variables=_variables_config(),
        metrics=_metrics_config(),
        optimizer=_optimizer_config(batch_size=3),
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=_FakeBatchTurbo,
        max_evals=5,
        replacement_attempts=1,
        parallel_jobs=2,
        threads_per_run=10,
    )

    result = runner.run()

    assert _FakeBatchTurbo.instances[0].optimize_called is True
    assert _FakeBatchTurbo.instances[0].batch_size == 3
    assert result.evaluation_count == 5
    assert seen_batches == [
        [{"FN": "2", "WN": "0.3u"}, {"FN": "3", "WN": "0.3u"}],
        [{"FN": "4", "WN": "0.7u"}, {"FN": "5", "WN": "0.8u"}],
    ]
    assert result.traces[0].batch_id == "batch_001"
    assert result.traces[0].batch_slot == 1
    assert result.traces[0].batch_size == 3
    assert result.traces[0].batch_worker_count == 2
    assert result.traces[0].parallel_jobs == 2
    assert result.traces[0].threads_per_run == 10
    assert result.traces[1].issues == ["duplicate candidate replaced"]
    assert result.traces[2].status == "duplicate_candidate_skipped"
    assert result.traces[3].selection_phase == "turbo_trust_region"


def test_run_native_turbo_optimization_writes_compact_trace_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        assert set(parameters) == {"FN", "WN", "FP", "WP"}
        return NativeTurboObservation(
            metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    result = run_native_turbo_optimization(
        project_dir,
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
    )

    report = json.loads(
        (project_dir / "reports" / "native_turbo_optimizer_report.json").read_text(
            encoding="utf-8"
        )
    )
    lines = (
        project_dir / "reports" / "native_turbo_optimizer_evaluations.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert report["evaluation_count"] == 5
    assert report["best_candidate"]["status"] == "feasible"
    assert report["initialization"] == "sobol"
    assert report["effective_initial_design"] == "sobol"
    assert len(lines) == 5
    assert result.report_path == project_dir / "reports/native_turbo_optimizer_report.json"


def test_run_batch_native_turbo_optimization_uses_optimizer_batch_size(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    observed_batch_sizes: list[int] = []

    def batch_evaluator(candidates) -> list[NativeTurboObservation]:
        return [
            NativeTurboObservation(
                metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
            )
            for _candidate in candidates
        ]

    class CapturingBatchTurbo(_FakeBatchTurbo):
        def __init__(self, **kwargs) -> None:
            observed_batch_sizes.append(kwargs["batch_size"])
            super().__init__(**kwargs)

    result = run_batch_native_turbo_optimization(
        project_dir,
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=CapturingBatchTurbo,
        max_evals=5,
        parallel_jobs=3,
        threads_per_run=10,
    )

    assert observed_batch_sizes == [10]
    assert result.evaluation_count == 5
    assert result.report_path == project_dir / "reports/native_turbo_optimizer_report.json"


def test_run_batch_native_turbo_optimization_accepts_adapter_argument(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    def batch_evaluator(candidates) -> list[NativeTurboObservation]:
        return [
            NativeTurboObservation(
                metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
            )
            for _candidate in candidates
        ]

    result = run_batch_native_turbo_optimization(
        project_dir,
        adapter=lambda *args, **kwargs: None,
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=_FakeBatchTurbo,
        max_evals=5,
        parallel_jobs=3,
        threads_per_run=10,
    )

    assert result.evaluation_count == 5
    report = json.loads(
        (project_dir / "reports/native_turbo_optimizer_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["runtime_thread_limits"]["env_vars"] == {
        "MKL_NUM_THREADS": "4",
        "NUMBA_NUM_THREADS": "4",
        "NUMEXPR_NUM_THREADS": "4",
        "OMP_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
        "VECLIB_MAXIMUM_THREADS": "4",
    }


def test_run_batch_native_turbo_optimization_applies_optimizer_cpu_thread_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hermes_workflow.native_turbo as module

    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "deduplicate_candidates: true",
            "deduplicate_candidates: true\n  optimizer_cpu_threads: 3",
        ),
        encoding="utf-8",
    )
    calls: list[tuple[int, dict[str, object]]] = []

    @contextmanager
    def fake_limits(threads: int, **kwargs):
        calls.append((threads, dict(kwargs)))
        yield

    monkeypatch.setattr(module, "optimizer_cpu_thread_limits", fake_limits)

    def batch_evaluator(candidates) -> list[NativeTurboObservation]:
        return [
            NativeTurboObservation(
                metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
            )
            for _candidate in candidates
        ]

    result = run_batch_native_turbo_optimization(
        project_dir,
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=_FakeBatchTurbo,
        max_evals=5,
        parallel_jobs=3,
        threads_per_run=10,
    )

    assert result.evaluation_count == 5
    assert calls == [(3, {"set_environment": True, "backend": "native_turbo", "execution_mode": "local"})]


def test_default_batch_turbo_factory_calls_f_batch_by_chunk() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("gpytorch")
    np = pytest.importorskip("numpy")
    calls: list[tuple[str, int]] = []

    def f_batch(raw_batch, *, selection_phase: str) -> list[float]:
        calls.append((selection_phase, len(raw_batch)))
        return [float(len(calls) * 10 + index) for index, _raw in enumerate(raw_batch)]

    turbo = _default_batch_turbo_factory(
        f_batch=f_batch,
        lb=np.array([0.0, 0.0]),
        ub=np.array([1.0, 1.0]),
        n_init=4,
        max_evals=6,
        batch_size=2,
        verbose=False,
        n_training_steps=30,
    )

    turbo._create_candidates = lambda *args, **kwargs: (  # noqa: SLF001
        np.array([[0.1, 0.1], [0.9, 0.9]]),
        np.array([[0.0, 1.0], [1.0, 0.0]]),
        {},
    )
    turbo._select_candidates = lambda x_cand, _y_cand: x_cand[: turbo.batch_size]  # noqa: SLF001

    turbo.optimize()

    assert calls == [
        ("initialization", 2),
        ("initialization", 2),
        ("turbo_trust_region", 2),
    ]
    assert turbo.fX.shape == (6, 1)


def test_prepare_explicit_candidate_real_run_allows_first_optimizer_candidate(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    # create_approved_real_project prepares the old lower-bound real_001 package.
    # Remove it to model C-17's first optimizer-selected candidate path.
    import shutil

    shutil.rmtree(project_dir / "runs")

    package = prepare_explicit_candidate_real_run(
        project_dir,
        candidate_id="candidate_000001",
        source="native_turbo_optimizer",
        parameters={"VAR_INT": "3", "VAR_WIDTH": "0.3u"},
        run_id="real_001",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    assert package.run_id == "real_001"
    assert load_json(package.candidate_path)["candidate_id"] == "candidate_000001"
    assert (package.run_dir / "candidate_request.json").exists()
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()


def test_real_candidate_evaluator_runs_fake_adapter_checks_and_records(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        assert cadence_cshrc == Path("/tmp/fake.csh")
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"VAR_INT": "3", "VAR_WIDTH": "0.3u"},
        run_id="real_001",
        cadence_cshrc=Path("/tmp/fake.csh"),
        adapter=adapter,
    )

    assert observation.status == "recorded"
    assert set(observation.metrics) == {"metric_gain", "metric_power"}
    assert observation.result_manifest == "runs/real/real_001/result_manifest.json"
    assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()


def test_real_batch_evaluator_caps_parallel_adapter_calls(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    import shutil
    import threading
    import time

    shutil.rmtree(project_dir / "runs")
    active = 0
    max_active = 0
    lock = threading.Lock()

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        nonlocal active, max_active
        assert cadence_cshrc == Path("/tmp/fake.csh")
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
        )
        with lock:
            active -= 1

    width_values = ["0.1u", "0.2u", "0.3u", "0.4u"]
    candidates = [
        NativeTurboBatchCandidate(
            evaluation_index=index,
            run_id=f"real_{index:03d}",
            candidate_id=f"candidate_{index:06d}",
            batch_id="batch_001",
            batch_slot=index,
            batch_size=4,
            selection_phase="initialization",
            raw_x=[4.0, 0.5, 4.0, 1.1],
            parameters={
                "VAR_INT": str(index),
                "VAR_WIDTH": width_values[index - 1],
            },
            replacement_issues=[],
        )
        for index in range(1, 5)
    ]

    evaluator = make_real_candidate_batch_evaluator(
        project_dir,
        cadence_cshrc=Path("/tmp/fake.csh"),
        max_workers=2,
        adapter=adapter,
    )

    observations = evaluator(candidates)

    assert len(observations) == 4
    assert [observation.status for observation in observations] == ["recorded"] * 4
    assert all(observation.metrics for observation in observations)
    assert max_active == 2
    assert [
        json.loads(line)["run_id"]
        for line in (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ] == ["real_001", "real_002", "real_003", "real_004"]


def test_batch_evaluator_limits_parallel_candidates_without_inner_child_parallelism(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    import time

    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    active_candidates: set[str] = set()
    active_child_calls: dict[str, int] = {}
    max_active_candidates = 0
    max_child_calls_per_candidate = 0
    lock = threading.Lock()

    def fake_run_spectre_ocean_adapter(
        project: Path,
        *,
        run_id: str | None,
        testbench_id: str | None,
        corner_id: str | None,
    ):
        nonlocal max_active_candidates, max_child_calls_per_candidate

        assert project == project_dir
        assert run_id is not None
        assert testbench_id is not None
        assert corner_id is not None
        with lock:
            active_candidates.add(run_id)
            active_child_calls[run_id] = active_child_calls.get(run_id, 0) + 1
            max_active_candidates = max(max_active_candidates, len(active_candidates))
            max_child_calls_per_candidate = max(
                max_child_calls_per_candidate,
                active_child_calls[run_id],
            )
        time.sleep(0.01)
        with lock:
            active_child_calls[run_id] -= 1
            if active_child_calls[run_id] == 0:
                active_child_calls.pop(run_id)
                active_candidates.remove(run_id)
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "issues": [],
            },
        )()

    def fake_aggregate(project: Path, *, run_id: str):
        assert project == project_dir
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"MAX_GAIN": 1.0, "IIP3": 1.0},
        )
        return object()

    import hermes_workflow.execution_adapters.spectre_ocean as adapter_module
    import hermes_workflow.multi_testbench_aggregation as aggregation_module

    monkeypatch.setattr(
        adapter_module,
        "run_spectre_ocean_adapter",
        fake_run_spectre_ocean_adapter,
    )
    monkeypatch.setattr(
        aggregation_module,
        "aggregate_multi_testbench_run",
        fake_aggregate,
    )

    candidates = [
        NativeTurboBatchCandidate(
            evaluation_index=index,
            run_id=f"real_{index:03d}",
            candidate_id=f"candidate_{index:06d}",
            batch_id="batch_001",
            batch_slot=index,
            batch_size=4,
            selection_phase="initialization",
            raw_x=[4.0, 0.5, 4.0, 1.1],
            parameters={
                "FN": str(3 + index),
                "WN": "0.5u",
                "FP": "4",
                "WP": "1.1u",
            },
            replacement_issues=[],
        )
        for index in range(1, 5)
    ]

    evaluator = make_real_candidate_batch_evaluator(
        project_dir,
        cadence_cshrc=None,
        max_workers=2,
    )
    observations = evaluator(candidates)

    assert len(observations) == 4
    assert max_active_candidates == 2
    assert max_child_calls_per_candidate == 1


def test_default_adapter_runs_and_aggregates_multi_testbench_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    assert prepare_from_requirement(project_dir).status == "pass"
    calls: list[tuple[str, str | None]] = []
    aggregate_calls: list[str] = []

    def fake_run_spectre_ocean_adapter(
        project: Path,
        *,
        run_id: str | None,
        testbench_id: str | None,
        corner_id: str | None = None,
    ):
        assert project == project_dir
        calls.append((str(run_id), testbench_id))
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "issues": [],
            },
        )()

    def fake_aggregate(project: Path, *, run_id: str):
        assert project == project_dir
        aggregate_calls.append(run_id)
        return object()

    import hermes_workflow.execution_adapters.spectre_ocean as adapter_module
    import hermes_workflow.multi_testbench_aggregation as aggregation_module

    monkeypatch.setattr(
        adapter_module,
        "run_spectre_ocean_adapter",
        fake_run_spectre_ocean_adapter,
    )
    monkeypatch.setattr(
        aggregation_module,
        "aggregate_multi_testbench_run",
        fake_aggregate,
    )

    _run_default_adapter(project_dir, run_id="real_007", cadence_cshrc=None)

    assert calls == [
        ("real_007", "cg_nf"),
        ("real_007", "iip3"),
    ]
    assert aggregate_calls == ["real_007"]


def test_default_adapter_runs_multi_corner_children_serially(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    _inject_three_corner_section(project_dir)
    assert prepare_from_requirement(project_dir).status == "pass"
    calls: list[tuple[str, str, str]] = []
    aggregate_calls: list[str] = []

    def fake_run_spectre_ocean_adapter(
        project: Path,
        *,
        run_id: str | None,
        testbench_id: str | None,
        corner_id: str | None,
    ):
        assert project == project_dir
        assert run_id is not None
        assert testbench_id is not None
        assert corner_id is not None
        calls.append((run_id, testbench_id, corner_id))
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "issues": [],
            },
        )()

    def fake_aggregate(project: Path, *, run_id: str):
        assert project == project_dir
        aggregate_calls.append(run_id)
        return object()

    import hermes_workflow.execution_adapters.spectre_ocean as adapter_module
    import hermes_workflow.multi_testbench_aggregation as aggregation_module

    monkeypatch.setattr(
        adapter_module,
        "run_spectre_ocean_adapter",
        fake_run_spectre_ocean_adapter,
    )
    monkeypatch.setattr(
        aggregation_module,
        "aggregate_multi_testbench_run",
        fake_aggregate,
    )

    _run_default_adapter(project_dir, run_id="real_007", cadence_cshrc=None)

    assert calls == [
        ("real_007", "cg_nf", "tt"),
        ("real_007", "cg_nf", "ff"),
        ("real_007", "cg_nf", "ss"),
        ("real_007", "iip3", "tt"),
        ("real_007", "iip3", "ff"),
        ("real_007", "iip3", "ss"),
    ]
    assert aggregate_calls == ["real_007"]


def test_default_adapter_runs_single_testbench_multi_corner_children_serially(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_ready_multi_corner_single_testbench_project(
        tmp_path,
        corner_ids=["tt", "ff", "ss"],
    )
    calls: list[tuple[str, str | None, str | None]] = []
    aggregate_calls: list[str] = []

    def fake_run_spectre_ocean_adapter(
        project: Path,
        *,
        run_id: str,
        testbench_id: str | None = None,
        corner_id: str | None = None,
    ):
        assert project == project_dir
        calls.append((run_id, testbench_id, corner_id))
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "issues": [],
            },
        )()

    def fake_aggregate(project: Path, *, run_id: str):
        assert project == project_dir
        aggregate_calls.append(run_id)
        return object()

    import hermes_workflow.execution_adapters.spectre_ocean as adapter_module
    import hermes_workflow.multi_testbench_aggregation as aggregation_module
    import hermes_workflow.native_turbo as native_turbo_module

    monkeypatch.setattr(
        adapter_module,
        "run_spectre_ocean_adapter",
        fake_run_spectre_ocean_adapter,
    )
    monkeypatch.setattr(
        aggregation_module,
        "aggregate_multi_testbench_run",
        fake_aggregate,
    )

    native_turbo_module._run_default_adapter(
        project_dir,
        run_id="real_007",
        cadence_cshrc=None,
    )

    assert calls == [
        ("real_007", None, "tt"),
        ("real_007", None, "ff"),
        ("real_007", None, "ss"),
    ]
    assert aggregate_calls == ["real_007"]


def test_default_adapter_preserves_explicit_single_corner_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_ready_multi_corner_single_testbench_project(
        tmp_path,
        corner_ids=["ss"],
    )
    calls: list[tuple[str, str | None, str | None]] = []
    aggregate_calls: list[str] = []

    def fake_run_spectre_ocean_adapter(
        project: Path,
        *,
        run_id: str,
        testbench_id: str | None = None,
        corner_id: str | None = None,
    ):
        assert project == project_dir
        calls.append((run_id, testbench_id, corner_id))
        return type("Result", (), {"status": "succeeded", "issues": []})()

    def fake_aggregate(project: Path, *, run_id: str):
        assert project == project_dir
        aggregate_calls.append(run_id)
        return object()

    import hermes_workflow.execution_adapters.spectre_ocean as adapter_module
    import hermes_workflow.multi_testbench_aggregation as aggregation_module
    import hermes_workflow.native_turbo as native_turbo_module

    monkeypatch.setattr(
        adapter_module,
        "run_spectre_ocean_adapter",
        fake_run_spectre_ocean_adapter,
    )
    monkeypatch.setattr(
        aggregation_module,
        "aggregate_multi_testbench_run",
        fake_aggregate,
    )

    native_turbo_module._run_default_adapter(
        project_dir,
        run_id="real_007",
        cadence_cshrc=None,
    )

    assert calls == [("real_007", None, "ss")]
    assert aggregate_calls == ["real_007"]


def test_real_candidate_evaluator_classifies_written_metric_failure(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            metric_status="failed",
        )
        raise RuntimeError("adapter returned failed status")

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"VAR_INT": "3", "VAR_WIDTH": "0.3u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "metric_check_failed"
    assert observation.metrics is None
    assert observation.issues is not None
    assert "metric metric_gain did not succeed" in observation.issues
    assert "adapter returned failed status" not in observation.issues
    assert (
        load_json(project_dir / "runs" / "real" / "real_001" / "recovery_decision.json")[
            "decision"
        ]
        == "abandon_candidate"
    )


def test_real_candidate_evaluator_classifies_failed_result_manifest_as_real_failure(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(
            project,
            run_id=run_id,
            status="failed",
        )
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"VAR_INT": "3", "VAR_WIDTH": "0.3u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "real_check_failed"
    assert observation.metrics is None
    assert any("result_status is failed" in issue for issue in observation.issues or [])
    assert observation.result_manifest == "runs/real/real_001/result_manifest.json"
    assert (
        load_json(project_dir / "runs" / "real" / "real_001" / "recovery_decision.json")[
            "decision"
        ]
        == "abandon_candidate"
    )


def test_run_native_turbo_cli_uses_fake_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    project_dir.mkdir()

    def fake_run_native_turbo_optimization(project_dir_arg: Path, **kwargs):
        assert kwargs["max_evals"] is None
        reports = project_dir_arg / "reports"
        reports.mkdir()
        report_path = reports / "native_turbo_optimizer_report.json"
        evaluations_path = reports / "native_turbo_optimizer_evaluations.jsonl"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "evaluation_count": 3,
                    "best_candidate": None,
                    "issues": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        evaluations_path.write_text("", encoding="utf-8")
        return type(
            "FakeResult",
            (),
            {
                "evaluation_count": 3,
                "report_path": report_path,
                "evaluations_path": evaluations_path,
            },
        )()

    monkeypatch.setattr(
        "hermes_workflow.cli.run_native_turbo_optimization",
        fake_run_native_turbo_optimization,
    )
    result = CliRunner().invoke(
        app,
            [
                "run-native-turbo",
                str(project_dir),
                "--cadence-cshrc",
                "/tmp/fake.csh",
            ],
    )

    assert result.exit_code == 0
    assert "native turbo optimization completed: 3 evaluations" in result.output


def test_run_native_turbo_cli_parallel_uses_batch_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    project_dir.mkdir()
    called: dict[str, object] = {}

    def fake_run_batch_native_turbo_optimization(project_dir_arg: Path, **kwargs):
        called["project_dir"] = project_dir_arg
        called["max_evals"] = kwargs["max_evals"]
        called["cadence_cshrc"] = kwargs["cadence_cshrc"]
        reports = project_dir_arg / "reports"
        reports.mkdir()
        report_path = reports / "native_turbo_optimizer_report.json"
        evaluations_path = reports / "native_turbo_optimizer_evaluations.jsonl"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "evaluation_count": 10,
                    "best_candidate": None,
                    "issues": [],
                    "batch_summary": {"batch_count": 1},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        evaluations_path.write_text("", encoding="utf-8")
        return type(
            "FakeResult",
            (),
            {
                "evaluation_count": 10,
                "report_path": report_path,
                "evaluations_path": evaluations_path,
            },
        )()

    monkeypatch.setattr(
        "hermes_workflow.cli.run_batch_native_turbo_optimization",
        fake_run_batch_native_turbo_optimization,
    )
    result = CliRunner().invoke(
        app,
            [
                "run-native-turbo",
                str(project_dir),
                "--parallel",
                "--cadence-cshrc",
                "/tmp/fake.csh",
            ],
    )

    assert result.exit_code == 0
    assert called["project_dir"] == project_dir
    assert called["max_evals"] is None
    assert called["cadence_cshrc"] == Path("/tmp/fake.csh")


def test_write_native_turbo_reports_includes_batch_summary(tmp_path: Path) -> None:
    trace_one = NativeTurboEvaluationTrace(
        evaluation_index=1,
        run_id="real_001",
        selection_phase="initialization",
        raw_x=[4.0, 0.5],
        parameters={"FN": "4", "WN": "0.5u"},
        status="feasible",
        objective=1.0,
        fom=1.0,
        constraint_penalty=0.0,
        metrics={"delay": 1.0, "gain": 20.0},
        result_manifest="runs/real/real_001/result_manifest.json",
        metric_result_manifest="runs/real/real_001/metrics/metric_result_manifest.json",
        issues=[],
        batch_id="batch_001",
        batch_slot=1,
        batch_size=2,
        batch_worker_count=2,
        max_parallel_jobs=10,
        threads_per_run=10,
        parallel_jobs=10,
    )
    trace_two = NativeTurboEvaluationTrace(
        evaluation_index=2,
        run_id="real_002",
        selection_phase="initialization",
        raw_x=[5.0, 0.6],
        parameters={"FN": "5", "WN": "0.6u"},
        status="constraint_failed",
        objective=1001.0,
        fom=1.5,
        constraint_penalty=1.0,
        metrics={"delay": 200.0, "gain": 20.0},
        result_manifest="runs/real/real_002/result_manifest.json",
        metric_result_manifest="runs/real/real_002/metrics/metric_result_manifest.json",
        issues=["constraint delay <= 100 ps failed"],
        batch_id="batch_001",
        batch_slot=2,
        batch_size=2,
        batch_worker_count=2,
        max_parallel_jobs=10,
        threads_per_run=10,
        parallel_jobs=10,
    )

    report_path, _evaluations_path = write_native_turbo_reports(
        tmp_path,
        NativeTurboRunResult(
            evaluation_count=2,
            traces=[trace_one, trace_two],
            best_trace=trace_one,
        ),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["effectiveness_audit"] == "reports/optimizer_effectiveness_audit.json"
    assert payload["batch_summary"] == {
        "batch_count": 1,
        "max_batch_worker_count": 2,
        "status_counts": {"constraint_failed": 1, "feasible": 1},
    }
    audit_payload = json.loads(
        (tmp_path / "reports" / "optimizer_effectiveness_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit_payload["backend"] == "native_turbo"
    assert audit_payload["requested_strategy"] == "turbo_trust_region"
    assert audit_payload["batches"][0]["history_size_before"] == 0


class _CapturedNativeTurboMaxWorkers(Exception):
    """Sentinel raised by the monkeypatched evaluator factory to short-circuit
    `run_batch_native_turbo_optimization` after capturing the scheduler value."""


def _set_native_turbo_config_parallelism(
    project_dir: Path,
    *,
    batch_size: int,
    parallel_jobs: int,
) -> None:
    """Update batch_size in optimizer.yaml and parallel_jobs in spectre.yaml."""

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


def test_native_turbo_uses_requirement_parallel_jobs_for_candidate_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock contract: native TuRBO real evaluator uses
    max_workers = min(batch_size, parallel_jobs_from_config)
    where parallel_jobs comes from bundle.spectre.spectre.parallel_jobs
    (config-loaded SpectreSettings), not from prepared/request spectre metadata.
    """

    import hermes_workflow.native_turbo as module

    # Schema rule (validate.py) requires optimizer.batch_size <= spectre.parallel_jobs.
    cases = [
        # (batch_size, parallel_jobs, expected min)
        (3, 5, 3),
        (2, 4, 2),
    ]
    for batch_size, parallel_jobs, expected in cases:
        case_root = tmp_path / f"case_b{batch_size}_p{parallel_jobs}"
        project_dir = case_root / "project"
        create_project_from_template(project_dir)
        _set_native_turbo_config_parallelism(
            project_dir,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
        )

        # No prepared/request files exist here at all, which makes it
        # mechanically impossible for the scheduler value to come from
        # runtime spectre metadata. The contract under test forces the value
        # to flow from bundle.spectre.spectre.parallel_jobs.
        assert not (project_dir / "runs").exists()

        captured: dict[str, int] = {}

        def fake_factory(
            project_dir,
            *,
            cadence_cshrc,
            max_workers,
            adapter=None,
        ):
            captured["max_workers"] = max_workers
            raise _CapturedNativeTurboMaxWorkers

        monkeypatch.setattr(
            module,
            "make_real_candidate_batch_evaluator",
            fake_factory,
        )

        with pytest.raises(_CapturedNativeTurboMaxWorkers):
            run_batch_native_turbo_optimization(
                project_dir,
                max_evals=1,
            )

        assert captured["max_workers"] == expected, (
            f"expected min({batch_size}, {parallel_jobs}) == {expected}, "
            f"got {captured['max_workers']}"
        )


# ---------------------------------------------------------------------------
# B-06 Run retention contract integration (local TuRBO paths)
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
    """Mirror create_approved_real_project but flip retention flags BEFORE the
    execution package hashes config files (to avoid immutable-config drift)."""
    from hermes_workflow.approvals import decide_first_real_run
    from hermes_workflow.real_run import prepare_real_run

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
    template_path.write_text(
        "simulator lang=spectre\n"
        "parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


def test_native_turbo_evaluate_real_candidate_deletes_run_dir_when_keep_successful_runs_false(
    tmp_path: Path,
) -> None:
    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=True, keep_successful_runs=False
    )
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "recorded"
    assert not (project_dir / "runs" / "real" / "real_001").exists()
    decision_path = project_dir / "state" / "run_retention" / "real_001.json"
    assert decision_path.is_file()
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["run_status"] == "successful"
    assert decision["local_action"] == "deleted"
    assert decision["candidate_id"] == "candidate_000001"
    # ledger and state must NOT be removed.
    assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert (project_dir / "state" / "optimizer_state.json").exists()


def test_native_turbo_evaluate_real_candidate_keeps_run_dir_when_keep_successful_runs_true(
    tmp_path: Path,
) -> None:
    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=True, keep_successful_runs=True
    )
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "recorded"
    assert (project_dir / "runs" / "real" / "real_001").is_dir()
    decision = json.loads(
        (project_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["local_action"] == "kept"
    assert decision["run_status"] == "successful"


def test_native_turbo_evaluate_real_candidate_classifies_constraint_fail_as_successful_for_retention(
    tmp_path: Path,
) -> None:
    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=False, keep_successful_runs=True
    )
    import shutil

    shutil.rmtree(project_dir / "runs")

    # Values violate the rise<80e-12 constraint but are valid finite scalars,
    # so record_real_result will still record (simulation_status=real_constraint_fail).
    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"rise": 200.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "recorded"
    decision = json.loads(
        (project_dir / "state" / "run_retention" / "real_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert decision["run_status"] == "successful"
    # keep_successful_runs is true → kept.
    assert decision["local_action"] == "kept"
    assert (project_dir / "runs" / "real" / "real_001").is_dir()


def test_native_turbo_evaluate_real_candidate_deletes_run_dir_when_keep_failed_runs_false_on_record_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_approved_real_project_with_keep_flags(
        tmp_path, keep_failed_runs=False, keep_successful_runs=True
    )
    import shutil

    shutil.rmtree(project_dir / "runs")

    def adapter(project: Path, *, run_id: str, cadence_cshrc: Path | None) -> None:
        write_fake_result_manifest(project, run_id=run_id)
        write_fake_metric_result_manifest(
            project,
            run_id=run_id,
            values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    # Force record_real_result to report a non-pass status.
    import hermes_workflow.native_turbo as native_turbo_module
    from hermes_workflow.reports import (
        RealResultRecordFlags,
        RealResultRecordReport,
        RealResultRecordStatus,
    )

    def fake_record(project_dir: Path, *, run_id: str) -> object:
        return RealResultRecordReport(
            schema_version="1.0",
            status=RealResultRecordStatus.FAIL,
            run_id=run_id,
            candidate_id="candidate_000001",
            ledger_path="ledger/experiment_ledger.jsonl",
            optimizer_state_path="state/optimizer_state.json",
            best_candidate_path=None,
            checks=RealResultRecordFlags(),
            issues=["fake record failure"],
        )

    monkeypatch.setattr(native_turbo_module, "record_real_result", fake_record)

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "record_failed"
    decision_path = project_dir / "state" / "run_retention" / "real_001.json"
    assert decision_path.is_file()
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["run_status"] == "failed"
    assert decision["local_action"] == "deleted"
    assert not (project_dir / "runs" / "real" / "real_001").exists()


def _make_split_native_turbo_traces() -> list[NativeTurboEvaluationTrace]:
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


def _write_seven_ledger_rows(project_dir: Path) -> None:
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


def _set_optimizer_max_evaluations_for_native(project_dir: Path, value: int) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    text = optimizer_path.read_text(encoding="utf-8")
    text = text.replace("max_evaluations: 100", f"max_evaluations: {value}")
    optimizer_path.write_text(text, encoding="utf-8")


def test_write_native_turbo_reports_syncs_optimizer_progress_state(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _set_optimizer_max_evaluations_for_native(project_dir, 10)
    _write_seven_ledger_rows(project_dir)

    traces = _make_split_native_turbo_traces()
    write_native_turbo_reports(
        project_dir,
        NativeTurboRunResult(
            evaluation_count=10,
            traces=traces,
            best_trace=None,
        ),
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


def _set_turbo_optimizer_initialization(
    project_dir: Path, *, initialization: str
) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    body = [
        'schema_version: "1.0"',
        '',
        'optimizer:',
        '  algorithm: turbo',
        f'  initialization: {initialization}',
        '  max_evaluations: 8',
        '  batch_size: 2',
        '  random_seed: 20260528',
        '  optimizer_cpu_threads: 4',
        '  failure_penalty: 1000000.0',
        '  deduplicate_candidates: true',
    ]
    optimizer_path.write_text("\n".join(body) + "\n", encoding="utf-8")


def test_initial_unit_design_returns_lhs_for_latin_hypercube() -> None:
    pytest.importorskip("numpy")
    from hermes_workflow.native_turbo import _initial_unit_design

    samples = _initial_unit_design("latin_hypercube", n=4, dim=2, seed=20260528)
    assert samples.shape == (4, 2)
    assert ((samples >= 0.0) & (samples <= 1.0)).all()


def test_initial_unit_design_random_is_deterministic() -> None:
    pytest.importorskip("numpy")
    from hermes_workflow.native_turbo import _initial_unit_design

    a = _initial_unit_design("random", n=4, dim=2, seed=20260528)
    b = _initial_unit_design("random", n=4, dim=2, seed=20260528)
    assert a.shape == (4, 2)
    assert ((a >= 0.0) & (a <= 1.0)).all()
    assert (a == b).all()


def test_initial_unit_design_sobol_is_deterministic() -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("scipy.stats.qmc")
    from hermes_workflow.native_turbo import _initial_unit_design

    a = _initial_unit_design("sobol", n=4, dim=2, seed=20260528)
    b = _initial_unit_design("sobol", n=4, dim=2, seed=20260528)
    assert a.shape == (4, 2)
    assert ((a >= 0.0) & (a <= 1.0)).all()
    assert (a == b).all()


def test_initial_unit_design_sobol_differs_for_different_seeds() -> None:
    """B-07 contract: random_seed must actually change the Sobol design.

    With ``scramble=False`` scipy's Sobol ignores the seed and returns the
    canonical Sobol sequence regardless of input. Two distinct seeds must
    therefore produce distinct samples for the contract to hold.
    """
    pytest.importorskip("numpy")
    pytest.importorskip("scipy.stats.qmc")
    from hermes_workflow.native_turbo import _initial_unit_design

    a = _initial_unit_design("sobol", n=4, dim=2, seed=1)
    b = _initial_unit_design("sobol", n=4, dim=2, seed=2)
    assert a.shape == (4, 2)
    assert b.shape == (4, 2)
    assert not (a == b).all()


def test_initial_unit_design_rejects_unknown_method() -> None:
    pytest.importorskip("numpy")
    from hermes_workflow.native_turbo import _initial_unit_design

    with pytest.raises(ValueError, match="initialization method"):
        _initial_unit_design("uniform_grid", n=4, dim=2, seed=42)


@pytest.mark.parametrize(
    "initialization",
    ["sobol", "latin_hypercube", "random"],
)
def test_native_turbo_batch_runner_passes_initialization_to_factory(
    tmp_path: Path, initialization: str
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    _set_turbo_optimizer_initialization(project_dir, initialization=initialization)

    captured: list[dict[str, object]] = []

    def fake_factory(**kwargs):
        captured.append(dict(kwargs))
        return _FakeBatchTurbo(
            **{
                key: value
                for key, value in kwargs.items()
                if key
                in {"f_batch", "lb", "ub", "n_init", "max_evals", "batch_size", "verbose"}
            }
        )

    _FakeBatchTurbo.instances.clear()

    def batch_evaluator(candidates):
        return [
            NativeTurboObservation(metrics={"delay": 50.0, "gain": 20.0})
            for _candidate in candidates
        ]

    run_batch_native_turbo_optimization(
        project_dir,
        max_evals=2,
        batch_evaluator=batch_evaluator,
        batch_turbo_factory=fake_factory,
    )

    assert captured, "factory must have been invoked at least once"
    assert captured[0]["initialization"] == initialization


def test_native_turbo_report_records_initialization(tmp_path: Path) -> None:
    trace = NativeTurboEvaluationTrace(
        evaluation_index=1,
        run_id="real_001",
        selection_phase="initialization",
        raw_x=[4.0, 0.5],
        parameters={"FN": "4", "WN": "0.5u"},
        status="feasible",
        objective=1.0,
        fom=1.0,
        constraint_penalty=0.0,
        metrics={"delay": 1.0, "gain": 20.0},
        result_manifest=None,
        metric_result_manifest=None,
        issues=[],
        batch_id="batch_001",
        batch_slot=1,
        batch_size=1,
        batch_worker_count=1,
        max_parallel_jobs=1,
        threads_per_run=1,
        parallel_jobs=1,
    )

    report_path, _evaluations_path = write_native_turbo_reports(
        tmp_path,
        NativeTurboRunResult(
            evaluation_count=1,
            traces=[trace],
            best_trace=trace,
            initialization="random",
            effective_initial_design="random",
        ),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["initialization"] == "random"
    assert payload["effective_initial_design"] == "random"

    audit_payload = json.loads(
        (tmp_path / "reports" / "optimizer_effectiveness_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit_payload["initialization"] == "random"
    assert audit_payload["effective_initial_design"] == "random"


# ---------------------------------------------------------------------------
# CPU thread limit runtime audit (B-11)
# ---------------------------------------------------------------------------


def test_native_turbo_report_contains_optimizer_cpu_threads(tmp_path: Path) -> None:
    """native_turbo_optimizer_report.json must record optimizer_cpu_threads."""
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "deduplicate_candidates: true",
            "deduplicate_candidates: true\n  optimizer_cpu_threads: 32",
        ),
        encoding="utf-8",
    )

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        return NativeTurboObservation(
            metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    run_native_turbo_optimization(
        project_dir,
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
    )

    report = json.loads(
        (project_dir / "reports" / "native_turbo_optimizer_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert "optimizer_cpu_threads" in report, (
        f"optimizer_cpu_threads missing from report, keys: {list(report.keys())}"
    )
    assert report["optimizer_cpu_threads"] == 32


def test_native_turbo_report_contains_runtime_thread_limits(tmp_path: Path) -> None:
    """native_turbo_optimizer_report.json must contain runtime_thread_limits
    with env vars and threadpoolctl state."""
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "deduplicate_candidates: true",
            "deduplicate_candidates: true\n  optimizer_cpu_threads: 32",
        ),
        encoding="utf-8",
    )

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        return NativeTurboObservation(
            metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    run_native_turbo_optimization(
        project_dir,
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
    )

    report = json.loads(
        (project_dir / "reports" / "native_turbo_optimizer_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert "runtime_thread_limits" in report, (
        f"runtime_thread_limits missing from report, keys: {list(report.keys())}"
    )
    rtl = report["runtime_thread_limits"]
    assert rtl["source"] == "optimizer.optimizer_cpu_threads"
    assert rtl["requested_threads"] == 32
    assert rtl["backend"] == "native_turbo"
    assert rtl["execution_mode"] == "local"
    assert rtl["process_scope"] == "local_optimizer_process"
    assert rtl["transport_mode"] == "local"
    # Native TuRBO uses set_environment=False, so env_vars reflect actual
    # runtime state (not forced). The key is that env_vars dict is present
    # with all expected keys, even if values are None.
    assert "OMP_NUM_THREADS" in rtl["env_vars"]
    assert "MKL_NUM_THREADS" in rtl["env_vars"]
    assert "available" in rtl["threadpoolctl"]
    assert "available" in rtl["torch"]
    assert isinstance(rtl["issues"], list)


def test_native_turbo_effectiveness_audit_contains_runtime_thread_limits(
    tmp_path: Path,
) -> None:
    """optimizer_effectiveness_audit.json must contain runtime_thread_limits
    for native TuRBO runs."""
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "deduplicate_candidates: true",
            "deduplicate_candidates: true\n  optimizer_cpu_threads: 32",
        ),
        encoding="utf-8",
    )

    def evaluator(parameters: dict[str, str]) -> NativeTurboObservation:
        return NativeTurboObservation(
            metrics={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
        )

    run_native_turbo_optimization(
        project_dir,
        evaluator=evaluator,
        turbo_factory=_FakeTurbo,
        max_evals=5,
    )

    audit = json.loads(
        (project_dir / "reports" / "optimizer_effectiveness_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert "runtime_thread_limits" in audit, (
        f"runtime_thread_limits missing from effectiveness audit, "
        f"keys: {list(audit.keys())}"
    )
    assert audit["runtime_thread_limits"]["backend"] == "native_turbo"
    assert audit["runtime_thread_limits"]["requested_threads"] == 32
    env_vars = audit["runtime_thread_limits"]["env_vars"]
    assert env_vars == {
        "MKL_NUM_THREADS": "32",
        "NUMBA_NUM_THREADS": "32",
        "NUMEXPR_NUM_THREADS": "32",
        "OMP_NUM_THREADS": "32",
        "OPENBLAS_NUM_THREADS": "32",
        "VECLIB_MAXIMUM_THREADS": "32",
    }
