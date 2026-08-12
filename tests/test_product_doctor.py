import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_workflow.product_doctor import ProductDoctorServices, run_product_doctor


NATIVE_VARIABLES = [
    {"name": "FN", "kind": "integer", "lower": "2", "upper": "12", "step": "1"},
    {
        "name": "WN",
        "kind": "continuous_step",
        "lower": "0.3u",
        "upper": "3u",
        "step": "0.2u",
    },
    {"name": "FP", "kind": "integer", "lower": "2", "upper": "12", "step": "1"},
    {
        "name": "WP",
        "kind": "continuous_step",
        "lower": "0.3u",
        "upper": "3u",
        "step": "0.2u",
    },
]


def _passing_controller_optimizer_runtime(
    *_args: object,
    **_kwargs: object,
) -> dict[str, object]:
    return {
        "status": "pass",
        "resolved_backend": "openbox",
        "detail": "test runtime passed",
        "issues": [],
    }


def test_product_doctor_passes_with_warning_before_first_run(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_controller_optimizer_runtime=_passing_controller_optimizer_runtime,
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert (project_dir / "reports" / "ic_opt_doctor_report.json").exists()
    assert [check.status for check in report.checks if check.name == "continuation_artifacts"] == [
        "warning"
    ]
    assert "no optimizer history yet" in report.warnings[0]


def test_product_doctor_checks_resolved_optimizer_runtime_in_controller_process(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    runtime_calls: list[tuple[dict[str, object], str]] = []
    sections: dict[str, object] = {
        "Optimizer Settings": {
            "algorithm": "turbo",
            "strategy": "turbo_trust_region",
            "initialization": "sobol",
            "max_evaluations": 10,
        },
        "Design Variables": NATIVE_VARIABLES,
    }

    def check_runtime(
        requirement_sections: dict[str, object],
        *,
        workflow_mode: str,
    ) -> dict[str, object]:
        runtime_calls.append((requirement_sections, workflow_mode))
        return {
            "status": "pass",
            "resolved_backend": "native_turbo",
            "detail": "native dependencies passed",
            "issues": [],
        }

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass",
            issues=[],
            sections=sections,
            workflow_mode="optimize",
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[]
        ),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_controller_optimizer_runtime=check_runtime,
        check_toolchain_environment=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy subprocess toolchain probe must not run")
        ),
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        services=services,
    )

    assert report.status == "pass"
    assert runtime_calls == [(sections, "optimize")]
    assert any(
        check.name == "controller_optimizer_runtime"
        and check.status == "pass"
        and check.detail == "native dependencies passed"
        for check in report.checks
    )


def test_product_doctor_fails_when_controller_optimizer_runtime_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass",
            issues=[],
            sections={
                "Optimizer Settings": {
                    "algorithm": "turbo",
                    "strategy": "turbo_trust_region",
                    "initialization": "sobol",
                    "max_evaluations": 10,
                },
                "Design Variables": NATIVE_VARIABLES,
            },
            workflow_mode="optimize",
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[]
        ),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_controller_optimizer_runtime=lambda *_args, **_kwargs: {
            "status": "fail",
            "resolved_backend": "native_turbo",
            "detail": "gpytorch import failed",
            "issues": ["gpytorch import failed"],
        },
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        services=services,
    )

    assert report.status == "fail"
    assert any(
        check.name == "controller_optimizer_runtime" and check.status == "fail"
        for check in report.checks
    )
    diagnostic = next(
        issue
        for issue in report.structured_issues
        if issue.code == "CONTROLLER_OPTIMIZER_RUNTIME_UNAVAILABLE"
    )
    assert diagnostic.detail == "gpytorch import failed"


def test_product_doctor_marks_fix_run_optimizer_runtime_skipped(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass",
            issues=[],
            sections={"Workflow": {"schema_version": "1.0", "mode": "fix_run"}},
            workflow_mode="fix_run",
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[]
        ),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        services=services,
    )

    runtime_check = next(
        check for check in report.checks if check.name == "controller_optimizer_runtime"
    )
    assert report.status == "pass"
    assert runtime_check.status == "skipped"
    assert "does not use an optimizer" in runtime_check.detail


def test_product_doctor_reports_missing_cadence_without_toolchain_probe(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    toolchain_calls: list[bool] = []

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: toolchain_calls.append(True),
        check_controller_optimizer_runtime=_passing_controller_optimizer_runtime,
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=None,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "fail"
    assert toolchain_calls == []
    assert any(check.name == "cadence_cshrc" and check.status == "fail" for check in report.checks)
    assert any(
        check.name == "controller_optimizer_runtime" and check.status == "pass"
        for check in report.checks
    )


def test_product_doctor_requires_state_when_optimizer_history_exists(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "optimizer_run_report.json").write_text("{}\n", encoding="utf-8")
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_controller_optimizer_runtime=_passing_controller_optimizer_runtime,
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "fail"
    assert any(
        check.name == "continuation_artifacts" and check.status == "fail"
        for check in report.checks
    )


def test_product_doctor_reports_continuation_readiness_when_history_exists(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "reports").mkdir(parents=True)
    (project_dir / "reports" / "optimizer_run_report.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "reports" / "optimizer_evaluations.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "ledger").mkdir()
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "state").mkdir()
    (project_dir / "state" / "optimizer_state.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_controller_optimizer_runtime=_passing_controller_optimizer_runtime,
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert any(
        check.name == "project_ready"
        and check.detail == "ready_for_continuation_or_closeout_review"
        for check in report.checks
    )
    assert any(
        check.name == "continuation_artifacts" and check.status == "pass"
        for check in report.checks
    )


def _native_turbo_product_doctor_services() -> ProductDoctorServices:
    return ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass",
            issues=[],
            sections={
                "Optimizer Settings": {
                    "algorithm": "turbo",
                    "strategy": "turbo_trust_region",
                    "max_evaluations": 10,
                },
                "Design Variables": NATIVE_VARIABLES,
            },
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[]
        ),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {
            "status": "pass",
            "issues": [],
        },
    )


def _valid_native_turbo_trace() -> dict[str, object]:
    return {
        "evaluation_index": 1,
        "run_id": "real_001",
        "selection_phase": "initialization",
        "raw_x": [2.0, 0.3, 2.0, 0.3],
        "parameters": {
            "FN": "2",
            "WN": "0.3u",
            "FP": "2",
            "WP": "0.3u",
        },
        "status": "recorded",
        "objective": 1.0,
        "fom": 1.0,
        "constraint_penalty": 0.0,
        "metrics": {"metric": 1.0},
        "result_manifest": "runs/real/real_001/result_manifest.json",
        "metric_result_manifest": (
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
        "issues": [],
        "batch_id": "batch_001",
        "batch_slot": 1,
        "batch_size": 1,
    }


def _write_product_native_turbo_history(
    project_dir: Path,
    trace: dict[str, object],
) -> None:
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "native_turbo_optimizer_report.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "backend": "native_turbo",
                "evaluation_count": 1,
                "evaluations": (
                    "reports/native_turbo_optimizer_evaluations.jsonl"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        json.dumps(trace) + "\n",
        encoding="utf-8",
    )


def test_product_doctor_recognizes_native_turbo_continuation_history(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    reports_dir = project_dir / "reports"
    _write_product_native_turbo_history(project_dir, _valid_native_turbo_trace())
    (reports_dir / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "backend": "openbox",
                "evaluation_count": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1}\n{"evaluation_index": 2}\n',
        encoding="utf-8",
    )
    (project_dir / "ledger").mkdir()
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "state").mkdir()
    (project_dir / "state" / "optimizer_state.json").write_text(
        json.dumps(
            {
                "current_evaluations": 1,
                "recorded_observation_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    services = _native_turbo_product_doctor_services()

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "native_turbo"
    assert report.optimizer_progress_summary["report_evaluation_count"] == 1
    assert report.dirty_state["has_optimizer_run_report"] is True
    assert report.dirty_state["has_optimizer_evaluations"] is True
    assert any(
        check.name == "project_ready"
        and check.detail == "ready_for_continuation_or_closeout_review"
        for check in report.checks
    )
    assert any(
        check.name == "continuation_artifacts" and check.status == "pass"
        for check in report.checks
    )
    assert not any("no optimizer history yet" in warning for warning in report.warnings)


def test_product_doctor_rejects_invalid_native_turbo_trace_schema(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "native_turbo_optimizer_report.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "backend": "native_turbo",
                "evaluation_count": 1,
                "evaluations": (
                    "reports/native_turbo_optimizer_evaluations.jsonl"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "native_turbo_optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1, "status": "recorded"}\n',
        encoding="utf-8",
    )
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=_native_turbo_product_doctor_services(),
    )

    assert report.status == "fail"
    invalid = next(
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert "evaluation line 1 is invalid" in (invalid.detail or "")


@pytest.mark.parametrize(
    ("invalid_case", "expected_detail"),
    [
        ("raw_x_dimension", "raw_x dimension mismatch"),
        ("parameter_names", "parameters mismatch"),
        ("quantized_values", "raw_x/parameters mismatch"),
    ],
)
def test_product_doctor_rejects_native_history_with_invalid_variable_semantics(
    tmp_path: Path,
    invalid_case: str,
    expected_detail: str,
) -> None:
    project_dir = tmp_path / "project"
    trace = _valid_native_turbo_trace()
    if invalid_case == "raw_x_dimension":
        trace["raw_x"] = [2.0, 0.3, 2.0]
    elif invalid_case == "parameter_names":
        parameters = dict(trace["parameters"])
        parameters["UNKNOWN"] = parameters.pop("WP")
        trace["parameters"] = parameters
    elif invalid_case == "quantized_values":
        parameters = dict(trace["parameters"])
        parameters["WN"] = "0.5u"
        trace["parameters"] = parameters
    else:  # pragma: no cover - parameter table is closed above
        raise AssertionError(invalid_case)
    _write_product_native_turbo_history(project_dir, trace)
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=_native_turbo_product_doctor_services(),
    )

    assert report.status == "fail"
    invalid = next(
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert expected_detail in (invalid.detail or "")


def test_product_doctor_random_baseline_uses_openbox_artifact_contract(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "backend": "openbox",
                "evaluation_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1}\n',
        encoding="utf-8",
    )
    (project_dir / "ledger").mkdir()
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_dir / "state").mkdir()
    (project_dir / "state" / "optimizer_state.json").write_text(
        json.dumps(
            {
                "current_evaluations": 1,
                "recorded_observation_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass",
            issues=[],
            sections={
                "Optimizer Settings": {
                    "algorithm": "random",
                    "strategy": "random_baseline",
                    "max_evaluations": 10,
                },
                "Design Variables": [{"name": "x"}],
            },
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[]
        ),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {
            "status": "pass",
            "issues": [],
        },
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "random_baseline"
    assert report.optimizer_progress_summary["report_evaluation_count"] == 1
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 1


def _multi_corner_sections() -> dict[str, object]:
    return {
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
                {"id": "ff"},
            ],
        },
        "Spectre Settings": {
            "parallel_jobs": 4,
            "threads_per_run": 8,
        },
        "Optimizer Settings": {
            "algorithm": "openbox",
            "strategy": "openbox_prf_eic",
            "max_evaluations": 80,
            "optimizer_cpu_threads": 4,
        },
        "Design Variables": [
            {"name": "v1"},
            {"name": "v2"},
        ],
    }


def test_product_doctor_attaches_unified_summaries(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["transport"]["mode"] == "local"
    assert payload["transport"]["ssh_profile"] is None
    assert payload["requirement_summary"]["corner_count"] == 3
    assert payload["requirement_summary"]["testbench_count"] == 2
    assert payload["requirement_summary"]["objective_policy"] == "worst_case"
    assert payload["requirement_summary"]["constraint_policy"] == "all_corners"
    assert payload["evaluation_matrix"]["child_runs_per_candidate"] == 6
    assert payload["evaluation_matrix"]["inside_candidate_execution"] == "serial"
    assert payload["evaluation_matrix"]["candidate_parallelism"] == 4
    assert payload["optimizer_summary"]["requested_strategy"] == "openbox_prf_eic"
    assert payload["optimizer_summary"]["max_evaluations_source"] == "config"
    assert payload["optimizer_summary"]["max_evaluations"] == 80
    assert payload["resource_summary"]["parallel_jobs"] == 4
    assert payload["resource_summary"]["threads_per_run"] == 8
    assert payload["resource_summary"]["optimizer_cpu_threads"] == 4
    assert payload["dirty_state"]["has_execution_package"] is False
    assert payload["dirty_state"]["has_runs"] is False
    assert report.status == "pass"


def test_product_doctor_warns_about_incomplete_real_run(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "runs" / "real" / "real_001").mkdir(parents=True)
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["dirty_state"]["has_runs"] is True
    assert payload["dirty_state"]["has_incomplete_real_run"] is True
    assert any(
        item["code"] == "INCOMPLETE_REAL_RUN" for item in payload["structured_issues"]
    )
    assert report.status == "pass"


def test_product_doctor_does_not_warn_for_completed_candidate_real_run(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = project_dir / "runs" / "real" / "real_001"
    run_dir.mkdir(parents=True)
    (run_dir / "result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"succeeded","run_id":"real_001"}\n',
        encoding="utf-8",
    )
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["dirty_state"]["has_runs"] is True
    assert payload["dirty_state"]["has_incomplete_real_run"] is False
    assert not any(
        item["code"] == "INCOMPLETE_REAL_RUN"
        for item in payload["structured_issues"]
    )
    assert report.status == "pass"


def test_product_doctor_reports_cli_max_evals_override(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
        cli_max_evals=5,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["optimizer_summary"]["max_evaluations"] == 5
    assert payload["optimizer_summary"]["max_evaluations_source"] == "cli"


def test_product_doctor_fails_on_invalid_optimizer_strategy(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()
    sections["Optimizer Settings"] = {
        "algorithm": "openbox",
        "strategy": "openbox_eic",
        "max_evaluations": 80,
    }

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report.status == "fail"
    assert payload["status"] == "fail"
    assert any(
        item["code"] == "OPTIMIZER_STRATEGY_INVALID"
        for item in payload["structured_issues"]
    )


def test_local_doctor_payload_exposes_run_retention_policy(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()
    sections["Spectre Settings"] = {
        "parallel_jobs": 4,
        "threads_per_run": 8,
        "keep_failed_runs": False,
        "keep_successful_runs": True,
    }

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    retention = payload["resource_summary"]["run_retention"]
    assert retention["keep_failed_runs"] is False
    assert retention["keep_successful_runs"] is True
    assert retention["cleanup_scope"] == "runs/real/<run_id>"
    assert retention["decision_reports"] == "state/run_retention/<run_id>.json"


def test_local_doctor_reports_optimizer_progress_summary_in_payload(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _multi_corner_sections()

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
    )

    run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(
            encoding="utf-8"
        )
    )
    progress = payload["optimizer_progress_summary"]
    assert "report_evaluation_count" in progress
    assert "evaluation_trace_count" in progress
    assert "state_current_evaluations" in progress
    assert "state_recorded_observation_count" in progress
    assert "ledger_row_count" in progress


# ── B-05: require_license_check tests ──────────────────────────────────────


def _sections_with_license_check(require: bool = True) -> dict[str, object]:
    sections = _multi_corner_sections()
    sections["Spectre Settings"] = {
        "parallel_jobs": 4,
        "threads_per_run": 8,
        "require_license_check": require,
    }
    return sections


def test_local_doctor_license_probe_pass_when_required_and_ok(
    tmp_path: Path,
) -> None:
    """B-05: require_license_check=true + probe pass → doctor pass, report has license_probe."""
    from hermes_workflow.license_probe import LicenseProbeReport

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _sections_with_license_check(require=True)
    probe_report = LicenseProbeReport(
        status="pass",
        execution_mode="local",
        require_license_check=True,
        spectre_path="/tools/spectre",
    )
    probe_calls: list[Path] = []

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_license=lambda cshrc, **_kw: (probe_calls.append(cshrc), probe_report)[1],
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert any(check.name == "license_probe" and check.status == "pass" for check in report.checks)
    # license_probe_report.json should be written
    assert (project_dir / "reports" / "license_probe_report.json").is_file()
    # Doctor report JSON should include license_probe
    payload = json.loads(
        (project_dir / "reports" / "ic_opt_doctor_report.json").read_text(encoding="utf-8")
    )
    assert "license_probe" in payload
    assert payload["license_probe"]["status"] == "pass"
    # Probe was actually called
    assert len(probe_calls) == 1


def test_local_doctor_license_probe_fail_when_required_and_fail(
    tmp_path: Path,
) -> None:
    """B-05: require_license_check=true + probe fail → doctor fail."""
    from hermes_workflow.license_probe import LicenseProbeReport

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _sections_with_license_check(require=True)
    probe_report = LicenseProbeReport(
        status="fail",
        execution_mode="local",
        require_license_check=True,
        issues=["spectre not found in PATH"],
    )

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_license=lambda cshrc, **_kw: probe_report,
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "fail"
    assert any(check.name == "license_probe" and check.status == "fail" for check in report.checks)
    assert any("license probe" in issue.lower() or "spectre not found" in issue for issue in report.issues)


def test_local_doctor_license_probe_skipped_when_not_required(
    tmp_path: Path,
) -> None:
    """B-05: require_license_check=false → probe skipped, fake probe should NOT be called."""
    from hermes_workflow.license_probe import LicenseProbeReport

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    sections = _sections_with_license_check(require=False)
    probe_calls: list[object] = []

    services = ProductDoctorServices(
        check_requirement=lambda _project: SimpleNamespace(
            status="pass", issues=[], sections=sections
        ),
        prepare_from_requirement=lambda _project: SimpleNamespace(status="pass", issues=[]),
        check_project_ready=lambda _project: SimpleNamespace(
            status="pass",
            readiness="ready_for_first_run",
            warnings=[],
        ),
        check_toolchain_environment=lambda **_kwargs: {"status": "pass", "issues": []},
        check_license=lambda cshrc, **_kw: (probe_calls.append(True), LicenseProbeReport(
            status="fail", execution_mode="local", require_license_check=True,
        ))[1],
    )

    report = run_product_doctor(
        project_dir,
        cadence_cshrc=cadence_cshrc,
        openbox_venv=tmp_path,
        services=services,
    )

    assert report.status == "pass"
    assert any(check.name == "license_probe" and check.status == "skipped" for check in report.checks)
    # The real probe function should NOT have been called
    assert len(probe_calls) == 0
