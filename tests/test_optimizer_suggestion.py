from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_suggestion import suggest_candidate_request
from hermes_workflow.real_run import prepare_candidate_real_run
from tests.test_next_real_run import _create_ready_project, _load_json, _record_real_001


def test_suggest_candidate_writes_initialization_request(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000002",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    payload = _load_json(result.output_path)
    assert result.candidate_id == "candidate_000002"
    assert result.selection_mode == "initialization_fallback"
    assert payload["schema_version"] == "1.0"
    assert payload["candidate_id"] == "candidate_000002"
    assert payload["source"] == "optimizer_initialization_suggestion"
    assert payload["parameters"] != {"FN": "2", "WN": "0.3u", "FP": "2", "WP": "0.3u"}
    assert payload["metadata"]["selection_mode"] == "initialization_fallback"
    assert payload["metadata"]["evaluation_index"] == 2
    assert payload["metadata"]["ledger_rows_seen"] == 1
    assert len(payload["metadata"]["ledger_sha256"]) == 64
    assert len(payload["metadata"]["optimizer_state_sha256"]) == 64


def test_suggested_request_can_prepare_candidate_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000002",
        created_at_utc="2026-06-04T00:00:00Z",
    )
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=result.output_path,
        run_id="real_002",
        created_at_utc="2026-06-04T00:01:00Z",
    )

    assert package.run_id == "real_002"
    candidate = _load_json(project_dir / "runs" / "real" / "real_002" / "candidate.json")
    assert candidate["candidate_id"] == "candidate_000002"
    assert candidate["source"] == "explicit_candidate_request"


def test_suggest_candidate_rejects_existing_output(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    output = project_dir / "candidate_requests" / "candidate_000002.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="candidate request already exists"):
        suggest_candidate_request(project_dir, candidate_id="candidate_000002")

    assert output.read_text(encoding="utf-8") == "{}\n"


def test_suggest_candidate_rejects_bad_candidate_id_before_write(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    with pytest.raises(ValueError, match="candidate_id must be a safe identifier"):
        suggest_candidate_request(project_dir, candidate_id="../bad")

    assert not (project_dir / "candidate_requests").exists()


def test_suggest_candidate_rejects_missing_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    shutil.rmtree(project_dir / "runs" / "real")

    with pytest.raises(ValueError, match="ledger is missing"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_missing_optimizer_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    (project_dir / "state" / "optimizer_state.json").unlink()

    with pytest.raises(ValueError, match="optimizer state is missing"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_completed_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["status"] = "completed"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="optimizer state is completed"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_max_evaluations_reached(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "max_evaluations: 100",
            "max_evaluations: 8",
        ),
        encoding="utf-8",
    )
    ledger = project_dir / "ledger" / "experiment_ledger.jsonl"
    first_row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    rows = []
    for index in range(8):
        row = dict(first_row)
        row["candidate_id"] = f"seed_{index + 1:03d}"
        row["parameters"] = {
            "FN": str(2 + index),
            "WN": f"{0.3 + 0.2 * index:g}u",
            "FP": str(2 + index),
            "WP": f"{0.3 + 0.2 * index:g}u",
        }
        rows.append(row)
    ledger.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["current_evaluations"] = 8
    state["max_evaluations"] = 8
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="optimizer maximum evaluations"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_unresolved_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    unresolved = project_dir / "runs" / "real" / "real_002"
    unresolved.mkdir(parents=True)
    (unresolved / "real_run_manifest.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unresolved real run exists"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_uses_turbo_when_enough_finite_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    ledger = project_dir / "ledger" / "experiment_ledger.jsonl"
    first_row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    rows = []
    for index in range(8):
        row = dict(first_row)
        row["candidate_id"] = f"seed_{index + 1:03d}"
        row["parameters"] = {
            "FN": str(2 + index),
            "WN": f"{0.3 + 0.2 * index:g}u",
            "FP": str(2 + index),
            "WP": f"{0.3 + 0.2 * index:g}u",
        }
        row["objective"] = float(100 - index)
        rows.append(row)
    ledger.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    state["current_evaluations"] = 8
    (project_dir / "state" / "optimizer_state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "hermes_workflow.optimizer_suggestion._suggest_turbo_raw_candidate",
        lambda *args, **kwargs: [12.0, 1.3, 2.0, 2.5],
    )

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000009",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    payload = _load_json(result.output_path)
    assert result.selection_mode == "turbo"
    assert payload["source"] == "optimizer_turbo_suggestion"
    assert payload["parameters"] == {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"}
    assert payload["metadata"]["selection_mode"] == "turbo"
    assert payload["metadata"]["finite_observations"] == 8


def test_suggest_candidate_cli_writes_request(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "suggest-candidate",
            str(project_dir),
            "--candidate-id",
            "candidate_000002",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "candidate request written:" in result.output
    request = project_dir / "candidate_requests" / "candidate_000002.json"
    assert request.exists()


def test_suggest_candidate_cli_output_can_prepare_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()
    request = project_dir / "requests" / "next.json"

    result = runner.invoke(
        app,
        [
            "suggest-candidate",
            str(project_dir),
            "--candidate-id",
            "candidate_000002",
            "--output",
            str(request),
        ],
    )

    assert result.exit_code == 0, result.output
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        run_id="real_002",
        created_at_utc="2026-06-04T00:01:00Z",
    )
    assert package.run_id == "real_002"


def test_suggest_candidate_does_not_overwrite_if_file_appears_during_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    output = project_dir / "candidate_requests" / "candidate_000002.json"

    original_link = __import__("os").link

    def competing_link(src: str, dst: str) -> None:
        output.write_text("{}\n", encoding="utf-8")
        original_link(src, dst)

    monkeypatch.setattr("hermes_workflow.optimizer_suggestion.os.link", competing_link)

    with pytest.raises(FileExistsError, match="candidate request already exists"):
        suggest_candidate_request(project_dir, candidate_id="candidate_000002")

    assert output.read_text(encoding="utf-8") == "{}\n"
    assert not list(output.parent.glob(".candidate_000002.json.*"))
