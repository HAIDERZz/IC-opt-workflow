import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow import __version__
from hermes_workflow.cli import app
from tests.report_helpers import write_pass_reports


runner = CliRunner()


def test_cli_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--max-evals", "1"),
        ("--batch-size", "1"),
        ("--parallel-jobs", "1"),
    ],
)
def test_optimize_command_rejects_cli_workload_resource_overrides(
    tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "optimize",
            str(project_dir),
            "--real",
            "--dry-orchestration",
            "--cadence-cshrc",
            str(cadence_cshrc),
            flag,
            value,
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--max-evals", "1"),
        ("--batch-size", "1"),
        ("--parallel-jobs", "1"),
    ],
)
def test_run_openbox_real_rejects_cli_workload_resource_overrides(
    tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "run-openbox-real",
            str(project_dir),
            flag,
            value,
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_run_native_turbo_rejects_cli_max_evals_override(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "run-native-turbo",
            str(project_dir),
            "--max-evals",
            "1",
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--max-evals", "1"),
        ("--batch-size", "1"),
    ],
)
def test_run_openbox_fake_rejects_cli_workload_overrides(
    tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "run-openbox-fake",
            str(project_dir),
            flag,
            value,
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--additional-evals", "1"),
        ("--batch-size", "1"),
        ("--parallel-jobs", "1"),
    ],
)
def test_continue_openbox_real_rejects_cli_workload_resource_overrides(
    tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "continue-openbox-real",
            str(project_dir),
            flag,
            value,
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--max-evals", "1"),
        ("--additional-evals", "1"),
    ],
)
def test_package_optimizer_task_rejects_cli_workload_overrides(
    tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "package-optimizer-task",
            str(project_dir),
            "--cadence-cshrc",
            str(cadence_cshrc),
            flag,
            value,
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_cli_init_and_validate(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"

    init_result = runner.invoke(app, ["init", str(project_dir)])
    validate_result = runner.invoke(app, ["validate", str(project_dir)])

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "validation passed" in validate_result.stdout


def test_cli_package_and_approve(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    init_result = runner.invoke(app, ["init", str(project_dir)])
    assert init_result.exit_code == 0

    package_result = runner.invoke(app, ["package", str(project_dir)])
    write_pass_reports(project_dir)
    approve_result = runner.invoke(app, ["approve", str(project_dir)])

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert package_result.exit_code == 0
    assert "execution_package/execution_manifest.json" in package_result.stdout
    assert approve_result.exit_code == 0
    assert instruction["decision"] == "approve_first_real_run"


def test_cli_package_reports_domain_error_without_traceback(tmp_path: Path) -> None:
    missing_project = tmp_path / "missing"

    result = runner.invoke(app, ["package", str(missing_project)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "required config file is missing" in result.stdout
    assert "Traceback" not in result.output


def test_cli_init_reports_template_error_without_traceback(tmp_path: Path) -> None:
    file_destination = tmp_path / "bridge_test_inv"
    file_destination.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(app, ["init", str(file_destination)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "destination exists and is not a directory" in result.stdout
    assert "Traceback" not in result.output


def test_cli_approve_reports_malformed_preflight_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    runner.invoke(app, ["package", str(project_dir)])
    write_pass_reports(project_dir)
    (project_dir / "reports" / "dry_run_report.json").write_text(
        "{",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["approve", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Expecting property name enclosed in double quotes" in result.stdout
    assert "Traceback" not in result.output


def test_cli_mock_run_produces_artifacts(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["mock-run", str(project_dir), "--max-evaluations", "4"])

    assert result.exit_code == 0
    assert "mock optimization completed" in result.stdout
    assert (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert (project_dir / "state" / "optimizer_state.json").exists()
    assert (project_dir / "state" / "best_candidate.json").exists()
    assert (project_dir / "state" / "health_check.json").exists()


def test_cli_mock_run_reports_domain_error_without_traceback(tmp_path: Path) -> None:
    missing_project = tmp_path / "missing"

    result = runner.invoke(app, ["mock-run", str(missing_project)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output


def test_cli_prepare_netlist_writes_template_and_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-netlist", str(project_dir)])

    assert result.exit_code == 0
    assert "netlist preparation passed" in result.stdout
    assert (project_dir / "netlists" / "templates" / "template.scs").exists()
    assert (project_dir / "reports" / "netlist_preparation_report.json").exists()


def test_cli_prepare_netlist_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["prepare-netlist", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "netlist preparation failed" in result.stdout
    assert "exported input.scs is missing" in result.stdout
    assert "reports/netlist_preparation_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_cli_dry_run_writes_candidate_and_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["dry-run", str(project_dir)])

    assert result.exit_code == 0
    assert "dry run passed" in result.stdout
    assert (project_dir / "runs" / "dry_run" / "input.scs").exists()
    assert (project_dir / "reports" / "dry_run_report.json").exists()


def test_cli_dry_run_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["dry-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "dry run failed" in result.stdout
    assert "template.scs is missing: netlists/templates/template.scs" in result.stdout
    assert "reports/dry_run_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_cli_preflight_health_writes_health_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["preflight-health", str(project_dir)])

    payload = json.loads(
        (project_dir / "state" / "health_check.json").read_text(encoding="utf-8")
    )
    assert result.exit_code == 0
    assert "preflight health passed" in result.stdout
    assert payload["status"] == "healthy"
    assert payload["real_run_started"] is False


def test_cli_preflight_health_reports_real_run_artifacts_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    (project_dir / "state" / "optimizer_state.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["preflight-health", str(project_dir)])

    payload = json.loads(
        (project_dir / "state" / "health_check.json").read_text(encoding="utf-8")
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "preflight health failed" in result.stdout
    assert "pre-approval real-run artifact exists: state/optimizer_state.json" in result.stdout
    assert "report: state/health_check.json" in result.stdout
    assert "Traceback" not in result.output
    assert payload["status"] == "error"
    assert payload["real_run_started"] is True


def test_cli_approve_help_uses_generic_preflight_language() -> None:
    result = runner.invoke(app, ["approve", "--help"])

    assert result.exit_code == 0
    assert "Project directory with preflight reports" in result.stdout
    assert "Claude preflight reports" not in result.stdout


def test_cli_preapproval_flow_can_approve_without_real_execution(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )

    prepare_result = runner.invoke(app, ["prepare-netlist", str(project_dir)])
    dry_run_result = runner.invoke(app, ["dry-run", str(project_dir)])
    health_result = runner.invoke(app, ["preflight-health", str(project_dir)])
    approve_result = runner.invoke(app, ["approve", str(project_dir)])

    assert prepare_result.exit_code == 0
    assert dry_run_result.exit_code == 0
    assert health_result.exit_code == 0
    assert approve_result.exit_code == 0

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert instruction["decision"] == "approve_first_real_run"
    assert instruction["reason"] == "config validation and preflight reports passed"
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_cli_prepare_real_run_writes_package_after_approval(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-netlist", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["dry-run", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["preflight-health", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    manifest_path = (
        project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json"
    )
    assert result.exit_code == 0
    assert "real run package prepared" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "manifest: runs/real/real_001/real_run_manifest.json" in result.stdout
    assert manifest_path.exists()
    assert (project_dir / "runs" / "real" / "real_001" / "netlist" / "input.scs").exists()


def test_cli_prepare_real_run_reports_missing_approval_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "supervisor instruction is missing" in result.stdout
    assert "Traceback" not in result.output


def test_cli_prepare_real_run_reports_config_drift_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-netlist", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["dry-run", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["preflight-health", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    variables_path = project_dir / "config" / "variables.yaml"
    variables_path.write_text(
        variables_path.read_text(encoding="utf-8").replace(
            'upper: "12"', 'upper: "14"', 1
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "immutable config drift detected: config/variables.yaml" in result.stdout
    assert "Traceback" not in result.output


def _prepare_cli_real_run(project_dir: Path) -> None:
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-netlist", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["dry-run", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["preflight-health", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0


def _write_cli_result_manifest(project_dir: Path) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spectre.log").write_text("sanitized spectre log\n", encoding="utf-8")
    (artifacts_dir / "psf_summary.txt").write_text(
        "sanitized artifact summary\n",
        encoding="utf-8",
    )
    prepared_manifest = json.loads(
        (run_dir / "real_run_manifest.json").read_text(encoding="utf-8")
    )
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": prepared_manifest["candidate_id"],
        "status": "succeeded",
        "started_at_utc": "2026-06-01T00:30:00Z",
        "completed_at_utc": "2026-06-01T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared_manifest["rendered_input_scs"],
        "prepared_input_sha256": prepared_manifest["rendered_input_sha256"],
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": ["runs/real/real_001/artifacts/psf_summary.txt"],
    }
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_cli_check_real_run_reports_success(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    _prepare_cli_real_run(project_dir)
    _write_cli_result_manifest(project_dir)

    result = runner.invoke(app, ["check-real-run", str(project_dir)])

    assert result.exit_code == 0
    assert "real run handoff check passed" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "result: runs/real/real_001/result_manifest.json" in result.stdout
    assert "report: reports/real_run_check_report.json" in result.stdout
    assert (project_dir / "reports" / "real_run_check_report.json").exists()


def test_cli_check_real_run_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    _prepare_cli_real_run(project_dir)

    result = runner.invoke(app, ["check-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "real run handoff check failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/real_run_check_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_cli_check_metric_results_passes_for_valid_fake_ocean_results(
    tmp_path: Path,
) -> None:
    from tests.test_metric_results import (
        TEMPLATE_TEXT,
        _load_json,
        _write_metric_result_manifest,
        _write_result_manifest,
    )

    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    write_pass_reports(project_dir)
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    result = runner.invoke(app, ["check-metric-results", str(project_dir)])

    assert result.exit_code == 0
    assert "metric result check passed" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "report: reports/metric_result_check_report.json" in result.stdout
    report = _load_json(project_dir / "reports" / "metric_result_check_report.json")
    assert report["status"] == "pass"


def test_cli_check_metric_results_reports_failure_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    write_pass_reports(project_dir)
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\n"
        "parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0

    result = runner.invoke(app, ["check-metric-results", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "metric result check failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/metric_result_check_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_cli_record_real_result_passes_for_valid_checked_result(
    tmp_path: Path,
) -> None:
    from tests.test_real_result_record import (
        _create_ready_project,
        _write_valid_checked_result,
    )

    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(project_dir)

    result = runner.invoke(
        app,
        ["record-real-result", str(project_dir), "--run-id", "real_001"],
    )

    assert result.exit_code == 0
    assert "real result recorded" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "ledger: ledger/experiment_ledger.jsonl" in result.stdout
    assert "state: state/optimizer_state.json" in result.stdout
    assert "report: reports/real_result_record_report.json" in result.stdout


def test_cli_record_real_result_reports_failure_without_traceback(
    tmp_path: Path,
) -> None:
    from tests.test_real_result_record import _create_ready_project

    project_dir = _create_ready_project(tmp_path)

    result = runner.invoke(app, ["record-real-result", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "real result record failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/real_result_record_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_run_openbox_fake_cli_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    import hermes_workflow.cli as cli_module

    project_dir = tmp_path / "bridge_test_inv"

    class FakeResult:
        evaluation_count = 4
        report_path = project_dir / "reports" / "optimizer_run_report.json"
        evaluations_path = project_dir / "reports" / "optimizer_evaluations.jsonl"

    seen: dict[str, int | None] = {}

    def fake_run(project_dir: Path, *, max_evals: int | None, batch_size: int | None) -> FakeResult:
        seen["max_evals"] = max_evals
        seen["batch_size"] = batch_size
        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "optimizer_run_report.json").write_text(
            json.dumps(
                {
                    "backend": "openbox",
                    "best_candidate": None,
                    "batch_summary": {
                        "batch_count": 0,
                        "max_batch_worker_count": batch_size,
                        "status_counts": {},
                    },
                    "evaluation_count": max_evals,
                    "evaluations": "reports/optimizer_evaluations.jsonl",
                    "execution_mode": "fake",
                    "issues": [],
                    "schema_version": "1.0",
                    "status": "completed",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (reports_dir / "optimizer_evaluations.jsonl").write_text("", encoding="utf-8")
        return FakeResult()

    monkeypatch.setattr(cli_module, "run_openbox_fake_optimization", fake_run)

    result = runner.invoke(
        cli_module.app,
        [
            "run-openbox-fake",
            str(project_dir),
        ],
    )

    assert result.exit_code == 0
    assert seen == {"max_evals": None, "batch_size": None}
    assert "openbox fake optimizer completed: 4 evaluations" in result.output
    assert "report: reports/optimizer_run_report.json" in result.output
    assert "evaluations: reports/optimizer_evaluations.jsonl" in result.output


def test_cli_assess_real_run_recovery_reports_pending(tmp_path: Path) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)

    result = runner.invoke(
        app,
        ["assess-real-run-recovery", str(project_dir), "--run-id", "real_001"],
    )

    assert result.exit_code == 0
    assert "real run recovery assessed" in result.output
    assert "classification: pending_execution" in result.output
    assert "report: reports/real_run_recovery_report.json" in result.output


def test_cli_assess_real_run_recovery_reports_failure_without_traceback(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)
    (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    ).unlink()

    result = runner.invoke(
        app,
        ["assess-real-run-recovery", str(project_dir), "--run-id", "real_001"],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "real run recovery assessed" in result.output
    assert "classification: contract_invalid" in result.output
    assert "metric extraction request is missing" in result.output
    assert "report: reports/real_run_recovery_report.json" in result.output
    assert "Traceback" not in result.output


def test_cli_resolve_real_run_failure_writes_abandon_decision(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project, _write_result_manifest

    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    result = runner.invoke(
        app,
        [
            "resolve-real-run-failure",
            str(project_dir),
            "--run-id",
            "real_001",
            "--decision",
            "abandon_candidate",
            "--reason",
            "skip failed candidate",
        ],
    )

    assert result.exit_code == 0
    assert "real run failure resolved" in result.output
    assert "decision: abandon_candidate" in result.output


def test_cli_prepare_real_run_retry_outputs_paths(tmp_path: Path) -> None:
    from tests.test_real_run_recovery import _create_ready_project, _write_result_manifest

    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    result = runner.invoke(
        app,
        [
            "prepare-real-run-retry",
            str(project_dir),
            "--failed-run-id",
            "real_001",
            "--retry-run-id",
            "real_002",
            "--reason",
            "retry failed simulation",
        ],
    )

    assert result.exit_code == 0
    assert "real run retry package prepared" in result.output
    assert "failed run: runs/real/real_001" in result.output
    assert "retry run: runs/real/real_002" in result.output
    assert "decision: runs/real/real_001/recovery_decision.json" in result.output


def test_cli_prepare_real_run_retry_reports_recovery_failure_without_traceback(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)
    (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    ).unlink()

    result = runner.invoke(
        app,
        [
            "prepare-real-run-retry",
            str(project_dir),
            "--failed-run-id",
            "real_001",
            "--reason",
            "retry invalid package",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "retry_same_candidate is not allowed for this run" in result.output
    assert "report: reports/real_run_recovery_report.json" in result.output
    assert "metric extraction request is missing" in result.output
    assert "Traceback" not in result.output


def test_cli_resolve_real_run_failure_reports_recovery_failure_without_traceback(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)
    (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    ).unlink()

    result = runner.invoke(
        app,
        [
            "resolve-real-run-failure",
            str(project_dir),
            "--run-id",
            "real_001",
            "--decision",
            "abandon_candidate",
            "--reason",
            "skip invalid package",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "abandon_candidate is not allowed for this run" in result.output
    assert "report: reports/real_run_recovery_report.json" in result.output
    assert "metric extraction request is missing" in result.output
    assert "Traceback" not in result.output


def test_cli_prepare_real_run_retry_does_not_print_stale_recovery_report(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)
    stale_result = runner.invoke(
        app,
        ["assess-real-run-recovery", str(project_dir), "--run-id", "real_001"],
    )
    assert stale_result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "prepare-real-run-retry",
            str(project_dir),
            "--failed-run-id",
            "real_001",
            "--retry-run-id",
            "real_001",
            "--reason",
            "invalid retry target",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "retry run_id must differ from failed run_id" in result.output
    assert "report: reports/real_run_recovery_report.json" not in result.output
    assert "Traceback" not in result.output


def test_cli_resolve_real_run_failure_does_not_print_stale_recovery_report(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)
    stale_result = runner.invoke(
        app,
        ["assess-real-run-recovery", str(project_dir), "--run-id", "real_001"],
    )
    assert stale_result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "resolve-real-run-failure",
            str(project_dir),
            "--run-id",
            "real_001",
            "--decision",
            "not_a_decision",
            "--reason",
            "invalid decision",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "not_a_decision" in result.output
    assert "report: reports/real_run_recovery_report.json" not in result.output
    assert "Traceback" not in result.output
