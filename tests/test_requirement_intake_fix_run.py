"""Tests for fix-run workflow awareness in requirement intake.

TDD RED phase: these tests define the required behavior before
the implementation exists.
"""
from __future__ import annotations

import pytest

from hermes_workflow.requirement_intake import (
    parse_requirement_text,
    render_config_payloads,
)

FIX_RUN_REQUIREMENT = """\
## Workflow
```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

## Project
```yaml
project_name: test_fix_run
backend: maestro_exported_spectre_deck
```

## Maestro Source
```yaml
maestro_point_root: /path/to/maestro/point
virtuoso_library: my_lib
cell: my_cell
design_view: schematic
maestro_view: maestro
test_name: test_dc
corner: tt
```

## Design Variables
```yaml
- name: w_m1
  kind: continuous_step
  lower: "1u"
  upper: "20u"
  step: "1u"
- name: cap_sw
  kind: continuous_step
  lower: "0.1p"
  upper: "10p"
  step: "0.1p"
```

## Spectre Settings
```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 4
parallel_jobs: 1
timeout_s: 3600
require_license_check: false
keep_failed_runs: false
keep_successful_runs: true
```

## Fixed Points
```yaml
schema_version: "1.0"
points:
  - candidate_id: user_point_001
    parameters:
      w_m1: "8u"
      cap_sw: "1.2p"
```

## Waveform Exports
```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

## Approval Checklist
```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
"""

FIX_RUN_METRICS_SECTION = """\
## Metrics
```yaml
- name: gain
  unit: dB
  ocean_expression: value(getData("gain" ?result "pac") 3e9)
```

"""

FIX_RUN_WAVEFORM_SECTION = """\
## Waveform Exports
```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

"""


def test_fix_run_rejects_inert_corner_aggregation_policies() -> None:
    process_corners = """\
## Process Corners
```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
```

"""
    text = FIX_RUN_REQUIREMENT.replace(
        "## Approval Checklist\n",
        process_corners + "## Approval Checklist\n",
    )

    report = parse_requirement_text(text, maestro_input_exists=lambda _path: True)

    assert report.status == "fail"
    assert any(
        "aggregation policies are not supported for fix_run" in issue
        for issue in report.issues
    )

# A minimal optimizer requirement with no Workflow section
OPTIMIZER_REQUIREMENT_NO_WORKFLOW = """\
## Project
```yaml
project_name: test_opt
backend: maestro_exported_spectre_deck
```

## Maestro Source
```yaml
maestro_point_root: /path/to/maestro/point
virtuoso_library: my_lib
cell: my_cell
design_view: schematic
maestro_view: maestro
test_name: test_dc
corner: tt
```

## Design Variables
```yaml
- name: w_m1
  kind: continuous_step
  lower: "1u"
  upper: "20u"
  step: "1u"
- name: cap_sw
  kind: continuous_step
  lower: "0.1p"
  upper: "10p"
  step: "0.1p"
```

## Metrics
```yaml
- name: gain
  unit: dB
  ocean_expression: value(getData("gain" ?result "pac") 3e9)
```

## Constraints
```yaml
- metric: gain
  op: gt
  value: "5 dB"
```

## Objective
```yaml
direction: maximize
expression: gain
```

## Spectre Settings
```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 4
parallel_jobs: 1
timeout_s: 3600
require_license_check: false
keep_failed_runs: false
keep_successful_runs: true
```

## Optimizer Settings
```yaml
algorithm: openbox
initialization: sobol
max_evaluations: 100
batch_size: 1
random_seed: 20260528
failure_penalty: 1000000.0
deduplicate_candidates: true
```

## Approval Checklist
```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
"""

# Optimizer requirement with explicit Workflow.mode: optimize
OPTIMIZER_REQUIREMENT_WITH_WORKFLOW = """\
## Workflow
```yaml
schema_version: "1.0"
mode: optimize
```

## Project
```yaml
project_name: test_opt
backend: maestro_exported_spectre_deck
```

## Maestro Source
```yaml
maestro_point_root: /path/to/maestro/point
virtuoso_library: my_lib
cell: my_cell
design_view: schematic
maestro_view: maestro
test_name: test_dc
corner: tt
```

## Design Variables
```yaml
- name: w_m1
  kind: continuous_step
  lower: "1u"
  upper: "20u"
  step: "1u"
- name: cap_sw
  kind: continuous_step
  lower: "0.1p"
  upper: "10p"
  step: "0.1p"
```

## Metrics
```yaml
- name: gain
  unit: dB
  ocean_expression: value(getData("gain" ?result "pac") 3e9)
```

## Constraints
```yaml
- metric: gain
  op: gt
  value: "5 dB"
```

## Objective
```yaml
direction: maximize
expression: gain
```

## Spectre Settings
```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 4
parallel_jobs: 1
timeout_s: 3600
require_license_check: false
keep_failed_runs: false
keep_successful_runs: true
```

## Optimizer Settings
```yaml
algorithm: openbox
initialization: sobol
max_evaluations: 100
batch_size: 1
random_seed: 20260528
failure_penalty: 1000000.0
deduplicate_candidates: true
```

## Approval Checklist
```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
"""


def _parse_fix_run(text: str | None = None, **kwargs) -> object:
    """Helper to parse a fix-run requirement with the maestro checker mocked."""
    requirement_text = text if text is not None else FIX_RUN_REQUIREMENT
    return parse_requirement_text(
        requirement_text,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
        **kwargs,
    )


# --- Test 1: Valid fix_run requirement passes without Optimizer Settings / Objective / Constraints ---
def test_fix_run_requirement_without_optimizer_sections_passes() -> None:
    report = _parse_fix_run()
    assert report.status == "pass", report.issues


def test_single_testbench_fix_run_rejects_ignored_waveform_route() -> None:
    text = FIX_RUN_REQUIREMENT.replace(
        "  - name: nf_pnoise\n",
        "  - name: nf_pnoise\n    testbench: ignored_route\n",
        1,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any(
        "waveform export nf_pnoise must not declare testbench for a "
        "single-testbench project" in issue
        for issue in report.issues
    )


@pytest.mark.parametrize("route", [None, "typo"])
def test_multi_testbench_fix_run_requires_valid_waveform_route(
    route: str | None,
) -> None:
    single_source = """\
maestro_point_root: /path/to/maestro/point
virtuoso_library: my_lib
cell: my_cell
design_view: schematic
maestro_view: maestro
test_name: test_dc
corner: tt
"""
    multi_source = """\
testbenches:
  - id: cg_nf
    maestro_point_root: /path/to/maestro/cg_nf
    virtuoso_library: my_lib
    cell: my_cell
    design_view: schematic
    maestro_view: maestro
    test_name: cg_nf
    corner: tt
  - id: iip3
    maestro_point_root: /path/to/maestro/iip3
    virtuoso_library: my_lib
    cell: my_cell
    design_view: schematic
    maestro_view: maestro
    test_name: iip3
    corner: tt
"""
    text = FIX_RUN_REQUIREMENT.replace(single_source, multi_source, 1)
    if route is not None:
        text = text.replace(
            "  - name: nf_pnoise\n",
            f"  - name: nf_pnoise\n    testbench: {route}\n",
            1,
        )

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any(
        "waveform export nf_pnoise must declare testbench" in issue
        or "waveform export nf_pnoise references unknown testbench typo" in issue
        for issue in report.issues
    )

def test_fix_run_rejects_fixed_point_outside_approved_bounds() -> None:
    text = FIX_RUN_REQUIREMENT.replace('w_m1: "8u"', 'w_m1: "99u"', 1)

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any(
        "Fixed Points point 'user_point_001': w_m1 is outside approved bounds"
        in issue
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "    expression: 'getData(\"NF\" ?result \"pnoise\")'",
            "    expression: ''",
            "String should have at least 1 character",
        ),
        (
            "    nil_policy: fail",
            "    nil_policy: skip",
            "Input should be 'fail'",
        ),
    ],
)
def test_fix_run_rejects_waveform_contract_that_runtime_cannot_honor(
    old: str,
    new: str,
    expected: str,
) -> None:
    report = _parse_fix_run(text=FIX_RUN_REQUIREMENT.replace(old, new, 1))

    assert report.status == "fail"
    assert any(expected in issue for issue in report.issues)


def test_fix_run_rejects_duplicate_waveform_export_names() -> None:
    duplicate = """\
  - name: nf_pnoise
    expression: 'getData("NF2" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
"""
    text = FIX_RUN_REQUIREMENT.replace(
        "    nil_policy: fail\n```\n\n## Approval Checklist",
        "    nil_policy: fail\n" + duplicate + "```\n\n## Approval Checklist",
        1,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any("waveform export names must be unique" in issue for issue in report.issues)


def test_fix_run_rejects_duplicate_fixed_point_candidate_ids() -> None:
    duplicate = """\
  - candidate_id: user_point_001
    parameters:
      w_m1: "9u"
      cap_sw: "1.3p"
"""
    text = FIX_RUN_REQUIREMENT.replace(
        '      cap_sw: "1.2p"\n```',
        '      cap_sw: "1.2p"\n' + duplicate + "```",
        1,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any("candidate_id values must be unique" in issue for issue in report.issues)


def test_fix_run_rejects_run_id_range_overflow() -> None:
    second_point = """\
  - candidate_id: user_point_002
    parameters:
      w_m1: "9u"
      cap_sw: "1.3p"
"""
    text = FIX_RUN_REQUIREMENT.replace("real_001", "real_999", 1).replace(
        '      cap_sw: "1.2p"\n```',
        '      cap_sw: "1.2p"\n' + second_point + "```",
        1,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert any("would exceed real_999" in issue for issue in report.issues)


# --- Test 2: Valid optimizer requirement with no Workflow section still passes ---
def test_optimizer_requirement_without_workflow_section_passes() -> None:
    report = parse_requirement_text(
        OPTIMIZER_REQUIREMENT_NO_WORKFLOW,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.status == "pass", report.issues


# --- Test 3: Optimizer with Workflow.mode: optimize still requires Optimizer Settings ---
def test_optimizer_with_explicit_workflow_mode_still_requires_optimizer_settings() -> None:
    # Remove Optimizer Settings section
    text = OPTIMIZER_REQUIREMENT_WITH_WORKFLOW.replace("## Optimizer Settings\n", "")
    # Also remove the yaml block that follows
    lines = text.splitlines(keepends=True)
    result_lines = []
    skip = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Optimizer Settings":
            skip = True
            i += 1
            continue
        if skip and line.strip().startswith("```"):
            # We're in the yaml block of the removed section
            if "```yaml" in line or "```" in line:
                # Skip the yaml block entirely
                if "```yaml" in line:
                    i += 1
                    while i < len(lines) and lines[i].strip() != "```":
                        i += 1
                    i += 1  # skip closing ```
                    skip = False
                    continue
                else:
                    skip = False
                    i += 1
                    continue
        result_lines.append(line)
        i += 1

    text = "".join(result_lines)

    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.status == "fail"
    assert any("Optimizer Settings" in issue for issue in report.issues)


def test_requirement_rejects_unknown_workflow_mode_before_mode_dispatch() -> None:
    text = OPTIMIZER_REQUIREMENT_WITH_WORKFLOW.replace(
        "mode: optimize",
        "mode: characterize",
        1,
    )

    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda _path: True,
    )

    assert report.status == "fail"
    assert any("Workflow.mode" in issue for issue in report.issues)


def test_render_config_payloads_rejects_unknown_workflow_mode() -> None:
    with pytest.raises(ValueError, match="unsupported workflow_mode"):
        render_config_payloads({}, workflow_mode="typo")


def test_optimize_workflow_rejects_unused_starting_run_id() -> None:
    text = OPTIMIZER_REQUIREMENT_WITH_WORKFLOW.replace(
        "mode: optimize",
        "mode: optimize\nstarting_run_id: real_007",
        1,
    )

    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda _path: True,
    )

    assert report.status == "fail"
    assert any(
        "Workflow.starting_run_id is not supported for optimize workflow mode"
        in issue
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("section_name", "payload"),
    [
        (
            "Fixed Points",
            "schema_version: '1.0'\npoints:\n  - candidate_id: p1\n"
            "    parameters: {w_m1: 8u, cap_sw: 1p}",
        ),
        (
            "Waveform Exports",
            "schema_version: '1.0'\nexports:\n  - name: gain_wave\n"
            "    testbench: test_dc\n    expression: getData(\"gain\")\n"
            "    output_format: csv\n    nil_policy: fail",
        ),
    ],
)
def test_optimize_workflow_rejects_fix_run_only_sections(
    section_name: str,
    payload: str,
) -> None:
    text = (
        OPTIMIZER_REQUIREMENT_WITH_WORKFLOW
        + f"\n## {section_name}\n```yaml\n{payload}\n```\n"
    )

    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda _path: True,
    )

    assert report.status == "fail"
    assert (
        f"section {section_name} is not supported for workflow mode optimize"
        in report.issues
    )


def test_requirement_rejects_unknown_section_heading() -> None:
    text = (
        OPTIMIZER_REQUIREMENT_WITH_WORKFLOW
        + "\n## Objective Polciy\n```yaml\npolicy: nominal\n```\n"
    )

    report = parse_requirement_text(
        text,
        constraints_text=None,
        maestro_input_exists=lambda _path: True,
    )

    assert report.status == "fail"
    assert "unknown requirement section: Objective Polciy" in report.issues


@pytest.mark.parametrize("section_name", ["Objective", "Constraints"])
def test_fix_run_rejects_optimizer_semantics_without_a_runtime_consumer(
    section_name: str,
) -> None:
    payload = (
        "direction: minimize\nexpression: gain"
        if section_name == "Objective"
        else "- metric: gain\n  op: lt\n  value: '1 dB'"
    )
    text = FIX_RUN_REQUIREMENT + f"\n## {section_name}\n```yaml\n{payload}\n```\n"

    report = _parse_fix_run(text=text)

    assert report.status == "fail"
    assert (
        f"section {section_name} is not supported for workflow mode fix_run"
        in report.issues
    )


# --- Test 4: fix_run without Fixed Points section fails ---
def test_fix_run_without_fixed_points_section_fails() -> None:
    text = FIX_RUN_REQUIREMENT.replace("## Fixed Points\n", "")
    # Remove the Fixed Points yaml block
    lines = text.splitlines(keepends=True)
    result_lines = []
    skip = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Fixed Points":
            skip = True
            i += 1
            continue
        if skip:
            if line.strip() == "```yaml":
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    i += 1
                i += 1  # skip closing ```
                skip = False
                continue
            elif line.strip() == "":
                i += 1
                continue
            else:
                skip = False
        if not skip:
            result_lines.append(line)
        i += 1

    text = "".join(result_lines)
    report = _parse_fix_run(text=text)
    assert report.status == "fail"
    assert any("Fixed Points" in issue for issue in report.issues)


# --- Test 5: fix_run without both Metrics and Waveform Exports fails ---
def test_fix_run_without_metrics_and_waveform_exports_fails() -> None:
    # Remove both Metrics and Waveform Exports sections
    text = FIX_RUN_REQUIREMENT
    # Remove Waveform Exports section
    lines = text.splitlines(keepends=True)
    result_lines = []
    skip = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Waveform Exports":
            skip = True
            i += 1
            continue
        if skip:
            if line.strip() == "```yaml":
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    i += 1
                i += 1
                skip = False
                continue
            elif line.strip() == "":
                i += 1
                continue
            else:
                skip = False
        if not skip:
            result_lines.append(line)
        i += 1

    text = "".join(result_lines)
    report = _parse_fix_run(text=text)
    assert report.status == "fail"
    assert any(
        "Metrics" in issue and "Waveform Exports" in issue
        for issue in report.issues
    )


# --- Test 6: fix_run with unknown fixed-point parameter names fails ---
def test_fix_run_with_unknown_fixed_point_parameter_fails() -> None:
    # Replace a known parameter with an unknown one in Fixed Points
    text = FIX_RUN_REQUIREMENT.replace(
        "      w_m1: \"8u\"",
        "      unknown_param: \"8u\"",
    )
    report = _parse_fix_run(text=text)
    assert report.status == "fail"
    assert any("unknown_param" in issue for issue in report.issues)


# --- Test 7: fix_run with missing required design variable in fixed-point parameters fails ---
def test_fix_run_with_missing_design_variable_in_fixed_points_fails() -> None:
    # Remove cap_sw from the fixed point parameters (it's a declared design variable)
    text = FIX_RUN_REQUIREMENT.replace("      cap_sw: \"1.2p\"\n", "")
    report = _parse_fix_run(text=text)
    assert report.status == "fail"
    assert any("cap_sw" in issue for issue in report.issues)


# --- Test 8: Wrong pnoise expression text is NOT rewritten by intake ---
def test_fix_run_preserves_pnoise_expression_verbatim() -> None:
    report = _parse_fix_run()
    assert report.status == "pass", report.issues
    # The expression in Waveform Exports should be preserved exactly
    waveform_exports = report.sections.get("Waveform Exports", {})
    exports = waveform_exports.get("exports", [])
    assert len(exports) >= 1
    assert exports[0]["expression"] == 'getData("NF" ?result "pnoise")'


# --- Test 9: fix_run mode produces config/fixed_points.yaml and config/waveform_exports.yaml ---
def test_fix_run_produces_fixed_points_and_waveform_exports_yaml() -> None:
    report = _parse_fix_run()
    assert report.status == "pass", report.issues

    payloads = render_config_payloads(report.sections, workflow_mode=report.workflow_mode)

    assert "fixed_points.yaml" in payloads
    assert "waveform_exports.yaml" in payloads

    fixed_points = payloads["fixed_points.yaml"]
    assert fixed_points["schema_version"] == "1.0"
    assert len(fixed_points["points"]) >= 1
    assert fixed_points["points"][0]["candidate_id"] == "user_point_001"

    waveform_exports = payloads["waveform_exports.yaml"]
    assert waveform_exports["schema_version"] == "1.0"
    assert len(waveform_exports["exports"]) >= 1
    assert "metrics.yaml" not in payloads


def test_fix_run_metrics_only_produces_metrics_yaml() -> None:
    text = FIX_RUN_REQUIREMENT.replace(
        FIX_RUN_WAVEFORM_SECTION,
        FIX_RUN_METRICS_SECTION,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "pass", report.issues
    assert report.sections["Metrics"][0]["name"] == "gain"
    payloads = render_config_payloads(
        report.sections,
        workflow_mode=report.workflow_mode,
    )
    assert payloads["metrics.yaml"]["metrics"][0]["name"] == "gain"
    assert "waveform_exports.yaml" not in payloads


def test_fix_run_metrics_and_waveforms_produce_both_configs() -> None:
    text = FIX_RUN_REQUIREMENT.replace(
        FIX_RUN_WAVEFORM_SECTION,
        FIX_RUN_METRICS_SECTION + FIX_RUN_WAVEFORM_SECTION,
    )

    report = _parse_fix_run(text=text)

    assert report.status == "pass", report.issues
    payloads = render_config_payloads(
        report.sections,
        workflow_mode=report.workflow_mode,
    )
    assert payloads["metrics.yaml"]["metrics"][0]["name"] == "gain"
    assert payloads["waveform_exports.yaml"]["exports"][0]["name"] == "nf_pnoise"


# --- Test 10: fix_run mode does NOT produce config/optimizer.yaml ---
def test_fix_run_does_not_produce_optimizer_yaml() -> None:
    report = _parse_fix_run()
    assert report.status == "pass", report.issues

    payloads = render_config_payloads(report.sections, workflow_mode=report.workflow_mode)

    assert "optimizer.yaml" not in payloads


# --- Test 11: RequirementIntakeReport.workflow_mode is "fix_run" for fix-run requirements ---
def test_workflow_mode_is_fix_run_for_fix_run_requirement() -> None:
    report = _parse_fix_run()
    assert report.workflow_mode == "fix_run"


# --- Test 12: RequirementIntakeReport.workflow_mode is "optimize" when Workflow section is absent ---
def test_workflow_mode_is_optimize_when_workflow_section_absent() -> None:
    report = parse_requirement_text(
        OPTIMIZER_REQUIREMENT_NO_WORKFLOW,
        constraints_text=None,
        maestro_input_exists=lambda path: True,
    )
    assert report.workflow_mode == "optimize"
