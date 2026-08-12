# Optimizer Algorithm Modes

Optimizer mode is part of `opt_requirement.md`. Product CLI flags do not
override algorithm, strategy, budget, batch size, Spectre parallelism, or
optimizer CPU limits for a first run. `--real --continue N` is the one
exception: it only appends `N` evaluations to the existing budget. Algorithm,
strategy, batch size, and every other optimizer setting still resolve from
the project's `config/optimizer.yaml`, not from the CLI invocation.

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

Do not omit `strategy` in a new production requirement.

## Compatibility Choice: `openbox_auto`

```yaml
algorithm: openbox
strategy: openbox_auto
```

`openbox_auto` is an explicit compatibility strategy used by sanitized
templates whose validated source run used OpenBox automatic model selection
(`surrogate_type: auto`, `acq_type: auto`, `acq_optimizer_type: auto`). It is
a legal, currently-shipping strategy — both
`spectre_maestro_project/opt_requirement.multi_testbench.md` and
`opt_requirement.history_warm_start.md` use it — but it is not one of the two
production peer choices above. Prefer `openbox_gp_eic` or `openbox_prf_eic`
for a new production requirement.

## Default Strategy Resolution

`strategy` may be omitted from `optimizer.yaml`. When omitted, it resolves
from `algorithm` alone:

| `algorithm` | Default `strategy` when omitted |
| --- | --- |
| `openbox` | `openbox_auto` |
| `turbo` | `turbo_trust_region` |
| `random` | `random_baseline` |

## Initialization Budget

- **`turbo`**: `optimizer.max_evaluations` must be at least `2 * number_of_variables`,
  or the project fails validation before any Spectre run. The native TuRBO
  backend itself always initializes with `n_init = 2 * n_params`.
- **`openbox` with `initial_trials: auto`** (the default for every OpenBox
  strategy, including `openbox_auto`): resolves to
  `max(2 * number_of_variables, 1)`. Set `optimizer.openbox.initial_trials`
  to an explicit integer to override this.
- **`batch_size`**: `optimizer.batch_size` must be `<= spectre.parallel_jobs`
  for every algorithm, or the project fails validation.

## How To Choose

| Strategy | Use when | Avoid when |
| --- | --- | --- |
| `openbox_gp_eic` | Smooth, low-to-medium-dimensional spaces where a GP surrogate is reasonable | Many coarse integer variables or frequent simulator failures |
| `openbox_prf_eic` | Coarse-step, integer-heavy, noisy, or failure-heavy spaces | Very smooth continuous spaces where GP is clearly better |
| `turbo_trust_region` | Legal variable steps are fine enough that snapping a continuous candidate is a small perturbation, for example about `0.1u` | Coarse finger-count-style grids, categorical choices, or many duplicate snapped candidates |

For poor TuRBO-fit spaces, prefer `openbox_prf_eic`. Before choosing
`turbo_trust_region`, estimate the snap perturbation from each variable's
`step` in `variables.yaml`; if a legal step is not small relative to the
variable's useful range, TuRBO's continuous-candidate snapping will collapse
many distinct suggestions onto the same duplicate point.

### `optimizer.openbox` / `optimizer.turbo` advanced blocks

`optimizer.openbox` and `optimizer.turbo` accept advanced overrides, and both
are cross-validated against `strategy`:

| `strategy` | Required `optimizer.openbox.surrogate_type` | Required `acq_type` | Required `acq_optimizer_type` |
| --- | --- | --- | --- |
| `openbox_gp_eic` | `gp` | `eic` | `random_scipy` |
| `openbox_prf_eic` | `prf` | `eic` | `local_random` |
| `openbox_auto` | any (unconstrained) | any (unconstrained) | any (unconstrained) |

Setting a value in `optimizer.openbox` that conflicts with the named preset
(for example `acq_optimizer_type: local_random` under `openbox_gp_eic`) fails
validation. `initial_trials` may still override the preset's automatic trial
count under any of the three strategies. Field-level detail is in
`examples/spectre_maestro_project/OPT_REQUIREMENT_README.md` (also shipped at
`src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`).

## Diagnostic Baseline

`random_baseline` is for checking simulator plumbing and measuring whether a
model-based optimizer is adding value. It is not a production optimization
choice.

```yaml
algorithm: random
strategy: random_baseline
```

`random_baseline` is executed by the OpenBox backend (it still requires a
working OpenBox environment); native TuRBO is the only separate execution
backend. `resolved backend` in report evidence reads `openbox` for
`random_baseline`, not a distinct `random` backend.

## Report Evidence

Every optimizer run should report whether the requested strategy took effect.
The authoritative fields live in two places:

| Field | Defined in | Written to |
| --- | --- | --- |
| `requested_strategy`, `backend`, `surrogate_type`, `acq_type`, `acq_optimizer_type` (resolved strategy) | `src/hermes_workflow/optimizer_strategy.py` (`ResolvedOptimizerStrategy`) | `reports/optimizer_run_report.json` or `reports/native_turbo_optimizer_report.json`, depending on backend |
| `history_size_before`, `history_size_after`, `suggestion_count`, `evaluation_count`, `successful_observation_count`, `penalty_observation_count`, `feasible_count`, `best_objective_so_far`, `best_feasible_so_far`, `duplicate_replacements`, `replay_history_count`, `resolved_surrogate_type`, `resolved_acq_type`, `resolved_acq_optimizer_type`, `phase` | `src/hermes_workflow/optimizer_effectiveness.py` (`OptimizerBatchAudit`) | `reports/optimizer_effectiveness_audit.json` (both backends; path constant `EFFECTIVENESS_AUDIT_RELATIVE` in `native_turbo.py`) |
| `requested_strategy`, `resolved_strategy`, `resolved_settings`, `model_replay_evaluation_count`, `batch_count`, `latest_batch` (rolled-up summary) | `src/hermes_workflow/optimizer_insights.py` | `reports/optimizer_insight_report.json` (and `.md`/`.html`) |

This artifact evidence matters because code review alone does not prove that
requirement variables reached the optimizer loop.
