from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.optimizer_artifacts import (
    EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_REPORT_RELATIVE,
    REPORT_RELATIVE,
    load_optimizer_artifacts,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_loader_prefers_backend_neutral_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / REPORT_RELATIVE,
        {"status": "completed", "backend": "openbox", "evaluation_count": 1},
    )
    _write_jsonl(
        tmp_path / EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "feasible"}],
    )
    _write_json(
        tmp_path / LEGACY_NATIVE_REPORT_RELATIVE,
        {"status": "completed", "backend": "turbo", "evaluation_count": 99},
    )
    _write_jsonl(
        tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "legacy"}],
    )

    artifacts = load_optimizer_artifacts(tmp_path, [])

    assert artifacts.source == "backend_neutral"
    assert artifacts.report["backend"] == "openbox"
    assert artifacts.traces == [{"evaluation_index": 1, "status": "feasible"}]


def test_loader_falls_back_to_legacy_native_turbo_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / LEGACY_NATIVE_REPORT_RELATIVE,
        {"status": "completed", "evaluation_count": 1},
    )
    _write_jsonl(
        tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "feasible"}],
    )

    artifacts = load_optimizer_artifacts(tmp_path, [])

    assert artifacts.source == "legacy_native_turbo"
    assert artifacts.report["status"] == "completed"
    assert artifacts.traces[0]["status"] == "feasible"
