from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    RealRunCheckFlags,
    RealRunCheckReport,
    RealRunCheckStatus,
    RealRunResultStatus,
)
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    return project_dir


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")


def _approve_project(project_dir: Path) -> None:
    build_execution_package(project_dir, created_at_utc="2026-06-01T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"


def _prepare_real_run_project(tmp_path: Path):
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:20:00Z",
    )
    return project_dir, package


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_run_check_report_schema_accepts_pass_report() -> None:
    report = RealRunCheckReport(
        schema_version="1.0",
        status=RealRunCheckStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        result_status=RealRunResultStatus.SUCCEEDED,
        real_run_manifest="runs/real/real_001/real_run_manifest.json",
        result_manifest="runs/real/real_001/result_manifest.json",
        prepared_input_scs="runs/real/real_001/input.scs",
        log_file="runs/real/real_001/spectre.log",
        artifact_files=["runs/real/real_001/artifacts/psf_summary.txt"],
        checks=RealRunCheckFlags(
            prepared_manifest_ok=True,
            candidate_ok=True,
            result_manifest_ok=True,
            prepared_input_hash_ok=True,
            artifact_paths_ok=True,
        ),
        issues=[],
    )

    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.SUCCEEDED
    assert report.checks.artifact_paths_ok is True


def test_real_run_check_report_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RealRunCheckReport(
            schema_version="1.0",
            status="pass",
            run_id="real_001",
            candidate_id="real_001",
            result_status="succeeded",
            real_run_manifest="runs/real/real_001/real_run_manifest.json",
            result_manifest="runs/real/real_001/result_manifest.json",
            prepared_input_scs="runs/real/real_001/input.scs",
            log_file="runs/real/real_001/spectre.log",
            artifact_files=[],
            checks={
                "prepared_manifest_ok": True,
                "candidate_ok": True,
                "result_manifest_ok": True,
                "prepared_input_hash_ok": True,
                "artifact_paths_ok": True,
            },
            issues=[],
            unexpected=True,
        )


def _write_result_handoff(
    project_dir: Path,
    *,
    status: str = "succeeded",
    overrides: dict | None = None,
) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spectre.log").write_text(
        "sanitized spectre log\nanalysis completed\n",
        encoding="utf-8",
    )
    (artifacts_dir / "psf_summary.txt").write_text(
        "sanitized artifact summary\n",
        encoding="utf-8",
    )
    prepared_manifest = _load_json(run_dir / "real_run_manifest.json")
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": prepared_manifest["candidate_id"],
        "status": status,
        "started_at_utc": "2026-06-01T00:30:00Z",
        "completed_at_utc": "2026-06-01T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared_manifest["rendered_input_scs"],
        "prepared_input_sha256": prepared_manifest["rendered_input_sha256"],
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": ["runs/real/real_001/artifacts/psf_summary.txt"],
        "notes": "sanitized fake execution result",
    }
    if overrides:
        payload.update(overrides)
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def test_check_real_run_accepts_valid_succeeded_handoff(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir)

    report = check_real_run(project_dir)

    report_path = project_dir / "reports" / "real_run_check_report.json"
    persisted = _load_json(report_path)
    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.SUCCEEDED
    assert report.run_id == "real_001"
    assert report.candidate_id == "real_001"
    assert report.real_run_manifest == "runs/real/real_001/real_run_manifest.json"
    assert report.result_manifest == "runs/real/real_001/result_manifest.json"
    assert report.prepared_input_scs == "runs/real/real_001/input.scs"
    assert report.log_file == "runs/real/real_001/spectre.log"
    assert report.artifact_files == ["runs/real/real_001/artifacts/psf_summary.txt"]
    assert report.checks.prepared_manifest_ok is True
    assert report.checks.candidate_ok is True
    assert report.checks.result_manifest_ok is True
    assert report.checks.prepared_input_hash_ok is True
    assert report.checks.artifact_paths_ok is True
    assert report.issues == []
    assert persisted["status"] == "pass"
    assert persisted["result_status"] == "succeeded"


def test_check_real_run_accepts_valid_failed_handoff(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, status="failed")

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.FAILED
    assert report.issues == []


@pytest.mark.parametrize(
    ("overrides", "expected_issue"),
    [
        (
            {"run_id": "real_002"},
            "result run_id does not match requested run_id",
        ),
        (
            {"candidate_id": "other_candidate"},
            "result candidate_id does not match prepared candidate",
        ),
        (
            {"prepared_input_scs": "runs/real/real_001/other.scs"},
            "result prepared_input_scs does not match prepared manifest",
        ),
        (
            {"prepared_input_sha256": "not-the-prepared-hash"},
            "prepared input hash mismatch",
        ),
        (
            {"status": "unknown"},
            "result status is invalid: unknown",
        ),
    ],
)
def test_check_real_run_reports_manifest_mismatches(
    tmp_path: Path,
    overrides: dict,
    expected_issue: str,
) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, overrides=overrides)

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert expected_issue in report.issues
    assert (project_dir / "reports" / "real_run_check_report.json").exists()


def test_check_real_run_reports_missing_result_manifest(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert report.candidate_id is None
    assert report.result_status is None
    assert "result manifest is missing" in report.issues


def test_check_real_run_reports_malformed_result_manifest(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_path.write_text("{", encoding="utf-8")

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "result manifest is invalid" in report.issues


def test_check_real_run_reports_prepared_input_hash_drift(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir)
    input_path = project_dir / "runs" / "real" / "real_001" / "input.scs"
    input_path.write_text(
        input_path.read_text(encoding="utf-8") + "\n// changed after prepare-real-run\n",
        encoding="utf-8",
    )

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "prepared input hash mismatch" in report.issues
    assert report.checks.prepared_input_hash_ok is False


@pytest.mark.parametrize(
    ("artifact_value", "expected_issue"),
    [
        ("/tmp/spectre.log", "result artifact path is unsafe: /tmp/spectre.log"),
        (
            "runs/real/real_001/../spectre.log",
            "result artifact path is unsafe: runs/real/real_001/../spectre.log",
        ),
        (
            "runs/real/real_002/spectre.log",
            "result artifact path is unsafe: runs/real/real_002/spectre.log",
        ),
    ],
)
def test_check_real_run_rejects_unsafe_log_paths(
    tmp_path: Path,
    artifact_value: str,
    expected_issue: str,
) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, overrides={"log_file": artifact_value})

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert expected_issue in report.issues
    assert report.checks.artifact_paths_ok is False


def test_check_real_run_rejects_missing_declared_artifact(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(
        project_dir,
        overrides={
            "artifact_files": ["runs/real/real_001/artifacts/missing.raw"],
        },
    )

    report = check_real_run(project_dir)

    assert (
        "result artifact is missing: runs/real/real_001/artifacts/missing.raw"
        in report.issues
    )
    assert report.status == RealRunCheckStatus.FAIL
    assert report.checks.artifact_paths_ok is False
