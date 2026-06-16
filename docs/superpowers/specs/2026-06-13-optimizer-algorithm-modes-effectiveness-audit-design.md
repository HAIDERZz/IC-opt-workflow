# C-77 Optimizer Algorithm Modes + Effectiveness Audit Design

Date: 2026-06-13

## Decision

Add user-selectable optimizer strategy modes and a runtime effectiveness audit
to the existing optimizer flow.

This is not a rewrite of the optimizer. C-77 keeps the current production route:

```bash
ic-opt PROJECT --doctor
ic-opt PROJECT --real
ic-opt PROJECT --continue 40
ic-opt --ssh-profile PROFILE PROJECT --real
```

The change is to make the existing optimizer backend choice explicit,
documented, and auditable.

## Background

Algorithm background is recorded in:

```text
docs/OPTIMIZER_ALGORITHM_MODES.md
```

The key correction is that `openbox-gp`, `openbox-prf`, and `openbox-eic` are
not peer optimizers. OpenBox Bayesian optimization combines a surrogate model,
an acquisition function, and an acquisition optimizer. `eic` is constrained
expected improvement, an acquisition function.

## Current Implementation Context

The current optimizer implementation already has the pieces C-77 should reuse:

- `src/hermes_workflow/openbox_backend.py`
  - production OpenBox ask-and-tell runner;
  - fake OpenBox runner;
  - continuation trace loading and capped model replay;
  - low-level `surrogate_type`, `acq_type`, and `acq_optimizer_type`
    overrides;
  - backend-neutral `reports/optimizer_run_report.json` and
    `reports/optimizer_evaluations.jsonl` writes.
- `src/hermes_workflow/native_turbo.py`
  - native TuRBO runner;
  - grid quantization and duplicate handling;
  - batch-aware candidate evaluation;
  - `initialization` and `turbo_trust_region` selection phases.
- `src/hermes_workflow/optimizer_flow.py`
  - local product flow that currently calls OpenBox directly.
- `src/hermes_workflow/remote_optimizer_flow.py`
  - remote flow that keeps OpenBox/controller logic local and sends
    Spectre/OCEAN work to the remote adapter.
- `src/hermes_workflow/optimizer_task_package.py`
  - execution-agent task generation for OpenBox and native TuRBO.
- `src/hermes_workflow/optimizer_insights.py`,
  `optimizer_completion.py`, `optimizer_finalize.py`, and
  `optimizer_status.py`
  - report consumers for optimizer artifacts.

## Strategy Contract

Add a user-facing optimizer strategy field.

Default config:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_auto
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  random_seed: 20260528
  optimizer_cpu_threads: 4
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

Supported strategies:

- `openbox_auto`
- `openbox_gp_eic`
- `openbox_prf_eic`
- `turbo_trust_region`
- `random_baseline`

Compatibility rules:

- Existing configs without `strategy` remain valid.
- Existing `algorithm: openbox` without `strategy` resolves to `openbox_auto`.
- Existing `algorithm: turbo` without `strategy` resolves to
  `turbo_trust_region`.
- `algorithm` remains for backward compatibility and high-level backend
  routing.
- `strategy` becomes the preferred user-facing algorithm mode.
- `openbox-eic` is not accepted as a strategy name because `eic` alone is not
  a backend.

## Preset Resolution

`openbox_auto` resolves to:

```text
backend: openbox
surrogate_type: auto
acq_type: auto
acq_optimizer_type: auto
initial_trials: auto
```

`openbox_gp_eic` resolves to:

```text
backend: openbox
surrogate_type: gp
acq_type: eic
acq_optimizer_type: random_scipy
initial_trials: auto
```

`openbox_prf_eic` resolves to:

```text
backend: openbox
surrogate_type: prf
acq_type: eic
acq_optimizer_type: local_random
initial_trials: auto
```

`turbo_trust_region` resolves to:

```text
backend: native_turbo
snap_to_step: true
duplicate_handling: resample
constraint_handling: finite_penalty
```

`random_baseline` resolves to:

```text
backend: random_baseline
sampling: sobol_or_random_grid
model_based: false
```

`random_baseline` is an audit and sanity-check mode, not the production default.

## Advanced Overrides

Advanced users may override OpenBox internals under `optimizer.openbox`:

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

Allowed `openbox.initial_trials` values:

- `auto`
- integer `>= 1`

Allowed `openbox.surrogate_type` values for C-77:

- `auto`
- `gp`
- `prf`
- `gp_rbf`
- `sk_prf`
- `lightgbm`

Allowed `openbox.acq_type` values for C-77:

- `auto`
- `ei`
- `eic`
- `pi`
- `lcb`

Allowed `openbox.acq_optimizer_type` values for C-77:

- `auto`
- `random_scipy`
- `local_random`

Advanced TuRBO settings are accepted only when strategy is
`turbo_trust_region`:

```yaml
optimizer:
  algorithm: turbo
  strategy: turbo_trust_region
  turbo:
    snap_to_step: true
    duplicate_handling: resample
```

For C-77 these TuRBO values document existing behavior. They should not create
a new TuRBO implementation.

## Effectiveness Audit

C-77 adds a stable optimizer effectiveness audit. It should be available in:

```text
reports/optimizer_run_report.json
reports/optimizer_effectiveness_audit.json
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
```

The standalone audit JSON is useful because it can be regenerated from accepted
optimizer artifacts without rerunning Spectre/OCEAN.

Top-level audit shape:

```json
{
  "schema_version": "1.0",
  "backend": "openbox",
  "requested_strategy": "openbox_gp_eic",
  "resolved_strategy": {
    "backend": "openbox",
    "surrogate_type": "gp",
    "acq_type": "eic",
    "acq_optimizer_type": "random_scipy",
    "initial_trials": 20
  },
  "continuation": {
    "enabled": false,
    "prior_evaluation_count": 0,
    "model_replay_evaluation_count": 0
  },
  "batches": []
}
```

Each batch audit row records:

```json
{
  "batch_id": "batch_001",
  "phase": "initialization",
  "history_size_before": 0,
  "history_size_after": 10,
  "suggestion_count": 10,
  "evaluation_count": 10,
  "successful_observation_count": 7,
  "penalty_observation_count": 3,
  "feasible_count": 2,
  "best_objective_so_far": 1.2,
  "best_feasible_so_far": 1.5,
  "duplicate_replacements": 0,
  "replay_history_count": 0,
  "resolved_surrogate_type": "gp",
  "resolved_acq_type": "eic",
  "resolved_acq_optimizer_type": "random_scipy"
}
```

Definitions:

- `successful_observation_count`: observations with real scalar metrics usable
  for objective and constraint learning. This includes `feasible` and
  `constraint_failed` rows.
- `penalty_observation_count`: rows that reached the optimizer as finite
  penalties because real tool execution or metric extraction did not produce
  usable scalar metrics.
- `phase`: `initialization`, `bo`, `turbo_trust_region`, or
  `random_baseline`.
- `best_objective_so_far`: best finite objective among all evaluable rows up to
  that batch.
- `best_feasible_so_far`: best finite feasible objective up to that batch.

## OpenBox Resolved Settings

When OpenBox is created with `auto` values, the workflow should inspect the
advisor instance after construction and record:

- `advisor.surrogate_type`
- `advisor.acq_type`
- `advisor.acq_optimizer_type`
- `advisor.constraint_surrogate_type` when present

If the active OpenBox object does not expose one of these values, report the
requested value and set the resolved field to `unknown`. Do not invent resolved
settings.

## Product Interface

Product-level interface:

```bash
ic-opt PROJECT --real --strategy openbox_gp_eic
ic-opt PROJECT --continue 40 --strategy openbox_prf_eic
ic-opt PROJECT --real --strategy turbo_trust_region
```

Lower-level interface:

```bash
hermes-workflow run-openbox-real PROJECT --strategy openbox_gp_eic
hermes-workflow continue-openbox-real PROJECT --additional-evals 40 --strategy openbox_prf_eic
hermes-workflow run-native-turbo PROJECT --parallel
```

Existing low-level OpenBox overrides remain available:

```bash
hermes-workflow run-openbox-real PROJECT \
  --strategy openbox_gp_eic \
  --surrogate-type gp \
  --acq-type eic \
  --acq-optimizer-type random_scipy
```

If an override conflicts with a preset, the override wins and the report must
show both the requested strategy and the resolved values.

## Continuation Rules

Continuation must inherit project resource settings by default.

Continuation strategy behavior:

- If the user supplies `--strategy`, use it.
- If prior optimizer artifacts record a requested strategy, continue with that
  strategy.
- If neither is available, use the current safe continuation default:
  `openbox_prf_eic`.
- Do not silently switch between OpenBox, TuRBO, and random baseline for an
  existing run history.
- If the requested continuation strategy is incompatible with the prior
  backend, fail closed with a clear message.

## Non-Goals

- No replacement of OpenBox ask-and-tell.
- No deletion of native TuRBO.
- No new broad optimizer framework.
- No changes to Spectre/OCEAN adapter semantics.
- No changes to multi-testbench or multi-corner concurrency semantics.
- No changes to OCEAN formulas or metric math.
- No PSF parsing.
- No real-tool run required for C-77 design or unit implementation.
- No per-project Python virtualenv.

## Acceptance Criteria

1. Existing optimizer configs without `strategy` remain valid.
2. Existing OpenBox and TuRBO CLI commands keep working.
3. New strategy presets resolve deterministically.
4. `openbox_gp_eic` and `openbox_prf_eic` pass the expected OpenBox settings
   into the existing OpenBox advisor path.
5. `turbo_trust_region` routes to the existing native TuRBO path without
   deleting or replacing TuRBO code.
6. `random_baseline` is available as a baseline mode and clearly reported as
   non-model-based.
7. Optimizer reports show requested strategy and resolved backend/settings.
8. Every batch includes an effectiveness audit row.
9. Continuation reports include prior history size and replay history count.
10. Insight markdown explains whether a run is initialization, BO,
    trust-region, or random baseline.
11. Product docs explain strategy choice and link to
    `docs/OPTIMIZER_ALGORITHM_MODES.md`.
12. No C-77 change modifies real-tool adapter behavior, OCEAN formulas, PSF
    handling, or candidate-level `parallel_jobs` semantics.

## Route Audit

C-77 aligns with the current practice-first product route. It does not restart
optimizer backend selection. It documents why OpenBox remains the default,
keeps TuRBO available as an explicit strategy, and adds the audit data needed
to judge algorithm effectiveness on real IC projects.
