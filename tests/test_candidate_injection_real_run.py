from __future__ import annotations

import json
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
from tests.test_next_real_run import _create_ready_project, _record_real_001


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
            "parameters": parameters
            or {"F": "24", "W": "0.8u", "L": "40n", "VB_LO": "320m"},
            "metadata": {"optimizer": "turbo", "evaluation_index": 9},
        },
    )
    return path


def _write_candidate_result_manifest(project_dir: Path, *, run_id: str) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = _load_json(run_dir / "real_run_manifest.json")
    candidate = _load_json(run_dir / "candidate.json")
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
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
    (run_dir / "spectre.stdout").write_text("sanitized stdout\n", encoding="utf-8")
    (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    _write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": candidate["candidate_id"],
            "status": "succeeded",
            "started_at_utc": "2026-06-04T00:30:00Z",
            "completed_at_utc": "2026-06-04T00:31:00Z",
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


def _write_candidate_metric_result_manifest(project_dir: Path, *, run_id: str) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    candidate = _load_json(run_dir / "candidate.json")
    metrics_dir = run_dir / "metrics"
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = {"NF_3G": 6.5}
    _write_json(
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
        parameters={"F": "24", "W": "0.8u", "L": "40n"},
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
        parameters={
            "F": "24",
            "W": "0.8u",
            "L": "40n",
            "VB_LO": "320m",
            "EXTRA": "1",
        },
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


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
            (
                {"F": "20.5", "W": "0.8u", "L": "40n", "VB_LO": "320m"},
                "F must be an integer",
            ),
            (
                {"F": "99", "W": "0.8u", "L": "40n", "VB_LO": "320m"},
                "F is outside approved bounds",
            ),
            (
                {"F": "24", "W": "0.8 um", "L": "40n", "VB_LO": "320m"},
                "W must use a Spectre-safe attached unit suffix",
            ),
            (
                {"F": "24", "W": " 0.8u ", "L": "40n", "VB_LO": "320m"},
                "W must use compact Spectre-safe formatting",
            ),
            (
                {"F": "24", "W": "0.7u", "L": "40n", "VB_LO": "320m"},
                "W is not aligned to approved step",
            ),
        ],
    )
def test_prepare_candidate_real_run_rejects_invalid_values(
    tmp_path: Path,
    parameters: dict[str, str],
    message: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, parameters=parameters)

    with pytest.raises(ValueError, match=message):
        prepare_candidate_real_run(project_dir, candidate_file=request)


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
    assert candidate["parameters"] == {
        "F": "24",
        "W": "0.8u",
        "L": "40n",
        "VB_LO": "320m",
    }
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
    request = _candidate_request(
        project_dir,
        parameters={"F": "20", "W": "0.6u", "L": "30n", "VB_LO": "280m"},
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
        parameters={"F": "26", "W": "1.0u", "L": "30n", "VB_LO": "360m"},
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
        parameters={"F": "28", "W": "1.0u", "L": "30n", "VB_LO": "360m"},
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
    assert ledger_rows[1]["parameters"] == {
        "F": "24",
        "W": "0.8u",
        "L": "40n",
        "VB_LO": "320m",
    }
