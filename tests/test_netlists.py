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
