from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REPORT_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")
NATIVE_REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
NATIVE_EVALUATIONS_RELATIVE = Path("reports/native_turbo_optimizer_evaluations.jsonl")


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


def check_optimizer_run(project_dir: str | Path) -> OptimizerRunAcceptanceReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []

    native_report = _load_json(project_root / NATIVE_REPORT_RELATIVE, issues)
    traces = _load_jsonl(project_root / NATIVE_EVALUATIONS_RELATIVE, issues)

    if native_report.get("status") != "completed":
        issues.append("native turbo report status is not completed")

    evaluation_count = _int_value(native_report.get("evaluation_count"))
    if evaluation_count != len(traces):
        issues.append(
            f"evaluation count mismatch: report={evaluation_count} trace={len(traces)}"
        )

    status_counts = dict(Counter(_string_value(row.get("status")) for row in traces))
    result_manifest_count = 0
    result_success_count = 0
    metric_manifest_count = 0
    simulator_settings: list[dict[str, Any]] = []
    parallel_jobs: set[int] = set()

    for row in traces:
        run_id = _string_value(row.get("run_id"))
        result_relative = _string_value(row.get("result_manifest"))
        metric_relative = _string_value(row.get("metric_result_manifest"))
        if not run_id:
            issues.append("trace row is missing run_id")
        if isinstance(row.get("parallel_jobs"), int):
            parallel_jobs.add(row["parallel_jobs"])

        result_manifest = _load_optional_json(project_root, result_relative, issues)
        if not result_manifest:
            continue
        result_manifest_count += 1

        simulator = result_manifest.get("simulator")
        if isinstance(simulator, dict):
            simulator_settings.append(simulator)

        trace_status = _string_value(row.get("status"))
        result_status = _string_value(result_manifest.get("status"))
        if result_status != "succeeded" and trace_status != "real_check_failed":
            issues.append(f"{run_id} result failure is not reflected as real_check_failed")
        if result_status != "succeeded":
            continue
        result_success_count += 1

        if result_status == "succeeded":
            result_metric_relative = _string_value(
                result_manifest.get("metric_result_manifest")
            )
            if not result_metric_relative:
                issues.append(f"{run_id} result succeeded but lacks metric manifest")
                continue
            if not metric_relative:
                issues.append(f"{run_id} result succeeded but trace lacks metric manifest")
                continue

        metric_manifest = _load_optional_json(project_root, metric_relative, issues)
        if not metric_manifest:
            continue
        metric_manifest_count += 1

        metric_status = metric_manifest.get("status")
        if metric_status != "succeeded" and trace_status != "metric_check_failed":
            issues.append(
                f"{run_id} metric failure is not reflected as metric_check_failed"
            )

    settings = _summarize_settings(simulator_settings, parallel_jobs, issues)
    if result_manifest_count == 0 and native_report.get("status") == "completed":
        issues.append("native turbo report completed but no result manifests exist")
    elif result_success_count == 0 and native_report.get("status") == "completed":
        issues.append("native turbo report completed but no result manifests succeeded")

    status = "rejected" if issues else "accepted"
    report_path = project_root / REPORT_RELATIVE
    report = OptimizerRunAcceptanceReport(
        status=status,
        evaluation_count=evaluation_count,
        result_manifest_count=result_manifest_count,
        metric_manifest_count=metric_manifest_count,
        status_counts=status_counts,
        settings=settings,
        best_candidate=native_report.get("best_candidate"),
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


def _load_jsonl(path: Path, issues: list[str]) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(f"missing file: {path}")
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"invalid JSONL row: {path}:{line_number}: {exc}")
            continue
        if not isinstance(payload, dict):
            issues.append(f"JSONL row must contain an object: {path}:{line_number}")
            continue
        rows.append(payload)
    return rows


def _load_optional_json(
    project_dir: Path,
    relative_path: str,
    issues: list[str],
) -> dict[str, Any]:
    if not relative_path:
        issues.append("trace row is missing manifest path")
        return {}
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        issues.append(f"manifest path is not project-relative: {relative_path}")
        return {}
    return _load_json(project_dir / path, issues)


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


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""
