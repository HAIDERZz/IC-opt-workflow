from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.openbox_backend import run_openbox_fake_optimization
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from tests.real_run_smoke_helpers import create_approved_real_project


class FakeAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        batch = self._batches.pop(0)
        return batch[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        assert observations


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
    assert len(rows) == 4
    assert rows[0]["parameters"]["WN"].endswith("u")
    assert rows[0]["result_manifest"] is None
    assert rows[0]["metric_result_manifest"] is None
    assert rows[0]["batch_id"] == "batch_001"


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
