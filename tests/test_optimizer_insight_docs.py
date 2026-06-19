from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

USER_AND_AGENT_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "USER_GUIDE_CN.md",
    ROOT / "docs" / "AGENT_OPTIMIZER_USAGE_MANUAL.md",
    ROOT / "docs" / "AGENT_USER_QUICKSTART_CN.md",
    ROOT / "skills" / "ic-opt" / "SKILL.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_optimizer_insight_docs_list_all_report_artifacts() -> None:
    required_terms = [
        "reports/optimizer_insight_report.json",
        "reports/optimizer_insight_report.md",
        "reports/optimizer_insight_report.html",
    ]
    for path in USER_AND_AGENT_DOCS:
        text = _read(path)
        missing = [term for term in required_terms if term not in text]
        assert not missing, f"{path.relative_to(ROOT)} missing {missing}"


def test_optimizer_insight_docs_describe_report_layer_boundaries() -> None:
    required_term_groups = [
        ("Pareto",),
        ("raw metrics",),
        ("OpenBox",),
        ("multi-objective",),
        ("Space Compression Advisory",),
        ("compressor dry-run",),
        ("advisory only", "只用于人工复盘", "只给出人工复盘建议"),
        ("not applied", "不会自动应用"),
    ]
    for path in USER_AND_AGENT_DOCS:
        text = " ".join(_read(path).split())
        missing = [
            terms[0]
            for terms in required_term_groups
            if not any(term in text for term in terms)
        ]
        assert not missing, f"{path.relative_to(ROOT)} missing {missing}"
