import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from tests.report_helpers import write_pass_reports


runner = CliRunner()


def test_cli_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


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

    instruction = json.loads(
        (project_dir / "supervisor_instruction.json").read_text(encoding="utf-8")
    )
    assert prepare_result.exit_code == 0
    assert dry_run_result.exit_code == 0
    assert health_result.exit_code == 0
    assert approve_result.exit_code == 0
    assert instruction["decision"] == "approve_first_real_run"
    assert instruction["reason"] == "config validation and preflight reports passed"
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
