from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: DiagnosticSeverity
    stage: str
    component: str
    message: str
    detail: str | None = None
    likely_cause: str | None = None
    recommended_action: str | None = None
    evidence: list[str] = Field(default_factory=list)


def parse_diagnostics(items: Iterable[object]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for item in items:
        if isinstance(item, Diagnostic):
            diagnostics.append(item)
            continue
        if isinstance(item, dict):
            diagnostics.append(Diagnostic.model_validate(item))
    return diagnostics


def _emit_diagnostic_lines(diagnostic: Diagnostic) -> list[str]:
    lines = [
        f"[{diagnostic.severity.value.upper()}] {diagnostic.code}",
        f"Stage: {diagnostic.stage}",
        f"Component: {diagnostic.component}",
        f"Message: {diagnostic.message}",
    ]
    if diagnostic.detail is not None:
        lines.append(f"Detail: {diagnostic.detail}")
    if diagnostic.likely_cause is not None:
        lines.append(f"Likely cause: {diagnostic.likely_cause}")
    if diagnostic.recommended_action is not None:
        lines.append(f"Action: {diagnostic.recommended_action}")
    if diagnostic.evidence:
        lines.append(f"Evidence: {', '.join(diagnostic.evidence)}")
    return lines


def diagnostic_to_issue(diagnostic: Diagnostic) -> str:
    return (
        f"{_emit_diagnostic_lines(diagnostic)[0]}: "
        f"{diagnostic.message} ({diagnostic.code})"
    )


def format_diagnostics_for_cli(
    diagnostics: Iterable[Diagnostic],
    fallback_issues: Sequence[str] | None = None,
) -> list[str]:
    output: list[str] = []
    for diagnostic in diagnostics:
        output.extend(_emit_diagnostic_lines(diagnostic))
        output.append("")

    if fallback_issues and not diagnostics:
        output.append("[WARN] ISSUES")
        output.extend(f"- {issue}" for issue in fallback_issues)
        output.append("")

    return output
