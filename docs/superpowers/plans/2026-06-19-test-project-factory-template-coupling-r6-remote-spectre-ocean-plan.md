# R6 Remote Spectre/OCEAN Template-Coupling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove direct packaged-template usage and legacy `rise/fall/DC` fallbacks from `tests/test_remote_spectre_ocean.py`.

**Architecture:** Replace the single direct template project helper with a generic project built by `tests.project_factory.create_generic_project`, then keep remote waveform helper imports stable. Convert fake remote scalar generation to require a real metric request instead of falling back to old inverter metrics.

**Tech Stack:** Python tests, pytest, `tests.project_factory.create_generic_project`, remote Spectre/OCEAN fake runners, JSON/YAML artifact fixtures.

---

## File Map

- Modify `tests/test_remote_spectre_ocean.py`
  - Remove `create_project_from_template`.
  - Import `yaml` and `create_generic_project`.
  - Add `_variable_names`.
  - Rewrite `_create_ready_multi_corner_single_testbench_project`.
  - Remove legacy scalar fallback rows.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_remote_spectre_ocean.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add R6 status and state only `tests/test_package.py` remains intentional.

## Task 1: Baseline and Consumer Mapping

**Files:**
- Verify: `tests/test_remote_spectre_ocean.py`
- Verify: `tests/test_remote_spectre_ocean_waveform.py`

- [ ] **Step 1: Run target baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
38 passed, 13 warnings
```

- [ ] **Step 2: Run target plus waveform consumer baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
45 passed, 13 warnings
```

- [ ] **Step 3: Confirm source consumers**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_spectre_ocean\|tests.test_remote_spectre_ocean" tests || true
```

Expected known consumers before guard update:

```text
tests/test_template_coupling_guard.py
tests/test_remote_spectre_ocean_waveform.py
```

- [ ] **Step 4: Capture direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected before R6:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
```

## Task 2: Replace Direct Template Project Setup

**Files:**
- Modify: `tests/test_remote_spectre_ocean.py`

- [ ] **Step 1: Update imports**

Change:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template, sha256_file
```

to:

```python
from hermes_workflow.package import build_execution_package, sha256_file
```

Add:

```python
import yaml

from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add `_variable_names` helper**

Add near `_metric_names`:

```python
def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    variables = payload["variables"]
    return tuple(str(variable["name"]) for variable in variables)
```

- [ ] **Step 3: Rewrite `_create_ready_multi_corner_single_testbench_project`**

Replace its project setup body so it uses `create_generic_project`:

```python
def _create_ready_multi_corner_single_testbench_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name="remote_single_tb_corner_project",
    )
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_text = (project_dir / "netlists" / "templates" / "template.scs").read_text(
        encoding="utf-8"
    )
    for corner_id in corner_ids:
        corner_template = (
            project_dir / "netlists" / "corners" / corner_id / "template.scs"
        )
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-13T00:20:00Z")
    return project_dir
```

- [ ] **Step 4: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected may still fail until legacy fallback cleanup is complete. Continue to Task 3.

## Task 3: Remove Legacy Scalar Fallbacks

**Files:**
- Modify: `tests/test_remote_spectre_ocean.py`

- [ ] **Step 1: Rewrite `_ocean_scalars_tsv` fail-fast behavior**

Replace the docstring and `if not request:` branch with:

```python
def _ocean_scalars_tsv(request: dict | None) -> str:
    """Build an ocean_scalars.tsv body from a metric request."""
    if request is None:
        raise AssertionError("metric request is required to build ocean_scalars.tsv")
    header = "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
    rows = "".join(
        f"{metric['name']}\t1e-12\t{metric['unit']}\tpass\t{metric['expression_sha256']}\t\n"
        for metric in request["metrics"]
    )
    return header + rows
```

- [ ] **Step 2: Update `MultiTestbenchFakeRunner._resolve_metric_names`**

Replace:

```python
return ["rise", "fall", "DC"]
```

with request-derived behavior:

```python
request = _request_for_metrics_dir(local_path)
if request is not None:
    return [str(metric["name"]) for metric in request["metrics"]]
raise AssertionError(f"metric request is required for {local_path}")
```

- [ ] **Step 3: Update `MetricFailFakeRunner` fallback**

Replace the `else:` branch that writes legacy rows with:

```python
else:
    raise AssertionError(
        f"metric request is required to build failing ocean_scalars.tsv for {local_path}"
    )
```

- [ ] **Step 4: Rename local variable `fall_metric`**

In `test_remote_adapter_propagates_metric_failure`, rename:

```python
fall_metric = next(...)
assert fall_metric["status"] == "failed"
```

to:

```python
failed_metric = next(...)
assert failed_metric["status"] == "failed"
```

This avoids leaving a stale `fall` label in a generic metric test.

- [ ] **Step 5: Remove stale comments/docstrings**

Remove comments/docstrings that mention:

```text
legacy rise/fall/DC
fall semantics
create_project_from_template
bridge_test_inv
```

## Task 4: Target Verification and Drift Cleanup

**Files:**
- Modify: `tests/test_remote_spectre_ocean.py`

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
38 passed, 13 warnings
```

- [ ] **Step 2: Run waveform consumer**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
45 passed, 13 warnings
```

- [ ] **Step 3: Run template-coupling grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_spectre_ocean.py || true
```

Expected: no output.

- [ ] **Step 4: Run legacy fallback grep**

```bash
grep -nE "\b(rise|fall|DC)\b" tests/test_remote_spectre_ocean.py || true
```

Expected: no output. If it prints a genuinely unrelated English word, prefer renaming/comment cleanup to keep the final drift check simple.

## Task 5: Guard and Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove remote Spectre/OCEAN from allowlist**

Remove:

```python
"tests/test_remote_spectre_ocean.py",
```

Expected allowlist count:

```text
2 -> 1
```

- [ ] **Step 2: Update remaining waves**

In the inventory report, remove `tests/test_remote_spectre_ocean.py` from remaining remote/adapter flows.

State that the only remaining direct template caller is:

```text
tests/test_package.py
```

- [ ] **Step 3: Add R6 verification section**

Add:

```markdown
### R6 Remote Spectre/OCEAN

- `pytest tests/test_remote_spectre_ocean.py -q` -> `38 passed, 13 warnings`
- `pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q` -> `45 passed, 13 warnings`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py tests/test_template_coupling_guard.py -q` -> `46 passed, 13 warnings`
- `pytest -q` -> `1194 passed, 13 warnings`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep template-coupling tokens over `tests/test_remote_spectre_ocean.py` -> no matches
- grep legacy `rise/fall/DC` tokens over `tests/test_remote_spectre_ocean.py` -> no matches
- grep cross-imports -> known waveform consumer only
- `ALLOWED_TEMPLATE_CALLERS` count: 2 -> 1.
```

## Task 6: Full Verification

**Files:**
- Verify: target, waveform consumer, guard, full suite, lint, release checkout

- [ ] **Step 1: Run target**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
38 passed, 13 warnings
```

- [ ] **Step 2: Run target plus waveform consumer**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
45 passed, 13 warnings
```

- [ ] **Step 3: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Run target plus waveform plus guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
46 passed, 13 warnings
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

- [ ] **Step 9: Run template-coupling grep**

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_spectre_ocean.py || true
```

Expected: no output.

- [ ] **Step 10: Run legacy fallback grep**

```bash
grep -nE "\b(rise|fall|DC)\b" tests/test_remote_spectre_ocean.py || true
```

Expected: no output.

- [ ] **Step 11: Run cross-import grep**

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_spectre_ocean\|tests.test_remote_spectre_ocean" tests || true
```

Expected known consumer only:

```text
tests/test_remote_spectre_ocean_waveform.py
```

The guard line should disappear after guard update.

- [ ] **Step 12: Run direct template caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

## Task 7: Final Report

Report:

1. Files modified.
2. Remote Spectre/OCEAN migration summary.
3. Waveform helper compatibility status.
4. Legacy fallback cleanup status.
5. Guard allowlist count `2 -> 1`.
6. Exact verification results.
7. Drift grep result.
8. Cross-import grep result.
9. Direct template caller list.
10. Release checkout status.
11. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.
12. Remaining direct template caller: `tests/test_package.py` only.

Do not commit, tag, push, or publish.
