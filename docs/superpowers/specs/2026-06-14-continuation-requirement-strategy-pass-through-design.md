# Continuation Requirement Strategy Pass-Through Design

Date: 2026-06-14

## Problem

`ic-opt PROJECT --real --continue N` was restored as a continuation-only CLI
entrypoint. Its intended contract is:

- `N` is the only runtime value supplied by CLI.
- Existing optimizer history is required.
- The effective target is `prior optimizer evaluations + N`.
- `opt_requirement.md` / generated config remains the source of truth for every
  optimizer, resource, Spectre, testbench, corner, and retention setting.
- `opt_requirement.md` must not be modified by continuation.

Current continuation flow violates the strategy portion of that contract.

Local continuation in `src/hermes_workflow/optimizer_continuation_flow.py` and
remote continuation in `src/hermes_workflow/remote_optimizer_flow.py` explicitly
pass:

```python
surrogate_type=CONTINUATION_SURROGATE_TYPE
acq_type=CONTINUATION_ACQ_TYPE
acq_optimizer_type=CONTINUATION_ACQ_OPTIMIZER_TYPE
```

Those constants are currently `prf`, `eic`, and `local_random`. Passing them into
`run_openbox_real_optimization()` overrides the OpenBox strategy details that
would otherwise be resolved from `config/optimizer.yaml`, which is generated from
`opt_requirement.md`.

Concrete example:

- Requirement/config says `optimizer.strategy: openbox_gp_eic`.
- Normal resolver path returns `surrogate_type=gp`,
  `acq_type=eic`, `acq_optimizer_type=random_scipy`.
- Continuation path forces `surrogate_type=prf`,
  `acq_type=eic`, `acq_optimizer_type=local_random`.

The current real validation sample did not expose this because its requirement
already used `openbox_prf_eic` and matching nested OpenBox settings.

## Root Cause

The continuation wrappers were written as if PRF/EIC/local-random were
"continuation defaults". That is a false contract for product `ic-opt`
continuation. Product continuation is not a strategy selection command. It is
only a budget-delta command.

The backend already contains the correct source-of-truth behavior:

- `run_openbox_real_optimization()` loads the native optimizer contract.
- `_resolve_openbox_strategy()` reads `optimizer.strategy` and
  `optimizer.openbox`.
- `resolve_optimizer_strategy()` applies the configured preset and advanced
  OpenBox settings.

The bug is introduced before this resolver by passing non-`None` strategy-detail
arguments from local/remote continuation helpers.

## Current Data Flow

Local continuation:

```text
product_cli.main
  -> continue_local_project(additional_evals=N)
  -> local_openbox()
  -> run_openbox_real_optimization(
       max_evals=None,
       additional_evals=N,
       continue_from_existing=True,
       batch_size=None,
       parallel_jobs=None,
       strategy=None,
       surrogate_type=prf,              # BUG
       acq_type=eic,                    # BUG
       acq_optimizer_type=local_random, # BUG
     )
```

Remote continuation:

```text
product_cli.main
  -> continue_remote_project(additional_evals=N)
  -> prepare_remote_project_cache()
  -> sync remote optimizer history into cache
  -> remote_openbox()
  -> run_openbox_real_optimization(
       max_evals=None,
       additional_evals=N,
       continue_from_existing=True,
       batch_size=None,
       parallel_jobs=None,
       strategy=None,
       surrogate_type=prf,              # BUG
       acq_type=eic,                    # BUG
       acq_optimizer_type=local_random, # BUG
     )
```

Backend resolver:

```text
run_openbox_real_optimization()
  -> load_native_turbo_contract()
  -> _resolve_openbox_strategy()
  -> resolve_optimizer_strategy()
```

This backend resolver should receive `None` for CLI strategy-detail arguments in
product continuation, so it can use requirement/config values.

## Required Behavior

For `ic-opt PROJECT --real --continue N` and
`ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real --continue N`:

1. `additional_evals` must be exactly `N`.
2. `max_evals` must be `None`.
3. `continue_from_existing` must be `True`.
4. Existing optimizer history must be required.
5. `batch_size` must be `None` so config/requirement controls it.
6. `parallel_jobs` must be `None` so config/requirement controls it.
7. `strategy` must be `None` so config/requirement controls it.
8. `surrogate_type` must be `None` so config/requirement controls it.
9. `acq_type` must be `None` so config/requirement controls it.
10. `acq_optimizer_type` must be `None` so config/requirement controls it.
11. `initial_trials` must be `None` so config/requirement controls it.
12. `opt_requirement.md` must remain byte-identical before and after
    continuation.
13. Report output must keep the continuation audit fields:

```json
"continuation": {
  "continuation_requested": true,
  "prior_evaluation_count": 10,
  "additional_evaluations_requested": 2,
  "effective_target_evaluations": 12,
  "budget_source": "cli_continuation_delta"
}
```

14. Report output must show the resolved strategy that came from requirement,
    not a hardcoded continuation strategy.

## Non-Goals

- Do not reintroduce `--max-evals`, `--batch-size`, `--parallel-jobs`,
  `--threads`, `--surrogate-type`, `--acq-type`, `--acq-optimizer-type`, or
  `--strategy` to product `ic-opt --real --continue`.
- Do not modify `opt_requirement.md` automatically.
- Do not rewrite OpenBox or TuRBO optimizer algorithms.
- Do not change candidate/testbench/corner execution order.
- Do not change remote adapter routing:
  - single testbench -> `run_remote_spectre_ocean_adapter`
  - multi-testbench or process-corner flow ->
    `run_remote_multi_testbench_adapter`
- Do not sync to `ic-auto-opt-workflow-v0.1` until the development package is
  fixed and verified.

## Acceptance Criteria

### Unit / Integration

1. Local product continuation passes `None` for strategy-detail overrides.
2. Remote product continuation passes `None` for strategy-detail overrides.
3. Existing tests that require `prf/eic/local_random` for remote continuation
   are updated because that old expectation is the bug.
4. A fake/OpenBox continuation project with `optimizer.strategy:
   openbox_gp_eic` resolves to:

```json
{
  "requested_strategy": "openbox_gp_eic",
  "resolved_strategy": {
    "surrogate_type": "gp",
    "acq_type": "eic",
    "acq_optimizer_type": "random_scipy"
  }
}
```

5. A fake/OpenBox continuation project with `optimizer.strategy:
   openbox_prf_eic` resolves to:

```json
{
  "requested_strategy": "openbox_prf_eic",
  "resolved_strategy": {
    "surrogate_type": "prf",
    "acq_type": "eic",
    "acq_optimizer_type": "local_random"
  }
}
```

6. A project with nested `optimizer.openbox` settings still preserves those
   settings through continuation.
7. CLI validation remains:
   - `--continue N` without `--real` fails.
   - `--real --continue N --strategy ...` fails.
   - no default continuation count exists.
8. Continuation still requires existing optimizer history.
9. `opt_requirement.md` is unchanged after continuation.

### Real Flow

After unit/full verification, run at least one development-package real local
continuation smoke against a copied prior real project:

```bash
./.venv/bin/ic-opt /tmp/<copy> --real --continue 2
```

Verify:

- `reports/optimizer_run_report.json` shows
  `continuation.budget_source == "cli_continuation_delta"`.
- `prior_evaluation_count + additional_evaluations_requested ==
  effective_target_evaluations`.
- `state/current_evaluations` and `reports/optimizer_evaluations.jsonl` row
  count increase by exactly `N`.
- `recorded_observation_count` equals ledger row count.
- `opt_requirement.md` hash is unchanged.
- Resolved strategy in the report matches that project's requirement/config.

Remote real continuation may be run after the local fix is proven, but it is not
required for the first code patch unless explicitly requested because it consumes
remote EDA resources.

## Files In Scope

Expected code/test files:

- `src/hermes_workflow/optimizer_continuation_flow.py`
- `src/hermes_workflow/remote_optimizer_flow.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_product_cli.py`
- `tests/test_product_cli_remote.py`
- `tests/test_openbox_backend.py`

Potential docs cleanup, if included in the same branch:

- `README.md`
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- `docs/USER_GUIDE_CN.md`
- `docs/TROUBLESHOOTING_CN.md`
- `skills/ic-opt/SKILL.md`
- `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

