from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_next_real_run, prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import RealResultRecordStatus, RealRunCheckStatus
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-02T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir


def _write_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = _load_json(run_dir / "real_run_manifest.json")
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
    _write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": run_id,
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


def _write_metric_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
    _write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": run_id,
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
                    "result": request_by_name[name]["result"],
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


def _record_real_001(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS
    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T00:40:00Z",
    )
    assert report.status == RealResultRecordStatus.PASS


def test_prepare_next_real_run_refuses_before_recorded_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    with pytest.raises(ValueError, match="ledger is missing"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_invalid_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ledger row 1 is invalid"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_optimizer_state_drift(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["random_seed"] = 99
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state random_seed disagrees"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_completed_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["status"] = "completed"
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state is completed"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_when_max_evaluations_reached(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        re.sub(
            r"max_evaluations: \d+",
            "max_evaluations: 1",
            optimizer_path.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable config drift detected"):
        prepare_next_real_run(project_dir)
