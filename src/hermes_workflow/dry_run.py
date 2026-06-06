from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from hermes_workflow.mock_optimizer import (
    compute_mock_metrics,
    evaluate_constraints,
    evaluate_objective_from_config,
)
from hermes_workflow.reports import DryRunReport, PassFail, PlaceholderCheck
from hermes_workflow.validate import ContractBundle, assert_valid_project


PLACEHOLDER_RE = re.compile(r"{{(?P<name>[A-Za-z_][A-Za-z0-9_]*)}}")
UNRESOLVED_PLACEHOLDER_RE = re.compile(r"{{[^{}]*}}")
RENDERED_CANDIDATE = "runs/dry_run/input.scs"


def run_dry_run(project_dir: Path) -> DryRunReport:
    bundle = assert_valid_project(project_dir)
    template_path = _project_path(bundle, bundle.project_config.netlist.template_scs)
    rendered_path = _project_path(bundle, RENDERED_CANDIDATE)
    issues: list[str] = []
    placeholder_check = PlaceholderCheck()
    metrics_import_ok = True
    mock_metrics_ok = False
    objective_ok = False
    constraints_ok = False
    ledger_write_ok = False
    state_write_ok = False

    if not template_path.exists():
        issues.append(
            f"template.scs is missing: {bundle.project_config.netlist.template_scs}"
        )
        report = _build_report(
            PassFail.FAIL,
            placeholder_check,
            metrics_import_ok,
            mock_metrics_ok,
            objective_ok,
            constraints_ok,
            ledger_write_ok,
            state_write_ok,
            issues,
        )
        _cleanup_rendered(rendered_path)
        _write_report(bundle, report)
        return report

    template_text = template_path.read_text(encoding="utf-8")
    candidate = _lower_bound_candidate(bundle)
    rendered_text, placeholder_check, placeholder_issues = _render_template(
        template_text,
        candidate,
    )
    issues.extend(placeholder_issues)
    child_rendered_inputs: dict[str, str] = {}
    if bundle.testbenches is not None:
        child_rendered_inputs = _render_testbench_templates(bundle, candidate, issues)

    try:
        computed_metrics = compute_mock_metrics(
            bundle.metrics,
            bundle.variables,
            candidate,
        )
        mock_metrics_ok = True
    except Exception as exc:
        computed_metrics = {}
        issues.append(f"mock metrics evaluation failed: {exc}")

    if mock_metrics_ok:
        try:
            evaluate_objective_from_config(bundle.metrics, computed_metrics)
            objective_ok = True
        except Exception as exc:
            issues.append(f"objective evaluation failed: {exc}")

        try:
            evaluate_constraints(bundle.metrics, computed_metrics)
            constraints_ok = True
        except Exception as exc:
            issues.append(f"constraints evaluation failed: {exc}")

    ledger_write_ok = _probe_directory_writable(bundle.project_dir / "ledger", issues)
    state_write_ok = _probe_directory_writable(bundle.project_dir / "state", issues)

    status = (
        PassFail.PASS
        if not issues
        and mock_metrics_ok
        and objective_ok
        and constraints_ok
        and ledger_write_ok
        and state_write_ok
        else PassFail.FAIL
    )

    if status == PassFail.PASS:
        try:
            rendered_path.parent.mkdir(parents=True, exist_ok=True)
            rendered_path.write_text(rendered_text, encoding="utf-8")
            _write_testbench_rendered_inputs(
                bundle,
                child_rendered_inputs,
            )
        except OSError as exc:
            issues.append(f"rendered candidate could not be written: {exc}")
            status = PassFail.FAIL
            _cleanup_rendered(rendered_path)
            _cleanup_testbench_rendered_inputs(bundle)
    else:
        _cleanup_rendered(rendered_path)
        _cleanup_testbench_rendered_inputs(bundle)

    report = _build_report(
        status,
        placeholder_check,
        metrics_import_ok,
        mock_metrics_ok,
        objective_ok,
        constraints_ok,
        ledger_write_ok,
        state_write_ok,
        issues,
    )
    _write_report(bundle, report)
    return report


def _lower_bound_candidate(bundle: ContractBundle) -> dict[str, str]:
    return {variable.name: variable.lower for variable in bundle.variables.variables}


def _render_template(
    template_text: str,
    candidate: dict[str, str],
) -> tuple[str, PlaceholderCheck, list[str]]:
    issues: list[str] = []
    approved_names = set(candidate)
    seen_names = {match.group("name") for match in PLACEHOLDER_RE.finditer(template_text)}
    unexpected = sorted(seen_names - approved_names)
    missing = sorted(approved_names - seen_names)

    for name in missing:
        issues.append(f"approved variable {name} placeholder is missing from template")
    for name in unexpected:
        issues.append(f"unexpected template variable {name}")

    rendered = template_text
    for name, value in candidate.items():
        rendered = rendered.replace(f"{{{{{name}}}}}", value)

    unresolved = sorted(
        {match.group(0) for match in UNRESOLVED_PLACEHOLDER_RE.finditer(rendered)}
    )
    if unresolved:
        issues.append("rendered candidate still contains unresolved placeholders")

    return (
        rendered,
        PlaceholderCheck(
            unresolved_placeholders=unresolved,
            unexpected_template_variables=unexpected,
        ),
        issues,
    )


def _render_testbench_templates(
    bundle: ContractBundle,
    candidate: dict[str, str],
    issues: list[str],
) -> dict[str, str]:
    if bundle.testbenches is None:
        return {}

    rendered_inputs: dict[str, str] = {}
    for testbench in bundle.testbenches.testbenches:
        template_relative = _testbench_template(testbench.id)
        template_path = _project_path(bundle, template_relative)
        if not template_path.exists():
            issues.append(f"{testbench.id}: template.scs is missing: {template_relative}")
            continue
        rendered, _placeholder_check, placeholder_issues = _render_template(
            template_path.read_text(encoding="utf-8"),
            candidate,
        )
        issues.extend(f"{testbench.id}: {issue}" for issue in placeholder_issues)
        rendered_inputs[testbench.id] = rendered
    return rendered_inputs


def _write_testbench_rendered_inputs(
    bundle: ContractBundle,
    child_rendered_inputs: dict[str, str],
) -> None:
    for testbench_id, rendered_text in child_rendered_inputs.items():
        rendered_path = _project_path(bundle, _testbench_rendered_input(testbench_id))
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_path.write_text(rendered_text, encoding="utf-8")


def _cleanup_testbench_rendered_inputs(bundle: ContractBundle) -> None:
    if bundle.testbenches is None:
        return
    for testbench in bundle.testbenches.testbenches:
        rendered_path = _project_path(bundle, _testbench_rendered_input(testbench.id))
        if rendered_path.exists():
            rendered_path.unlink()


def _probe_directory_writable(path: Path, issues: list[str]) -> bool:
    probe = path / ".dry_run_write_probe"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        issues.append(f"{path.name} directory is not writable: {exc}")
        return False
    return True


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"dry-run path must be project-relative and safe: {relative_path}"
        )
    return bundle.project_dir / Path(*path.parts)


def _testbench_template(testbench_id: str) -> str:
    return f"netlists/testbenches/{testbench_id}/templates/template.scs"


def _testbench_rendered_input(testbench_id: str) -> str:
    return f"runs/dry_run/testbenches/{testbench_id}/input.scs"


def _build_report(
    status: PassFail,
    placeholder_check: PlaceholderCheck,
    metrics_import_ok: bool,
    mock_metrics_ok: bool,
    objective_ok: bool,
    constraints_ok: bool,
    ledger_write_ok: bool,
    state_write_ok: bool,
    issues: list[str],
) -> DryRunReport:
    return DryRunReport(
        schema_version="1.0",
        status=status,
        rendered_candidate_scs=RENDERED_CANDIDATE,
        placeholder_check=placeholder_check,
        metrics_import_ok=metrics_import_ok,
        mock_metrics_ok=mock_metrics_ok,
        objective_ok=objective_ok,
        constraints_ok=constraints_ok,
        ledger_write_ok=ledger_write_ok,
        state_write_ok=state_write_ok,
        issues=issues,
    )


def _write_report(bundle: ContractBundle, report: DryRunReport) -> None:
    report_path = bundle.project_dir / "reports" / "dry_run_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _cleanup_rendered(rendered_path: Path) -> None:
    if rendered_path.exists():
        rendered_path.unlink()
