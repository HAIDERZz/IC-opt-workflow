"""Local fix-run orchestration flow.

Runs a set of fixed simulation points (no optimizer) through the Spectre/OCEAN
adapter, collects results, and writes a ``reports/fix_run_report.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.execution_adapters.spectre_ocean import run_spectre_ocean_adapter
from hermes_workflow.fix_run_models import (
    ChildRunIssue,
    FixRunPointReport,
    FixRunReport,
    FixedPointsConfig,
    WorkflowSettings,
)
from hermes_workflow.package import build_execution_package
from hermes_workflow.product_doctor import run_product_doctor
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
from hermes_workflow.requirement_intake import check_requirement, prepare_from_requirement
from hermes_workflow.validate import assert_valid_project

REPORT_RELATIVE = Path("reports/fix_run_report.json")


def _load_fixed_points(project_dir: Path) -> FixedPointsConfig:
    """Load and validate fixed_points.yaml from the project config directory."""
    path = project_dir / "config" / "fixed_points.yaml"
    if not path.exists():
        raise FileNotFoundError("config/fixed_points.yaml is missing")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FixedPointsConfig.model_validate(payload)


def _load_workflow_settings(project_dir: Path) -> WorkflowSettings | None:
    """Load workflow.yaml if it exists; return None otherwise."""
    path = project_dir / "config" / "workflow.yaml"
    if not path.exists():
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowSettings.model_validate(payload)


def _require_license_check(project_dir: Path) -> bool:
    """Return True if the project's Spectre settings require a license check."""
    try:
        bundle = assert_valid_project(project_dir)
        return bundle.spectre.spectre.require_license_check
    except (ValueError, FileNotFoundError):
        # If we cannot validate the project yet, default to True for safety
        return True


def _starting_run_id(project_dir: Path) -> str:
    """Determine the starting run_id from WorkflowSettings or default."""
    settings = _load_workflow_settings(project_dir)
    if settings is not None:
        return settings.starting_run_id
    return "real_001"


def _run_id_for_index(starting_run_id: str, index: int) -> str:
    """Convert a starting run_id and 0-based index to a concrete run_id.

    For starting_run_id='real_003' and index=0, returns 'real_003'.
    For index=1, returns 'real_004'.
    """
    prefix = starting_run_id.rsplit("_", 1)[0]
    base_num = int(starting_run_id.split("_")[1])
    return f"{prefix}_{base_num + index:03d}"


def _collect_child_runs(
    project_dir: Path,
    run_id: str,
) -> list[dict[str, str | None]]:
    """Discover testbench/corner child runs for a given run_id.

    Returns a list of dicts with keys ``testbench_id`` and ``corner_id``.
    """
    run_root = project_dir / "runs" / "real" / run_id
    children: list[dict[str, str | None]] = []

    if not run_root.is_dir():
        return children

    # Check for testbench subdirectories
    testbenches_dir = run_root / "testbenches"
    if testbenches_dir.is_dir():
        for tb_dir in sorted(testbenches_dir.iterdir()):
            if not tb_dir.is_dir():
                continue
            corners_dir = tb_dir / "corners"
            if corners_dir.is_dir():
                for corner_dir in sorted(corners_dir.iterdir()):
                    if corner_dir.is_dir():
                        children.append({
                            "testbench_id": tb_dir.name,
                            "corner_id": corner_dir.name,
                        })
            else:
                # Testbench without corners
                if (tb_dir / "real_run_manifest.json").exists():
                    children.append({
                        "testbench_id": tb_dir.name,
                        "corner_id": None,
                    })
        return children

    # Check for corners without testbenches (single-testbench corner project)
    corners_dir = run_root / "corners"
    if corners_dir.is_dir():
        for corner_dir in sorted(corners_dir.iterdir()):
            if corner_dir.is_dir():
                children.append({
                    "testbench_id": None,
                    "corner_id": corner_dir.name,
                })
        return children

    # Single testbench, no corners
    if (run_root / "real_run_manifest.json").exists():
        children.append({"testbench_id": None, "corner_id": None})

    return children


def run_fix_run_project(
    project_dir: str | Path,
    *,
    real: bool = True,
    cadence_cshrc: Path | None = None,
) -> FixRunReport:
    """Execute the fix-run workflow for a project.

    1. Checks requirement intake and confirms ``workflow_mode == "fix_run"``.
    2. Prepares the project from requirement.
    3. When ``real=True``, runs product doctor (if license check required),
       then iterates over fixed points, creating candidate requests and
       running the Spectre/OCEAN adapter for each testbench/corner.
    4. Writes ``reports/fix_run_report.json`` and returns a ``FixRunReport``.
    """
    project_root = Path(project_dir)

    # --- Requirement intake ---
    intake = check_requirement(project_root)
    if intake.status != "pass":
        raise ValueError("requirement intake failed: " + "; ".join(intake.issues))
    if intake.workflow_mode != "fix_run":
        raise ValueError(
            f"expected workflow_mode=fix_run, got {intake.workflow_mode}"
        )

    # --- Prepare from requirement ---
    prep = prepare_from_requirement(project_root)
    if prep.status != "pass":
        raise ValueError("prepare from requirement failed: " + "; ".join(prep.issues))

    # --- Load fixed points ---
    fixed_points_config = _load_fixed_points(project_root)
    starting_id = _starting_run_id(project_root)

    point_reports: list[FixRunPointReport] = []
    all_issues: list[str] = []

    if real:
        # --- Product doctor (if license check required) ---
        if _require_license_check(project_root):
            doctor_report = run_product_doctor(
                project_root,
                cadence_cshrc=cadence_cshrc,
            )
            if doctor_report.status != "pass":
                raise ValueError(
                    "doctor failed: " + "; ".join(doctor_report.issues)
                )

        # --- Build execution package and approve ---
        build_execution_package(
            project_root, created_at_utc="2026-06-01T00:00:00Z"
        )
        decide_first_real_run(
            project_root, created_at_utc="2026-06-01T00:10:00Z"
        )

        # --- Run each fixed point ---
        for point_index, point in enumerate(fixed_points_config.points):
            run_id = _run_id_for_index(starting_id, point_index)
            point_issues: list[str] = []
            child_issues: list[ChildRunIssue] = []
            scalar_manifest_paths: list[str] = []
            waveform_manifest_paths: list[str] = []
            csv_paths: list[str] = []

            # Prepare the real run package for this fixed point
            try:
                prepare_explicit_candidate_real_run(
                    project_root,
                    candidate_id=point.candidate_id,
                    source="fix_run_fixed_point",
                    parameters=point.parameters,
                    run_id=run_id,
                    allow_unresolved_batch_runs=True,
                    allow_optimizer_continuation=True,
                )
            except Exception as exc:
                point_issues.append(f"prepare failed: {exc}")
                point_reports.append(
                    FixRunPointReport(
                        candidate_id=point.candidate_id,
                        run_id=run_id,
                        testbench_corner_count=0,
                        scalar_metric_manifest_paths=[],
                        waveform_export_manifest_paths=[],
                        csv_artifact_paths=[],
                        issues=point_issues,
                        child_issues=child_issues,
                    )
                )
                all_issues.extend(point_issues)
                continue

            # Discover child runs (testbench/corner combinations)
            children = _collect_child_runs(project_root, run_id)

            # If no child runs discovered, run the top-level adapter
            if not children:
                children = [{"testbench_id": None, "corner_id": None}]

            # Run the Spectre/OCEAN adapter for each child
            for child in children:
                tb_id = child["testbench_id"]
                corner_id = child["corner_id"]

                try:
                    adapter_result = run_spectre_ocean_adapter(
                        project_root,
                        run_id=run_id,
                        testbench_id=tb_id,
                        corner_id=corner_id,
                    )
                except Exception as exc:
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=tb_id,
                            corner_id=corner_id,
                            message=f"adapter failed: {exc}",
                        )
                    )
                    continue

                if adapter_result.status != "succeeded":
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=tb_id,
                            corner_id=corner_id,
                            message=f"adapter status: {adapter_result.status}",
                        )
                    )

                # Collect manifest paths
                if adapter_result.metric_result_manifest_path is not None:
                    try:
                        rel = adapter_result.metric_result_manifest_path.relative_to(
                            project_root
                        )
                        scalar_manifest_paths.append(rel.as_posix())
                    except ValueError:
                        scalar_manifest_paths.append(
                            str(adapter_result.metric_result_manifest_path)
                        )

            point_reports.append(
                FixRunPointReport(
                    candidate_id=point.candidate_id,
                    run_id=run_id,
                    testbench_corner_count=len(children),
                    scalar_metric_manifest_paths=scalar_manifest_paths,
                    waveform_export_manifest_paths=waveform_manifest_paths,
                    csv_artifact_paths=csv_paths,
                    issues=point_issues,
                    child_issues=child_issues,
                )
            )
            all_issues.extend(point_issues)

    # --- Build report ---
    overall_status = "pass" if not all_issues else "fail"
    report = FixRunReport(
        schema_version="1.0",
        workflow_mode="fix_run",
        status=overall_status,
        points=point_reports,
        optimizer_state_created=False,
        optimizer_decision_report_created=False,
    )

    # --- Write report ---
    _write_report(project_root, report)

    return report


def _write_report(project_root: Path, report: FixRunReport) -> None:
    """Write the FixRunReport to reports/fix_run_report.json."""
    report_path = project_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
