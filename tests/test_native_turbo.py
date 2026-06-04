from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.native_turbo import (
    NativeTurboObservation,
    NativeTurboBatchCandidate,
    NativeTurboBatchRunner,
    NativeTurboEvaluationTrace,
    NativeTurboRunner,
    NativeTurboRunResult,
    _default_batch_turbo_factory,
    evaluate_candidate_objective,
    evaluate_real_candidate,
    load_native_turbo_contract,
    make_real_candidate_batch_evaluator,
    quantize_candidate,
    run_batch_native_turbo_optimization,
    run_native_turbo_optimization,
    write_native_turbo_reports,
)
from hermes_workflow.package import create_project_from_template
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
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
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    load_json,
    write_fake_metric_result_manifest,
    write_fake_result_manifest,
)


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
    ) -> None:
        self.f_batch = f_batch
        self.lb = lb
        self.ub = ub
        self.n_init = n_init
        self.max_evals = max_evals
        self.batch_size = batch_size
        self.verbose = verbose
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
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
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
            values={"rise": 1.0, "fall": 1.0, "DC": 1.0},
        )

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        cadence_cshrc=Path("/tmp/fake.csh"),
        adapter=adapter,
    )

    assert observation.status == "recorded"
    assert observation.metrics == {"rise": 1.0, "fall": 1.0, "DC": 1.0}
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
            values={"rise": 1.0, "fall": 1.0, "DC": 1.0},
        )
        with lock:
            active -= 1

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
            values={"rise": 1.0, "fall": 1.0, "DC": 1.0},
        )
        raise RuntimeError("adapter returned failed status")

    observation = evaluate_real_candidate(
        project_dir,
        candidate_id="candidate_000001",
        parameters={"FN": "4", "WN": "0.5u", "FP": "4", "WP": "1.1u"},
        run_id="real_001",
        adapter=adapter,
    )

    assert observation.status == "metric_check_failed"
    assert observation.metrics is None
    assert observation.issues is not None
    assert "metric rise did not succeed" in observation.issues
    assert "adapter returned failed status" not in observation.issues
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
        reports = project_dir_arg / "reports"
        reports.mkdir()
        report_path = reports / "native_turbo_optimizer_report.json"
        evaluations_path = reports / "native_turbo_optimizer_evaluations.jsonl"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "evaluation_count": kwargs["max_evals"],
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
                "evaluation_count": kwargs["max_evals"],
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
            "--max-evals",
            "3",
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
            "--max-evals",
            "10",
            "--cadence-cshrc",
            "/tmp/fake.csh",
        ],
    )

    assert result.exit_code == 0
    assert called["project_dir"] == project_dir
    assert called["max_evals"] == 10
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
    assert payload["batch_summary"] == {
        "batch_count": 1,
        "max_batch_worker_count": 2,
        "status_counts": {"constraint_failed": 1, "feasible": 1},
    }
