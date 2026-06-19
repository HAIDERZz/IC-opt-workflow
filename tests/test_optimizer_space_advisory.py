from __future__ import annotations

from pathlib import Path

import yaml

from hermes_workflow.optimizer_space_advisory import build_space_compression_advisory


def _write_variables(project_dir: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "variables": [
            {
                "name": "W",
                "kind": "continuous_step",
                "lower": "1u",
                "upper": "5u",
                "step": "0.5u",
            },
            {
                "name": "L",
                "kind": "continuous_step",
                "lower": "20n",
                "upper": "60n",
                "step": "10n",
            },
        ],
    }
    (project_dir / "config").mkdir(parents=True)
    (project_dir / "config" / "variables.yaml").write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )

def _write_integer_variables(project_dir: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "variables": [
            {
                "name": "N",
                "kind": "integer",
                "lower": "1",
                "upper": "5",
                "step": "1",
            },
            {
                "name": "W",
                "kind": "continuous_step",
                "lower": "1u",
                "upper": "5u",
                "step": "1u",
            },
        ],
    }
    (project_dir / "config").mkdir(parents=True)
    (project_dir / "config" / "variables.yaml").write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )


def test_space_compression_advisory_requires_enough_rows(tmp_path: Path) -> None:
    _write_variables(tmp_path)
    variables_path = tmp_path / "config" / "variables.yaml"
    before = variables_path.read_text(encoding="utf-8")

    summary = build_space_compression_advisory(
        tmp_path,
        [
            {
                "evaluation_index": 1,
                "run_id": "real_001",
                "status": "feasible",
                "parameters": {"W": "1u", "L": "20n"},
                "objective": 1.0,
            }
        ],
    )

    assert summary["status"] == "not_available"
    assert summary["reason"] == "fewer than three eligible finite-objective rows"
    assert summary["advisory_only"] is True
    assert summary["applied_to_optimizer"] is False
    assert summary["eligible_count"] == 1
    assert variables_path.read_text(encoding="utf-8") == before


def test_space_compression_advisory_uses_openbox_boundary_ranges(tmp_path: Path) -> None:
    _write_variables(tmp_path)
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"W": "1u", "L": "20n"},
            "objective": 1.0,
        },
        {
            "evaluation_index": 2,
            "run_id": "real_002",
            "status": "feasible",
            "parameters": {"W": "1.5u", "L": "20n"},
            "objective": 2.0,
        },
        {
            "evaluation_index": 3,
            "run_id": "real_003",
            "status": "constraint_failed",
            "parameters": {"W": "5u", "L": "60n"},
            "objective": 20.0,
        },
    ]

    summary = build_space_compression_advisory(tmp_path, traces)

    assert summary["status"] == "available"
    assert summary["mode"] == "openbox_compressor_dry_run"
    assert summary["advisory_only"] is True
    assert summary["applied_to_optimizer"] is False
    assert summary["method"] == "r_boundary"
    assert summary["eligible_count"] == 3
    assert summary["feasible_count"] == 2
    assert summary["confidence"] == "low"
    assert {item["variable"] for item in summary["suggestions"]}
    assert {item["variable"] for item in summary["suggestions"]}.issubset({"W", "L"})
    assert all(item["compression_ratio"] < 1.0 for item in summary["suggestions"])


def test_space_compression_advisory_excludes_rows_outside_current_space(
    tmp_path: Path,
) -> None:
    _write_variables(tmp_path)
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"W": "1u", "L": "20n"},
            "objective": 1.0,
        },
        {
            "evaluation_index": 2,
            "run_id": "real_002",
            "status": "feasible",
            "parameters": {"W": "100u", "L": "30n"},
            "objective": 2.0,
        },
    ]

    summary = build_space_compression_advisory(tmp_path, traces)

    assert summary["status"] == "not_available"
    assert summary["reason"] == "fewer than three eligible finite-objective rows"
    assert summary["eligible_count"] == 1

def test_space_compression_advisory_supports_integer_variables(
    tmp_path: Path,
) -> None:
    _write_integer_variables(tmp_path)
    traces = [
        {
            "evaluation_index": 1,
            "run_id": "real_001",
            "status": "feasible",
            "parameters": {"N": "1", "W": "1u"},
            "objective": 1.0,
        },
        {
            "evaluation_index": 2,
            "run_id": "real_002",
            "status": "feasible",
            "parameters": {"N": "2", "W": "2u"},
            "objective": 2.0,
        },
        {
            "evaluation_index": 3,
            "run_id": "real_003",
            "status": "constraint_failed",
            "parameters": {"N": "5", "W": "5u"},
            "objective": 20.0,
        },
    ]

    summary = build_space_compression_advisory(tmp_path, traces)

    assert summary["mode"] == "openbox_compressor_dry_run"
    assert summary["advisory_only"] is True
    assert summary["applied_to_optimizer"] is False
    assert summary["eligible_count"] == 3
