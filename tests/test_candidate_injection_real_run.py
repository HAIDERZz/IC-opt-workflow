from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import prepare_candidate_real_run
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
            or {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "metadata": {"optimizer": "turbo", "evaluation_index": 9},
        },
    )
    return path


def test_prepare_candidate_real_run_rejects_missing_parameter(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters={"FN": "12", "WN": "1.3u", "FP": "2"},
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
            "FN": "12",
            "WN": "1.3u",
            "FP": "2",
            "WP": "2.5u",
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
            {"FN": "1.5", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "FN must be an integer",
        ),
        (
            {"FN": "99", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "FN is outside approved bounds",
        ),
        (
            {"FN": "12", "WN": "1.3 um", "FP": "2", "WP": "2.5u"},
            "WN must use a Spectre-safe attached unit suffix",
        ),
        (
            {"FN": "12", "WN": "1.4u", "FP": "2", "WP": "2.5u"},
            "WN is not aligned to approved step",
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
        "FN": "12",
        "WN": "1.3u",
        "FP": "2",
        "WP": "2.5u",
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
        parameters={"FN": "2", "WN": "0.3u", "FP": "2", "WP": "0.3u"},
    )

    with pytest.raises(ValueError, match="ledger already contains candidate parameters"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_unresolved_prepared_candidate_first(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    second = _candidate_request(
        project_dir,
        candidate_id="candidate_000009",
        parameters={"FN": "13", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
    )

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_candidate_real_run(
            project_dir,
            candidate_file=second,
            run_id="real_003",
        )


def test_prepare_candidate_real_run_rejects_unresolved_prepared_parameters_first(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    second = _candidate_request(project_dir, candidate_id="candidate_000010")

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_candidate_real_run(
            project_dir,
            candidate_file=second,
            run_id="real_003",
        )
