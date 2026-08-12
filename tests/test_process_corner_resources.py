from __future__ import annotations

from pathlib import Path

from hermes_workflow.requirement_intake import parse_requirement_text


VALID_REQUIREMENT_PATH = Path(
    "tests/fixtures/requirement_intake/valid_project/opt_requirement.md"
)


def requirement_with_model_file(model_file: str) -> str:
    requirement_text = VALID_REQUIREMENT_PATH.read_text(encoding="utf-8").replace(
        "__MAESTRO_POINT_ROOT__",
        "/remote/maestro/Interactive.1/point_1",
    )
    process_corners = f"""## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: external_model
    model_file: {model_file}
```

"""
    return requirement_text.replace(
        "## Spectre Settings\n",
        process_corners + "## Spectre Settings\n",
    )


def test_parse_requirement_text_uses_injected_model_file_checker() -> None:
    checked: list[str] = []

    def remote_model_checker(path: str) -> bool:
        checked.append(path)
        return path == "/remote/pdk/models/device.scs"

    report = parse_requirement_text(
        requirement_with_model_file("/remote/pdk/models/device.scs"),
        constraints_text=None,
        maestro_input_exists=lambda _path: True,
        model_file_is_readable=remote_model_checker,
    )

    assert report.status == "pass", report.issues
    assert checked == ["/remote/pdk/models/device.scs"]


def test_parse_requirement_text_default_model_checker_requires_readable_file(
    tmp_path: Path,
) -> None:
    model_file = tmp_path / "device.scs"
    model_file.write_text("simulator lang=spectre\n", encoding="utf-8")
    model_file.chmod(0o000)
    try:
        report = parse_requirement_text(
            requirement_with_model_file(model_file.as_posix()),
            constraints_text=None,
            maestro_input_exists=lambda _path: True,
        )
    finally:
        model_file.chmod(0o600)

    assert report.status == "fail"
    assert report.issues == [
        f"Process Corners.model_file is missing or unreadable: {model_file}"
    ]
