"""Tests for fix-run documentation and template files.

TDD RED phase: these tests define the required documentation behavior
before the template/example files exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hermes_workflow.requirement_intake import parse_requirement_text

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

MIRRORED_TEMPLATE_FILES = [
    "OPT_REQUIREMENT_README.md",
    "METRICS.md",
    "constraints.md",
    "opt_requirement.md",
    "opt_requirement.multi_corner.md",
    "opt_requirement.multi_testbench.md",
    "opt_requirement.multi_tb_corner.md",
    "opt_requirement.fix_run.md",
]

DOCS_WITH_DOCTOR_REPORT_PATHS = [
    ROOT / "README.md",
    ROOT / "docs" / "TOOLCHAIN_EXECUTION_REFERENCE.md",
    ROOT / "docs" / "TROUBLESHOOTING_CN.md",
    ROOT / "docs" / "USER_GUIDE_CN.md",
    ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
    ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
    ROOT / "docs" / "OPTIMIZER_PRODUCTION_QUICKSTART.md",
    ROOT / "docs" / "OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md",
    ROOT / "docs" / "ROLE_MODEL_AND_TERMINOLOGY.md",
    ROOT / "skills" / "ic-opt" / "SKILL.md",
]


@pytest.mark.parametrize("relative_path", MIRRORED_TEMPLATE_FILES)
def test_release_examples_and_packaged_templates_are_identical(relative_path: str) -> None:
    example = ROOT / "examples" / "spectre_maestro_project" / relative_path
    template = ROOT / "src" / "hermes_workflow" / "templates" / "spectre_maestro_project" / relative_path
    assert example.is_file(), f"Example file missing: {example}"
    assert template.is_file(), f"Template file missing: {template}"
    example_bytes = example.read_bytes()
    template_bytes = template.read_bytes()
    assert example_bytes == template_bytes, (
        f"Release example and packaged template must match: {relative_path}"
    )


def test_opt_requirement_readme_matches_current_release_contract() -> None:
    readme = ROOT / "examples" / "spectre_maestro_project" / "OPT_REQUIREMENT_README.md"
    text = readme.read_text(encoding="utf-8")
    assert "This directory contains five requirement templates." in text
    assert "`opt_requirement.fix_run.md`" in text
    assert "ic-opt <project> --real --continue N" in text
    assert "ic-opt <project> --continue N" not in text
    assert "```yaml\nalgorithm: openbox\nstrategy: openbox_prf_eic" in text
    assert "```yaml\nalgorithm: turbo\nstrategy: turbo_trust_region" not in text


@pytest.mark.parametrize("path", DOCS_WITH_DOCTOR_REPORT_PATHS)
def test_user_and_agent_docs_use_real_doctor_report_path(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "reports/project_doctor_report.json" not in text
    assert "reports/ic_opt_doctor_report.json" in text


def test_release_checklist_mentions_template_mirror_guards() -> None:
    checklist = ROOT / "docs" / "PRODUCT_RELEASE_CHECKLIST.md"
    text = checklist.read_text(encoding="utf-8")
    required = [
        "tests/test_fix_run_docs.py",
        "tests/test_package.py",
        "examples/spectre_maestro_project/OPT_REQUIREMENT_README.md",
        "src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md",
        "./.venv/bin/python -m pytest tests/test_fix_run_docs.py tests/test_package.py -q",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []


def test_release_checklist_tracks_post_release_template_decoupling() -> None:
    """Non-blocking guard: the post-v0.1.8 follow-up to migrate generic tests
    off create_project_from_template() must stay documented so it is not lost.
    This does NOT fail on the current (still template-using) state."""
    checklist = ROOT / "docs" / "PRODUCT_RELEASE_CHECKLIST.md"
    text = checklist.read_text(encoding="utf-8")
    assert "Post-v0.1.8 Follow-up" in text
    assert "create_project_from_template()" in text
    assert "tests/helpers/project_factory.py" in text


def test_generic_tests_are_known_to_still_use_release_template() -> None:
    """Informational, non-blocking snapshot of which test files still reference
    the packaged release template factory. It records the current migration
    backlog without asserting it is empty (see the post-v0.1.8 follow-up)."""
    tests_dir = ROOT / "tests"
    dependents = sorted(
        path.relative_to(ROOT).as_posix()
        for path in tests_dir.rglob("*.py")
        if "create_project_from_template" in path.read_text(encoding="utf-8")
    )
    # Only assert the snapshot mechanism works; the list itself is the backlog.
    assert isinstance(dependents, list)
    assert "tests/test_package.py" in dependents  # legitimate contract user


    roots = [
        ROOT / "README.md",
        ROOT / "docs",
        ROOT / "skills",
        ROOT / "examples",
        ROOT / "src" / "hermes_workflow" / "templates",
    ]
    paths = [roots[0]]
    for root in roots[1:]:
        paths.extend(sorted(root.rglob("*.md")))
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in paths
        if "reports/project_doctor_report.json" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


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
