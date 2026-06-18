from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.reports import DryRunReport, PassFail
from tests.netlist_dry_run_helpers import (
    project_with_template,
    template_text,
    variable_names,
)


def _create_project_with_template(tmp_path: Path, template: str | None = None) -> Path:
    return project_with_template(tmp_path, template)


def _load_report(project_dir: Path) -> DryRunReport:
    payload = json.loads(
        (project_dir / "reports" / "dry_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    return DryRunReport.model_validate(payload)


def test_run_dry_run_renders_lower_bound_candidate(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    first, second = variable_names(project_dir)

    report = run_dry_run(project_dir)

    rendered_path = project_dir / "runs" / "dry_run" / "input.scs"
    rendered = rendered_path.read_text(encoding="utf-8")
    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.PASS
    assert report.rendered_candidate_scs == "runs/dry_run/input.scs"
    assert report.placeholder_check.unresolved_placeholders == []
    assert report.placeholder_check.unexpected_template_variables == []
    assert report.metrics_import_ok is True
    assert report.mock_metrics_ok is True
    assert report.objective_ok is True
    assert report.constraints_ok is True
    assert report.ledger_write_ok is True
    assert report.state_write_ok is True
    assert report.issues == []
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert f"{first}=1" in rendered
    assert f"{second}=0.1u" in rendered
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_run_dry_run_reports_missing_template(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    (project_dir / "netlists" / "templates" / "template.scs").unlink()

    report = run_dry_run(project_dir)

    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.FAIL
    assert "template.scs is missing: netlists/templates/template.scs" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_reports_missing_approved_placeholder(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    _first, second = variable_names(project_dir)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        template_text(project_dir, omit_second=True), encoding="utf-8"
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.FAIL
    assert (
        f"approved variable {second} placeholder is missing from template"
        in report.issues
    )
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_reports_unexpected_placeholder(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        template_text(project_dir, unexpected="EXTRA_GAIN"), encoding="utf-8"
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.FAIL
    assert report.placeholder_check.unexpected_template_variables == ["EXTRA_GAIN"]
    assert report.placeholder_check.unresolved_placeholders == ["{{EXTRA_GAIN}}"]
    assert "unexpected template variable EXTRA_GAIN" in report.issues
    assert "rendered candidate still contains unresolved placeholders" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_reports_unresolved_malformed_placeholder(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        template_text(project_dir, malformed="GAIN"), encoding="utf-8"
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.FAIL
    assert report.placeholder_check.unresolved_placeholders == ["{{ GAIN }}"]
    assert "rendered candidate still contains unresolved placeholders" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_removes_stale_render_on_failure(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    first_report = run_dry_run(project_dir)
    assert first_report.status == PassFail.PASS
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        template_text(project_dir, unexpected="EXTRA"), encoding="utf-8"
    )

    failed_report = run_dry_run(project_dir)

    assert failed_report.status == PassFail.FAIL
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_constraint_result_false_still_checks_evaluability(
    tmp_path: Path,
) -> None:
    project_dir = _create_project_with_template(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    assert payload["constraints"]
    payload["constraints"][0]["value"] = "0 W"
    metrics_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    report = run_dry_run(project_dir)

    assert report.status == PassFail.PASS
    assert report.constraints_ok is True
    assert report.issues == []


def test_run_dry_run_does_not_write_optimizer_artifacts(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)

    report = run_dry_run(project_dir)

    assert report.status == PassFail.PASS
    assert (project_dir / "runs" / "dry_run" / "input.scs").exists()
    assert not (project_dir / "ledger" / ".dry_run_write_probe").exists()
    assert not (project_dir / "state" / ".dry_run_write_probe").exists()
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
    assert not (project_dir / "state" / "health_check.json").exists()


def test_run_dry_run_reports_render_write_failure(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(tmp_path)
    # The generic factory pre-creates runs/real/; replace runs/ with a file so the
    # dry-run render write (runs/dry_run/input.scs) fails.
    shutil.rmtree(project_dir / "runs")
    (project_dir / "runs").write_text("not a directory", encoding="utf-8")

    report = run_dry_run(project_dir)

    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.FAIL
    assert report.issues
    assert "rendered candidate could not be written" in report.issues[0]
