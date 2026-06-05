# C-41 Optimizer Continuation Decision Detail Design

Date: 2026-06-05

## Purpose

The optimizer now supports first-run OpenBox execution and real continuation.
The supervisor still needs a concise machine-readable answer to:

```text
The run finished. Should we continue, stop, or change strategy?
```

C-41 strengthens `summarize-optimizer-run` by adding a narrow continuation
summary to the existing completion report.

## Scope

In scope:

- Add a `continuation` object to `reports/optimizer_completion_report.json`.
- Keep existing `decision` values unchanged.
- Summarize:
  - whether continuation is recommended;
  - suggested additional eval count;
  - recent-window size;
  - whether the recent window improved;
  - whether the accepted trace looks plateaued;
  - feasible ratio and low-feasible-ratio flag;
  - estimated remaining finite combinations when available.
- Add focused tests.

Out of scope:

- Running real tools.
- Changing OpenBox or TuRBO candidate generation.
- Changing objective, constraints, metrics, formulas, or acceptance rules.
- Adding surrogate/SHAP/PDP analysis.
- Claiming global optimum unless the finite search space is actually exhausted.
- Adding a broad optimizer strategy engine.

## Semantics

`decision` remains the top-level action.

`continuation` is supporting detail:

- `recommended=true` only when top-level `decision` is `continue_more_evals`.
- `suggested_additional_evals` is a conservative default batch budget for the
  next continuation task. It is capped by remaining finite search space when
  that estimate is available.
- `plateau_detected=true` when feasible candidates exist but the recent window
  did not improve.
- `low_feasible_ratio=true` when at least one feasible point exists but fewer
  than 10% of evaluated candidates are feasible.

This is a reporting improvement, not a new optimizer algorithm.

## Acceptance

- Existing completion decisions remain compatible.
- Tests prove continuation detail is emitted for both continue and plateau
  cases.
- No real-tool command is run.
