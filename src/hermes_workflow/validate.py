from __future__ import annotations

import ast
import math
import re
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
from hermes_workflow.fix_run_models import WaveformExportsConfig


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

_ALLOWED_OBJECTIVE_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
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
)
_OBJECTIVE_FUNCTIONS = {"min": min, "max": max, "ln": math.log}


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
    waveform_exports: WaveformExportsConfig | None = None
    history_warm_start: HistoryWarmStartConfig | None = None


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
    workflow_mode = _detect_workflow_mode(config_dir)

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


def _validate_contract_bundle(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_netlist_paths(bundle.project_config))
    issues.extend(_validate_variables(bundle.variables))
    if bundle.metrics is not None:
        issues.extend(_validate_metrics(bundle.metrics, bundle.testbenches))
        issues.extend(_validate_objective_expression(bundle.metrics))
    if bundle.optimizer is not None:
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
    testbenches_config: TestbenchesConfig | None,
) -> list[ValidationIssue]:
    declared_metrics = {metric.name for metric in metrics_config.metrics}
    issues: list[ValidationIssue] = []
    declared_testbenches = (
        {testbench.id for testbench in testbenches_config.testbenches}
        if testbenches_config is not None
        else set()
    )
    for index, metric in enumerate(metrics_config.metrics):
        if testbenches_config is None:
            if metric.testbench is not None:
                issues.append(
                    _issue(
                        "metrics.yaml",
                        f"metrics[{index}].testbench",
                        "metric testbench requires config/testbenches.yaml",
                    )
                )
            continue
        if metric.testbench is None:
            issues.append(
                _issue(
                    "metrics.yaml",
                    f"metrics[{index}].testbench",
                    "metric must declare testbench when config/testbenches.yaml exists",
                )
            )
            continue
        if metric.testbench not in declared_testbenches:
            issues.append(
                _issue(
                    "metrics.yaml",
                    f"metrics[{index}].testbench",
                    f"metric {metric.name} references unknown testbench {metric.testbench}",
                )
            )
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

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _OBJECTIVE_FUNCTIONS:
                function_name = getattr(node.func, "id", type(node.func).__name__)
                issues.append(
                    _issue(
                        "metrics.yaml",
                        "objective.expression",
                        f"unsupported objective function {function_name}",
                    )
                )
            if node.keywords:
                issues.append(
                    _issue(
                        "metrics.yaml",
                        "objective.expression",
                        "objective function keyword arguments are unsupported",
                    )
                )
        elif (
            isinstance(node, ast.Name)
            and node.id not in declared_metrics
            and node.id not in _OBJECTIVE_FUNCTIONS
        ):
            issues.append(
                _issue(
                    "metrics.yaml",
                    "objective.expression",
                    f"objective references unknown metric {node.id}",
                )
            )
        elif isinstance(node, ast.Constant):
            issues.extend(_validate_objective_literal(node.value))

    return issues


def _validate_objective_literal(value: object) -> list[ValidationIssue]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return [
            _issue(
                "metrics.yaml",
                "objective.expression",
                f"unsupported objective literal {value!r}",
            )
        ]

    if isinstance(value, float) and not math.isfinite(value):
        return [
            _issue(
                "metrics.yaml",
                "objective.expression",
                "objective numeric literals must be finite",
            )
        ]

    return []


def _is_allowed_objective_node(node: ast.AST) -> bool:
    return isinstance(node, _ALLOWED_OBJECTIVE_NODES)


def evaluate_objective(expression: str, metrics: dict[str, float]) -> float:
    """Evaluate a validated objective expression against computed metric values.

    Parses the expression AST, substitutes metric names with float values,
    and evaluates arithmetic. Only allows the same nodes as validation:
    metric name references, numeric constants, and arithmetic operators.

    Raises ValueError if the expression contains unknown names, disallowed
    nodes, boolean constants, or non-finite numeric constants.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid objective expression: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_OBJECTIVE_NODES):
            raise ValueError(
                f"unsupported objective expression node {type(node).__name__}"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _OBJECTIVE_FUNCTIONS:
                function_name = getattr(node.func, "id", type(node.func).__name__)
                raise ValueError(f"unsupported objective function {function_name}")
            if node.keywords:
                raise ValueError("objective function keyword arguments are unsupported")
        elif isinstance(node, ast.Name):
            if node.id in _OBJECTIVE_FUNCTIONS:
                continue
            if node.id not in metrics:
                raise ValueError(f"objective references unknown metric {node.id}")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise ValueError(f"unsupported objective literal {node.value!r}")
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise ValueError("objective numeric literals must be finite")

    return _eval_ast(tree.body, metrics)


def _eval_ast(node: ast.AST, metrics: dict[str, float]) -> float:
    """Recursively evaluate an objective AST node with metric substitution."""
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in _OBJECTIVE_FUNCTIONS:
            raise ValueError(f"objective function {node.id} must be called")
        return metrics[node.id]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _OBJECTIVE_FUNCTIONS:
            function_name = getattr(node.func, "id", type(node.func).__name__)
            raise ValueError(f"unsupported objective function {function_name}")
        if node.keywords:
            raise ValueError("objective function keyword arguments are unsupported")
        args = [_eval_ast(arg, metrics) for arg in node.args]
        if node.func.id == "ln":
            if len(args) != 1:
                raise ValueError("objective function ln expects one argument")
            if args[0] <= 0:
                raise ValueError("objective function ln argument must be positive")
        return float(_OBJECTIVE_FUNCTIONS[node.func.id](*args))
    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand, metrics)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"unsupported unary operator {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, metrics)
        right = _eval_ast(node.right, metrics)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise ValueError(f"unsupported binary operator {type(node.op).__name__}")
    raise ValueError(f"unsupported objective expression node {type(node).__name__}")


def _validate_optimizer_contract(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if bundle.optimizer is None:
        return issues
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


def _detect_workflow_mode(config_dir: Path) -> str:
    """Detect workflow mode from config/workflow.yaml.

    Falls back to ``fix_run`` if ``fixed_points.yaml`` exists but
    ``workflow.yaml`` does not (defensive — keeps fix-run shape recognized).
    Defaults to ``optimize`` otherwise. Malformed YAML defaults to
    ``optimize`` so the standard required-config validator still runs."""
    workflow_path = config_dir / "workflow.yaml"
    if workflow_path.exists():
        try:
            payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return "optimize"
        if isinstance(payload, dict):
            mode = payload.get("mode")
            if isinstance(mode, str):
                return mode
    if (config_dir / "fixed_points.yaml").exists():
        return "fix_run"
    return "optimize"


def _cast_model(model_type: type[Any], model: BaseModel) -> Any:
    if not isinstance(model, model_type):
        raise TypeError(f"expected {model_type.__name__}, got {type(model).__name__}")
    return model
