from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import prepare_candidate_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealResultRecordStatus,
    RealRunCheckStatus,
)
from hermes_workflow.result_handoff import check_real_run
from tests.real_run_cluster_helpers import (
    create_ready_project as _create_ready_project,
    extra_candidate_parameters,
    invalid_candidate_cases,
    load_json as _load_json,
    missing_candidate_parameters,
    record_real_001 as _record_real_001,
    valid_candidate_parameters,
    write_json as _write_json,
    write_metric_result_manifest,
    write_result_manifest,
)


def _candidate_request(
    project_dir: Path,
    *,
    candidate_id: str = "candidate_000009",
    parameters: dict[str, str] | None = None,
    source: str = "optimizer_turbo_suggestion",
) -> Path:
    path = project_dir / "candidate_requests" / f"{candidate_id}.json"
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "source": source,
            "parameters": parameters or valid_candidate_parameters(project_dir),
            "metadata": {"optimizer": "turbo", "evaluation_index": 9},
        },
    )
    return path


def _write_candidate_result_manifest(project_dir: Path, *, run_id: str) -> None:
    write_result_manifest(project_dir, run_id=run_id)


def _write_candidate_metric_result_manifest(project_dir: Path, *, run_id: str) -> None:
    write_metric_result_manifest(project_dir, run_id=run_id)


def _write_abandon_decision(project_dir: Path, *, run_id: str) -> None:
    _write_json(
        project_dir / "runs" / "real" / run_id / "recovery_decision.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": _load_json(
                project_dir / "runs" / "real" / run_id / "candidate.json"
            )["candidate_id"],
            "decision": "abandon_candidate",
            "reason": "test resolved prepared package",
            "decided_at_utc": "2026-06-04T00:05:00Z",
            "issues": [],
        },
    )


def test_prepare_candidate_real_run_rejects_missing_parameter(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters=missing_candidate_parameters(project_dir),
    )

    with pytest.raises(
        ValueError,
        match="candidate parameters must match variables.yaml",
    ):
        prepare_candidate_real_run(project_dir, candidate_file=request)

    assert not (project_dir / "runs" / "real" / "real_002").exists()


def test_prepare_candidate_real_run_rejects_extra_parameter(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters=extra_candidate_parameters(project_dir),
    )

    with pytest.raises(
        ValueError,
        match="candidate parameters must match variables.yaml",
    ):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_bad_candidate_id(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, candidate_id="../bad")

    with pytest.raises(ValueError, match="candidate_id must be a safe identifier"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_invalid_values(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    for parameters, message in invalid_candidate_cases(project_dir):
        request = _candidate_request(project_dir, parameters=parameters)
        with pytest.raises(ValueError, match=re.escape(message)):
            prepare_candidate_real_run(project_dir, candidate_file=request)
        request.unlink()


def test_prepare_candidate_real_run_writes_real_002_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    variables_path = project_dir / "config" / "variables.yaml"
    variables_before = variables_path.read_text(encoding="utf-8")

    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        created_at_utc="2026-06-04T00:00:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_002"
    candidate = _load_json(run_dir / "candidate.json")
    copied_request = _load_json(run_dir / "candidate_request.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")
    metric_request = _load_json(run_dir / "metric_extraction_request.json")

    assert package.run_id == "real_002"
    assert copied_request["candidate_id"] == "candidate_000009"
    assert candidate["candidate_id"] == "candidate_000009"
    assert candidate["source"] == "explicit_candidate_request"
    assert candidate["requested_source"] == "optimizer_turbo_suggestion"
    assert candidate["parameters"] == valid_candidate_parameters(project_dir)
    assert candidate["candidate_request_file"] == (
        "runs/real/real_002/candidate_request.json"
    )
    assert candidate["candidate_request_sha256"] == sha256_file(
        run_dir / "candidate_request.json"
    )
    assert manifest["run_id"] == "real_002"
    assert manifest["candidate_id"] == "candidate_000009"
    assert manifest["candidate_source"] == "explicit_candidate_request"
    assert manifest["selection_policy"] == "explicit_candidate_injection"
    assert manifest["candidate_request_file"] == (
        "runs/real/real_002/candidate_request.json"
    )
    assert manifest["candidate_request_sha256"] == candidate["candidate_request_sha256"]
    assert manifest["previous_evaluations"] == 1
    assert manifest["ledger_snapshot_sha256"]
    assert manifest["optimizer_state_sha256"]
    assert metric_request["run_id"] == "real_002"
    assert metric_request["candidate_id"] == "candidate_000009"
    assert (run_dir / "netlist" / "input.scs").exists()
    assert variables_path.read_text(encoding="utf-8") == variables_before


def test_prepare_candidate_real_run_rejects_real_001_override(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)

    with pytest.raises(
        ValueError,
        match="prepare-candidate-real-run cannot target real_001",
    ):
        prepare_candidate_real_run(project_dir, candidate_file=request, run_id="real_001")


def test_prepare_candidate_real_run_rejects_existing_override_run_dir(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_009"
    run_dir.mkdir(parents=True)

    with pytest.raises(
        FileExistsError,
        match="candidate real run directory already exists",
    ):
        prepare_candidate_real_run(project_dir, candidate_file=request, run_id="real_009")

    assert not (run_dir / "real_run_manifest.json").exists()


def test_prepare_candidate_real_run_rejects_duplicate_candidate_id_from_ledger(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, candidate_id="real_001")

    with pytest.raises(ValueError, match="ledger already contains candidate_id real_001"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_duplicate_parameter_tuple_from_ledger(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first_candidate = _load_json(
        project_dir / "runs" / "real" / "real_001" / "candidate.json"
    )
    request = _candidate_request(
        project_dir,
        parameters=first_candidate["parameters"],
    )

    with pytest.raises(ValueError, match="ledger already contains candidate parameters"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_duplicate_prepared_candidate_id(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    _write_abandon_decision(project_dir, run_id="real_002")
    second = _candidate_request(
        project_dir,
        candidate_id="candidate_000009",
        parameters=valid_candidate_parameters(
            project_dir, int_value="4", width_value="0.4u"
        ),
    )

    with pytest.raises(
        ValueError,
        match="prepared run already contains candidate_id candidate_000009",
    ):
        prepare_candidate_real_run(
            project_dir,
            candidate_file=second,
            run_id="real_003",
        )


def test_prepare_candidate_real_run_rejects_duplicate_prepared_parameters(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    _write_abandon_decision(project_dir, run_id="real_002")
    second = _candidate_request(project_dir, candidate_id="candidate_000010")

    with pytest.raises(ValueError, match="prepared run already contains candidate parameters"):
        prepare_candidate_real_run(
            project_dir,
            candidate_file=second,
            run_id="real_003",
        )


def test_prepare_candidate_real_run_rejects_unresolved_distinct_prepared_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    second = _candidate_request(
        project_dir,
        candidate_id="candidate_000010",
        parameters=valid_candidate_parameters(
            project_dir, int_value="4", width_value="0.4u"
        ),
    )

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_candidate_real_run(
            project_dir,
            candidate_file=second,
            run_id="real_003",
        )


def test_prepare_candidate_real_run_cleans_up_after_write_failure(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    (project_dir / "netlists" / "exported" / "sidecar.scs").symlink_to(
        project_dir / "netlists" / "exported" / "input.scs"
    )

    with pytest.raises(
        FileExistsError,
        match="exported netlist bundle must not contain symlinks",
    ):
        prepare_candidate_real_run(project_dir, candidate_file=request)

    assert not (project_dir / "runs" / "real" / "real_002").exists()


def test_prepare_candidate_real_run_cli_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)

    result = CliRunner().invoke(
        app,
        [
            "prepare-candidate-real-run",
            str(project_dir),
            "--candidate-file",
            str(request),
        ],
    )

    assert result.exit_code == 0
    assert "candidate real run package prepared" in result.output
    assert "run: runs/real/real_002" in result.output
    assert "manifest: runs/real/real_002/real_run_manifest.json" in result.output
    assert "candidate: runs/real/real_002/candidate.json" in result.output
    assert (
        "candidate request: runs/real/real_002/candidate_request.json"
        in result.output
    )


def test_prepare_candidate_real_run_cli_rejects_unresolved_baseline(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    request = _candidate_request(project_dir)

    result = CliRunner().invoke(
        app,
        [
            "prepare-candidate-real-run",
            str(project_dir),
            "--candidate-file",
            str(request),
        ],
    )

    assert result.exit_code == 1
    assert "unresolved real run exists" in result.output


def test_candidate_package_accepts_fake_c7_result_and_records(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        created_at_utc="2026-06-04T00:00:00Z",
    )
    _write_candidate_result_manifest(project_dir, run_id=package.run_id)
    _write_candidate_metric_result_manifest(project_dir, run_id=package.run_id)

    real_report = check_real_run(project_dir, run_id=package.run_id)
    metric_report = check_metric_results(project_dir, run_id=package.run_id)
    record_report = record_real_result(
        project_dir,
        run_id=package.run_id,
        recorded_at_utc="2026-06-04T00:40:00Z",
    )

    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
    assert record_report.status == RealResultRecordStatus.PASS
    assert record_report.candidate_id == "candidate_000009"
    ledger_rows = [
        json.loads(line)
        for line in (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["run_id"] for row in ledger_rows] == ["real_001", "real_002"]
    assert ledger_rows[1]["candidate_id"] == "candidate_000009"
    assert ledger_rows[1]["parameters"] == valid_candidate_parameters(project_dir)
