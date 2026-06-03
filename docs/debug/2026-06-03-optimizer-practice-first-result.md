# Optimizer Practice-First Result

Date: 2026-06-03

## Scope

This note records the productization decision from `docs/superpowers/plans/2026-06-03-optimizer-practice-first.md`.

No Hermes optimizer code was added. Raw Cadence decks, PSF data, protected sidecars, and full tool logs remain local-only under `/tmp`.

## References Used

- Optimizer skill: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/virtuoso-bridge-lite/skills/optimizer/SKILL.md`
- Local TuRBO README: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO/README.md`
- Local TuRBO implementation: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO/turbo/turbo_1.py`
- Temporary practice script: `/tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py`

## Launch Command

```bash
./.venv/bin/python /tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py
```

## Result

- Final evaluation count: `9`
- TuRBO budget: `n_init=8`, `max_evals=9`, `batch_size=1`
- Post-initial TuRBO evaluations: `1`
- OCEAN scalar evaluations: `9`
- Finite penalty evaluations: `0`
- Status split: `7` `real_constraint_fail`, `2` `real_pass`

Best candidate:

```text
FN = 12
WN = 1.3u
FP = 2
WP = 2.5u
objective = 4.183168953894332e-14
```

Evidence:

```text
/tmp/ic_auto_opt_optimizer_practice/turbo_bridge_test_inv_001/summary.json
/tmp/ic_auto_opt_optimizer_practice/turbo_bridge_test_inv_001/evaluations.jsonl
```

## Metric Source

All metric values came from batch OCEAN scalar output through the C-7 Spectre/OCEAN adapter.

Python did not parse PSF data and did not rewrite Calculator/OCEAN formulas.

## Contract Path Used

The practice used Hermes package/check/record contracts, not a native bridge-only loop:

```text
candidate values
-> Hermes init/package/prepare-netlist/dry-run/preflight/approve/prepare-real-run
-> C-7 Spectre/OCEAN adapter
-> hermes-workflow check-real-run
-> hermes-workflow check-metric-results
-> hermes-workflow record-real-result
-> TuRBO objective return
```

The temporary script created one isolated project per evaluation and locked each candidate into `config/variables.yaml` by setting lower and upper bounds to the same values. That was acceptable for practice evidence, but it is not the right product interface.

## Productization Decision

Decision: **B. Native optimizer passed but Hermes lacks explicit candidate injection; add that contract first.**

The real optimizer route is viable:

- local `Turbo1` ran the required minimum four-variable budget;
- at least one candidate was chosen after initialization;
- every evaluation preserved the Maestro/ADE netlist bundle shape;
- Spectre/OCEAN produced scalar evidence for every evaluated candidate;
- Hermes validators and ledger/state recording accepted the returned real results.

The smallest productization gap is an explicit, narrow way to prepare a real-run package for a supervisor- or optimizer-selected candidate without rewriting project-level variable ranges for every point.

## Next Narrow Scope

Design the smallest candidate-injection contract needed by the proven loop:

```text
candidate parameters from optimizer
-> deterministic Hermes real-run package for that exact candidate
-> existing C-7 adapter
-> existing check-real-run/check-metric-results/record-real-result
```

Do not design a new optimizer framework yet. Keep TuRBO execution as an adapter-side practice-proven loop until the candidate injection package contract is stable.
