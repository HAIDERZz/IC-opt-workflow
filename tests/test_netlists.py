import json
from pathlib import Path

import pytest
import yaml

from hermes_workflow.netlists import (
    prepare_netlist,
    render_corner_netlist_template,
)
from hermes_workflow.reports import NetlistPreparationReport, PassFail
from hermes_workflow.schemas import ProcessCorner, ProcessCornerConfig
from tests.netlist_dry_run_helpers import (
    assign_all_metrics_to_testbench,
    create_preflight_project,
    variable_names,
)


@pytest.mark.parametrize(
    "corner_kwargs",
    [
        {"model_section": ""},
        {"model_section": None},
        {"model_section": "tt section=evil"},
        {"model_section": "tt\ninclude /tmp/evil"},
        {"model_section": 'tt"evil'},
        {"model_file": "relative/model.scs"},
        {"model_file": ""},
        {"model_file": None},
        {"model_file": '/models/good.scs" section=evil'},
        {"model_file": "/models/good.scs\ninclude /tmp/evil"},
        {"variables": {"bad-name": "27"}},
        {"variables": None},
        {"variables": {"temperature": ""}},
        {"variables": {"temperature": "27 C"}},
        {"variables": {"temperature": '27"evil'}},
        {"variables": {"temperature": "27\nparameters hacked=1"}},
    ],
)
def test_process_corner_rejects_unsafe_netlist_rendering_tokens(
    corner_kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ProcessCorner(id="ss", **corner_kwargs)


def test_process_corner_rejects_spaced_model_file_for_unquoted_include() -> None:
    source_text = (
        "simulator lang=spectre\n"
        "include /models/device.scs section=Post_simu_top_tt\n"
    )

    with pytest.raises(ValueError, match="model_file.*whitespace"):
        corner = ProcessCorner(
            id="ss",
            model_file="/models/slow corner/device.scs",
        )
        render_corner_netlist_template(source_text, corner, "tt")


def _load_netlist_report(project_dir: Path) -> NetlistPreparationReport:
    payload = json.loads(
        (project_dir / "reports" / "netlist_preparation_report.json").read_text(
            encoding="utf-8"
        )
    )
    return NetlistPreparationReport.model_validate(payload)


def test_prepare_netlist_templates_single_line_parameter_values(tmp_path: Path) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {first}=4 {second}=0.6u\n"
        f"M0 (VOUT IN VSS VSS) nmos w={second}*{first} l=45n\n"
        "tran tran stop=10n\n"
        "dcOp dc oppoint=rawfile\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    persisted_report = _load_netlist_report(project_dir)

    assert report.status == PassFail.PASS
    assert persisted_report == report
    assert f"{first}={{{{{first}}}}}" in template_text
    assert f"{second}={{{{{second}}}}}" in template_text
    assert "temperature=27" in template_text
    assert f"w={second}*{first}" in template_text
    assert report.approved_variables_template_status == {first: True, second: True}
    assert report.analysis_statements == ["tran", "dcOp"]
    assert report.forbidden_setup_changes_detected is False
    assert report.issues == []


def test_prepare_netlist_templates_backslash_continued_parameters(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        "parameters \\\n"
        "    temperature=27 \\\n"
        f"    L2=45n {first}=4 \\\n"
        f"    {second}=0.6u\n"
        f"I0 (VOUT IN VSS VSS) inverter w={second}*{first} fingers={first}\n"
        "pss pss fund=1G harms=10\n"
        "pac pac maxsideband=10\n"
        "pnoise pnoise maxsideband=10\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert f"{first}={{{{{first}}}}}" in template_text
    assert f"{second}={{{{{second}}}}}" in template_text
    assert "L2=45n" in template_text
    assert f"w={second}*{first} fingers={first}" in template_text
    assert report.analysis_statements == ["pss", "pac", "pnoise"]


def test_prepare_netlist_does_not_template_instance_parameters(tmp_path: Path) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {first}=4 {second}=0.6u\n"
        "subckt wrapped IN OUT VDD VSS\n"
        f"M0 (OUT IN VSS VSS) nmos w={second}*{first} l=45n\n"
        "ends wrapped\n"
        f"X0 (IN OUT VDD VSS) wrapped {first}=99 {second}=99u\n"
        "ac ac start=1 stop=10G\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert (
        f"parameters temperature=27 {first}={{{{{first}}}}} {second}={{{{{second}}}}}"
        in template_text
    )
    assert f"X0 (IN OUT VDD VSS) wrapped {first}=99 {second}=99u" in template_text


def test_prepare_netlist_writes_fail_report_when_input_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    (project_dir / "netlists" / "exported" / "input.scs").unlink()
    # The generic factory pre-creates a template; remove it so this test verifies
    # prepare_netlist does not write a template when the exported input is missing.
    (project_dir / "netlists" / "templates" / "template.scs").unlink()

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert "exported input.scs is missing" in report.issues[0]
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()
    assert _load_netlist_report(project_dir) == report


def test_prepare_netlist_writes_fail_report_when_approved_variable_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {first}=4\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert report.approved_variables_template_status[second] is False
    assert (
        f"approved variable {second} was not found in top-level parameters"
        in report.issues
    )
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def test_prepare_netlist_writes_fail_report_for_duplicate_approved_variable(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {first}=4 {second}=0.6u\n"
        f"parameters {first}=5\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert (
        f"approved variable {first} appears more than once in top-level parameters"
        in report.issues
    )
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def test_prepare_netlist_templates_values_with_whitespace_units(tmp_path: Path) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {first}=4 {second}=0.6 u\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert f"{first}={{{{{first}}}}}" in template_text
    assert f"{second}={{{{{second}}}}}" in template_text
    assert f"{second}={{{{{second}}}}} u" not in template_text


def test_prepare_netlist_fails_closed_for_subckt_parameter_assignments(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        "simulator lang=spectre\n"
        f"parameters temperature=27 {second}=0.6u\n"
        "subckt wrapped IN OUT VDD VSS\n"
        f"parameters {first}=4\n"
        f"M0 (OUT IN VSS VSS) nmos w={second}*{first} l=45n\n"
        "ends wrapped\n"
        "tran tran stop=10n\n",
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert report.forbidden_setup_changes_detected is True
    assert (
        f"approved variable {first} was found outside top-level parameters"
        in report.issues
    )
    assert (
        f"approved variable {first} was not found in top-level parameters"
        in report.issues
    )
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def _setup_testbench_project(
    project_dir: Path,
    deck_text: str,
    corner_config: ProcessCornerConfig | None,
) -> None:
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
    assign_all_metrics_to_testbench(project_dir, "tb1")
    input_path = (
        project_dir / "netlists" / "testbenches" / "tb1" / "exported" / "input.scs"
    )
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(deck_text, encoding="utf-8")
    legacy_input = project_dir / "netlists" / "exported" / "input.scs"
    legacy_input.parent.mkdir(parents=True, exist_ok=True)
    legacy_input.write_text(deck_text, encoding="utf-8")
    if corner_config is not None:
        corner_path = project_dir / "config" / "process_corners.yaml"
        corner_path.write_text(
            yaml.safe_dump(corner_config.model_dump(mode="json", exclude_none=True)),
            encoding="utf-8",
        )


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


def test_render_corner_netlist_template_rejects_model_file_without_section() -> None:
    source_text = """simulator lang=spectre
include /path/to/old_model.scs
parameters temperature=27
"""
    corner = ProcessCorner(
        id="ss",
        model_file="/path/to/new_model.scs",
    )

    with pytest.raises(ValueError, match="model_file"):
        render_corner_netlist_template(source_text, corner, "tt")


def test_render_corner_netlist_template_model_file_preserves_quotes() -> None:
    source_text = """simulator lang=spectre
include "/path/to/old_model.scs" section=Post_simu_top_tt
"""
    corner = ProcessCorner(id="ss", model_file="/path/to/new_model.scs")

    result = render_corner_netlist_template(source_text, corner, "tt")

    assert 'include "/path/to/new_model.scs" section=Post_simu_top_tt' in result


def test_render_corner_netlist_template_rejects_ambiguous_model_file_include() -> None:
    source_text = """simulator lang=spectre
include "/models/device.scs" section=Post_simu_top_tt
include "/models/passive.scs" section=passive_typ
"""
    corner = ProcessCorner(id="ss", model_file="/models/device_ss.scs")

    with pytest.raises(ValueError, match="exactly one.*found 2"):
        render_corner_netlist_template(source_text, corner, "tt")


def test_prepare_netlist_fails_before_writing_ambiguous_corner_model_file(
    tmp_path: Path,
) -> None:
    corner_config = ProcessCornerConfig(
        schema_version="1.0",
        objective_policy="worst_case",
        constraint_policy="all_corners",
        corners=[ProcessCorner(id="ss", model_file="/models/device_ss.scs")],
    )
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    _setup_testbench_project(
        project_dir,
        "simulator lang=spectre\n"
        'include "/models/device.scs" section=Post_simu_top_tt\n'
        'include "/models/passive.scs" section=passive_typ\n'
        f"parameters {first}=4 {second}=0.6u\n",
        corner_config,
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert any("must match exactly one" in issue for issue in report.issues)
    assert not (
        project_dir
        / "netlists"
        / "testbenches"
        / "tb1"
        / "corners"
        / "ss"
        / "template.scs"
    ).exists()


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
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    _setup_testbench_project(
        project_dir,
        "simulator lang=spectre\n"
        'include "/path/to/toplevel.scs" section=Post_simu_top_tt\n'
        f"parameters temperature=27 {first}=4 {second}=0.6u\n"
        "tran tran stop=10n\n",
        corner_config,
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.PASS
    tt_template = project_dir / "netlists" / "testbenches" / "tb1" / "corners" / "tt" / "template.scs"
    ss_template = project_dir / "netlists" / "testbenches" / "tb1" / "corners" / "ss" / "template.scs"
    assert tt_template.exists()
    assert ss_template.exists()
    ss_text = ss_template.read_text(encoding="utf-8")
    assert "section=Post_simu_top_ss" in ss_text
    assert "temperature=125" in ss_text
    assert f"{first}={{{{{first}}}}}" in ss_text
    assert f"{second}={{{{{second}}}}}" in ss_text


def test_prepare_netlist_rejects_corner_variable_not_present_in_deck(
    tmp_path: Path,
) -> None:
    corner_config = ProcessCornerConfig(
        schema_version="1.0",
        objective_policy="worst_case",
        constraint_policy="all_corners",
        corners=[
            ProcessCorner(
                id="ss",
                model_section="Post_simu_top_ss",
                variables={"temperatur": "125"},
            ),
        ],
    )
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    _setup_testbench_project(
        project_dir,
        "simulator lang=spectre\n"
        'include "/path/to/toplevel.scs" section=Post_simu_top_tt\n'
        f"parameters temperature=27 {first}=4 {second}=0.6u\n",
        corner_config,
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert any(
        "corner ss variable 'temperatur' was not found" in issue
        for issue in report.issues
    )


def test_prepare_netlist_uses_each_testbench_source_corner(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    project_config_path = project_dir / "config" / "project_config.yaml"
    project_config = yaml.safe_load(project_config_path.read_text(encoding="utf-8"))
    project_config["testbench"]["corner"] = "tt"
    project_config_path.write_text(
        yaml.safe_dump(project_config, sort_keys=False),
        encoding="utf-8",
    )
    (project_dir / "config" / "testbenches.yaml").write_text(
        """schema_version: "1.0"
testbenches:
  - id: tb_tt
    maestro_point_root: /tmp/maestro_tt
    virtuoso_library: TestLib
    cell: TestCellTT
    design_view: schematic
    maestro_view: maestro
    test_name: test_tt
    corner: tt
  - id: tb_ss
    maestro_point_root: /tmp/maestro_ss
    virtuoso_library: TestLib
    cell: TestCellSS
    design_view: schematic
    maestro_view: maestro
    test_name: test_ss
    corner: ss
""",
        encoding="utf-8",
    )
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics_payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    metrics_payload["metrics"][0]["testbench"] = "tb_tt"
    metrics_payload["metrics"][1]["testbench"] = "tb_ss"
    metrics_path.write_text(
        yaml.safe_dump(metrics_payload, sort_keys=False),
        encoding="utf-8",
    )
    for testbench_id, section, temperature in (
        ("tb_tt", "Post_simu_top_tt", "27"),
        ("tb_ss", "Post_simu_top_ss", "125"),
    ):
        input_path = (
            project_dir
            / "netlists"
            / "testbenches"
            / testbench_id
            / "exported"
            / "input.scs"
        )
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            "simulator lang=spectre\n"
            f'include "/path/to/toplevel.scs" section={section}\n'
            f"parameters temperature={temperature} {first}=4 {second}=0.6u\n",
            encoding="utf-8",
        )
    (project_dir / "netlists" / "exported" / "input.scs").unlink()
    corner_config = ProcessCornerConfig(
        schema_version="1.0",
        objective_policy="worst_case",
        constraint_policy="all_corners",
        corners=[
            ProcessCorner(
                id="tt",
                model_section="Post_simu_top_tt",
                variables={"temperature": "27"},
            ),
            ProcessCorner(
                id="ss",
                model_section="Post_simu_top_ss",
                variables={"temperature": "125"},
            ),
        ],
    )
    (project_dir / "config" / "process_corners.yaml").write_text(
        yaml.safe_dump(corner_config.model_dump(mode="json", exclude_none=True)),
        encoding="utf-8",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.PASS, report.issues
    secondary_root = project_dir / "netlists" / "testbenches" / "tb_ss" / "corners"
    tt_text = (secondary_root / "tt" / "template.scs").read_text(encoding="utf-8")
    ss_text = (secondary_root / "ss" / "template.scs").read_text(encoding="utf-8")
    assert "section=Post_simu_top_tt" in tt_text
    assert "temperature=27" in tt_text
    assert "section=Post_simu_top_ss" in ss_text
    assert "temperature=125" in ss_text
    assert tt_text != ss_text


def test_prepare_netlist_skips_corner_templates_when_no_corners_configured(
    tmp_path: Path,
) -> None:
    project_dir = create_preflight_project(tmp_path)
    first, second = variable_names(project_dir)
    _setup_testbench_project(
        project_dir,
        "simulator lang=spectre\n"
        'include "/path/to/toplevel.scs" section=Post_simu_top_tt\n'
        f"parameters temperature=27 {first}=4 {second}=0.6u\n"
        "tran tran stop=10n\n",
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
