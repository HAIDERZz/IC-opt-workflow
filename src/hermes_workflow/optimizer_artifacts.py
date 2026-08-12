from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes_workflow.native_turbo_history import (
    EVALUATIONS_RELATIVE as LEGACY_NATIVE_EVALUATIONS_RELATIVE,
)
from hermes_workflow.native_turbo_history import (
    REPORT_RELATIVE as LEGACY_NATIVE_REPORT_RELATIVE,
)

REPORT_RELATIVE = Path("reports/optimizer_run_report.json")
EVALUATIONS_RELATIVE = Path("reports/optimizer_evaluations.jsonl")
SUPPORTED_REPORT_RELATIVES = (
    REPORT_RELATIVE,
    LEGACY_NATIVE_REPORT_RELATIVE,
)
SUPPORTED_EVALUATIONS_RELATIVES = (
    EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_EVALUATIONS_RELATIVE,
)
SUPPORTED_ARTIFACT_RELATIVES = (
    *SUPPORTED_REPORT_RELATIVES,
    *SUPPORTED_EVALUATIONS_RELATIVES,
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
    *,
    expected_backend: str | None = None,
) -> OptimizerArtifacts:
    project_root = Path(project_dir)
    if expected_backend is not None:
        return _load_expected_backend_artifacts(
            project_root,
            issues,
            expected_backend=expected_backend,
        )

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


def _load_expected_backend_artifacts(
    project_root: Path,
    issues: list[str],
    *,
    expected_backend: str,
) -> OptimizerArtifacts:
    expected = normalize_optimizer_artifact_backend(expected_backend)
    if expected not in {"openbox", "native_turbo"}:
        issues.append(f"unsupported expected optimizer backend: {expected_backend}")
        return _empty_artifacts(expected_backend)

    candidates: list[tuple[str, Path, Path]] = []
    if expected == "native_turbo":
        candidates.append(
            (
                "legacy_native_turbo",
                LEGACY_NATIVE_REPORT_RELATIVE,
                LEGACY_NATIVE_EVALUATIONS_RELATIVE,
            )
        )
    candidates.append(("backend_neutral", REPORT_RELATIVE, EVALUATIONS_RELATIVE))

    observed: list[str] = []
    invalid_match: tuple[OptimizerArtifacts, list[str]] | None = None
    for source, report_relative, evaluations_relative in candidates:
        report_path = project_root / report_relative
        evaluations_path = project_root / evaluations_relative
        if not report_path.exists() and not evaluations_path.exists():
            continue

        candidate_issues: list[str] = []
        artifact = OptimizerArtifacts(
            source=source,
            report_relative=report_relative,
            evaluations_relative=evaluations_relative,
            report=_load_json(report_path, candidate_issues),
            traces=_load_jsonl(evaluations_path, candidate_issues),
        )
        actual = _artifact_backend(source, artifact.report)
        observed.append(f"{source}={actual or 'missing'}")
        if actual != expected:
            continue
        if not candidate_issues:
            return artifact
        if invalid_match is None:
            invalid_match = artifact, candidate_issues

    if invalid_match is not None:
        artifact, candidate_issues = invalid_match
        issues.extend(candidate_issues)
        return artifact

    detail = ", ".join(observed) if observed else "none"
    issues.append(
        f"optimizer artifacts do not match expected backend {expected}; "
        f"observed: {detail}"
    )
    return _empty_artifacts(expected)


def _artifact_backend(source: str, report: dict[str, Any]) -> str:
    raw = report.get("backend")
    if isinstance(raw, str) and raw:
        return normalize_optimizer_artifact_backend(raw)
    if source == "legacy_native_turbo":
        return "native_turbo"
    return ""


def normalize_optimizer_artifact_backend(backend: str) -> str:
    if backend == "turbo":
        return "native_turbo"
    if backend == "random_baseline":
        return "openbox"
    return backend


def _empty_artifacts(expected_backend: str) -> OptimizerArtifacts:
    if normalize_optimizer_artifact_backend(expected_backend) == "native_turbo":
        return OptimizerArtifacts(
            source="expected_native_turbo_missing",
            report_relative=LEGACY_NATIVE_REPORT_RELATIVE,
            evaluations_relative=LEGACY_NATIVE_EVALUATIONS_RELATIVE,
            report={},
            traces=[],
        )
    return OptimizerArtifacts(
        source="expected_openbox_missing",
        report_relative=REPORT_RELATIVE,
        evaluations_relative=EVALUATIONS_RELATIVE,
        report={},
        traces=[],
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
