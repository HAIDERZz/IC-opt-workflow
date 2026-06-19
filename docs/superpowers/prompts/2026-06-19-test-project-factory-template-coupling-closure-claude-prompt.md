# Claude Prompt: Template Coupling Cleanup Closure

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-closure-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-closure-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

## Goal

Close the template-coupling cleanup by tightening the guard and inventory wording. No production code migration remains.

## Strict Scope

Allowed to modify:

```text
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Optional create:

```text
docs/superpowers/reports/2026-06-19-test-project-factory-template-coupling-closure.md
```

Do not modify:

```text
src/
tests/test_package.py
any other tests/
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

If an out-of-scope file appears necessary, stop and report the exact reason.

## Required Changes

1. Rename `ALLOWED_TEMPLATE_CALLERS` in `tests/test_template_coupling_guard.py` to:

```python
INTENTIONAL_TEMPLATE_API_CALLERS = {
    "tests/test_package.py",
}
```

2. Rename the guard test to:

```python
test_create_project_from_template_usage_is_limited_to_product_template_api_tests
```

3. Keep the guard behavior the same: scan `tests/*.py`, ignore itself, and fail if any non-intentional test directly contains `create_project_from_template`.

4. Update the inventory so it no longer has stale "Remaining migration waves" / "How to continue" guidance.

5. Add a final guard state section explaining:

```text
All non-product test files have been migrated away from direct create_project_from_template usage.
Only tests/test_package.py remains because it tests the product/template API itself.
New tests should use tests/project_factory.py or existing generic helpers.
```

6. Optional: create a closure report with final caller list and verification results.

## Required Verification

Run exactly:

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
- release checkout: no output
- direct caller list:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

- stale wording grep: no current/final-state stale wording. Historical phase entries may remain only if clearly historical.

## Final Report Format

Return:

1. Files modified/created.
2. Final guard contract.
3. Final direct caller list.
4. Exact verification results.
5. Release checkout status.
6. Confirmation that no production files, release files, or `graphify-out/` were touched.

Do not commit, tag, push, publish, or modify the release checkout.
