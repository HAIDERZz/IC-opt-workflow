from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.multi_testbench_aggregation import aggregate_multi_testbench_run
from hermes_workflow.package import build_execution_package, create_project_from_template, sha256_file
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


def _inject_three_corner_section(
    project_dir: Path,
    *,
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> None:
    requirement_path = project_dir / "opt_requirement.md"
    text = requirement_path.read_text(encoding="utf-8")
    corners_section = f"""
## Process Corners

```yaml
objective_policy: {objective_policy}
constraint_policy: {constraint_policy}
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: "0"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
```
"""
    requirement_path.write_text(
        text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist"),
        encoding="utf-8",
    )


def _create_ready_multi_corner_multi_testbench_project(
    tmp_path: Path,
    *,
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    _inject_three_corner_section(
        project_dir,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"
    build_execution_package(project_dir, created_at_utc="2026-06-12T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-12T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-12T00:20:00Z")
    _copy_corner_child_inputs(project_dir)
    return project_dir


def _write_process_corners_config(
    project_dir: Path,
    corner_ids: list[str],
    *,
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> None:
    lines = [
        'schema_version: "1.0"',
        f"objective_policy: {objective_policy}",
        f"constraint_policy: {constraint_policy}",
        "corners:",
    ]
    for corner_id in corner_ids:
        lines.extend(
            [
                f"  - id: {corner_id}",
                f"    description: {corner_id} corner",
            ]
        )
    (project_dir / "config" / "process_corners.yaml").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _create_ready_single_testbench_corner_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\n"
        "parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )
    template_text = template_path.read_text(encoding="utf-8")
    for corner_id in corner_ids:
        corner_template = (
            project_dir / "netlists" / "corners" / corner_id / "template.scs"
        )
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-13T00:20:00Z")
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


def _copy_corner_child_inputs(project_dir: Path) -> None:
    for testbench_id in ("cg_nf", "iip3"):
        source = (
            project_dir
            / "runs"
            / "dry_run"
            / "testbenches"
            / testbench_id
            / "input.scs"
        )
        for corner_id in ("tt", "ff", "ss"):
            target = (
                project_dir
                / "runs"
                / "real"
                / "real_001"
                / "testbenches"
                / testbench_id
                / "corners"
                / corner_id
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


def _prepared_child_dir(
    project_dir: Path,
    testbench_id: str | None,
    *,
    run_id: str = "real_001",
    corner_id: str | None = None,
) -> Path:
    child_dir = project_dir / "runs" / "real" / run_id
    if testbench_id is not None:
        child_dir = child_dir / "testbenches" / testbench_id
    if corner_id is not None:
        return child_dir / "corners" / corner_id
    if (child_dir / "metric_extraction_request.json").is_file():
        return child_dir
    corner_requests = sorted(child_dir.glob("corners/*/metric_extraction_request.json"))
    if len(corner_requests) == 1:
        return corner_requests[0].parent
    return child_dir


def _child_metric_request(
    project_dir: Path,
    testbench_id: str | None,
    corner_id: str | None,
    *,
    run_id: str = "real_001",
) -> dict:
    request = _load_json(
        _prepared_child_dir(
            project_dir,
            testbench_id,
            run_id=run_id,
            corner_id=corner_id,
        )
        / "metric_extraction_request.json"
    )
    assert request is not None
    return request


def _write_child_handoff(
    project_dir: Path,
    *,
    testbench_id: str,
    metric_name: str,
    result_status: str = "succeeded",
    metric_status: str = "succeeded",
) -> None:
    child_dir = _prepared_child_dir(project_dir, testbench_id)
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
    child_result_relative = child_dir.relative_to(project_dir).as_posix()
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
    child_dir = _prepared_child_dir(project_dir, testbench_id)
    child_prefix = child_dir.relative_to(project_dir).as_posix()
    child_input = child_dir / "netlist" / "input.scs"
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


def _write_corner_child_handoff(
    project_dir: Path,
    *,
    testbench_id: str | None,
    corner_id: str,
    metric_name: str,
    run_id: str = "real_001",
    value: float | None = 7.5,
    metric_status: str = "succeeded",
    result_status: str = "succeeded",
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    child_dir = run_dir
    if testbench_id is not None:
        child_dir = child_dir / "testbenches" / testbench_id
    child_dir = child_dir / "corners" / corner_id
    child_psf = child_dir / "psf"
    child_metrics = child_dir / "metrics"
    child_psf.mkdir(parents=True, exist_ok=True)
    child_metrics.mkdir(parents=True, exist_ok=True)
    child_input = child_dir / "netlist" / "input.scs"
    child_log = child_dir / "spectre.log"
    child_script = child_metrics / "metric_probe.ocn"
    child_ocean_log = child_metrics / "ocean.log"
    child_scalars = child_metrics / "ocean_scalars.tsv"
    child_spectre_out = child_psf / "spectre.out"
    child_request = _child_metric_request(
        project_dir,
        testbench_id,
        corner_id,
        run_id=run_id,
    )
    metric_rows = []
    for child_metric in child_request["metrics"]:
        is_target_metric = child_metric["name"] == metric_name
        child_status = metric_status if is_target_metric else "succeeded"
        if is_target_metric and metric_status == "succeeded":
            child_value = value
        elif child_metric["unit"] == "s":
            child_value = 20e-12
        elif child_metric["unit"] == "W":
            child_value = 1e-4
        else:
            child_value = 1.0
        metric_rows.append(
            {
                "name": child_metric["name"],
                "status": child_status,
                "value": child_value if child_status == "succeeded" else None,
                "value_text": (
                    f"{child_value:.12g}" if child_status == "succeeded" else "nil"
                ),
                "unit": child_metric["unit"],
                "result": child_metric.get("result"),
                "expression": child_metric["expression"],
                "expression_sha256": child_metric["expression_sha256"],
                "expression_source": child_metric["expression_source"],
                "issues": [] if child_status == "succeeded" else ["nil metric"],
            }
        )
    child_request_path = child_dir / "metric_extraction_request.json"

    child_log.write_text("spectre log\n", encoding="utf-8")
    child_script.write_text("metric probe\n", encoding="utf-8")
    child_ocean_log.write_text("ocean log\n", encoding="utf-8")
    child_spectre_out.write_text("spectre output\n", encoding="utf-8")
    child_scalars.write_text(
        "metric\tstatus\tvalue_text\n"
        f"{metric_name}\t{metric_status}\t"
        f"{'' if value is None else f'{value:.12g}'}\n",
        encoding="utf-8",
    )

    child_prefix = child_dir.relative_to(project_dir).as_posix()
    result_payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": run_id,
        "testbench_id": testbench_id,
        "status": result_status,
        "started_at_utc": "2026-06-12T00:30:00Z",
        "completed_at_utc": "2026-06-12T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "output_format": "psfxl",
            "threads_per_run": 10,
            "timeout_s": 3600,
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": f"{child_prefix}/netlist/input.scs",
        "prepared_input_sha256": sha256_file(child_input),
        "log_file": f"{child_prefix}/spectre.log",
        "artifact_files": [
            f"{child_prefix}/psf",
            f"{child_prefix}/psf/spectre.out",
            f"{child_prefix}/metrics/ocean.log",
            f"{child_prefix}/metrics/ocean_scalars.tsv",
        ],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": f"{child_prefix}/psf",
            "spectre_out": f"{child_prefix}/psf/spectre.out",
        },
        "metric_result_manifest": f"{child_prefix}/metrics/metric_result_manifest.json",
        "notes": "" if result_status == "succeeded" else "child result failed",
    }
    metric_payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": run_id,
        "backend": "spectre_ocean_batch",
        "status": metric_status,
        "request_file": f"{child_prefix}/metric_extraction_request.json",
        "request_sha256": sha256_file(child_request_path),
        "psf_dir": f"{child_prefix}/psf",
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0 if metric_status == "succeeded" else 1,
            "attempts": 1,
            "return_codes": [0 if metric_status == "succeeded" else 1],
            "script_file": f"{child_prefix}/metrics/metric_probe.ocn",
            "script_sha256": sha256_file(child_script),
            "log_file": f"{child_prefix}/metrics/ocean.log",
            "scalar_output_file": f"{child_prefix}/metrics/ocean_scalars.tsv",
        },
        "metrics": metric_rows,
        "child_metric_results": [],
        "issues": [] if metric_status == "succeeded" else ["ocean failed"],
    }

    _write_json(child_dir / "result_manifest.json", result_payload)
    _write_json(child_metrics / "metric_result_manifest.json", metric_payload)


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
    assert any("IIP3" in issue for issue in metric_report.issues)


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


def test_aggregate_multi_corner_feasible_uses_worst_case_corner_metrics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    for corner_id, gain, iip3 in (
        ("tt", 10.0, 20.0),
        ("ff", 6.0, 4.0),
        ("ss", 8.0, 16.0),
    ):
        _write_corner_child_handoff(
            project_dir,
            testbench_id="cg_nf",
            corner_id=corner_id,
            metric_name="MAX_GAIN",
            value=gain,
        )
        _write_corner_child_handoff(
            project_dir,
            testbench_id="iip3",
            corner_id=corner_id,
            metric_name="IIP3",
            value=iip3,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    aggregate_metrics = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    )

    assert report.status == "succeeded"
    assert report.constraint_policy == "all_corners"
    assert report.objective_policy == "worst_case"
    assert report.worst_corner == "ff"
    assert report.selected_corner == "ff"
    assert report.corner_status_counts["feasible"] == 3
    assert {
        metric["name"]: metric["value"]
        for metric in aggregate_metrics["metrics"]
    } == {"MAX_GAIN": 6.0, "IIP3": 4.0}


def test_aggregate_multi_corner_constraint_failure_tracks_worst_corner(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    for corner_id, gain, iip3 in (
        ("tt", 10.0, 20.0),
        ("ff", 4.0, 4.0),
        ("ss", 8.0, 16.0),
    ):
        _write_corner_child_handoff(
            project_dir,
            testbench_id="cg_nf",
            corner_id=corner_id,
            metric_name="MAX_GAIN",
            value=gain,
        )
        _write_corner_child_handoff(
            project_dir,
            testbench_id="iip3",
            corner_id=corner_id,
            metric_name="IIP3",
            value=iip3,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    aggregate_metrics = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    )

    assert report.status == "constraint_failed"
    assert report.worst_corner == "ff"
    assert report.corner_status_counts["constraint_failed"] == 1
    assert {
        metric["name"]: metric["value"]
        for metric in aggregate_metrics["metrics"]
    } == {"MAX_GAIN": 4.0, "IIP3": 4.0}


def test_aggregate_multi_corner_metric_failure_propagates(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    for corner_id in ("tt", "ff", "ss"):
        _write_corner_child_handoff(
            project_dir,
            testbench_id="cg_nf",
            corner_id=corner_id,
            metric_name="MAX_GAIN",
            value=8.0,
        )
        _write_corner_child_handoff(
            project_dir,
            testbench_id="iip3",
            corner_id=corner_id,
            metric_name="IIP3",
            value=None if corner_id == "ff" else 10.0,
            metric_status="failed" if corner_id == "ff" else "succeeded",
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "metric_check_failed"
    assert any("ff" in issue for issue in report.issues)


def test_aggregate_multi_corner_real_failure_propagates(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    for corner_id in ("tt", "ff", "ss"):
        _write_corner_child_handoff(
            project_dir,
            testbench_id="cg_nf",
            corner_id=corner_id,
            metric_name="MAX_GAIN",
            value=8.0,
            result_status="failed" if corner_id == "ss" else "succeeded",
        )
        _write_corner_child_handoff(
            project_dir,
            testbench_id="iip3",
            corner_id=corner_id,
            metric_name="IIP3",
            value=10.0,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "real_check_failed"
    assert any("ss" in issue for issue in report.issues)


def test_aggregate_multi_corner_nominal_policy_ignores_non_nominal_constraint_failure(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(
        tmp_path,
        objective_policy="nominal",
        constraint_policy="nominal",
    )
    for corner_id, gain, iip3 in (
        ("tt", 8.0, 10.0),
        ("ff", 4.0, 10.0),
        ("ss", 9.0, 11.0),
    ):
        _write_corner_child_handoff(
            project_dir,
            testbench_id="cg_nf",
            corner_id=corner_id,
            metric_name="MAX_GAIN",
            value=gain,
        )
        _write_corner_child_handoff(
            project_dir,
            testbench_id="iip3",
            corner_id=corner_id,
            metric_name="IIP3",
            value=iip3,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")
    aggregate_metrics = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    )

    assert report.status == "succeeded"
    assert report.selected_corner == "tt"
    assert report.worst_corner is None
    assert {
        metric["name"]: metric["value"]
        for metric in aggregate_metrics["metrics"]
    } == {"MAX_GAIN": 8.0, "IIP3": 10.0}


def test_aggregate_single_testbench_multi_corner_feasible_uses_worst_case_corner_metrics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_single_testbench_corner_project(
        tmp_path,
        corner_ids=["tt", "ff", "ss"],
    )

    for corner_id, gain in (("tt", 10e-12), ("ff", 4e-12), ("ss", 8e-12)):
        _write_corner_child_handoff(
            project_dir,
            testbench_id=None,
            corner_id=corner_id,
            metric_name="rise",
            value=gain,
        )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "succeeded"
    assert report.constraint_policy == "all_corners"
    assert report.objective_policy == "worst_case"
    assert report.selected_corner == "tt"
    assert report.worst_corner == "tt"
    assert report.corner_objectives == pytest.approx(
        {"tt": 3.0e-15, "ff": 2.4e-15, "ss": 2.8e-15}
    )
    assert report.corner_status_counts == {"feasible": 3}
    assert {metric["name"]: metric["value"] for metric in _load_json(project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json")["metrics"]} == {
        "rise": 10e-12,
        "fall": 20e-12,
        "DC": 1e-4,
    }


def test_aggregate_single_testbench_explicit_one_corner_preserves_configured_semantics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_single_testbench_corner_project(
        tmp_path,
        corner_ids=["ss"],
    )

    _write_corner_child_handoff(
        project_dir,
        testbench_id=None,
        corner_id="ss",
        metric_name="rise",
        value=7e-12,
    )

    report = aggregate_multi_testbench_run(project_dir, run_id="real_001")

    assert report.status == "succeeded"
    assert report.constraint_policy == "all_corners"
    assert report.objective_policy == "worst_case"
    assert report.selected_corner == "ss"
    assert report.worst_corner == "ss"
    assert report.corner_objectives == pytest.approx({"ss": 2.7e-15})
    assert report.corner_status_counts == {"feasible": 1}
    assert [(child.testbench, child.corner) for child in report.child_statuses] == [
        ("default_testbench", "ss")
    ]
