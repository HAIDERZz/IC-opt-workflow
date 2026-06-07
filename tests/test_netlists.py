import json
from pathlib import Path

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.package import create_project_from_template
from hermes_workflow.reports import NetlistPreparationReport, PassFail


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
