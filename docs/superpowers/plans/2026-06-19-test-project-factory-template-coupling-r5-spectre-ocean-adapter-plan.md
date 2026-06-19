# R5 Spectre/OCEAN Adapter Template-Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove direct packaged-template usage from `tests/test_spectre_ocean_adapter.py` while preserving local adapter behavior and downstream helper compatibility.

**Architecture:** Move the single-run adapter fixture from `create_project_from_template` plus `TEMPLATE_TEXT` to `create_approved_generic_project` plus `prepare_real_run`. Keep multi-testbench and corner helpers requirement-driven. Preserve exported helper names so consumer tests do not need edits.

**Tech Stack:** Python tests, pytest, `tests.project_factory.create_approved_generic_project`, existing adapter fake runners, YAML/JSON test artifacts.

---

## File Map

- Modify `tests/test_spectre_ocean_adapter.py`
  - Remove direct packaged-template import and old `TEMPLATE_TEXT`.
  - Import `create_approved_generic_project`.
  - Rewrite `_create_ready_real_run_project`.
  - Replace project-name and old Spectre-setting assumptions where needed.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_spectre_ocean_adapter.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R5 status and remove adapter from remaining waves.

## Task 1: Baseline and Consumer Mapping

**Files:**
- Verify: `tests/test_spectre_ocean_adapter.py`
- Verify: known consumers

- [ ] **Step 1: Run target baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected:

```text
87 passed, 13 warnings
```

- [ ] **Step 2: Run consumer regression baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_real_run.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
161 passed, 13 warnings
```

- [ ] **Step 3: Confirm source consumers**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_spectre_ocean_adapter\|tests.test_spectre_ocean_adapter" tests || true
```

Expected known consumers:

```text
tests/test_real_run.py
tests/test_remote_spectre_ocean.py
tests/test_remote_spectre_ocean_waveform.py
tests/test_template_coupling_guard.py
```

- [ ] **Step 4: Capture direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected before R5:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Task 2: Replace Single-Run Project Setup

**Files:**
- Modify: `tests/test_spectre_ocean_adapter.py`

- [ ] **Step 1: Update imports**

Remove `create_project_from_template` from:

```python
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
```

Keep:

```python
from hermes_workflow.package import (
    build_execution_package,
    sha256_file,
)
```

Add:

```python
from tests.project_factory import create_approved_generic_project
```

- [ ] **Step 2: Remove `TEMPLATE_TEXT`**

Delete:

```python
TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""
```

The generic factory writes `netlists/templates/template.scs`.

- [ ] **Step 3: Rewrite `_create_ready_real_run_project`**

Replace the function with:

```python
def _create_ready_real_run_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        name="spectre_ocean_adapter_project",
        created_at_utc="2026-06-02T00:00:00Z",
        max_evaluations=12,
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir
```

Do not call `build_execution_package`, `write_pass_reports`, or `decide_first_real_run` inside this helper; `create_approved_generic_project` already handles the package and approval gate for a generic project.

- [ ] **Step 4: Run target to reveal project-name/settings assumptions**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected initially may fail on hardcoded old assumptions. Fix those in Task 3.

## Task 3: Remove Old Single-Run Assumptions

**Files:**
- Modify: `tests/test_spectre_ocean_adapter.py`

- [ ] **Step 1: Replace `FakeSuccessRunner` project-name assertion**

Find:

```python
assert cwd.name == "bridge_test_inv"
```

Replace with a contract assertion that does not encode the old template project name:

```python
assert (cwd / "config" / "project_config.yaml").is_file()
```

This still verifies the Ocean runner is invoked with the project root as `cwd`.

- [ ] **Step 2: Derive Spectre thread assertions**

If these assertions fail:

```python
assert "+mt=10" in runner.commands[0]
assert manifest["simulator"]["threads_per_run"] == 10
```

Replace them with generic-project-derived values. Add a helper if needed:

```python
def _prepared_threads_per_run(project_dir: Path) -> int:
    request = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metric_extraction_request.json"
    )
    return int(request["spectre"]["threads_per_run"])
```

Then assert:

```python
threads_per_run = _prepared_threads_per_run(project_dir)
assert f"+mt={threads_per_run}" in runner.commands[0]
assert manifest["simulator"]["threads_per_run"] == threads_per_run
```

Do not hardcode `2` unless the test is specifically checking the generic factory default.

- [ ] **Step 3: Keep parser-only metric names out of scope**

Do not rewrite pure `parse_ocean_scalars` table tests solely because they use `rise` or `fall` as arbitrary TSV row names. R5 drift guard checks only direct template-coupling tokens:

```text
create_project_from_template
bridge_test_inv
FN
WN
FP
WP
TEMPLATE_TEXT
```

- [ ] **Step 4: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected:

```text
87 passed, 13 warnings
```

## Task 4: Guard and Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove adapter from allowlist**

Remove:

```python
"tests/test_spectre_ocean_adapter.py",
```

Expected allowlist count:

```text
3 -> 2
```

- [ ] **Step 2: Update remaining waves**

In the inventory report, remove `tests/test_spectre_ocean_adapter.py` from remaining remote/adapter flows.

Remaining direct template migration file after R5 should be:

```text
tests/test_remote_spectre_ocean.py
```

`tests/test_package.py` remains intentional template behavior.

- [ ] **Step 3: Add R5 verification section**

Add:

```markdown
### R5 Spectre/OCEAN Adapter

- `pytest tests/test_spectre_ocean_adapter.py -q` -> `87 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_spectre_ocean_adapter.py tests/test_template_coupling_guard.py -q` -> `88 passed, 13 warnings`
- `pytest tests/test_spectre_ocean_adapter.py tests/test_real_run.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q` -> `161 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep forbidden template-coupling tokens over `tests/test_spectre_ocean_adapter.py` -> no matches
- grep cross-imports -> known consumers covered by consumer regression
- `ALLOWED_TEMPLATE_CALLERS` count: 3 -> 2.
```

## Task 5: Full Verification

**Files:**
- Verify: target, guard, consumers, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected:

```text
87 passed, 13 warnings
```

- [ ] **Step 2: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run target plus guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
88 passed, 13 warnings
```

- [ ] **Step 4: Run consumer regression group**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_real_run.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
161 passed, 13 warnings
```

- [ ] **Step 5: Run full suite**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 6: Run ruff**

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 8: Confirm release checkout untouched**

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 9: Run drift grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" tests/test_spectre_ocean_adapter.py || true
```

Expected: no output.

- [ ] **Step 10: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_spectre_ocean_adapter\|tests.test_spectre_ocean_adapter" tests || true
```

Expected known consumers only:

```text
tests/test_real_run.py
tests/test_remote_spectre_ocean.py
tests/test_remote_spectre_ocean_waveform.py
```

The guard line should disappear after guard update.

- [ ] **Step 11: Run direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
```

## Task 6: Final Report

Report:

1. Files modified.
2. Spectre/OCEAN adapter migration summary.
3. Helper compatibility status.
4. Guard allowlist count `3 -> 2`.
5. Exact verification results.
6. Drift grep result.
7. Cross-import grep result.
8. Direct template caller list.
9. Release checkout status.
10. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.
11. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
