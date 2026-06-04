# Optimizer Completion And Continuation Decision Report Design

Date: 2026-06-05

## Goal

Add the smallest deterministic supervisor/Hermes report for deciding what to do
after a completed native TuRBO optimizer run has already passed
`check-optimizer-run`.

C-25 answers:

```text
Did the execution agent return a structurally valid optimizer run?
```

C-26 answers:

```text
Given the accepted optimizer run, should the supervisor accept the current best
observed candidate, continue optimization, locally refine, restart, consider
exhaustive sweep, or stop for user review?
```

The report must be honest about optimizer evidence. A 100-evaluation TuRBO run
does not prove global optimality. It can only identify the best observed
candidate under the current budget, search space, metrics, constraints, and
real-tool outcomes.

## Non-Goals

- Do not run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or an
  execution agent.
- Do not change TuRBO, optimizer candidate generation, batch scheduling, or
  Spectre/OCEAN execution.
- Do not implement continuation execution.
- Do not implement exhaustive sweep execution.
- Do not parse PSF or waveform data in Python.
- Do not rewrite OCEAN or ADE Calculator formulas.
- Do not change approved metrics, constraints, or objective formulas.
- Do not claim global optimum unless the available trace actually covers the
  full discrete search space.

## User-Level Behavior

Expose one narrow command:

```bash
hermes-workflow summarize-optimizer-run PROJECT_DIR
```

The command reads existing artifacts only:

```text
reports/optimizer_run_acceptance_report.json
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
config/variables.yaml
config/optimizer.yaml
```

It writes:

```text
reports/optimizer_completion_report.json
```

The command should fail closed if the C-25 acceptance report is missing or
rejected. It should not attempt to repair, rerun, or reinterpret real-tool
artifacts.

## Output Shape

The report should use a small schema:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "decision": "continue_more_evals",
  "confidence": "medium",
  "global_optimum_claim": false,
  "best_observed": {
    "run_id": "real_021",
    "parameters": {
      "FN": "10",
      "WN": "1.1u",
      "FP": "9",
      "WP": "0.5u"
    },
    "objective": 4.305718220077049e-14,
    "fom": 23224876558049.3
  },
  "evaluation_count": 100,
  "status_counts": {
    "feasible": 36,
    "constraint_failed": 43,
    "metric_check_failed": 21
  },
  "search_space": {
    "estimated_discrete_combinations": 1000,
    "evaluated_fraction": 0.1,
    "exhaustive_trace": false
  },
  "improvement": {
    "best_objective_start": 6.2e-14,
    "best_objective_end": 4.3e-14,
    "recent_best_improved": true,
    "recent_window": 20
  },
  "reasons": [
    "best observed improved inside the recent window",
    "search space is not exhausted"
  ],
  "warnings": [],
  "issues": []
}
```

Use `status = fail` only when required input artifacts are missing, malformed, or
C-25 acceptance rejected the run. Candidate-level optimizer failures should
remain summarized as evidence, not as report-level failure by themselves.

## Decision Values

Use a small decision enum:

- `accept_best_observed`: current best observed candidate is a reasonable stop
  point for the supervisor to review or hand to the user.
- `continue_more_evals`: the optimizer is still improving, so another batch is
  likely useful.
- `local_refine_around_best`: global progress has slowed, but the neighborhood
  around the best observed candidate is under-sampled.
- `restart_with_new_seed`: the run has weak feasibility or appears stuck in a
  poor region.
- `switch_to_exhaustive_sweep`: the estimated discrete search space is small
  enough that an exhaustive route is more honest than continued Bayesian
  optimization.
- `stop_for_user_review`: artifacts are accepted structurally, but the outcome
  is too ambiguous or failure-heavy for an automatic next step.

## Deterministic Decision Rules

The first implementation should use simple deterministic heuristics, not a new
optimizer model:

1. If `optimizer_run_acceptance_report.status != accepted`, write `status =
   fail`, `decision = stop_for_user_review`.
2. If no feasible candidate exists, choose `stop_for_user_review`.
3. Estimate discrete search-space size from `config/variables.yaml` when all
   variables have finite integer or continuous-step grids. If the trace covers
   every combination, set `global_optimum_claim = true` and choose
   `accept_best_observed`.
4. If the estimated discrete search space is modest relative to the completed
   budget, prefer `switch_to_exhaustive_sweep` over pretending the 100-point
   TuRBO result is globally conclusive.
5. Build a best-so-far objective curve using trace rows with finite objective
   values. Lower objective is better because native TuRBO writes the minimized
   objective.
6. Use a recent window of `min(20, max(5, evaluation_count // 5))`.
7. If the best objective improved inside the recent window, choose
   `continue_more_evals`.
8. If recent improvement plateaued and the best candidate neighborhood has few
   nearby samples, choose `local_refine_around_best`.
9. If feasible ratio is very low or metric/tool failure classes dominate,
   choose `restart_with_new_seed` or `stop_for_user_review` with clear reasons.
10. Otherwise choose `accept_best_observed`.

These rules are intentionally conservative about global-optimum claims and
aggressive about exposing uncertainty to the supervisor.

## Failure Classification

C-26 should not invent new execution statuses. It should summarize the statuses
already emitted by native TuRBO and C-25:

- `feasible`: satisfies constraints and can compete for best observed.
- `constraint_failed`: real scalar metrics exist, but the candidate does not
  satisfy the configured performance constraints.
- `metric_check_failed`: Spectre may have succeeded, but OCEAN metric extraction
  did not produce all required scalar metrics for that candidate.
- `real_check_failed`: physical run/result manifest failed before usable metric
  extraction.
- `record_failed` or other native trace statuses: report as issues or warnings
  according to severity.

The report should distinguish candidate-level performance failure from tool or
workflow failure. A high number of `constraint_failed` rows is optimizer evidence;
a high number of `real_check_failed` rows is workflow/tool risk.

## Search-Space Estimate

The search-space estimate is only valid for finite grids:

- integer variables: `upper - lower + 1`;
- continuous-step variables: `(upper - lower) / step + 1` when the step divides
  the range cleanly under the existing compact-unit parser semantics.

If any variable cannot be counted deterministically, set
`estimated_discrete_combinations = null` and do not make exhaustive-sweep claims.

## Route Alignment

C-26 preserves the current project direction:

```text
Execution agent runs optimizer packet
-> Hermes C-25 accepts returned artifacts structurally
-> Hermes C-26 summarizes optimizer quality and next action
-> Supervisor decides whether to accept, continue, refine, restart, sweep, or
   ask the user
```

This keeps the execution agent focused on tool-side work and keeps the
supervisor from manually interpreting a large optimizer trace. It also prevents
the project from falsely treating one 100-point TuRBO run as proof of global
optimality.

## Test Strategy

Use fake artifact projects only:

- accepted C-25 report plus improving trace -> `continue_more_evals`;
- accepted C-25 report plus plateaued trace and under-sampled neighborhood ->
  `local_refine_around_best`;
- accepted C-25 report plus full finite-grid coverage ->
  `accept_best_observed` with `global_optimum_claim = true`;
- rejected or missing C-25 report -> `status = fail`,
  `decision = stop_for_user_review`;
- failure-heavy trace -> `stop_for_user_review` or `restart_with_new_seed`.

Do not run real tools in C-26 implementation tests.
