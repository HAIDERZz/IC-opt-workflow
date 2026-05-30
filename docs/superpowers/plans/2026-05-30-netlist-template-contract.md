# Netlist Template Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Plan C C-1: a safe Hermes netlist preparation step that templates only approved top-level Spectre parameter assignments and writes the existing netlist preparation report.

**Architecture:** Add a focused `hermes_workflow.netlists` module that reads the validated YAML bundle, scans exported Spectre decks conservatively, writes `template.scs`, and emits `NetlistPreparationReport`. Wire it into `cli.py` as `prepare-netlist`; keep real Virtuoso decks local-only and use sanitized repository fixtures in tests.

**Tech Stack:** Python 3.11+, standard library text scanning, existing Pydantic report model, Typer CLI, pytest, ruff.

---

## Spec And Scope

Design spec: `docs/superpowers/specs/2026-05-30-netlist-template-contract-design.md`

This plan implements only C-1:

- Convert `netlists/exported/input.scs` to `netlists/templates/template.scs`.
- Rewrite only approved variable values in top-level `parameters` statements.
- Write `reports/netlist_preparation_report.json`.
- Expose `hermes-workflow prepare-netlist PROJECT_DIR`.
- Do not commit real `input.scs` files from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example`.

## File Structure

- Create `src/hermes_workflow/netlists.py`
  - Public API: `prepare_netlist(project_dir: Path) -> NetlistPreparationReport`
  - Internal scanner helpers for logical Spectre statements and parameter assignment spans.
  - Report writer for pass/fail outcomes.
- Create `tests/test_netlists.py`
  - Unit tests for single-line parameters, continuation parameters, no off-target replacement, missing variables, duplicates, missing input, and analysis detection.
- Modify `src/hermes_workflow/cli.py`
  - Import `prepare_netlist`.
  - Add `prepare-netlist` command.
- Modify `tests/test_cli.py`
  - CLI smoke tests for success and failure without tracebacks.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`
  - Add a short Plan C progress note after implementation and review gates pass.

## Implementation Rules

- Use TDD for each task: write the failing test first, run the targeted test, implement the minimum, rerun targeted tests.
- Keep real deck examples out of git. Use only hand-written sanitized test strings.
- Do not change Plan A or Plan B behavior except adding the new CLI command.
- Do not widen `NetlistPreparationReport`; use the existing schema in `reports.py`.
- Commit after each task if tests pass.

## Execution Status

Task 5 completed on 2026-05-30. Do not redo Tasks 1-5.

- Task 1 complete and reviewed: `1ab42e1 feat: prepare spectre netlist templates`.
- Task 2 complete and reviewed: `6ce3e69 fix: support continued spectre parameters`.
- Task 3 complete and reviewed: `8e59ac9 fix: report unsafe netlist templating failures`.
- Task 4 complete and reviewed: `04fa358 feat: add prepare netlist cli`.
- Task 5 verification complete: `pytest -q` passed, 146 tests; `ruff check .` passed; local-only smoke under `/tmp/hermes_plan_c_smoke` passed for all four real deck examples.
- Next resume point: Task 6, Review Gate And Final Verification.

---

### Task 1: Single-Line Parameter Templating

**Files:**
- Create: `src/hermes_workflow/netlists.py`
- Create: `tests/test_netlists.py`

- [ ] **Step 1: Write the failing single-line test**

Create `tests/test_netlists.py` with this content:

```python
import json
from pathlib import Path

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.package import create_project_from_template
from hermes_workflow.reports import NetlistPreparationReport, PassFail


def _project_with_input(tmp_path: Path, deck_text: str) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    input_path = project_dir / "netlists" / "exported" / "input.scs"
    input_path.write_text(deck_text, encoding="utf-8")
    return project_dir


def _load_netlist_report(project_dir: Path) -> NetlistPreparationReport:
    payload = json.loads(
        (project_dir / "reports" / "netlist_preparation_report.json").read_text(
            encoding="utf-8"
        )
    )
    return NetlistPreparationReport.model_validate(payload)


def test_prepare_netlist_templates_single_line_parameter_values(tmp_path: Path) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
M0 (VOUT IN VSS VSS) nmos w=WN*FN l=45n
tran tran stop=10n
dcOp dc oppoint=rawfile
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    persisted_report = _load_netlist_report(project_dir)

    assert report.status == PassFail.PASS
    assert persisted_report == report
    assert "FN={{FN}}" in template_text
    assert "FP={{FP}}" in template_text
    assert "WN={{WN}}" in template_text
    assert "WP={{WP}}" in template_text
    assert "temperature=27" in template_text
    assert "w=WN*FN" in template_text
    assert report.approved_variables_template_status == {
        "FN": True,
        "WN": True,
        "FP": True,
        "WP": True,
    }
    assert report.analysis_statements == ["tran", "dcOp"]
    assert report.forbidden_setup_changes_detected is False
    assert report.issues == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_netlists.py::test_prepare_netlist_templates_single_line_parameter_values -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.netlists'`.

- [ ] **Step 3: Implement minimal single-line support**

Create `src/hermes_workflow/netlists.py` with this content:

```python
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
```

- [ ] **Step 4: Run the targeted test**

Run:

```bash
pytest tests/test_netlists.py::test_prepare_netlist_templates_single_line_parameter_values -v
```

Expected: PASS.

- [ ] **Step 5: Run lint on changed files**

Run:

```bash
ruff check src/hermes_workflow/netlists.py tests/test_netlists.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/hermes_workflow/netlists.py tests/test_netlists.py
git commit -m "feat: prepare spectre netlist templates"
```

---

### Task 2: Continuation Blocks And Safe Assignment Scanner

**Files:**
- Modify: `src/hermes_workflow/netlists.py`
- Modify: `tests/test_netlists.py`

- [ ] **Step 1: Add failing tests for continuation and off-target references**

Append these tests to `tests/test_netlists.py`:

```python
def test_prepare_netlist_templates_backslash_continued_parameters(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters \\
    temperature=27 \\
    L2=45n FN=4 \\
    FP=4 WN=0.6u WP=1.2u
I0 (VOUT IN VSS VSS) inverter w=WP*FP fingers=FN
pss pss fund=1G harms=10
pac pac maxsideband=10
pnoise pnoise maxsideband=10
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert "FN={{FN}}" in template_text
    assert "FP={{FP}}" in template_text
    assert "WN={{WN}}" in template_text
    assert "WP={{WP}}" in template_text
    assert "L2=45n" in template_text
    assert "w=WP*FP fingers=FN" in template_text
    assert report.analysis_statements == ["pss", "pac", "pnoise"]


def test_prepare_netlist_does_not_template_instance_parameters(tmp_path: Path) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
subckt wrapped IN OUT VDD VSS
M0 (OUT IN VSS VSS) nmos w=WN*FN l=45n
ends wrapped
X0 (IN OUT VDD VSS) wrapped FN=99 WP=99u
ac ac start=1 stop=10G
""",
    )

    report = prepare_netlist(project_dir)

    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    assert report.status == PassFail.PASS
    assert "parameters temperature=27 FN={{FN}} FP={{FP}} WN={{WN}} WP={{WP}}" in template_text
    assert "X0 (IN OUT VDD VSS) wrapped FN=99 WP=99u" in template_text
```

- [ ] **Step 2: Run tests to verify the continuation case fails**

Run:

```bash
pytest tests/test_netlists.py::test_prepare_netlist_templates_backslash_continued_parameters tests/test_netlists.py::test_prepare_netlist_does_not_template_instance_parameters -v
```

Expected: at least the continuation test FAILS because Task 1 only rewrites one line at a time.

- [ ] **Step 3: Replace the scanner with logical-statement rewriting**

In `src/hermes_workflow/netlists.py`, replace `_template_deck()` and add these helper functions:

```python
ASSIGNMENT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(?P<name>[A-Za-z_][A-Za-z0-9_]*)=")


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
```

Remove the old `_replace_assignment_value()` helper after the new scanner passes tests.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
pytest tests/test_netlists.py -v
```

Expected: all current `test_netlists.py` tests PASS.

- [ ] **Step 5: Run lint**

Run:

```bash
ruff check src/hermes_workflow/netlists.py tests/test_netlists.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/hermes_workflow/netlists.py tests/test_netlists.py
git commit -m "fix: support continued spectre parameters"
```

---

### Task 3: Failure Reports For Missing And Duplicate Variables

**Files:**
- Modify: `src/hermes_workflow/netlists.py`
- Modify: `tests/test_netlists.py`

- [ ] **Step 1: Add failing tests for missing input, missing variables, and duplicates**

Append these tests to `tests/test_netlists.py`:

```python
def test_prepare_netlist_writes_fail_report_when_input_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert "exported input.scs is missing" in report.issues[0]
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()
    assert _load_netlist_report(project_dir) == report


def test_prepare_netlist_writes_fail_report_when_approved_variable_is_missing(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert report.approved_variables_template_status["WP"] is False
    assert "approved variable WP was not found in top-level parameters" in report.issues
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()


def test_prepare_netlist_writes_fail_report_for_duplicate_approved_variable(
    tmp_path: Path,
) -> None:
    project_dir = _project_with_input(
        tmp_path,
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
parameters FN=5
tran tran stop=10n
""",
    )

    report = prepare_netlist(project_dir)

    assert report.status == PassFail.FAIL
    assert "approved variable FN appears more than once in top-level parameters" in report.issues
    assert not (project_dir / "netlists" / "templates" / "template.scs").exists()
```

- [ ] **Step 2: Run the new tests**

Run:

```bash
pytest tests/test_netlists.py::test_prepare_netlist_writes_fail_report_when_input_is_missing tests/test_netlists.py::test_prepare_netlist_writes_fail_report_when_approved_variable_is_missing tests/test_netlists.py::test_prepare_netlist_writes_fail_report_for_duplicate_approved_variable -v
```

Expected: missing input may already PASS; missing/duplicate tests should FAIL if the Task 2 scanner writes a template on fail or status handling is incomplete.

- [ ] **Step 3: Harden `prepare_netlist()` fail behavior**

In `src/hermes_workflow/netlists.py`, update `prepare_netlist()` so it writes `template.scs` only when status is pass and removes any stale template output on fail. Use this exact status branch:

```python
    status = PassFail.PASS if not issues and all(template_status.values()) else PassFail.FAIL

    if status == PassFail.PASS:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_text, encoding="utf-8")
    elif template_path.exists():
        template_path.unlink()
```

Keep the report-writing branch unchanged after this status branch:

```python
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
```

- [ ] **Step 4: Run all netlist tests**

Run:

```bash
pytest tests/test_netlists.py -v
```

Expected: PASS.

- [ ] **Step 5: Run lint**

Run:

```bash
ruff check src/hermes_workflow/netlists.py tests/test_netlists.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/hermes_workflow/netlists.py tests/test_netlists.py
git commit -m "fix: report unsafe netlist templating failures"
```

---

### Task 4: CLI Command

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Append these tests to `tests/test_cli.py`:

```python
def test_cli_prepare_netlist_writes_template_and_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-netlist", str(project_dir)])

    assert result.exit_code == 0
    assert "netlist preparation passed" in result.stdout
    assert (project_dir / "netlists" / "templates" / "template.scs").exists()
    assert (project_dir / "reports" / "netlist_preparation_report.json").exists()


def test_cli_prepare_netlist_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])

    result = runner.invoke(app, ["prepare-netlist", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "netlist preparation failed" in result.stdout
    assert "exported input.scs is missing" in result.stdout
    assert "reports/netlist_preparation_report.json" in result.stdout
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run CLI tests to verify the command is missing**

Run:

```bash
pytest tests/test_cli.py::test_cli_prepare_netlist_writes_template_and_report tests/test_cli.py::test_cli_prepare_netlist_reports_failure_without_traceback -v
```

Expected: FAIL because `prepare-netlist` is not registered.

- [ ] **Step 3: Wire CLI command**

In `src/hermes_workflow/cli.py`, add this import near the existing workflow imports:

```python
from hermes_workflow.netlists import prepare_netlist
```

Add this command between `validate_command` and `package_command`:

```python
@app.command("prepare-netlist")
def prepare_netlist_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with exported netlists/input.scs."),
    ],
) -> None:
    try:
        report = prepare_netlist(project_dir)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("netlist preparation passed")
        return

    typer.echo("netlist preparation failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/netlist_preparation_report.json")
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Run CLI targeted tests**

Run:

```bash
pytest tests/test_cli.py::test_cli_prepare_netlist_writes_template_and_report tests/test_cli.py::test_cli_prepare_netlist_reports_failure_without_traceback -v
```

Expected: PASS.

- [ ] **Step 5: Run netlist and CLI tests**

Run:

```bash
pytest tests/test_netlists.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Run lint**

Run:

```bash
ruff check src/hermes_workflow/cli.py src/hermes_workflow/netlists.py tests/test_cli.py tests/test_netlists.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/hermes_workflow/cli.py src/hermes_workflow/netlists.py tests/test_cli.py tests/test_netlists.py
git commit -m "feat: add prepare netlist cli"
```

---

### Task 5: Local-Only Real Deck Smoke And Progress Note

**Files:**
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`

- [ ] **Step 1: Run full verification before manual smoke**

Run:

```bash
pytest -q
```

Expected: all tests PASS.

Run:

```bash
ruff check .
```

Expected: PASS.

- [ ] **Step 2: Manually smoke the local-only real examples without committing them**

Use a temporary project and copy only one local deck at a time into the temp project. Do not copy files into the repository.

Run these commands from the repo root:

```bash
hermes-workflow init /tmp/hermes_plan_c_smoke --force
cp /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs /tmp/hermes_plan_c_smoke/netlists/exported/input.scs
hermes-workflow prepare-netlist /tmp/hermes_plan_c_smoke
```

Expected: command exits 0 for `input.scs` if its approved variables match the template project variables `FN`, `WN`, `FP`, and `WP`.

Run the same shape for `input1.scs`, `input2.scs`, and `input3.scs` only after adapting a temp project's `variables.yaml` to the variables present in that local deck. Keep those temp edits under `/tmp/hermes_plan_c_smoke*`.

- [ ] **Step 3: Confirm real examples are not tracked**

Run:

```bash
git status --short
```

Expected: no `netlist_example` files and no real `input.scs` files appear in the repository status.

- [ ] **Step 4: Update execution progress**

Append this section to `docs/EXECUTION_PROGRESS_2026-05-29.md`:

```markdown

## Plan C: Netlist Template Contract

Status: C-1 implementation completed.

Implemented:

- `src/hermes_workflow/netlists.py`
- `hermes-workflow prepare-netlist`
- Sanitized netlist templating tests in `tests/test_netlists.py`

Important decisions:

- Real Virtuoso-exported `input.scs` examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` remain local-only and untracked.
- The templater rewrites only approved top-level `parameters` assignment values.
- Later variable references in device, subckt, source, analysis, include, model, and save statements remain unchanged.

Verification:

- `pytest -q`
- `ruff check .`
```

- [ ] **Step 5: Run doc/status check**

Run:

```bash
git diff -- docs/EXECUTION_PROGRESS_2026-05-29.md
```

Expected: only the Plan C progress section was added.

- [ ] **Step 6: Commit**

Run:

```bash
git add docs/EXECUTION_PROGRESS_2026-05-29.md
git commit -m "docs: record netlist template progress"
```

---

### Task 6: Review Gate And Final Verification

**Files:**
- No code edits expected unless review finds Critical or Important issues.

- [ ] **Step 1: Capture implementation range**

Run:

```bash
git log --oneline -6
```

Expected: the Plan C implementation commits from Tasks 1-5 are visible after `51253fe docs: design netlist template contract`.

- [ ] **Step 2: Run final local verification**

Run:

```bash
pytest -q
```

Expected: all tests PASS.

Run:

```bash
ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run spec review gate**

Use the project Claude review MCP if available:

```text
claude-review.spec_review
repo_path: /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
task_text: docs/superpowers/specs/2026-05-30-netlist-template-contract-design.md and docs/superpowers/plans/2026-05-30-netlist-template-contract.md
implementer_report: Summarize Task 1-5 commits, tests, and local-only real deck policy.
git_range: 51253fe..HEAD
extra_context: Verify Plan C C-1 only; real input.scs examples must remain untracked.
```

If MCP is unavailable, use the existing direct Claude CLI reviewer flow documented in `docs/CLAUDE_REVIEW_MCP.md`.

Expected: `Spec compliant`. If issues are found, fix Critical and Important issues, then rerun tests and review.

- [ ] **Step 4: Run code-quality review gate**

Use:

```text
claude-review.code_quality_review
repo_path: /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
requirements: Plan C C-1 netlist template contract; safe top-level parameter templating only; existing report schema; CLI command.
base_sha: 51253fe
head_sha: HEAD
description: Adds netlist preparation module, tests, CLI command, and progress docs.
extra_context: Treat real input.scs examples as local-only references and confirm they are not committed.
```

Expected: no Critical or Important issues. If Critical or Important issues appear, fix them before completion.

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: clean worktree after review fixes are committed.

Run:

```bash
git log --oneline -8
```

Expected: Plan C design and implementation commits are visible.
