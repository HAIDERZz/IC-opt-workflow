# C-28 OpenBox Real Backend Acceptance Spike

Date: 2026-06-05

## Decision

`proceed_to_openbox_productization`

OpenBox passed a narrow real-tool acceptance spike against the existing Hermes
Spectre/OCEAN candidate execution path. This does not replace TuRBO yet; it
means OpenBox is evidence-backed enough for a narrow production backend plan.

## Run

- Run directory: `/tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv`
- Backend: OpenBox ask-and-tell
- Execution mode: real Spectre/OCEAN through existing Hermes adapter path
- Max evaluations: 100
- Batch size: 10
- Parallel jobs: 10
- Random seed: 20260528
- Candidate variables: current approved `variables.yaml` only (`FN`, `WN`, `FP`, `WP`)
- No `FN=FP` coupling was added.

## Counts

- Total evaluations: 100
- Feasible: 43
- Constraint failed: 51
- Metric check failed: 6
- Real check failed: 0
- Duplicate replacements: 0
- Result manifests: 100
- Metric manifests: 100

## Best Observed Candidate

This is the best observed point from the 100 evaluated candidates, not a global
optimum claim.

- Run: `real_071`
- Parameters:
  - `FN=12`
  - `WN=2.7u`
  - `FP=7`
  - `WP=0.7u`
- Metrics:
  - `rise=6.960432235471526e-11`
  - `fall=5.678189223340601e-11`
  - `DC=0.0003269781831574406`
- Objective: `4.1325534822170306e-14`

## Spectre Settings Audit

C-25 accepted the run with stable settings:

- `preset=ax`
- `threads_per_run=10`
- `parallel_jobs=10`
- `output_format=psfxl`

## C-25 Result

`hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv`

Result:

- Status: `accepted`
- Report: `reports/optimizer_run_acceptance_report.json`

## C-26 Decision

`hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv`

Result:

- Decision: `accept_best_observed`
- Confidence: `medium`
- Global optimum claim: `false`
- Recent window improvement: `false`

## TuRBO Baseline Comparison

Closest accepted TuRBO baseline: C-24 retry run at
`/tmp/ic_auto_opt_c24_retry/bridge_test_inv`.

- TuRBO C-24: 100 evaluations, 36 feasible, 43 constraint failed,
  21 metric check failed.
- TuRBO C-24 best observed: `real_021`,
  `FN=10`, `WN=1.1u`, `FP=9`, `WP=0.5u`,
  objective `4.305718220077049e-14`.
- OpenBox C-28: 100 evaluations, 43 feasible, 51 constraint failed,
  6 metric check failed.
- OpenBox C-28 best observed: `real_071`,
  `FN=12`, `WN=2.7u`, `FP=7`, `WP=0.7u`,
  objective `4.1325534822170306e-14`.

Additional TuRBO baseline: C-18 batch run at
`/tmp/ic_auto_opt_c18_batch_native_turbo_001/bridge_test_inv`.

- TuRBO C-18: 100 evaluations, 36 feasible, 50 constraint failed,
  14 metric check failed.
- TuRBO C-18 best observed: `real_018`,
  `FN=12`, `WN=1.7u`, `FP=10`, `WP=0.5u`,
  objective `4.2413224774045756e-14`.

For this inverter case and seed, OpenBox produced a better best observed
objective than both accepted TuRBO reference runs and fewer metric check
failures than C-24.

## Issues And Required Productization Notes

- OpenBox `Real(q=...)` requires `(upper - lower)` to be an exact multiple of
  `q`. The current approved grid `0.3u..3u step 0.2u` has effective maximum
  value `2.9u`. A production OpenBox backend must derive the OpenBox search
  upper bound from the same Hermes quantization grid rather than using the raw
  configured upper text directly.
- The local C-28 project initially missed `netlists/templates/template.scs`.
  A production OpenBox backend must use the same complete Hermes project bundle
  as the TuRBO path and must preserve both `netlists/exported/` and
  `netlists/templates/template.scs`.
- No Python PSF parsing occurred.
- No OCEAN formula rewrite occurred.
- No TuRBO code was replaced or deleted.
- Raw Cadence artifacts and full logs remain under `/tmp` only.

## Next Recommendation

Write a narrow C-29 OpenBox productization plan. The plan should keep the
existing Spectre/OCEAN execution path and C-25/C-26 audit reports, while
productizing only the OpenBox candidate generation backend and its required
dependency/config gates.
