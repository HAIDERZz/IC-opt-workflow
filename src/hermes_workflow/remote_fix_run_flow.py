"""Remote fix-run orchestration flow.

Mirrors the local fix_run_flow but uses remote execution via SSH runner.
Runs remote doctor, uploads artifacts, invokes remote Spectre/OCEAN per
fixed-point / testbench / corner, downloads results, and writes a
``reports/fix_run_report.json``.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.approvals import decide_fix_run_real_run
from hermes_workflow.fix_run_models import (
    ChildRunIssue,
    FixRunPointReport,
    FixRunReport,
    FixedPointsConfig,
    WorkflowSettings,
)
from hermes_workflow.package import build_execution_package
from hermes_workflow.real_run import prepare_explicit_candidate_real_run
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteSshRunner
from hermes_workflow.requirement_intake import check_requirement, prepare_from_requirement
from hermes_workflow.validate import assert_valid_project

from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_spectre_ocean_adapter,
)

REPORT_RELATIVE = Path("reports/fix_run_report.json")


@dataclass(frozen=True)
class _RemoteChildAdapterOutcome:
    testbench_id: str | None
    corner_id: str | None
    adapter_result: Any | None = None
    issue: ChildRunIssue | None = None


def _load_fixed_points(project_dir: Path) -> FixedPointsConfig:
    """Load and validate fixed_points.yaml from the project config directory."""
    import yaml

    path = project_dir / "config" / "fixed_points.yaml"
    if not path.exists():
        raise FileNotFoundError("config/fixed_points.yaml is missing")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FixedPointsConfig.model_validate(payload)


def _load_workflow_settings(project_dir: Path) -> WorkflowSettings | None:
    """Load workflow.yaml if it exists; return None otherwise."""
    import yaml

    path = project_dir / "config" / "workflow.yaml"
    if not path.exists():
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowSettings.model_validate(payload)


def _starting_run_id(project_dir: Path) -> str:
    """Determine the starting run_id from WorkflowSettings or default."""
    settings = _load_workflow_settings(project_dir)
    if settings is not None:
        return settings.starting_run_id
    return "real_001"


def _run_id_for_index(starting_run_id: str, index: int) -> str:
    """Convert a starting run_id and 0-based index to a concrete run_id."""
    prefix = starting_run_id.rsplit("_", 1)[0]
    base_num = int(starting_run_id.split("_")[1])
    return f"{prefix}_{base_num + index:03d}"


def _collect_child_runs(
    project_dir: Path,
    run_id: str,
) -> list[dict[str, str | None]]:
    """Discover testbench/corner child runs for a given run_id."""
    run_root = project_dir / "runs" / "real" / run_id
    children: list[dict[str, str | None]] = []

    if not run_root.is_dir():
        return children

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
                if (tb_dir / "real_run_manifest.json").exists():
                    children.append({
                        "testbench_id": tb_dir.name,
                        "corner_id": None,
                    })
        return children

    corners_dir = run_root / "corners"
    if corners_dir.is_dir():
        for corner_dir in sorted(corners_dir.iterdir()):
            if corner_dir.is_dir():
                children.append({
                    "testbench_id": None,
                    "corner_id": corner_dir.name,
                })
        return children

    if (run_root / "real_run_manifest.json").exists():
        children.append({"testbench_id": None, "corner_id": None})

    return children


def _relative_artifact_path(project_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def _collect_waveform_artifacts(
    project_dir: Path,
    run_id: str,
) -> tuple[list[str], list[str]]:
    run_root = project_dir / "runs" / "real" / run_id
    if not run_root.is_dir():
        return [], []

    manifest_paths = [
        _relative_artifact_path(project_dir, path)
        for path in sorted(run_root.rglob("metrics/waveform_export_manifest.json"))
        if path.is_file()
    ]
    csv_paths = [
        _relative_artifact_path(project_dir, path)
        for path in sorted(run_root.rglob("metrics/waveforms/*.csv"))
        if path.is_file()
    ]
    return manifest_paths, csv_paths


def _has_waveform_exports(project_dir: Path) -> bool:
    """Return True if the project declares waveform exports."""
    if (project_dir / "config" / "waveform_exports.yaml").exists():
        return True
    run_root = project_dir / "runs" / "real"
    if run_root.is_dir():
        for request_path in run_root.rglob("metric_extraction_request.json"):
            try:
                payload = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("waveform_exports"):
                return True
    return False


def _fix_run_parallel_jobs(project_dir: Path) -> int:
    """Resolve max concurrent remote child Spectre/OCEAN runs for one fixed
    point from ``Spectre Settings.parallel_jobs`` (clamped to >= 1). Falls
    back to serial (1) if the project cannot be fully validated here; the
    project is validated earlier by the execution-package/approval gate."""
    try:
        bundle = assert_valid_project(project_dir)
    except (ValueError, FileNotFoundError):
        return 1
    return max(1, int(bundle.spectre.spectre.parallel_jobs))


def _run_remote_child_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    child: dict[str, str | None],
) -> _RemoteChildAdapterOutcome:
    """Run the remote Spectre/OCEAN adapter for one child.

    Exceptions become ``ChildRunIssue`` so one child failure cannot abort the
    whole fixed point. Worker threads return outcomes; the main thread mutates
    shared report lists. The shared SSH runner is effectively stateless around
    a profile and an execute function, so concurrent worker calls are safe.
    """
    tb_id = child["testbench_id"]
    corner_id = child["corner_id"]
    try:
        adapter_result = run_remote_spectre_ocean_adapter(
            project_dir,
            run_id=run_id,
            remote_ref=remote_ref,
            remote_cadence_cshrc=remote_cadence_cshrc,
            runner=runner,
            testbench_id=tb_id,
            corner_id=corner_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _RemoteChildAdapterOutcome(
            testbench_id=tb_id,
            corner_id=corner_id,
            issue=ChildRunIssue(
                testbench_id=tb_id,
                corner_id=corner_id,
                message=f"adapter failed: {exc}",
            ),
        )
    return _RemoteChildAdapterOutcome(
        testbench_id=tb_id,
        corner_id=corner_id,
        adapter_result=adapter_result,
    )


def _run_remote_child_adapters(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    children: list[dict[str, str | None]],
    parallel_jobs: int,
) -> list[_RemoteChildAdapterOutcome]:
    """Run remote child adapters with bounded parallelism, returning outcomes
    in deterministic child order. No partial remote report sync happens inside
    worker threads."""
    if not children:
        return []
    max_workers = min(max(1, parallel_jobs), len(children))
    outcomes: list[_RemoteChildAdapterOutcome | None] = [None] * len(children)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                _run_remote_child_adapter,
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=runner,
                child=child,
            ): index
            for index, child in enumerate(children)
        }
        for future in as_completed(future_to_index):
            outcomes[future_to_index[future]] = future.result()
    return [outcome for outcome in outcomes if outcome is not None]


def run_remote_fix_run_project(
    remote_ref: RemoteProjectRef,
    *,
    remote_cadence_cshrc: PurePosixPath,
    real: bool = True,
    runner: Any | None = None,
) -> FixRunReport:
    """Execute the remote fix-run workflow for a project.

    1. Runs remote doctor and blocks on failure.
    2. Prepares remote project cache and uploads fixed-point request artifacts.
    3. For each fixed point, each testbench/corner combination, runs remote
       Spectre/OCEAN via ``run_remote_spectre_ocean_adapter()``.
    4. Downloads PSF, scalar outputs, OCEAN logs, waveform CSV files, and
       manifests.
    5. Writes ``reports/fix_run_report.json`` and returns a ``FixRunReport``.
    """
    ssh = runner or RemoteSshRunner(remote_ref.ssh_profile)

    # --- Remote doctor ---
    doctor = run_remote_doctor(
        remote_ref,
        runner=ssh,
        cadence_cshrc=remote_cadence_cshrc,
    )
    if doctor.status != "pass":
        raise ValueError("remote doctor failed: " + "; ".join(doctor.issues))

    # --- Prepare remote project cache ---
    prepared = prepare_remote_project_cache(remote_ref, runner=ssh)
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))

    project_dir = prepared.cache_dir

    # --- Requirement intake ---
    intake = check_requirement(project_dir)
    if intake.status != "pass":
        raise ValueError("requirement intake failed: " + "; ".join(intake.issues))
    if intake.workflow_mode != "fix_run":
        raise ValueError(
            f"expected workflow_mode=fix_run, got {intake.workflow_mode}"
        )

    # --- Prepare from requirement ---
    prep = prepare_from_requirement(project_dir)
    if prep.status != "pass":
        raise ValueError("prepare from requirement failed: " + "; ".join(prep.issues))

    # --- Load fixed points ---
    fixed_points_config = _load_fixed_points(project_dir)
    starting_id = _starting_run_id(project_dir)

    point_reports: list[FixRunPointReport] = []
    all_issues: list[str] = []

    if real:
        # --- Build execution package and approve ---
        build_execution_package(
            project_dir, created_at_utc="2026-06-01T00:00:00Z"
        )
        decide_fix_run_real_run(
            project_dir, created_at_utc="2026-06-01T00:10:00Z"
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
                    project_dir,
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
            children = _collect_child_runs(project_dir, run_id)

            # If no child runs discovered, run the top-level adapter
            if not children:
                children = [{"testbench_id": None, "corner_id": None}]

            # Run the remote Spectre/OCEAN adapter for each child with bounded
            # child-level parallelism. Worker threads return outcomes; the main
            # thread converts them into child_issues and manifest paths in
            # deterministic child order. Remote report sync stays after all
            # children complete (no partial sync inside workers).
            parallel_jobs = _fix_run_parallel_jobs(project_dir)
            child_outcomes = _run_remote_child_adapters(
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
                children=children,
                parallel_jobs=parallel_jobs,
            )

            for outcome in child_outcomes:
                if outcome.issue is not None:
                    child_issues.append(outcome.issue)
                    continue

                adapter_result = outcome.adapter_result
                if adapter_result is None:
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message="adapter produced no result",
                        )
                    )
                    continue

                if adapter_result.status != "succeeded":
                    adapter_detail = "; ".join(adapter_result.issues) if adapter_result.issues else adapter_result.status
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message=adapter_detail,
                        )
                    )

                # Collect manifest paths
                if adapter_result.metric_result_manifest_path is not None:
                    try:
                        rel = adapter_result.metric_result_manifest_path.relative_to(
                            project_dir
                        )
                        scalar_manifest_paths.append(rel.as_posix())
                    except ValueError:
                        scalar_manifest_paths.append(
                            str(adapter_result.metric_result_manifest_path)
                        )

            waveform_manifest_paths, csv_paths = _collect_waveform_artifacts(
                project_dir,
                run_id,
            )

            # Artifact gate parity with the local flow: when waveform exports
            # are configured, every child must produce its CSV and waveform
            # export manifest.
            if _has_waveform_exports(project_dir):
                expected = len(children)
                if len(waveform_manifest_paths) < expected:
                    missing = expected - len(waveform_manifest_paths)
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=None,
                            corner_id=None,
                            message=(
                                f"{missing} waveform_export_manifest.json missing "
                                f"(expected {expected})"
                            ),
                        )
                    )
                if len(csv_paths) < expected:
                    missing = expected - len(csv_paths)
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=None,
                            corner_id=None,
                            message=(
                                f"{missing} waveform CSV missing (expected {expected})"
                            ),
                        )
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
            for ci in child_issues:
                all_issues.append(f"child run {ci.testbench_id or ''}/{ci.corner_id or ''}: {ci.message}")

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
    _write_report(project_dir, report)

    # --- Sync report to remote ---
    _sync_report_to_remote(remote_ref, project_dir, ssh)

    return report


def _write_report(project_root: Path, report: FixRunReport) -> None:
    """Write the FixRunReport to reports/fix_run_report.json."""
    report_path = project_root / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sync_report_to_remote(
    ref: RemoteProjectRef,
    cache_dir: Path,
    ssh: Any,
) -> None:
    """Upload the fix-run report and run artifacts back to remote."""
    local_report = cache_dir / REPORT_RELATIVE
    if local_report.is_file():
        remote_report = ref.remote_project_dir / REPORT_RELATIVE
        try:
            ssh.upload(local_report, remote_report)
        except Exception:
            pass  # best-effort upload

    # Upload run artifacts (PSF, metrics, manifests) back to remote
    runs_dir = cache_dir / "runs"
    if runs_dir.is_dir():
        remote_runs = ref.remote_project_dir / "runs"
        try:
            ssh.upload_tree(runs_dir, remote_runs)
        except Exception:
            pass  # best-effort upload
