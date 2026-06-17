# Optimizer Algorithm Modes

Optimizer mode is part of `opt_requirement.md`. Product CLI flags do not
override algorithm, strategy, budget, batch size, Spectre parallelism, or
optimizer CPU limits for a first run.

This document applies to `Workflow.mode: optimize`. `Workflow.mode: fix_run`
does not use an optimizer strategy; it runs fixed points and records
Spectre/OCEAN artifacts.

## Production Choices

Use one of these production strategy pairs:

```yaml
algorithm: openbox
strategy: openbox_gp_eic
```

```yaml
algorithm: openbox
strategy: openbox_prf_eic
```

```yaml
algorithm: turbo
strategy: turbo_trust_region
```

These are user-facing peer choices. OpenBox GP+EIC and OpenBox PRF+EIC use the
OpenBox backend. TuRBO uses the native TuRBO backend. That backend detail should
not change how the user chooses a strategy.

## How To Choose

| Strategy | Use when | Avoid when |
| --- | --- | --- |
| `openbox_gp_eic` | Smooth, low-to-medium-dimensional spaces where a GP surrogate is reasonable | Many coarse integer variables or frequent simulator failures |
| `openbox_prf_eic` | Coarse-step, integer-heavy, noisy, or failure-heavy spaces | Very smooth continuous spaces where GP is clearly better |
| `turbo_trust_region` | Legal variable steps are fine enough that snapping a continuous candidate is a small perturbation, for example about `0.1u` | Coarse finger-count-style grids, categorical choices, or many duplicate snapped candidates |

For poor TuRBO-fit spaces, prefer `openbox_prf_eic`.

## Diagnostic Baseline

`random_baseline` is for checking simulator plumbing and measuring whether a
model-based optimizer is adding value. It is not a production optimization
choice.

```yaml
algorithm: random
strategy: random_baseline
```

## Report Evidence

Every optimizer run should report whether the requested strategy took effect.
Useful evidence includes:

- requested algorithm and strategy
- resolved backend
- surrogate model and acquisition function, when applicable
- initialization mode
- optimizer phase
- history size before and after suggestion
- successful observation count
- feasible count
- best observed objective and best feasible objective
- duplicate replacement count
- continuation replay count, when applicable

This artifact evidence matters because code review alone does not prove that
requirement variables reached the optimizer loop.
