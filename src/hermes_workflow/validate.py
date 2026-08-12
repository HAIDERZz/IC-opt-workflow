from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from hermes_workflow.schemas import (
    HistoryWarmStartConfig,
    MetricsConfig,
    OptimizerAlgorithm,
    OptimizerConfig,
    ProcessCornerConfig,
    ProjectConfig,
    SpectreConfig,
    TestbenchesConfig,
    VariableKind,
    VariablesConfig,
)
from hermes_workflow.fix_run_models import (
    FixedPointsConfig,
    WaveformExportsConfig,
    WorkflowSettings,
    fix_run_id_range_issue,
)
from hermes_workflow.candidate_contract import (
    assert_candidate_parameters_match_variables,
)
from hermes_workflow.measurement_routes import measurement_route_issues
from hermes_workflow.objective_contract import (
    evaluate_objective_expression,
    objective_expression_issues,
)
from hermes_workflow.requirement_semantics import parse_constraint_threshold
from hermes_workflow.optimizer_strategy import (
    OptimizerStrategyRequest,
    resolve_optimizer_strategy,
)


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "project_config.yaml": ProjectConfig,
    "variables.yaml": VariablesConfig,
    "spectre.yaml": SpectreConfig,
}
OPTIMIZER_REQUIRED_CONFIGS: tuple[str, ...] = (
    "metrics.yaml",
    "optimizer.yaml",
)
FIX_RUN_REQUIRED_CONFIGS: tuple[str, ...] = (
    "fixed_points.yaml",
)
# Fix-run also requires at least one of these; checked separately.
FIX_RUN_ONE_OF_CONFIGS: tuple[str, ...] = (
    "metrics.yaml",
    "waveform_exports.yaml",
)
OPTIONAL_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "workflow.yaml": WorkflowSettings,
    "fixed_points.yaml": FixedPointsConfig,
    "metrics.yaml": MetricsConfig,
    "optimizer.yaml": OptimizerConfig,
    "testbenches.yaml": TestbenchesConfig,
    "process_corners.yaml": ProcessCornerConfig,
    "waveform_exports.yaml": WaveformExportsConfig,
    "history_warm_start.yaml": HistoryWarmStartConfig,
}

INTEGER_RE = re.compile(r"^[+-]?\d+$")
CONTINUOUS_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s*(?P<unit>\S+))?\s*$"
)

@dataclass(frozen=True)
class ValidationIssue:
    file: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.issues

    def format(self) -> str:
        if self.ok:
            return "validation passed"
        return "\n".join(
            f"{issue.file}:{issue.path}: {issue.message}" for issue in self.issues
        )


@dataclass(frozen=True)
class ContractBundle:
    project_dir: Path
    project_config: ProjectConfig
    testbenches: TestbenchesConfig | None
    process_corners: ProcessCornerConfig | None
    variables: VariablesConfig
    metrics: MetricsConfig | None
    spectre: SpectreConfig
    optimizer: OptimizerConfig | None
    workflow: WorkflowSettings | None = None
    fixed_points: FixedPointsConfig | None = None
    waveform_exports: WaveformExportsConfig | None = None
    history_warm_start: HistoryWarmStartConfig | None = None


def require_optimize_bundle(
    bundle: ContractBundle,
    *,
    operation: str = "optimizer execution",
) -> ContractBundle:
    """Require a complete optimize-mode contract at public optimizer seams."""
    workflow_mode = bundle.workflow.mode if bundle.workflow is not None else "optimize"
    if (
        workflow_mode != "optimize"
        or bundle.optimizer is None
        or bundle.metrics is None
        or bundle.metrics.objective is None
    ):
        raise ValueError(f"{operation} requires optimize workflow")
    return bundle


def validate_project_files(
    project_dir: Path,
    *,
    model_file_is_readable: Callable[[str], bool] | None = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    loaded = _load_config_models(project_dir, issues)
    bundle = _bundle_from_loaded(project_dir, loaded)
    if bundle is not None:
        issues.extend(
            _validate_contract_bundle(
                bundle,
                model_file_is_readable=model_file_is_readable,
            )
        )
    return ValidationReport(issues)


def assert_valid_project(
    project_dir: Path,
    *,
    model_file_is_readable: Callable[[str], bool] | None = None,
) -> ContractBundle:
    report = validate_project_files(
        project_dir,
        model_file_is_readable=model_file_is_readable,
    )
    if not report.ok:
        raise ValueError(report.format())
    return load_contract_bundle(project_dir)


def load_contract_bundle(project_dir: Path) -> ContractBundle:
    issues: list[ValidationIssue] = []
    loaded = _load_config_models(project_dir, issues)
    bundle = _bundle_from_loaded(project_dir, loaded)
    if issues or bundle is None:
        raise ValueError(ValidationReport(issues).format())
    return bundle


def _load_config_models(
    project_dir: Path, issues: list[ValidationIssue]
) -> dict[str, BaseModel]:
    loaded: dict[str, BaseModel] = {}
    config_dir = project_dir / "config"
    workflow_mode = _detect_workflow_mode(config_dir)
    if not (config_dir / "workflow.yaml").exists() and (
        config_dir / "fixed_points.yaml"
    ).exists():
        issues.append(
            ValidationIssue(
                file="config/workflow.yaml",
                path="",
                message=(
                    "workflow.yaml is required when fixed_points.yaml is present"
                ),
            )
        )

    for file_name, model in CONFIG_MODELS.items():
        config_path = config_dir / file_name
        if not config_path.exists():
            issues.append(
                ValidationIssue(
                    file=_display_file(project_dir, config_path),
                    path="",
                    message="required config file is missing",
                )
            )
            continue

        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            issues.append(
                ValidationIssue(
                    file=_display_file(project_dir, config_path),
                    path="",
                    message=f"invalid YAML: {exc}",
                )
            )
            continue

        try:
            loaded[file_name] = model.model_validate(payload)
        except ValidationError as exc:
            issues.extend(_validation_error_issues(project_dir, config_path, exc))
            continue
    # Mode-specific required configs.
    mode_required = (
        FIX_RUN_REQUIRED_CONFIGS
        if workflow_mode == "fix_run"
        else OPTIMIZER_REQUIRED_CONFIGS
    )
    for file_name in mode_required:
        config_path = config_dir / file_name
        if not config_path.exists():
            issues.append(
                ValidationIssue(
                    file=_display_file(project_dir, config_path),
                    path="",
                    message="required config file is missing",
                )
            )
    if workflow_mode == "fix_run":
        if not any(
            (config_dir / file_name).exists()
            for file_name in FIX_RUN_ONE_OF_CONFIGS
        ):
            issues.append(
                ValidationIssue(
                    file="config/metrics.yaml or config/waveform_exports.yaml",
                    path="",
                    message=(
                        "fix-run requires at least one of metrics.yaml or "
                        "waveform_exports.yaml"
                    ),
                )
            )

    for file_name, model in OPTIONAL_CONFIG_MODELS.items():
        config_path = config_dir / file_name
        if not config_path.exists():
            continue
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            issues.append(
                ValidationIssue(
                    file=_display_file(project_dir, config_path),
                    path="",
                    message=f"invalid YAML: {exc}",
                )
            )
            continue

        try:
            loaded[file_name] = model.model_validate(payload)
        except ValidationError as exc:
            issues.extend(_validation_error_issues(project_dir, config_path, exc))
            continue
        if (
            file_name == "metrics.yaml"
            and workflow_mode != "fix_run"
            and isinstance(loaded[file_name], MetricsConfig)
            and loaded[file_name].objective is None
        ):
            issues.append(
                ValidationIssue(
                    file=_display_file(project_dir, config_path),
                    path="objective",
                    message="required field is missing for optimize workflow",
                )
            )

    issues.extend(
        _config_mode_applicability_issues(
            project_dir=project_dir,
            config_dir=config_dir,
            workflow_mode=workflow_mode,
        )
    )

    return loaded


def _bundle_from_loaded(
    project_dir: Path, loaded: dict[str, BaseModel]
) -> ContractBundle | None:
    if not set(CONFIG_MODELS).issubset(loaded):
        return None

    return ContractBundle(
        project_dir=project_dir,
        project_config=_cast_model(ProjectConfig, loaded["project_config.yaml"]),
        testbenches=(
            _cast_model(TestbenchesConfig, loaded["testbenches.yaml"])
            if "testbenches.yaml" in loaded
            else None
        ),
        process_corners=(
            _cast_model(ProcessCornerConfig, loaded["process_corners.yaml"])
            if "process_corners.yaml" in loaded
            else None
        ),
        variables=_cast_model(VariablesConfig, loaded["variables.yaml"]),
        metrics=(
            _cast_model(MetricsConfig, loaded["metrics.yaml"])
            if "metrics.yaml" in loaded
            else None
        ),
        spectre=_cast_model(SpectreConfig, loaded["spectre.yaml"]),
        optimizer=(
            _cast_model(OptimizerConfig, loaded["optimizer.yaml"])
            if "optimizer.yaml" in loaded
            else None
        ),
        workflow=(
            _cast_model(WorkflowSettings, loaded["workflow.yaml"])
            if "workflow.yaml" in loaded
            else None
        ),
        fixed_points=(
            _cast_model(FixedPointsConfig, loaded["fixed_points.yaml"])
            if "fixed_points.yaml" in loaded
            else None
        ),
        waveform_exports=(
            _cast_model(WaveformExportsConfig, loaded["waveform_exports.yaml"])
            if "waveform_exports.yaml" in loaded
            else None
        ),
        history_warm_start=(
            _cast_model(HistoryWarmStartConfig, loaded["history_warm_start.yaml"])
            if "history_warm_start.yaml" in loaded
            else None
        ),
    )


def _validate_contract_bundle(
    bundle: ContractBundle,
    *,
    model_file_is_readable: Callable[[str], bool] | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_netlist_paths(bundle.project_config))
    if bundle.process_corners is not None:
        for index, corner in enumerate(bundle.process_corners.corners):
            if (
                corner.model_file is not None
                and model_file_is_readable is not None
                and not model_file_is_readable(corner.model_file)
            ):
                issues.append(
                    _issue(
                        "process_corners.yaml",
                        f"corners[{index}].model_file",
                        f"model_file is missing or unreadable: {corner.model_file}",
                    )
                )
    issues.extend(variable_contract_issues(bundle.variables))
    if bundle.metrics is not None:
        issues.extend(_validate_metrics(bundle.metrics))
        if bundle.metrics.objective is not None:
            issues.extend(_validate_objective_expression(bundle.metrics))
    for route_issue in measurement_route_issues(
        metrics=bundle.metrics,
        waveform_exports=bundle.waveform_exports,
        testbenches=bundle.testbenches,
    ):
        issues.append(
            _issue(route_issue.file, route_issue.path, route_issue.message)
        )
    if bundle.fixed_points is not None:
        for index, point in enumerate(bundle.fixed_points.points):
            try:
                assert_candidate_parameters_match_variables(
                    bundle.variables,
                    point.parameters,
                )
            except ValueError as exc:
                issues.append(
                    _issue(
                        "fixed_points.yaml",
                        f"points[{index}].parameters",
                        str(exc),
                    )
                )
    range_issue = fix_run_id_range_issue(bundle.workflow, bundle.fixed_points)
    if range_issue is not None:
        issues.append(_issue("workflow.yaml", "starting_run_id", range_issue))
    if bundle.workflow is not None and bundle.workflow.mode == "fix_run":
        if bundle.metrics is not None and bundle.metrics.objective is not None:
            issues.append(
                _issue(
                    "metrics.yaml",
                    "objective",
                    "objective is not supported for fix_run workflow",
                )
            )
        if bundle.metrics is not None and bundle.metrics.constraints:
            issues.append(
                _issue(
                    "metrics.yaml",
                    "constraints",
                    "constraints are not supported for fix_run workflow",
                )
            )
        if bundle.process_corners is not None:
            if bundle.process_corners.objective_policy != "nominal":
                issues.append(
                    _issue(
                        "process_corners.yaml",
                        "objective_policy",
                        "objective_policy must be nominal for fix_run workflow",
                    )
                )
            if bundle.process_corners.constraint_policy != "nominal":
                issues.append(
                    _issue(
                        "process_corners.yaml",
                        "constraint_policy",
                        "constraint_policy must be nominal for fix_run workflow",
                    )
                )
    elif bundle.process_corners is not None:
        corner_ids = {corner.id for corner in bundle.process_corners.corners}
        if (
            bundle.process_corners.objective_policy == "nominal"
            or bundle.process_corners.constraint_policy == "nominal"
        ) and "nominal" not in corner_ids:
            issues.append(
                _issue(
                    "process_corners.yaml",
                    "corners",
                    "nominal policy requires a corner with id 'nominal'",
                )
            )
    if bundle.optimizer is not None:
        issues.extend(
            optimizer_contract_issues(
                optimizer_config=bundle.optimizer,
                spectre_config=bundle.spectre,
                variable_count=len(bundle.variables.variables),
            )
        )
    warm_start_issue = history_warm_start_backend_issue(
        optimizer=bundle.optimizer,
        history_warm_start=bundle.history_warm_start,
        variable_count=len(bundle.variables.variables),
    )
    if warm_start_issue is not None:
        issues.append(
            _issue(
                "history_warm_start.yaml",
                "history_warm_start.enabled",
                warm_start_issue,
            )
        )
    return issues


def local_model_file_is_readable(path: str) -> bool:
    model_file = Path(path).expanduser()
    return model_file.is_file() and os.access(model_file, os.R_OK)


def history_warm_start_backend_issue(
    *,
    optimizer: OptimizerConfig | None,
    history_warm_start: HistoryWarmStartConfig | None,
    variable_count: int,
) -> str | None:
    """Return the capability-contract issue for an enabled warm start.

    Strategy resolution is centralized in ``optimizer_strategy``; this keeps
    intake and on-disk project validation aligned when defaults or explicit
    strategies select the native TuRBO backend.
    """
    if (
        history_warm_start is None
        or not history_warm_start.history_warm_start.enabled
    ):
        return None

    if optimizer is None:
        return (
            "history_warm_start.enabled=true is only supported for optimize "
            "workflow"
        )

    settings = optimizer.optimizer
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=settings.algorithm,
            strategy=settings.strategy,
            openbox=settings.openbox,
            turbo=settings.turbo,
            variable_count=max(variable_count, 1),
        )
    )
    if resolved.backend == "openbox":
        return None
    return (
        "history_warm_start.enabled=true requires the OpenBox optimizer backend; "
        f"resolved backend is {resolved.backend}"
    )


def _validate_netlist_paths(project_config: ProjectConfig) -> list[ValidationIssue]:
    netlist = project_config.netlist
    checks = [
        (
            "exported_input_scs",
            netlist.exported_input_scs,
            PurePosixPath("netlists/exported"),
        ),
        ("template_scs", netlist.template_scs, PurePosixPath("netlists/templates")),
    ]
    issues: list[ValidationIssue] = []

    for field_name, value, expected_parent in checks:
        path = PurePosixPath(value)
        issue_path = f"netlist.{field_name}"
        if Path(value).is_absolute():
            issues.append(
                _issue(
                    "project_config.yaml",
                    issue_path,
                    f"{issue_path} must be relative",
                )
            )
        if ".." in path.parts:
            issues.append(
                _issue(
                    "project_config.yaml",
                    issue_path,
                    f"{issue_path} must not contain ..",
                )
            )
        if not path.is_relative_to(expected_parent):
            issues.append(
                _issue(
                    "project_config.yaml",
                    issue_path,
                    f"{issue_path} must stay under {expected_parent}/",
                )
            )

    return issues


def variable_contract_issues(
    variables_config: VariablesConfig,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, variable in enumerate(variables_config.variables):
        path = f"variables[{index}]"
        if variable.kind == VariableKind.INTEGER or variable.kind == "integer":
            issues.extend(
                _validate_integer_variable(
                    variable.name,
                    variable.lower,
                    variable.upper,
                    variable.step,
                    path,
                )
            )
            continue

        if (
            variable.kind == VariableKind.CONTINUOUS_STEP
            or variable.kind == "continuous_step"
        ):
            issues.extend(
                _validate_continuous_variable(
                    variable.name,
                    variable.lower,
                    variable.upper,
                    variable.step,
                    path,
                )
            )

    return issues


def _validate_integer_variable(
    name: str, lower_raw: str, upper_raw: str, step_raw: str, path: str
) -> list[ValidationIssue]:
    parsed: list[int] = []
    issues: list[ValidationIssue] = []
    for field_name, raw in (
        ("lower", lower_raw),
        ("upper", upper_raw),
        ("step", step_raw),
    ):
        if not INTEGER_RE.match(raw):
            issues.append(
                _issue(
                    "variables.yaml",
                    f"{path}.{field_name}",
                    f"{name} {field_name} must be an integer without units",
                )
            )
        else:
            parsed.append(int(raw))

    if issues:
        return issues

    lower, upper, step = parsed
    if step <= 0:
        issues.append(
            _issue("variables.yaml", f"{path}.step", f"{name} step must be positive")
        )
    if lower > upper:
        issues.append(_issue("variables.yaml", path, f"{name} lower must be <= upper"))
    if step > 0 and lower <= upper and (upper - lower) % step != 0:
        issues.append(
            _issue("variables.yaml", path, f"{name} range must be divisible by step")
        )
    return issues


def _validate_continuous_variable(
    name: str, lower_raw: str, upper_raw: str, step_raw: str, path: str
) -> list[ValidationIssue]:
    parsed: list[tuple[Decimal, str]] = []
    issues: list[ValidationIssue] = []
    for field_name, raw in (
        ("lower", lower_raw),
        ("upper", upper_raw),
        ("step", step_raw),
    ):
        value = _parse_continuous(raw)
        if value is None:
            issues.append(
                _issue(
                    "variables.yaml",
                    f"{path}.{field_name}",
                    f"{name} {field_name} must be numeric with an optional unit suffix",
                )
            )
        else:
            if _has_whitespace_unit_suffix(raw):
                issues.append(
                    _issue(
                        "variables.yaml",
                        f"{path}.{field_name}",
                        (
                            f"{name} {field_name} must use a Spectre-safe "
                            "attached unit suffix such as 0.3u, not 0.3 um"
                        ),
                    )
                )
            parsed.append(value)

    if issues:
        return issues

    (lower, lower_unit), (upper, upper_unit), (step, step_unit) = parsed
    if len({lower_unit, upper_unit, step_unit}) != 1:
        issues.append(
            _issue(
                "variables.yaml",
                path,
                f"{name} lower, upper, and step unit suffixes must match",
            )
        )
    if step <= 0:
        issues.append(
            _issue("variables.yaml", f"{path}.step", f"{name} step must be positive")
        )
    if lower > upper:
        issues.append(_issue("variables.yaml", path, f"{name} lower must be <= upper"))
    # Continuous candidates are generated as lower + k * step <= upper; upper may
    # be off-grid, unlike integer ranges where exact divisibility is required.
    return issues


def _parse_continuous(raw: str) -> tuple[Decimal, str] | None:
    match = CONTINUOUS_RE.match(raw)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value"))
    except InvalidOperation:
        return None
    return value, match.group("unit") or ""


def _has_whitespace_unit_suffix(raw: str) -> bool:
    match = CONTINUOUS_RE.match(raw)
    if match is None or match.group("unit") is None:
        return False
    return match.start("unit") > match.end("value")


def _validate_metrics(
    metrics_config: MetricsConfig,
) -> list[ValidationIssue]:
    metrics_by_name = {metric.name: metric for metric in metrics_config.metrics}
    issues: list[ValidationIssue] = []
    for index, constraint in enumerate(metrics_config.constraints):
        metric = metrics_by_name.get(constraint.metric)
        if metric is None:
            issues.append(
                _issue(
                    "metrics.yaml",
                    f"constraints[{index}].metric",
                    f"constraint references unknown metric {constraint.metric}",
                )
            )
            continue
        try:
            parse_constraint_threshold(constraint.value, metric.unit)
        except ValueError as exc:
            issues.append(
                _issue(
                    "metrics.yaml",
                    f"constraints[{index}].value",
                    str(exc),
                )
            )
    return issues


def _validate_objective_expression(
    metrics_config: MetricsConfig,
) -> list[ValidationIssue]:
    if metrics_config.objective is None:
        return []
    declared_metrics = {metric.name for metric in metrics_config.metrics}
    return [
        _issue("metrics.yaml", "objective.expression", message)
        for message in objective_expression_issues(
            metrics_config.objective.expression,
            declared_metrics,
        )
    ]


def evaluate_objective(expression: str, metrics: dict[str, float]) -> float:
    """Evaluate using the same objective contract enforced by both validators."""
    return evaluate_objective_expression(expression, metrics)


def optimizer_contract_issues(
    *,
    optimizer_config: OptimizerConfig,
    spectre_config: SpectreConfig,
    variable_count: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    optimizer = optimizer_config.optimizer
    spectre = spectre_config.spectre

    try:
        resolve_optimizer_strategy(
            OptimizerStrategyRequest(
                algorithm=optimizer.algorithm,
                strategy=optimizer.strategy,
                openbox=optimizer.openbox,
                turbo=optimizer.turbo,
                variable_count=max(variable_count, 1),
            )
        )
    except ValueError as exc:
        issues.append(
            _issue(
                "optimizer.yaml",
                "optimizer.strategy",
                str(exc),
            )
        )

    if optimizer.batch_size > spectre.parallel_jobs:
        issues.append(
            _issue(
                "optimizer.yaml",
                "optimizer.batch_size",
                "optimizer.batch_size must be <= spectre.parallel_jobs",
            )
        )

    if (
        optimizer.algorithm == OptimizerAlgorithm.TURBO
        or optimizer.algorithm == "turbo"
    ) and optimizer.max_evaluations < 2 * variable_count:
        issues.append(
            _issue(
                "optimizer.yaml",
                "optimizer.max_evaluations",
                "optimizer.max_evaluations must be >= 2 * number_of_variables",
            )
        )

    return issues


def _validation_error_issues(
    project_dir: Path, config_path: Path, exc: ValidationError
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            file=_display_file(project_dir, config_path),
            path=".".join(str(part) for part in error["loc"]),
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]


def _issue(file_name: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(file=f"config/{file_name}", path=path, message=message)


def _display_file(project_dir: Path, config_path: Path) -> str:
    try:
        return config_path.relative_to(project_dir).as_posix()
    except ValueError:
        return config_path.as_posix()


def _config_mode_applicability_issues(
    *, project_dir: Path, config_dir: Path, workflow_mode: str
) -> list[ValidationIssue]:
    if workflow_mode == "fix_run":
        unsupported = ("optimizer.yaml", "history_warm_start.yaml")
    else:
        unsupported = ("fixed_points.yaml", "waveform_exports.yaml")

    issues: list[ValidationIssue] = []
    for file_name in unsupported:
        config_path = config_dir / file_name
        if not config_path.exists():
            continue
        issues.append(
            ValidationIssue(
                file=_display_file(project_dir, config_path),
                path="",
                message=(
                    f"{file_name} is not supported for {workflow_mode} workflow"
                ),
            )
        )
    return issues


def _detect_workflow_mode(config_dir: Path) -> str:
    """Detect workflow mode from config/workflow.yaml.

    A missing or invalid workflow file never infers ``fix_run`` from another
    config file. Those inputs are validated separately; mode selection remains
    ``optimize`` until a supported explicit mode is present.
    """
    workflow_path = config_dir / "workflow.yaml"
    if workflow_path.exists():
        try:
            payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return "optimize"
        if isinstance(payload, dict):
            mode = payload.get("mode")
            if mode in {"optimize", "fix_run"}:
                return mode
    return "optimize"


def _cast_model(model_type: type[Any], model: BaseModel) -> Any:
    if not isinstance(model, model_type):
        raise TypeError(f"expected {model_type.__name__}, got {type(model).__name__}")
    return model
