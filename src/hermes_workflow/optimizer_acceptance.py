from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts
from hermes_workflow.optimizer_trace_identity import (
    optimizer_trace_identity_issues,
)
from hermes_workflow.optimizer_trace_science import (
    DUPLICATE_SKIPPED,
    select_best_trace,
    validate_trace_science,
)
from hermes_workflow.real_run import RUN_ID_RE
from hermes_workflow.retention_evidence import (
    materialize_decision_bound_retention_evidence,
)
from hermes_workflow.validate import load_contract_bundle, require_optimize_bundle


REPORT_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")


@dataclass(frozen=True)
class OptimizerRunAcceptanceReport:
    status: str
    evaluation_count: int
    result_manifest_count: int
    metric_manifest_count: int
    status_counts: dict[str, int]
    settings: dict[str, Any]
    best_candidate: dict[str, Any] | None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None


def check_optimizer_run(
    project_dir: str | Path,
    *,
    expected_backend: str | None = None,
    supplementary_artifact_root: str | Path | None = None,
) -> OptimizerRunAcceptanceReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []
    artifacts = load_optimizer_artifacts(
        project_root,
        issues,
        expected_backend=expected_backend,
    )
    native_report = artifacts.report
    traces = artifacts.traces
    if supplementary_artifact_root is not None:
        supplementary_root = Path(supplementary_artifact_root)
    else:
        run_ids = {
            value
            for row in traces
            if isinstance((value := row.get("run_id")), str)
            and RUN_ID_RE.fullmatch(value) is not None
        }
        try:
            supplementary_root = materialize_decision_bound_retention_evidence(
                project_root,
                run_ids=run_ids,
                action_field="local_action",
                canonical_missing_only=True,
            )
        except RuntimeError as exc:
            supplementary_root = None
            issues.append(f"retention evidence is invalid: {exc}")
    backend = _string_value(native_report.get("backend"))
    candidate_backend = (
        backend
        if backend
        else "native_turbo"
        if artifacts.source == "legacy_native_turbo"
        else ""
    )
    is_fake = _string_value(native_report.get("execution_mode")) == "fake"

    if native_report.get("status") != "completed":
        issues.append("optimizer report status is not completed")
    if is_fake and backend != "openbox":
        issues.append("fake optimizer artifacts are only accepted for backend=openbox")

    metrics_config = None
    optimizer_config = None
    if not is_fake:
        try:
            bundle = require_optimize_bundle(
                load_contract_bundle(project_root),
                operation="optimizer acceptance",
            )
        except ValueError as exc:
            issues.append(f"optimizer scientific contract is invalid: {exc}")
        else:
            metrics_config = bundle.metrics
            optimizer_config = bundle.optimizer

    # Fail-closed on any issue the optimizer writer recorded in the report.
    # Best-effort writers (B-09 progress-state sync, etc.) log structured
    # failures here; acceptance must surface them instead of silently accepting.
    if "issues" in native_report:
        report_issues = native_report["issues"]
        if isinstance(report_issues, list):
            for entry in report_issues:
                if isinstance(entry, str) and entry:
                    issues.append(f"optimizer report issue: {entry}")
                elif entry is not None:
                    issues.append(
                        f"optimizer report issue: {entry!r}"
                    )
        else:
            issues.append("optimizer report issues must be a list")

    evaluation_count = _int_value(native_report.get("evaluation_count"))
    if evaluation_count != len(traces):
        issues.append(
            f"evaluation count mismatch: report={evaluation_count} trace={len(traces)}"
        )
    issues.extend(optimizer_trace_identity_issues(traces, is_fake=is_fake))

    status_counts = dict(Counter(_string_value(row.get("status")) for row in traces))
    result_manifest_count = 0
    result_success_count = 0
    metric_manifest_count = 0
    simulator_settings: list[dict[str, Any]] = []
    parallel_jobs: set[int] = set()
    verified_traces: list[dict[str, Any]] = []

    for row in traces:
        run_id = _string_value(row.get("run_id"))
        result_relative = _string_value(row.get("result_manifest"))
        metric_relative = _string_value(row.get("metric_result_manifest"))
        trace_candidate_id = _string_value(row.get("candidate_id"))
        if not run_id:
            issues.append("trace row is missing run_id")
        if isinstance(row.get("parallel_jobs"), int):
            parallel_jobs.add(row["parallel_jobs"])
        if is_fake:
            if result_relative or metric_relative:
                warnings.append(f"{run_id} fake row includes manifest paths")
            verified_traces.append(dict(row))
            continue
        trace_status = _string_value(row.get("status"))
        if trace_status == DUPLICATE_SKIPPED:
            if candidate_backend != "native_turbo":
                issues.append(
                    f"{run_id} duplicate_candidate_skipped is only valid for "
                    "backend=native_turbo"
                )
            if metrics_config is not None and optimizer_config is not None:
                validation = validate_trace_science(
                    row,
                    result_manifest={},
                    metric_manifest=None,
                    metrics_config=metrics_config,
                    optimizer_config=optimizer_config,
                )
                issues.extend(validation.issues)
                if validation.verified_row is not None:
                    verified_traces.append(validation.verified_row)
            continue

        expected_result_relative = (
            f"runs/real/{run_id}/result_manifest.json"
        )
        if result_relative != expected_result_relative:
            issues.append(
                f"{run_id} trace does not reference its canonical result manifest: "
                f"{result_relative!r}"
            )
        expected_metric_relative = (
            f"runs/real/{run_id}/metrics/metric_result_manifest.json"
        )
        if metric_relative and metric_relative != expected_metric_relative:
            issues.append(
                f"{run_id} trace does not reference its canonical metric manifest: "
                f"{metric_relative!r}"
            )

        result_manifest = _load_optional_json(
            project_root,
            result_relative,
            issues,
            supplementary_root=supplementary_root,
        )
        if not result_manifest:
            continue
        result_manifest_count += 1

        result_run_id = _string_value(result_manifest.get("run_id"))
        if result_run_id != run_id:
            issues.append(
                f"{run_id} result manifest run_id mismatch: {result_run_id!r}"
            )
        result_candidate_id = _string_value(
            result_manifest.get("candidate_id")
        )
        if not result_candidate_id:
            issues.append(f"{run_id} result manifest candidate_id is missing")
        else:
            expected_candidate_id = _expected_candidate_id(
                backend=candidate_backend,
                run_id=run_id,
                evaluation_index=row.get("evaluation_index"),
            )
            if (
                expected_candidate_id is not None
                and result_candidate_id != expected_candidate_id
            ):
                issues.append(
                    f"{run_id} result manifest candidate_id mismatch: "
                    f"expected={expected_candidate_id!r}, "
                    f"actual={result_candidate_id!r}"
                )
        if trace_candidate_id and result_candidate_id != trace_candidate_id:
            issues.append(
                f"{run_id} result/trace candidate_id mismatch: "
                f"result={result_candidate_id!r}, trace={trace_candidate_id!r}"
            )
        result_metric_relative = _string_value(
            result_manifest.get("metric_result_manifest")
        )
        result_status = _string_value(result_manifest.get("status"))
        if result_metric_relative != metric_relative and (
            result_status == "succeeded" or bool(metric_relative)
        ):
            issues.append(
                f"{run_id} result/trace metric manifest mismatch: "
                f"result={result_metric_relative!r}, trace={metric_relative!r}"
            )
        if (
            result_metric_relative
            and result_metric_relative != expected_metric_relative
        ):
            issues.append(
                f"{run_id} result does not reference its canonical metric manifest: "
                f"{result_metric_relative!r}"
            )

        simulator = result_manifest.get("simulator")
        if isinstance(simulator, dict):
            simulator_settings.append(simulator)

        if result_status != "succeeded":
            if trace_status != "real_check_failed":
                issues.append(
                    f"{run_id} result failure is not reflected as "
                    "real_check_failed"
                )
            if metrics_config is not None and optimizer_config is not None:
                validation = validate_trace_science(
                    row,
                    result_manifest=result_manifest,
                    metric_manifest=None,
                    metrics_config=metrics_config,
                    optimizer_config=optimizer_config,
                )
                issues.extend(validation.issues)
                if validation.verified_row is not None:
                    verified_traces.append(validation.verified_row)
            continue
        result_success_count += 1

        if result_status == "succeeded":
            if not result_metric_relative:
                issues.append(f"{run_id} result succeeded but lacks metric manifest")
                continue
            if not metric_relative:
                issues.append(f"{run_id} result succeeded but trace lacks metric manifest")
                continue

        metric_manifest = _load_optional_json(
            project_root,
            metric_relative,
            issues,
            supplementary_root=supplementary_root,
        )
        if not metric_manifest:
            continue
        metric_manifest_count += 1

        metric_run_id = _string_value(metric_manifest.get("run_id"))
        if metric_run_id != run_id:
            issues.append(
                f"{run_id} metric manifest run_id mismatch: {metric_run_id!r}"
            )
        metric_candidate_id = _string_value(
            metric_manifest.get("candidate_id")
        )
        if not metric_candidate_id:
            issues.append(f"{run_id} metric manifest candidate_id is missing")
        elif metric_candidate_id != result_candidate_id:
            issues.append(
                f"{run_id} metric/result candidate_id mismatch: "
                f"metric={metric_candidate_id!r}, result={result_candidate_id!r}"
            )
        if trace_candidate_id and metric_candidate_id != trace_candidate_id:
            issues.append(
                f"{run_id} metric/trace candidate_id mismatch: "
                f"metric={metric_candidate_id!r}, trace={trace_candidate_id!r}"
            )

        if metrics_config is not None and optimizer_config is not None:
            validation = validate_trace_science(
                row,
                result_manifest=result_manifest,
                metric_manifest=metric_manifest,
                metrics_config=metrics_config,
                optimizer_config=optimizer_config,
            )
            issues.extend(validation.issues)
            if validation.verified_row is not None:
                verified_traces.append(validation.verified_row)

    settings = _summarize_settings(simulator_settings, parallel_jobs, issues)
    if not is_fake and result_manifest_count == 0 and native_report.get("status") == "completed":
        issues.append("optimizer report completed but no result manifests exist")
    elif (
        not is_fake
        and result_success_count == 0
        and native_report.get("status") == "completed"
    ):
        issues.append("optimizer report completed but no result manifests succeeded")

    recomputed_best = select_best_trace(verified_traces)
    if native_report.get("best_candidate") != recomputed_best:
        issues.append(
            "optimizer report best_candidate does not match recomputed verified trace"
        )

    status = "rejected" if issues else "accepted"
    report_path = project_root / REPORT_RELATIVE
    report = OptimizerRunAcceptanceReport(
        status=status,
        evaluation_count=evaluation_count,
        result_manifest_count=result_manifest_count,
        metric_manifest_count=metric_manifest_count,
        status_counts=status_counts,
        settings=settings,
        best_candidate=recomputed_best,
        issues=issues,
        warnings=warnings,
        report_path=report_path,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["report_path"] = REPORT_RELATIVE.as_posix()
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _load_json(path: Path, issues: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(f"missing file: {path}")
        return {}
    except json.JSONDecodeError as exc:
        issues.append(f"invalid JSON: {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"JSON file must contain an object: {path}")
        return {}
    return payload


def _load_optional_json(
    project_dir: Path,
    relative_path: str,
    issues: list[str],
    *,
    supplementary_root: Path | None = None,
) -> dict[str, Any]:
    if not relative_path:
        issues.append("trace row is missing manifest path")
        return {}
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        issues.append(f"manifest path is not project-relative: {relative_path}")
        return {}
    primary = project_dir / path
    supplementary = (
        supplementary_root / path if supplementary_root is not None else None
    )
    if supplementary is not None and supplementary.is_file():
        return _load_json(supplementary, issues)
    return _load_json(primary, issues)


def _summarize_settings(
    simulator_settings: list[dict[str, Any]],
    parallel_jobs: set[int],
    issues: list[str],
) -> dict[str, Any]:
    if not simulator_settings:
        return {}
    keys = ("preset", "threads_per_run", "output_format")
    summary: dict[str, Any] = {}
    for key in keys:
        values = {settings.get(key) for settings in simulator_settings}
        if len(values) > 1:
            issues.append(f"Spectre setting drift detected: {key}")
        summary[key] = next(iter(values))
    if len(parallel_jobs) > 1:
        issues.append("Spectre setting drift detected: parallel_jobs")
    if parallel_jobs:
        summary["parallel_jobs"] = next(iter(parallel_jobs))
    return summary


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _expected_candidate_id(
    *,
    backend: str,
    run_id: str,
    evaluation_index: object,
) -> str | None:
    if backend == "native_turbo":
        suffix = run_id.removeprefix("real_")
        if not suffix.isdecimal():
            return None
        run_number = int(suffix)
        return f"candidate_{run_number:06d}"
    if (
        backend == "openbox"
        and isinstance(evaluation_index, int)
        and not isinstance(evaluation_index, bool)
    ):
        return f"candidate_{evaluation_index:06d}"
    return None


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""
