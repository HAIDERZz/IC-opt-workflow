# Optimizer Algorithm Modes For IC Optimization

Date: 2026-06-13

## Purpose

This note records the optimizer algorithm choices available to the IC
optimization workflow and the problem shapes where each choice is appropriate.
It is the algorithm background for C-77 Optimizer Algorithm Modes +
Effectiveness Audit.

The project should not expose raw optimizer internals first and explain them
later. Users need a small set of clear strategy presets, and runtime reports
must show what strategy was requested and what settings actually ran.

## Release-Supported Product Modes

Product users select optimizer behavior only in `opt_requirement.md`.
The product CLI must not be used to override strategy, budget, batch size, or
parallelism.

The release-supported OpenBox strategy combinations are:

- `algorithm: openbox`, `strategy: openbox_auto`
- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`

Native TuRBO is also supported as `algorithm: turbo`,
`strategy: turbo_trust_region` for mostly continuous trust-region search.
`algorithm: random`, `strategy: random_baseline` is a diagnostic baseline for
pipeline sanity checks and algorithm comparisons, not a production default.

## OpenBox Terminology

`openbox-gp`, `openbox-prf`, and `openbox-eic` are not peer algorithms.
OpenBox Bayesian optimization is configured by three main parts:

- Surrogate model: `gp`, `prf`, `lightgbm`, and related model choices.
- Acquisition function: `ei`, `eic`, `pi`, `lcb`, and related acquisition
  choices.
- Acquisition optimizer: `random_scipy`, `local_random`, and related search
  choices for maximizing the acquisition function.

`eic` means constrained expected improvement. It is an acquisition function,
not a standalone optimizer backend.

The user-facing strategy names should therefore be combinations such as:

- `openbox_auto`
- `openbox_gp_eic`
- `openbox_prf_eic`

## Strategy Summary

| Strategy | Principle | Strength | Risk | Good IC Fit |
| --- | --- | --- | --- | --- |
| `turbo_trust_region` | Trust-region Bayesian optimization. Search stays inside a local trust region; successes expand it and failures shrink it. | Strong for medium/high-dimensional mostly continuous variables; fast local improvement for expensive simulations. | Native geometry is continuous. Coarse step grids, integer-only variables, categorical choices, or narrow feasible regions can distort the trust region, produce duplicates, or require heavy penalty handling for constraints. | Mostly continuous IC variables, fine step sizes, not too many hard failures, and a need for fast local improvement. |
| `openbox_gp_eic` | Gaussian process surrogate for objective and constraints plus constrained expected improvement. | Good sample efficiency for small, smooth, continuous design spaces; explicit constraint handling. | Can become slow or brittle with higher dimensions, many failed points, rough metrics, or coarse mixed grids. | Roughly 8 to 15 mostly continuous IC parameters, smooth metrics, and important hard constraints. |
| `openbox_prf_eic` | Probabilistic random forest surrogate for objective and constraints plus constrained expected improvement. | Robust for integer, discrete, mixed, higher-dimensional, and non-smooth spaces; usually lower CPU cost than GP. | Less precise local modeling on smooth continuous functions than GP or TuRBO. | Coarse steps, finger/integer parameters, many failed points, many variables, or non-smooth/corner-heavy behavior. |
| `openbox_auto` | Let OpenBox choose surrogate, acquisition, and acquisition optimizer from problem dimensions and types. | Safe default when users do not know optimizer internals. | Not IC-specific. OpenBox can choose PRF for dimensions where a smooth analog circuit problem might still benefit from GP. | Default baseline for production use, as long as reports show the resolved settings. |
| `random_baseline` | No surrogate model. Use random or Sobol-style exploration only. | Simple, robust, and useful for sanity checks and failure triage. | Low optimization efficiency. It should not be the production default. | Validate the simulation/evaluation pipeline, debug constraints, or compare whether BO is doing better than uninformed sampling. |

## TuRBO With Stepped IC Variables

TuRBO generates candidate points in a continuous normalized space. IC variables
usually have legal step grids, so the workflow must snap a continuous candidate
to the nearest approved grid value before simulation.

This can still work when the step grid is fine. Examples include widths,
voltages, passive values, or bias parameters where each range has many legal
values. Snapping then behaves like a small quantization error.

It becomes weaker when the grid is coarse. Examples include transistor finger
counts with only a few legal values, discrete architecture switches, category
variables, or process section choices. In those cases the trust-region distance
is no longer a natural distance in the legal design space, duplicate candidates
become more likely, and the local region can be misleading. OpenBox PRF + EIC
is usually a better fit for those mixed or coarse spaces.

The current workflow already adapts TuRBO through:

- grid quantization;
- duplicate handling;
- finite penalties for failed or constraint-violating candidates;
- batch candidate evaluation.

That is enough to keep TuRBO as an optional strategy. It should not be the only
production route for stepped or mixed IC parameter spaces.

## Recommended Defaults

Default:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_auto
```

Recommended choices:

- Use `openbox_auto` when the user does not know the algorithm details.
- Use `openbox_gp_eic` for mostly continuous, smooth, low-to-medium-dimensional
  IC optimization with important constraints.
- Use `openbox_prf_eic` for coarse-step, integer-heavy, mixed, high-failure, or
  non-smooth spaces.
- Use `turbo_trust_region` for experimental high-dimensional mostly continuous
  optimization with fine steps.
- Use `random_baseline` only for sanity checks and comparison.

Advanced users may override OpenBox internals:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_gp_eic
  openbox:
    surrogate_type: gp
    acq_type: eic
    acq_optimizer_type: random_scipy
    initial_trials: auto
```

Advanced TuRBO settings should remain explicit:

```yaml
optimizer:
  algorithm: turbo
  strategy: turbo_trust_region
  turbo:
    snap_to_step: true
    duplicate_handling: resample
```

## Required Runtime Audit

Exposing strategy selection is not enough. Every optimizer run must report
whether the optimizer actually moved beyond initialization/random sampling and
whether continuation history was replayed into the model.

Each batch should record:

- requested strategy;
- resolved backend;
- resolved surrogate model;
- resolved acquisition function;
- resolved acquisition optimizer;
- initial trials;
- phase: `initialization`, `bo`, `turbo_trust_region`, or `random_baseline`;
- history size before and after suggestion;
- successful observation count;
- feasible count;
- best objective so far;
- best feasible objective so far;
- replay history count for continuation;
- duplicate replacement count.

This audit is what lets the project answer practical questions:

- Did OpenBox actually enter BO, or is the run still initialization?
- Was history replayed during continuation?
- Did the run feed useful observations back to the model?
- Is GP, PRF, TuRBO, or random baseline more effective on a real IC case?
