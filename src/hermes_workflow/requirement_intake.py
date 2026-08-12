from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from hermes_workflow.candidate_contract import (
    assert_candidate_parameters_match_variables,
)
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.schemas import (
    HistoryWarmStartConfig,
    MetricsConfig,
    NamedTestbenchConfig,
    NonEmptyStr,
    OptimizerConfig,
    ProcessCornerConfig,
    ProjectConfig,
    SpectreConfig,
    StrictModel,
    TestbenchConfig,
    TestbenchesConfig,
    VariablesConfig,
    validate_name,
)
from hermes_workflow.fix_run_models import (
    FixedPointsConfig,
    WaveformExportsConfig,
    WorkflowSettings,
    fix_run_id_range_issue,
)
from hermes_workflow.measurement_routes import measurement_route_issues
from hermes_workflow.requirement_semantics import validate_requirement_semantics
from hermes_workflow.diagnostics import Diagnostic, DiagnosticSeverity
from hermes_workflow.validate import (
    history_warm_start_backend_issue,
    local_model_file_is_readable,
    optimizer_contract_issues,
    variable_contract_issues,
)

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
    "Workflow",
    "History Warm Start",
]
FIX_RUN_OPTIONAL_SECTIONS = [
    "Process Corners",
    "Metrics",
    "Waveform Exports",
]
FIX_RUN_REQUIRED_SECTIONS = [
    "Workflow",
    "Project",
    "Maestro Source",
    "Design Variables",
    "Spectre Settings",
    "Fixed Points",
    "Approval Checklist",
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
    "fixed_points.yaml": FixedPointsConfig,
    "waveform_exports.yaml": WaveformExportsConfig,
    "history_warm_start.yaml": HistoryWarmStartConfig,
}
MANAGED_CONFIG_FILES = frozenset(
    {
        *CONFIG_FILE_MODELS,
        *OPTIONAL_CONFIG_FILE_MODELS,
        "workflow.yaml",
    }
)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


class _RequirementProject(StrictModel):
    project_name: str
    description: str = ""
    backend: Literal["maestro_exported_spectre_deck"]

    @field_validator("project_name")
    @classmethod
    def _project_name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "project_name")


class _RequirementMetric(StrictModel):
    name: str
    unit: NonEmptyStr
    ocean_expression: NonEmptyStr
    testbench: str | None = None
    result: NonEmptyStr | None = None
    required_signals: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "metric name")

    @field_validator("testbench")
    @classmethod
    def _testbench_is_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_name(value, "metric testbench")


class _RequirementMaestroPoint(TestbenchConfig):
    maestro_point_root: NonEmptyStr


class _RequirementMaestroCollection(StrictModel):
    testbenches: list[NamedTestbenchConfig] = Field(min_length=1)


class _RequirementApprovalChecklist(StrictModel):
    metric_formulas_user_approved: Literal[True]
    maestro_source_user_approved: Literal[True]
    variable_bounds_user_approved: Literal[True]
    spectre_resource_settings_user_approved: Literal[True]


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
    workflow_mode: str = "optimize"


@dataclass(frozen=True)
class MaestroPointImportReport:
    status: str
    issues: list[str]
    maestro_point_root: str
    copied_file_count: int
    materialized_symlink_count: int
    input_scs_sha256: str | None


@dataclass(frozen=True)
class _ImportCollection:
    files: list[tuple[Path, Path]]
    directories: list[Path]
    materialized_symlink_count: int
    issues: list[str]


@dataclass(frozen=True)
class RequirementPreparationReport:
    status: str
    issues: list[str]


def check_requirement(
    project_dir: str | Path,
    *,
    maestro_input_exists: Callable[[str], bool] | None = None,
    model_file_is_readable: Callable[[str], bool] | None = None,
) -> RequirementIntakeReport:
    project_root = Path(project_dir)
    report = _parse_and_validate_requirement(
        project_root,
        maestro_input_exists=maestro_input_exists,
        model_file_is_readable=model_file_is_readable,
    )
    _write_requirement_report(project_root, report)
    return report


def prepare_from_requirement(project_dir: str | Path) -> RequirementPreparationReport:
    project_root = Path(project_dir)
    intake = check_requirement(project_root)
    if intake.status != "pass":
        return RequirementPreparationReport(status="fail", issues=intake.issues)

    config_payloads = render_config_payloads(intake.sections, workflow_mode=intake.workflow_mode)
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


def render_config_payloads(sections: dict[str, Any], *, workflow_mode: str = "optimize") -> dict[str, dict[str, Any]]:
    if workflow_mode not in {"optimize", "fix_run"}:
        raise ValueError(f"unsupported workflow_mode: {workflow_mode!r}")
    project = _dict_section(sections, "Project")
    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    primary_testbench = testbenches[0]
    variables = _list_section(sections, "Design Variables")
    spectre = _dict_section(sections, "Spectre Settings")

    payloads: dict[str, dict[str, Any]] = {
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
        "spectre.yaml": {
            "schema_version": "1.0",
            "spectre": spectre,
        },
    }

    if workflow_mode == "fix_run":
        # fix_run: render workflow.yaml, fixed_points.yaml,
        # waveform_exports.yaml (if present), metrics.yaml (if Metrics
        # present), process_corners.yaml. Do NOT render optimizer.yaml.
        workflow = _dict_section(sections, "Workflow")
        payloads["workflow.yaml"] = workflow

        fixed_points = _dict_section(sections, "Fixed Points")
        payloads["fixed_points.yaml"] = fixed_points

        if "Waveform Exports" in sections:
            waveform_exports = _dict_section(sections, "Waveform Exports")
            payloads["waveform_exports.yaml"] = waveform_exports

        if "Metrics" in sections:
            metrics = _list_section(sections, "Metrics")
            constraints = _list_section(sections, "Constraints") if "Constraints" in sections else []
            metrics_payload: dict[str, Any] = {
                "schema_version": "1.0",
                "metrics": [_metric_payload(metric) for metric in metrics],
                "constraints": constraints,
            }
            if "Objective" in sections:
                metrics_payload["objective"] = _dict_section(sections, "Objective")
            payloads["metrics.yaml"] = metrics_payload
    else:
        # optimize mode: existing behavior
        metrics = _list_section(sections, "Metrics")
        constraints = _list_section(sections, "Constraints")
        objective = _dict_section(sections, "Objective")
        optimizer = _dict_section(sections, "Optimizer Settings")

        payloads["metrics.yaml"] = {
            "schema_version": "1.0",
            "metrics": [_metric_payload(metric) for metric in metrics],
            "constraints": constraints,
            "objective": objective,
        }
        payloads["optimizer.yaml"] = {
            "schema_version": "1.0",
            "optimizer": optimizer,
        }
        if "History Warm Start" in sections:
            payloads["history_warm_start.yaml"] = {
                "schema_version": "1.0",
                "history_warm_start": _dict_section(sections, "History Warm Start"),
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
        corner_policies = (
            {
                "objective_policy": "nominal",
                "constraint_policy": "nominal",
            }
            if workflow_mode == "fix_run"
            else {
                "objective_policy": process_corners.get(
                    "objective_policy", "worst_case"
                ),
                "constraint_policy": process_corners.get(
                    "constraint_policy", "all_corners"
                ),
            }
        )
        payloads["process_corners.yaml"] = {
            "schema_version": "1.0",
            **corner_policies,
            "corners": corners,
        }
    else:
        payloads["process_corners.yaml"] = {
            "schema_version": "1.0",
            "objective_policy": "nominal",
            "constraint_policy": "nominal",
            "corners": [{"id": "nominal"}],
        }
    _validate_config_payloads(payloads, workflow_mode=workflow_mode)
    return payloads


def write_config_payloads(
    project_dir: str | Path,
    payloads: dict[str, dict[str, Any]],
) -> None:
    config_dir = Path(project_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".requirement-config-", dir=config_dir)
    )
    try:
        for file_name, payload in payloads.items():
            (staging_dir / file_name).write_text(
                yaml.safe_dump(payload, sort_keys=False),
                encoding="utf-8",
            )
        for file_name in sorted(payloads):
            (staging_dir / file_name).replace(config_dir / file_name)
        for file_name in sorted(MANAGED_CONFIG_FILES - payloads.keys()):
            stale_path = config_dir / file_name
            if stale_path.exists() or stale_path.is_symlink():
                stale_path.unlink()
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


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

    collection = _ImportCollection(
        files=[],
        directories=[],
        materialized_symlink_count=0,
        issues=[],
    )
    if not issues:
        collection = _collect_import_entries(
            _maestro_history_root(source_root),
            netlist_root,
        )
        issues = collection.issues

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
    for relative in sorted(
        collection.directories,
        key=lambda value: (len(value.parts), value.as_posix()),
    ):
        (staging / relative).mkdir(parents=True, exist_ok=True)
    for source, relative in collection.files:
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)
    input_hash = _sha256(destination / "input.scs")
    report = MaestroPointImportReport(
        status="pass",
        issues=[],
        maestro_point_root=source_root.as_posix(),
        copied_file_count=len(collection.files),
        materialized_symlink_count=collection.materialized_symlink_count,
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
    model_file_is_readable: Callable[[str], bool] = local_model_file_is_readable,
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

    raw_sections, section_issues, section_diagnostics, workflow_mode = _extract_required_sections(
        requirement_text
    )
    issues.extend(section_issues)
    structured_issues.extend(section_diagnostics)
    if not issues:
        for name, raw_section in raw_sections.items():
            payload, payload_issues = _parse_section_yaml(name, raw_section)
            if payload_issues:
                issues.extend(payload_issues)
                structured_issues.extend(
                    _structured_from_issue(name, payload_issue)
                    for payload_issue in payload_issues
                )
            else:
                sections[name] = payload

    if not issues:
        issues.extend(
            _validate_requirement_section_models(
                sections,
                workflow_mode=workflow_mode,
            )
        )

    if not issues:
        issues.extend(_validate_approval_checklist(sections))
        issues.extend(_validate_required_fields(sections, workflow_mode=workflow_mode))
        if not issues:
            semantic_issues = validate_requirement_semantics(sections)
            issues.extend(semantic_issues)
            structured_issues.extend(
                _structured_from_issue(_issue_context(issue), issue)
                for issue in semantic_issues
            )
        if not issues:
            try:
                render_config_payloads(sections, workflow_mode=workflow_mode)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                issues.append(f"rendered config validation failed: {exc}")
        for model_file in _corner_model_files(sections):
            if not model_file_is_readable(model_file):
                issues.append(
                    "Process Corners.model_file is missing or unreadable: "
                    f"{model_file}"
                )
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
        workflow_mode=workflow_mode,
    )


def _validate_requirement_section_models(
    sections: dict[str, Any],
    *,
    workflow_mode: str,
) -> list[str]:
    project = sections.get("Project")
    if project is not None:
        try:
            _RequirementProject.model_validate(project)
        except ValidationError as exc:
            return _section_validation_issues("Project", exc)

    metrics = sections.get("Metrics")
    if metrics is not None:
        try:
            TypeAdapter(list[_RequirementMetric]).validate_python(metrics)
        except ValidationError as exc:
            return _section_validation_issues("Metrics", exc)

    maestro = sections.get("Maestro Source")
    if maestro is not None:
        maestro_model: type[BaseModel] = (
            _RequirementMaestroCollection
            if isinstance(maestro, dict) and "testbenches" in maestro
            else _RequirementMaestroPoint
        )
        try:
            maestro_model.model_validate(maestro)
        except ValidationError as exc:
            return _section_validation_issues("Maestro Source", exc)

    approval = sections.get("Approval Checklist")
    if approval is not None:
        try:
            _RequirementApprovalChecklist.model_validate(approval)
        except ValidationError as exc:
            return _section_validation_issues("Approval Checklist", exc)

    process_corners = sections.get("Process Corners")
    if process_corners is None:
        return []
    if not isinstance(process_corners, dict):
        return ["Process Corners must be a YAML mapping"]
    process_corners_for_validation = process_corners
    if workflow_mode == "fix_run":
        policy_fields = {"objective_policy", "constraint_policy"}
        if policy_fields.intersection(process_corners):
            return [
                "Process Corners aggregation policies are not supported for "
                "fix_run workflow; fix-run executes every declared corner"
            ]
        process_corners_for_validation = {
            "objective_policy": "nominal",
            "constraint_policy": "nominal",
            **process_corners,
        }
    try:
        process_corner_config = ProcessCornerConfig.model_validate(
            {"schema_version": "1.0", **process_corners_for_validation}
        )
    except ValidationError as exc:
        return _section_validation_issues("Process Corners", exc)
    if workflow_mode == "optimize":
        corner_ids = {corner.id for corner in process_corner_config.corners}
        if (
            process_corner_config.objective_policy == "nominal"
            or process_corner_config.constraint_policy == "nominal"
        ) and "nominal" not in corner_ids:
            return [
                "Process Corners nominal policy requires a corner with id 'nominal'"
            ]
    return []


def _parse_and_validate_requirement(
    project_dir: Path,
    *,
    maestro_input_exists: Callable[[str], bool] | None = None,
    model_file_is_readable: Callable[[str], bool] | None = None,
) -> RequirementIntakeReport:
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
        maestro_input_exists=(
            maestro_input_exists
            if maestro_input_exists is not None
            else lambda path: Path(path).expanduser().is_file()
        ),
        model_file_is_readable=(
            model_file_is_readable
            if model_file_is_readable is not None
            else local_model_file_is_readable
        ),
    )


def _extract_required_sections(
    text: str,
) -> tuple[dict[str, str], list[str], list[Diagnostic], str]:
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

    # Detect workflow mode from Workflow section if present
    workflow_mode = "optimize"
    workflow_heading_indices = [
        i for i, (name, _s, _e) in enumerate(headings) if name == "Workflow"
    ]
    if workflow_heading_indices:
        idx = workflow_heading_indices[0]
        content_start = headings[idx][2]
        content_end = (
            headings[idx + 1][1] if idx + 1 < len(headings) else len(text)
        )
        workflow_text = text[content_start:content_end]
        workflow_payload, workflow_issues = _parse_section_yaml("Workflow", workflow_text)
        if workflow_issues:
            issues.extend(workflow_issues)
        else:
            try:
                workflow = WorkflowSettings.model_validate(workflow_payload)
            except ValidationError as exc:
                issues.extend(_section_validation_issues("Workflow", exc))
            else:
                workflow_mode = workflow.mode

    if issues:
        return {}, issues, structured_issues, workflow_mode

    required_sections = (
        FIX_RUN_REQUIRED_SECTIONS if workflow_mode == "fix_run" else REQUIRED_SECTIONS
    )
    optional_sections = (
        FIX_RUN_OPTIONAL_SECTIONS
        if workflow_mode == "fix_run"
        else OPTIONAL_SECTIONS
    )
    known_sections = set(
        REQUIRED_SECTIONS
        + OPTIONAL_SECTIONS
        + FIX_RUN_REQUIRED_SECTIONS
        + FIX_RUN_OPTIONAL_SECTIONS
    )
    allowed_sections = set(required_sections + optional_sections)
    for name, _start, _end in headings:
        if name not in known_sections:
            issues.append(f"unknown requirement section: {name}")
        elif name not in allowed_sections:
            issues.append(
                f"section {name} is not supported for workflow mode {workflow_mode}"
            )

    if issues:
        return {}, issues, structured_issues, workflow_mode

    counts = {name: 0 for name in required_sections}
    for name, _start, _end in headings:
        if name in counts:
            counts[name] += 1
    for name in required_sections:
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
    for name in optional_sections:
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
        return {}, issues, structured_issues, workflow_mode

    sections: dict[str, str] = {}
    for index, (name, _start, content_start) in enumerate(headings):
        if name not in required_sections and name not in optional_sections:
            continue
        content_end = headings[index + 1][1] if index + 1 < len(headings) else len(text)
        sections[name] = text[content_start:content_end]
    return sections, [], structured_issues, workflow_mode


def _section_validation_issues(
    section: str,
    error: ValidationError,
) -> list[str]:
    issues: list[str] = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"])
        message = str(item["msg"])
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        if not location and message.startswith("starting_run_id "):
            issues.append(f"{section}.{message}")
            continue
        path = f"{section}.{location}" if location else section
        issues.append(f"{path}: {message}")
    return issues


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


def _validate_required_fields(sections: dict[str, Any], *, workflow_mode: str = "optimize") -> list[str]:
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

    if workflow_mode == "fix_run" and "History Warm Start" in sections:
        issues.append("History Warm Start is only supported for optimize workflow mode")

    if workflow_mode == "fix_run":
        # Skip Objective, Constraints, Optimizer Settings required-field checks
        required = {
            k: v for k, v in required.items()
            if k not in ("Objective", "Constraints", "Optimizer Settings")
        }

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
    if workflow_mode == "fix_run":
        # Validate Fixed Points section
        fixed_points = sections.get("Fixed Points")
        if isinstance(fixed_points, dict):
            if "points" not in fixed_points or not isinstance(fixed_points["points"], list):
                issues.append("Fixed Points.points is required and must be a list")
            else:
                # Validate parameter names are in Design Variables
                variable_names = {
                    v["name"] for v in sections.get("Design Variables", []) if isinstance(v, dict)
                }
                for point in fixed_points["points"]:
                    if not isinstance(point, dict):
                        continue
                    params = point.get("parameters", {})
                    for param_name in params:
                        if param_name not in variable_names:
                            issues.append(
                                f"Fixed Points parameter '{param_name}' is not a declared Design Variable"
                            )
                    missing = variable_names - set(params.keys())
                    if missing:
                        for missing_name in sorted(missing):
                            issues.append(
                                f"Fixed Points point '{point.get('candidate_id', '?')}' "
                                f"is missing Design Variable '{missing_name}'"
                            )
        # Validate at least one of Metrics or Waveform Exports is present
        has_metrics = "Metrics" in sections
        has_waveform_exports = "Waveform Exports" in sections
        if not has_metrics and not has_waveform_exports:
            issues.append(
                "fix_run mode requires at least one of Metrics or Waveform Exports"
            )
        # Metrics must be a list if present
        if has_metrics and not isinstance(sections.get("Metrics"), list):
            issues.append("Metrics must be a YAML list")
        # Design Variables must be a list
        if not isinstance(sections.get("Design Variables"), list):
            issues.append("Design Variables must be a YAML list")
    else:
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


def _validate_config_payloads(payloads: dict[str, dict[str, Any]], *, workflow_mode: str = "optimize") -> None:
    config_models: dict[str, BaseModel] = {}
    for file_name, model in CONFIG_FILE_MODELS.items():
        if file_name not in payloads:
            continue
        config_models[file_name] = model.model_validate(payloads[file_name])
    optional_models: dict[str, BaseModel] = {}
    for file_name, model in OPTIONAL_CONFIG_FILE_MODELS.items():
        if file_name in payloads:
            optional_models[file_name] = model.model_validate(payloads[file_name])

    fixed_points = optional_models.get("fixed_points.yaml")
    variables_model = config_models.get("variables.yaml")
    if variables_model is not None:
        variable_issues = variable_contract_issues(
            _cast_config(VariablesConfig, variables_model)
        )
        if variable_issues:
            raise ValueError(
                "; ".join(issue.message for issue in variable_issues)
            )
    if fixed_points is not None and variables_model is not None:
        fixed_points_config = _cast_config(FixedPointsConfig, fixed_points)
        variables_config = _cast_config(VariablesConfig, variables_model)
        for point in fixed_points_config.points:
            try:
                assert_candidate_parameters_match_variables(
                    variables_config,
                    point.parameters,
                )
            except ValueError as exc:
                raise ValueError(
                    f"Fixed Points point {point.candidate_id!r}: {exc}"
                ) from exc

    workflow = (
        WorkflowSettings.model_validate(payloads["workflow.yaml"])
        if "workflow.yaml" in payloads
        else None
    )
    fixed_points_config = (
        _cast_config(FixedPointsConfig, fixed_points)
        if fixed_points is not None
        else None
    )
    run_range_issue = fix_run_id_range_issue(workflow, fixed_points_config)
    if run_range_issue is not None:
        raise ValueError(run_range_issue)

    route_issues = measurement_route_issues(
        metrics=(
            MetricsConfig.model_validate(payloads["metrics.yaml"])
            if "metrics.yaml" in payloads
            else None
        ),
        waveform_exports=(
            _cast_config(
                WaveformExportsConfig,
                optional_models["waveform_exports.yaml"],
            )
            if "waveform_exports.yaml" in optional_models
            else None
        ),
        testbenches=(
            _cast_config(TestbenchesConfig, optional_models["testbenches.yaml"])
            if "testbenches.yaml" in optional_models
            else None
        ),
    )
    if route_issues:
        raise ValueError("; ".join(issue.message for issue in route_issues))

    if (
        "optimizer.yaml" in config_models
        and "variables.yaml" in config_models
    ):
        variables = _cast_config(VariablesConfig, config_models["variables.yaml"])
        optimizer = _cast_config(
            OptimizerConfig,
            config_models["optimizer.yaml"],
        )
        optimizer_issues = optimizer_contract_issues(
            optimizer_config=optimizer,
            spectre_config=_cast_config(
                SpectreConfig,
                config_models["spectre.yaml"],
            ),
            variable_count=len(variables.variables),
        )
        if optimizer_issues:
            raise ValueError(
                "; ".join(issue.message for issue in optimizer_issues)
            )
        warm_start = optional_models.get("history_warm_start.yaml")
        issue = history_warm_start_backend_issue(
            optimizer=optimizer,
            history_warm_start=(
                _cast_config(HistoryWarmStartConfig, warm_start)
                if warm_start is not None
                else None
            ),
            variable_count=len(variables.variables),
        )
        if issue is not None:
            raise ValueError(issue)


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


def _corner_model_files(sections: dict[str, Any]) -> list[str]:
    process_corners = sections.get("Process Corners")
    if not isinstance(process_corners, dict):
        return []
    corners = process_corners.get("corners")
    if not isinstance(corners, list):
        return []
    return [
        str(corner["model_file"])
        for corner in corners
        if isinstance(corner, dict) and corner.get("model_file") is not None
    ]


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
) -> _ImportCollection:
    files: list[tuple[Path, Path]] = []
    directories: list[Path] = []
    issues: list[str] = []
    destinations: dict[Path, str] = {}
    materialized_symlink_count = 0

    try:
        resolved_root = allowed_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return _ImportCollection(
            files=[],
            directories=[],
            materialized_symlink_count=0,
            issues=[f"Maestro point root cannot be resolved: {allowed_root}"],
        )

    try:
        resolved_netlist_root = netlist_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return _ImportCollection(
            files=[],
            directories=[],
            materialized_symlink_count=0,
            issues=[f"maestro_point_root/netlist cannot be resolved: {netlist_root}"],
        )

    try:
        resolved_netlist_root.relative_to(resolved_root)
    except ValueError:
        return _ImportCollection(
            files=[],
            directories=[],
            materialized_symlink_count=0,
            issues=["symlink target escapes Maestro point root: ."],
        )

    def display(relative: Path) -> str:
        return relative.as_posix() if relative.parts else "."

    def claim(relative: Path, kind: str) -> bool:
        existing = destinations.get(relative)
        if existing is not None:
            issues.append(f"duplicate import destination: {display(relative)}")
            return False
        destinations[relative] = kind
        return True

    def walk_directory(
        directory: Path,
        relative: Path,
        active_directories: tuple[tuple[int, int], ...],
        *,
        claim_directory: bool,
    ) -> None:
        try:
            stat_result = directory.stat()
        except OSError:
            issues.append(f"netlist directory cannot be traversed: {display(relative)}")
            return
        identity = (stat_result.st_dev, stat_result.st_ino)
        if identity in active_directories:
            issues.append(f"symlink cycle detected: {display(relative)}")
            return
        if claim_directory:
            if not claim(relative, "directory"):
                return
            directories.append(relative)
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            issues.append(f"netlist directory cannot be traversed: {display(relative)}")
            return
        next_active = (*active_directories, identity)
        for child in children:
            walk_node(child, relative / child.name, next_active)

    def walk_node(
        path: Path,
        relative: Path,
        active_directories: tuple[tuple[int, int], ...],
    ) -> None:
        nonlocal materialized_symlink_count
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
            except RuntimeError:
                issues.append(f"symlink cycle detected: {display(relative)}")
                return
            except OSError:
                issues.append(f"symlink target is missing: {display(relative)}")
                return
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                issues.append(
                    f"symlink target escapes Maestro point root: {display(relative)}"
                )
                return
            if resolved.is_file():
                if claim(relative, "file"):
                    files.append((resolved, relative))
                    materialized_symlink_count += 1
                return
            if resolved.is_dir():
                materialized_symlink_count += 1
                walk_directory(
                    resolved,
                    relative,
                    active_directories,
                    claim_directory=True,
                )
                return
            issues.append(
                "symlink target is not a regular file or directory: "
                f"{display(relative)}"
            )
            return
        if path.is_file():
            if claim(relative, "file"):
                files.append((path, relative))
            return
        if path.is_dir():
            walk_directory(
                path,
                relative,
                active_directories,
                claim_directory=True,
            )
            return
        issues.append(
            f"netlist entry is not a regular file or directory: {display(relative)}"
        )

    walk_directory(
        resolved_netlist_root,
        Path(),
        (),
        claim_directory=False,
    )
    return _ImportCollection(
        files=files,
        directories=directories,
        materialized_symlink_count=materialized_symlink_count,
        issues=issues,
    )


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
        "workflow_mode": report.workflow_mode,
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
