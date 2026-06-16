"""Tests for the local fix-run orchestration flow."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from hermes_workflow.fix_run_models import (
    FixRunPointReport,
    FixRunReport,
)
from hermes_workflow.package import create_project_from_template


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")


def _create_fix_run_project(tmp_path: Path) -> Path:
    """Create a minimal project with fix_run mode configured."""
    project_dir = tmp_path / "fix_run_test_inv"
    create_project_from_template(project_dir)
    _write_template(project_dir)

    # Write workflow.yaml to set fix_run mode
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
                        "parameters": {"FN": "2", "WN": "0.3u", "FP": "2", "WP": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    return project_dir


def _create_two_point_fix_run_project(tmp_path: Path) -> Path:
    """Create a fix_run project with two fixed points."""
    project_dir = tmp_path / "fix_run_two_points"
    create_project_from_template(project_dir)
    _write_template(project_dir)

    # Write workflow.yaml
    workflow_yaml = project_dir / "config" / "workflow.yaml"
    workflow_yaml.write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    # Write fixed_points.yaml with TWO points
    fixed_points_yaml = project_dir / "config" / "fixed_points.yaml"
    fixed_points_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {
                            "FN": "2",
                            "WN": "0.3u",
                            "FP": "2",
                            "WP": "0.3u",
                        },
                    },
                    {
                        "candidate_id": "user_point_002",
                        "parameters": {
                            "FN": "4",
                            "WN": "0.5u",
                            "FP": "4",
                            "WP": "0.5u",
                        },
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
        assert call_kwargs.kwargs["candidate_id"] == "user_point_001"
        assert call_kwargs.kwargs["parameters"] == {
            "FN": "2",
            "WN": "0.3u",
            "FP": "2",
            "WP": "0.3u",
        }


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
        assert report.points[0].candidate_id == "user_point_001"
        assert report.points[0].run_id == "real_001"
        assert report.optimizer_state_created is False
        assert report.optimizer_decision_report_created is False
