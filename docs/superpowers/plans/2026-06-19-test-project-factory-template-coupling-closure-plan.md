# Template Coupling Cleanup Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the template-coupling guard and inventory from migration-mode wording to final-state intentional API coverage.

**Architecture:** Keep the runtime code and migrated tests unchanged. Rename the guard's allowlist to an intentional product-template caller contract, update the inventory's remaining-work language, and optionally add a compact closure report.

**Tech Stack:** Python pytest guard, markdown documentation, repository grep verification.

---

## File Map

- Modify `tests/test_template_coupling_guard.py`
  - Rename `ALLOWED_TEMPLATE_CALLERS`.
  - Rename the guard test.
  - Keep `tests/test_package.py` as the only intentional caller.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Replace stale remaining-wave guidance with final guard state.
  - Keep phase history.
- Optional create `docs/superpowers/reports/2026-06-19-test-project-factory-template-coupling-closure.md`
  - Summarize final state and verification.

## Task 1: Baseline Final Caller State

**Files:**
- Verify only.

- [ ] **Step 1: Run direct caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

- [ ] **Step 2: Run guard baseline**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

## Task 2: Rename Guard Contract

**Files:**
- Modify: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Replace the constant and test name**

Replace the file contents with:

```python
from __future__ import annotations

from pathlib import Path

INTENTIONAL_TEMPLATE_API_CALLERS = {
    "tests/test_package.py",
}


def test_create_project_from_template_usage_is_limited_to_product_template_api_tests() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "tests").glob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/test_template_coupling_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        if (
            "create_project_from_template" in text
            and relative not in INTENTIONAL_TEMPLATE_API_CALLERS
        ):
            offenders.append(relative)

    assert offenders == []
```

- [ ] **Step 2: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

## Task 3: Update Inventory Final State

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Replace stale remaining-wave section**

Find the section beginning with:

```markdown
## Remaining migration waves
```

Replace through the end of the stale "How to continue" instructions with:

```markdown
## Final Guard State

All non-product test files have been migrated away from direct
`create_project_from_template()` usage.

The only intentional direct caller under `tests/` is:

- `tests/test_package.py` — product/template API coverage for packaged template
  creation, packaged resources, execution-package behavior over the packaged
  template, and init/template materialization semantics.

`tests/test_template_coupling_guard.py` enforces this contract. New tests that
need a valid project should use `tests/project_factory.py` or an existing
generic helper rather than calling the packaged-template API directly.
```

- [ ] **Step 2: Update references to the guard name**

Where the inventory talks about `ALLOWED_TEMPLATE_CALLERS` in the current/final state, use:

```text
INTENTIONAL_TEMPLATE_API_CALLERS
```

Historical phase entries can keep old allowlist counts if they clearly refer to past phases.

- [ ] **Step 3: Run stale wording grep**

```bash
grep -R --exclude-dir=__pycache__ -n "Remaining migration waves\|Pick one file from a wave" docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md || true
```

Expected: no output.

## Task 4: Optional Closure Report

**Files:**
- Optional create: `docs/superpowers/reports/2026-06-19-test-project-factory-template-coupling-closure.md`

- [ ] **Step 1: Create closure report if useful**

If creating the report, use this content:

```markdown
# Test Project Factory / Template Coupling Cleanup Closure

## Final State

All non-product tests have been migrated away from direct
`create_project_from_template()` usage.

The only intentional direct caller under `tests/` is `tests/test_package.py`,
which exercises the product/template API itself.

## Guard

`tests/test_template_coupling_guard.py` enforces the final contract through
`INTENTIONAL_TEMPLATE_API_CALLERS`.

## Verification

- `pytest tests/test_template_coupling_guard.py -q`
- `pytest -q`
- `ruff check src tests`
- `git diff --check`
- `git -C ../ic-auto-opt-workflow-v0.1 status --short`
- `rg -l "create_project_from_template" tests | sort`

## Release Boundary

The release checkout is intentionally untouched by this cleanup. Release sync
and publication remain separate release work.
```

## Task 5: Full Verification

**Files:**
- Verify guard, full suite, lint, release checkout.

- [ ] **Step 1: Run guard**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 2: Run full suite**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 3: Run ruff**

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Confirm release checkout untouched**

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 6: Run direct caller list**

```bash
rg -l "create_project_from_template" tests | sort
```

Expected:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

- [ ] **Step 7: Run stale migration wording grep**

```bash
grep -R --exclude-dir=__pycache__ -n "ALLOWED_TEMPLATE_CALLERS\|Remaining migration waves\|Pick one file from a wave" tests docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md || true
```

Expected: no output, except historical phase references if intentionally retained. Prefer no output for current/final-state sections.

## Task 6: Final Report

Report:

1. Files modified/created.
2. Final guard contract.
3. Final direct caller list.
4. Verification results.
5. Release checkout status.
6. Confirmation that `src/`, release checkout, and `graphify-out/` were untouched.

Do not tag, push, publish, or modify the release checkout.
