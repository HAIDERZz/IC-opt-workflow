from __future__ import annotations

from pathlib import Path

from hermes_workflow.requirement_intake import (
    parse_requirement_text,
    render_config_payloads,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_TEMPLATE_ROOT = ROOT / "examples" / "spectre_maestro_project"
PACKAGED_TEMPLATE_ROOT = (
    ROOT
    / "src"
    / "hermes_workflow"
    / "templates"
    / "spectre_maestro_project"
)
STATIC_MIRROR_FILES = [
    "OPT_REQUIREMENT_README.md",
    "METRICS.md",
    "constraints.md",
]
EXPECTED_REQUIREMENT_TEMPLATES = {
    "opt_requirement.fix_run.md",
    "opt_requirement.fix_run.metrics_only.md",
    "opt_requirement.fix_run.multi_testbench.metrics_waveform.md",
    "opt_requirement.history_warm_start.md",
    "opt_requirement.history_warm_start.multi_corner.md",
    "opt_requirement.md",
    "opt_requirement.multi_corner.md",
    "opt_requirement.multi_tb_corner.md",
    "opt_requirement.multi_testbench.md",
    "opt_requirement.openbox_gp_eic.md",
    "opt_requirement.turbo.md",
}


def _requirement_template_names(root: Path) -> set[str]:
    return {path.name for path in root.glob("opt_requirement*.md")}


def _all_mirror_files() -> list[str]:
    return [
        *STATIC_MIRROR_FILES,
        *sorted(_requirement_template_names(PACKAGED_TEMPLATE_ROOT)),
    ]


REQUIRED_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "USER_GUIDE_CN.md",
    ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
    ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
    ROOT / "docs" / "OPTIMIZER_PRODUCTION_QUICKSTART.md",
    EXAMPLE_TEMPLATE_ROOT / "OPT_REQUIREMENT_README.md",
    PACKAGED_TEMPLATE_ROOT / "OPT_REQUIREMENT_README.md",
    ROOT / "skills" / "ic-opt" / "SKILL.md",
]
TEMPLATE_DISCOVERY_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "USER_GUIDE_CN.md",
    ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
    ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
    ROOT / "docs" / "OPTIMIZER_PRODUCTION_QUICKSTART.md",
    PACKAGED_TEMPLATE_ROOT / "OPT_REQUIREMENT_README.md",
    ROOT / "skills" / "ic-opt" / "SKILL.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_history_warm_start_docs_cover_runtime_contract() -> None:
    required_terms = [
        "History Warm Start",
        "history_warm_start",
        "opt_requirement.history_warm_start.md",
        "reports/history_warm_start_audit.json",
        "openbox.history_warm_start",
    ]
    for path in REQUIRED_DOCS:
        text = _read(path)
        missing = [term for term in required_terms if term not in text]
        assert not missing, f"{path.relative_to(ROOT)} missing {missing}"


def test_history_warm_start_docs_cover_mode_boundaries() -> None:
    boundary_docs = [
        ROOT / "README.md",
        ROOT / "docs" / "USER_GUIDE_CN.md",
        ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
        ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
        ROOT / "skills" / "ic-opt" / "SKILL.md",
    ]
    for path in boundary_docs:
        text = _read(path).lower()
        assert "optimize" in text, path.relative_to(ROOT)
        assert "fix-run" in text or "fix run" in text, path.relative_to(ROOT)
        assert "--continue" in text, path.relative_to(ROOT)


def test_history_warm_start_docs_do_not_invent_cli_flag() -> None:
    forbidden = "--history-warm-start"
    for path in REQUIRED_DOCS:
        assert forbidden not in _read(path), path.relative_to(ROOT)


def test_requirement_examples_are_mirrored_to_packaged_templates() -> None:
    example_templates = _requirement_template_names(EXAMPLE_TEMPLATE_ROOT)
    packaged_templates = _requirement_template_names(PACKAGED_TEMPLATE_ROOT)
    assert example_templates == EXPECTED_REQUIREMENT_TEMPLATES
    assert packaged_templates == EXPECTED_REQUIREMENT_TEMPLATES

    for relative_path in _all_mirror_files():
        example = EXAMPLE_TEMPLATE_ROOT / relative_path
        packaged = PACKAGED_TEMPLATE_ROOT / relative_path
        assert example.exists(), relative_path
        assert packaged.exists(), relative_path
        assert _read(example) == _read(packaged), relative_path


def test_all_requirement_templates_parse_and_render() -> None:
    for template_name in sorted(EXPECTED_REQUIREMENT_TEMPLATES):
        report = parse_requirement_text(
            _read(PACKAGED_TEMPLATE_ROOT / template_name),
            maestro_input_exists=lambda _path: True,
            model_file_is_readable=lambda _path: True,
        )
        assert report.status == "pass", (template_name, report.issues)
        payloads = render_config_payloads(
            report.sections,
            workflow_mode=report.workflow_mode,
        )
        assert payloads, template_name


def test_requirement_template_discovery_docs_name_complete_set() -> None:
    for path in TEMPLATE_DISCOVERY_DOCS:
        text = _read(path)
        missing = sorted(
            template_name
            for template_name in EXPECTED_REQUIREMENT_TEMPLATES
            if template_name not in text
        )
        assert not missing, f"{path.relative_to(ROOT)} missing {missing}"


def test_release_checklist_names_complete_requirement_mirror_set() -> None:
    text = _read(ROOT / "docs" / "PRODUCT_RELEASE_CHECKLIST.md")
    for relative_path in _all_mirror_files():
        assert f"examples/spectre_maestro_project/{relative_path}" in text
        assert (
            f"src/hermes_workflow/templates/spectre_maestro_project/{relative_path}"
            in text
        )
