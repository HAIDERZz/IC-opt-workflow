from __future__ import annotations

import json
import shutil
from pathlib import Path

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run
from hermes_workflow.package import build_execution_package, sha256_file
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealRunResultStatus,
)
from hermes_workflow.requirement_intake import prepare_from_requirement
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports
from tests.test_requirement_intake import _copy_multi_testbench_requirement_project


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _create_ready_multi_testbench_project(tmp_path: Path) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"
    build_execution_package(project_dir, created_at_utc="2026-06-06T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-06T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-06T00:20:00Z")
    _copy_child_inputs(project_dir)
    return project_dir


def _copy_child_inputs(project_dir: Path) -> None:
    for testbench_id in ("cg_nf", "iip3"):
        source = (
            project_dir
            / "runs"
            / "dry_run"
            / "testbenches"
            / testbench_id
            / "input.scs"
        )
        target = (
            project_dir
            / "runs"
            / "real"
            / "real_001"
            / "testbenches"
            / testbench_id
            / "netlist"
            / "input.scs"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _request_metric(project_dir: Path, metric_name: str) -> dict:
    request = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metric_extraction_request.json"
    )
    return next(metric for metric in request["metrics"] if metric["name"] == metric_name)


def _write_child_handoff(
    project_dir: Path,
    *,
    testbench_id: str,
    metric_name: str,
    result_status: str = "succeeded",
    metric_status: str = "succeeded",
) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    child_dir = run_dir / "testbenches" / testbench_id
    child_psf = child_dir / "psf"
    child_metrics = child_dir / "metrics"
    child_psf.mkdir(parents=True, exist_ok=True)
    child_metrics.mkdir(parents=True, exist_ok=True)
    child_input = child_dir / "netlist" / "input.scs"
    child_spectre_out = child_psf / "spectre.out"
    child_log = child_dir / "spectre.log"
    child_script = child_metrics / "metric_probe.ocn"
    child_ocean_log = child_metrics / "ocean.log"
    child_scalars = child_metrics / "ocean_scalars.tsv"
    child_spectre_out.write_text(f"{testbench_id} spectre out\n", encoding="utf-8")
    child_log.write_text(f"{testbench_id} spectre log\n", encoding="utf-8")
    child_script.write_text(f"{testbench_id} ocean script\n", encoding="utf-8")
    child_ocean_log.write_text(f"{testbench_id} ocean log\n", encoding="utf-8")
    child_scalars.write_text("metric\tstatus\tvalue_text\n", encoding="utf-8")
    child_request = _child_request_payload(
        project_dir,
        testbench_id=testbench_id,
        metric_name=metric_name,
    )
    child_request_path = child_dir / "metric_extraction_request.json"
    _write_json(child_request_path, child_request)
    child_result_relative = f"runs/real/real_001/testbenches/{testbench_id}"
    _write_json(
        child_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": "real_001",
            "candidate_id": "real_001",
            "status": result_status,
            "started_at_utc": "2026-06-06T00:30:00Z",
            "completed_at_utc": "2026-06-06T00:31:00Z",
            "simulator": {
                "engine": "spectre_x",
                "preset": "ax",
                "output_format": "psfxl",
                "threads_per_run": 10,
                "timeout_s": 3600,
                "command_label": "external_spectre_run",
            },
            "prepared_input_scs": f"{child_result_relative}/netlist/input.scs",
            "prepared_input_sha256": sha256_file(child_input),
            "log_file": f"{child_result_relative}/spectre.log",
            "artifact_files": [
                f"{child_result_relative}/psf/spectre.out",
                f"{child_result_relative}/metrics/ocean.log",
                f"{child_result_relative}/metrics/ocean_scalars.tsv",
            ],
            "result_data": {
                "kind": "spectre_psf",
                "psf_dir": f"{child_result_relative}/psf",
                "spectre_out": f"{child_result_relative}/psf/spectre.out",
            },
            "metric_result_manifest": (
                f"{child_result_relative}/metrics/metric_result_manifest.json"
            ),
        },
    )
    request_metric = _request_metric(project_dir, metric_name)
    value = 7.5 if metric_status == "succeeded" else None
    value_text = "7.5" if metric_status == "succeeded" else "nil"
    _write_json(
        child_metrics / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": "real_001",
            "candidate_id": "real_001",
            "backend": "spectre_ocean_batch",
            "status": metric_status,
            "request_file": f"{child_result_relative}/metric_extraction_request.json",
            "request_sha256": sha256_file(child_request_path),
            "psf_dir": f"{child_result_relative}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "return_code": 0,
                "script_file": f"{child_result_relative}/metrics/metric_probe.ocn",
                "script_sha256": sha256_file(child_script),
                "log_file": f"{child_result_relative}/metrics/ocean.log",
                "scalar_output_file": f"{child_result_relative}/metrics/ocean_scalars.tsv",
            },
            "metrics": [
                {
                    "name": metric_name,
                    "status": metric_status,
                    "value": value,
                    "value_text": value_text,
                    "unit": request_metric["unit"],
                    "result": request_metric.get("result"),
                    "expression": request_metric["expression"],
                    "expression_sha256": request_metric["expression_sha256"],
                    "expression_source": request_metric["expression_source"],
                    "issues": [] if metric_status == "succeeded" else ["nil metric"],
                }
            ],
            "issues": [] if metric_status == "succeeded" else ["nil metric"],
        },
    )


def _child_request_payload(
    project_dir: Path,
    *,
    testbench_id: str,
    metric_name: str,
) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    request = _load_json(run_dir / "metric_extraction_request.json")
    metric = _request_metric(project_dir, metric_name)
    child_prefix = f"runs/real/real_001/testbenches/{testbench_id}"
    child_input = run_dir / "testbenches" / testbench_id / "netlist" / "input.scs"
    payload = dict(request)
    payload.update(
        {
            "prepared_input_scs": f"{child_prefix}/netlist/input.scs",
            "prepared_input_sha256": sha256_file(child_input),
            "expected_psf_dir": f"{child_prefix}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "script_file": f"{child_prefix}/metrics/metric_probe.ocn",
                "log_file": f"{child_prefix}/metrics/ocean.log",
                "scalar_output_file": f"{child_prefix}/metrics/ocean_scalars.tsv",
            },
            "metrics": [metric],
        }
    )
    return payload


def test_aggregate_multi_testbench_child_manifests_pass_existing_checks(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_testbench_project(tmp_path)
    _write_child_handoff(project_dir, testbench_id="cg_nf", metric_name="MAX_GAIN")
    _write_child_handoff(project_dir, testbench_id="iip3", metric_name="IIP3")

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)

    aggregate_metrics = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    aggregate_result = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    assert report.status == "succeeded"
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
    assert [metric["name"] for metric in aggregate_metrics["metrics"]] == [
        "MAX_GAIN",
        "IIP3",
    ]
    assert [child["testbench"] for child in aggregate_result["child_results"]] == [
        "cg_nf",
        "iip3",
    ]
    assert [child["testbench"] for child in aggregate_metrics["child_metric_results"]] == [
        "cg_nf",
        "iip3",
    ]


def test_aggregate_multi_testbench_metric_failure_fails_metric_check_only(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_testbench_project(tmp_path)
    _write_child_handoff(project_dir, testbench_id="cg_nf", metric_name="MAX_GAIN")
    _write_child_handoff(
        project_dir,
        testbench_id="iip3",
        metric_name="IIP3",
        metric_status="failed",
    )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)

    aggregate_result = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    assert report.status == "metric_check_failed"
    assert aggregate_result["status"] == RealRunResultStatus.SUCCEEDED
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    assert "metric IIP3 did not succeed" in metric_report.issues


def test_aggregate_multi_testbench_real_failure_marks_candidate_result_failed(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_testbench_project(tmp_path)
    _write_child_handoff(project_dir, testbench_id="cg_nf", metric_name="MAX_GAIN")
    _write_child_handoff(
        project_dir,
        testbench_id="iip3",
        metric_name="IIP3",
        result_status="failed",
    )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)

    aggregate_result = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    assert report.status == "real_check_failed"
    assert aggregate_result["status"] == RealRunResultStatus.FAILED
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    assert "simulator result is not succeeded" in metric_report.issues
