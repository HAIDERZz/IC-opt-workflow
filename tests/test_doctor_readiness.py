from __future__ import annotations

from pathlib import Path

from hermes_workflow.doctor_readiness import (
    build_dirty_state_summary,
    build_evaluation_matrix_summary,
    build_optimizer_summary,
    build_requirement_summary,
)


def test_requirement_summary_reports_nominal_defaults() -> None:
    summary = build_requirement_summary(
        {
            "Design Variables": [{"name": "W", "lower": "1u", "upper": "10u"}],
            "Metrics": [{"name": "gain"}],
            "Objective": {"expression": "-gain"},
            "Spectre Settings": {"parallel_jobs": 4},
        }
    )
    assert summary["has_process_corners"] is False
    assert summary["corner_count"] == 1
    assert summary["testbench_count"] == 1
    assert summary["child_runs_per_candidate"] == 1
    assert summary["inside_candidate_execution"] == "serial"
    assert summary["objective_policy"] == "nominal"
    assert summary["constraint_policy"] == "nominal"
    assert summary["has_multi_testbench"] is False


def test_requirement_summary_reports_multi_tb_multi_corner_matrix() -> None:
    summary = build_requirement_summary(
        {
            "Maestro Source": {
                "testbenches": [
                    {"id": "gain_tb", "maestro_view": "gain"},
                    {"id": "noise_tb", "maestro_view": "noise"},
                ],
            },
            "Process Corners": {
                "objective_policy": "worst_case",
                "constraint_policy": "all_corners",
                "corners": [
                    {"id": "tt", "model_section": "tt"},
                    {"id": "ss", "model_section": "ss"},
                    {"id": "ff", "model_section": "ff"},
                ],
            },
            "Spectre Settings": {"parallel_jobs": 4},
        }
    )
    assert summary["has_process_corners"] is True
    assert summary["corner_count"] == 3
    assert summary["testbench_count"] == 2
    assert summary["child_runs_per_candidate"] == 6
    assert summary["objective_policy"] == "worst_case"
    assert summary["constraint_policy"] == "all_corners"
    assert summary["has_multi_testbench"] is True


def test_requirement_summary_explicit_single_corner_is_preserved() -> None:
    summary = build_requirement_summary(
        {
            "Process Corners": {
                "objective_policy": "worst_case",
                "constraint_policy": "all_corners",
                "corners": [{"id": "tt", "model_section": "tt"}],
            },
            "Spectre Settings": {"parallel_jobs": 2},
        }
    )
    assert summary["has_process_corners"] is True
    assert summary["corner_count"] == 1
    assert summary["testbench_count"] == 1
    assert summary["child_runs_per_candidate"] == 1


def test_evaluation_matrix_summary_uses_parallel_jobs() -> None:
    summary = build_evaluation_matrix_summary(
        {
            "Maestro Source": {
                "testbenches": [
                    {"id": "tb1"},
                    {"id": "tb2"},
                ],
            },
            "Process Corners": {
                "objective_policy": "worst_case",
                "constraint_policy": "all_corners",
                "corners": [
                    {"id": "tt"},
                    {"id": "ss"},
                ],
            },
            "Spectre Settings": {"parallel_jobs": 4},
        }
    )
    assert summary["candidate_parallelism"] == 4
    assert summary["testbench_count"] == 2
    assert summary["corner_count"] == 2
    assert summary["child_runs_per_candidate"] == 4
    assert summary["inside_candidate_execution"] == "serial"


def test_optimizer_summary_resolves_prf_eic_strategy() -> None:
    summary = build_optimizer_summary(
        optimizer_section={
            "algorithm": "openbox",
            "strategy": "openbox_prf_eic",
            "max_evaluations": 80,
        },
        variable_count=11,
        cli_max_evals=None,
    )
    assert summary["algorithm"] == "openbox"
    assert summary["requested_strategy"] == "openbox_prf_eic"
    assert summary["resolved_backend"] == "openbox"
    assert summary["surrogate_type"] == "prf"
    assert summary["acq_type"] == "eic"
    assert summary["acq_optimizer_type"] == "local_random"
    assert summary["initial_trials"] == 22
    assert summary["max_evaluations"] == 80
    assert summary["max_evaluations_source"] == "config"


def test_optimizer_summary_reports_cli_budget_override() -> None:
    summary = build_optimizer_summary(
        optimizer_section={"algorithm": "openbox", "max_evaluations": 80},
        variable_count=4,
        cli_max_evals=3,
    )
    assert summary["max_evaluations"] == 3
    assert summary["max_evaluations_source"] == "cli"


def test_optimizer_summary_reports_default_when_no_budget_value() -> None:
    summary = build_optimizer_summary(
        optimizer_section={"algorithm": "openbox"},
        variable_count=4,
        cli_max_evals=None,
    )
    assert summary["max_evaluations"] is None
    assert summary["max_evaluations_source"] == "default"


def test_optimizer_summary_resolves_turbo_trust_region() -> None:
    summary = build_optimizer_summary(
        optimizer_section={
            "algorithm": "turbo",
            "strategy": "turbo_trust_region",
            "max_evaluations": 40,
        },
        variable_count=5,
        cli_max_evals=None,
    )
    assert summary["algorithm"] == "turbo"
    assert summary["requested_strategy"] == "turbo_trust_region"
    assert summary["resolved_backend"] == "native_turbo"


def test_optimizer_summary_resolves_random_baseline() -> None:
    summary = build_optimizer_summary(
        optimizer_section={
            "algorithm": "random",
            "strategy": "random_baseline",
            "max_evaluations": 25,
        },
        variable_count=3,
        cli_max_evals=None,
    )
    assert summary["algorithm"] == "random"
    assert summary["requested_strategy"] == "random_baseline"
    assert summary["resolved_backend"] == "random_baseline"


def test_optimizer_summary_rejects_invalid_strategy_alias() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_optimizer_summary(
            optimizer_section={"algorithm": "openbox", "strategy": "openbox_eic"},
            variable_count=5,
            cli_max_evals=None,
        )


def test_dirty_state_warns_on_incomplete_real_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "runs" / "real" / "real_001").mkdir(parents=True)
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is True
    assert any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_reports_optimizer_history(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "state").mkdir(parents=True)
    (project / "state" / "optimizer_state.json").write_text("{}", encoding="utf-8")
    (project / "reports").mkdir(parents=True)
    (project / "reports" / "optimizer_evaluations.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_optimizer_state"] is True
    assert summary["has_optimizer_evaluations"] is True
    assert diagnostics == []


def test_dirty_state_pass_for_completed_real_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run_dir = project / "runs" / "real" / "real_001"
    (run_dir / "reports").mkdir(parents=True)
    (run_dir / "reports" / "optimizer_run_report.json").write_text(
        "{}", encoding="utf-8"
    )
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert diagnostics == []


def test_dirty_state_does_not_warn_for_completed_candidate_run(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    run.mkdir(parents=True)
    (run / "candidate_request.json").write_text("{}", encoding="utf-8")
    (run / "result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"succeeded","run_id":"real_001"}\n',
        encoding="utf-8",
    )

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert not any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_does_not_warn_for_completed_multi_corner_candidate_run(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    run.mkdir(parents=True)
    (run / "result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"succeeded","run_id":"real_001"}\n',
        encoding="utf-8",
    )
    child_corner = run / "testbenches" / "cg_nf" / "corners" / "tt"
    child_corner.mkdir(parents=True)
    (child_corner / "result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"succeeded"}\n',
        encoding="utf-8",
    )

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert not any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_does_not_warn_when_only_metric_result_manifest_exists(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    metrics_dir = run / "metrics"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "metric_result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"failed"}\n',
        encoding="utf-8",
    )

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert not any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_warns_for_started_candidate_without_result_manifest(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    run.mkdir(parents=True)
    (run / "candidate_request.json").write_text("{}", encoding="utf-8")

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_incomplete_real_run"] is True
    incomplete = [d for d in diagnostics if d.code == "INCOMPLETE_REAL_RUN"]
    assert len(incomplete) == 1


def test_dirty_state_still_warns_for_empty_run_dir(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "runs" / "real" / "real_001").mkdir(parents=True)

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is True
    assert any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_detects_execution_package(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "execution_package").mkdir(parents=True)
    summary, _ = build_dirty_state_summary(project)
    assert summary["has_execution_package"] is True


def test_dirty_state_clean_project_has_no_dirty_flags(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_runs"] is False
    assert summary["has_incomplete_real_run"] is False
    assert summary["has_execution_package"] is False
    assert summary["has_optimizer_state"] is False
    assert summary["has_optimizer_evaluations"] is False
    assert diagnostics == []


def test_doctor_semantic_summaries_emits_diagnostic_on_invalid_strategy() -> None:
    from hermes_workflow.diagnostics import DiagnosticSeverity
    from hermes_workflow.doctor_readiness import build_doctor_semantic_summaries

    sections = {
        "Spectre Settings": {"parallel_jobs": 4},
        "Optimizer Settings": {
            "algorithm": "openbox",
            "strategy": "openbox_eic",
        },
        "Design Variables": [{"name": "v"}],
    }
    _, _, optimizer_summary, _, diagnostics = build_doctor_semantic_summaries(
        sections, cli_max_evals=None
    )
    assert optimizer_summary == {}
    assert any(
        d.code == "OPTIMIZER_STRATEGY_INVALID"
        and d.severity is DiagnosticSeverity.ERROR
        for d in diagnostics
    )


def test_doctor_semantic_summaries_returns_empty_for_no_sections() -> None:
    from hermes_workflow.doctor_readiness import build_doctor_semantic_summaries

    req, matrix, opt, res, diags = build_doctor_semantic_summaries(
        {}, cli_max_evals=None
    )
    assert (req, matrix, opt, res, diags) == ({}, {}, {}, {}, [])


def test_resource_summary_includes_run_retention_policy_from_spectre_settings() -> None:
    from hermes_workflow.doctor_readiness import build_resource_summary

    summary = build_resource_summary(
        spectre_section={
            "parallel_jobs": 4,
            "threads_per_run": 8,
            "keep_failed_runs": False,
            "keep_successful_runs": True,
        },
        optimizer_section={"optimizer_cpu_threads": 2},
    )

    retention = summary["run_retention"]
    assert retention["keep_failed_runs"] is False
    assert retention["keep_successful_runs"] is True
    assert retention["cleanup_scope"] == "runs/real/<run_id>"
    assert retention["decision_reports"] == "state/run_retention/<run_id>.json"


def _write_optimizer_artifacts_for_progress_summary(
    project_dir: Path,
    *,
    report_evaluation_count: int,
    trace_count: int,
    state_current_evaluations: int | None,
    state_recorded_observation_count: int | None,
    ledger_row_count: int,
) -> None:
    import json as _json

    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "optimizer_run_report.json").write_text(
        _json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "evaluation_count": report_evaluation_count,
                "issues": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (reports_dir / "optimizer_evaluations.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for index in range(trace_count):
            handle.write(
                _json.dumps({"evaluation_index": index + 1, "status": "constraint_failed"})
                + "\n"
            )
    if state_current_evaluations is not None:
        state_dir = project_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "optimizer_state.json").write_text(
            _json.dumps(
                {
                    "schema_version": "1.0",
                    "project_name": "bridge_test_inv",
                    "algorithm": "openbox",
                    "initialization": "lhs",
                    "current_evaluations": state_current_evaluations,
                    "max_evaluations": 10,
                    "batch_size": 2,
                    "random_seed": 7,
                    "best_candidate_id": None,
                    "status": "running",
                    "started_at_utc": "2026-06-14T00:00:00Z",
                    "updated_at_utc": "2026-06-14T00:00:00Z",
                    "recorded_observation_count": state_recorded_observation_count,
                    "failed_evaluation_count": (
                        report_evaluation_count - (state_recorded_observation_count or 0)
                    ),
                    "status_counts": {"constraint_failed": trace_count},
                    "progress_source": "reports/optimizer_evaluations.jsonl",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    ledger_dir = project_dir / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with (ledger_dir / "experiment_ledger.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for index in range(ledger_row_count):
            handle.write(
                _json.dumps({"candidate_id": f"real_{index + 1:03d}"}) + "\n"
            )


def test_build_optimizer_progress_summary_emits_mismatch_when_state_disagrees_with_report(
    tmp_path: Path,
) -> None:
    from hermes_workflow.doctor_readiness import build_optimizer_progress_summary

    project = tmp_path / "project"
    project.mkdir()
    _write_optimizer_artifacts_for_progress_summary(
        project,
        report_evaluation_count=10,
        trace_count=10,
        state_current_evaluations=7,
        state_recorded_observation_count=7,
        ledger_row_count=7,
    )
    summary, diagnostics = build_optimizer_progress_summary(project)
    assert summary["report_evaluation_count"] == 10
    assert summary["evaluation_trace_count"] == 10
    assert summary["state_current_evaluations"] == 7
    assert summary["state_recorded_observation_count"] == 7
    assert summary["ledger_row_count"] == 7
    mismatch = [d for d in diagnostics if d.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH"]
    assert len(mismatch) == 1
    assert "report=10" in (mismatch[0].detail or "")
    assert "state.current_evaluations=7" in (mismatch[0].detail or "")


def test_build_optimizer_progress_summary_no_mismatch_when_artifacts_agree(
    tmp_path: Path,
) -> None:
    from hermes_workflow.doctor_readiness import build_optimizer_progress_summary

    project = tmp_path / "project"
    project.mkdir()
    _write_optimizer_artifacts_for_progress_summary(
        project,
        report_evaluation_count=10,
        trace_count=10,
        state_current_evaluations=10,
        state_recorded_observation_count=7,
        ledger_row_count=7,
    )
    summary, diagnostics = build_optimizer_progress_summary(project)
    assert summary["report_evaluation_count"] == 10
    assert summary["state_current_evaluations"] == 10
    assert not any(
        d.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH" for d in diagnostics
    )


def test_build_optimizer_progress_summary_silent_when_no_artifacts_yet(
    tmp_path: Path,
) -> None:
    from hermes_workflow.doctor_readiness import build_optimizer_progress_summary

    project = tmp_path / "project"
    project.mkdir()
    summary, diagnostics = build_optimizer_progress_summary(project)
    assert summary["report_evaluation_count"] is None
    assert summary["evaluation_trace_count"] == 0
    assert summary["state_current_evaluations"] is None
    assert summary["ledger_row_count"] == 0
    assert not any(
        d.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH" for d in diagnostics
    )
