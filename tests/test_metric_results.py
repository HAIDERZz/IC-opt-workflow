from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    MetricResultCheckFlags,
    MetricResultCheckReport,
    MetricResultCheckStatus,
)
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=True) + "\n",
        encoding="utf-8",
    )


def _rewrite_json(path: Path, mutator) -> dict:
    payload = _load_json(path)
    mutator(payload)
    _write_json(path, payload)
    return payload


def _write_result_manifest(
    project_dir: Path,
    *,
    status: str = "succeeded",
    overrides: dict | None = None,
) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    prepared = _load_json(run_dir / "real_run_manifest.json")
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (psf_dir / "spectre.out").write_text("sanitized spectre output\n", encoding="utf-8")
    (metrics_dir / "ocean.log").write_text("sanitized ocean log\n", encoding="utf-8")
    (metrics_dir / "ocean_scalars.tsv").write_text(
        "metric\tstatus\tvalue_text\tunit\texpression_sha256\tissue\n",
        encoding="utf-8",
    )
    (run_dir / "spectre.log").write_text("sanitized run log\n", encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
        "status": status,
        "started_at_utc": "2026-06-02T00:30:00Z",
        "completed_at_utc": "2026-06-02T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared["rendered_input_scs"],
        "prepared_input_sha256": prepared["rendered_input_sha256"],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": "runs/real/real_001/psf",
            "spectre_out": "runs/real/real_001/psf/spectre.out",
        },
        "metric_result_manifest": (
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": [
            "runs/real/real_001/psf/spectre.out",
            "runs/real/real_001/metrics/ocean.log",
            "runs/real/real_001/metrics/ocean_scalars.tsv",
        ],
        "notes": "sanitized fake execution result",
    }
    if overrides:
        payload.update(overrides)
    _write_json(run_dir / "result_manifest.json", payload)
    return payload


def _default_metric_entries(project_dir: Path) -> list[dict]:
    request = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    return [
        {
            "name": request_metric["name"],
            "status": "succeeded",
            "value": 1.25,
            "value_text": "1.25",
            "unit": request_metric["unit"],
            "result": request_metric["result"],
            "expression": request_metric["expression"],
            "expression_sha256": request_metric["expression_sha256"],
            "expression_source": request_metric["expression_source"],
            "issues": [],
        }
        for request_metric in request["metrics"]
    ]


def _write_metric_result_manifest(
    project_dir: Path,
    *,
    overrides: dict | None = None,
    metrics: list[dict] | None = None,
    relative_path: str = "metrics/metric_result_manifest.json",
) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text(
        "sanitized ocean script\n",
        encoding="utf-8",
    )
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
        "metrics": metrics if metrics is not None else _default_metric_entries(project_dir),
        "issues": [],
    }
    if overrides:
        payload.update(overrides)
    result_path = run_dir / relative_path
    result_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(result_path, payload)
    return payload


def _write_valid_result_files(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)


def test_metric_result_check_report_schema_accepts_pass_report() -> None:
    report = MetricResultCheckReport(
        schema_version="1.0",
        status=MetricResultCheckStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        backend="spectre_ocean_batch",
        request_file="runs/real/real_001/metric_extraction_request.json",
        metric_result_manifest=(
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
        psf_dir="runs/real/real_001/psf",
        metrics={},
        checks=MetricResultCheckFlags(
            request_hash_ok=True,
            result_manifest_ok=True,
            metric_manifest_ok=True,
            metric_identity_ok=True,
            formula_hashes_ok=True,
            scalar_values_ok=True,
            artifact_paths_ok=True,
        ),
        issues=[],
    )

    assert report.status == MetricResultCheckStatus.PASS
    assert report.checks.metric_identity_ok is True


def test_metric_result_check_report_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MetricResultCheckReport(
            schema_version="1.0",
            status="pass",
            run_id="real_001",
            candidate_id="real_001",
            backend="spectre_ocean_batch",
            request_file="runs/real/real_001/metric_extraction_request.json",
            metric_result_manifest=(
                "runs/real/real_001/metrics/metric_result_manifest.json"
            ),
            psf_dir="runs/real/real_001/psf",
            metrics={},
            checks={},
            issues=[],
            unexpected=True,
        )


def test_check_metric_results_accepts_valid_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    report = check_metric_results(project_dir)

    persisted = _load_json(project_dir / "reports" / "metric_result_check_report.json")
    assert report.status == MetricResultCheckStatus.PASS
    assert report.run_id == "real_001"
    assert report.backend == "spectre_ocean_batch"
    assert report.checks.request_hash_ok is True
    assert report.checks.result_manifest_ok is True
    assert report.checks.metric_manifest_ok is True
    assert report.checks.metric_identity_ok is True
    assert report.checks.formula_hashes_ok is True
    assert report.checks.scalar_values_ok is True
    assert report.checks.artifact_paths_ok is True
    assert report.issues == []
    assert persisted["status"] == "pass"
    assert persisted["metrics"]["rise"]["status"] == "succeeded"


@pytest.mark.parametrize(
    ("mutator", "expected_issue"),
    [
        (
            lambda payload: payload.update({"request_sha256": "wrong"}),
            "metric request hash mismatch",
        ),
        (
            lambda payload: payload.update({"run_id": "real_002"}),
            "metric result run_id does not match requested run_id",
        ),
        (
            lambda payload: payload.update({"candidate_id": "other_candidate"}),
            "metric result candidate_id does not match request",
        ),
        (
            lambda payload: payload.update({"backend": "other_backend"}),
            "metric backend does not match request",
        ),
        (
            lambda payload: payload.update(
                {"request_file": "runs/real/real_001/other_request.json"}
            ),
            "metric request_file does not match result manifest request",
        ),
        (
            lambda payload: payload.update({"psf_dir": "runs/real/real_001/other_psf"}),
            "metric psf_dir does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"expression": 'value(VT("/OTHER") 1n)'}
            ),
            "metric rise expression does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"expression_sha256": "wrong"}),
            "metric rise expression hash does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"unit": "ps"}),
            "metric rise unit does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"result": "dc"}),
            "metric rise result selector does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"expression_source": "agent_discovered"}
            ),
            "metric rise expression source does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"status": "failed"}),
            "metric rise did not succeed",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"value": math.nan, "value_text": "NaN"}
            ),
            "metric rise value is not finite",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"value": None, "value_text": "nil"}
            ),
            "metric rise value is not finite",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"value": 1.0, "value_text": ""}
            ),
            "metric rise value_text is not a finite scalar",
        ),
        (
            lambda payload: payload["metrics"][0].update(
                {"value": 1.0, "value_text": "srrWave:0x123"}
            ),
            "metric rise value_text looks like a waveform object",
        ),
        (
            lambda payload: payload.update({"psf_dir": "../psf"}),
            "metric artifact path is unsafe: ../psf",
        ),
        (
            lambda payload: payload["ocean"].update({"script_file": "/tmp/probe.ocn"}),
            "metric artifact path is unsafe: /tmp/probe.ocn",
        ),
    ],
)
def test_check_metric_results_rejects_invalid_metric_contract(
    tmp_path: Path,
    mutator,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    mutator(payload)
    result_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    _write_json(result_path, payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues


def test_check_metric_results_rejects_missing_metric(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"] = payload["metrics"][1:]
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    _write_json(result_path / "metric_result_manifest.json", payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "requested metric is missing from metric results: rise" in report.issues


def test_check_metric_results_rejects_extra_metric(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"].append(
        {
            "name": "not_requested",
            "status": "succeeded",
            "value": 1.0,
            "value_text": "1.0",
            "unit": "V",
            "result": "tran",
            "expression": "1.0",
            "expression_sha256": expression_sha256("1.0"),
            "expression_source": "user_approved",
            "issues": [],
        }
    )
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    _write_json(result_path / "metric_result_manifest.json", payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "unrequested metric in metric results: not_requested" in report.issues


def test_check_metric_results_rejects_duplicate_metric(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"].append(dict(payload["metrics"][0]))
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    _write_json(result_path / "metric_result_manifest.json", payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "duplicate metric in metric results: rise" in report.issues


def test_check_metric_results_rejects_non_succeeded_handoff(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    _write_metric_result_manifest(project_dir)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "simulator result is not succeeded" in report.issues
    assert report.checks.result_manifest_ok is False


@pytest.mark.parametrize(
    ("result_overrides", "expected_issue"),
    [
        (
            {"metric_result_manifest": "runs/real/real_001/metrics/other.json"},
            "metric_result_manifest path does not match expected path",
        ),
        (
            {"metric_result_manifest": "../metric_result_manifest.json"},
            "metric_result_manifest path is unsafe: ../metric_result_manifest.json",
        ),
    ],
)
def test_check_metric_results_rejects_result_manifest_metric_path_problems(
    tmp_path: Path,
    result_overrides: dict,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, overrides=result_overrides)
    _write_metric_result_manifest(project_dir)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues


@pytest.mark.parametrize(
    ("path_to_remove", "expected_issue"),
    [
        (
            ("runs", "real", "real_001", "psf"),
            "metric artifact is missing: runs/real/real_001/psf",
        ),
        (
            ("runs", "real", "real_001", "metrics", "ocean.log"),
            "metric artifact is missing: runs/real/real_001/metrics/ocean.log",
        ),
        (
            ("runs", "real", "real_001", "metrics", "ocean_scalars.tsv"),
            "metric artifact is missing: runs/real/real_001/metrics/ocean_scalars.tsv",
        ),
    ],
)
def test_check_metric_results_rejects_missing_declared_artifact(
    tmp_path: Path,
    path_to_remove: tuple[str, ...],
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    target = project_dir / Path(*path_to_remove)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues


def test_check_metric_results_rejects_unsafe_request_file_before_hashing(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(
        project_dir,
        overrides={"request_file": "../metric_extraction_request.json"},
    )
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    _write_json(result_path / "metric_result_manifest.json", payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "metric artifact path is unsafe: ../metric_extraction_request.json" in (
        report.issues
    )
    assert "metric request hash mismatch" in report.issues


def test_check_metric_results_loads_manifest_declared_by_result_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    declared_path = "runs/real/real_001/metrics/declared_metric_result_manifest.json"
    _write_result_manifest(
        project_dir,
        overrides={"metric_result_manifest": declared_path},
    )
    _write_metric_result_manifest(
        project_dir,
        relative_path="metrics/declared_metric_result_manifest.json",
    )

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert report.metric_result_manifest == declared_path
    assert "metric_result_manifest path does not match expected path" in report.issues


def test_check_metric_results_rejects_malformed_metric_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    result_path.mkdir(parents=True, exist_ok=True)
    (result_path / "metric_result_manifest.json").write_text("{", encoding="utf-8")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "metric result manifest is invalid" in report.issues


def test_check_metric_results_rejects_missing_real_run_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    (project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json").unlink()

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "real run manifest is missing" in report.issues
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()


def test_check_metric_results_rejects_malformed_real_run_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    real_manifest_path = (
        project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json"
    )
    real_manifest_path.write_text("{", encoding="utf-8")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "real run manifest is invalid" in report.issues
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()


def test_check_metric_results_rejects_missing_metric_request(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    ).unlink()

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "metric extraction request is missing" in report.issues
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()


@pytest.mark.parametrize(
    ("mutator", "expected_issue"),
    [
        (
            lambda payload: payload.update({"metrics": {"rise": {}}}),
            "metric extraction request is invalid",
        ),
        (
            lambda payload: payload["metrics"][0].pop("expression"),
            "metric extraction request is invalid",
        ),
    ],
)
def test_check_metric_results_rejects_malformed_request_shape(
    tmp_path: Path,
    mutator,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    _rewrite_json(request_path, mutator)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()


@pytest.mark.parametrize(
    ("target_file", "mutator", "expected_issue"),
    [
        (
            "metric_extraction_request.json",
            lambda payload: payload.update(
                {"prepared_input_scs": "runs/real/real_001/other_input.scs"}
            ),
            "metric request prepared_input_scs does not match prepared manifest",
        ),
        (
            "metric_extraction_request.json",
            lambda payload: payload.update({"prepared_input_sha256": "wrong"}),
            "metric request prepared_input_sha256 does not match prepared manifest",
        ),
        (
            "result_manifest.json",
            lambda payload: payload.update(
                {"prepared_input_scs": "runs/real/real_001/other_input.scs"}
            ),
            "result prepared_input_scs does not match prepared manifest",
        ),
        (
            "result_manifest.json",
            lambda payload: payload.update({"prepared_input_sha256": "wrong"}),
            "result prepared_input_sha256 does not match prepared manifest",
        ),
    ],
)
def test_check_metric_results_rejects_prepared_input_identity_drift(
    tmp_path: Path,
    target_file: str,
    mutator,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    target_path = project_dir / "runs" / "real" / "real_001" / target_file
    _rewrite_json(target_path, mutator)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues


def test_check_metric_results_rejects_prepared_input_path_drift(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_001"
    other_input = run_dir / "other_input.scs"
    other_input.write_text("simulator lang=spectre\n// wrong deck\n", encoding="utf-8")
    other_relative = "runs/real/real_001/other_input.scs"
    other_hash = sha256_file(other_input)
    _rewrite_json(
        run_dir / "real_run_manifest.json",
        lambda payload: payload.update(
            {
                "rendered_input_scs": other_relative,
                "rendered_input_sha256": other_hash,
            }
        ),
    )
    _rewrite_json(
        run_dir / "metric_extraction_request.json",
        lambda payload: payload.update(
            {
                "prepared_input_scs": other_relative,
                "prepared_input_sha256": other_hash,
            }
        ),
    )
    _rewrite_json(
        run_dir / "result_manifest.json",
        lambda payload: payload.update(
            {
                "prepared_input_scs": other_relative,
                "prepared_input_sha256": other_hash,
            }
        ),
    )

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "prepared input path does not match expected path" in report.issues
    assert report.checks.metric_identity_ok is False


def test_check_metric_results_rejects_request_drift_after_prepare(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    drifted_expression = 'value(VT("/DRIFTED") 1n)'
    drifted_hash = expression_sha256(drifted_expression)
    _rewrite_json(
        request_path,
        lambda payload: payload["metrics"][0].update(
            {
                "expression": drifted_expression,
                "expression_sha256": drifted_hash,
            }
        ),
    )
    _rewrite_json(
        run_dir / "metrics" / "metric_result_manifest.json",
        lambda payload: (
            payload.update({"request_sha256": sha256_file(request_path)}),
            payload["metrics"][0].update(
                {
                    "expression": drifted_expression,
                    "expression_sha256": drifted_hash,
                }
            ),
        ),
    )

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert (
        "metric extraction request hash does not match prepared manifest"
        in report.issues
    )
    assert report.checks.metric_identity_ok is False


def test_check_metric_results_rejects_invalid_formula_hash_even_when_manifests_agree(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    _rewrite_json(
        request_path,
        lambda payload: payload["metrics"][0].update(
            {"expression_sha256": "wrong"}
        ),
    )
    _rewrite_json(
        run_dir / "metrics" / "metric_result_manifest.json",
        lambda payload: (
            payload.update({"request_sha256": sha256_file(request_path)}),
            payload["metrics"][0].update({"expression_sha256": "wrong"}),
        ),
    )

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "metric rise request expression hash is invalid" in report.issues
    assert "metric rise expression hash is invalid" in report.issues


def test_check_metric_results_rejects_current_prepared_input_hash_drift(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_result_files(project_dir)
    input_path = project_dir / "runs" / "real" / "real_001" / "input.scs"
    input_path.write_text(input_path.read_text(encoding="utf-8") + "\n// drift\n")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "prepared input file hash mismatch" in report.issues
    assert report.checks.metric_identity_ok is False


@pytest.mark.parametrize(
    ("value", "expected_issue"),
    [
        ("1.25", "metric rise value is not a JSON number"),
        (True, "metric rise value is not a JSON number"),
    ],
)
def test_check_metric_results_rejects_non_numeric_json_metric_value(
    tmp_path: Path,
    value,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"][0]["value"] = value
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics"
    _write_json(result_path / "metric_result_manifest.json", payload)

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues
