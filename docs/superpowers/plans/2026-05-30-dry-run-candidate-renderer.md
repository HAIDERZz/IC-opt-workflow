# Dry-Run Candidate Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Hermes dry-run command that renders one deterministic candidate Spectre deck, validates placeholder/mock-metric contracts, and writes `reports/dry_run_report.json` without starting Spectre, Virtuoso, or the optimizer loop.

**Architecture:** Add a focused `src/hermes_workflow/dry_run.py` module that loads the validated contract bundle, renders `netlists/templates/template.scs` with lower-bound variable values, probes mock metrics/objective/constraints and writable project directories, then writes the existing `DryRunReport` model. Add a thin Typer `dry-run` command that delegates to this module and formats pass/fail output.

**Tech Stack:** Python 3.11+, Typer, Pydantic, PyYAML, pytest, ruff, existing `hermes_workflow` schema/report/validation/mock optimizer helpers.

---

## Execution Model

Use `superpowers:subagent-driven-development` for implementation. For each task:

1. Dispatch a fresh Claude CLI coding worker with only the task section and the current spec path.
2. Review the worker diff before running the next task.
3. Run the task-specific pytest command and `ruff check .`.
4. Run the Claude review MCP gate for the task diff:

```bash
claude -p "Review the current git diff for C-2 Task N against docs/superpowers/specs/2026-05-30-dry-run-candidate-renderer-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

5. Fix Critical and Important findings before proceeding.
6. Commit after the task is green.

Do not commit local real netlist examples from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example`.

## File Map

- Create `src/hermes_workflow/dry_run.py`: dry-run orchestration, lower-bound candidate builder, template rendering, placeholder checks, writability probes, report writing.
- Modify `src/hermes_workflow/cli.py`: add `dry-run` command and import `run_dry_run`.
- Create `tests/test_dry_run.py`: dry-run unit tests using sanitized inline Spectre snippets.
- Modify `tests/test_cli.py`: CLI smoke tests for dry-run success and failure.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-2 task progress.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: record resumable C-2 checkpoint.

## Execution Status

Status: complete as of 2026-05-30.

Completed commits:

- Task 1: `b925cb9 feat: add dry-run renderer`
- Task 2: `b042a74 fix: enforce dry-run placeholder failures`
- Task 3: `c2e08d2 test: lock dry-run mock check semantics`
- Task 4: `9fffb90 feat: add dry-run cli command`
- Task 5: `59c0aff docs: record dry-run renderer progress`
- Task 6 hardening: `1835c94 fix: report dry-run render write failures`

Final verification:

- `pytest -q`: passed, 159 tests.
- `ruff check .`: passed.
- Local-only smoke under `/tmp/hermes_c2_smoke` passed using `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs`: `prepare-netlist` passed and `dry-run` passed.

Final reviews:

- Final spec review: passed.
- Final code-quality review: passed through the project Claude Review MCP wrapper with no Critical or Important findings.

## Task 1: Dry-Run Success Path

**Files:**
- Create: `src/hermes_workflow/dry_run.py`
- Create: `tests/test_dry_run.py`

- [ ] **Step 1: Write the failing success-path test**

Add `tests/test_dry_run.py` with this starting content:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.package import create_project_from_template
from hermes_workflow.reports import DryRunReport, PassFail


def _create_project_with_template(tmp_path: Path, template_text: str) -> Path:
    project_dir = create_project_from_template(tmp_path / "bridge_test_inv")
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(template_text, encoding="utf-8")
    return project_dir


def _load_report(project_dir: Path) -> DryRunReport:
    payload = json.loads(
        (project_dir / "reports" / "dry_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    return DryRunReport.model_validate(payload)


def test_run_dry_run_renders_lower_bound_candidate(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
    )

    report = run_dry_run(project_dir)

    rendered_path = project_dir / "runs" / "dry_run" / "input.scs"
    rendered = rendered_path.read_text(encoding="utf-8")
    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.PASS
    assert report.rendered_candidate_scs == "runs/dry_run/input.scs"
    assert report.placeholder_check.unresolved_placeholders == []
    assert report.placeholder_check.unexpected_template_variables == []
    assert report.metrics_import_ok is True
    assert report.mock_metrics_ok is True
    assert report.objective_ok is True
    assert report.constraints_ok is True
    assert report.ledger_write_ok is True
    assert report.state_write_ok is True
    assert report.issues == []
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "FN=2" in rendered
    assert "WN=0.3 um" in rendered
    assert "FP=2" in rendered
    assert "WP=0.3 um" in rendered
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_dry_run.py::test_run_dry_run_renders_lower_bound_candidate -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.dry_run'`.

- [ ] **Step 3: Implement the minimal dry-run module**

Create `src/hermes_workflow/dry_run.py`:

```python
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
from hermes_workflow.schemas import VariableKind
from hermes_workflow.validate import ContractBundle, assert_valid_project


PLACEHOLDER_RE = re.compile(r"{{(?P<name>[A-Za-z_][A-Za-z0-9_]*)}}")
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
        issues.append(f"template.scs is missing: {bundle.project_config.netlist.template_scs}")
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
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_path.write_text(rendered_text, encoding="utf-8")
    else:
        _cleanup_rendered(rendered_path)

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
    candidate: dict[str, str] = {}
    for variable in bundle.variables.variables:
        if variable.kind == VariableKind.INTEGER:
            candidate[variable.name] = str(int(variable.lower))
        else:
            candidate[variable.name] = variable.lower
    return candidate


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

    unresolved = sorted({match.group(0) for match in PLACEHOLDER_RE.finditer(rendered)})
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
        raise ValueError(f"dry-run path must be project-relative and safe: {relative_path}")
    return bundle.project_dir / Path(*path.parts)


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
```

- [ ] **Step 4: Run the success-path test**

Run:

```bash
pytest tests/test_dry_run.py::test_run_dry_run_renders_lower_bound_candidate -v
```

Expected: PASS.

- [ ] **Step 5: Run focused quality checks**

Run:

```bash
pytest tests/test_dry_run.py -v
ruff check .
```

Expected: all tests pass and ruff reports `All checks passed!`.

- [ ] **Step 6: Run review gate and commit**

Run the Claude review command from the Execution Model with `Task 1`. Fix Critical and Important findings.

Commit:

```bash
git add src/hermes_workflow/dry_run.py tests/test_dry_run.py
git commit -m "feat: add dry-run renderer"
```

## Task 2: Placeholder and Template Failure Contracts

**Files:**
- Modify: `tests/test_dry_run.py`
- Modify: `src/hermes_workflow/dry_run.py`

- [ ] **Step 1: Add failing tests for missing template, missing approved placeholders, unexpected placeholders, and stale render cleanup**

Append to `tests/test_dry_run.py`:

```python
def test_run_dry_run_reports_missing_template(tmp_path: Path) -> None:
    project_dir = create_project_from_template(tmp_path / "bridge_test_inv")

    report = run_dry_run(project_dir)

    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.FAIL
    assert "template.scs is missing: netlists/templates/template.scs" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_reports_missing_approved_placeholder(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}}
tran tran stop=10n
""",
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.FAIL
    assert "approved variable WP placeholder is missing from template" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_reports_unexpected_placeholder(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}} GAIN={{GAIN}}
tran tran stop=10n
""",
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.FAIL
    assert report.placeholder_check.unexpected_template_variables == ["GAIN"]
    assert report.placeholder_check.unresolved_placeholders == ["{{GAIN}}"]
    assert "unexpected template variable GAIN" in report.issues
    assert "rendered candidate still contains unresolved placeholders" in report.issues
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()


def test_run_dry_run_removes_stale_render_on_failure(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
    )
    first_report = run_dry_run(project_dir)
    assert first_report.status == PassFail.PASS
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.write_text(
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}} EXTRA={{EXTRA}}
tran tran stop=10n
""",
        encoding="utf-8",
    )

    failed_report = run_dry_run(project_dir)

    assert failed_report.status == PassFail.FAIL
    assert not (project_dir / "runs" / "dry_run" / "input.scs").exists()
```

- [ ] **Step 2: Run the failure-contract tests**

Run:

```bash
pytest tests/test_dry_run.py -v
```

Expected: PASS if Task 1 implementation already covers these failures. If any test fails, fix only `src/hermes_workflow/dry_run.py`.

- [ ] **Step 3: Strengthen placeholder scanning if needed**

If `test_run_dry_run_reports_unexpected_placeholder` fails because unresolved tokens are not captured, keep `PLACEHOLDER_RE` strict and ensure `_render_template()` computes unresolved placeholders after approved replacements:

```python
unresolved = sorted({match.group(0) for match in PLACEHOLDER_RE.finditer(rendered)})
```

If `test_run_dry_run_reports_missing_approved_placeholder` fails, ensure missing approved names are computed before replacement:

```python
missing = sorted(approved_names - seen_names)
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
pytest tests/test_dry_run.py -v
ruff check .
```

Expected: all tests pass and ruff reports `All checks passed!`.

- [ ] **Step 5: Run review gate and commit**

Run the Claude review command from the Execution Model with `Task 2`. Fix Critical and Important findings.

Commit:

```bash
git add src/hermes_workflow/dry_run.py tests/test_dry_run.py
git commit -m "fix: enforce dry-run placeholder failures"
```

## Task 3: Mock Metric and Writability Semantics

**Files:**
- Modify: `tests/test_dry_run.py`
- Modify: `src/hermes_workflow/dry_run.py`

- [ ] **Step 1: Add tests proving dry-run does not treat constraint failure as renderer failure**

Append to `tests/test_dry_run.py`:

```python
def test_run_dry_run_constraint_result_false_still_checks_evaluability(
    tmp_path: Path,
) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
    )
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics_text = metrics_path.read_text(encoding="utf-8")
    metrics_path.write_text(
        metrics_text.replace("value: \"80 ps\"", "value: \"0 ps\"", 1),
        encoding="utf-8",
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.PASS
    assert report.constraints_ok is True
    assert report.issues == []
```

- [ ] **Step 2: Add tests proving dry-run writes only dry-run probes and output**

Append to `tests/test_dry_run.py`:

```python
def test_run_dry_run_does_not_write_optimizer_artifacts(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
    )

    report = run_dry_run(project_dir)

    assert report.status == PassFail.PASS
    assert (project_dir / "runs" / "dry_run" / "input.scs").exists()
    assert not (project_dir / "ledger" / ".dry_run_write_probe").exists()
    assert not (project_dir / "state" / ".dry_run_write_probe").exists()
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
    assert not (project_dir / "state" / "health_check.json").exists()
```

- [ ] **Step 3: Run the semantic tests**

Run:

```bash
pytest tests/test_dry_run.py::test_run_dry_run_constraint_result_false_still_checks_evaluability tests/test_dry_run.py::test_run_dry_run_does_not_write_optimizer_artifacts -v
```

Expected: PASS. If the constraint test fails, adjust `run_dry_run()` so `constraints_ok` means `evaluate_constraints()` ran without raising, not that it returned `True`.

- [ ] **Step 4: Implement the constraints-ok semantics if needed**

Use this pattern in `run_dry_run()`:

```python
try:
    evaluate_constraints(bundle.metrics, computed_metrics)
    constraints_ok = True
except Exception as exc:
    issues.append(f"constraints evaluation failed: {exc}")
```

Do not branch on the boolean returned by `evaluate_constraints()`.

- [ ] **Step 5: Run focused checks**

Run:

```bash
pytest tests/test_dry_run.py -v
ruff check .
```

Expected: all tests pass and ruff reports `All checks passed!`.

- [ ] **Step 6: Run review gate and commit**

Run the Claude review command from the Execution Model with `Task 3`. Fix Critical and Important findings.

Commit:

```bash
git add src/hermes_workflow/dry_run.py tests/test_dry_run.py
git commit -m "fix: define dry-run mock check semantics"
```

## Task 4: CLI Command

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI success and failure tests**

Append to `tests/test_cli.py`:

```python
def test_cli_dry_run_writes_candidate_and_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["dry-run", str(project_dir)])

    assert result.exit_code == 0
    assert "dry run passed" in result.stdout
    assert (project_dir / "runs" / "dry_run" / "input.scs").exists()
    assert (project_dir / "reports" / "dry_run_report.json").exists()


def test_cli_dry_run_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["dry-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "dry run failed" in result.stdout
    assert "template.scs is missing: netlists/templates/template.scs" in result.stdout
    assert "reports/dry_run_report.json" in result.stdout
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run:

```bash
pytest tests/test_cli.py::test_cli_dry_run_writes_candidate_and_report tests/test_cli.py::test_cli_dry_run_reports_failure_without_traceback -v
```

Expected: FAIL because `dry-run` command does not exist.

- [ ] **Step 3: Add the CLI command**

Modify `src/hermes_workflow/cli.py`.

Add import:

```python
from hermes_workflow.dry_run import run_dry_run
```

Add command after `prepare_netlist_command()`:

```python
@app.command("dry-run")
def dry_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with netlists/templates/template.scs."),
    ],
) -> None:
    try:
        report = run_dry_run(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("dry run passed")
        return

    typer.echo("dry run failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/dry_run_report.json")
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Run CLI checks**

Run:

```bash
pytest tests/test_cli.py::test_cli_dry_run_writes_candidate_and_report tests/test_cli.py::test_cli_dry_run_reports_failure_without_traceback -v
pytest tests/test_cli.py tests/test_dry_run.py -v
ruff check .
```

Expected: all tests pass and ruff reports `All checks passed!`.

- [ ] **Step 5: Run review gate and commit**

Run the Claude review command from the Execution Model with `Task 4`. Fix Critical and Important findings.

Commit:

```bash
git add src/hermes_workflow/cli.py tests/test_cli.py tests/test_dry_run.py
git commit -m "feat: add dry-run cli command"
```

## Task 5: Integration Verification and Progress Docs

**Files:**
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] **Step 1: Run full verification**

Run:

```bash
pytest -q
ruff check .
```

Expected: `pytest` reports all tests passing, and ruff reports `All checks passed!`.

- [ ] **Step 2: Run a local-only smoke using the first real netlist example if present**

Run only if `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs` exists:

```bash
python -m hermes_workflow.cli init /tmp/hermes_c2_smoke --force
cp /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs /tmp/hermes_c2_smoke/netlists/exported/input.scs
python -m hermes_workflow.cli prepare-netlist /tmp/hermes_c2_smoke
python -m hermes_workflow.cli dry-run /tmp/hermes_c2_smoke
```

Expected output includes:

```text
netlist preparation passed
dry run passed
```

Do not copy files from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` into the git repository.

- [ ] **Step 3: Update execution progress**

Add a Plan C-2 section to `docs/EXECUTION_PROGRESS_2026-05-29.md`:

```markdown
## Plan C-2: Dry-Run Candidate Renderer

Status: completed and committed.

Implemented:

- `src/hermes_workflow/dry_run.py` renders one lower-bound candidate from `netlists/templates/template.scs`.
- `hermes-workflow dry-run PROJECT_DIR` writes `runs/dry_run/input.scs` and `reports/dry_run_report.json`.
- Dry-run checks placeholders, mock metric computation, objective evaluation, constraint evaluability, and `ledger/` and `state/` writability.
- Dry-run does not run Spectre, Virtuoso, or `run_mock_optimization()`.
- Dry-run does not write optimizer ledger rows, optimizer state, best-candidate files, or health-check files.

Verification:

- `pytest -q`: passed.
- `ruff check .`: passed.
- Local-only real-deck smoke passed when `netlist_example/input.scs` was available.
```

- [ ] **Step 4: Update compact resume checkpoint**

Add or revise these bullets in `docs/COMPACT_RESUME_CHECKPOINT.md`:

```markdown
- Plan C-2 dry-run candidate renderer is complete.
- `hermes-workflow dry-run PROJECT_DIR` renders `runs/dry_run/input.scs` from `netlists/templates/template.scs` and writes `reports/dry_run_report.json`.
- Real `input.scs` examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` remain local-only references and are not committed.
```

- [ ] **Step 5: Commit documentation**

Commit:

```bash
git add docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "docs: record dry-run renderer progress"
```

## Task 6: Final Review Gate and Closeout

**Files:**
- Modify: `docs/superpowers/plans/2026-05-30-dry-run-candidate-renderer.md`

- [ ] **Step 1: Run final verification**

Run:

```bash
pytest -q
ruff check .
git status --short
```

Expected:

- `pytest` reports all tests passing.
- `ruff check .` reports `All checks passed!`.
- `git status --short` contains only intentional documentation edits for this task or is empty.

- [ ] **Step 2: Run final spec and code-quality review gates**

Run:

```bash
claude -p "Spec review: compare the implemented C-2 dry-run candidate renderer against docs/superpowers/specs/2026-05-30-dry-run-candidate-renderer-design.md. Report Critical, Important, Minor findings."
claude -p "Code quality review: inspect the C-2 dry-run implementation and tests for correctness, maintainability, failure surfaces, and accidental real-run side effects. Report Critical, Important, Minor findings."
```

Expected: no Critical or Important findings. Fix Critical and Important findings, rerun focused tests, then rerun the relevant review.

- [ ] **Step 3: Mark the plan complete**

Edit this plan file and change task statuses in any execution notes to show C-2 is complete. Do not alter the completed implementation instructions.

- [ ] **Step 4: Commit closeout docs**

Commit:

```bash
git add docs/superpowers/plans/2026-05-30-dry-run-candidate-renderer.md
git commit -m "docs: close dry-run renderer plan"
```

## Self-Review

Spec coverage:

- Deterministic lower-bound rendering is covered by Task 1.
- Placeholder checks for missing approved variables, unexpected variables, unresolved tokens, and stale render cleanup are covered by Task 2.
- Mock metrics, objective evaluation, constraint evaluability, and non-production writability probes are covered by Task 3.
- CLI `hermes-workflow dry-run PROJECT_DIR` is covered by Task 4.
- Full verification, local-only smoke, and progress records are covered by Task 5.
- Final review gate is covered by Task 6.

Type consistency:

- `run_dry_run(project_dir: Path) -> DryRunReport` is the only public dry-run API introduced by this plan.
- `DryRunReport`, `PlaceholderCheck`, and `PassFail` are reused from `src/hermes_workflow/reports.py`.
- Mock metric helpers are reused from `src/hermes_workflow/mock_optimizer.py`.
- The rendered candidate path is consistently `runs/dry_run/input.scs`.

Execution boundary:

- The plan never calls Spectre, Virtuoso, or `run_mock_optimization()`.
- The plan never writes `ledger/experiment_ledger.jsonl`, `state/optimizer_state.json`, `state/best_candidate.json`, or `state/health_check.json`.
- Local real netlist examples are read only for optional smoke testing and are never committed.
