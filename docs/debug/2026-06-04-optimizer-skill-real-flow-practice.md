# Optimizer Skill Real Flow Practice

Date: 2026-06-04

## Purpose

This note archives the first complete optimizer practice that follows the
`virtuoso-bridge-lite/skills/optimizer/SKILL.md` core pattern while using the
already-proven Hermes + Spectre + OCEAN real evaluation path.

The important correction is that this run did not use Hermes'
single-candidate suggestion loop as a proxy for optimization. Local `Turbo1`
from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO` drove candidate
selection through `Turbo1.optimize()`.

## Local Evidence

Raw artifacts are local-only and must not be committed.

```text
/tmp/ic_auto_opt_optimizer_skill_flow_001/summary.json
/tmp/ic_auto_opt_optimizer_skill_flow_001/evaluations.tsv
/tmp/ic_auto_opt_optimizer_skill_flow_001/evaluations.jsonl
/tmp/ic_auto_opt_optimizer_skill_flow_001/bridge_test_inv/
```

The practice used the known-good Maestro/ADE exported netlist bundle from the
C-7/C-14 closure path. Python did not parse PSF data and did not rewrite OCEAN
formulas.

## Flow tested

```text
Turbo1.optimize()
-> objective(x)
-> quantize x into FN/WN/FP/WP
-> Hermes approved real-run package
-> C-7 Spectre/OCEAN adapter
-> check-real-run
-> check-metric-results
-> record-real-result when scalar metrics are valid
-> return finite scalar objective or finite failure penalty to TuRBO
```

Optimizer settings:

```text
params = FN, WN, FP, WP
n_init = 8
max_evals = 100
batch_size = 1
random_seed = 20260528
```

Spectre settings observed:

```text
preset = ax
threads_per_run = 10
parallel_jobs_limit = 10
actual_simultaneous_spectre_processes = 1
```

## Result Summary

```text
evaluation_count = 100
initialization_count = 8
turbo_trust_region_count = 92
recorded = 73
duplicate_candidate_skipped = 24
adapter_failed = 3
```

The three adapter failures were metric scalar failures, not broad tool-chain
failure:

```text
real_047: metric rise non_scalar, metric fall non_scalar
real_048: metric rise non_scalar, metric fall non_scalar
real_087: metric rise non_scalar, metric fall non_scalar
```

Best candidate:

```text
run_id = real_011
selection_phase = turbo_trust_region
FN = 11
WN = 1.9u
FP = 9
WP = 0.5u
rise = 7.248965506773538e-11 s
fall = 6.456994704970738e-11 s
DC = 0.0003013343489079966 W
objective = 4.1300765965648685e-14
constraint_penalty = 0
```

## Lessons

1. The correct optimizer validation route is native `Turbo1.optimize()`, not a
   Hermes one-candidate loop.
2. The objective must be feasibility-first: candidates that violate specs should
   receive finite penalty and only spec-satisfying candidates should compete by
   FOM.
3. Continuous TuRBO output plus discrete circuit variables causes duplicate
   quantized candidates. Product code must add quantized-candidate de-duplication
   and replacement sampling.
4. Metric non-scalar candidates should be recorded in optimizer trace as finite
   penalty observations or candidate-level failures. They should not stop the
   entire optimization unless the failure is classified as true tool/contract
   failure.
5. The first optimizer-selected candidate should be packageable without
   requiring a pre-existing lower-bound ledger seed. The product contract needs
   an explicit first-candidate path or an optimizer runner that owns the first
   package preparation.

## Productization Decision

Proceed with C-17: Native TuRBO Optimizer Runner MVP.

Do not add a broad optimizer framework. Productize only the proven path:

```text
Turbo1.optimize()
-> Hermes real-run package/evaluator
-> Spectre/OCEAN scalar metrics
-> feasibility-first objective
-> optimizer trace and best-candidate report
```

The next implementation must preserve:

- native Maestro/ADE netlist layout;
- exact approved OCEAN formulas;
- no Python PSF parsing;
- Spectre `threads_per_run` as per-process `+mt`;
- `parallel_jobs` as maximum simultaneous Spectre process count.
