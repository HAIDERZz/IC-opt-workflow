# Optimizer Flow Validation Risk Spec

## Problem

`src/hermes_workflow/optimizer_flow.py` contains a real validation risk in `_validate_options()`:

```python
if backend not in {"openbox", "native_turbo"}:
    raise ValueError("optimize backend must be openbox or native_turbo")
    if max_evals is not None and max_evals < 1:
        raise ValueError("max_evals must be >= 1")
```

The `max_evals` check is unreachable because it is indented under the branch that immediately raises for an invalid backend. As a result, `optimize_project(..., max_evals=0)` or `max_evals=-1` can pass the initial option validation for valid backends and fail later for unrelated reasons.

This is a focused bugfix. It must not become an optimizer-flow refactor.

## Scope

In scope:

- Add a focused regression test proving non-positive `max_evals` is rejected before workflow steps run.
- Fix `_validate_options()` so `max_evals is not None and max_evals < 1` is checked for all valid backends.
- Correct the `_validate_options()` type annotation to match actual callers: `max_evals: int | None`.
- Clean the obviously broken formatting in the touched `optimize_project()` blocks if needed, without changing behavior.
- Run focused tests and lint.

Out of scope:

- Refactoring `optimize_project()` into smaller functions.
- Refactoring OpenBox, native TuRBO, CLI dispatch, remote flow, or fix-run.
- Changing CLI flags or docs.
- Touching the release checkout `ic-auto-opt-workflow-v0.1`.
- Touching `graphify-out/`.

## Expected Behavior

`optimize_project()` must fail fast with `ValueError("max_evals must be >= 1")` when:

- `real=True`
- `cadence_cshrc` is provided
- `backend` resolves to either `openbox` or `native_turbo`
- `max_evals` is `0` or negative

No optimizer workflow services should run before this failure. The fail report may still be written by the existing `except` block, but it must contain the `max_evals must be >= 1` issue and no completed workflow steps.

`max_evals=None` remains valid and must preserve current behavior.

## Tooling Guidance

Use codegraph first to inspect the exact source and callers:

```bash
codegraph_node _validate_options file=optimizer_flow.py includeCode=true
codegraph_node optimize_project file=optimizer_flow.py includeCode=true
```

Graphify can help orient the surrounding workflow graph, but do not rebuild the graph. If `graphify-out/graph.json` exists, use a query only:

```bash
graphify query "Trace optimizer_flow.py optimize_project and _validate_options risks. Which surrounding tests and workflow nodes should be checked for a focused validation bugfix?" --budget 2200
```

Graphify is useful for scope control here: it shows `optimizer_flow.py`, `test_optimizer_flow.py`, and the product CLI/remote callers around the node. The fix itself should be driven by source and tests, not by graph inference.

## Acceptance Criteria

- A regression test fails before the code fix and passes after it.
- `_validate_options()` rejects `max_evals=0` and `max_evals=-1` independently of backend validity.
- Existing optimize flow behavior with `max_evals=None` still passes existing tests.
- `tests/test_optimizer_flow.py` passes.
- `tests/test_product_cli.py` passes or is explicitly reported if not run.
- Ruff check passes for touched files.
- The final diff touches only:
  - `src/hermes_workflow/optimizer_flow.py`
  - `tests/test_optimizer_flow.py`
  - optional plan/report files if the worker records results
