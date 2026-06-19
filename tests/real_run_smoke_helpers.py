from __future__ import annotations

import json
from pathlib import Path

import yaml

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import sha256_file
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealResultRecordReport,
)
from hermes_workflow.result_handoff import check_real_run
from tests.project_factory import create_approved_generic_project


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    variables = payload["variables"]
    names = [variable["name"] for variable in variables]
    assert len(names) == 2
    return names[0], names[1]


def metric_names_for_run(project_dir: Path, run_id: str = "real_001") -> tuple[str, str]:
    request = load_json(
        project_dir / "runs" / "real" / run_id / "metric_extraction_request.json"
    )
    names = [metric["name"] for metric in request["metrics"]]
    assert len(names) == 2
    return names[0], names[1]


def default_metric_values(
    project_dir: Path,
    *,
    run_id: str = "real_001",
) -> dict[str, float]:
    objective_metric, constraint_metric = metric_names_for_run(project_dir, run_id)
    return {
        objective_metric: 10.0,
        constraint_metric: 1.0e-6,
    }


def advisor_suggestion(
    project_dir: Path,
    *,
    int_value: float,
    width_value: float,
) -> dict[str, float]:
    int_name, width_name = variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}


def advisor_batches(project_dir: Path) -> list[list[dict[str, float]]]:
    return [
        [
            advisor_suggestion(project_dir, int_value=2, width_value=0.2),
            advisor_suggestion(project_dir, int_value=4, width_value=0.4),
        ],
        [
            advisor_suggestion(project_dir, int_value=3, width_value=0.3),
            advisor_suggestion(project_dir, int_value=5, width_value=0.5),
        ],
    ]


def create_approved_real_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        name="real_run_smoke_project",
        created_at_utc="2026-06-03T00:00:00Z",
        max_evaluations=12,
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


def write_fake_result_manifest(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    status: str = "succeeded",
    include_artifacts: bool = True,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = load_json(run_dir / "real_run_manifest.json")
    selected_candidate_id = candidate_id or prepared["candidate_id"]
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    if include_artifacts:
        psf_dir.mkdir(parents=True, exist_ok=True)
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (psf_dir / "spectre.out").write_text(
            "sanitized spectre output\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean.log").write_text(
            "sanitized ocean log\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean_scalars.tsv").write_text(
            "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stdout").write_text(
            "sanitized stdout\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "status": status,
            "started_at_utc": "2026-06-03T00:30:00Z",
            "completed_at_utc": "2026-06-03T00:31:00Z",
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


def write_fake_metric_result_manifest(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    status: str = "succeeded",
    metric_status: str = "succeeded",
    values: dict[str, float] | None = None,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    selected_candidate_id = candidate_id or request["candidate_id"]
    metric_values = values or default_metric_values(project_dir, run_id=run_id)
    write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "backend": "spectre_ocean_batch",
            "status": status,
            "request_file": f"runs/real/{run_id}/metric_extraction_request.json",
            "request_sha256": sha256_file(request_path),
            "psf_dir": f"runs/real/{run_id}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "return_code": 0,
                "script_file": f"runs/real/{run_id}/metrics/metric_probe.ocn",
                "script_sha256": sha256_file(script_path),
                "log_file": f"runs/real/{run_id}/metrics/ocean.log",
                "scalar_output_file": (
                    f"runs/real/{run_id}/metrics/ocean_scalars.tsv"
                ),
            },
            "metrics": [
                {
                    "name": name,
                    "status": metric_status,
                    "value": value if metric_status == "succeeded" else None,
                    "value_text": (
                        f"{value:.12g}" if metric_status == "succeeded" else None
                    ),
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name]["result"],
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [] if metric_status == "succeeded" else ["scalar failed"],
                }
                for name, value in metric_values.items()
            ],
            "issues": [] if status == "succeeded" else ["ocean failed"],
        },
    )


def record_checked_run(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    recorded_at_utc: str,
) -> RealResultRecordReport:
    write_fake_result_manifest(project_dir, run_id=run_id, candidate_id=candidate_id)
    write_fake_metric_result_manifest(
        project_dir,
        run_id=run_id,
        candidate_id=candidate_id,
    )
    assert check_real_run(project_dir, run_id=run_id).status == RealRunCheckStatus.PASS
    assert (
        check_metric_results(project_dir, run_id=run_id).status
        == MetricResultCheckStatus.PASS
    )
    return record_real_result(
        project_dir,
        run_id=run_id,
        recorded_at_utc=recorded_at_utc,
    )


def ledger_rows(project_dir: Path) -> list[dict]:
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    return [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
