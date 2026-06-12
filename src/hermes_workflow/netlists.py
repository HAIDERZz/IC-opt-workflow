from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

import yaml

from hermes_workflow.reports import NetlistPreparationReport, PassFail
from hermes_workflow.schemas import ProcessCorner, ProcessCornerConfig
from hermes_workflow.validate import ContractBundle, assert_valid_project


ANALYSIS_NAMES = {"tran", "dc", "dcOp", "ac", "pss", "pac", "pnoise", "stb", "sp"}
ASSIGNMENT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<name>[A-Za-z_][A-Za-z0-9_]*)=")
INCLUDE_SECTION_RE = re.compile(r"^(include\s+\S+\s+section=)\S+", re.MULTILINE)
INCLUDE_FILE_RE = re.compile(r'^(include\s+)("?)[^"\s]+("?\s+section=\S+)', re.MULTILINE)


def prepare_netlist(project_dir: Path) -> NetlistPreparationReport:
    bundle = assert_valid_project(project_dir)
    variable_names = [variable.name for variable in bundle.variables.variables]
    if bundle.testbenches is not None:
        report = _prepare_multi_testbench_netlists(bundle, variable_names)
        _write_report(bundle, report)
        return report

    report = _prepare_one_netlist(
        bundle,
        bundle.project_config.netlist.exported_input_scs,
        bundle.project_config.netlist.template_scs,
        variable_names,
    )
    _write_report(bundle, report)
    return report


def _prepare_one_netlist(
    bundle: ContractBundle,
    exported_relative: str,
    template_relative: str,
    variable_names: list[str],
    testbench_id: str | None = None,
) -> NetlistPreparationReport:
    exported_path = _project_path(bundle, exported_relative)
    template_path = _project_path(bundle, template_relative)
    template_status = {name: False for name in variable_names}
    issues: list[str] = []

    if not exported_path.exists():
        issues.append(f"exported input.scs is missing: {exported_relative}")
        return _build_report(
            PassFail.FAIL,
            exported_relative,
            template_relative,
            template_status,
            [],
            False,
            issues,
        )

    deck_text = exported_path.read_text(encoding="utf-8")
    (
        template_text,
        template_status,
        analysis_statements,
        forbidden_setup_changes_detected,
        issues,
    ) = _template_deck(
        deck_text,
        variable_names,
    )
    status = PassFail.PASS if not issues and all(template_status.values()) else PassFail.FAIL

    if status == PassFail.PASS:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_text, encoding="utf-8")
        corner_issues = prepare_corner_netlist_templates(
            bundle,
            testbench_id,
            template_text,
        )
        issues.extend(corner_issues)
        if corner_issues:
            status = PassFail.FAIL
            template_path.unlink()
    elif template_path.exists():
        template_path.unlink()

    return _build_report(
        status,
        exported_relative,
        template_relative,
        template_status,
        analysis_statements,
        forbidden_setup_changes_detected,
        issues,
    )


def _prepare_multi_testbench_netlists(
    bundle: ContractBundle,
    variable_names: list[str],
) -> NetlistPreparationReport:
    if bundle.testbenches is None:
        raise TypeError("multi-testbench netlist preparation requires testbenches")

    reports: list[tuple[str, NetlistPreparationReport]] = []
    for testbench in bundle.testbenches.testbenches:
        testbench_id = testbench.id
        reports.append(
            (
                testbench_id,
                _prepare_one_netlist(
                    bundle,
                    _testbench_exported_input(testbench_id),
                    _testbench_template(testbench_id),
                    variable_names,
                    testbench_id,
                ),
            )
        )

    primary_legacy_report: NetlistPreparationReport | None = None
    legacy_exported = _project_path(
        bundle,
        bundle.project_config.netlist.exported_input_scs,
    )
    if legacy_exported.exists():
        primary_legacy_report = _prepare_one_netlist(
            bundle,
            bundle.project_config.netlist.exported_input_scs,
            bundle.project_config.netlist.template_scs,
            variable_names,
        )

    return _aggregate_multi_testbench_reports(
        bundle,
        reports,
        primary_legacy_report,
        variable_names,
    )


def _aggregate_multi_testbench_reports(
    bundle: ContractBundle,
    reports: list[tuple[str, NetlistPreparationReport]],
    primary_legacy_report: NetlistPreparationReport | None,
    variable_names: list[str],
) -> NetlistPreparationReport:
    all_reports = [report for _testbench_id, report in reports]
    if primary_legacy_report is not None:
        all_reports.append(primary_legacy_report)

    template_status = {
        name: all(
            report.approved_variables_template_status.get(name, False)
            for report in all_reports
        )
        for name in variable_names
    }
    analysis_statements: list[str] = []
    for report in all_reports:
        for analysis in report.analysis_statements:
            if analysis not in analysis_statements:
                analysis_statements.append(analysis)

    issues: list[str] = []
    for testbench_id, report in reports:
        if report.status == PassFail.PASS:
            continue
        issues.extend(f"{testbench_id}: {issue}" for issue in report.issues)
    if primary_legacy_report is not None and primary_legacy_report.status != PassFail.PASS:
        issues.extend(
            f"primary: {issue}" for issue in primary_legacy_report.issues
        )

    status = (
        PassFail.PASS
        if not issues
        and all(report.status == PassFail.PASS for report in all_reports)
        and all(template_status.values())
        else PassFail.FAIL
    )
    return _build_report(
        status,
        "netlists/testbenches",
        "netlists/testbenches",
        template_status,
        analysis_statements,
        any(report.forbidden_setup_changes_detected for report in all_reports),
        issues,
    )


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"netlist path must be project-relative and safe: {relative_path}")
    return bundle.project_dir / Path(*path.parts)


def _testbench_exported_input(testbench_id: str) -> str:
    return f"netlists/testbenches/{testbench_id}/exported/input.scs"


def _testbench_template(testbench_id: str) -> str:
    return f"netlists/testbenches/{testbench_id}/templates/template.scs"


def _template_deck(
    deck_text: str,
    variable_names: list[str],
) -> tuple[str, dict[str, bool], list[str], bool, list[str]]:
    template_status = {name: False for name in variable_names}
    seen_counts = {name: 0 for name in variable_names}
    lines = deck_text.splitlines(keepends=True)
    output_lines = list(lines)
    analysis_statements: list[str] = []
    variable_set = set(variable_names)
    issues: list[str] = []
    ineligible_counts = {name: 0 for name in variable_names}
    subckt_depth = 0

    for statement in _logical_statements(lines):
        statement_text = "".join(lines[index] for index in statement)
        first_token = _first_token(statement_text)
        if first_token in ANALYSIS_NAMES and first_token not in analysis_statements:
            analysis_statements.append(first_token)

        is_top_level = subckt_depth == 0
        if first_token == "subckt":
            subckt_depth += 1
        elif first_token == "ends" and subckt_depth > 0:
            subckt_depth -= 1

        if first_token != "parameters":
            continue

        if not is_top_level:
            for name, count in _count_approved_assignments(
                statement_text,
                variable_set,
            ).items():
                ineligible_counts[name] += count
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
    for name, count in ineligible_counts.items():
        if count:
            issues.append(f"approved variable {name} was found outside top-level parameters")

    forbidden_setup_changes_detected = any(ineligible_counts.values())
    return (
        "".join(output_lines),
        template_status,
        analysis_statements,
        forbidden_setup_changes_detected,
        issues,
    )


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


def _count_approved_assignments(
    statement_text: str,
    variable_set: set[str],
) -> dict[str, int]:
    found_counts = {name: 0 for name in variable_set}
    for match in ASSIGNMENT_TOKEN_RE.finditer(statement_text):
        name = match.group("name")
        if name in variable_set:
            found_counts[name] += 1
    return found_counts


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
    segment = statement_text[value_start:next_start]
    if "\\" in segment:
        segment = segment[: segment.index("\\")]
    return value_start + len(segment.rstrip())


def _split_rewritten_statement(
    rewritten: str,
    original: str,
) -> list[str]:
    if original.count("\n") != rewritten.count("\n"):
        return [rewritten]
    return rewritten.splitlines(keepends=True)


def render_corner_netlist_template(
    source_text: str,
    corner: ProcessCorner,
    base_corner_id: str,
) -> str:
    if corner.id == base_corner_id:
        return source_text

    result = source_text
    if corner.model_section is not None:
        if not INCLUDE_SECTION_RE.search(result):
            raise ValueError(
                f"corner {corner.id} requests model_section={corner.model_section!r} "
                "but no include ... section=... line was found"
            )
        result = INCLUDE_SECTION_RE.sub(
            r"\g<1>" + corner.model_section,
            result,
        )

    if corner.model_file is not None:
        result = INCLUDE_FILE_RE.sub(
            r"\g<1>\g<2>" + corner.model_file + r"\g<3>",
            result,
        )

    if corner.variables is not None:
        result = _rewrite_corner_variables(result, corner.variables)

    return result


def _rewrite_corner_variables(
    source_text: str,
    corner_variables: dict[str, str],
) -> str:
    lines = source_text.splitlines(keepends=True)
    output_lines = list(lines)
    subckt_depth = 0

    for statement in _logical_statements(lines):
        statement_text = "".join(lines[index] for index in statement)
        first_token = _first_token(statement_text)

        if first_token == "subckt":
            subckt_depth += 1
            continue
        elif first_token == "ends" and subckt_depth > 0:
            subckt_depth -= 1
            continue

        if first_token != "parameters" or subckt_depth > 0:
            continue

        rewritten = _rewrite_parameter_values(statement_text, corner_variables)
        rewritten_lines = _split_rewritten_statement(rewritten, statement_text)
        if len(rewritten_lines) != len(statement):
            continue
        for index, rewritten_line in zip(statement, rewritten_lines, strict=True):
            output_lines[index] = rewritten_line

    return "".join(output_lines)


def _rewrite_parameter_values(
    statement_text: str,
    corner_variables: dict[str, str],
) -> str:
    matches = list(ASSIGNMENT_TOKEN_RE.finditer(statement_text))
    pieces: list[str] = []
    cursor = 0

    for index, match in enumerate(matches):
        name = match.group("name")
        value_start = match.end()
        value_end = _assignment_value_end(statement_text, matches, index)
        pieces.append(statement_text[cursor:value_start])
        if name in corner_variables:
            pieces.append(corner_variables[name])
        else:
            pieces.append(statement_text[value_start:value_end])
        cursor = value_end

    pieces.append(statement_text[cursor:])
    return "".join(pieces)


def prepare_corner_netlist_templates(
    bundle: ContractBundle,
    testbench_id: str | None,
    base_template_text: str,
) -> list[str]:
    corner_path = bundle.project_dir / "config" / "process_corners.yaml"
    if not corner_path.exists():
        return []

    payload = yaml.safe_load(corner_path.read_text(encoding="utf-8"))
    corner_config = ProcessCornerConfig.model_validate(payload)

    issues: list[str] = []
    for corner in corner_config.corners:
        try:
            corner_text = render_corner_netlist_template(
                base_template_text,
                corner,
                bundle.project_config.testbench.corner,
            )
        except ValueError as exc:
            issues.append(str(exc))
            continue

        if testbench_id is not None:
            corner_template_path = _project_path(
                bundle,
                f"netlists/testbenches/{testbench_id}/corners/{corner.id}/template.scs",
            )
        else:
            corner_template_path = _project_path(
                bundle,
                f"netlists/corners/{corner.id}/template.scs",
            )

        corner_template_path.parent.mkdir(parents=True, exist_ok=True)
        corner_template_path.write_text(corner_text, encoding="utf-8")

    return issues


def _build_report(
    status: PassFail,
    exported_input_scs: str,
    template_scs: str,
    template_status: dict[str, bool],
    analysis_statements: list[str],
    forbidden_setup_changes_detected: bool,
    issues: list[str],
) -> NetlistPreparationReport:
    return NetlistPreparationReport(
        schema_version="1.0",
        status=status,
        exported_input_scs=exported_input_scs,
        template_scs=template_scs,
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
