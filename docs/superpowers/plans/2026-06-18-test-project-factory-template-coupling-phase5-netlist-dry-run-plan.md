# Netlist and Dry-Run Preflight Template Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `tests/test_netlists.py` and `tests/test_dry_run.py` from packaged-template setup to the generic project factory.

**Architecture:** Add one test-only helper for generic preflight project creation, approved-variable lookup, exported deck generation, and template generation. Then update netlist and dry-run tests to assert the same preflight contracts with generated variable names instead of the old release-template circuit.

**Tech Stack:** Python 3.11, pytest, PyYAML, repo-local `tests/project_factory.py`, existing Hermes workflow APIs.

---

## File Structure

- Create `tests/netlist_dry_run_helpers.py`
  - Creates valid generic projects through `tests.project_factory.create_generic_project`.
  - Reads approved variable names from `config/variables.yaml`.
  - Writes exported input decks and template decks with generated variable names.
  - Adds testbench metadata to generic metrics for multi-testbench netlist tests.
- Modify `tests/test_netlists.py`
  - Replace `create_project_from_template()` setup with helper-based generic projects.
  - Replace old variable assertions with generated variable assertions.
- Modify `tests/test_dry_run.py`
  - Replace `create_project_from_template()` setup with helper-based generic projects.
  - Replace lower-bound and placeholder assertions with generated variable names.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_netlists.py` and `tests/test_dry_run.py`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Record Phase 5 status and remaining deferred work.

## Task 0: Baseline Audit

**Files:**
- Read: `tests/test_netlists.py`
- Read: `tests/test_dry_run.py`
- Read: `tests/project_factory.py`
- Read: `src/hermes_workflow/netlists.py`
- Read: `src/hermes_workflow/dry_run.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm clean starting state**

Run:

```bash
git status --short
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Dev checkout has only expected untracked planning files or implementation files.
- Release checkout prints no modified files.

- [ ] **Step 2: Confirm current coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_netlists.py tests/test_dry_run.py || true
grep -R -n "from tests.test_netlists\|from tests.test_dry_run" tests || true
```

Expected before migration:

- The first command shows old coupling in the two target files.
- The second command shows no external tests importing these files.

## Task 1: Add Shared Netlist/Dry-Run Helper

**Files:**
- Create: `tests/netlist_dry_run_helpers.py`
- Test: `tests/test_project_factory.py`

- [ ] **Step 1: Create the helper module shell**

Create `tests/netlist_dry_run_helpers.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from tests.project_factory import create_generic_project

def create_preflight_project(tmp_path: Path) -> Path:
    return create_generic_project(tmp_path)

def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    names = [variable["name"] for variable in payload["variables"]]
    assert len(names) == 2
    return names[0], names[1]
```

- [ ] **Step 2: Add deck/template builders**

Extend the helper:

```python
def top_level_parameters_line(
    project_dir: Path,
    *,
    include_first: bool = True,
    include_second: bool = True,
    duplicate_first: bool = False,
    whitespace_units: bool = False,
    extra: str = "temperature=27",
) -> str:
    first, second = variable_names(project_dir)
    parts = ["parameters", extra]
    if include_first:
        parts.append(f"{first}=4")
    if include_second:
        parts.append(f"{second}=0.6 u" if whitespace_units else f"{second}=0.6u")
    line = " ".join(parts)
    if duplicate_first:
        line += f"\nparameters {first}=5"
    return line

def exported_deck(
    project_dir: Path,
    *,
    parameter_line: str | None = None,
    body: str = "tran tran stop=10n\n",
) -> str:
    return "simulator lang=spectre\n" + (
        parameter_line or top_level_parameters_line(project_dir)
    ) + "\n" + body

def template_text(
    project_dir: Path,
    *,
    omit_first: bool = False,
    omit_second: bool = False,
    unexpected: str | None = None,
    malformed: str | None = None,
) -> str:
    first, second = variable_names(project_dir)
    parts = ["parameters"]
    if not omit_first:
        parts.append(f"{first}={{{{{first}}}}}")
    if not omit_second:
        parts.append(f"{second}={{{{{second}}}}}")
    if unexpected is not None:
        parts.append(f"{unexpected}={{{{{unexpected}}}}}")
    if malformed is not None:
        parts.append(f"BAD={{{{ {malformed} }}}}")
    return "simulator lang=spectre\n" + " ".join(parts) + "\ntran tran stop=10n\n"
```

These helper functions may be adjusted during implementation if exact formatting
needs to match the current parser, but the helper must remain generic and must not
use the old release-template variable names.

- [ ] **Step 3: Add project writers**

Extend the helper:

```python
def project_with_exported_input(tmp_path: Path, deck_text: str) -> Path:
    project_dir = create_preflight_project(tmp_path)
    input_path = project_dir / "netlists" / "exported" / "input.scs"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(deck_text, encoding="utf-8")
    return project_dir

def project_with_template(tmp_path: Path, text: str | None = None) -> Path:
    project_dir = create_preflight_project(tmp_path)
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text or template_text(project_dir), encoding="utf-8")
    return project_dir
```

- [ ] **Step 4: Add multi-testbench metric helper**

Extend the helper:

```python
def assign_all_metrics_to_testbench(project_dir: Path, testbench_id: str) -> None:
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    for metric in payload.get("metrics", []):
        metric["testbench"] = testbench_id
    metrics_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 5: Run helper smoke check**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py -q
```

Expected:

- `3 passed`

## Task 2: Migrate `tests/test_dry_run.py`

**Files:**
- Modify: `tests/test_dry_run.py`
- Test: `tests/test_dry_run.py`

- [ ] **Step 1: Replace setup imports and helper**

Remove:

```python
from hermes_workflow.package import create_project_from_template
```

Import:

```python
import yaml

from tests.netlist_dry_run_helpers import (
    project_with_template,
    template_text,
    variable_names,
)
```

Replace `_create_project_with_template()` with either direct calls to
`project_with_template()` or a local alias:

```python
def _create_project_with_template(tmp_path: Path, template: str | None = None) -> Path:
    return project_with_template(tmp_path, template)
```

- [ ] **Step 2: Generalize lower-bound rendering assertions**

In `test_run_dry_run_renders_lower_bound_candidate`, use the default generic
template:

```python
project_dir = _create_project_with_template(tmp_path)
first, second = variable_names(project_dir)
```

Replace exact rendered assertions with:

```python
assert f"{first}=1" in rendered
assert f"{second}=0.1u" in rendered
```

Keep all report status, placeholder, metrics/objective/constraints, ledger, and
state assertions.

- [ ] **Step 3: Generalize missing template test**

Use a generic project and remove the factory-provided template:

```python
project_dir = _create_project_with_template(tmp_path)
(project_dir / "netlists" / "templates" / "template.scs").unlink()
```

Keep the expected issue:

```python
"template.scs is missing: netlists/templates/template.scs"
```

- [ ] **Step 4: Generalize placeholder failure tests**

Use generated variable names:

```python
first, second = variable_names(project_dir)
project_dir = _create_project_with_template(
    tmp_path,
    template_text(project_dir, omit_second=True),
)
```

Because `template_text()` needs a project to know variable names, the implementation
may create the project first, then overwrite the template:

```python
project_dir = _create_project_with_template(tmp_path)
first, second = variable_names(project_dir)
template_path = project_dir / "netlists" / "templates" / "template.scs"
template_path.write_text(template_text(project_dir, omit_second=True), encoding="utf-8")
```

Expected missing-placeholder issue:

```python
f"approved variable {second} placeholder is missing from template"
```

Unexpected placeholder tests should use a neutral name such as `EXTRA_GAIN`.

- [ ] **Step 5: Generalize stale-render and write-failure tests**

Use the default generic template for pass cases. When adding an unexpected
placeholder, write:

```python
template_path.write_text(
    template_text(project_dir, unexpected="EXTRA_GAIN"),
    encoding="utf-8",
)
```

Keep the existing assertions that stale render output is removed and write
failures are reported.

- [ ] **Step 6: Generalize constraint false-but-evaluable test**

Parse `metrics.yaml` and mutate the first constraint to a false but valid value:

```python
metrics_path = project_dir / "config" / "metrics.yaml"
payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
assert payload["constraints"]
payload["constraints"][0]["value"] = "0 W"
metrics_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

Keep:

```python
assert report.status == PassFail.PASS
assert report.constraints_ok is True
assert report.issues == []
```

- [ ] **Step 7: Run dry-run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_dry_run.py -q
```

Expected:

- All tests in `tests/test_dry_run.py` pass.

## Task 3: Migrate `tests/test_netlists.py`

**Files:**
- Modify: `tests/test_netlists.py`
- Test: `tests/test_netlists.py`

- [ ] **Step 1: Replace setup imports and helper**

Remove:

```python
from hermes_workflow.package import create_project_from_template
```

Import:

```python
from tests.netlist_dry_run_helpers import (
    assign_all_metrics_to_testbench,
    exported_deck,
    project_with_exported_input,
    create_preflight_project,
    top_level_parameters_line,
    variable_names,
)
```

Replace `_project_with_input()` with:

```python
def _project_with_input(tmp_path: Path, deck_text: str) -> Path:
    return project_with_exported_input(tmp_path, deck_text)
```

- [ ] **Step 2: Generalize single-line and continuation templating tests**

Use generated variable names:

```python
project_dir = create_preflight_project(tmp_path)
first, second = variable_names(project_dir)
deck = exported_deck(
    project_dir,
    parameter_line=f"parameters temperature=27 {first}=4 {second}=0.6u",
    body=f"M0 (VOUT IN VSS VSS) nmos w={second}*{first} l=45n\ntran tran stop=10n\ndcOp dc oppoint=rawfile\n",
)
project_dir = project_with_exported_input(tmp_path, deck)
```

Assert:

```python
assert f"{first}={{{{{first}}}}}" in template_text
assert f"{second}={{{{{second}}}}}" in template_text
assert "temperature=27" in template_text
assert f"w={second}*{first}" in template_text
assert report.approved_variables_template_status == {first: True, second: True}
```

Preserve analysis statement assertions.

- [ ] **Step 3: Generalize instance/subckt assignment test**

Use generated variables at the top level and also in an instance assignment:

```python
body = (
    "subckt wrapped IN OUT VDD VSS\n"
    f"M0 (OUT IN VSS VSS) nmos w={second}*{first} l=45n\n"
    "ends wrapped\n"
    f"X0 (IN OUT VDD VSS) wrapped {first}=99 {second}=99u\n"
    "ac ac start=1 stop=10G\n"
)
```

Assert the top-level line is templated and the instance assignment remains literal.

- [ ] **Step 4: Generalize missing exported input test**

Create a generic project and remove the factory-provided exported input:

```python
project_dir = create_preflight_project(tmp_path)
(project_dir / "netlists" / "exported" / "input.scs").unlink()
```

Keep the existing failure assertions.

- [ ] **Step 5: Generalize missing/duplicate approved variable tests**

Use generated variable names:

```python
first, second = variable_names(project_dir)
parameter_line = f"parameters temperature=27 {first}=4"
```

Expected missing issue:

```python
f"approved variable {second} was not found in top-level parameters"
```

For duplicate:

```python
parameter_line = f"parameters temperature=27 {first}=4 {second}=0.6u\nparameters {first}=5"
```

Expected duplicate issue:

```python
f"approved variable {first} appears more than once in top-level parameters"
```

- [ ] **Step 6: Generalize whitespace-unit and subckt-fail-closed tests**

For whitespace-unit templating, use:

```python
parameter_line = f"parameters temperature=27 {first}=4 {second}=0.6 u"
```

Assert:

```python
assert f"{second}={{{{{second}}}}}" in template_text
assert f"{second}={{{{{second}}}}} u" not in template_text
```

For subckt fail-closed, put both approved variables inside a subckt and omit them
from the top-level parameter line. Assert messages using generated names.

- [ ] **Step 7: Generalize multi-testbench helper**

Update `_project_with_testbench_input_and_corners()` to:

1. Create a generic project through `create_preflight_project(tmp_path)`.
2. Write `config/testbenches.yaml`.
3. Use `assign_all_metrics_to_testbench(project_dir, "tb1")`.
4. Write the testbench exported input under:
   `netlists/testbenches/tb1/exported/input.scs`.
5. Write the legacy exported input only if the test needs it.
6. Write `process_corners.yaml` when `corner_config` is provided.

Replace old variables in multi-testbench deck strings with generated variables.
Preserve assertions that corner templates exist, model section changes, corner
variables change, and no corner directory is written when no corner config exists.

- [ ] **Step 8: Leave pure corner-rendering tests generic**

Pure `render_corner_netlist_template()` tests may continue to use arbitrary names
such as `F`, `W`, `temperature`, or `vdd`, because they do not use the packaged
release template and they intentionally test generic string rewriting. Do not
rewrite those unless they still contain the old release-template tuple.

- [ ] **Step 9: Run netlist tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_netlists.py -q
```

Expected:

- All tests in `tests/test_netlists.py` pass.

## Task 4: Shrink Guard and Update Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove migrated files from allowlist**

Remove:

```python
"tests/test_dry_run.py",
"tests/test_netlists.py",
```

Expected allowlist count after this change: 16.

- [ ] **Step 2: Update inventory**

Update
`docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
with:

- Phase 5 status.
- New helper file.
- Files migrated.
- Guard count 18 -> 16.
- Exact verification command results.
- Remaining deferred groups.

- [ ] **Step 3: Run guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

- `1 passed`

## Task 5: Verification

**Files:**
- Verify: target tests, guard, regression group, full suite

- [ ] **Step 1: Run target pair**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_netlists.py tests/test_dry_run.py -q
```

Expected:

- Both target files pass together.

- [ ] **Step 2: Run drift checks**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_netlists.py tests/test_dry_run.py tests/netlist_dry_run_helpers.py || true
grep -R -n "from tests.test_netlists\|from tests.test_dry_run" tests || true
```

Expected:

- No matches in the first command.
- No cross-test imports in the second command.

- [ ] **Step 3: Run Phase 1-5 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py \
  tests/test_real_run.py \
  tests/test_real_run_recovery.py \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  tests/test_netlists.py \
  tests/test_dry_run.py \
  -q
```

Expected:

- Regression group passes.

- [ ] **Step 4: Run final checks**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Full suite passes.
- Ruff passes.
- Diff check is clean.
- Release checkout prints no modified files.

## Stop Conditions

Stop and report instead of broadening scope if:

- a production source change appears necessary,
- approval/package tests must be changed to make these two files pass,
- the generic factory needs new production-like behavior beyond test setup,
- remote/adapter/backend tests become involved,
- full-suite failures reveal a separate existing product bug.
