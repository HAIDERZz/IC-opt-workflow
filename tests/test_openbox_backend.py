from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.cli import app
from hermes_workflow.openbox_backend import (
    _build_openbox_space,
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


class FakeAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "FP": 3, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "FP": 5, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "FP": 7, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "FP": 9, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        batch = self._batches.pop(0)
        return batch[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        self.updated_observations.extend(observations)
        assert observations


class ContinuationAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self.updated_observations: list[object] = []
        self.seen_prior_before_suggest = False
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "FP": 3, "WP": 0.4},
                {"FN": 10, "WN": 2.4, "FP": 11, "WP": 2.6},
            ],
            [
                {"FN": 12, "WN": 2.8, "FP": 12, "WP": 2.8},
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
                    "FN": 2 + (value % 10),
                    "WN": 0.3 + 0.2 * (value % 10),
                    "FP": 3 + (value % 9),
                    "WP": 0.5 + 0.2 * (value % 9),
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
        "max_evaluations: 100",
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

    assert by_name["WN"].upper == 2.9
    assert by_name["WP"].upper == 2.9
    assert by_name["FN"].upper == 12
    assert by_name["FP"].upper == 12
    assert list(by_name) == ["FN", "WN", "FP", "WP"]


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
    assert rows[0]["parameters"]["WN"].endswith("u")
    assert rows[0]["parameters"]["FP"] != rows[0]["parameters"]["FN"]
    assert rows[0]["result_manifest"] is None
    assert rows[0]["metric_result_manifest"] is None
    assert rows[0]["batch_id"] == "batch_001"


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
        "prior_evaluation_count": 2,
        "additional_evals": 2,
        "target_total_evals": 4,
    }
    assert len(rows) == 4
    assert rows[0]["evaluation_index"] == 1
    assert rows[2]["evaluation_index"] == 3
    assert rows[2]["run_id"] == "fake_003"
    assert rows[2]["batch_id"] == "batch_002"
    assert rows[2]["parameters"] == {
        "FN": "10",
        "WN": "2.3u",
        "FP": "11",
        "WP": "2.7u",
    }


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
    class MissingFpAdvisor:
        def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
            assert batch_size == 1
            return [{"FN": 2, "WN": 0.2, "WP": 0.4}]

        def update_observations(self, observations: list[object]) -> None:
            raise AssertionError("must fail before observation update")

    try:
        run_openbox_fake_optimization(
            create_approved_real_project(tmp_path),
            max_evals=1,
            batch_size=1,
            advisor_factory=lambda _space, _seed: MissingFpAdvisor(),
        )
    except ValueError as exc:
        assert "missing variable FP" in str(exc)
    else:
        raise AssertionError("expected missing FP to fail")


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
        advisor_factory=lambda _space, _seed: SequentialAdvisor(),
        adapter=adapter,
    )
    state = json.loads(
        (project_dir / "state" / "optimizer_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "completed"
    advisor = SequentialAdvisor(start=8)

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
    ) -> object:
        assert max_evals == 3
        assert batch_size == 2
        assert parallel_jobs == 2
        assert cadence_cshrc is None
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
            "--max-evals",
            "3",
            "--batch-size",
            "2",
            "--parallel-jobs",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "openbox real optimization completed: 3 evaluations" in result.output


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
    ) -> object:
        assert max_evals is None
        assert additional_evals == 5
        assert continue_from_existing is True
        assert batch_size == 2
        assert parallel_jobs == 2
        assert cadence_cshrc is None
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
            "--additional-evals",
            "5",
            "--batch-size",
            "2",
            "--parallel-jobs",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "openbox real continuation completed: 7 cumulative evaluations" in result.output
