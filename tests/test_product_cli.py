from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from hermes_workflow import product_cli


runner = CliRunner()


def test_ic_opt_invokes_optimizer_flow(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            stopped_before="run-openbox-real",
            recommended_run_id=None,
            user_decision_required=False,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--dry-orchestration",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "project": project_dir,
            "real": True,
            "dry_orchestration": True,
            "max_evals": None,
            "batch_size": None,
            "parallel_jobs": None,
            "cadence_cshrc": cadence_cshrc,
            "strategy": None,
        }
    ]
    assert "optimizer flow completed" in result.output
    assert "report: reports/optimizer_flow_run_report.json" in result.output
    assert "stopped before: run-openbox-real" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--max-evals", "1"),
        ("--batch-size", "1"),
        ("--parallel-jobs", "1"),
    ],
)
def test_ic_opt_rejects_cli_workload_resource_overrides(
    monkeypatch, tmp_path: Path, flag: str, value: str
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "cadence_env.csh").write_text("# test\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        return SimpleNamespace(status="pass", report_path=project / "report.json")

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--dry-orchestration", flag, value],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output
    assert calls == []


def test_ic_opt_real_with_strategy_fails(tmp_path: Path, monkeypatch) -> None:
    """Product CLI must reject --strategy on initial real run; only requirement
    drives optimizer strategy."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    monkeypatch.setattr(
        product_cli,
        "optimize_project",
        lambda *a, **kw: pytest.fail(
            "optimize_project must not be called when --strategy is passed"
        ),
    )

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--dry-orchestration",
            "--strategy",
            "openbox_gp_eic",
        ],
    )

    assert result.exit_code != 0
    # Typer rejects unknown options with "No such option:" — the message must
    # mention --strategy so users see why.
    assert "--strategy" in result.output


def test_ic_opt_help_does_not_show_strategy() -> None:
    """`ic-opt --help` must not advertise `--strategy`; strategy belongs in
    opt_requirement.md / config."""
    result = runner.invoke(product_cli.app, ["--help"])
    assert result.exit_code == 0
    assert "--strategy" not in result.output


def test_ic_opt_does_not_default_max_evals_over_requirement(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "cadence_env.csh").write_text("# project\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            stopped_before="run-openbox-real",
            user_decision_required=False,
            recommended_run_id=None,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--dry-orchestration"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["max_evals"] is None


def test_ic_opt_explicit_cadence_env_overrides_project_file(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "cadence_env.csh").write_text("# project\n", encoding="utf-8")
    explicit_cadence_cshrc = tmp_path / "explicit_env.csh"
    explicit_cadence_cshrc.write_text("# explicit\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            stopped_before="run-openbox-real",
            recommended_run_id=None,
            user_decision_required=False,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--dry-orchestration",
            "--cadence-cshrc",
            str(explicit_cadence_cshrc),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["cadence_cshrc"] == explicit_cadence_cshrc


def test_ic_opt_uses_cadence_env_variable(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "env_cadence.csh"
    cadence_cshrc.write_text("# env\n", encoding="utf-8")
    monkeypatch.setenv(product_cli.CADENCE_CSHRC_ENV_VAR, str(cadence_cshrc))
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            stopped_before="run-openbox-real",
            recommended_run_id=None,
            user_decision_required=False,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--dry-orchestration"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["cadence_cshrc"] == cadence_cshrc


def test_ic_opt_rejects_execution_agent_option(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        raise AssertionError("legacy execution-agent option must be rejected before optimize")

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--execution-agent", "legacy-agent"],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_ic_opt_reports_missing_cadence_env(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.delenv(product_cli.CADENCE_CSHRC_ENV_VAR, raising=False)
    monkeypatch.setattr(
        product_cli,
        "USER_CADENCE_CSHRC",
        tmp_path / "missing_user_cadence_env.csh",
    )

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--dry-orchestration"],
    )

    assert result.exit_code == 1
    assert "Cadence cshrc was not found" in result.output
    assert "--cadence-cshrc" in result.output


def test_ic_opt_reports_optimizer_flow_failure(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    def fake_optimize_project(_project: Path, **_kwargs: object) -> object:
        raise ValueError("check-requirement failed: missing opt_requirement.md")

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--cadence-cshrc",
            str(cadence_cshrc),
        ],
    )

    assert result.exit_code == 1
    assert "check-requirement failed: missing opt_requirement.md" in result.output


def test_ic_opt_real_continue_invokes_local_continue_project(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_continue_local_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append({"project": project, **kwargs})
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_012",
            user_decision_required=True,
            issues=[],
        )

    def fail_optimize_project(*_a, **_kw):
        raise AssertionError("optimize_project must not be called for --real --continue")

    monkeypatch.setattr(product_cli, "continue_local_project", fake_continue_local_project, raising=False)
    monkeypatch.setattr(product_cli, "optimize_project", fail_optimize_project)

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--continue", "20"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "project": project_dir,
            "additional_evals": 20,
            "cadence_cshrc": cadence_cshrc,
        }
    ]
    assert "continuation completed" in result.output


def test_continue_local_project_does_not_pass_strategy_detail_overrides(
    monkeypatch, tmp_path: Path
) -> None:
    """Local product continuation must pass `None` for every CLI-side strategy
    detail, so requirement/config drives the strategy resolver."""
    from hermes_workflow import optimizer_continuation_flow

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence = project_dir / "cadence_env.csh"
    cadence.write_text("# test\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run_openbox_real_optimization(project, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            evaluation_count=12, report_path=None, evaluations_path=None
        )

    monkeypatch.setattr(
        optimizer_continuation_flow,
        "run_openbox_real_optimization",
        fake_run_openbox_real_optimization,
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "check_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="accepted"),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "summarize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "finalize_optimizer_run",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "generate_optimizer_insight_report",
        lambda *a, **k: SimpleNamespace(status="pass"),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "generate_optimizer_decision_report",
        lambda *a, **k: SimpleNamespace(
            status="pass",
            recommended_run_id="real_012",
            recommended_action="stop_for_user_review",
        ),
    )
    monkeypatch.setattr(
        optimizer_continuation_flow,
        "assert_valid_project",
        lambda *a, **k: None,
    )

    optimizer_continuation_flow.continue_local_project(
        project_dir,
        additional_evals=20,
        cadence_cshrc=cadence,
    )

    assert captured["max_evals"] is None
    assert captured["additional_evals"] == 20
    assert captured["continue_from_existing"] is True
    assert captured["batch_size"] is None
    assert captured["parallel_jobs"] is None
    assert captured["strategy"] is None
    assert captured["surrogate_type"] is None
    assert captured["acq_type"] is None
    assert captured["acq_optimizer_type"] is None
    assert captured["initial_trials"] is None


def test_ic_opt_continue_without_real_fails(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--continue", "20"],
    )

    assert result.exit_code != 0
    assert "--continue" in result.output and "--real" in result.output


def test_ic_opt_real_continue_with_strategy_fails(monkeypatch, tmp_path: Path) -> None:
    """`--strategy` is no longer a product CLI option; passing it must fail at
    the Typer parsing layer, before any continuation logic runs."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")

    monkeypatch.setattr(
        product_cli,
        "continue_local_project",
        lambda *a, **kw: pytest.fail(
            "continue_local_project must not be called when --strategy is passed"
        ),
        raising=False,
    )

    result = runner.invoke(
        product_cli.app,
        [str(project_dir), "--real", "--continue", "20", "--strategy", "openbox_gp_eic"],
    )

    assert result.exit_code != 0
    assert "--strategy" in result.output


def test_ic_opt_real_alone_does_not_trigger_continuation(monkeypatch, tmp_path: Path) -> None:
    """`--real` without `--continue` must NOT default to a continuation delta."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = project_dir / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_optimize_project(project: Path, **kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        report_path = project / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="pass", report_path=report_path,
            stopped_before=None, recommended_run_id=None,
            user_decision_required=False, issues=[],
        )

    def fail_continue(*_a, **_kw):
        raise AssertionError("continue_local_project must not be called for plain --real")

    monkeypatch.setattr(product_cli, "optimize_project", fake_optimize_project)
    monkeypatch.setattr(product_cli, "continue_local_project", fail_continue, raising=False)

    result = runner.invoke(product_cli.app, [str(project_dir), "--real", "--dry-orchestration"])

    assert result.exit_code == 0
    assert all("additional_evals" not in c for c in calls)
