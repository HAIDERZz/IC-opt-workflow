from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.diagnostics import DiagnosticSeverity
from hermes_workflow.requirement_intake import (
    check_requirement,
    import_maestro_point_netlist,
    prepare_from_requirement,
)
from hermes_workflow.reports import PassFail
from hermes_workflow.schemas import ProcessCornerConfig
from hermes_workflow.validate import validate_project_files

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "requirement_intake"
VALID_PROJECT = FIXTURE_ROOT / "valid_project"
VALID_MAESTRO_POINT = FIXTURE_ROOT / "valid_maestro_point"


def _copy_requirement_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    shutil.copytree(VALID_PROJECT, project_dir)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("__MAESTRO_POINT_ROOT__", VALID_MAESTRO_POINT.as_posix())
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")
    return project_dir


def _copy_maestro_point(tmp_path: Path) -> Path:
    point = tmp_path / "maestro_point"
    shutil.copytree(VALID_MAESTRO_POINT, point)
    return point


def _replace_section_yaml(text: str, section: str, yaml_text: str) -> str:
    heading = f"## {section}\n"
    start = text.index(heading) + len(heading)
    block_start = text.index("```yaml", start)
    block_end = text.index("```", block_start + len("```yaml"))
    return (
        text[:block_start]
        + "```yaml\n"
        + yaml_text.strip()
        + "\n```"
        + text[block_end + len("```") :]
    )


def _copy_multi_testbench_requirement_project(tmp_path: Path) -> Path:
    project_dir = _copy_requirement_project(tmp_path)
    second_point = tmp_path / "iip3_point"
    shutil.copytree(VALID_MAESTRO_POINT, second_point)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    maestro_yaml = f"""
testbenches:
  - id: cg_nf
    maestro_point_root: {VALID_MAESTRO_POINT.as_posix()}
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: CG_NF_Test
    corner: Nominal
  - id: iip3
    maestro_point_root: {second_point.as_posix()}
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: IIP3_Test
    corner: Nominal
"""
    metrics_yaml = """
- name: MAX_GAIN
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("gain" ?result "pac") 3e+09)
- name: IIP3
  unit: dBm
  testbench: iip3
  ocean_expression: value(getData("iip3" ?result "hb") 3e+09)
"""
    constraints_yaml = """
- metric: MAX_GAIN
  op: gt
  value: "5 dB"
- metric: IIP3
  op: gt
  value: "0 dBm"
"""
    objective_yaml = """
direction: maximize
expression: "MAX_GAIN + IIP3"
"""
    text = _replace_section_yaml(text, "Maestro Source", maestro_yaml)
    text = _replace_section_yaml(text, "Metrics", metrics_yaml)
    text = _replace_section_yaml(text, "Constraints", constraints_yaml)
    text = _replace_section_yaml(text, "Objective", objective_yaml)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")
    return project_dir


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_check_requirement_reports_missing_file(tmp_path: Path) -> None:
    report = check_requirement(tmp_path / "missing_project")

    assert report.status == "fail"
    assert "opt_requirement.md is missing" in report.issues
    assert len(report.structured_issues) == 1
    assert report.structured_issues[0].code == "REQUIREMENT_SECTION_MISSING"
    assert (tmp_path / "missing_project" / "reports" / "requirement_intake_report.json").exists()


def test_check_requirement_rejects_missing_required_heading(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("## Metrics\n", "")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "required section is missing: Metrics" in report.issues
    assert any(
        issue.code == "REQUIREMENT_SECTION_MISSING" for issue in report.structured_issues
    )


def test_check_requirement_rejects_duplicate_required_heading(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    path = project_dir / "opt_requirement.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n## Metrics\n", encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "required section appears more than once: Metrics" in report.issues


def test_check_requirement_rejects_missing_yaml_block(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("```yaml\nproject_name:", "```text\nproject_name:", 1)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "required section Project must contain exactly one fenced yaml block" in report.issues


def test_check_requirement_rejects_invalid_yaml(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("project_name: bridge_test_inv", "project_name: [", 1)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any(issue.startswith("invalid YAML in Project:") for issue in report.issues)


def test_check_requirement_rejects_duplicate_yaml_key(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        "project_name: bridge_test_inv",
        "project_name: bridge_test_inv\nproject_name: duplicate",
        1,
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any(
        issue.startswith("invalid YAML in Project:") and "duplicate key 'project_name'" in issue
        for issue in report.issues
    )


def test_check_requirement_rejects_unapproved_checklist(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("metric_formulas_user_approved: true", "metric_formulas_user_approved: false")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "approval checklist metric_formulas_user_approved must be true" in report.issues


def test_check_requirement_rejects_unknown_objective_metric(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        "expression: \"(rise + fall) * DC\"",
        "expression: \"(rise + NF_3G)\"",
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "objective expression references unknown metric NF_3G" in report.issues
    assert len(report.structured_issues) == 1
    assert report.structured_issues[0].code == "OBJECTIVE_UNKNOWN_METRIC"
    assert report.structured_issues[0].severity == DiagnosticSeverity.ERROR
    assert report.structured_issues[0].message == (
        "Objective expression references unknown metric NF_3G."
    )

def test_check_requirement_writes_structured_diagnostics_to_report_json(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace('name: DC', 'name: P1dB', 1)
    text = text.replace('metric: DC', 'metric: P1dB', 1)
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        'expression: "(rise + P1DB)"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)
    assert report.status == "fail"

    path = project_dir / "reports" / "requirement_intake_report.json"
    state = _load_json(path)

    assert report.structured_issues[0].code == state["structured_issues"][0]["code"]
    assert state["issues"] == report.issues

def test_check_requirement_reports_no_structured_issues_for_valid_requirements(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)

    report = check_requirement(project_dir)

    assert report.status == "pass"
    assert report.structured_issues == []


def test_check_requirement_suggests_close_objective_metric_name(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("name: DC", "name: P1dB", 1)
    text = text.replace("metric: DC", "metric: P1dB", 1)
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        'expression: "P1DB + rise"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert (
        "objective expression references unknown metric P1DB; did you mean P1dB?"
        in report.issues
    )
    assert any(
        issue.code == "OBJECTIVE_UNKNOWN_METRIC"
        and "P1DB" in issue.message
        and issue.recommended_action is not None
        for issue in report.structured_issues
    )


def test_check_requirement_handles_non_mapping_metric_item(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '  - /M0/S\n```',
        '  - /M0/S\n- BAD\n```',
        1,
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any(
        issue.startswith("rendered config validation failed")
        or "metric names must be unique" in issue
        or "metric names must be a YAML mapping" in issue
        for issue in report.issues
    )


def test_check_requirement_rejects_unknown_constraint_metric(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("metric: fall", "metric: NF_3G", 1)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "constraint references unknown metric NF_3G" in report.issues


def test_check_requirement_rejects_unknown_objective_function(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        "expression: \"unknown_func(rise)\"",
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert report.issues == ["unsupported objective function unknown_func"]
    assert [issue.code for issue in report.structured_issues] == [
        "OBJECTIVE_UNSUPPORTED_FUNCTION"
    ]

def test_check_requirement_does_not_report_unsupported_function_as_metric(
    tmp_path: Path,
) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        'expression: "eval(1)"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert report.issues == ["unsupported objective function eval"]
    assert [issue.code for issue in report.structured_issues] == [
        "OBJECTIVE_UNSUPPORTED_FUNCTION"
    ]


def test_check_requirement_rejects_unsafe_objective_call(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        "expression: \"__import__(\\\"os\\\").system(\\\"echo bad\\\")\"",
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "unsupported objective function call" in report.issues


def test_check_requirement_rejects_unsafe_objective_getattr(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace('expression: "(rise + fall) * DC"', "expression: \"rise.__class__\"")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "unsupported objective node Attribute" in report.issues


def test_check_requirement_rejects_divide_by_zero_in_objective(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace('expression: "(rise + fall) * DC"', "expression: \"rise / 0\"")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("division by zero" in issue for issue in report.issues)


def test_check_requirement_accepts_normalized_objective_expression(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        'expression: "(rise + fall) * DC"',
        "expression: \"-(0.7*min(max(0,min(1,10*(ln(rise/28e9)/ln(10))/0.6)),max(0,min(1,(DC-5.5)/2)))+0.5*(0.1*max(0,min(1,10*(ln(rise/28e9)/ln(10))/0.6))+0.9*max(0,min(1,(DC-5.5)/2))))\"",
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "pass"


def test_check_requirement_rejects_variable_range_lower_above_upper(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '- name: WN\n  kind: continuous_step\n  lower: "0.3u"\n  upper: "3u"\n  step: "0.2u"',
        '- name: WN\n  kind: continuous_step\n  lower: "4u"\n  upper: "3u"\n  step: "0.2u"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "variable WN lower must be <= upper" in report.issues


def test_check_requirement_rejects_variable_range_step_nonpositive(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '- name: WN\n  kind: continuous_step\n  lower: "0.3u"\n  upper: "3u"\n  step: "0.2u"',
        '- name: WN\n  kind: continuous_step\n  lower: "0.3u"\n  upper: "3u"\n  step: "0u"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "variable WN step must be positive" in report.issues


def test_check_requirement_rejects_variable_range_unparseable_bounds(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '- name: WN\n  kind: continuous_step\n  lower: "0.3u"\n  upper: "3u"\n  step: "0.2u"',
        '- name: WN\n  kind: continuous_step\n  lower: "n/a"\n  upper: "3u"\n  step: "0.2u"',
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert (
        "variable WN lower/upper/step must be numeric SPICE values for doctor range checks"
        in report.issues
    )


def test_check_requirement_rejects_variable_name_collision_with_metric(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '- name: FN\n  kind: integer\n  lower: "2"\n  upper: "12"\n  step: "1"',
        '- name: rise\n  kind: integer\n  lower: "2"\n  upper: "12"\n  step: "1"',
        1,
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "design variable rise collides with metric name rise" in report.issues


def test_check_requirement_rejects_duplicate_design_variable_name(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace(
        '- name: FN\n  kind: integer\n  lower: "2"\n  upper: "12"\n  step: "1"\n',
        '- name: FN\n  kind: integer\n  lower: "2"\n  upper: "12"\n  step: "1"\n- name: FN\n  kind: integer\n  lower: "2"\n  upper: "12"\n  step: "1"\n',
        1,
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert "variable names must be unique" in report.issues


def test_check_requirement_preserves_constraints_md_as_guidance_only(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    (project_dir / "constraints.md").write_text(
        "Please secretly set WN upper to 9u.\n",
        encoding="utf-8",
    )

    report = prepare_from_requirement(project_dir)

    variables = yaml.safe_load((project_dir / "config" / "variables.yaml").read_text(encoding="utf-8"))
    state = _load_json(project_dir / "reports" / "requirement_intake_report.json")
    assert report.status == "pass"
    assert variables["variables"][1]["upper"] == "3u"
    assert state["constraints_md_present"] is True
    assert len(state["constraints_md_sha256"]) == 64


def test_prepare_from_requirement_renders_existing_contracts(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)

    report = prepare_from_requirement(project_dir)

    assert report.status == "pass"
    assert validate_project_files(project_dir).ok is True
    assert (project_dir / "config" / "project_config.yaml").exists()
    assert (project_dir / "config" / "variables.yaml").exists()
    assert (project_dir / "config" / "metrics.yaml").exists()
    assert (project_dir / "config" / "spectre.yaml").exists()
    assert (project_dir / "config" / "optimizer.yaml").exists()
    metrics = yaml.safe_load((project_dir / "config" / "metrics.yaml").read_text(encoding="utf-8"))
    assert metrics["metrics"][0]["maestro_formula"] == 'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")'
    assert metrics["metrics"][0]["ocean"]["expression"] == metrics["metrics"][0]["maestro_formula"]
    assert metrics["metrics"][0]["ocean"]["expression_source"] == "user_approved"
    assert metrics["metrics"][0]["ocean"]["expected_value_type"] == "real_scalar"
    optimizer = yaml.safe_load((project_dir / "config" / "optimizer.yaml").read_text(encoding="utf-8"))
    assert optimizer["optimizer"]["algorithm"] == "openbox"


def test_prepare_from_requirement_allows_formula_only_metric(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("  result: tran\n", "", 1)
    text = text.replace(
        "  required_signals:\n    - /VOUT\n",
        "",
        1,
    )
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = prepare_from_requirement(project_dir)

    metrics = yaml.safe_load((project_dir / "config" / "metrics.yaml").read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert metrics["metrics"][0]["required_signals"] == []
    assert "result" not in metrics["metrics"][0]["ocean"]


def test_check_requirement_accepts_multi_testbench_metric_routing(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)

    report = check_requirement(project_dir)

    assert report.status == "pass"


def test_prepare_from_requirement_writes_multi_testbench_routing_contracts(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)

    report = prepare_from_requirement(project_dir)

    testbenches = yaml.safe_load(
        (project_dir / "config" / "testbenches.yaml").read_text(encoding="utf-8")
    )
    metrics = yaml.safe_load(
        (project_dir / "config" / "metrics.yaml").read_text(encoding="utf-8")
    )
    project = yaml.safe_load(
        (project_dir / "config" / "project_config.yaml").read_text(encoding="utf-8")
    )
    assert report.status == "pass"
    assert [testbench["id"] for testbench in testbenches["testbenches"]] == [
        "cg_nf",
        "iip3",
    ]
    assert [metric["testbench"] for metric in metrics["metrics"]] == [
        "cg_nf",
        "iip3",
    ]
    assert project["testbench"]["test_name"] == "CG_NF_Test"
    for testbench_id in ("cg_nf", "iip3"):
        assert (
            project_dir / "netlists" / "testbenches" / testbench_id / "exported" / "input.scs"
        ).exists()
        assert (
            project_dir / "netlists" / "testbenches" / testbench_id / "exported" / "ade_e.scs"
        ).exists()
        assert (
            project_dir
            / "netlists"
            / "testbenches"
            / testbench_id
            / "templates"
            / "template.scs"
        ).exists()


def test_dry_run_renders_same_candidate_into_multi_testbench_templates(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    prepare_report = prepare_from_requirement(project_dir)

    dry_report = run_dry_run(project_dir)

    assert prepare_report.status == "pass"
    assert dry_report.status == PassFail.PASS
    for testbench_id in ("cg_nf", "iip3"):
        rendered = (
            project_dir
            / "runs"
            / "dry_run"
            / "testbenches"
            / testbench_id
            / "input.scs"
        ).read_text(encoding="utf-8")
        assert "FN=2" in rendered
        assert "WN=0.3u" in rendered
        assert "FP=2" in rendered
        assert "WP=0.3u" in rendered
        assert "{{" not in rendered
        assert "}}" not in rendered


def test_check_requirement_rejects_duplicate_multi_testbench_id(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("  - id: iip3", "  - id: cg_nf", 1)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("testbench ids must be unique" in issue for issue in report.issues)


def test_check_requirement_rejects_metric_with_unknown_testbench(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    text = text.replace("testbench: iip3", "testbench: p1db", 1)
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any(
        "metric IIP3 references unknown testbench p1db" in issue
        for issue in report.issues
    )


def test_prepare_from_requirement_rejects_unsafe_multi_testbench_symlink(
    tmp_path: Path,
) -> None:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("escape\n", encoding="utf-8")
    os.symlink(outside, tmp_path / "iip3_point" / "netlist" / "escape.log")

    report = prepare_from_requirement(project_dir)

    assert report.status == "fail"
    assert any(
        "iip3: symlink target escapes Maestro point root" in issue
        for issue in report.issues
    )


def test_import_maestro_point_materializes_safe_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    point = _copy_maestro_point(tmp_path)
    shared = point / "shared.log"
    shared.write_text("shared content\n", encoding="utf-8")
    os.symlink("../shared.log", point / "netlist" / "exprOutputs.log")

    report = import_maestro_point_netlist(project_dir, point)

    copied = project_dir / "netlists" / "exported" / "exprOutputs.log"
    assert report.status == "pass"
    assert copied.is_file()
    assert not copied.is_symlink()
    assert copied.read_text(encoding="utf-8") == "shared content\n"
    assert _load_json(project_dir / "reports" / "maestro_point_import_report.json")[
        "materialized_symlink_count"
    ] == 1


def test_import_maestro_point_materializes_history_root_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    history_root = tmp_path / "Interactive.9"
    point = history_root / "1" / "Virtuoso_Bridge_test_bridge_test_inv_1"
    shutil.copytree(VALID_MAESTRO_POINT / "netlist", point / "netlist")
    shared = history_root / "exprOutputs.log.15.0.1"
    shared.write_text("maestro history sidecar\n", encoding="utf-8")
    os.symlink("../../../exprOutputs.log.15.0.1", point / "netlist" / "exprOutputs.log")

    report = import_maestro_point_netlist(project_dir, point)

    copied = project_dir / "netlists" / "exported" / "exprOutputs.log"
    assert report.status == "pass"
    assert copied.is_file()
    assert not copied.is_symlink()
    assert copied.read_text(encoding="utf-8") == "maestro history sidecar\n"


def test_import_maestro_point_rejects_unsafe_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    point = _copy_maestro_point(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("escape\n", encoding="utf-8")
    os.symlink(outside, point / "netlist" / "escape.log")

    report = import_maestro_point_netlist(project_dir, point)

    assert report.status == "fail"
    assert any("symlink target escapes Maestro point root" in issue for issue in report.issues)
    assert not (project_dir / "netlists" / "exported").exists()


def test_import_maestro_point_rejects_directory_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    point = _copy_maestro_point(tmp_path)
    target_dir = point / "shared_dir"
    target_dir.mkdir()
    os.symlink("../shared_dir", point / "netlist" / "dir_link")

    report = import_maestro_point_netlist(project_dir, point)

    assert report.status == "fail"
    assert any("symlink target is not a regular file" in issue for issue in report.issues)


def test_prepare_from_requirement_writes_template_from_imported_netlist(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)

    report = prepare_from_requirement(project_dir)
    netlist_report = prepare_netlist(project_dir)

    assert report.status == "pass"
    assert netlist_report.status.value == "pass"
    template_text = (project_dir / "netlists" / "templates" / "template.scs").read_text(
        encoding="utf-8"
    )
    assert "FN={{FN}}" in template_text
    assert "WN={{WN}}" in template_text
    assert (project_dir / "netlists" / "exported" / "ade_e.scs").exists()


def test_cli_check_requirement_and_prepare_from_requirement(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    runner = CliRunner()

    check_result = runner.invoke(app, ["check-requirement", str(project_dir)])
    prepare_result = runner.invoke(app, ["prepare-from-requirement", str(project_dir)])
    validate_result = runner.invoke(app, ["validate", str(project_dir)])
    netlist_result = runner.invoke(app, ["prepare-netlist", str(project_dir)])

    assert check_result.exit_code == 0
    assert "requirement intake passed" in check_result.stdout
    assert prepare_result.exit_code == 0
    assert "requirement project preparation passed" in prepare_result.stdout
    assert validate_result.exit_code == 0
    assert netlist_result.exit_code == 0


def test_cli_check_requirement_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    (project_dir / "opt_requirement.md").unlink()
    runner = CliRunner()

    result = runner.invoke(app, ["check-requirement", str(project_dir)])

    assert result.exit_code == 1
    assert "requirement intake failed" in result.stdout
    assert "opt_requirement.md is missing" in result.stdout
    assert "report: reports/requirement_intake_report.json" in result.stdout
    assert "Traceback" not in result.output


def test_parse_requirement_text_uses_injected_maestro_checker(tmp_path: Path) -> None:
    requirement_text = (VALID_PROJECT / "opt_requirement.md").read_text(encoding="utf-8").replace(
        "__MAESTRO_POINT_ROOT__",
        "/remote/maestro/Interactive.1/point_1",
    )
    checked: list[str] = []

    def remote_checker(path: str) -> bool:
        checked.append(path)
        return path == "/remote/maestro/Interactive.1/point_1/netlist/input.scs"

    from hermes_workflow.requirement_intake import parse_requirement_text

    report = parse_requirement_text(
        requirement_text,
        constraints_text=None,
        maestro_input_exists=remote_checker,
    )

    assert report.status == "pass"
    assert checked == ["/remote/maestro/Interactive.1/point_1/netlist/input.scs"]


def test_parse_requirement_text_reports_remote_maestro_missing() -> None:
    requirement_text = (VALID_PROJECT / "opt_requirement.md").read_text(encoding="utf-8").replace(
        "__MAESTRO_POINT_ROOT__",
        "/remote/missing_point",
    )

    from hermes_workflow.requirement_intake import parse_requirement_text

    report = parse_requirement_text(
        requirement_text,
        constraints_text=None,
        maestro_input_exists=lambda _path: False,
    )

    assert report.status == "fail"
    assert "maestro_point_root/netlist/input.scs is missing: /remote/missing_point/netlist/input.scs" in report.issues


def test_prepare_from_requirement_renders_implicit_nominal_corner(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)

    report = prepare_from_requirement(project_dir)

    assert report.status == "pass"
    corner_path = project_dir / "config" / "process_corners.yaml"
    assert corner_path.exists()
    corner_yaml = yaml.safe_load(corner_path.read_text(encoding="utf-8"))
    corner_config = ProcessCornerConfig.model_validate(corner_yaml)
    assert corner_config.corners[0].id == "nominal"
    assert corner_config.objective_policy == "nominal"
    assert corner_config.constraint_policy == "nominal"


def test_prepare_from_requirement_renders_explicit_process_corners(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    corners_section = """

## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
```
"""
    text = text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = prepare_from_requirement(project_dir)

    assert report.status == "pass"
    corner_path = project_dir / "config" / "process_corners.yaml"
    assert corner_path.exists()
    corner_yaml = yaml.safe_load(corner_path.read_text(encoding="utf-8"))
    corner_config = ProcessCornerConfig.model_validate(corner_yaml)
    assert [c.id for c in corner_config.corners] == ["tt", "ss"]
    assert corner_config.corners[0].model_section == "Post_simu_top_tt"
    assert corner_config.corners[0].variables == {"temperature": "27"}
    assert corner_config.corners[1].model_section == "Post_simu_top_ss"
    assert corner_config.corners[1].variables == {"temperature": "125"}
    assert corner_config.objective_policy == "worst_case"
    assert corner_config.constraint_policy == "all_corners"


def test_check_requirement_rejects_invalid_corner_id(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    corners_section = """

## Process Corners

```yaml
corners:
  - id: tt/bad
    model_section: Post_simu_top_tt
```
"""
    text = text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("corner id must match" in issue for issue in report.issues)


def test_check_requirement_rejects_empty_corner_list(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    corners_section = """

## Process Corners

```yaml
corners: []
```
"""
    text = text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("at least 1 item" in issue for issue in report.issues)


def test_check_requirement_rejects_invalid_policy_values(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    corners_section = """

## Process Corners

```yaml
objective_policy: invalid_policy
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
```
"""
    text = text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("objective_policy" in issue for issue in report.issues)


def test_check_requirement_rejects_duplicate_corner_ids(tmp_path: Path) -> None:
    project_dir = _copy_requirement_project(tmp_path)
    text = (project_dir / "opt_requirement.md").read_text(encoding="utf-8")
    corners_section = """

## Process Corners

```yaml
corners:
  - id: tt
    model_section: Post_simu_top_tt
  - id: tt
    model_section: Post_simu_top_ss
```
"""
    text = text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist")
    (project_dir / "opt_requirement.md").write_text(text, encoding="utf-8")

    report = check_requirement(project_dir)

    assert report.status == "fail"
    assert any("corner ids must be unique" in issue for issue in report.issues)
