import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.optimizer_acceptance import check_optimizer_run
from tests.project_factory import create_generic_project
from tests.real_run_smoke_helpers import advisor_batches, create_approved_real_project


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
    if status in {"real_check_failed", "metric_check_failed", "adapter_failed", "record_failed"}:
        metrics = None
        fom = None
        objective = 1_000_000.0
        constraint_penalty = 0.0
    elif status == "constraint_failed":
        metrics = {"metric_gain": 1.0, "metric_power": 0.002}
        fom = 0.998
        objective = 1_000_001.0
        constraint_penalty = 1.0
    else:
        metrics = {"metric_gain": 1.0, "metric_power": 0.0}
        fom = 1.0
        objective = -1.0
        constraint_penalty = 0.0
    return {
        "batch_id": "batch_001",
        "batch_size": 2,
        "batch_slot": evaluation_index,
        "batch_worker_count": 2,
        "constraint_penalty": constraint_penalty,
        "evaluation_index": evaluation_index,
        "fom": fom,
        "issues": [],
        "max_parallel_jobs": 10,
        "metric_result_manifest": metric_result_manifest,
        "metrics": metrics,
        "objective": objective,
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
    run_number = int(run_id.removeprefix("real_"))
    _write_json(
        project_dir / "runs" / "real" / run_id / "result_manifest.json",
        {
            "candidate_id": f"candidate_{run_number:06d}",
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
    run_id = Path(relative_path).parts[2]
    run_number = int(run_id.removeprefix("real_"))
    _write_json(
        project_dir / relative_path,
        {
            "backend": "spectre_ocean",
            "candidate_id": f"candidate_{run_number:06d}",
            "issues": [] if status == "succeeded" else ["non-scalar metric"],
            "metrics": (
                [
                    {
                        "name": "metric_gain",
                        "status": "succeeded",
                        "unit": "V/V",
                        "value": 1.0,
                        "value_text": "1.0",
                    },
                    {
                        "name": "metric_power",
                        "status": "succeeded",
                        "unit": "W",
                        "value": 0.0,
                        "value_text": "0.0",
                    },
                ]
                if status == "succeeded"
                else []
            ),
            "ocean": {"attempts": 1, "return_codes": [0]},
            "psf_dir": "runs/real/real_001/psf",
            "request_file": "runs/real/real_001/metric_extraction_request.json",
            "request_sha256": "sha",
            "run_id": run_id,
            "schema_version": "1.0",
            "status": status,
        },
    )


def _write_minimal_optimizer_run(tmp_path: Path) -> Path:
    project_dir = create_generic_project(tmp_path, name="bridge_test_inv")
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
    def __init__(self, project_dir: Path) -> None:
        self._batches = advisor_batches(project_dir)

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


def _rewrite_native_rows_and_best(project_dir: Path, rows: list[dict]) -> None:
    _append_jsonl(
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl",
        rows,
    )
    feasible = [row for row in rows if row.get("status") == "feasible"]
    best = min(feasible or rows, key=lambda row: row["objective"])
    report_path = project_dir / "reports/native_turbo_optimizer_report.json"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["best_candidate"] = best
    _write_json(report_path, report_payload)


def test_check_optimizer_run_accepts_fake_openbox_without_manifests(
    tmp_path: Path,
) -> None:
    from hermes_workflow.openbox_backend import run_openbox_fake_optimization

    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForAcceptance(project_dir),
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.result_manifest_count == 0
    assert report.metric_manifest_count == 0


def test_check_optimizer_run_uses_expected_native_artifacts_when_openbox_is_stale(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    _write_backend_neutral_optimizer_report(
        project_dir,
        backend="openbox",
        execution_mode="real",
        rows=[{"evaluation_index": 99, "run_id": "real_099", "status": "feasible"}],
    )

    report = check_optimizer_run(
        project_dir,
        expected_backend="native_turbo",
    )

    assert report.status == "accepted"
    assert report.evaluation_count == 2
    assert report.status_counts == {"feasible": 1, "metric_check_failed": 1}
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


@pytest.mark.parametrize("backend", ["openbox", "native_turbo"])
@pytest.mark.parametrize(
    ("field", "value", "expected_issue"),
    [
        (
            "metrics",
            {"metric_gain": 999.0, "metric_power": 0.0},
            "trace metrics do not match parent metric manifest",
        ),
        ("fom", 999.0, "trace fom mismatch"),
        ("objective", -999.0, "trace objective mismatch"),
        (
            "constraint_penalty",
            999.0,
            "trace constraint_penalty mismatch",
        ),
        ("status", "constraint_failed", "trace status mismatch"),
        ("status", "unknown_science", "trace status is unknown"),
    ],
)
def test_check_optimizer_run_rejects_scientific_trace_drift(
    tmp_path: Path,
    backend: str,
    field: str,
    value: object,
    expected_issue: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    native_evaluations = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in native_evaluations.read_text(encoding="utf-8").splitlines()
    ]
    rows[0][field] = value
    if backend == "openbox":
        _write_backend_neutral_optimizer_report(
            project_dir,
            backend="openbox",
            execution_mode="real",
            rows=rows,
        )
    else:
        _append_jsonl(native_evaluations, rows)
        report_path = project_dir / "reports/native_turbo_optimizer_report.json"
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        report_payload["best_candidate"] = rows[0]
        _write_json(report_path, report_payload)

    report = check_optimizer_run(project_dir, expected_backend=backend)

    assert report.status == "rejected"
    assert any(expected_issue in issue for issue in report.issues), report.issues


def test_check_optimizer_run_recomputes_constraint_failure_from_parent_metrics(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0].update(
        {
            "status": "constraint_failed",
            "metrics": {"metric_gain": 1.0, "metric_power": 0.002},
            "fom": 0.998,
            "objective": 1_000_001.0,
            "constraint_penalty": 1.0,
        }
    )
    _rewrite_native_rows_and_best(project_dir, rows)
    metric_path = project_dir / rows[0]["metric_result_manifest"]
    metric_payload = json.loads(metric_path.read_text(encoding="utf-8"))
    power = next(
        metric for metric in metric_payload["metrics"]
        if metric["name"] == "metric_power"
    )
    power["value"] = 0.002
    power["value_text"] = "0.002"
    _write_json(metric_path, metric_payload)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "accepted", report.issues
    assert report.status_counts["constraint_failed"] == 1


@pytest.mark.parametrize("failure_kind", ["metric", "real"])
@pytest.mark.parametrize(
    ("field", "value", "expected_issue"),
    [
        ("metrics", {"metric_gain": 1.0}, "failure trace metrics must be null"),
        ("fom", 1.0, "failure trace fom must be null"),
        ("objective", 0.0, "trace objective mismatch"),
        ("constraint_penalty", 1.0, "trace constraint_penalty mismatch"),
        ("status", "feasible", "trace status mismatch"),
    ],
)
def test_check_optimizer_run_rejects_failure_trace_sentinel_drift(
    tmp_path: Path,
    failure_kind: str,
    field: str,
    value: object,
    expected_issue: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    target = 1
    if failure_kind == "real":
        target = 0
        result_path = project_dir / rows[target]["result_manifest"]
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        result_payload["status"] = "failed"
        _write_json(result_path, result_payload)
        rows[target].update(
            {
                "status": "real_check_failed",
                "metrics": None,
                "fom": None,
                "objective": 1_000_000.0,
                "constraint_penalty": 0.0,
                "metric_result_manifest": "",
            }
        )
    rows[target][field] = value
    _rewrite_native_rows_and_best(project_dir, rows)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "rejected"
    assert any(expected_issue in issue for issue in report.issues), report.issues


@pytest.mark.parametrize("status", ["adapter_failed", "record_failed"])
def test_check_optimizer_run_preserves_known_workflow_failure_history(
    tmp_path: Path,
    status: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0].update(
        {
            "status": status,
            "metrics": None,
            "fom": None,
            "objective": 1_000_000.0,
            "constraint_penalty": 0.0,
        }
    )
    _rewrite_native_rows_and_best(project_dir, rows)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "accepted", report.issues
    assert report.status_counts[status] == 1


def test_check_optimizer_run_accepts_duplicate_skipped_without_parent_manifests(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[1].update(
        {
            "status": "duplicate_candidate_skipped",
            "metrics": None,
            "fom": None,
            "objective": 1_000_000.0,
            "constraint_penalty": 0.0,
            "result_manifest": None,
            "metric_result_manifest": None,
        }
    )
    _rewrite_native_rows_and_best(project_dir, rows)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "accepted", report.issues
    assert report.evaluation_count == 2
    assert report.result_manifest_count == 1
    assert report.metric_manifest_count == 1


@pytest.mark.parametrize(
    ("field", "value", "expected_issue"),
    [
        (
            "result_manifest",
            "runs/real/real_002/result_manifest.json",
            "duplicate trace result_manifest must be null",
        ),
        ("metrics", {"metric_gain": 1.0}, "duplicate trace metrics must be null"),
        ("fom", 1.0, "duplicate trace fom must be null"),
        ("objective", 0.0, "trace objective mismatch"),
        ("constraint_penalty", 1.0, "trace constraint_penalty mismatch"),
    ],
)
def test_check_optimizer_run_rejects_invalid_duplicate_skipped_sentinel(
    tmp_path: Path,
    field: str,
    value: object,
    expected_issue: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[1].update(
        {
            "status": "duplicate_candidate_skipped",
            "metrics": None,
            "fom": None,
            "objective": 1_000_000.0,
            "constraint_penalty": 0.0,
            "result_manifest": None,
            "metric_result_manifest": None,
        }
    )
    rows[1][field] = value
    _rewrite_native_rows_and_best(project_dir, rows)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "rejected"
    assert any(expected_issue in issue for issue in report.issues), report.issues


@pytest.mark.parametrize(
    ("corruption", "expected_issue"),
    [
        ("unit", "unit mismatch"),
        ("non_finite", "value is not finite"),
        ("missing", "configured parent metric metric_power is missing"),
        ("duplicate", "parent metric metric_gain is duplicated"),
    ],
)
def test_check_optimizer_run_rejects_invalid_parent_scientific_metrics(
    tmp_path: Path,
    corruption: str,
    expected_issue: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    metric_path = (
        project_dir
        / "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    payload = json.loads(metric_path.read_text(encoding="utf-8"))
    if corruption == "unit":
        payload["metrics"][0]["unit"] = "W"
    elif corruption == "non_finite":
        payload["metrics"][0]["value"] = True
    elif corruption == "missing":
        payload["metrics"] = payload["metrics"][:1]
    else:
        payload["metrics"].append(dict(payload["metrics"][0]))
    _write_json(metric_path, payload)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "rejected"
    assert any(expected_issue in issue for issue in report.issues), report.issues


@pytest.mark.parametrize("mutated_field", ["value", "value_text"])
def test_check_optimizer_run_binds_parent_metric_value_to_value_text(
    tmp_path: Path,
    mutated_field: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    metric_path = (
        project_dir
        / "runs/real/real_001/metrics/metric_result_manifest.json"
    )
    payload = json.loads(metric_path.read_text(encoding="utf-8"))
    gain = next(
        metric for metric in payload["metrics"]
        if metric["name"] == "metric_gain"
    )
    gain[mutated_field] = 2.0 if mutated_field == "value" else "2.0"
    _write_json(metric_path, payload)

    if mutated_field == "value":
        evaluations_path = (
            project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
        )
        rows = [
            json.loads(line)
            for line in evaluations_path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0].update(
            {
                "metrics": {"metric_gain": 2.0, "metric_power": 0.0},
                "fom": 2.0,
                "objective": -2.0,
            }
        )
        _rewrite_native_rows_and_best(project_dir, rows)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "rejected"
    assert any("value/value_text mismatch" in issue for issue in report.issues)


def test_check_optimizer_run_rejects_report_best_outside_verified_traces(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    report_path = project_dir / "reports/native_turbo_optimizer_report.json"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["best_candidate"] = {
        **report_payload["best_candidate"],
        "run_id": "real_999",
        "objective": -999_999_999.0,
    }
    _write_json(report_path, report_payload)

    report = check_optimizer_run(project_dir, expected_backend="native_turbo")

    assert report.status == "rejected"
    assert any("best_candidate" in issue for issue in report.issues)
    assert report.best_candidate is not None
    assert report.best_candidate["run_id"] == "real_001"
    persisted = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert persisted["best_candidate"]["run_id"] == "real_001"


def test_check_optimizer_run_rejects_duplicate_evaluation_and_run_identity(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [json.loads(line) for line in evaluations.read_text().splitlines()]
    rows[1]["evaluation_index"] = 1
    rows[1]["run_id"] = "real_001"
    rows[1]["result_manifest"] = rows[0]["result_manifest"]
    rows[1]["metric_result_manifest"] = rows[0]["metric_result_manifest"]
    _append_jsonl(evaluations, rows)

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("evaluation_index sequence" in issue for issue in report.issues)
    assert any("duplicate run_id" in issue for issue in report.issues)


@pytest.mark.parametrize(
    ("corruption", "expected_issue"),
    [
        ("trace_result_path", "canonical result manifest"),
        ("result_run_id", "result manifest run_id mismatch"),
        ("result_metric_path", "result/trace metric manifest mismatch"),
        ("metric_run_id", "metric manifest run_id mismatch"),
        ("metric_candidate_id", "metric/result candidate_id mismatch"),
        ("metric_noncanonical", "canonical metric manifest"),
        ("candidates_same_wrong", "result manifest candidate_id mismatch"),
    ],
)
def test_check_optimizer_run_rejects_cross_run_manifest_identity(
    tmp_path: Path,
    corruption: str,
    expected_issue: str,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [json.loads(line) for line in evaluations.read_text().splitlines()]
    result_path = project_dir / rows[0]["result_manifest"]
    metric_path = project_dir / rows[0]["metric_result_manifest"]

    if corruption == "trace_result_path":
        rows[0]["result_manifest"] = rows[1]["result_manifest"]
        _append_jsonl(evaluations, rows)
    elif corruption == "result_run_id":
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["run_id"] = "real_002"
        _write_json(result_path, payload)
    elif corruption == "result_metric_path":
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["metric_result_manifest"] = rows[1]["metric_result_manifest"]
        _write_json(result_path, payload)
    elif corruption == "metric_run_id":
        payload = json.loads(metric_path.read_text(encoding="utf-8"))
        payload["run_id"] = "real_002"
        _write_json(metric_path, payload)
    elif corruption == "metric_candidate_id":
        payload = json.loads(metric_path.read_text(encoding="utf-8"))
        payload["candidate_id"] = "candidate_999999"
        _write_json(metric_path, payload)
    elif corruption == "metric_noncanonical":
        wrong_relative = "runs/real/real_001/metrics/other.json"
        wrong_path = project_dir / wrong_relative
        _write_json(
            wrong_path,
            json.loads(metric_path.read_text(encoding="utf-8")),
        )
        rows[0]["metric_result_manifest"] = wrong_relative
        _append_jsonl(evaluations, rows)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["metric_result_manifest"] = wrong_relative
        _write_json(result_path, payload)
    else:
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        result_payload["candidate_id"] = "candidate_999999"
        _write_json(result_path, result_payload)
        metric_payload = json.loads(metric_path.read_text(encoding="utf-8"))
        metric_payload["candidate_id"] = "candidate_999999"
        _write_json(metric_path, metric_payload)

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any(expected_issue in issue for issue in report.issues), report.issues


def test_check_optimizer_run_allows_monotonic_run_id_gaps_from_orphan_runs(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    evaluations = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [json.loads(line) for line in evaluations.read_text().splitlines()]
    rows[1]["run_id"] = "real_003"
    rows[1]["result_manifest"] = (
        "runs/real/real_003/result_manifest.json"
    )
    rows[1]["metric_result_manifest"] = (
        "runs/real/real_003/metrics/metric_result_manifest.json"
    )
    _append_jsonl(evaluations, rows)
    old_run = project_dir / "runs/real/real_002"
    new_run = project_dir / "runs/real/real_003"
    old_run.replace(new_run)
    _write_result_manifest(
        project_dir,
        "real_003",
        "runs/real/real_003/metrics/metric_result_manifest.json",
    )
    _write_metric_manifest(
        project_dir,
        "runs/real/real_003/metrics/metric_result_manifest.json",
        "failed",
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.evaluation_count == 2


def test_check_optimizer_run_uses_openbox_evaluation_candidate_across_run_gap(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, name="bridge_test_inv")
    rows = [
        _trace_row(
            evaluation_index=1,
            run_id="real_001",
            status="feasible",
            result_manifest="runs/real/real_001/result_manifest.json",
            metric_result_manifest=(
                "runs/real/real_001/metrics/metric_result_manifest.json"
            ),
        ),
        _trace_row(
            evaluation_index=2,
            run_id="real_003",
            status="feasible",
            result_manifest="runs/real/real_003/result_manifest.json",
            metric_result_manifest=(
                "runs/real/real_003/metrics/metric_result_manifest.json"
            ),
        ),
    ]
    _write_backend_neutral_optimizer_report(
        project_dir,
        backend="openbox",
        execution_mode="real",
        rows=rows,
    )
    for run_id in ("real_001", "real_003"):
        metric_relative = (
            f"runs/real/{run_id}/metrics/metric_result_manifest.json"
        )
        _write_result_manifest(project_dir, run_id, metric_relative)
        _write_metric_manifest(project_dir, metric_relative, "succeeded")
    for relative in (
        rows[1]["result_manifest"],
        rows[1]["metric_result_manifest"],
    ):
        path = project_dir / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["candidate_id"] = "candidate_000002"
        _write_json(path, payload)

    report = check_optimizer_run(project_dir, expected_backend="openbox")

    assert report.status == "accepted"


def test_check_optimizer_run_accepts_verified_supplementary_history_manifests(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    supplementary_root = project_dir / ".remote_history_manifests"
    historical_run = project_dir / "runs" / "real" / "real_001"
    supplementary_run = supplementary_root / "runs" / "real" / "real_001"
    supplementary_run.parent.mkdir(parents=True, exist_ok=True)
    historical_run.replace(supplementary_run)

    report = check_optimizer_run(
        project_dir,
        supplementary_artifact_root=supplementary_root,
    )

    assert report.status == "accepted"
    assert report.result_manifest_count == 2
    assert report.metric_manifest_count == 2


def test_check_optimizer_run_auto_uses_checksum_verified_retention_evidence(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    project_dir = _write_minimal_optimizer_run(tmp_path)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    decision_path = project_dir / "state/run_retention/real_001.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        decision_path,
        {
            "run_id": "real_001",
            "local_action": "deleted",
            "evidence_status": "preserved",
            "evidence_digest": evidence.digest,
        },
    )
    shutil.rmtree(project_dir / "runs/real/real_001")

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.result_manifest_count == 2
    assert report.metric_manifest_count == 2


def test_check_optimizer_run_rejects_trace_drift_against_retained_parent_metrics(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    project_dir = _write_minimal_optimizer_run(tmp_path)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    _write_json(
        project_dir / "state/run_retention/real_001.json",
        {
            "run_id": "real_001",
            "local_action": "deleted",
            "evidence_status": "preserved",
            "evidence_digest": evidence.digest,
        },
    )
    evaluations_path = (
        project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
    )
    rows = [
        json.loads(line)
        for line in evaluations_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["objective"] = -999.0
    _rewrite_native_rows_and_best(project_dir, rows)
    shutil.rmtree(project_dir / "runs/real/real_001")

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("trace objective mismatch" in issue for issue in report.issues)


def test_current_canonical_run_ignores_corrupt_stale_retention_evidence(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    project_dir = _write_minimal_optimizer_run(tmp_path)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    (evidence.bundle_path / "artifacts/result_manifest.json").write_text(
        "stale corrupt bytes\n",
        encoding="utf-8",
    )
    _write_json(
        project_dir / "state/run_retention/real_001.json",
        {
            "run_id": "real_001",
            "local_action": "kept",
            "evidence_status": "not_required",
        },
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert not any("retention evidence" in issue for issue in report.issues)


def test_deleted_run_with_corrupt_current_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    from hermes_workflow.retention_evidence import preserve_retention_evidence

    project_dir = _write_minimal_optimizer_run(tmp_path)
    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_001",
        candidate_id="candidate_000001",
    )
    _write_json(
        project_dir / "state/run_retention/real_001.json",
        {
            "run_id": "real_001",
            "local_action": "deleted",
            "evidence_status": "preserved",
            "evidence_digest": evidence.digest,
        },
    )
    shutil.rmtree(project_dir / "runs/real/real_001")
    (evidence.bundle_path / "artifacts/result_manifest.json").write_text(
        "corrupt current evidence\n",
        encoding="utf-8",
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("retention evidence is invalid" in issue for issue in report.issues)


@pytest.mark.parametrize("backend", ["openbox", "native_turbo"])
def test_combined_prior_and_current_deleted_evidence_accepts_both_backends(
    tmp_path: Path,
    backend: str,
) -> None:
    from hermes_workflow.retention_evidence import (
        materialize_combined_supplementary_artifacts,
        preserve_retention_evidence,
    )

    project_dir = _write_minimal_optimizer_run(tmp_path)
    rows = [
        json.loads(line)
        for line in (
            project_dir / "reports/native_turbo_optimizer_evaluations.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    if backend == "openbox":
        _write_backend_neutral_optimizer_report(
            project_dir,
            backend="openbox",
            execution_mode="real",
            rows=rows,
        )

    prior_root = project_dir / ".remote_history_manifests"
    prior_run = prior_root / "runs/real/real_001"
    prior_run.parent.mkdir(parents=True)
    (project_dir / "runs/real/real_001").replace(prior_run)

    evidence = preserve_retention_evidence(
        project_dir,
        run_id="real_002",
        candidate_id="candidate_000002",
    )
    _write_json(
        project_dir / "state/run_retention/real_002.json",
        {
            "run_id": "real_002",
            "local_action": "deleted",
            "evidence_status": "preserved",
            "evidence_digest": evidence.digest,
        },
    )
    shutil.rmtree(project_dir / "runs/real/real_002")

    supplementary = materialize_combined_supplementary_artifacts(
        project_dir,
        prior_verified_root=prior_root,
        run_ids={"real_001", "real_002"},
    )
    report = check_optimizer_run(
        project_dir,
        expected_backend=backend,
        supplementary_artifact_root=supplementary,
    )

    assert report.status == "accepted"
    assert report.result_manifest_count == 2
    assert report.metric_manifest_count == 2


def test_verified_supplementary_history_overrides_stale_controller_run_copy(
    tmp_path: Path,
) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    supplementary_root = project_dir / ".remote_history_manifests"
    historical_run = project_dir / "runs" / "real" / "real_001"
    supplementary_run = supplementary_root / "runs" / "real" / "real_001"
    supplementary_run.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(historical_run, supplementary_run)
    (historical_run / "result_manifest.json").write_text(
        "stale Controller bytes\n",
        encoding="utf-8",
    )
    stale_metric_path = historical_run / "metrics/metric_result_manifest.json"
    stale_metric = json.loads(stale_metric_path.read_text(encoding="utf-8"))
    stale_metric["metrics"][0]["value"] = 999.0
    _write_json(stale_metric_path, stale_metric)

    report = check_optimizer_run(
        project_dir,
        supplementary_artifact_root=supplementary_root,
    )

    assert report.status == "accepted"
    assert report.result_manifest_count == 2


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
    assert any("trace status mismatch" in issue for issue in report.issues)


def test_check_optimizer_run_accepts_reflected_real_check_failure_without_metric(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, name="bridge_test_inv")
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
            "best_candidate": trace_rows[1],
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
                "candidate_id": "candidate_000001",
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


def _set_optimizer_report_issues(project_dir: Path, issues: object) -> None:
    """Mutate the legacy native turbo optimizer report's `issues` field in place."""
    report_path = project_dir / "reports" / "native_turbo_optimizer_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["issues"] = issues
    _write_json(report_path, payload)


def test_check_optimizer_run_rejects_when_optimizer_report_lists_progress_sync_failure(
    tmp_path: Path,
) -> None:
    """B-09 blocker: writer best-effort sync logs failures into
    `optimizer_run_report.json.issues`. Acceptance must fail-closed and surface
    every report issue. Otherwise progress-state contract failures get silently
    accepted and downstream completion can pass.
    """
    project_dir = _write_minimal_optimizer_run(tmp_path)
    _set_optimizer_report_issues(
        project_dir,
        ["optimizer_progress_state_sync_failed: boom"],
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any(
        "optimizer_progress_state_sync_failed" in issue for issue in report.issues
    ), report.issues
    # The acceptance JSON on disk must agree with the returned dataclass.
    on_disk = json.loads(
        (project_dir / "reports" / "optimizer_run_acceptance_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert on_disk["status"] == "rejected"
    assert any(
        "optimizer_progress_state_sync_failed" in issue for issue in on_disk["issues"]
    )


def test_check_optimizer_run_keeps_accepting_when_optimizer_report_issues_is_empty_list(
    tmp_path: Path,
) -> None:
    """Empty issues list must not regress the existing accepted path."""
    project_dir = _write_minimal_optimizer_run(tmp_path)
    _set_optimizer_report_issues(project_dir, [])

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.issues == []


def test_check_optimizer_run_rejects_when_optimizer_report_issues_is_not_a_list(
    tmp_path: Path,
) -> None:
    """If the optimizer report ships a malformed `issues` field, acceptance must
    flag it instead of silently ignoring the contract."""
    project_dir = _write_minimal_optimizer_run(tmp_path)
    _set_optimizer_report_issues(project_dir, "boom-as-string")

    report = check_optimizer_run(project_dir)

    assert report.status == "rejected"
    assert any("issues must be a list" in issue for issue in report.issues), report.issues
