from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from hermes_workflow.reports import NetlistPreparationReport, PassFail
from hermes_workflow.validate import ContractBundle, assert_valid_project


ASSIGNMENT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ANALYSIS_NAMES = {"tran", "dc", "dcOp", "ac", "pss", "pac", "pnoise", "stb", "sp"}


def prepare_netlist(project_dir: Path) -> NetlistPreparationReport:
    bundle = assert_valid_project(project_dir)
    exported_path = _project_path(bundle, bundle.project_config.netlist.exported_input_scs)
    template_path = _project_path(bundle, bundle.project_config.netlist.template_scs)
    variable_names = [variable.name for variable in bundle.variables.variables]
    template_status = {name: False for name in variable_names}
    issues: list[str] = []

    if not exported_path.exists():
        issues.append(f"exported input.scs is missing: {bundle.project_config.netlist.exported_input_scs}")
        report = _build_report(bundle, PassFail.FAIL, template_status, [], False, issues)
        _write_report(bundle, report)
        return report

    deck_text = exported_path.read_text(encoding="utf-8")
    template_text, template_status, analysis_statements, issues = _template_deck(
        deck_text,
        variable_names,
    )
    status = PassFail.PASS if not issues and all(template_status.values()) else PassFail.FAIL

    if status == PassFail.PASS:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_text, encoding="utf-8")

    report = _build_report(
        bundle,
        status,
        template_status,
        analysis_statements,
        False,
        issues,
    )
    _write_report(bundle, report)
    return report


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"netlist path must be project-relative and safe: {relative_path}")
    return bundle.project_dir / Path(*path.parts)


def _template_deck(
    deck_text: str,
    variable_names: list[str],
) -> tuple[str, dict[str, bool], list[str], list[str]]:
    template_status = {name: False for name in variable_names}
    seen_counts = {name: 0 for name in variable_names}
    output_lines: list[str] = []
    analysis_statements: list[str] = []

    for line in deck_text.splitlines(keepends=True):
        stripped = line.lstrip()
        token = stripped.split(maxsplit=1)[0] if stripped.split(maxsplit=1) else ""
        if token in ANALYSIS_NAMES and token not in analysis_statements:
            analysis_statements.append(token)

        if token != "parameters":
            output_lines.append(line)
            continue

        rewritten = line
        for name in variable_names:
            rewritten, count = _replace_assignment_value(rewritten, name, f"{{{{{name}}}}}")
            seen_counts[name] += count
            if count:
                template_status[name] = True
        output_lines.append(rewritten)

    issues: list[str] = []
    for name, count in seen_counts.items():
        if count == 0:
            issues.append(f"approved variable {name} was not found in top-level parameters")
        elif count > 1:
            issues.append(f"approved variable {name} appears more than once in top-level parameters")

    return "".join(output_lines), template_status, analysis_statements, issues


def _replace_assignment_value(line: str, name: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<![A-Za-z0-9_])({re.escape(name)}=)(\S+)")
    return pattern.subn(rf"\1{replacement}", line)


def _build_report(
    bundle: ContractBundle,
    status: PassFail,
    template_status: dict[str, bool],
    analysis_statements: list[str],
    forbidden_setup_changes_detected: bool,
    issues: list[str],
) -> NetlistPreparationReport:
    return NetlistPreparationReport(
        schema_version="1.0",
        status=status,
        exported_input_scs=bundle.project_config.netlist.exported_input_scs,
        template_scs=bundle.project_config.netlist.template_scs,
        approved_variables_template_status=template_status,
        analysis_statements=analysis_statements,
        forbidden_setup_changes_detected=forbidden_setup_changes_detected,
        issues=issues,
    )


def _write_report(bundle: ContractBundle, report: NetlistPreparationReport) -> None:
    report_path = bundle.project_dir / "reports" / "netlist_preparation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
