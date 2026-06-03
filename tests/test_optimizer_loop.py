from __future__ import annotations

import importlib.util
import json
import re
from types import SimpleNamespace
from pathlib import Path

from hermes_workflow.optimizer_loop import (
    ADAPTER_FAILED,
    ADAPTER_SUCCEEDED,
    METRIC_CHECK_FAILED,
    RECORDED,
    OptimizerLoopAdapterResult,
    run_single_optimizer_cycle,
)
from tests.test_candidate_injection_real_run import (
    _write_candidate_metric_result_manifest,
    _write_candidate_result_manifest,
)
from tests.test_next_real_run import _create_ready_project, _record_real_001


def _load_loop_tool():
    tool_path = Path(__file__).resolve().parents[1] / "tools" / "run_real_optimizer_loop.py"
    spec = importlib.util.spec_from_file_location("run_real_optimizer_loop", tool_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ledger_rows(project_dir: Path) -> list[dict]:
    ledger = project_dir / "ledger" / "experiment_ledger.jsonl"
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_success_adapter(project_dir: Path, run_id: str) -> OptimizerLoopAdapterResult:
    _write_candidate_result_manifest(project_dir, run_id=run_id)
    _write_candidate_metric_result_manifest(project_dir, run_id=run_id)
    return OptimizerLoopAdapterResult(status=ADAPTER_SUCCEEDED)


def test_single_optimizer_cycle_records_candidate(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    report = run_single_optimizer_cycle(
        project_dir,
        adapter_runner=_fake_success_adapter,
        created_at_utc="2026-06-04T01:00:00Z",
        recorded_at_utc="2026-06-04T01:01:00Z",
    )

    assert report.status == RECORDED
    assert report.candidate_id == "candidate_000002"
    assert report.run_id == "real_002"
    rows = _ledger_rows(project_dir)
    assert len(rows) == 2
    assert rows[-1]["candidate_id"] == "candidate_000002"
    assert rows[-1]["run_id"] == "real_002"


def test_single_optimizer_cycle_allocates_next_unused_ids(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = run_single_optimizer_cycle(
        project_dir,
        adapter_runner=_fake_success_adapter,
        created_at_utc="2026-06-04T01:00:00Z",
        recorded_at_utc="2026-06-04T01:01:00Z",
    )

    second = run_single_optimizer_cycle(
        project_dir,
        adapter_runner=_fake_success_adapter,
        created_at_utc="2026-06-04T01:02:00Z",
        recorded_at_utc="2026-06-04T01:03:00Z",
    )

    assert first.candidate_id == "candidate_000002"
    assert first.run_id == "real_002"
    assert second.status == RECORDED
    assert second.candidate_id == "candidate_000003"
    assert second.run_id == "real_003"
    assert len(_ledger_rows(project_dir)) == 3


def test_single_optimizer_cycle_stops_on_adapter_failure(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    def fail_adapter(_project_dir: Path, _run_id: str) -> OptimizerLoopAdapterResult:
        return OptimizerLoopAdapterResult(status="failed", issues=("adapter exploded",))

    report = run_single_optimizer_cycle(
        project_dir,
        adapter_runner=fail_adapter,
        created_at_utc="2026-06-04T01:00:00Z",
    )

    assert report.status == ADAPTER_FAILED
    assert report.issues == ("adapter exploded",)
    assert len(_ledger_rows(project_dir)) == 1
    assert not (
        project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    ).exists()


def test_single_optimizer_cycle_stops_on_metric_check_failure(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    def missing_metric_adapter(
        project_dir: Path,
        run_id: str,
    ) -> OptimizerLoopAdapterResult:
        _write_candidate_result_manifest(project_dir, run_id=run_id)
        _write_candidate_metric_result_manifest(project_dir, run_id=run_id)
        manifest_path = (
            project_dir
            / "runs"
            / "real"
            / run_id
            / "metrics"
            / "metric_result_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["metrics"][0]["expression_sha256"] = "0" * 64
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return OptimizerLoopAdapterResult(status=ADAPTER_SUCCEEDED)

    report = run_single_optimizer_cycle(
        project_dir,
        adapter_runner=missing_metric_adapter,
        created_at_utc="2026-06-04T01:00:00Z",
    )

    assert report.status == METRIC_CHECK_FAILED
    assert report.issues
    assert len(_ledger_rows(project_dir)) == 1


def test_real_optimizer_loop_tool_records_fake_cycle(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    tool = _load_loop_tool()

    def fake_runner(command, **_kwargs):
        command_text = command[-1]
        run_id = re.search(r"--run-id (real_[0-9]+)", command_text).group(1)
        _write_candidate_result_manifest(project_dir, run_id=run_id)
        _write_candidate_metric_result_manifest(project_dir, run_id=run_id)
        return SimpleNamespace(returncode=0, stdout="succeeded\n", stderr="")

    exit_code = tool.main(
        [
            str(project_dir),
            "--max-new-evaluations",
            "1",
            "--cadence-cshrc",
            "/tmp/fake.csh",
        ],
        command_runner=fake_runner,
    )

    assert exit_code == 0
    assert len(_ledger_rows(project_dir)) == 2
    report = _load_json(project_dir / "reports" / "optimizer_loop_report.json")
    assert report["cycles"][0]["status"] == RECORDED
    assert report["cycles"][0]["candidate_id"] == "candidate_000002"


def test_real_optimizer_loop_tool_stops_on_adapter_failure(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    tool = _load_loop_tool()

    def fake_runner(_command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="failed\n", stderr="")

    exit_code = tool.main(
        [
            str(project_dir),
            "--max-new-evaluations",
            "1",
            "--cadence-cshrc",
            "/tmp/fake.csh",
        ],
        command_runner=fake_runner,
    )

    assert exit_code == 1
    assert len(_ledger_rows(project_dir)) == 1
    report = _load_json(project_dir / "reports" / "optimizer_loop_report.json")
    assert report["cycles"][0]["status"] == ADAPTER_FAILED


def test_real_optimizer_loop_tool_rejects_empty_budget(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    tool = _load_loop_tool()

    exit_code = tool.main(
        [
            str(project_dir),
            "--max-new-evaluations",
            "0",
            "--cadence-cshrc",
            "/tmp/fake.csh",
        ],
    )

    assert exit_code == 2
