from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_TEMPLATE_ROOT = ROOT / "examples" / "spectre_maestro_project"
PACKAGED_TEMPLATE_ROOT = (
    ROOT
    / "src"
    / "hermes_workflow"
    / "templates"
    / "spectre_maestro_project"
)
REQUIREMENT_MIRROR_FILES = [
    "OPT_REQUIREMENT_README.md",
    "opt_requirement.md",
    "opt_requirement.multi_corner.md",
    "opt_requirement.multi_testbench.md",
    "opt_requirement.multi_tb_corner.md",
    "opt_requirement.history_warm_start.md",
    "opt_requirement.fix_run.md",
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
    for relative_path in REQUIREMENT_MIRROR_FILES:
        example = EXAMPLE_TEMPLATE_ROOT / relative_path
        packaged = PACKAGED_TEMPLATE_ROOT / relative_path
        assert example.exists(), relative_path
        assert packaged.exists(), relative_path
        assert _read(example) == _read(packaged), relative_path


def test_release_checklist_names_complete_requirement_mirror_set() -> None:
    text = _read(ROOT / "docs" / "PRODUCT_RELEASE_CHECKLIST.md")
    for relative_path in REQUIREMENT_MIRROR_FILES:
        assert f"examples/spectre_maestro_project/{relative_path}" in text
        assert (
            f"src/hermes_workflow/templates/spectre_maestro_project/{relative_path}"
            in text
        )
