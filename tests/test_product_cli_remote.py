from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from hermes_workflow import product_cli
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir


runner = CliRunner()


@pytest.fixture(autouse=True)
def _avoid_real_remote_attempt_archive(monkeypatch) -> None:
    monkeypatch.setattr(
        product_cli,
        "begin_remote_optimizer_attempt",
        lambda *args, **kwargs: None,
    )


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
    assert "doctor completed" in result.output
    assert "transport: remote" in result.output
    assert "remote report: /remote/project/reports/ic_opt_doctor_report.json" in result.output


def test_ic_opt_remote_doctor_normalizes_windows_cadence_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    product_cli.main(
        project_dir=Path("/remote/project"),
        real=False,
        dry_orchestration=False,
        cadence_cshrc=PureWindowsPath(r"C:\cadence\cadence_env.csh"),
        ssh_profile="lab",
        doctor=True,
        continue_evals=None,
    )

    assert calls[0]["cadence_cshrc"] == PurePosixPath(
        "C:/cadence/cadence_env.csh"
    )


def test_ic_opt_remote_real_calls_optimize_remote_project(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        product_cli,
        "run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        ),
    )

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
    assert calls[0]["max_evals"] is None
    assert calls[0]["attempt_started"] is True
    assert "remote optimizer flow completed" in result.output
    assert "recommended: real_001" in result.output


def test_ic_opt_remote_real_archives_stale_pass_before_doctor(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        product_cli,
        "begin_remote_optimizer_attempt",
        lambda *args, **kwargs: calls.append("archive"),
    )
    monkeypatch.setattr(
        product_cli,
        "run_remote_doctor",
        lambda *args, **kwargs: (
            calls.append("doctor"),
            (_ for _ in ()).throw(RuntimeError("doctor transport failed")),
        )[-1],
    )
    monkeypatch.setattr(
        product_cli,
        "optimize_remote_project",
        lambda *args, **kwargs: pytest.fail(
            "optimizer must not start after doctor transport failure"
        ),
    )

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real"],
    )

    assert result.exit_code == 1
    assert calls == ["archive", "doctor"]
    assert "doctor transport failed" in result.output


def test_ic_opt_remote_real_normalizes_windows_cadence_path(monkeypatch) -> None:
    doctor_calls: list[dict[str, object]] = []
    optimize_calls: list[dict[str, object]] = []

    def fake_run_remote_doctor(ref, **kwargs):
        doctor_calls.append({"ref": ref, **kwargs})
        return SimpleNamespace(
            status="pass",
            workflow_mode="optimize",
            issues=[],
        )

    def fake_optimize_remote_project(ref, **kwargs):
        optimize_calls.append({"ref": ref, **kwargs})
        return SimpleNamespace(
            status="pass",
            report_path=Path("reports/optimizer_flow_run_report.json"),
            recommended_run_id=None,
            user_decision_required=False,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "run_remote_doctor", fake_run_remote_doctor)
    monkeypatch.setattr(
        product_cli,
        "optimize_remote_project",
        fake_optimize_remote_project,
    )

    product_cli.main(
        project_dir=Path("/remote/project"),
        real=True,
        dry_orchestration=False,
        cadence_cshrc=PureWindowsPath(r"C:\cadence\cadence_env.csh"),
        ssh_profile="lab",
        doctor=False,
        continue_evals=None,
    )

    expected = PurePosixPath("C:/cadence/cadence_env.csh")
    assert doctor_calls[0]["cadence_cshrc"] == expected
    assert optimize_calls[0]["remote_cadence_cshrc"] == expected


def test_ic_opt_remote_fix_run_prints_controller_and_remote_report_paths(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        product_cli,
        "run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(
            status="pass",
            workflow_mode="fix_run",
            issues=[],
        ),
    )
    monkeypatch.setattr(
        product_cli,
        "run_remote_fix_run_project",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    expected_local = remote_cache_dir(ref) / "reports" / "fix_run_report.json"

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real"],
    )

    assert result.exit_code == 0, result.output
    assert f"local report: {expected_local}" in result.output
    assert (
        "remote report: /remote/project/reports/fix_run_report.json"
        in result.output
    )


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
        ["--ssh-profile", "lab", "/remote/project", "--real", "--continue", "40"],
    )

    assert result.exit_code == 0, result.output
    assert "remote continuation completed" in result.output
    assert "recommended: real_141" in result.output
    assert calls[0]["additional_evals"] == 40
    assert calls[0]["strategy"] is None


def test_ic_opt_remote_continue_without_real_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        product_cli,
        "continue_remote_project",
        lambda *a, **kw: pytest.fail("continue_remote_project must not be called without --real"),
    )
    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--continue", "40"],
    )
    assert result.exit_code != 0
    assert "--continue" in result.output and "--real" in result.output


def test_ic_opt_remote_continue_with_strategy_fails(monkeypatch, tmp_path: Path) -> None:
    """`--strategy` is no longer a product CLI option for remote continuation
    either."""
    monkeypatch.setattr(
        product_cli,
        "continue_remote_project",
        lambda *a, **kw: pytest.fail("strategy override must be rejected"),
    )
    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real", "--continue", "40", "--strategy", "openbox_gp_eic"],
    )
    assert result.exit_code != 0
    assert "--strategy" in result.output


def test_ic_opt_remote_real_with_strategy_fails(monkeypatch) -> None:
    """Remote initial real run also rejects --strategy at the CLI layer."""
    monkeypatch.setattr(
        product_cli,
        "optimize_remote_project",
        lambda *a, **kw: pytest.fail(
            "optimize_remote_project must not be called when --strategy is passed"
        ),
    )
    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real", "--strategy", "openbox_gp_eic"],
    )
    assert result.exit_code != 0
    assert "--strategy" in result.output
