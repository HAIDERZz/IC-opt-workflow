from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from hermes_workflow.reports import NetlistPreparationReport, PassFail
from hermes_workflow.validate import ContractBundle, assert_valid_project


ANALYSIS_NAMES = {"tran", "dc", "dcOp", "ac", "pss", "pac", "pnoise", "stb", "sp"}
ASSIGNMENT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<name>[A-Za-z_][A-Za-z0-9_]*)=")


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
    lines = deck_text.splitlines(keepends=True)
    output_lines = list(lines)
    analysis_statements: list[str] = []
    variable_set = set(variable_names)
    issues: list[str] = []

    for statement in _logical_statements(lines):
        statement_text = "".join(lines[index] for index in statement)
        first_token = _first_token(statement_text)
        if first_token in ANALYSIS_NAMES and first_token not in analysis_statements:
            analysis_statements.append(first_token)

        if first_token != "parameters":
            continue

        rewritten, found_counts = _rewrite_parameter_statement(
            statement_text,
            variable_set,
        )
        for name, count in found_counts.items():
            seen_counts[name] += count
            if count:
                template_status[name] = True

        rewritten_lines = _split_rewritten_statement(rewritten, statement_text)
        if len(rewritten_lines) != len(statement):
            issues.append("parameters statement could not be rewritten without changing line structure")
            continue
        for index, rewritten_line in zip(statement, rewritten_lines, strict=True):
            output_lines[index] = rewritten_line

    for name, count in seen_counts.items():
        if count == 0:
            issues.append(f"approved variable {name} was not found in top-level parameters")
        elif count > 1:
            issues.append(f"approved variable {name} appears more than once in top-level parameters")

    return "".join(output_lines), template_status, analysis_statements, issues


def _logical_statements(lines: list[str]) -> list[list[int]]:
    statements: list[list[int]] = []
    current: list[int] = []
    for index, line in enumerate(lines):
        current.append(index)
        if _continues(line):
            continue
        statements.append(current)
        current = []
    if current:
        statements.append(current)
    return statements


def _continues(line: str) -> bool:
    return line.rstrip("\r\n").rstrip().endswith("\\")


def _first_token(statement_text: str) -> str:
    stripped = statement_text.lstrip()
    if not stripped:
        return ""
    return stripped.split(maxsplit=1)[0]


def _rewrite_parameter_statement(
    statement_text: str,
    variable_set: set[str],
) -> tuple[str, dict[str, int]]:
    matches = list(ASSIGNMENT_TOKEN_RE.finditer(statement_text))
    found_counts = {name: 0 for name in variable_set}
    pieces: list[str] = []
    cursor = 0

    for index, match in enumerate(matches):
        name = match.group("name")
        value_start = match.end()
        value_end = _assignment_value_end(statement_text, matches, index)
        pieces.append(statement_text[cursor:value_start])
        if name in variable_set:
            pieces.append(f"{{{{{name}}}}}")
            found_counts[name] += 1
        else:
            pieces.append(statement_text[value_start:value_end])
        cursor = value_end

    pieces.append(statement_text[cursor:])
    return "".join(pieces), found_counts


def _assignment_value_end(
    statement_text: str,
    matches: list[re.Match[str]],
    index: int,
) -> int:
    value_start = matches[index].end()
    if index + 1 < len(matches):
        next_start = matches[index + 1].start()
    else:
        next_start = len(statement_text)
    value_end = value_start
    for char in statement_text[value_start:next_start]:
        if char.isspace() or char == "\\":
            break
        value_end += 1
    return value_end


def _split_rewritten_statement(
    rewritten: str,
    original: str,
) -> list[str]:
    if original.count("\n") != rewritten.count("\n"):
        return [rewritten]
    return rewritten.splitlines(keepends=True)


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
