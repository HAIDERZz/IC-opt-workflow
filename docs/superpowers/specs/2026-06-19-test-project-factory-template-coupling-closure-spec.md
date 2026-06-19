# Template Coupling Cleanup Closure Spec

## Objective

Close the test project factory/template-coupling cleanup after R6 by tightening the guard language and inventory so the repository no longer reads as if more non-product migrations remain.

The cleanup is complete when the only direct `create_project_from_template()` usage under `tests/` is the intentional product/template API coverage in `tests/test_package.py`, plus the guard that enforces that contract.

## Current State

R6 Remote Spectre/OCEAN has been committed as:

```text
969a172 test: decouple remote spectre ocean tests from template
```

Current direct callers:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

`tests/test_package.py` is intentionally direct because it tests:

- `create_project_from_template()`
- packaged template tree resources
- `hermes-workflow init` / template materialization semantics
- execution-package behavior over the packaged template

## In Scope

Allowed files:

- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- optional new closure report:
  - `docs/superpowers/reports/2026-06-19-test-project-factory-template-coupling-closure.md`

## Out of Scope

Do not modify:

- `src/`
- test files other than `tests/test_template_coupling_guard.py`
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`
- old phase prompt/spec/plan files

If any out-of-scope file appears required, stop and report the exact reason.

## Required Behavior

### Guard Becomes Intentional Caller Contract

Rename the migration-era allowlist to a final-state name.

Recommended:

```python
INTENTIONAL_TEMPLATE_API_CALLERS = {
    "tests/test_package.py",
}
```

Rename the test to make the contract explicit:

```python
def test_create_project_from_template_usage_is_limited_to_product_template_api_tests() -> None:
```

The guard should still scan `tests/*.py`, ignore itself, and fail if any other file contains `create_project_from_template`.

It must not allow broad future direct template usage by accident.

### Inventory Reflects Final State

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md` so it no longer says or implies there are remaining migration waves.

Replace the stale "Remaining migration waves" / "How to continue" section with a final state section:

```markdown
## Final Guard State

All non-product test files have been migrated away from direct
`create_project_from_template()` usage.

The only intentional direct caller under `tests/` is:

- `tests/test_package.py` — product/template API coverage for packaged template
  creation, packaged resources, and init/template materialization behavior.

`tests/test_template_coupling_guard.py` enforces this contract.
```

Keep historical verification sections. Do not delete phase history unless it is duplicative and clearly stale.

### Optional Closure Report

If creating a new closure report, include:

- final direct caller list
- final guard name and contract
- verification commands and results
- release checkout untouched status
- note that release sync/publication is separate work

## Required Verification

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
rg -l "create_project_from_template" tests | sort
grep -R --exclude-dir=__pycache__ -n "ALLOWED_TEMPLATE_CALLERS\|Remaining migration waves\|Pick one file from a wave" tests docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md || true
git status --short
```

Expected:

- guard: `1 passed`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- direct caller list:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

- stale migration wording grep: no output, except if quoted intentionally in historical phase entries. Prefer no output.

## Stop Conditions

Stop and report before editing outside scope if:

- Any non-`test_package.py` file still directly calls `create_project_from_template()`.
- The guard cannot be made stricter without changing production code.
- The full suite fails.
- Release checkout has local changes.
