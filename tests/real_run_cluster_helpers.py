"""Shared generic real-run fixture helpers for the next-real-run test cluster.

These helpers back ``tests/test_next_real_run.py``,
``tests/test_candidate_injection_real_run.py``,
``tests/test_optimizer_suggestion.py``, and ``tests/test_optimizer_loop.py``.
They build projects with ``tests/project_factory.py`` (never the packaged release
template) and derive variable/metric names from generated config and request
artifacts, so the cluster's behavioral assertions stay decoupled from any
circuit-specific template contents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import RealResultRecordStatus, RealRunCheckStatus
from hermes_workflow.result_handoff import check_real_run
from tests.project_factory import create_approved_generic_project

DEFAULT_CREATED_AT_UTC = "2026-06-02T00:00:00Z"
DEFAULT_REAL_001_PREPARED_AT_UTC = "2026-06-02T00:20:00Z"
DEFAULT_REAL_001_RECORDED_AT_UTC = "2026-06-02T00:40:00Z"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc=DEFAULT_CREATED_AT_UTC,
        max_evaluations=12,
    )
    prepare_real_run(project_dir, created_at_utc=DEFAULT_REAL_001_PREPARED_AT_UTC)
    return project_dir


def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    names = [variable["name"] for variable in payload["variables"]]
    assert len(names) == 2
    return names[0], names[1]


def metric_names_for_run(project_dir: Path, run_id: str = "real_001") -> list[str]:
    request = load_json(
        project_dir / "runs" / "real" / run_id / "metric_extraction_request.json"
    )
    return [metric["name"] for metric in request["metrics"]]


def default_metric_values(
    project_dir: Path, run_id: str = "real_001"
) -> dict[str, float]:
    names = metric_names_for_run(project_dir, run_id)
    values: dict[str, float] = {}
    for index, name in enumerate(names):
        values[name] = 10.0 if index == 0 else 1.0e-6
    return values


def valid_candidate_parameters(
    project_dir: Path,
    *,
    int_value: str = "3",
    width_value: str = "0.3u",
) -> dict[str, str]:
    int_name, width_name = variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}


def missing_candidate_parameters(project_dir: Path) -> dict[str, str]:
    int_name, _width_name = variable_names(project_dir)
    return {int_name: "3"}


def extra_candidate_parameters(project_dir: Path) -> dict[str, str]:
    params = valid_candidate_parameters(project_dir)
    params["EXTRA"] = "1"
    return params


def invalid_candidate_cases(
    project_dir: Path,
) -> list[tuple[dict[str, str], str]]:
    int_name, width_name = variable_names(project_dir)
    return [
        ({int_name: "1.5", width_name: "0.3u"}, f"{int_name} must be an integer"),
        ({int_name: "99", width_name: "0.3u"}, f"{int_name} is outside approved bounds"),
        (
            {int_name: "3", width_name: "0.3 um"},
            f"{width_name} must use a Spectre-safe attached unit suffix",
        ),
        (
            {int_name: "3", width_name: " 0.3u "},
            f"{width_name} must use compact Spectre-safe formatting",
        ),
        (
            {int_name: "3", width_name: "0.35u"},
            f"{width_name} is not aligned to approved step",
        ),
    ]


def write_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = load_json(run_dir / "real_run_manifest.json")
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (psf_dir / "spectre.out").write_text("sanitized spectre output\n", encoding="utf-8")
    (metrics_dir / "ocean.log").write_text("sanitized ocean log\n", encoding="utf-8")
    (metrics_dir / "ocean_scalars.tsv").write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
        encoding="utf-8",
    )
    (run_dir / "spectre.stdout").write_text("sanitized stdout\n", encoding="utf-8")
    (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": prepared["candidate_id"],
            "status": "succeeded",
            "started_at_utc": "2026-06-02T00:30:00Z",
            "completed_at_utc": "2026-06-02T00:31:00Z",
            "simulator": {
                "engine": "spectre_x",
                "preset": "ax",
                "command_label": "spectre_ocean_adapter",
            },
            "prepared_input_scs": prepared["rendered_input_scs"],
            "prepared_input_sha256": prepared["rendered_input_sha256"],
            "log_file": f"runs/real/{run_id}/spectre.stdout",
            "artifact_files": [
                f"runs/real/{run_id}/spectre.stderr",
                f"runs/real/{run_id}/psf/spectre.out",
                f"runs/real/{run_id}/metrics/ocean.log",
                f"runs/real/{run_id}/metrics/ocean_scalars.tsv",
            ],
            "result_data": {
                "kind": "spectre_psf",
                "psf_dir": f"runs/real/{run_id}/psf",
                "spectre_out": f"runs/real/{run_id}/psf/spectre.out",
            },
            "metric_result_manifest": (
                f"runs/real/{run_id}/metrics/metric_result_manifest.json"
            ),
        },
    )


def write_metric_result_manifest(
    project_dir: Path, *, run_id: str = "real_001"
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = load_json(request_path)
    candidate = load_json(run_dir / "candidate.json")
    metrics_dir = run_dir / "metrics"
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = default_metric_values(project_dir, run_id)
    write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": candidate["candidate_id"],
            "backend": "spectre_ocean_batch",
            "status": "succeeded",
            "request_file": f"runs/real/{run_id}/metric_extraction_request.json",
            "request_sha256": sha256_file(request_path),
            "psf_dir": f"runs/real/{run_id}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "return_code": 0,
                "script_file": f"runs/real/{run_id}/metrics/metric_probe.ocn",
                "script_sha256": sha256_file(script_path),
                "log_file": f"runs/real/{run_id}/metrics/ocean.log",
                "scalar_output_file": f"runs/real/{run_id}/metrics/ocean_scalars.tsv",
            },
            "metrics": [
                {
                    "name": name,
                    "status": "succeeded",
                    "value": value,
                    "value_text": f"{value:.12g}",
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name].get("result"),
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [],
                }
                for name, value in values.items()
            ],
            "issues": [],
        },
    )


def record_real_001(project_dir: Path) -> None:
    write_result_manifest(project_dir)
    write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS
    report = record_real_result(
        project_dir,
        recorded_at_utc=DEFAULT_REAL_001_RECORDED_AT_UTC,
    )
    assert report.status == RealResultRecordStatus.PASS
