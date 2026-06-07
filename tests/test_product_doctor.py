from pathlib import Path
from types import SimpleNamespace

from hermes_workflow.product_doctor import ProductDoctorServices, run_product_doctor


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
        check.name == "toolchain_environment" and check.status == "fail"
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
