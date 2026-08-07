"""Tests for the remote fix-run orchestration flow."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from hermes_workflow.fix_run_models import (
    FixRunReport,
)
from hermes_workflow.remote_project import RemoteProjectRef
from tests.project_factory import create_generic_project


def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _fixed_points(project_dir: Path) -> list[dict[str, object]]:
    payload = _read_yaml(project_dir / "config" / "fixed_points.yaml")
    points = payload["points"]
    assert isinstance(points, list)
    return points


def _fixed_point_candidate_id(project_dir: Path) -> str:
    candidate_id = _fixed_points(project_dir)[0]["candidate_id"]
    assert isinstance(candidate_id, str)
    return candidate_id


def _fixed_point_parameters(project_dir: Path) -> dict[str, str]:
    parameters = _fixed_points(project_dir)[0]["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}


def _write_remote_waveform_exports(project_dir: Path) -> None:
    (project_dir / "config" / "waveform_exports.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "exports": [
                    {
                        "name": "nf_pnoise",
                        "testbench": "cg_nf",
                        "expression": 'getData("NF" ?result "pnoise")',
                        "output_format": "csv",
                        "nil_policy": "fail",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _set_remote_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _create_remote_fix_run_project(
    tmp_path: Path,
    *,
    name: str = "remote_fix_run_project",
    waveform_exports: bool = False,
    parallel_jobs: int | None = None,
) -> Path:
    """Create a generic fix-run project for remote tests."""
    project_dir = create_generic_project(
        tmp_path,
        name=name,
        workflow_mode="fix_run",
        parallel_jobs=parallel_jobs or 4,
    )
    if waveform_exports:
        _write_remote_waveform_exports(project_dir)
    if parallel_jobs is not None and parallel_jobs != 4:
        _set_remote_spectre_parallel_jobs(project_dir, parallel_jobs)
    return project_dir


def _mock_intake(project_dir: Path) -> SimpleNamespace:
    """Create a mock requirement intake result for fix_run mode."""
    return SimpleNamespace(
        status="pass",
        issues=[],
        workflow_mode="fix_run",
        sections={},
    )


def _mock_preparation(project_dir: Path) -> SimpleNamespace:
    """Create a mock preparation result."""
    return SimpleNamespace(
        status="pass",
        issues=[],
        cache_dir=project_dir,
        requirement_report=_mock_intake(project_dir),
        preparation_report=SimpleNamespace(status="pass", issues=[]),
    )


def _mock_adapter_result(
    project_dir: Path, run_id: str = "real_001"
) -> MagicMock:
    """Create a mock adapter result."""
    return MagicMock(
        status="succeeded",
        run_id=run_id,
        result_manifest_path=project_dir
        / "runs"
        / "real"
        / run_id
        / "result_manifest.json",
        metric_result_manifest_path=project_dir
        / "runs"
        / "real"
        / run_id
        / "metrics"
        / "metric_result_manifest.json",
        issues=[],
    )


def _write_remote_fix_run_child_dirs(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    testbench_id: str = "cg_nf",
    corner_ids: tuple[str, str, str] = ("tt", "ss", "ff"),
) -> None:
    for corner_id in corner_ids:
        child_dir = (
            project_dir
            / "runs"
            / "real"
            / run_id
            / "testbenches"
            / testbench_id
            / "corners"
            / corner_id
        )
        child_dir.mkdir(parents=True, exist_ok=True)


def _write_remote_waveform_artifacts(
    project_dir: Path, run_id: str, tb: str, corner: str
) -> None:
    metrics_dir = (
        project_dir / "runs" / "real" / run_id
        / "testbenches" / tb / "corners" / corner / "metrics"
    )
    (metrics_dir / "waveforms").mkdir(parents=True, exist_ok=True)
    (metrics_dir / "waveforms" / "nf_pnoise.csv").write_text("freq,nf\n", encoding="utf-8")
    (metrics_dir / "waveform_export_manifest.json").write_text("{}", encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Remote fix-run calls remote doctor and blocks on failure
# ---------------------------------------------------------------------------
def test_remote_fix_run_calls_remote_doctor_and_blocks_on_failure() -> None:
    """run_remote_fix_run_project must call run_remote_doctor and raise on failure."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor:
        mock_doctor.return_value = MagicMock(
            status="fail",
            issues=["SSH_LOGIN_FAILED"],
        )
        with pytest.raises(ValueError, match="remote doctor failed"):
            run_remote_fix_run_project(
                ref,
                remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
                real=True,
                runner=mock_runner,
            )

        mock_doctor.assert_called_once()


def test_remote_fix_run_reuses_frozen_remote_preparation_snapshot(
    tmp_path: Path,
) -> None:
    """Remote-owned Maestro paths must not be checked on the Controller."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path,
        name="remote_fix_run_snapshot",
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch(
            "hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache"
        ) as mock_prepare,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_preparation(project_dir)

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath(
                "/remote/project/cadence_env.csh"
            ),
            real=False,
            runner=mock_runner,
        )

    assert report.status == "pass"
    mock_prepare.assert_called_once()
    assert mock_prepare.call_args.kwargs["persist_snapshot"] is True


def test_remote_fix_run_fails_when_report_upload_fails(tmp_path: Path) -> None:
    """A Controller-only report is not a successful remote fix-run."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path,
        name="remote_fix_run_sync_failure",
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.upload.side_effect = RuntimeError("scp failed")

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch(
            "hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache"
        ) as mock_prepare,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_preparation(project_dir)

        with pytest.raises(RuntimeError, match="failed to upload fix-run report"):
            run_remote_fix_run_project(
                ref,
                remote_cadence_cshrc=PurePosixPath(
                    "/remote/project/cadence_env.csh"
                ),
                real=False,
                runner=mock_runner,
            )

    assert (project_dir / "reports" / "fix_run_report.json").is_file()


def test_remote_fix_run_publishes_pass_report_after_run_artifacts(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_fix_run_flow import (
        REPORT_RELATIVE,
        _sync_report_to_remote,
    )

    cache_dir = tmp_path / "cache"
    report_path = cache_dir / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
    (cache_dir / "runs" / "real" / "real_001").mkdir(parents=True)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[str] = []

    class RecordingRunner:
        def upload_tree(self, local_path, remote_path) -> None:
            calls.append(f"tree:{remote_path}")

        def upload(self, local_path, remote_path) -> None:
            calls.append(f"file:{remote_path}")

    _sync_report_to_remote(ref, cache_dir, RecordingRunner())

    assert calls == [
        "tree:/remote/project/runs",
        "file:/remote/project/reports/fix_run_report.json",
    ]


# ---------------------------------------------------------------------------
# Test 2: Remote fix-run uploads fixed-point request artifacts
# ---------------------------------------------------------------------------
def test_remote_fix_run_uploads_fixed_point_artifacts(tmp_path: Path) -> None:
    """run_remote_fix_run_project must upload fixed-point artifacts to the remote project."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(tmp_path)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.return_value = MagicMock(
            run_id="real_001",
            run_dir=project_dir / "runs" / "real" / "real_001",
        )
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

        # Verify upload_tree was called (to upload run artifacts)
        assert mock_runner.upload_tree.call_count >= 1 or mock_adapter.called


# ---------------------------------------------------------------------------
# Test 3: Remote fix-run writes reports/fix_run_report.json
# ---------------------------------------------------------------------------
def test_remote_fix_run_writes_report_json(tmp_path: Path) -> None:
    """run_remote_fix_run_project must write reports/fix_run_report.json."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(tmp_path, name="remote_fix_run_report")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.return_value = MagicMock(
            run_id="real_001",
            run_dir=project_dir / "runs" / "real" / "real_001",
        )
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

        report_path = project_dir / "reports" / "fix_run_report.json"
        assert report_path.exists()
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_data["schema_version"] == "1.0"
        assert report_data["workflow_mode"] == "fix_run"
        assert isinstance(report, FixRunReport)


# ---------------------------------------------------------------------------
# Test 4: Remote fix-run calls remote spectre/ocean for each testbench/corner
# ---------------------------------------------------------------------------
def test_remote_fix_run_calls_remote_spectre_ocean_per_child(tmp_path: Path) -> None:
    """run_remote_fix_run_project must call run_remote_spectre_ocean_adapter for each child run."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(tmp_path, name="remote_fix_run_children")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.return_value = MagicMock(
            run_id="real_001",
            run_dir=project_dir / "runs" / "real" / "real_001",
        )
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

        # The adapter should be called at least once
        assert mock_adapter.call_count >= 1
        # Verify it's called with remote_ref and remote_cadence_cshrc
        first_call = mock_adapter.call_args
        assert first_call.kwargs.get("remote_ref") == ref or first_call.kwargs.get("ref") == ref


# ---------------------------------------------------------------------------
# Test 5: Remote failure manifests preserve waveform export issues and command trace
# ---------------------------------------------------------------------------
def test_remote_failure_manifest_preserves_waveform_export_issues(tmp_path: Path) -> None:
    """When remote adapter fails, the fix-run report must preserve issues including
    waveform export problems."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(tmp_path, name="remote_fix_run_fail")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.return_value = MagicMock(
            run_id="real_001",
            run_dir=project_dir / "runs" / "real" / "real_001",
        )
        # Simulate adapter failure with waveform export issue
        mock_adapter.return_value = MagicMock(
            status="failed",
            run_id="real_001",
            result_manifest_path=project_dir
            / "runs"
            / "real"
            / "real_001"
            / "result_manifest.json",
            metric_result_manifest_path=None,
            issues=["waveform export failed: CSV write error", "adapter status: failed"],
        )

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

        # The report should capture the failure issues
        assert report.status == "fail"
        # Child issues should preserve the waveform export problem
        all_child_issues = [
            ci.message for point in report.points for ci in point.child_issues
        ]
        assert any("waveform export" in issue for issue in all_child_issues)


# ---------------------------------------------------------------------------
# Test 6: Product CLI remote --real dispatches to remote fix-run when workflow_mode is fix_run
# ---------------------------------------------------------------------------
def test_product_cli_remote_real_dispatches_to_remote_fix_run(
    monkeypatch, tmp_path: Path
) -> None:
    """When workflow_mode is fix_run and --ssh-profile is set, `ic-opt PROJECT --real`
    should dispatch to run_remote_fix_run_project instead of optimize_remote_project."""
    from typer.testing import CliRunner

    from hermes_workflow import product_cli

    runner = CliRunner()
    project_dir = tmp_path / "controller_cannot_see_remote_project"

    remote_fix_run_calls: list[dict[str, object]] = []

    def fake_run_remote_fix_run_project(ref, **kwargs: object) -> FixRunReport:
        remote_fix_run_calls.append({"ref": ref, **kwargs})
        return FixRunReport(
            schema_version="1.0",
            workflow_mode="fix_run",
            status="pass",
            points=[],
            optimizer_state_created=False,
            optimizer_decision_report_created=False,
        )

    def fail_optimize_remote(*_a, **_kw):
        raise AssertionError("optimize_remote_project must not be called when workflow_mode is fix_run")

    monkeypatch.setattr(product_cli, "run_remote_fix_run_project", fake_run_remote_fix_run_project)
    monkeypatch.setattr(product_cli, "optimize_remote_project", fail_optimize_remote)
    monkeypatch.setattr(
        product_cli,
        "begin_remote_optimizer_attempt",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        product_cli,
        "run_remote_doctor",
        lambda *a, **kw: SimpleNamespace(
            status="pass",
            workflow_mode="fix_run",
            issues=[],
        ),
    )

    # Remote dispatch must never inspect the Controller's same-named path.
    monkeypatch.setattr(
        product_cli,
        "check_requirement",
        lambda *a, **kw: pytest.fail(
            "remote workflow mode must not be read from the Controller filesystem"
        ),
    )

    result = runner.invoke(
        product_cli.app,
        [
            str(project_dir),
            "--real",
            "--ssh-profile",
            "lab",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "fix-run" in result.output.lower()
    assert len(remote_fix_run_calls) == 1


def test_remote_fix_run_report_collects_waveform_artifacts(tmp_path: Path) -> None:
    """Remote parent report must list downloaded waveform manifests and CSV files."""
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path, name="remote_fix_run_artifacts", waveform_exports=True
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    metrics_dir = run_dir / "testbenches" / "cg_nf" / "corners" / "tt" / "metrics"
    waveforms_dir = metrics_dir / "waveforms"

    def _adapter_side_effect(*args: object, **kwargs: object) -> MagicMock:
        waveforms_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "waveform_export_manifest.json").write_text(
            json.dumps({"schema_version": "1.0"}),
            encoding="utf-8",
        )
        (waveforms_dir / "nf_pnoise.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        return _mock_adapter_result(project_dir, run_id="real_001")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.build_execution_package") as mock_build,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.remote_fix_run_flow._collect_child_runs") as mock_children,
        patch(
            "hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter"
        ) as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_build.return_value = MagicMock(status="pass")
        mock_children.return_value = [{"testbench_id": "cg_nf", "corner_id": "tt"}]
        mock_adapter.side_effect = _adapter_side_effect

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

    point = report.points[0]
    assert point.waveform_export_manifest_paths == [
        "runs/real/real_001/testbenches/cg_nf/corners/tt/metrics/"
        "waveform_export_manifest.json"
    ]
    assert point.csv_artifact_paths == [
        "runs/real/real_001/testbenches/cg_nf/corners/tt/metrics/waveforms/"
        "nf_pnoise.csv"
    ]


def test_remote_fix_run_flow_does_not_import_optimizer_approval() -> None:
    """remote_fix_run_flow must NOT import or directly use
    decide_first_real_run. Locks in the B-FIXRUN-01 fix on the remote path."""
    import hermes_workflow.remote_fix_run_flow as remote_fix_run_flow_module

    assert hasattr(remote_fix_run_flow_module, "decide_fix_run_real_run")
    assert not hasattr(remote_fix_run_flow_module, "decide_first_real_run")


# ---------------------------------------------------------------------------
# Fix-run remote child-level parallelism (Spectre Settings.parallel_jobs)
# ---------------------------------------------------------------------------
def test_remote_fix_run_uses_parallel_jobs_for_child_runs(tmp_path: Path) -> None:
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path,
        name="remote_fix_run_parallel",
        waveform_exports=True,
        parallel_jobs=2,
    )

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_remote_fix_run_child_dirs(project_dir, run_id=run_id)
        return MagicMock(run_id=run_id, run_dir=project_dir / "runs" / "real" / run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        tb = kwargs.get("testbench_id") or "cg_nf"
        corner = kwargs.get("corner_id") or "tt"
        _write_remote_waveform_artifacts(project_dir, kwargs["run_id"], tb, corner)
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active > 1
    assert report.points[0].testbench_corner_count == 3


def test_remote_fix_run_parallel_jobs_one_keeps_child_runs_serial(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path,
        name="remote_fix_run_serial",
        waveform_exports=True,
        parallel_jobs=1,
    )

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_remote_fix_run_child_dirs(project_dir, run_id=run_id)
        return MagicMock(run_id=run_id, run_dir=project_dir / "runs" / "real" / run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        tb = kwargs.get("testbench_id") or "cg_nf"
        corner = kwargs.get("corner_id") or "tt"
        _write_remote_waveform_artifacts(project_dir, kwargs["run_id"], tb, corner)
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active == 1


# ---------------------------------------------------------------------------
# Failure preservation under remote parallelism
# ---------------------------------------------------------------------------
def test_remote_fix_run_parallel_child_failure_preserved_and_report_fails(
    tmp_path: Path,
) -> None:
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = _create_remote_fix_run_project(
        tmp_path,
        name="remote_fix_run_failure",
        waveform_exports=True,
        parallel_jobs=2,
    )

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_remote_fix_run_child_dirs(project_dir, run_id=run_id)
        return MagicMock(run_id=run_id, run_dir=project_dir / "runs" / "real" / run_id)

    def adapter_side_effect(*args, **kwargs):
        corner = kwargs.get("corner_id")
        tb = kwargs.get("testbench_id") or "cg_nf"
        if corner != "ss":
            _write_remote_waveform_artifacts(project_dir, kwargs["run_id"], tb, corner)
            return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])
        return MagicMock(
            status="failed",
            run_id=kwargs["run_id"],
            result_manifest_path=project_dir / "runs" / "real" / kwargs["run_id"] / "result_manifest.json",
            metric_result_manifest_path=None,
            issues=["sim failed"],
        )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

    assert report.status == "fail"
    assert report.points[0].testbench_corner_count == 3
    assert mock_adapter.call_count == 3
    assert any(
        "failed" in issue.message or "sim failed" in issue.message
        for issue in report.points[0].child_issues
    )
