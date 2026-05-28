from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from hermes_workflow.schemas import (
    MetricsConfig,
    OptimizerAlgorithm,
    OptimizerConfig,
    ProjectConfig,
    SpectreConfig,
    VariableKind,
    VariablesConfig,
)


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "project_config.yaml": ProjectConfig,
    "variables.yaml": VariablesConfig,
    "metrics.yaml": MetricsConfig,
    "spectre.yaml": SpectreConfig,
    "optimizer.yaml": OptimizerConfig,
}

INTEGER_RE = re.compile(r"^[+-]?\d+$")
CONTINUOUS_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s+(?P<unit>\S+))?\s*$"
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
    variables: VariablesConfig
    metrics: MetricsConfig
    spectre: SpectreConfig
    optimizer: OptimizerConfig


def validate_project_files(project_dir: Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    loaded = _load_config_models(project_dir, issues)
    bundle = _bundle_from_loaded(project_dir, loaded)
    if bundle is not None:
        issues.extend(_validate_contract_bundle(bundle))
    return ValidationReport(issues)


def assert_valid_project(project_dir: Path) -> ContractBundle:
    report = validate_project_files(project_dir)
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

    return loaded


def _bundle_from_loaded(
    project_dir: Path, loaded: dict[str, BaseModel]
) -> ContractBundle | None:
    if set(loaded) != set(CONFIG_MODELS):
        return None

    return ContractBundle(
        project_dir=project_dir,
        project_config=_cast_model(ProjectConfig, loaded["project_config.yaml"]),
        variables=_cast_model(VariablesConfig, loaded["variables.yaml"]),
        metrics=_cast_model(MetricsConfig, loaded["metrics.yaml"]),
        spectre=_cast_model(SpectreConfig, loaded["spectre.yaml"]),
        optimizer=_cast_model(OptimizerConfig, loaded["optimizer.yaml"]),
    )


def _validate_contract_bundle(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_netlist_paths(bundle.project_config))
    issues.extend(_validate_variables(bundle.variables))
    issues.extend(_validate_metrics(bundle.metrics))
    issues.extend(_validate_objective_expression(bundle.metrics))
    issues.extend(_validate_optimizer_contract(bundle))
    return issues


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


def _validate_variables(variables_config: VariablesConfig) -> list[ValidationIssue]:
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


def _validate_metrics(metrics_config: MetricsConfig) -> list[ValidationIssue]:
    declared_metrics = {metric.name for metric in metrics_config.metrics}
    issues: list[ValidationIssue] = []
    for index, constraint in enumerate(metrics_config.constraints):
        if constraint.metric not in declared_metrics:
            issues.append(
                _issue(
                    "metrics.yaml",
                    f"constraints[{index}].metric",
                    f"constraint references unknown metric {constraint.metric}",
                )
            )
    return issues


def _validate_objective_expression(
    metrics_config: MetricsConfig,
) -> list[ValidationIssue]:
    try:
        tree = ast.parse(metrics_config.objective.expression, mode="eval")
    except SyntaxError as exc:
        return [
            _issue(
                "metrics.yaml",
                "objective.expression",
                f"invalid objective expression: {exc.msg}",
            )
        ]

    declared_metrics = {metric.name for metric in metrics_config.metrics}
    issues: list[ValidationIssue] = []
    for node in ast.walk(tree):
        if not _is_allowed_objective_node(node):
            issues.append(
                _issue(
                    "metrics.yaml",
                    "objective.expression",
                    f"unsupported objective expression node {type(node).__name__}",
                )
            )
            continue

        if isinstance(node, ast.Name) and node.id not in declared_metrics:
            issues.append(
                _issue(
                    "metrics.yaml",
                    "objective.expression",
                    f"objective references unknown metric {node.id}",
                )
            )
        elif isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            issues.append(
                _issue(
                    "metrics.yaml",
                    "objective.expression",
                    f"unsupported objective literal {node.value!r}",
                )
            )

    return issues


def _is_allowed_objective_node(node: ast.AST) -> bool:
    return isinstance(
        node,
        (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Pow,
            ast.Mod,
            ast.UAdd,
            ast.USub,
        ),
    )


def _validate_optimizer_contract(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    optimizer = bundle.optimizer.optimizer
    spectre = bundle.spectre.spectre

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
    ) and optimizer.max_evaluations < 2 * len(bundle.variables.variables):
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


def _cast_model(model_type: type[Any], model: BaseModel) -> Any:
    if not isinstance(model, model_type):
        raise TypeError(f"expected {model_type.__name__}, got {type(model).__name__}")
    return model
