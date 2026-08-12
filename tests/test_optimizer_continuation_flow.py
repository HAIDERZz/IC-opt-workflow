from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_workflow import optimizer_continuation_flow
from hermes_workflow.validate import local_model_file_is_readable
from tests.project_factory import create_generic_project


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_scientifically_drifted_history(
    tmp_path: Path,
    *,
    backend: str,
) -> Path:
    project_dir = create_generic_project(tmp_path)
    result_relative = "runs/real/real_001/result_manifest.json"
    metric_relative = (
        "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    trace = {
        "batch_id": "batch_001",
        "batch_size": 1,
        "batch_slot": 1,
        "constraint_penalty": 0.0,
        "evaluation_index": 1,
        "fom": 1.0,
        "issues": [],
        "metric_result_manifest": metric_relative,
        "metrics": {"metric_gain": 1.0, "metric_power": 0.0},
        "objective": -999.0,
        "parameters": {"VAR_INT": "1", "VAR_WIDTH": "0.1u"},
        "raw_x": [1.0, 0.1],
        "result_manifest": result_relative,
        "run_id": "real_001",
        "selection_phase": "initialization",
        "status": "feasible",
    }
    evaluations_relative = (
        "reports/optimizer_evaluations.jsonl"
        if backend == "openbox"
        else "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    report_relative = (
        "reports/optimizer_run_report.json"
        if backend == "openbox"
        else "reports/native_turbo_optimizer_report.json"
    )
    report_payload: dict[str, object] = {
        "backend": backend,
        "best_candidate": trace,
        "evaluation_count": 1,
        "evaluations": evaluations_relative,
        "issues": [],
        "schema_version": "1.0",
        "status": "completed",
    }
    if backend == "openbox":
        report_payload["execution_mode"] = "real"
    _write_json(project_dir / report_relative, report_payload)
    evaluations_path = project_dir / evaluations_relative
    evaluations_path.parent.mkdir(parents=True, exist_ok=True)
    evaluations_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    _write_json(
        project_dir / result_relative,
        {
            "candidate_id": "candidate_000001",
            "metric_result_manifest": metric_relative,
            "run_id": "real_001",
            "simulator": {
                "output_format": "psfxl",
                "preset": "ax",
                "threads_per_run": 2,
            },
            "status": "succeeded",
        },
    )
    _write_json(
        project_dir / metric_relative,
        {
            "candidate_id": "candidate_000001",
            "metrics": [
                {
                    "name": "metric_gain",
                    "status": "succeeded",
                    "unit": "V/V",
                    "value": 1.0,
                },
                {
                    "name": "metric_power",
                    "status": "succeeded",
                    "unit": "W",
                    "value": 0.0,
                },
            ],
            "run_id": "real_001",
            "status": "succeeded",
        },
    )
    return project_dir


def test_local_turbo_continuation_dispatches_to_native_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "assert_valid_project",
        lambda _project, **_kwargs: SimpleNamespace(optimizer=object()),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "_backend_from_project_strategy",
        lambda *_args, **_kwargs: "native_turbo",
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_openbox_real_optimization",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("OpenBox must not run for a TuRBO continuation")
        ),
    )

    def fake_native(project: Path, **kwargs: object) -> SimpleNamespace:
        captured["native_project"] = project
        captured["native_kwargs"] = kwargs
        return SimpleNamespace(evaluation_count=7)

    def fake_closeout(project: Path, **kwargs: object) -> SimpleNamespace:
        captured["closeout_project"] = project
        captured["closeout_kwargs"] = kwargs
        kwargs["optimizer_fn"](project)
        return SimpleNamespace(status="pass", backend=kwargs["backend"])

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_batch_native_turbo_optimization",
        fake_native,
        raising=False,
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_continuation_closeout",
        fake_closeout,
    )

    result = optimizer_continuation_flow.continue_local_project(
        project_dir,
        additional_evals=2,
        cadence_cshrc=Path("/cadence/env.csh"),
    )

    assert result.status == "pass"
    assert result.backend == "native_turbo"
    assert captured["native_project"] == project_dir
    assert captured["native_kwargs"] == {
        "max_evals": None,
        "additional_evals": 2,
        "continue_from_existing": True,
        "cadence_cshrc": Path("/cadence/env.csh"),
        "transport_mode": "local",
    }
    closeout_kwargs = captured["closeout_kwargs"]
    assert closeout_kwargs["backend"] == "native_turbo"
    assert closeout_kwargs["run_step_name"] == "run-native-turbo-real"


def test_local_openbox_continuation_keeps_existing_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "assert_valid_project",
        lambda _project, **_kwargs: SimpleNamespace(optimizer=object()),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "_backend_from_project_strategy",
        lambda *_args, **_kwargs: "openbox",
    )

    def fake_openbox(project: Path, **kwargs: object) -> SimpleNamespace:
        captured["project"] = project
        captured["kwargs"] = kwargs
        return SimpleNamespace(evaluation_count=6)

    def fake_closeout(project: Path, **kwargs: object) -> SimpleNamespace:
        captured["closeout"] = kwargs
        kwargs["optimizer_fn"](project)
        return SimpleNamespace(status="pass", backend=kwargs["backend"])

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_openbox_real_optimization",
        fake_openbox,
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_continuation_closeout",
        fake_closeout,
    )

    result = optimizer_continuation_flow.continue_local_project(
        project_dir,
        additional_evals=3,
        cadence_cshrc=Path("/cadence/env.csh"),
    )

    assert result.backend == "openbox"
    assert captured["kwargs"] == {
        "max_evals": None,
        "additional_evals": 3,
        "continue_from_existing": True,
        "batch_size": None,
        "parallel_jobs": None,
        "cadence_cshrc": Path("/cadence/env.csh"),
        "strategy": None,
        "surrogate_type": None,
        "acq_type": None,
        "acq_optimizer_type": None,
        "initial_trials": None,
    }
    closeout_kwargs = captured["closeout"]
    assert closeout_kwargs["backend"] == "openbox"
    assert closeout_kwargs["run_step_name"] == "run-openbox-real"


def test_local_continuation_uses_turbo_algorithm_when_strategy_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = create_generic_project(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_openbox_real_optimization",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("algorithm=turbo must not fall back to OpenBox")
        ),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_batch_native_turbo_optimization",
        lambda *_args, **_kwargs: calls.append("native")
        or SimpleNamespace(evaluation_count=3),
    )

    def fake_closeout(project: Path, **kwargs: object) -> SimpleNamespace:
        kwargs["optimizer_fn"](project)
        return SimpleNamespace(status="pass", backend=kwargs["backend"])

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_continuation_closeout",
        fake_closeout,
    )

    result = optimizer_continuation_flow.continue_local_project(
        project_dir,
        additional_evals=1,
        cadence_cshrc=Path("/cadence/env.csh"),
    )

    assert result.backend == "native_turbo"
    assert calls == ["native"]


@pytest.mark.parametrize("backend", ["openbox", "native_turbo"])
def test_local_continuation_rejects_scientific_drift_before_optimizer_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    project_dir = _write_scientifically_drifted_history(
        tmp_path,
        backend=backend,
    )
    optimizer_calls: list[str] = []
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "_backend_from_project_strategy",
        lambda *_args, **_kwargs: backend,
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_openbox_real_optimization",
        lambda *_args, **_kwargs: optimizer_calls.append("openbox"),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_batch_native_turbo_optimization",
        lambda *_args, **_kwargs: optimizer_calls.append("native_turbo"),
    )

    rejection: RuntimeError | None = None
    try:
        optimizer_continuation_flow.continue_local_project(
            project_dir,
            additional_evals=1,
            cadence_cshrc=Path("/cadence/env.csh"),
        )
    except RuntimeError as exc:
        rejection = exc

    assert optimizer_calls == []
    assert rejection is not None
    assert "prior optimizer history acceptance rejected" in str(rejection)


def test_local_continuation_rejects_fix_run_before_backend_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = create_generic_project(tmp_path, workflow_mode="fix_run")
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "_backend_from_project_strategy",
        lambda *_args, **_kwargs: pytest.fail(
            "fix-run must fail before optimizer backend dispatch"
        ),
    )

    with pytest.raises(
        ValueError,
        match="continuation requires an optimize workflow",
    ):
        optimizer_continuation_flow.continue_local_project(
            project_dir,
            additional_evals=1,
            cadence_cshrc=Path("/cadence/env.csh"),
        )
def test_local_continuation_preflights_model_files_on_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fail_preflight(project_dir: Path, **kwargs: object) -> object:
        captured.update(kwargs)
        raise ValueError("local model preflight failed")

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "assert_valid_project",
        fail_preflight,
    )

    with pytest.raises(ValueError, match="local model preflight failed"):
        optimizer_continuation_flow.continue_local_project(
            tmp_path,
            additional_evals=1,
            cadence_cshrc=tmp_path / "cadence.csh",
        )

    assert captured["model_file_is_readable"] is local_model_file_is_readable
