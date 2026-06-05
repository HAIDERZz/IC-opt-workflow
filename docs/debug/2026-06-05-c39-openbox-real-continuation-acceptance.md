# C-39 OpenBox Real Continuation Acceptance

Date: 2026-06-05

Status: complete, verified-only.

## Scope

Validate the C-38 OpenBox continuation command against the known-good C-34 real
OpenBox/Spectre/OCEAN project copy.

This did not change metric formulas, parse PSF, rewrite OCEAN expressions, or
commit raw Cadence artifacts.

## Inputs

- Source project: `/tmp/ic_auto_opt_c34_clean2/bridge_test_inv`
- Accepted C-34 baseline: `100` real OpenBox evaluations
- Continuation workspace:
  `/tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv`
- OpenBox venv: `/tmp/ic_auto_opt_openbox_spike/.venv`
- Cadence cshrc: `/home/zzchen/cadence_ic231_env.csh`

## First Attempt And Fix

The first continuation attempt on
`/tmp/ic_auto_opt_c39_continuation_001/bridge_test_inv` failed before launching
new Spectre/OCEAN workers:

```text
optimizer state is completed
```

Root cause:

- C-38 continuation correctly loaded prior backend-neutral OpenBox traces and
  prepared cumulative reporting.
- Explicit candidate package preparation still treated a prior completed
  optimizer state as terminal.

Fix:

- Add a continuation-only `allow_optimizer_continuation` path from
  `run_openbox_real_optimization(... continue_from_existing=True)` to
  explicit candidate package preparation.
- Keep normal completed/stopped-state guards for non-continuation real-run
  preparation.
- Keep existing ledger/state count checks, config identity checks, candidate
  uniqueness checks, hashes, and stopped-state rejection.

Regression:

```text
tests/test_openbox_backend.py::test_run_openbox_real_continuation_allows_completed_prior_state
```

## Successful Continuation

Command shape:

```text
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_c39_continuation_002/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow continue-openbox-real /tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv --additional-evals 20 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Result:

```text
openbox real continuation completed: 120 cumulative evaluations
```

Closeout:

```text
check-optimizer-run: accepted
summarize-optimizer-run: accept_best_observed, confidence medium, global_optimum_claim=false
finalize-optimizer-run: passed
```

## Report Summary

- Backend: `openbox`
- Execution mode: `real`
- Cumulative evaluations: `120`
- Continuation prior evaluations: `100`
- Continuation additional evaluations: `20`
- Batch size: `10`
- Parallel jobs: `10`
- Spectre threads per run: `10`
- New run ids: `real_101` through `real_120`
- New continuation statuses: `15 feasible`, `5 constraint_failed`
- Cumulative statuses: `58 feasible`, `56 constraint_failed`,
  `6 metric_check_failed`
- Best observed: `real_071`

Best observed remained the C-34 point:

```text
FN=12
WN=2.7u
FP=7
WP=0.7u
rise=6.960432235471526e-11
fall=5.678189223340601e-11
DC=0.0003269781831574406
objective=4.1325534822170306e-14
```

## Conclusion

C-38 continuation is accepted on the real OpenBox/Spectre/OCEAN path after the
continuation-only completed-state package fix.

The result is still a best-observed conclusion, not a global optimum claim.
