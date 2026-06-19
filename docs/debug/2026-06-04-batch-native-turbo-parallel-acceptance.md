# C-18 Batch Native TuRBO Parallel Acceptance

Date: 2026-06-04

## Scope

This acceptance validates the C-18 batch-native TuRBO runner on the proven
Hermes + Spectre/OCEAN path.

The run used:

```text
/tmp/ic_auto_opt_c18_batch_native_turbo_001/bridge_test_inv
```

Raw Cadence artifacts, generated netlists, PSF data, OCEAN scripts, and full
logs remain local-only under `/tmp`.

## Command Shape

```text
hermes-workflow run-native-turbo \
  /tmp/ic_auto_opt_c18_batch_native_turbo_001/bridge_test_inv \
  --parallel \
  --max-evals 100 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

## Result

```text
native turbo optimization completed: 100 evaluations
```

Summary:

```text
trace_count 100
status_counts {'feasible': 36, 'constraint_failed': 50, 'metric_check_failed': 14}
phase_counts {'initialization': 16, 'turbo_trust_region': 84}
batch_count 11
max_workers 10
```

Report batch summary:

```json
{
  "batch_count": 11,
  "max_batch_worker_count": 10,
  "status_counts": {
    "constraint_failed": 50,
    "feasible": 36,
    "metric_check_failed": 14
  }
}
```

Best candidate:

```text
run_id real_018
status feasible
parameters FN=12 FP=10 WN=1.7u WP=0.5u
rise 6.608725022174673e-11
fall 6.129060537337709e-11
DC 0.0003329717286877405
objective 4.2413224774045756e-14
selection_phase turbo_trust_region
batch_id batch_002
batch_slot 10
batch_worker_count 10
```

## Spectre Settings Audit

All prepared real-run manifests used the expected Spectre settings:

```text
prepared_manifests 100
preset {'ax': 100}
threads_per_run {10: 100}
parallel_jobs {10: 100}
output_format {'psfxl': 100}
```

Interpretation:

- `threads_per_run=10` maps to per-Spectre `+mt=10`.
- `parallel_jobs=10` is the maximum number of concurrent Spectre/OCEAN
  candidate evaluations.
- C-18 preserved the distinction between per-process Spectre threading and
  process-level batch parallelism.

## Route Audit

Aligned with C-18:

- Native `Turbo1.optimize()` remains the optimizer driver.
- Batch evaluation is bounded by `min(optimizer.batch_size, spectre.parallel_jobs)`.
- Ledger/state recording remains sequential after checked worker results.
- Python does not parse PSF.
- Python does not rewrite OCEAN formulas.
- Native Maestro/ADE netlist layout remains the proven execution foundation.

