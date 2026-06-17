# Optimizer Flow Validation Risk — Fix Report

- **Date:** 2026-06-18
- **Branch:** `plan-a-hermes-file-contract-mvp`
- **Base commit:** `7e9b13e`
- **Spec:** [`docs/superpowers/specs/2026-06-18-optimizer-flow-validation-risk-spec.md`](../specs/2026-06-18-optimizer-flow-validation-risk-spec.md)
- **Plan:** [`docs/superpowers/plans/2026-06-18-optimizer-flow-validation-risk-plan.md`](../plans/2026-06-18-optimizer-flow-validation-risk-plan.md)
- **Type:** Focused validation bugfix (TDD: failing test → fix → green)

---

## 1. Problem

`_validate_options()` in [`src/hermes_workflow/optimizer_flow.py`](../../../src/hermes_workflow/optimizer_flow.py) contained a real validation risk: the `max_evals < 1` check was **dead-nested** under the invalid-backend branch, which raises immediately.

```python
# BEFORE (buggy)
if backend not in {"openbox", "native_turbo"}:
    raise ValueError("optimize backend must be openbox or native_turbo")
    if max_evals is not None and max_evals < 1:      # unreachable
        raise ValueError("max_evals must be >= 1")   # unreachable
```

Because the outer branch raises before reaching the inner statement, the `max_evals` guard only ever runs for **invalid** backends — exactly the case that already fails. For **valid** backends (`openbox` / `native_turbo`), non-positive `max_evals` (e.g. `0`, `-1`) passed initial validation and failed later for unrelated reasons.

## 2. Root Cause

Pure indentation error. The `max_evals` guard was indented one level too deep, placing it inside the body of the `if backend not in {...}` block — a block that unconditionally raises, making the guard unreachable for the inputs that matter.

## 3. The Fix

De-indented the `max_evals` guard out of the dead branch so it runs for **all** backends, and corrected the type annotation to match the actual caller (`optimize_project` passes `max_evals: int | None`).

```python
# AFTER (fixed)
def _validate_options(
    *,
    real: bool,
    cadence_cshrc: Path | None,
    max_evals: int | None,
    backend: str,
) -> None:
    if not real:
        raise ValueError("optimize requires --real; fake optimize is not supported")
    if backend not in {"openbox", "native_turbo"}:
        raise ValueError("optimize backend must be openbox or native_turbo")
    if max_evals is not None and max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if cadence_cshrc is None:
        raise ValueError("--cadence-cshrc is required")
```

`max_evals=None` remains valid and preserves existing behavior.

Because `optimize_project()` calls `_validate_options()` before any service step and re-raises from its `except` block after writing a fail report, a bad `max_evals` now fails fast:

1. `_validate_options(...)` raises `ValueError("max_evals must be >= 1")`
2. The `except` appends the issue, writes `reports/optimizer_flow_run_report.json` (`status="fail"`, `steps=[]`), then re-raises
3. No `doctor` / workflow service ever runs

## 4. Files Changed

| File | Change |
| --- | --- |
| [`src/hermes_workflow/optimizer_flow.py`](../../../src/hermes_workflow/optimizer_flow.py) | `_validate_options()`: de-indent `max_evals` guard; annotation `int` → `int \| None`. `optimize_project()` untouched. |
| [`tests/test_optimizer_flow.py`](../../../tests/test_optimizer_flow.py) | Add `import pytest`; add parametrized regression test `test_optimize_project_rejects_non_positive_max_evals_before_doctor[0/-1]`. |

Diff is minimal and focused. The pre-existing oddly-indented `optimize_project()` blocks were **intentionally left as-is** — `ruff check` passes on them already, so per the spec's "clean broken formatting *if needed*" clause and the "do not refactor" mandate, no formatting cleanup was warranted.

## 5. Test Added (TDD evidence)

```python
@pytest.mark.parametrize("max_evals", [0, -1])
def test_optimize_project_rejects_non_positive_max_evals_before_doctor(
    tmp_path: Path,
    max_evals: int,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    cadence_cshrc = tmp_path / "cadence_env.csh"
    cadence_cshrc.write_text("# test\n", encoding="utf-8")
    calls: list[str] = []

    with pytest.raises(ValueError, match="max_evals must be >= 1"):
        optimize_project(
            project_dir,
            real=True,
            max_evals=max_evals,
            cadence_cshrc=cadence_cshrc,
            services=_services(project_dir, calls),
        )

    assert calls == []                       # no service ran
    payload = json.loads(
        (project_dir / "reports" / "optimizer_flow_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "fail"
    assert payload["issues"] == ["max_evals must be >= 1"]
    assert payload["steps"] == []
```

- **Before fix:** FAILED — `Failed: DID NOT RAISE <class 'ValueError'>` (validation passed, mocked workflow ran to completion).
- **After fix:** PASSED for both `max_evals=0` and `max_evals=-1`.

## 6. Verification (exact results)

| # | Command | Result |
| --- | --- | --- |
| 1 | `PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py::test_optimize_project_rejects_non_positive_max_evals_before_doctor -q` | `2 passed` (parametrized `[0]`, `[-1]`) |
| 2 | `PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py -q` | `9 passed, 13 warnings in 0.63s` |
| 3 | `PYTHONPATH=src .venv/bin/python -m pytest tests/test_product_cli.py -q` | `20 passed, 13 warnings in 0.69s` |
| 4 | `PYTHONPATH=src .venv/bin/python -m ruff check src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py` | `All checks passed!` |
| 5 | `git diff -- src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py` | Only `_validate_options()` (annotation + de-indented guard) + test additions |
| 6 | `git status --short` | `M src/hermes_workflow/optimizer_flow.py`; `M tests/test_optimizer_flow.py`; untracked plan/spec/prompt docs + `graphify-out/` |

> **Note:** The full `pytest` suite was **not** run. Only the three scopes above (regression test, `test_optimizer_flow.py`, `test_product_cli.py`) and `ruff` were executed. No full-suite pass is claimed.

## 7. Scope Confirmation (graph + source)

- **codegraph:** `_validate_options()` is called only by `optimize_project()` (twice — pre-doctor and post-strategy-resolution), confirming the fix at this single boundary covers both calls and all callers (`optimize_remote_project()`, CLI `optimize_command`, product CLI `main()`).
- **graphify (read-only query, graph not rebuilt):** BFS depth-2 from `optimize_project()` / `_validate_options()` returned 113 nodes, confirming the surrounding surface — `test_optimizer_flow.py` (`_services()` helper), `OptimizerFlowServices`, `OptimizerFlowReport`, and the remote/product-CLI pass-through callers. No unexpected dependents.

## 8. Out of Scope (not touched)

- ❌ Release checkout `ic-auto-opt-workflow-v0.1`
- ❌ `graphify-out/` (read-only query only; graph not rebuilt)
- ❌ Optimizer orchestration / OpenBox / native TuRBO / CLI dispatch / remote flow / fix-run
- ❌ CLI flags or docs
- ❌ Cosmetic indentation cleanup in `optimize_project()` (not needed — ruff passes)
- ❌ Commit / merge / PR (left to the user; nothing committed)

## 9. Conclusion

The validation bug is fixed and protected by a parametrized regression test that fails before the fix and passes after. All required test scopes and `ruff` are green. The diff is minimal, touching only `_validate_options()` and the test file, with no scope creep into orchestration or formatting.
