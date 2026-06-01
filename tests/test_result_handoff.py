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
