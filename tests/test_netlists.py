import json
from pathlib import Path

import pytest
import yaml

from hermes_workflow.netlists import (
    prepare_netlist,
    render_corner_netlist_template,
)
from hermes_workflow.package import create_project_from_template
from hermes_workflow.reports import NetlistPreparationReport, PassFail
from hermes_workflow.schemas import ProcessCorner, ProcessCornerConfig


def _project_with_input(tmp_path: Path, deck_text: str) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    input_path = project_dir / "netlists" / "exported" / "input.scs"
    input_path.write_text(deck_text, encoding="utf-8")
    return project_dir


def _load_netlist_report(project_dir: Path) -> NetlistPreparationReport:
    payload = json.loads(
        (project_dir / "reports" / "netlist_preparation_report.json").read_text(
            encoding="utf-8"
        )
    )
    return NetlistPreparationReport.model_validate(payload)


def test_prepare_netlist_templates_single_line_parameter_values(tmp_path: Path) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
M0 (VOUT IN VSS VSS) nmos w=WN*FN l=45n
tran tran stop=10n
dcOp dc oppoint=rawfile
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    persisted_report = _load_netlist_report(project_dir)

    assert report.status == PassFail.PASS
    assert persisted_report == report
    assert "FN={{FN}}" in template_text
    assert "FP={{FP}}" in template_text
    assert "WN={{WN}}" in template_text
    assert "WP={{WP}}" in template_text
    assert "temperature=27" in template_text
    assert "w=WN*FN" in template_text
    assert report.approved_variables_template_status == {
        "FN": True,
        "WN": True,
        "FP": True,
        "WP": True,
    }
    assert report.analysis_statements == ["tran", "dcOp"]
    assert report.forbidden_setup_changes_detected is False
    assert report.issues == []


def test_prepare_netlist_templates_backslash_continued_parameters(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters \\
    temperature=27 \\
    L2=45n FN=4 \\
    FP=4 WN=0.6u WP=1.2u
I0 (VOUT IN VSS VSS) inverter w=WP*FP fingers=FN
pss pss fund=1G harms=10
pac pac maxsideband=10
pnoise pnoise maxsideband=10
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert "FN={{FN}}" in template_text
    assert "FP={{FP}}" in template_text
    assert "WN={{WN}}" in template_text
    assert "WP={{WP}}" in template_text
    assert "L2=45n" in template_text
    assert "w=WP*FP fingers=FN" in template_text
    assert report.analysis_statements == ["pss", "pac", "pnoise"]


def test_prepare_netlist_does_not_template_instance_parameters(tmp_path: Path) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
subckt wrapped IN OUT VDD VSS
M0 (OUT IN VSS VSS) nmos w=WN*FN l=45n
ends wrapped
X0 (IN OUT VDD VSS) wrapped FN=99 WP=99u
ac ac start=1 stop=10G
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert "parameters temperature=27 FN={{FN}} FP={{FP}} WN={{WN}} WP={{WP}}" in template_text
    assert "X0 (IN OUT VDD VSS) wrapped FN=99 WP=99u" in template_text


def test_prepare_netlist_writes_fail_report_when_input_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert "exported input.scs is missing" in report.issues[0]
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()
    assert _load_netlist_report(project_dir) == report


def test_prepare_netlist_writes_fail_report_when_approved_variable_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert report.approved_variables_template_status["WP"] is False
    assert "approved variable WP was not found in top-level parameters" in report.issues
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def test_prepare_netlist_writes_fail_report_for_duplicate_approved_variable(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
parameters FN=5
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert "approved variable FN appears more than once in top-level parameters" in report.issues
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def test_prepare_netlist_templates_values_with_whitespace_units(tmp_path: Path) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6 u WP=1.2 u
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert "WN={{WN}}" in template_text
    assert "WP={{WP}}" in template_text
    assert "WN={{WN}} u" not in template_text
    assert "WP={{WP}} u" not in template_text


def test_prepare_netlist_fails_closed_for_subckt_parameter_assignments(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FP=4 WP=1.2u
subckt wrapped IN OUT VDD VSS
parameters FN=4 WN=0.6u
M0 (OUT IN VSS VSS) nmos w=WN*FN l=45n
ends wrapped
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert report.forbidden_setup_changes_detected is True
    assert "approved variable FN was found outside top-level parameters" in report.issues
    assert "approved variable WN was found outside top-level parameters" in report.issues
    assert "approved variable FN was not found in top-level parameters" in report.issues
    assert "approved variable WN was not found in top-level parameters" in report.issues
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def _project_with_testbench_input_and_corners(
    tmp_path: Path,
    deck_text: str,
    corner_config: ProcessCornerConfig | None,
) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    testbenches_yaml = """
schema_version: "1.0"
testbenches:
  - id: tb1
    maestro_point_root: /tmp/maestro_point
    virtuoso_library: TestLib
    cell: TestCell
    design_view: schematic
    maestro_view: maestro
    test_name: test1
    corner: Nominal
"""
    (project_dir / "config" / "testbenches.yaml").write_text(
        testbenches_yaml, encoding="utf-8"
    )
    metrics_text = (project_dir / "config" / "metrics.yaml").read_text(encoding="utf-8")
    metrics_text = metrics_text.replace(
        "    maestro_formula: riseTime",
        "    testbench: tb1\n    maestro_formula: riseTime",
    )
    metrics_text = metrics_text.replace(
        "    maestro_formula: fallTime",
        "    testbench: tb1\n    maestro_formula: fallTime",
    )
    metrics_text = metrics_text.replace(
        "    maestro_formula: VDC",
        "    testbench: tb1\n    maestro_formula: VDC",
    )
    (project_dir / "config" / "metrics.yaml").write_text(metrics_text, encoding="utf-8")
    input_path = project_dir / "netlists" / "testbenches" / "tb1" / "exported" / "input.scs"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(deck_text, encoding="utf-8")
    legacy_input = project_dir / "netlists" / "exported" / "input.scs"
    legacy_input.parent.mkdir(parents=True, exist_ok=True)
    legacy_input.write_text(deck_text, encoding="utf-8")
    if corner_config is not None:
        corner_path = project_dir / "config" / "process_corners.yaml"
        corner_path.write_text(
            yaml.safe_dump(corner_config.model_dump(mode="json")),
            encoding="utf-8",
        )
    return project_dir


def test_render_corner_netlist_template_generates_two_corners() -> None:
    source_text = """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 F=20 W=1.8u
tran tran stop=10n
"""
    corner_config = ProcessCornerConfig(
        schema_version="1.0",
        objective_policy="worst_case",
        constraint_policy="all_corners",
        corners=[
            ProcessCorner(id="tt", model_section="Post_simu_top_tt", variables={"temperature": "27"}),
            ProcessCorner(id="ss", model_section="Post_simu_top_ss", variables={"temperature": "125"}),
        ],
    )

    tt_text = render_corner_netlist_template(source_text, corner_config.corners[0], "tt")
    ss_text = render_corner_netlist_template(source_text, corner_config.corners[1], "tt")

    assert tt_text == source_text
    assert 'section=Post_simu_top_ss' in ss_text
    assert 'section=Post_simu_top_tt' not in ss_text
    assert 'temperature=125' in ss_text
    assert 'temperature=27' not in ss_text
    assert 'F=20' in ss_text
    assert 'W=1.8u' in ss_text
    assert 'tran tran stop=10n' in ss_text


def test_render_corner_netlist_template_safe_replacement() -> None:
    source_text = """simulator lang=spectre
// include "commented.scs" section=Post_simu_top_tt
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 F=20 W=1.8u
// OCEAN: section=Post_simu_top_tt should not be replaced
"""
    corner = ProcessCorner(id="ss", model_section="Post_simu_top_ss")

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert 'include "/path/to/toplevel.scs" section=Post_simu_top_ss' in result
    assert '// include "commented.scs" section=Post_simu_top_tt' in result
    assert '// OCEAN: section=Post_simu_top_tt should not be replaced' in result


def test_render_corner_netlist_template_updates_variables() -> None:
    source_text = """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 F=20 W=1.8u
"""
    corner = ProcessCorner(id="ss", model_section="Post_simu_top_ss", variables={"temperature": "125", "F": "40"})

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert 'temperature=125' in result
    assert 'F=40' in result
    assert 'W=1.8u' in result


def test_render_corner_netlist_template_replaces_model_file() -> None:
    source_text = """simulator lang=spectre
include /path/to/old_model.scs section=Post_simu_top_tt
parameters temperature=27
"""
    corner = ProcessCorner(
        id="ss",
        model_file="/path/to/new_model.scs",
        model_section="Post_simu_top_ss",
    )

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert "include /path/to/new_model.scs section=Post_simu_top_ss" in result
    assert "/path/to/old_model.scs" not in result
    assert "section=Post_simu_top_tt" not in result


def test_render_corner_netlist_template_model_file_replaces_file_path() -> None:
    source_text = """simulator lang=spectre
include /old/path/model.scs section=Post_simu_top_tt
"""
    corner = ProcessCorner(id="ss", model_file="/new/path/model.scs")

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert "include /new/path/model.scs section=Post_simu_top_tt" in result
    assert "/old/path/model.scs" not in result


def test_render_corner_netlist_template_model_file_without_section_silently_noop() -> None:
    source_text = """simulator lang=spectre
include /path/to/old_model.scs
parameters temperature=27
"""
    corner = ProcessCorner(
        id="ss",
        model_file="/path/to/new_model.scs",
    )

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert "include /path/to/old_model.scs" in result
    assert "/path/to/new_model.scs" not in result


def test_render_corner_netlist_template_model_file_preserves_quotes() -> None:
    source_text = """simulator lang=spectre
include "/path/to/old_model.scs" section=Post_simu_top_tt
"""
    corner = ProcessCorner(id="ss", model_file="/path/to/new_model.scs")

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert 'include "/path/to/new_model.scs" section=Post_simu_top_tt' in result


def test_render_corner_netlist_template_raises_when_model_section_missing() -> None:
    source_text = """simulator lang=spectre
parameters temperature=27 F=20 W=1.8u
"""
    corner = ProcessCorner(id="ss", model_section="Post_simu_top_ss")

    with pytest.raises(ValueError, match="model_section"):
        render_corner_netlist_template(source_text, corner, "tt")


def test_prepare_netlist_generates_corner_templates_for_multi_testbench(
    tmp_path: Path,
) -> None:
    corner_config = ProcessCornerConfig(
        schema_version="1.0",
        objective_policy="worst_case",
        constraint_policy="all_corners",
        corners=[
            ProcessCorner(id="tt", model_section="Post_simu_top_tt", variables={"temperature": "27"}),
            ProcessCorner(id="ss", model_section="Post_simu_top_ss", variables={"temperature": "125"}),
        ],
    )
    project_dir = _project_with_testbench_input_and_corners(
        tmp_path,
        """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        corner_config,
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.PASS
    tt_template = project_dir / "netlists" / "testbenches" / "tb1" / "corners" / "tt" / "template.scs"
    ss_template = project_dir / "netlists" / "testbenches" / "tb1" / "corners" / "ss" / "template.scs"
    assert tt_template.exists()
    assert ss_template.exists()
    ss_text = ss_template.read_text(encoding="utf-8")
    assert 'section=Post_simu_top_ss' in ss_text
    assert 'temperature=125' in ss_text
    assert 'FN={{FN}}' in ss_text
    assert 'WN={{WN}}' in ss_text


def test_prepare_netlist_skips_corner_templates_when_no_corners_configured(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_testbench_input_and_corners(
        tmp_path,
        """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        None,
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.PASS
    assert not (project_dir / "netlists" / "testbenches" / "tb1" / "corners").exists()


def test_corner_variables_are_generic_not_temperature_special_cased() -> None:
    """B-FIXRUN-04: Process Corners.variables must use the generic parameter
    rewrite path for ANY variable name. An arbitrary (non-temperature) variable
    must be injected identically to temperature, proving no special-casing."""
    source_text = """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 F=20 vdd=900m
"""
    # Use only arbitrary (non-temperature) variable names.
    corner = ProcessCorner(
        id="ss",
        model_section="Post_simu_top_ss",
        variables={"F": "40", "vdd": "850m"},
    )

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert "F=40" in result
    assert "vdd=850m" in result
    # temperature is untouched (not special-cased to follow simulatorOptions).
    assert "temperature=27" in result
    assert "section=Post_simu_top_ss" in result
    assert "section=Post_simu_top_tt" not in result


def test_corner_model_section_switches_per_corner() -> None:
    """B-FIXRUN-04: model_section must switch per corner via the generic
    include-section substitution."""
    source_text = """simulator lang=spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27
"""
    tt = ProcessCorner(id="tt", model_section="Post_simu_top_tt")
    ss = ProcessCorner(id="ss", model_section="Post_simu_top_ss")
    ff = ProcessCorner(id="ff", model_section="Post_simu_top_ff")

    assert "section=Post_simu_top_tt" in render_corner_netlist_template(
        source_text, tt, "tt"
    )
    assert "section=Post_simu_top_ss" in render_corner_netlist_template(
        source_text, ss, "tt"
    )
    assert "section=Post_simu_top_ff" in render_corner_netlist_template(
        source_text, ff, "tt"
    )
