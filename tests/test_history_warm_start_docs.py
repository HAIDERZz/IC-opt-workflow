from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "USER_GUIDE_CN.md",
    ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
    ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
    ROOT / "docs" / "OPTIMIZER_PRODUCTION_QUICKSTART.md",
    ROOT / "examples" / "spectre_maestro_project" / "OPT_REQUIREMENT_README.md",
    ROOT
    / "src"
    / "hermes_workflow"
    / "templates"
    / "spectre_maestro_project"
    / "OPT_REQUIREMENT_README.md",
    ROOT / "skills" / "ic-opt" / "SKILL.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_history_warm_start_docs_cover_runtime_contract() -> None:
    required_terms = [
        "History Warm Start",
        "history_warm_start",
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


def test_history_warm_start_example_readme_is_mirrored_to_packaged_template() -> None:
    example = (
        ROOT / "examples" / "spectre_maestro_project" / "OPT_REQUIREMENT_README.md"
    )
    packaged = (
        ROOT
        / "src"
        / "hermes_workflow"
        / "templates"
        / "spectre_maestro_project"
        / "OPT_REQUIREMENT_README.md"
    )
    assert _read(example) == _read(packaged)
