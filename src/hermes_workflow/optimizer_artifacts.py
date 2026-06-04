from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPORT_RELATIVE = Path("reports/optimizer_run_report.json")
EVALUATIONS_RELATIVE = Path("reports/optimizer_evaluations.jsonl")
LEGACY_NATIVE_REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
LEGACY_NATIVE_EVALUATIONS_RELATIVE = Path(
    "reports/native_turbo_optimizer_evaluations.jsonl"
)


@dataclass(frozen=True)
class OptimizerArtifacts:
    source: str
    report_relative: Path
    evaluations_relative: Path
    report: dict[str, Any]
    traces: list[dict[str, Any]]


def load_optimizer_artifacts(
    project_dir: str | Path,
    issues: list[str],
) -> OptimizerArtifacts:
    project_root = Path(project_dir)
    neutral_report = project_root / REPORT_RELATIVE
    neutral_evaluations = project_root / EVALUATIONS_RELATIVE
    if neutral_report.exists() or neutral_evaluations.exists():
        return OptimizerArtifacts(
            source="backend_neutral",
            report_relative=REPORT_RELATIVE,
            evaluations_relative=EVALUATIONS_RELATIVE,
            report=_load_json(neutral_report, issues),
            traces=_load_jsonl(neutral_evaluations, issues),
        )

    return OptimizerArtifacts(
        source="legacy_native_turbo",
        report_relative=LEGACY_NATIVE_REPORT_RELATIVE,
        evaluations_relative=LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        report=_load_json(project_root / LEGACY_NATIVE_REPORT_RELATIVE, issues),
        traces=_load_jsonl(project_root / LEGACY_NATIVE_EVALUATIONS_RELATIVE, issues),
    )


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
