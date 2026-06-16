# Optimizer Algorithm Modes For IC Optimization

Date: 2026-06-16

This document explains the optimizer strategy choices exposed through
`opt_requirement.md`. Product CLI flags must not override algorithm, strategy,
budget, batch size, Spectre parallelism, or optimizer CPU limits.

## Strategy Model

The production strategy choices are peers:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic mode when the user has not chosen a
strategy. `random_baseline` is a diagnostic baseline for pipeline checks and
algorithm comparison; it is not the production optimization default.

OpenBox is the backend for the `openbox_*` strategies. TuRBO is a separate
native backend. TuRBO should not be described as an OpenBox mode, and OpenBox
should not be described as the umbrella for all production strategies.

## Strategy Choices

| Strategy | Backend | Best Fit | Avoid When |
| --- | --- | --- | --- |
| `openbox_gp_eic` | OpenBox GP surrogate plus constrained expected improvement | Smooth, low-to-medium-dimensional IC spaces with important constraints and fine-grained numeric variables | Many failed points, rough metrics, higher dimensions, or coarse/mixed discrete grids |
| `openbox_prf_eic` | OpenBox probabilistic random forest surrogate plus constrained expected improvement | Coarse-step, integer-heavy, mixed, high-failure, or non-smooth spaces; multi-corner and constraint-heavy cases where GP is brittle | Very smooth continuous spaces where GP or TuRBO can model local behavior more precisely |
| `turbo_trust_region` | Native TuRBO trust-region optimizer | Variables have fine legal step sizes, so snapping a continuous candidate to the legal grid is a small perturbation; for example widths or lengths with about `0.1u` step size across a broad range | Coarse step grids, small integer choices such as finger counts, category switches, model-section choices, or any case where many TuRBO suggestions collapse to duplicate snapped points |
| `openbox_auto` | OpenBox automatic preset resolution | Default when the user does not know which strategy to select | When acceptance requires a reproducible, explicitly chosen algorithm mode |
| `random_baseline` | Random/Sobol-style baseline | Sanity checks, simulator pipeline debugging, and measuring whether model-based optimization is adding value | Production optimization where sample efficiency matters |

## TuRBO Step-Size Rule

TuRBO proposes candidates in a continuous trust region; that is an
implementation mechanism, not the main product selection rule. In this workflow,
choose TuRBO only when the legal IC variable grid is fine enough that snapping
the continuous candidate is a small perturbation.

Good TuRBO fit:

- width/length/bias/passive values with many legal values;
- step size is small relative to the total range, such as about `0.1u`;
- snapped candidate remains close to the continuous candidate;
- duplicate snapped points are rare.

Poor TuRBO fit:

- transistor finger count or multiplier has only a few legal values;
- step size is large relative to the range;
- categorical or architecture variables are present;
- snapping causes many duplicate candidates;
- local continuous distance no longer reflects the real design-space distance.

For poor TuRBO-fit spaces, prefer `openbox_prf_eic`. PRF handles coarse,
integer, mixed, and failure-heavy behavior more naturally.

## Requirement Examples

GP + EIC:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_gp_eic
```

PRF + EIC:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_prf_eic
```

TuRBO:

```yaml
optimizer:
  algorithm: turbo
  strategy: turbo_trust_region
```

Diagnostic baseline:

```yaml
optimizer:
  algorithm: random
  strategy: random_baseline
```

## Audit Expectations

Every optimizer run should report whether the requested strategy actually took
effect. Reports should expose:

- requested strategy;
- resolved backend;
- surrogate model and acquisition function where applicable;
- initial-design mode;
- phase: `initialization`, `bo`, `turbo_trust_region`, or `random_baseline`;
- history size before and after suggestion;
- successful observation count;
- feasible count;
- best observed objective and best feasible objective;
- duplicate replacement count;
- continuation replay count when applicable.

These fields are required because tests and static code review alone are not
enough to prove that requirement variables reached the optimizer loop.
