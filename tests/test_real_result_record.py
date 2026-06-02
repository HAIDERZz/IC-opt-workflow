from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import (
    RealRunCheckStatus,
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.schemas import LedgerRow
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def test_ledger_row_accepts_real_result_provenance() -> None:
    row = LedgerRow(
        candidate_id="real_001",
        parameters={"FN": "2", "WN": "0.3 um", "FP": "2", "WP": "0.3 um"},
        metrics={"rise": 1.25e-10, "fall": 1.45e-10, "DC": 3.2e-4},
        constraints_passed=True,
        objective=3.2e-4,
        batch_id=1,
        simulation_status="real_pass",
        timestamp_utc="2026-06-02T12:00:00Z",
        result_source="real",
        run_id="real_001",
        result_manifest="runs/real/real_001/result_manifest.json",
        metric_result_manifest=(
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
    )

    assert row.result_source == "real"
    assert row.run_id == "real_001"
    assert row.simulation_status == "real_pass"


def test_ledger_row_still_accepts_existing_mock_payload() -> None:
    row = LedgerRow(
        candidate_id="cand_001",
        parameters={"FN": "4"},
        metrics={"rise": 52.0},
        constraints_passed=True,
        objective=52.0,
        batch_id=1,
        simulation_status="mock_pass",
        timestamp_utc="2026-05-29T12:00:00Z",
    )

    assert row.result_source is None
    assert row.run_id is None


@pytest.mark.parametrize(
    "bad_status",
    ["real_error", "spectre_failed", "pass", ""],
)
def test_ledger_row_rejects_unapproved_real_statuses(bad_status: str) -> None:
    with pytest.raises(ValidationError, match="simulation_status must be one of"):
        LedgerRow(
            candidate_id="real_001",
            parameters={"FN": "2"},
            metrics={"rise": 1.25e-10},
            constraints_passed=True,
            objective=1.25e-10,
            batch_id=1,
            simulation_status=bad_status,
            timestamp_utc="2026-06-02T12:00:00Z",
            result_source="real",
            run_id="real_001",
        )


def test_real_result_record_report_schema_accepts_pass_report() -> None:
    report = RealResultRecordReport(
        schema_version="1.0",
        status=RealResultRecordStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        ledger_path="ledger/experiment_ledger.jsonl",
        optimizer_state_path="state/optimizer_state.json",
        best_candidate_path="state/best_candidate.json",
        checks=RealResultRecordFlags(
            real_run_check_ok=True,
            metric_result_check_ok=True,
            candidate_ok=True,
            duplicate_ok=True,
            objective_ok=True,
            constraints_ok=True,
            ledger_write_ok=True,
            state_write_ok=True,
        ),
        issues=[],
    )

    assert report.status == RealResultRecordStatus.PASS
    assert report.checks.ledger_write_ok is True


def _write_json(path: Path, payload: dict) -> None:
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


def _write_result_manifest(
    project_dir: Path,
    *,
    include_metric_result_manifest: bool = True,
) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
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
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
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
        "log_file": "runs/real/real_001/spectre.stdout",
        "artifact_files": [
            "runs/real/real_001/spectre.stderr",
            "runs/real/real_001/psf/spectre.out",
            "runs/real/real_001/metrics/ocean.log",
            "runs/real/real_001/metrics/ocean_scalars.tsv",
        ],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": "runs/real/real_001/psf",
            "spectre_out": "runs/real/real_001/psf/spectre.out",
        },
    }
    if include_metric_result_manifest:
        payload["metric_result_manifest"] = (
            "runs/real/real_001/metrics/metric_result_manifest.json"
        )
    _write_json(run_dir / "result_manifest.json", payload)


def _write_metric_result_manifest(
    project_dir: Path,
    *,
    values: dict[str, float] | None = None,
) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    metric_values = values or {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
        "backend": "spectre_ocean_batch",
        "status": "succeeded",
        "request_file": "runs/real/real_001/metric_extraction_request.json",
        "request_sha256": sha256_file(request_path),
        "psf_dir": "runs/real/real_001/psf",
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0,
            "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
            "script_sha256": sha256_file(script_path),
            "log_file": "runs/real/real_001/metrics/ocean.log",
            "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv",
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
            for name, value in metric_values.items()
        ],
        "issues": [],
    }
    _write_json(metrics_dir / "metric_result_manifest.json", payload)


def _write_valid_checked_result(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS


def _assert_no_optimizer_writes(project_dir: Path) -> None:
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def _assert_no_prerequisite_check_reports(project_dir: Path) -> None:
    assert not (project_dir / "reports" / "real_run_check_report.json").exists()
    assert not (project_dir / "reports" / "metric_result_check_report.json").exists()


def test_record_real_result_rejects_missing_result_manifest_without_writes(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)

    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T12:00:00Z",
    )

    assert report.status == RealResultRecordStatus.FAIL
    assert "result manifest is missing" in report.issues
    _assert_no_optimizer_writes(project_dir)
    _assert_no_prerequisite_check_reports(project_dir)
    persisted = _load_json(project_dir / "reports" / "real_result_record_report.json")
    assert persisted["status"] == "fail"


def test_record_real_result_rejects_missing_metric_manifest_without_writes(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, include_metric_result_manifest=False)

    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T12:00:00Z",
    )

    assert report.status == RealResultRecordStatus.FAIL
    assert any("metric_result_manifest" in issue for issue in report.issues)
    _assert_no_optimizer_writes(project_dir)
    _assert_no_prerequisite_check_reports(project_dir)
