# Claude Prompt: Fix Optimizer Flow Validation Risk

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Do not touch:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1
graphify-out/
```

## Goal

Fix one focused bug in `src/hermes_workflow/optimizer_flow.py`: `_validate_options()` currently has the `max_evals < 1` check indented under an invalid-backend branch that immediately raises, making the `max_evals` check unreachable for valid backends.

This is a small validation bugfix. Do not refactor optimizer orchestration, OpenBox, native TuRBO, CLI dispatch, remote flow, or fix-run.

## Use codegraph and graphify

Use codegraph first to inspect the exact source and callers:

```bash
codegraph_node _validate_options file=optimizer_flow.py includeCode=true
codegraph_node optimize_project file=optimizer_flow.py includeCode=true
```

Graphify is helpful for scope control, but do not rebuild the graph. If `graphify-out/graph.json` exists, run only:

```bash
graphify query "Trace optimizer_flow.py optimize_project and _validate_options risks. Which surrounding tests and workflow nodes should be checked for a focused validation bugfix?" --budget 2200
```

Graphify should confirm the surrounding nodes; the actual fix must be based on source and tests.

## Spec

Read and follow:

```text
docs/superpowers/specs/2026-06-18-optimizer-flow-validation-risk-spec.md
```

## Plan

Read and execute:

```text
docs/superpowers/plans/2026-06-18-optimizer-flow-validation-risk-plan.md
```

Core expected change:

```python
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

Add a pytest regression test proving `max_evals=0` and `max_evals=-1` fail before doctor/workflow services run.

## Verification requirements

Run these commands and report exact results:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py::test_optimize_project_rejects_non_positive_max_evals_before_doctor -q
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py -q
PYTHONPATH=src .venv/bin/python -m pytest tests/test_product_cli.py -q
PYTHONPATH=src .venv/bin/python -m ruff check src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py
git diff -- src/hermes_workflow/optimizer_flow.py tests/test_optimizer_flow.py
git status --short
```

If you run full pytest, report the exact pass/fail count. Do not claim full-suite pass unless you actually ran it.

## Final response format

Use this shape:

```text
Files changed:
- src/hermes_workflow/optimizer_flow.py
- tests/test_optimizer_flow.py

Behavior fixed:
- optimize_project now rejects max_evals=0 and max_evals=-1 before doctor or workflow services run.

Verification:
- <command>: <exact result>
- <command>: <exact result>
- <command>: <exact result>

Notes:
- release checkout not touched
- graphify-out not touched
```
