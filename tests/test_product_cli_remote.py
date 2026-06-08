from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow import product_cli


runner = CliRunner()


def test_ic_opt_remote_doctor_does_not_resolve_local_cadence_env(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_remote_doctor(ref, **kwargs):
        calls.append({"ref": ref, **kwargs})
        report_path = tmp_path / "reports" / "ic_opt_doctor_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            local_report_path=report_path,
            remote_report_path="/remote/project/reports/ic_opt_doctor_report.json",
            issues=[],
        )

    monkeypatch.setattr(product_cli, "run_remote_doctor", fake_run_remote_doctor)

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--doctor"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["ref"].ssh_profile == "lab"
    assert calls[0]["ref"].remote_project_dir == PurePosixPath("/remote/project")
    assert "remote doctor completed" in result.output
    assert "remote report: /remote/project/reports/ic_opt_doctor_report.json" in result.output


def test_ic_opt_remote_real_calls_optimize_remote_project(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_optimize_remote_project(ref, **kwargs):
        calls.append({"ref": ref, **kwargs})
        report_path = tmp_path / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_remote_project", fake_optimize_remote_project)

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["ref"].ssh_profile == "lab"
    assert "remote optimizer flow completed" in result.output
    assert "recommended: real_001" in result.output


def test_ic_opt_remote_continue_routes_additional_evals(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_continue_remote_project(ref, **kwargs):
        calls.append({"ref": ref, **kwargs})
        return SimpleNamespace(
            status="pass",
            report_path=tmp_path / "reports" / "optimizer_flow_run_report.json",
            recommended_run_id="real_141",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "continue_remote_project", fake_continue_remote_project)

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--continue", "40"],
    )

    assert result.exit_code == 0, result.output
    assert "remote continuation completed" in result.output
    assert "recommended: real_141" in result.output
