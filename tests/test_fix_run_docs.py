"""Tests for fix-run documentation and template files.

TDD RED phase: these tests define the required documentation behavior
before the template/example files exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hermes_workflow.requirement_intake import parse_requirement_text

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_FIX_RUN = ROOT / "examples" / "spectre_maestro_project" / "opt_requirement.fix_run.md"
TEMPLATE_FIX_RUN = (
    ROOT
    / "src"
    / "hermes_workflow"
    / "templates"
    / "spectre_maestro_project"
    / "opt_requirement.fix_run.md"
)


# ---------------------------------------------------------------------------
# Test 1: Release example and packaged template are byte-for-byte identical
# ---------------------------------------------------------------------------
def test_example_and_template_are_identical() -> None:
    assert EXAMPLE_FIX_RUN.is_file(), f"Example file missing: {EXAMPLE_FIX_RUN}"
    assert TEMPLATE_FIX_RUN.is_file(), f"Template file missing: {TEMPLATE_FIX_RUN}"
    example_bytes = EXAMPLE_FIX_RUN.read_bytes()
    template_bytes = TEMPLATE_FIX_RUN.read_bytes()
    assert example_bytes == template_bytes, (
        "Example and template must be byte-for-byte identical"
    )


# ---------------------------------------------------------------------------
# Test 2: opt_requirement.fix_run.md parses as Workflow.mode: fix_run
# ---------------------------------------------------------------------------
def test_fix_run_requirement_parses_as_fix_run_mode() -> None:
    text = EXAMPLE_FIX_RUN.read_text(encoding="utf-8")
    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.status == "pass", f"Parse failed: {report.issues}"
    assert report.workflow_mode == "fix_run", (
        f"Expected workflow_mode 'fix_run', got '{report.workflow_mode}'"
    )


# ---------------------------------------------------------------------------
# Test 3: The example uses getData("NF" ?result "pnoise") — correct pnoise form
# ---------------------------------------------------------------------------
def test_example_uses_correct_pnoise_expression() -> None:
    text = EXAMPLE_FIX_RUN.read_text(encoding="utf-8")
    assert 'getData("NF" ?result "pnoise")' in text, (
        "Example must contain the correct pnoise expression: "
        'getData("NF" ?result "pnoise")'
    )


# ---------------------------------------------------------------------------
# Test 4: The example does NOT mention forbidden terms
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "forbidden",
    [
        "--fix-run",
        "--max-evals",
        "--parallel-jobs",
        "--strategy",
        "--multi-corner",
        "psfascii",
    ],
)
def test_example_does_not_mention_forbidden_terms(forbidden: str) -> None:
    text = EXAMPLE_FIX_RUN.read_text(encoding="utf-8")
    assert forbidden not in text, (
        f"Example must not contain forbidden term '{forbidden}'"
    )


# ---------------------------------------------------------------------------
# Test 5: The example includes Fixed Points section with at least one point
# ---------------------------------------------------------------------------
def test_example_includes_fixed_points_section() -> None:
    text = EXAMPLE_FIX_RUN.read_text(encoding="utf-8")
    assert "## Fixed Points" in text, "Example must include ## Fixed Points section"
    # Parse to verify there is at least one point
    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.status == "pass", f"Parse failed: {report.issues}"
    fixed_points = report.sections.get("Fixed Points", {})
    points = fixed_points.get("points", [])
    assert len(points) >= 1, "Fixed Points section must contain at least one point"


# ---------------------------------------------------------------------------
# Test 6: The example includes Waveform Exports section
# ---------------------------------------------------------------------------
def test_example_includes_waveform_exports_section() -> None:
    text = EXAMPLE_FIX_RUN.read_text(encoding="utf-8")
    assert "## Waveform Exports" in text, (
        "Example must include ## Waveform Exports section"
    )
    # Parse to verify the section is valid
    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.status == "pass", f"Parse failed: {report.issues}"
    waveform_exports = report.sections.get("Waveform Exports", {})
    exports = waveform_exports.get("exports", [])
    assert len(exports) >= 1, "Waveform Exports section must contain at least one export"
