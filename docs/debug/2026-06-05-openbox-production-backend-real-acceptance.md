# C-29 OpenBox Production Backend Real Acceptance

Date: 2026-06-05

Status: complete, verified-only.

## Scope

This note records the real-tool acceptance rerun for the productized OpenBox
backend. The run used OpenBox only for ask-and-tell candidate generation and
observation updates. Real execution stayed on the existing Hermes candidate
package, Spectre/OCEAN adapter, result checks, ledger recording, C-25
acceptance, and C-26 completion reports.

No TuRBO code was deleted or replaced. No hidden `FN=FP` coupling was added.
No Python PSF parsing or OCEAN formula rewriting occurred.

## Local Evidence

Raw tool outputs remain local-only and are not committed.

```text
/tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv
```

The clean local project reused the C-28 known-good project basis:

- `config/`
- `netlists/exported/`
- `netlists/templates/template.scs`
- `execution_package/`
- `supervisor_instruction.json`

It did not copy old C-28 `runs/`, `reports/`, `ledger/`, or `state/` outputs.

## Command Shape

The productized CLI entrypoint was used:

```text
hermes-workflow run-openbox-real PROJECT_DIR --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

The local OpenBox dependency came from the existing evidence environment and
reference checkout:

```text
/tmp/ic_auto_opt_openbox_spike/.venv/lib/python3.11/site-packages
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box
```

## Result

The productized runner completed 100 real evaluations.

```text
backend: openbox
execution_mode: real
evaluation_count: 100
status_counts:
  feasible: 43
  constraint_failed: 51
  metric_check_failed: 6
  real_check_failed: 0
duplicate_replacements: 0
parallel_jobs: 10
threads_per_run: 10
```

Best observed candidate:

```text
run_id: real_071
FN: 12
WN: 2.7u
FP: 7
WP: 0.7u
objective: 4.1325534822170306e-14
```

All 100 quantized parameter sets were unique.

## Supervisor Checks

C-25 accepted the optimizer run:

```text
optimizer run accepted
report: reports/optimizer_run_acceptance_report.json
```

C-26 generated a completion decision:

```text
optimizer completion decision: accept_best_observed
confidence: medium
global optimum claim: false
report: reports/optimizer_completion_report.json
```

## Route Audit

Active spec:

```text
docs/superpowers/specs/2026-06-05-openbox-production-backend-design.md
```

Active plan:

```text
docs/superpowers/plans/2026-06-05-openbox-production-backend.md
```

Alignment:

- The productized OpenBox backend reproduced the C-28 evidence-backed path.
- The proven Spectre/OCEAN execution path remained the execution foundation.
- Backend-neutral artifacts remained readable by C-25 and C-26.
- TuRBO remains implemented and available.

Drift:

- None. The implementation stayed within the narrow C-29 productization scope.
