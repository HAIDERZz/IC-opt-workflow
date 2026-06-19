from __future__ import annotations

from pathlib import Path


# Only tests that intentionally exercise the product/template API
# (create_project_from_template) itself. All other test files must use
# tests/project_factory.py or existing generic helpers instead.
INTENTIONAL_TEMPLATE_API_CALLERS = {
    "tests/test_package.py",
}


def test_create_project_from_template_usage_is_limited_to_product_template_api_tests() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "tests").glob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/test_template_coupling_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "create_project_from_template" in text and relative not in INTENTIONAL_TEMPLATE_API_CALLERS:
            offenders.append(relative)

    assert offenders == []
