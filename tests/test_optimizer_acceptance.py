import json
from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from tests.real_run_smoke_helpers import create_approved_real_project


runner = CliRunner()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _trace_row(
    *,
    evaluation_index: int,
    run_id: str,
    status: str,
    result_manifest: str,
    metric_result_manifest: str,
) -> dict:
    return {
        "batch_id": "batch_001",
        "batch_size": 2,
        "batch_slot": evaluation_index,
        "batch_worker_count": 2,
        "constraint_penalty": 0.0,
        "evaluation_index": evaluation_index,
        "fom": 1.0,
        "issues": [],
        "max_parallel_jobs": 10,
        "metric_result_manifest": metric_result_manifest,
        "metrics": {"rise": 1.0},
        "objective": 1.0,
        "parallel_jobs": 10,
        "parameters": {"FN": "4"},
        "raw_x": [4.0],
        "result_manifest": result_manifest,
        "run_id": run_id,
        "selection_phase": "initialization",
        "status": status,
        "threads_per_run": 10,
    }


def _write_result_manifest(project_dir: Path, run_id: str, metric_path: str) -> None:
    _write_json(
        project_dir / "runs" / "real" / run_id / "result_manifest.json",
        {
            "metric_result_manifest": metric_path,
            "run_id": run_id,
            "simulator": {
                "output_format": "psfxl",
                "preset": "ax",
                "threads_per_run": 10,
                "timeout_s": 3600,
            },
            "status": "succeeded",
        },
    )


def _write_metric_manifest(project_dir: Path, relative_path: str, status: str) -> None:
    _write_json(
        project_dir / relative_path,
        {
            "backend": "spectre_ocean",
            "candidate_id": "candidate_000001",
            "issues": [] if status == "succeeded" else ["non-scalar metric"],
            "metrics": [],
            "ocean": {"attempts": 1, "return_codes": [0]},
            "psf_dir": "runs/real/real_001/psf",
            "request_file": "runs/real/real_001/metric_extraction_request.json",
            "request_sha256": "sha",
            "run_id": "real_001",
            "schema_version": "1.0",
            "status": status,
        },
    )


def _write_minimal_optimizer_run(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    trace_rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="feasible",
            result_manifest="runs/real/real_001/result_manifest.json",
            metric_result_manifest="runs/real/real_001/metrics/metric_result_manifest.json",
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="metric_check_failed",
            result_manifest="runs/real/real_002/result_manifest.json",
            metric_result_manifest="runs/real/real_002/metrics/metric_result_manifest.json",
        ),
    ]
    _write_json(
        project_dir / "reports" / "native_turbo_optimizer_report.json",
        {
            "batch_summary": {
                "batch_count": 1,
                "max_batch_worker_count": 2,
                "status_counts": {"feasible": 1, "metric_check_failed": 1},
            },
            "best_candidate": trace_rows[0],
            "evaluation_count": 2,
            "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
            "issues": [],
            "schema_version": "1.0",
            "status": "completed",
        },
    )
    _append_jsonl(
        project_dir / "reports" / "native_turbo_optimizer_evaluations.jsonl",
        trace_rows,
    )
    _write_result_manifest(
        project_dir,
        "real_001",
        "runs/real/real_001/metrics/metric_result_manifest.json",
    )
    _write_result_manifest(
        project_dir,
        "real_002",
        "runs/real/real_002/metrics/metric_result_manifest.json",
    )
    _write_metric_manifest(
        project_dir,
        "runs/real/real_001/metrics/metric_result_manifest.json",
        "succeeded",
    )
    _write_metric_manifest(
        project_dir,
        "runs/real/real_002/metrics/metric_result_manifest.json",
        "failed",
    )
    _write_json(
        project_dir / "state" / "optimizer_state.json",
        {"current_evaluations": 1, "schema_version": "1.0", "status": "running"},
    )
    (project_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (project_dir / "ledger" / "experiment_ledger.jsonl").write_text(
        json.dumps({"run_id": "real_001"}) + "\n",
        encoding="utf-8",
    )
    return project_dir


class FakeAdvisorForAcceptance:
    def __init__(self) -> None:
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def _write_backend_neutral_optimizer_report(
    project_dir: Path,
    *,
    backend: str,
    execution_mode: str,
    rows: list[dict],
) -> None:
    _write_json(
        project_dir / "reports" / "optimizer_run_report.json",
        {
            "batch_summary": {
                "batch_count": 1,
                "max_batch_worker_count": 1,
                "status_counts": {"feasible": len(rows)},
            },
            "backend": backend,
            "best_candidate": rows[0] if rows else None,
            "evaluation_count": len(rows),
            "evaluations": "reports/optimizer_evaluations.jsonl",
            "execution_mode": execution_mode,
            "issues": [],
            "schema_version": "1.0",
            "status": "completed",
        },
    )
    _append_jsonl(project_dir / "reports" / "optimizer_evaluations.jsonl", rows)


def test_check_optimizer_run_accepts_fake_openbox_without_manifests(
    tmp_path: Path,
) -> None:
    from hermes_workflow.openbox_backend import run_openbox_fake_optimization

    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForAcceptance(),
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.result_manifest_count == 0
    assert report.metric_manifest_count == 0
    assert report.status_counts


def test_check_optimizer_run_rejects_real_backend_rows_without_manifests(
    tmp_path: Path,
) -> None:
    _write_backend_neutral_optimizer_report(
        tmp_path,
        backend="openbox",
        execution_mode="real",
        rows=[{"evaluation_index": 1, "run_id": "real_001", "status": "feasible"}],
    )

    report = check_optimizer_run(tmp_path)

    assert report.status == "rejected"
    assert any("manifest" in issue for issue in report.issues)


def test_check_optimizer_run_accepts_completed_manifest_audit(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.evaluation_count == 2
    assert report.result_manifest_count == 2
    assert report.metric_manifest_count == 2
    assert report.status_counts == {"feasible": 1, "metric_check_failed": 1}
    assert report.settings["preset"] == "ax"
    assert report.settings["threads_per_run"] == 10
    assert report.settings["parallel_jobs"] == 10
    assert report.settings["output_format"] == "psfxl"
    assert report.issues == []
    assert report.report_path == (
        project_dir / "reports" / "optimizer_run_acceptance_report.json"
    )


def test_check_optimizer_run_rejects_trace_count_mismatch(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    (project_dir / "reports" / "native_turbo_optimizer_evaluations.jsonl").write_text(
        "",
        encoding="utf-8",
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("evaluation count mismatch" in issue for issue in report.issues)


def test_check_optimizer_run_rejects_missing_result_manifest(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    (project_dir / "runs" / "real" / "real_002" / "result_manifest.json").unlink()

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("missing file" in issue for issue in report.issues)


def test_check_optimizer_run_rejects_spectre_setting_drift(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_payload["simulator"]["threads_per_run"] = 20
    _write_json(result_path, result_payload)

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("threads_per_run" in issue for issue in report.issues)


def test_check_optimizer_run_rejects_success_without_result_metric_reference(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_payload["metric_result_manifest"] = None
    _write_json(result_path, result_payload)

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("result succeeded but lacks metric manifest" in issue for issue in report.issues)


def test_check_optimizer_run_rejects_result_failure_recorded_as_feasible(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_payload["status"] = "failed"
    result_payload["issues"] = ["spectre failed"]
    _write_json(result_path, result_payload)

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("result failure is not reflected" in issue for issue in report.issues)


def test_check_optimizer_run_accepts_reflected_real_check_failure_without_metric(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    trace_rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="real_check_failed",
            result_manifest="runs/real/real_001/result_manifest.json",
            metric_result_manifest="",
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_002",
            status="feasible",
            result_manifest="runs/real/real_002/result_manifest.json",
            metric_result_manifest="runs/real/real_002/metrics/metric_result_manifest.json",
        ),
    ]
    _write_json(
        project_dir / "reports" / "native_turbo_optimizer_report.json",
        {
            "batch_summary": {
                "batch_count": 1,
                "max_batch_worker_count": 1,
                "status_counts": {"feasible": 1, "real_check_failed": 1},
            },
            "best_candidate": None,
            "evaluation_count": 2,
            "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
            "issues": [],
            "schema_version": "1.0",
            "status": "completed",
        },
    )
    _append_jsonl(
        project_dir / "reports" / "native_turbo_optimizer_evaluations.jsonl",
        trace_rows,
    )
    _write_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json",
        {
            "issues": ["spectre failed"],
            "run_id": "real_001",
            "simulator": {
                "output_format": "psfxl",
                "preset": "ax",
                "threads_per_run": 10,
            },
            "status": "failed",
        },
    )
    _write_result_manifest(
        project_dir,
        "real_002",
        "runs/real/real_002/metrics/metric_result_manifest.json",
    )
    _write_metric_manifest(
        project_dir,
        "runs/real/real_002/metrics/metric_result_manifest.json",
        "succeeded",
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.metric_manifest_count == 1
    assert report.status_counts == {"feasible": 1, "real_check_failed": 1}


def test_check_optimizer_run_cli_writes_acceptance_report(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)

    result = runner.invoke(app, ["check-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "reports/optimizer_run_acceptance_report.json" in result.stdout
    assert "optimizer run accepted" in result.stdout
    assert (project_dir / "reports/optimizer_run_acceptance_report.json").exists()


def test_check_optimizer_run_cli_exits_nonzero_for_rejected_run(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    (project_dir / "reports/native_turbo_optimizer_evaluations.jsonl").write_text(
        "",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check-optimizer-run", str(project_dir)])

    assert result.exit_code == 1
    assert "optimizer run rejected" in result.stdout
    assert "reports/optimizer_run_acceptance_report.json" in result.stdout
