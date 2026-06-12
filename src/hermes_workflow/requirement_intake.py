from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.schemas import (
    MetricsConfig,
    OptimizerConfig,
    ProcessCornerConfig,
    ProjectConfig,
    SpectreConfig,
    TestbenchesConfig,
    VariablesConfig,
)
from hermes_workflow.requirement_semantics import validate_requirement_semantics
from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity

REQUIRED_SECTIONS = [
    "Project",
    "Maestro Source",
    "Design Variables",
    "Metrics",
    "Constraints",
    "Objective",
    "Spectre Settings",
    "Optimizer Settings",
    "Approval Checklist",
]
OPTIONAL_SECTIONS = [
    "Process Corners",
]
APPROVAL_FIELDS = [
    "metric_formulas_user_approved",
    "maestro_source_user_approved",
    "variable_bounds_user_approved",
    "spectre_resource_settings_user_approved",
]
CONFIG_FILE_MODELS: dict[str, type[BaseModel]] = {
    "project_config.yaml": ProjectConfig,
    "variables.yaml": VariablesConfig,
    "metrics.yaml": MetricsConfig,
    "spectre.yaml": SpectreConfig,
    "optimizer.yaml": OptimizerConfig,
}
OPTIONAL_CONFIG_FILE_MODELS: dict[str, type[BaseModel]] = {
    "testbenches.yaml": TestbenchesConfig,
    "process_corners.yaml": ProcessCornerConfig,
}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping_without_duplicate_keys(
    loader: yaml.Loader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_without_duplicate_keys,
)


@dataclass(frozen=True)
class RequirementIntakeReport:
    status: str
    issues: list[str]
    structured_issues: list[Diagnostic]
    sections: dict[str, Any]
    constraints_md_present: bool
    constraints_md_sha256: str | None


@dataclass(frozen=True)
class MaestroPointImportReport:
    status: str
    issues: list[str]
    maestro_point_root: str
    copied_file_count: int
    materialized_symlink_count: int
    input_scs_sha256: str | None


@dataclass(frozen=True)
class RequirementPreparationReport:
    status: str
    issues: list[str]


def check_requirement(project_dir: str | Path) -> RequirementIntakeReport:
    project_root = Path(project_dir)
    report = _parse_and_validate_requirement(project_root)
    _write_requirement_report(project_root, report)
    return report


def prepare_from_requirement(project_dir: str | Path) -> RequirementPreparationReport:
    project_root = Path(project_dir)
    intake = check_requirement(project_root)
    if intake.status != "pass":
        return RequirementPreparationReport(status="fail", issues=intake.issues)

    config_payloads = render_config_payloads(intake.sections)
    write_config_payloads(project_root, config_payloads)
    import_reports = _import_requirement_netlists(project_root, intake.sections)
    import_issues = [
        issue
        for import_report in import_reports
        if import_report.status != "pass"
        for issue in import_report.issues
    ]
    if import_issues:
        return RequirementPreparationReport(status="fail", issues=import_issues)

    netlist_report = prepare_netlist(project_root)
    if netlist_report.status.value != "pass":
        return RequirementPreparationReport(status="fail", issues=netlist_report.issues)

    return RequirementPreparationReport(status="pass", issues=[])


def render_config_payloads(sections: dict[str, Any]) -> dict[str, dict[str, Any]]:
    project = _dict_section(sections, "Project")
    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    primary_testbench = testbenches[0]
    variables = _list_section(sections, "Design Variables")
    metrics = _list_section(sections, "Metrics")
    constraints = _list_section(sections, "Constraints")
    objective = _dict_section(sections, "Objective")
    spectre = _dict_section(sections, "Spectre Settings")
    optimizer = _dict_section(sections, "Optimizer Settings")

    payloads = {
        "project_config.yaml": {
            "schema_version": "1.0",
            "project": {
                "name": project["project_name"],
                "description": project.get("description", ""),
                "backend": project["backend"],
            },
            "testbench": {
                "virtuoso_library": primary_testbench["virtuoso_library"],
                "cell": primary_testbench["cell"],
                "design_view": primary_testbench["design_view"],
                "maestro_view": primary_testbench["maestro_view"],
                "test_name": primary_testbench["test_name"],
                "corner": primary_testbench["corner"],
            },
            "netlist": {
                "source": "existing_maestro_setup",
                "export_method": "maeCreateNetlistForCorner",
                "exported_input_scs": "netlists/exported/input.scs",
                "template_scs": "netlists/templates/template.scs",
            },
            "safety": {
                "immutable_after_package": True,
                "require_hermes_approval_before_real_run": True,
                "allow_maestro_setup_modification": False,
                "allow_only_variable_templating": True,
            },
        },
        "variables.yaml": {
            "schema_version": "1.0",
            "variables": variables,
        },
        "metrics.yaml": {
            "schema_version": "1.0",
            "metrics": [_metric_payload(metric) for metric in metrics],
            "constraints": constraints,
            "objective": objective,
        },
        "spectre.yaml": {
            "schema_version": "1.0",
            "spectre": spectre,
        },
        "optimizer.yaml": {
            "schema_version": "1.0",
            "optimizer": optimizer,
        },
    }
    if "testbenches" in maestro:
        payloads["testbenches.yaml"] = {
            "schema_version": "1.0",
            "testbenches": testbenches,
        }
    if "Process Corners" in sections:
        process_corners = _dict_section(sections, "Process Corners")
        corners = process_corners.get("corners", [])
        if not isinstance(corners, list):
            raise TypeError("Process Corners.corners must be a YAML list")
        payloads["process_corners.yaml"] = {
            "schema_version": "1.0",
            "objective_policy": process_corners.get("objective_policy", "worst_case"),
            "constraint_policy": process_corners.get("constraint_policy", "all_corners"),
            "corners": corners,
        }
    else:
        payloads["process_corners.yaml"] = {
            "schema_version": "1.0",
            "objective_policy": "nominal",
            "constraint_policy": "nominal",
            "corners": [{"id": "nominal"}],
        }
    _validate_config_payloads(payloads)
    return payloads


def write_config_payloads(
    project_dir: str | Path,
    payloads: dict[str, dict[str, Any]],
) -> None:
    config_dir = Path(project_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for file_name, payload in payloads.items():
        (config_dir / file_name).write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )


def import_maestro_point_netlist(
    project_dir: str | Path,
    maestro_point_root: str | Path,
    *,
    testbench_id: str | None = None,
) -> MaestroPointImportReport:
    project_root = Path(project_dir)
    source_root = Path(maestro_point_root).expanduser()
    netlist_root = source_root / "netlist"
    destination = _import_destination(project_root, testbench_id)
    report_path = _import_report_path(project_root, testbench_id)
    issues: list[str] = []

    if not netlist_root.is_dir():
        issues.append(f"maestro_point_root/netlist is missing: {netlist_root}")
    if not (netlist_root / "input.scs").is_file():
        issues.append(f"maestro_point_root/netlist/input.scs is missing: {netlist_root / 'input.scs'}")

    entries: list[tuple[Path, Path, bool]] = []
    if not issues:
        entries, issues = _collect_import_entries(
            _maestro_history_root(source_root),
            netlist_root,
        )

    if issues:
        issues = _prefix_import_issues(issues, testbench_id)
        report = MaestroPointImportReport(
            status="fail",
            issues=issues,
            maestro_point_root=source_root.as_posix(),
            copied_file_count=0,
            materialized_symlink_count=0,
            input_scs_sha256=None,
        )
        _write_import_report(report_path, report)
        return report

    staging_name = (
        ".exported_import_tmp"
        if testbench_id is None
        else f".{testbench_id}_exported_import_tmp"
    )
    staging = destination.parent / staging_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    copied_count = 0
    materialized_count = 0
    for source, relative, was_symlink in entries:
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_count += 1
        if was_symlink:
            materialized_count += 1

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)
    input_hash = _sha256(destination / "input.scs")
    report = MaestroPointImportReport(
        status="pass",
        issues=[],
        maestro_point_root=source_root.as_posix(),
        copied_file_count=copied_count,
        materialized_symlink_count=materialized_count,
        input_scs_sha256=input_hash,
    )
    _write_import_report(report_path, report)
    return report


def _import_requirement_netlists(
    project_root: Path,
    sections: dict[str, Any],
) -> list[MaestroPointImportReport]:
    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    if "testbenches" not in maestro:
        return [
            import_maestro_point_netlist(
                project_root,
                testbenches[0]["maestro_point_root"],
            )
        ]

    reports = [
        import_maestro_point_netlist(
            project_root,
            testbench["maestro_point_root"],
            testbench_id=testbench["id"],
        )
        for testbench in testbenches
    ]
    if all(report.status == "pass" for report in reports):
        primary = testbenches[0]
        reports.append(
            import_maestro_point_netlist(
                project_root,
                primary["maestro_point_root"],
            )
        )
    return reports


def _import_destination(project_root: Path, testbench_id: str | None) -> Path:
    if testbench_id is None:
        return project_root / "netlists" / "exported"
    return project_root / "netlists" / "testbenches" / testbench_id / "exported"


def _import_report_path(project_root: Path, testbench_id: str | None) -> Path:
    if testbench_id is None:
        return project_root / "reports" / "maestro_point_import_report.json"
    return (
        project_root
        / "reports"
        / "testbenches"
        / testbench_id
        / "maestro_point_import_report.json"
    )


def _prefix_import_issues(
    issues: list[str],
    testbench_id: str | None,
) -> list[str]:
    if testbench_id is None:
        return issues
    return [f"{testbench_id}: {issue}" for issue in issues]


def parse_requirement_text(
    requirement_text: str,
    *,
    constraints_text: str | None = None,
    maestro_input_exists: Callable[[str], bool] = lambda path: Path(path).expanduser().is_file(),
) -> RequirementIntakeReport:
    """Parse requirement text and validate its structure.

    This is the public, injectable entry-point used by both the local CLI
    (via ``_parse_and_validate_requirement``) and the remote doctor (which
    supplies its own ``maestro_input_exists`` callable to check paths over
    SSH).
    """
    issues: list[str] = []
    structured_issues: list[Diagnostic] = []
    sections: dict[str, Any] = {}

    constraints_sha = hashlib.sha256(constraints_text.encode("utf-8")).hexdigest() if constraints_text is not None else None

    raw_sections, section_issues, section_diagnostics = _extract_required_sections(
        requirement_text
    )
    issues.extend(section_issues)
    structured_issues.extend(section_diagnostics)
    if not issues:
        for name in REQUIRED_SECTIONS + OPTIONAL_SECTIONS:
            if name not in raw_sections:
                continue
            payload, payload_issues = _parse_section_yaml(name, raw_sections[name])
            if payload_issues:
                issues.extend(payload_issues)
                structured_issues.extend(
                    _structured_from_issue(name, payload_issue)
                    for payload_issue in payload_issues
                )
            else:
                sections[name] = payload

    if not issues:
        issues.extend(_validate_approval_checklist(sections))
        issues.extend(_validate_required_fields(sections))
        if not issues:
            semantic_issues = validate_requirement_semantics(sections)
            issues.extend(semantic_issues)
            structured_issues.extend(
                _structured_from_issue(_issue_context(issue), issue)
                for issue in semantic_issues
            )
        if not issues:
            try:
                render_config_payloads(sections)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                issues.append(f"rendered config validation failed: {exc}")
        for maestro_root in _maestro_point_roots(sections):
            netlist_input = PurePosixPath(str(maestro_root)) / "netlist" / "input.scs"
            if not maestro_input_exists(netlist_input.as_posix()):
                issues.append(f"maestro_point_root/netlist/input.scs is missing: {netlist_input}")
                structured_issues.append(
                    Diagnostic(
                        code="MAESTRO_INPUT_SCS_MISSING",
                        severity=DiagnosticSeverity.ERROR,
                        stage="requirement",
                        component="requirement_intake",
                        message="Required Maestro input netlist is missing.",
                        detail=f"Expected netlist/input.scs at {netlist_input}.",
                        likely_cause="maestro_point_root points to an incomplete Maestro point.",
                        recommended_action=(
                            "Update Maestro Source.maestro_point_root to a Maestro point "
                            "containing netlist/input.scs."
                        ),
                        evidence=["opt_requirement.md:Maestro Source.maestro_point_root"],
                    )
                )

    return RequirementIntakeReport(
        status="pass" if not issues else "fail",
        issues=issues,
        structured_issues=structured_issues,
        sections=sections,
        constraints_md_present=constraints_text is not None,
        constraints_md_sha256=constraints_sha,
    )


def _parse_and_validate_requirement(project_dir: Path) -> RequirementIntakeReport:
    requirement_path = project_dir / "opt_requirement.md"
    issues: list[str] = []
    sections: dict[str, Any] = {}
    constraints_path = project_dir / "constraints.md"

    if not requirement_path.exists():
        issues.append("opt_requirement.md is missing")
        structured_issues = [
            Diagnostic(
                code="REQUIREMENT_SECTION_MISSING",
                severity=DiagnosticSeverity.ERROR,
                stage="requirement",
                component="requirement_intake",
                message="opt_requirement.md is missing.",
                detail="The requirement file is required for project intake.",
                likely_cause="The project is missing opt_requirement.md.",
                recommended_action="Create opt_requirement.md before running checks.",
                evidence=["opt_requirement.md"],
            )
        ]
        return RequirementIntakeReport(
            status="fail",
            issues=issues,
            structured_issues=structured_issues,
            sections=sections,
            constraints_md_present=constraints_path.is_file(),
            constraints_md_sha256=_sha256(constraints_path) if constraints_path.is_file() else None,
        )

    requirement_text = requirement_path.read_text(encoding="utf-8")
    constraints_text = constraints_path.read_text(encoding="utf-8") if constraints_path.is_file() else None

    return parse_requirement_text(
        requirement_text,
        constraints_text=constraints_text,
        maestro_input_exists=lambda path: Path(path).expanduser().is_file(),
    )


def _extract_required_sections(
    text: str,
) -> tuple[dict[str, str], list[str], list[Diagnostic]]:
    headings: list[tuple[str, int, int]] = []
    issues: list[str] = []
    structured_issues: list[Diagnostic] = []
    lines = text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            name = stripped[3:].strip()
            headings.append((name, offset, offset + len(line)))
        offset += len(line)

    counts = {name: 0 for name in REQUIRED_SECTIONS}
    for name, _start, _end in headings:
        if name in counts:
            counts[name] += 1
    for name in REQUIRED_SECTIONS:
        if counts[name] == 0:
            issues.append(f"required section is missing: {name}")
            structured_issues.append(
                Diagnostic(
                    code="REQUIREMENT_SECTION_MISSING",
                    severity=DiagnosticSeverity.ERROR,
                    stage="requirement",
                    component="requirement_intake",
                    message=f"Required section is missing: {name}",
                    detail=f"opt_requirement.md must include a {name} section.",
                    likely_cause=f"Section {name} is not present in opt_requirement.md.",
                    recommended_action=f"Add a ## {name} section with exactly one YAML block.",
                    evidence=[f"opt_requirement.md:{name}"],
                )
            )
        elif counts[name] > 1:
            issues.append(f"required section appears more than once: {name}")
            structured_issues.append(
                Diagnostic(
                    code="REQUIREMENT_SECTION_MISSING",
                    severity=DiagnosticSeverity.ERROR,
                    stage="requirement",
                    component="requirement_intake",
                    message=f"Section {name} appears more than once.",
                    detail=f"Section {name} appears {counts[name]} times.",
                    likely_cause="Section duplication can cause parser ambiguity.",
                    recommended_action=f"Keep a single ## {name} section.",
                    evidence=[f"opt_requirement.md:{name}"],
                )
            )
    for name in OPTIONAL_SECTIONS:
        count = sum(1 for n, _s, _e in headings if n == name)
        if count > 1:
            issues.append(f"optional section appears more than once: {name}")
            structured_issues.append(
                Diagnostic(
                    code="REQUIREMENT_SECTION_MISSING",
                    severity=DiagnosticSeverity.ERROR,
                    stage="requirement",
                    component="requirement_intake",
                    message=f"Optional section {name} appears more than once.",
                    detail=f"Section {name} appears {count} times.",
                    likely_cause="Section duplication can cause parser ambiguity.",
                    recommended_action=f"Keep a single ## {name} section.",
                    evidence=[f"opt_requirement.md:{name}"],
                )
            )
    if issues:
        return {}, issues, structured_issues

    sections: dict[str, str] = {}
    for index, (name, _start, content_start) in enumerate(headings):
        if name not in REQUIRED_SECTIONS and name not in OPTIONAL_SECTIONS:
            continue
        content_end = headings[index + 1][1] if index + 1 < len(headings) else len(text)
        sections[name] = text[content_start:content_end]
    return sections, [], structured_issues


def _parse_section_yaml(name: str, text: str) -> tuple[Any, list[str]]:
    blocks = _yaml_blocks(text)
    if len(blocks) != 1:
        return None, [f"required section {name} must contain exactly one fenced yaml block"]
    try:
        payload = yaml.load(blocks[0], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return None, [f"invalid YAML in {name}: {exc}"]
    if payload is None:
        return None, [f"YAML block in {name} must not be empty"]
    return payload, []


def _structured_from_issue(context: str, issue: str) -> Diagnostic:
    if context == "objective" and "unknown metric" in issue:
        unknown_match = re.search(
            r"objective expression references unknown metric "
            r"([A-Za-z0-9_\-\.]+)(; did you mean (.+)\?)?",
            issue,
        )
        metric_name = (
            unknown_match.group(1) if unknown_match is not None else "the expression"
        )
        suggestion = unknown_match.group(3) if unknown_match is not None else None
        return Diagnostic(
            code="OBJECTIVE_UNKNOWN_METRIC",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message=f"Objective expression references unknown metric {metric_name}.",
            detail="Objective references a metric not declared in the Metrics section.",
            likely_cause="A metric name in the objective expression does not match the "
            "declared metric names.",
            recommended_action=(
                f"Replace {metric_name} with the declared name."
                + (f" Did you mean {suggestion}?" if suggestion else "")
            ),
            evidence=["opt_requirement.md:Objective.expression"],
        )

    if (
        issue.startswith("unsupported objective function ")
        or "unsupported objective node" in issue
        or issue.startswith("unsupported objective function call")
    ):
        return Diagnostic(
            code="OBJECTIVE_UNSUPPORTED_FUNCTION",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message="Objective expression uses an unsupported function or AST node.",
            detail=issue,
            likely_cause="The objective expression contains unsupported syntax.",
            recommended_action="Use supported operators and functions only.",
            evidence=["opt_requirement.md:Objective.expression"],
        )

    if (
        "objective expression returned non-finite value" in issue
        or issue.startswith("invalid objective expression")
        or "division by zero" in issue
        or "objective numeric literals must be finite" in issue
        or issue.startswith("objective function")
    ):
        return Diagnostic(
            code="OBJECTIVE_UNSAFE_EXPRESSION",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message="Objective expression is unsafe or invalid.",
            detail=issue,
            likely_cause="Expression may be mathematically invalid.",
            recommended_action="Review and simplify the objective expression.",
            evidence=["opt_requirement.md:Objective.expression"],
        )

    if "constraint references unknown metric" in issue:
        metric_match = re.search(
            r"constraint references unknown metric ([A-Za-z0-9_\-\.]+)",
            issue,
        )
        metric_name = metric_match.group(1) if metric_match is not None else "it"
        return Diagnostic(
            code="CONSTRAINT_UNKNOWN_METRIC",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message=f"Constraint references unknown metric {metric_name}.",
            detail=issue,
            likely_cause="A constraint refers to a metric not declared in Metrics.",
            recommended_action="Use a metric name from the Metrics section.",
            evidence=["opt_requirement.md:Constraints"],
        )

    if (
        "lower/upper/step must be numeric" in issue
        or "step must be positive" in issue
        or "lower must be <=" in issue
        or "names must be unique" in issue
    ):
        return Diagnostic(
            code="VARIABLE_RANGE_INVALID",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message="Design variable range is invalid.",
            detail=issue,
            likely_cause="Variable bounds or step are invalid or inconsistent.",
            recommended_action=(
                "Check lower, upper, step values and ensure variable names are unique."
            ),
            evidence=["opt_requirement.md:Design Variables"],
        )

    if "not a YAML mapping" in issue or "must contain exactly one fenced yaml block" in issue:
        return Diagnostic(
            code="REQUIREMENT_YAML_INVALID",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message="Requirement section YAML is invalid.",
            detail=issue,
            likely_cause="A required section has malformed YAML.",
            recommended_action="Fix the section YAML syntax.",
            evidence=[f"opt_requirement.md:{context}"],
        )

    if "invalid YAML in" in issue:
        return Diagnostic(
            code="REQUIREMENT_YAML_INVALID",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message="Requirement section YAML is invalid.",
            detail=issue,
            likely_cause="Malformed YAML in a required section.",
            recommended_action="Fix the section YAML syntax.",
            evidence=[f"opt_requirement.md:{context}"],
        )

    if "required section is missing" in issue or "appears more than once" in issue:
        return Diagnostic(
            code="REQUIREMENT_SECTION_MISSING",
            severity=DiagnosticSeverity.ERROR,
            stage="requirement",
            component="requirement_intake",
            message=issue,
            detail=issue,
            likely_cause="The section layout does not match the expected template.",
            recommended_action="Keep required sections exactly once with proper YAML.",
            evidence=[f"opt_requirement.md:{context}"],
        )

    return Diagnostic(
        code="REQUIREMENT_YAML_INVALID",
        severity=DiagnosticSeverity.ERROR,
        stage="requirement",
        component="requirement_intake",
        message=issue,
        detail="Unmapped requirement validation issue.",
        likely_cause="The issue did not match a known diagnostic pattern.",
        recommended_action="Check opt_requirement.md against the template and constraints.",
        evidence=[f"opt_requirement.md:{context}"],
    )


def _issue_context(issue: str) -> str:
    if issue.startswith("objective"):
        return "objective"
    if issue.startswith("constraint"):
        return "constraints"
    if issue.startswith("variable"):
        return "design variables"
    return "requirement"


def _yaml_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "```yaml":
            index += 1
            continue
        index += 1
        block_lines: list[str] = []
        while index < len(lines) and lines[index].strip() != "```":
            block_lines.append(lines[index])
            index += 1
        if index < len(lines):
            blocks.append("\n".join(block_lines))
        index += 1
    return blocks


def _validate_approval_checklist(sections: dict[str, Any]) -> list[str]:
    checklist = _dict_section(sections, "Approval Checklist")
    issues: list[str] = []
    for field in APPROVAL_FIELDS:
        if checklist.get(field) is not True:
            issues.append(f"approval checklist {field} must be true")
    return issues


def _validate_required_fields(sections: dict[str, Any]) -> list[str]:
    required = {
        "Project": ["project_name", "backend"],
        "Objective": ["direction", "expression"],
        "Spectre Settings": [
            "engine",
            "preset",
            "output_format",
            "threads_per_run",
            "parallel_jobs",
            "timeout_s",
            "require_license_check",
            "keep_failed_runs",
            "keep_successful_runs",
        ],
        "Optimizer Settings": [
            "algorithm",
            "initialization",
            "max_evaluations",
            "batch_size",
            "random_seed",
            "failure_penalty",
            "deduplicate_candidates",
        ],
    }
    issues: list[str] = []
    for section, fields in required.items():
        payload = _dict_section(sections, section)
        for field in fields:
            if field not in payload:
                issues.append(f"{section}.{field} is required")
    maestro = _dict_section(sections, "Maestro Source")
    if "testbenches" in maestro:
        testbenches = maestro["testbenches"]
        if not isinstance(testbenches, list) or not testbenches:
            issues.append("Maestro Source.testbenches must be a non-empty YAML list")
        else:
            required_testbench_fields = [
                "id",
                "maestro_point_root",
                "virtuoso_library",
                "cell",
                "design_view",
                "maestro_view",
                "test_name",
                "corner",
            ]
            for index, testbench in enumerate(testbenches):
                if not isinstance(testbench, dict):
                    issues.append(f"Maestro Source.testbenches[{index}] must be a YAML mapping")
                    continue
                for field in required_testbench_fields:
                    if field not in testbench:
                        issues.append(f"Maestro Source.testbenches[{index}].{field} is required")
    else:
        for field in [
            "maestro_point_root",
            "virtuoso_library",
            "cell",
            "design_view",
            "maestro_view",
            "test_name",
            "corner",
        ]:
            if field not in maestro:
                issues.append(f"Maestro Source.{field} is required")
    for section in ("Design Variables", "Metrics", "Constraints"):
        if not isinstance(sections.get(section), list):
            issues.append(f"{section} must be a YAML list")
    return issues


def _metric_payload(metric: dict[str, Any]) -> dict[str, Any]:
    expression = metric["ocean_expression"]
    name = metric["name"]
    ocean = {
        "expression": expression,
        "expression_source": "user_approved",
        "source_reference": f"opt_requirement.md:{name}",
        "expected_value_type": "real_scalar",
        "nil_policy": "fail",
        "non_finite_policy": "fail",
    }
    if metric.get("result"):
        ocean["result"] = metric["result"]
    payload = {
        "name": name,
        "unit": metric["unit"],
        "maestro_formula": expression,
        "required_signals": metric.get("required_signals", []),
        "ocean": ocean,
    }
    if metric.get("testbench"):
        payload["testbench"] = metric["testbench"]
    return payload


def _validate_config_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    for file_name, model in CONFIG_FILE_MODELS.items():
        model.model_validate(payloads[file_name])
    optional_models: dict[str, BaseModel] = {}
    for file_name, model in OPTIONAL_CONFIG_FILE_MODELS.items():
        if file_name in payloads:
            optional_models[file_name] = model.model_validate(payloads[file_name])
    if "testbenches.yaml" in optional_models:
        _validate_metric_testbench_routes(
            MetricsConfig.model_validate(payloads["metrics.yaml"]),
            _cast_config(TestbenchesConfig, optional_models["testbenches.yaml"]),
        )


def _testbench_sources(maestro: dict[str, Any]) -> list[dict[str, Any]]:
    if "testbenches" not in maestro:
        return [maestro]
    payload = maestro["testbenches"]
    if not isinstance(payload, list):
        raise TypeError("Maestro Source.testbenches must be a YAML list")
    return payload


def _primary_maestro_point_root(sections: dict[str, Any]) -> str:
    maestro = _dict_section(sections, "Maestro Source")
    return str(_testbench_sources(maestro)[0]["maestro_point_root"])


def _maestro_point_roots(sections: dict[str, Any]) -> list[str]:
    maestro = sections.get("Maestro Source")
    if not isinstance(maestro, dict):
        return []
    try:
        return [str(testbench["maestro_point_root"]) for testbench in _testbench_sources(maestro)]
    except (KeyError, TypeError):
        return []


def _validate_metric_testbench_routes(
    metrics_config: MetricsConfig,
    testbenches_config: TestbenchesConfig,
) -> None:
    declared_testbenches = {testbench.id for testbench in testbenches_config.testbenches}
    for metric in metrics_config.metrics:
        if metric.testbench is None:
            raise ValueError(
                f"metric {metric.name} must declare testbench when Maestro Source.testbenches is used"
            )
        if metric.testbench not in declared_testbenches:
            raise ValueError(
                f"metric {metric.name} references unknown testbench {metric.testbench}"
            )


def _cast_config(model_type: type[Any], model: BaseModel) -> Any:
    if not isinstance(model, model_type):
        raise TypeError(f"expected {model_type.__name__}, got {type(model).__name__}")
    return model


def _maestro_history_root(maestro_point_root: Path) -> Path:
    parent = maestro_point_root.parent
    if parent.name in {"1", "psf"}:
        return parent.parent
    return maestro_point_root


def _collect_import_entries(
    allowed_root: Path,
    netlist_root: Path,
) -> tuple[list[tuple[Path, Path, bool]], list[str]]:
    entries: list[tuple[Path, Path, bool]] = []
    issues: list[str] = []
    resolved_root = allowed_root.resolve()
    for path in sorted(netlist_root.rglob("*")):
        relative = path.relative_to(netlist_root)
        if path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink():
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                issues.append(f"symlink target escapes Maestro point root: {relative}")
                continue
            if not resolved.is_file():
                issues.append(f"symlink target is not a regular file: {relative}")
                continue
            entries.append((resolved, relative, True))
            continue
        if path.is_file():
            entries.append((path, relative, False))
            continue
        issues.append(f"netlist entry is not a regular file: {relative}")
    return entries, issues


def _write_requirement_report(
    project_dir: Path,
    report: RequirementIntakeReport,
) -> None:
    path = project_dir / "reports" / "requirement_intake_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "status": report.status,
        "issues": report.issues,
        "structured_issues": [diagnostic.model_dump() for diagnostic in report.structured_issues],
        "sections": sorted(report.sections),
        "constraints_md_present": report.constraints_md_present,
        "constraints_md_sha256": report.constraints_md_sha256,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_import_report(path: Path, report: MaestroPointImportReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "status": report.status,
        "issues": report.issues,
        "maestro_point_root": report.maestro_point_root,
        "copied_file_count": report.copied_file_count,
        "materialized_symlink_count": report.materialized_symlink_count,
        "input_scs_sha256": report.input_scs_sha256,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dict_section(sections: dict[str, Any], name: str) -> dict[str, Any]:
    payload = sections[name]
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must be a YAML mapping")
    return payload


def _list_section(sections: dict[str, Any], name: str) -> list[dict[str, Any]]:
    payload = sections[name]
    if not isinstance(payload, list):
        raise TypeError(f"{name} must be a YAML list")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
