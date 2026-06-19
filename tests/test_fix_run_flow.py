"""Tests for the local fix-run orchestration flow."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from hermes_workflow.fix_run_models import (
    FixRunPointReport,
    FixRunReport,
)
from tests.project_factory import create_generic_project


def _fixed_points(project_dir: Path) -> list[dict[str, object]]:
    payload = yaml.safe_load(
        (project_dir / "config" / "fixed_points.yaml").read_text(encoding="utf-8")
    )
    points = payload["points"]
    assert isinstance(points, list)
    return points


def _fixed_point_parameters(project_dir: Path, index: int = 0) -> dict[str, str]:
    parameters = _fixed_points(project_dir)[index]["parameters"]
    assert isinstance(parameters, dict)
    return {str(key): str(value) for key, value in parameters.items()}


def _fixed_point_candidate_id(project_dir: Path, index: int = 0) -> str:
    candidate_id = _fixed_points(project_dir)[index]["candidate_id"]
    assert isinstance(candidate_id, str)
    return candidate_id


def _create_fix_run_project(tmp_path: Path) -> Path:
    """Create a minimal project with fix_run mode configured."""
    return create_generic_project(
        tmp_path,
        name="fix_run_project",
        workflow_mode="fix_run",
    )


def _create_two_point_fix_run_project(tmp_path: Path) -> Path:
    """Create a fix_run project with two fixed points."""
    project_dir = create_generic_project(
        tmp_path,
        name="fix_run_two_points",
        workflow_mode="fix_run",
    )
    first_point = _fixed_points(project_dir)[0]
    first_parameters = _fixed_point_parameters(project_dir)
    parameter_names = list(first_parameters)
    assert len(parameter_names) == 2
    second_parameters = {
        parameter_names[0]: "4",
        parameter_names[1]: "0.4u",
    }
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    first_point,
                    {
                        "candidate_id": "fixed_002",
                        "parameters": second_parameters,
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
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
    return SimpleNamespace(status="pass", issues=[])


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


def _mock_prepare_result(project_dir: Path, run_id: str = "real_001") -> MagicMock:
    """Create a mock prepare_explicit_candidate_real_run result."""
    return MagicMock(
        run_id=run_id,
        run_dir=project_dir / "runs" / "real" / run_id,
        testbench_id=None,
        corner_id=None,
    )


def _write_fix_run_child_dirs(
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


def _set_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _strip_optimizer_configs_for_fix_run(project_dir: Path) -> None:
    """A genuine fix-run project does not carry optimizer-only configs.
    Removing metrics.yaml/optimizer.yaml avoids the optimizer contract check
    (batch_size <= parallel_jobs) when lowering parallel_jobs in tests. A
    minimal waveform_exports.yaml keeps the fix-run contract valid (at least
    one of metrics.yaml or waveform_exports.yaml)."""
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


# Standard mock context for fix_run tests - patches all external calls
_FIX_RUN_PATCHES = (
    "check_requirement",
    "prepare_from_requirement",
    "run_product_doctor",
    "prepare_explicit_candidate_real_run",
    "run_spectre_ocean_adapter",
)


# ---------------------------------------------------------------------------
# Test 1: run_fix_run_project calls product doctor when require_license_check
#         is true
# ---------------------------------------------------------------------------
def test_fix_run_project_calls_product_doctor_when_license_check_required(
    tmp_path: Path,
) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(
            project_dir, real=True, cadence_cshrc=project_dir / "cadence_env.csh"
        )

        mock_doctor.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: One fixed point creates one candidate request with the configured
#         candidate_id and parameters
# ---------------------------------------------------------------------------
def test_fix_run_one_fixed_point_creates_one_candidate(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        # prepare_explicit_candidate_real_run should be called once for 1 fixed point
        assert mock_prepare.call_count == 1
        call_kwargs = mock_prepare.call_args
        assert call_kwargs.kwargs["candidate_id"] == _fixed_point_candidate_id(project_dir)
        assert call_kwargs.kwargs["parameters"] == _fixed_point_parameters(project_dir)


# ---------------------------------------------------------------------------
# Test 3: Two fixed points allocate real_001 and real_002
# ---------------------------------------------------------------------------
def test_fix_run_two_fixed_points_allocate_consecutive_run_ids(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_two_point_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        # Two calls for two fixed points
        assert mock_prepare.call_count == 2
        # First call: real_001
        assert mock_prepare.call_args_list[0].kwargs["run_id"] == "real_001"
        # Second call: real_002
        assert mock_prepare.call_args_list[1].kwargs["run_id"] == "real_002"


# ---------------------------------------------------------------------------
# Test 4: Testbench/corner expansion calls the same child run path used by
#         optimizer real runs
# ---------------------------------------------------------------------------
def test_fix_run_calls_spectre_ocean_adapter_for_child_runs(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        # The adapter should be called at least once (for the single
        # testbench/corner combination)
        assert mock_adapter.call_count >= 1
        # Verify the adapter is called with the project directory
        first_call = mock_adapter.call_args
        assert first_call.args[0] == project_dir
        # Verify run_id is passed
        assert first_call.kwargs.get("run_id") == "real_001"


# ---------------------------------------------------------------------------
# Test 5: reports/fix_run_report.json is written after execution
# ---------------------------------------------------------------------------
def test_fix_run_writes_report_json(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        report_path = project_dir / "reports" / "fix_run_report.json"
        assert report_path.exists()
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_data["schema_version"] == "1.0"
        assert report_data["workflow_mode"] == "fix_run"
        assert report_data["status"] == "pass"
        assert "points" in report_data


# ---------------------------------------------------------------------------
# Test 6: No optimizer state path is created during fix-run
# ---------------------------------------------------------------------------
def test_fix_run_does_not_create_optimizer_state(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        # optimizer_state_created must be False per the FixRunReport model
        assert report.optimizer_state_created is False
        # And the actual file should not exist (it is only created by optimizer flow)
        assert not (project_dir / "state" / "optimizer_state.json").exists()


# ---------------------------------------------------------------------------
# Test 7: Fix-run returns FixRunReport with correct structure
# ---------------------------------------------------------------------------
def test_fix_run_returns_fix_run_report(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.return_value = _mock_prepare_result(project_dir)
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

        assert isinstance(report, FixRunReport)
        assert report.schema_version == "1.0"
        assert report.workflow_mode == "fix_run"
        assert report.status == "pass"
        assert len(report.points) == 1
        assert isinstance(report.points[0], FixRunPointReport)
    assert report.points[0].candidate_id == _fixed_point_candidate_id(project_dir)
    assert report.points[0].run_id == "real_001"
    assert report.optimizer_state_created is False
    assert report.optimizer_decision_report_created is False


def test_fix_run_report_collects_waveform_artifacts(tmp_path: Path) -> None:
    """Parent fix-run report must list child waveform manifests and CSV files."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

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

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package") as mock_build,
        patch("hermes_workflow.fix_run_flow.decide_fix_run_real_run"),
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_build.return_value = SimpleNamespace(status="pass")
        mock_children.return_value = [{"testbench_id": "cg_nf", "corner_id": "tt"}]
        mock_adapter.side_effect = _adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    point = report.points[0]
    assert point.waveform_export_manifest_paths == [
        "runs/real/real_001/testbenches/cg_nf/corners/tt/metrics/"
        "waveform_export_manifest.json"
    ]
    assert point.csv_artifact_paths == [
        "runs/real/real_001/testbenches/cg_nf/corners/tt/metrics/waveforms/"
        "nf_pnoise.csv"
    ]


def test_fix_run_flow_uses_fix_run_approval_not_optimizer_approval(
    tmp_path: Path,
) -> None:
    """The local fix-run flow must call decide_fix_run_real_run, not the
    optimizer-only decide_first_real_run. Locks in the B-FIXRUN-01 fix."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package") as mock_build,
        patch(
            "hermes_workflow.fix_run_flow.decide_fix_run_real_run"
        ) as mock_fix_run_approval,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_build.return_value = SimpleNamespace(status="pass")
        mock_children.return_value = [{"testbench_id": None, "corner_id": None}]
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    # The fix-run-specific approval must have been invoked exactly once.
    assert mock_fix_run_approval.call_count == 1


def test_fix_run_flow_does_not_import_optimizer_approval(tmp_path: Path) -> None:
    """fix_run_flow must NOT import or directly use decide_first_real_run.
    Locks in the regression where the wrong approval was wired up."""
    import hermes_workflow.fix_run_flow as fix_run_flow_module

    # The module must expose the fix-run approval, not the optimizer approval,
    # as a module-level attribute (it is imported by name).
    assert hasattr(fix_run_flow_module, "decide_fix_run_real_run")
    assert not hasattr(fix_run_flow_module, "decide_first_real_run")


# ---------------------------------------------------------------------------
# B-FIXRUN-02: status gate must fail when child adapter runs all fail.
# ---------------------------------------------------------------------------
def test_fix_run_report_fails_when_all_child_adapters_fail(tmp_path: Path) -> None:
    """When every child adapter raises (e.g. spectre not found), the report
    status must be 'fail', not 'pass'. Reproduces the local false-pass bug."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    def _adapter_side_effect(*args, **kwargs):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'spectre'")

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package"),
        patch("hermes_workflow.fix_run_flow.decide_fix_run_real_run"),
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_children.return_value = [
            {"testbench_id": "cg_nf", "corner_id": "tt_27"},
            {"testbench_id": "cg_nf", "corner_id": "ss_27"},
        ]
        mock_adapter.side_effect = _adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "fail"
    assert report.points[0].child_issues
    assert len(report.points[0].child_issues) == 2


def test_fix_run_report_fails_when_adapter_status_not_succeeded(tmp_path: Path) -> None:
    """adapter_result.status != 'succeeded' must count as a child failure and
    fail the overall report."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package"),
        patch("hermes_workflow.fix_run_flow.decide_fix_run_real_run"),
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_children.return_value = [{"testbench_id": None, "corner_id": None}]
        mock_adapter.return_value = MagicMock(
            status="failed",
            run_id="real_001",
            result_manifest_path=project_dir / "runs" / "real" / "real_001" / "result_manifest.json",
            metric_result_manifest_path=None,
            issues=["spectre command failed"],
        )

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "fail"


def test_fix_run_report_fails_when_waveform_csv_missing(tmp_path: Path) -> None:
    """When waveform_exports are configured but the CSV artifact is missing,
    the report must fail even if the adapter returned succeeded."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    # Add a waveform_exports.yaml so the flow expects CSV artifacts.
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

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package"),
        patch("hermes_workflow.fix_run_flow.decide_fix_run_real_run"),
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_children.return_value = [{"testbench_id": "cg_nf", "corner_id": "tt"}]
        mock_adapter.return_value = _mock_adapter_result(project_dir, run_id="real_001")

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    # Adapter "succeeded" but no CSV was produced -> must fail.
    assert report.status == "fail"


def test_fix_run_flow_passes_cadence_cshrc_to_adapter(tmp_path: Path) -> None:
    """cadence_cshrc must reach the Spectre/OCEAN adapter, not just the doctor.
    Locks in B-FIXRUN-01 at the flow level."""
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    cshrc = project_dir / "cadence_env.csh"

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.build_execution_package"),
        patch("hermes_workflow.fix_run_flow.decide_fix_run_real_run"),
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run"),
        patch("hermes_workflow.fix_run_flow._collect_child_runs") as mock_children,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = SimpleNamespace(status="pass", issues=[])
        mock_doctor.return_value = SimpleNamespace(status="pass", issues=[])
        mock_children.return_value = [{"testbench_id": None, "corner_id": None}]
        mock_adapter.return_value = _mock_adapter_result(project_dir)

        run_fix_run_project(project_dir, real=True, cadence_cshrc=cshrc)

    # The adapter must have been called with cadence_cshrc=<cshrc path>.
    adapter_kwargs = mock_adapter.call_args.kwargs
    assert adapter_kwargs.get("cadence_cshrc") == cshrc


# ---------------------------------------------------------------------------
# Fix-run child-level parallelism (Spectre Settings.parallel_jobs)
# ---------------------------------------------------------------------------
def test_fix_run_uses_parallel_jobs_for_child_runs(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    _strip_optimizer_configs_for_fix_run(project_dir)
    _set_spectre_parallel_jobs(project_dir, 2)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_fix_run_child_dirs(project_dir, run_id=run_id)
        return _mock_prepare_result(project_dir, run_id=run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        # Create waveform artifacts so the fix-run waveform gate passes.
        tb = kwargs.get("testbench_id") or "cg_nf"
        corner = kwargs.get("corner_id") or "tt"
        metrics_dir = (
            project_dir / "runs" / "real" / kwargs["run_id"]
            / "testbenches" / tb / "corners" / corner / "metrics"
        )
        (metrics_dir / "waveforms").mkdir(parents=True, exist_ok=True)
        (metrics_dir / "waveforms" / "nf_pnoise.csv").write_text("freq,nf\n", encoding="utf-8")
        (metrics_dir / "waveform_export_manifest.json").write_text("{}", encoding="utf-8")
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active > 1
    assert report.points[0].testbench_corner_count == 3


def test_fix_run_parallel_jobs_one_keeps_child_runs_serial(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    _strip_optimizer_configs_for_fix_run(project_dir)
    _set_spectre_parallel_jobs(project_dir, 1)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_fix_run_child_dirs(project_dir, run_id=run_id)
        return _mock_prepare_result(project_dir, run_id=run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        # Create waveform artifacts so the fix-run waveform gate passes.
        tb = kwargs.get("testbench_id") or "cg_nf"
        corner = kwargs.get("corner_id") or "tt"
        metrics_dir = (
            project_dir / "runs" / "real" / kwargs["run_id"]
            / "testbenches" / tb / "corners" / corner / "metrics"
        )
        (metrics_dir / "waveforms").mkdir(parents=True, exist_ok=True)
        (metrics_dir / "waveforms" / "nf_pnoise.csv").write_text("freq,nf\n", encoding="utf-8")
        (metrics_dir / "waveform_export_manifest.json").write_text("{}", encoding="utf-8")
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active == 1


# ---------------------------------------------------------------------------
# Failure preservation under parallelism: one failing child must not abort the
# others and must mark the parent report failed.
# ---------------------------------------------------------------------------
def test_fix_run_parallel_child_failure_preserved_and_report_fails(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    _strip_optimizer_configs_for_fix_run(project_dir)
    _set_spectre_parallel_jobs(project_dir, 2)

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_fix_run_child_dirs(project_dir, run_id=run_id)
        return _mock_prepare_result(project_dir, run_id=run_id)

    def adapter_side_effect(*args, **kwargs):
        corner = kwargs.get("corner_id")
        tb = kwargs.get("testbench_id") or "cg_nf"
        if corner != "ss":
            metrics_dir = (
                project_dir / "runs" / "real" / kwargs["run_id"]
                / "testbenches" / tb / "corners" / corner / "metrics"
            )
            (metrics_dir / "waveforms").mkdir(parents=True, exist_ok=True)
            (metrics_dir / "waveforms" / "nf_pnoise.csv").write_text("freq,nf\n", encoding="utf-8")
            (metrics_dir / "waveform_export_manifest.json").write_text("{}", encoding="utf-8")
            return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])
        return MagicMock(
            status="failed",
            run_id=kwargs["run_id"],
            result_manifest_path=project_dir / "runs" / "real" / kwargs["run_id"] / "result_manifest.json",
            metric_result_manifest_path=None,
            issues=["sim failed"],
        )

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "fail"
    assert report.points[0].testbench_corner_count == 3
    assert mock_adapter.call_count == 3
    assert any(
        "failed" in issue.message or "sim failed" in issue.message
        for issue in report.points[0].child_issues
    )
