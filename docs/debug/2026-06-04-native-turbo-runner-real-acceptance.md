# C-17 Native TuRBO Runner Real Acceptance

Date: 2026-06-04

## Purpose

Validate that the productized Hermes `run-native-turbo` command can run the
same native `Turbo1.optimize()` style proven in practice, using Hermes real-run
packages and the Spectre/OCEAN adapter as the black-box evaluator.

This is a sanitized record. Raw Cadence decks, protected sidecars, PSF/raw data,
and full logs remain local-only under `/tmp`.

## Local Workspace

```text
/tmp/ic_auto_opt_c17_native_turbo_002/bridge_test_inv
```

The project was initialized from the Hermes template and used the known-good
C-7 closure exported netlist bundle:

```text
/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv/netlists/exported
```

## Command Shape

```text
hermes-workflow run-native-turbo PROJECT_DIR \
  --max-evals 100 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

The command was run through the Cadence csh environment outside the Codex
sandbox restrictions.

## Result

The command completed normally:

```text
native turbo optimization completed: 100 evaluations
```

Trace summary:

- Total evaluations: 100
- Initialization evaluations: 8
- TuRBO trust-region evaluations: 92
- Feasible candidates: 45
- Constraint-failed candidates: 43
- Metric-check-failed candidates: 12
- Ledger rows: 88
- Recovery decisions: 12
- Residual Spectre processes after completion: 0

Best candidate:

```json
{
  "run_id": "real_030",
  "selection_phase": "turbo_trust_region",
  "parameters": {
    "FN": "12",
    "FP": "2",
    "WN": "1.7u",
    "WP": "2.7u"
  },
  "metrics": {
    "DC": 0.0003265612598325413,
    "fall": 6.190153048273253e-11,
    "rise": 6.72081749122453e-11
  },
  "objective": 4.216222805039221e-14,
  "constraint_penalty": 0.0,
  "status": "feasible"
}
```

Spectre setting audit across all 100 prepared manifests:

```text
preset: ax
threads_per_run: 10
parallel_jobs: 10
output_format: psfxl
```

## Implementation Lessons

- C-17 is now a native TuRBO runner, not the older one-candidate suggestion
  loop.
- `Turbo1.optimize()` drives candidate generation directly.
- Hermes remains the deterministic contract layer: package, adapter handoff,
  checks, metric-result validation, recovery decisions, and ledger/state record.
- Candidate-local metric failures must be finite penalty observations. They are
  not automatically workflow-level adapter failures if Hermes can classify the
  returned manifests.
- Repeated workflow-level failures that do not produce classifiable candidate
  manifests should stop the runner instead of consuming the full optimization
  budget as penalties.
- The authoritative metric path remains OCEAN-produced scalar values. Python
  does not parse PSF and does not rewrite Calculator/OCEAN formulas.
- Native Maestro/ADE netlist layout remains required.

## Verdict

C-17 real acceptance passed. The next productization step should build directly
on this native `Turbo1.optimize()` runner path rather than extending the older
single-candidate suggestion loop.
