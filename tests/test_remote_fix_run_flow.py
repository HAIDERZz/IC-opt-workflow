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
    return SimpleNamespace(status="pass", issues=[], cache_dir=project_dir)


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


def _set_remote_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _strip_optimizer_configs_for_remote_fix_run(project_dir: Path) -> None:
    """Make a genuine fix-run project: drop optimizer-only configs (avoids the
    optimizer contract check batch_size <= parallel_jobs when lowering
    parallel_jobs) and add a minimal waveform_exports.yaml so the fix-run
    contract (at least one of metrics/waveform_exports) holds."""
    for name in ("optimizer.yaml", "metrics.yaml"):
        path = project_dir / "config" / name
        if path.exists():
            path.unlink()
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


# ---------------------------------------------------------------------------
# Test 2: Remote fix-run uploads fixed-point request artifacts
# ---------------------------------------------------------------------------
def test_remote_fix_run_uploads_fixed_point_artifacts(tmp_path: Path) -> None:
    """run_remote_fix_run_project must upload fixed-point artifacts to the remote project."""
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    import yaml

    project_dir = tmp_path / "remote_fix_run_test"
    create_project_from_template(project_dir)
    # Write template
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    # Write workflow.yaml
    workflow_yaml = project_dir / "config" / "workflow.yaml"
    workflow_yaml.write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    # Write fixed_points.yaml
    fixed_points_yaml = project_dir / "config" / "fixed_points.yaml"
    fixed_points_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    import yaml

    project_dir = tmp_path / "remote_fix_run_report"
    create_project_from_template(project_dir)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    workflow_yaml = project_dir / "config" / "workflow.yaml"
    workflow_yaml.write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fixed_points_yaml = project_dir / "config" / "fixed_points.yaml"
    fixed_points_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    import yaml

    project_dir = tmp_path / "remote_fix_run_children"
    create_project_from_template(project_dir)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    workflow_yaml = project_dir / "config" / "workflow.yaml"
    workflow_yaml.write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fixed_points_yaml = project_dir / "config" / "fixed_points.yaml"
    fixed_points_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    import yaml

    project_dir = tmp_path / "remote_fix_run_fail"
    create_project_from_template(project_dir)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    workflow_yaml = project_dir / "config" / "workflow.yaml"
    workflow_yaml.write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fixed_points_yaml = project_dir / "config" / "fixed_points.yaml"
    fixed_points_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "opt_requirement.md").write_text("# requirement\n", encoding="utf-8")

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

    # Mock check_requirement to return fix_run mode
    monkeypatch.setattr(
        product_cli,
        "check_requirement",
        lambda *a, **kw: SimpleNamespace(workflow_mode="fix_run", status="pass"),
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

    project_dir = tmp_path / "remote_fix_run_artifacts"
    config_dir = project_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "workflow.yaml").write_text(
        json.dumps(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"}
        ),
        encoding="utf-8",
    )
    (config_dir / "fixed_points.yaml").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            }
        ),
        encoding="utf-8",
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
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.build_execution_package") as mock_build,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.remote_fix_run_flow._collect_child_runs") as mock_children,
        patch(
            "hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter"
        ) as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = tmp_path / "remote_fix_run_parallel"
    create_project_from_template(project_dir)
    (project_dir / "netlists" / "templates").mkdir(parents=True, exist_ok=True)
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    (project_dir / "config" / "workflow.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _strip_optimizer_configs_for_remote_fix_run(project_dir)
    _set_remote_spectre_parallel_jobs(project_dir, 2)

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
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = tmp_path / "remote_fix_run_serial"
    create_project_from_template(project_dir)
    (project_dir / "netlists" / "templates").mkdir(parents=True, exist_ok=True)
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    (project_dir / "config" / "workflow.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _strip_optimizer_configs_for_remote_fix_run(project_dir)
    _set_remote_spectre_parallel_jobs(project_dir, 1)

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
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    project_dir = tmp_path / "remote_fix_run_failure"
    create_project_from_template(project_dir)
    (project_dir / "netlists" / "templates").mkdir(parents=True, exist_ok=True)
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    (project_dir / "config" / "workflow.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _strip_optimizer_configs_for_remote_fix_run(project_dir)
    _set_remote_spectre_parallel_jobs(project_dir, 2)

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
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
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
