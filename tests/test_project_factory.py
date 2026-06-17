"""Tests for the generic, release-template-independent project factory.

These prove the product supports arbitrary variables/metrics (not just the
release Mixer example): a project built with custom metric names validates,
runs the dry-run fake path, and records a value for every declared metric.
"""
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.openbox_backend import run_openbox_fake_optimization
from hermes_workflow.validate import assert_valid_project

from tests.helpers.project_factory import build_project


def test_factory_builds_valid_project_with_arbitrary_metrics(tmp_path: Path) -> None:
    project_dir = build_project(
        tmp_path / "project",
        variables=[
            {"name": "width", "kind": "continuous_step", "lower": "1u", "upper": "2u", "step": "0.2u"},
            {"name": "current", "kind": "integer", "lower": "1", "upper": "8", "step": "1"},
        ],
        metrics=[
            {"name": "gain_db", "unit": "dB", "maestro_formula": "gain"},
            {"name": "power_mw", "unit": "mW", "maestro_formula": "pwr"},
            {"name": "phase_margin", "unit": "deg", "maestro_formula": "pm"},
        ],
        constraints=[
            {"metric": "gain_db", "op": "ge", "value": "10"},
            {"metric": "power_mw", "op": "le", "value": "5"},
        ],
        objective={"direction": "maximize", "expression": "gain_db"},
    )

    bundle = assert_valid_project(project_dir)
    assert [variable.name for variable in bundle.variables.variables] == [
        "width",
        "current",
    ]
    assert [metric.name for metric in bundle.metrics.metrics] == [
        "gain_db",
        "power_mw",
        "phase_margin",
    ]


def test_factory_default_project_runs_dry_run_and_records_metric(
    tmp_path: Path,
) -> None:
    project_dir = build_project(tmp_path / "project")

    report = run_dry_run(project_dir)

    assert report.status.value == "pass"


def test_factory_project_fake_optimization_records_every_declared_metric(
    tmp_path: Path,
) -> None:
    project_dir = build_project(
        tmp_path / "project",
        metrics=[
            {"name": "gain_db", "unit": "dB", "maestro_formula": "gain"},
            {"name": "power_mw", "unit": "mW", "maestro_formula": "pwr"},
        ],
        constraints=[{"metric": "power_mw", "op": "le", "value": "5"}],
        objective={"direction": "maximize", "expression": "gain_db"},
    )

    result = run_openbox_fake_optimization(project_dir, batch_size=4, max_evals=4)

    evaluations_path = project_dir / "reports" / "optimizer_evaluations.jsonl"
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    metrics_block = rows[0]["metrics"]
    assert "gain_db" in metrics_block
    assert "power_mw" in metrics_block
    assert result.traces
