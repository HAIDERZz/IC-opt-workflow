# Optimizer Practice-First Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development only after the user confirms execution. This is a practice-first plan, not an optimizer implementation plan.

**Goal:** Run one small but complete real optimizer practice using `virtuoso-bridge-lite` optimizer guidance and the local TuRBO implementation before designing or coding optimizer support in Hermes.

**Architecture:** Treat the already-passed C-7 Spectre + OCEAN single-point path as the simulation/metric foundation, but do not mistake a few manual candidates for an optimizer proof. The required proof is a native practice loop where an optimizer skill-guided objective calls real simulation/metric extraction repeatedly and TuRBO chooses at least one candidate after its initial sample set.

**Tech Stack:** `virtuoso-bridge-lite/skills/optimizer/SKILL.md`, local TuRBO at `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO`, existing Cadence/Spectre/OCEAN environment, the known-good `bridge_test_inv` Maestro/ADE netlist bundle, and local `/tmp` evidence only.

---

## Scope Lock

This plan intentionally does not add Hermes optimizer code.

Do not:

- create a new optimizer algorithm;
- create new Hermes optimizer schemas or broad framework assets;
- flatten or redesign the Maestro/ADE netlist bundle layout;
- parse PSF in Python;
- translate or rewrite Calculator/OCEAN formulas;
- commit raw Cadence decks, protected includes, PSF data, or full Cadence logs;
- proceed past a failed practice step by repairing manifests manually.

The only purpose is to prove the optimizer route from practice before productizing it.

## Required External References

Read these before running optimizer practice:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/virtuoso-bridge-lite/skills/optimizer/SKILL.md
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO/README.md
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO/turbo/turbo_1.py
```

Important constraints from those files:

- The optimizer skill is for black-box multi-parameter optimization, not single-variable sweeps.
- TuRBO is a minimization algorithm.
- TuRBO needs at least `2 * n_params` initial samples.
- The local `Turbo1` implementation asserts `max_evals > n_init`.
- With four `bridge_test_inv` variables, the smallest useful practice is:

```text
n_params = 4
n_init = 8
max_evals = 9
batch_size = 1
```

This is the minimum that exercises TuRBO beyond pure initialization.

## Known-Good Simulation Foundation

Use the C-7 closure result as the reference behavior:

```text
Spectre runs from runs/real/<run_id>/netlist
-> Spectre writes PSF to sibling runs/real/<run_id>/psf
-> OCEAN evaluates approved formulas
-> Python records scalar outputs/provenance only
```

Reference values from the successful inverter single-point closure:

```text
rise = 7.52016846017672e-11 s
fall = 1.078998721053984e-10 s
DC   = 0.0002588877964196586 W
```

## Practice Workspace

Use local temporary artifacts only:

```bash
export PRACTICE_ROOT=/tmp/ic_auto_opt_optimizer_practice
export PRACTICE_PROJECT=$PRACTICE_ROOT/bridge_test_inv
export TURBO_ROOT=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO
export OPTIMIZER_SKILL=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/virtuoso-bridge-lite/skills/optimizer/SKILL.md
```

Use the same `bridge_test_inv` Maestro-exported netlist bundle and approved `metrics.yaml` that already passed the C-7 closure flow.

## Task 1: Baseline Package Shape Check

**Status:** Complete, verified-only.

**Intent:** Confirm the practice workspace still produces the proven ADE-style single-point package before optimizer work starts.

**Commands:**

```bash
rm -rf "$PRACTICE_PROJECT"
hermes-workflow init "$PRACTICE_PROJECT"
# User or execution agent places the known-good Maestro/ADE netlist bundle under:
# "$PRACTICE_PROJECT/netlists/exported/"
hermes-workflow validate "$PRACTICE_PROJECT"
hermes-workflow package "$PRACTICE_PROJECT"
hermes-workflow prepare-netlist "$PRACTICE_PROJECT"
hermes-workflow dry-run "$PRACTICE_PROJECT"
hermes-workflow preflight-health "$PRACTICE_PROJECT"
hermes-workflow approve "$PRACTICE_PROJECT"
hermes-workflow prepare-real-run "$PRACTICE_PROJECT" --run-id real_001
```

**Expected Evidence:**

- `runs/real/real_001/netlist/input.scs` exists.
- Exported sidecars needed by the Maestro deck are inside `runs/real/real_001/netlist/`.
- `runs/real/real_001/metric_extraction_request.json` contains approved formulas unchanged.
- Verified in `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv`.
- Verified sidecars include `runs/real/real_001/netlist/ade_e.scs` and `runs/real/real_001/netlist/amap/`.
- Verified `metric_extraction_request.json` declares `prepared_input_scs` as `runs/real/real_001/netlist/input.scs` and `expected_psf_dir` as `runs/real/real_001/psf`.
- Verified no PSF exists before Task 2, as expected for a package-only baseline.

**Stop Condition:** If this package differs from the C-7 closure shape, fix the package/layout before touching optimizer practice.

## Task 2: Single-Point Replay Sanity Check

**Status:** Complete, verified-only.

**Intent:** Confirm the clean practice workspace reproduces the already proven real simulation/metric chain.

**Commands:**

```bash
tools/run_spectre_ocean_adapter.py "$PRACTICE_PROJECT" --run-id real_001
hermes-workflow check-real-run "$PRACTICE_PROJECT" --run-id real_001
hermes-workflow check-metric-results "$PRACTICE_PROJECT" --run-id real_001
hermes-workflow record-real-result "$PRACTICE_PROJECT" --run-id real_001
```

**Expected Evidence:**

- `result_manifest.json` status is `succeeded`.
- `metrics/metric_result_manifest.json` status is `succeeded`.
- `ledger/experiment_ledger.jsonl` has exactly one checked real row.
- `state/optimizer_state.json` has `current_evaluations = 1`.
- Metrics are close to the known-good C-7 closure values unless the deck intentionally changed.
- First attempt on `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv` returned `rise/fall non_scalar` for template default lower-bound parameters `FN=2`, `WN=0.3u`, `FP=2`, `WP=0.3u`.
- This is a candidate-level performance failure: when the same OCEAN script, request, layout, and approved formulas produce scalars for other parameter points, a parameter point that cannot produce the required scalar metrics should be treated as not satisfying the performance target. It is not an OCEAN, formula, request, or layout failure by itself.
- Optimizer practice must convert this class of metric failure into a finite penalty or constraint failure for that candidate, not stop the whole workflow as a tool-chain failure.
- Successful replay used `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv_baseline_001` with C-7 closure baseline parameters `FN=4`, `WN=0.6u`, `FP=4`, `WP=1.2u`.
- Successful replay metrics exactly matched C-7 closure:
  - `rise = 7.52016846017672e-11 s`
  - `fall = 1.078998721053984e-10 s`
  - `DC = 0.0002588877964196586 W`
- `record-real-result` wrote one ledger row and `state/optimizer_state.json` with `current_evaluations = 1`.
- `state/best_candidate.json` was absent after this replay because the recorded result had `simulation_status = real_constraint_fail`; this does not block the single-point tool-chain sanity check.

**Stop Condition:** If this fails, compare against C-7 closure evidence first. Do not proceed to optimizer practice.

## Task 3: Optimizer Skill And TuRBO Environment Gate

**Intent:** Verify the actual optimizer ingredients before running a real optimization loop.

**Commands:**

```bash
sed -n '1,140p' "$OPTIMIZER_SKILL"
python3 - <<'PY'
import sys
sys.path.insert(0, "/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO")
from turbo import Turbo1
print(Turbo1.__name__)
PY
```

**Expected Evidence:**

- The optimizer skill describes black-box optimization with TuRBO or scipy.
- `Turbo1` imports from the local TuRBO checkout.
- The practice record states the selected optimizer budget:

```text
n_init = 8
max_evals = 9
batch_size = 1
```

**Stop Condition:** If TuRBO cannot import, fix the environment or record the exact missing dependency before any optimizer development.

## Task 4: Native Optimizer Full-Loop Practice

**Intent:** Run a real optimizer flow, not a hand-picked point sequence.

Create only a temporary practice script under `/tmp`, for example:

```text
/tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py
```

The script must follow `optimizer/SKILL.md`:

- define `PARAMS = ["FN", "WN", "FP", "WP"]`;
- define numeric lower/upper bounds from the approved project variables;
- call local `Turbo1`;
- set `n_init=8`, `max_evals=9`, `batch_size=1`;
- implement an `objective(x)` that returns one finite scalar to minimize;
- on simulation or metric failure, return the configured finite failure penalty, not `nan` or `inf`;
- record every evaluated candidate, metric values, objective value, status, and artifact paths in `/tmp`.

The evaluation function may use the already proven Spectre + OCEAN path, but it must preserve these rules:

- use the Maestro/ADE netlist bundle shape that passed C-7 closure;
- run Spectre/OCEAN in the same result context that makes approved formulas valid;
- do not parse PSF in Python;
- do not rewrite formulas;
- do not commit raw Cadence artifacts.

**Expected Evidence:**

- TuRBO creates at least nine evaluations for the four-variable problem.
- At least one evaluation occurs after the eight initial samples.
- Each successful evaluation has Spectre and OCEAN scalar evidence.
- The optimizer returns a best candidate and best objective.
- Failures, if any, use a finite penalty and preserve logs.

**Stop Condition:** If the only way to run this is to bypass too much of the known-good result context, stop and record the missing integration seam instead of forcing a fake success.

## Task 5: Productization Decision

**Intent:** Convert real optimizer practice into one narrow next development scope.

Write a short practice note:

```text
docs/debug/2026-06-03-optimizer-practice-first-result.md
```

The note must include:

- exact optimizer skill and TuRBO references used;
- exact command that launched the practice optimizer;
- final evaluation count;
- final best candidate and objective;
- whether all metric values came from OCEAN;
- whether the practice used Hermes package/check/record contracts or a native bridge-only loop;
- the smallest productization gap.

Allowed next targets:

```text
A. Native optimizer practice passed; design a narrow Hermes/bridge optimizer adapter around the proven script.
B. Native optimizer passed but Hermes lacks explicit candidate injection; add that contract first.
C. TuRBO or optimizer.skill integration failed; fix the environment/invocation before Hermes optimizer development.
D. Spectre/OCEAN failed inside optimizer loop; fix the tool boundary before optimizer development.
```

## Completion Criteria

This practice plan is complete only when:

- `real_001` still passes the clean single-point replay;
- a real optimizer practice invokes `optimizer/SKILL.md` guidance and local `Turbo1`;
- the practice runs at least `n_init=8`, `max_evals=9`, `batch_size=1` for `bridge_test_inv`;
- metrics are OCEAN-produced, not Python-reimplemented;
- no raw Cadence data is committed;
- the next development scope is chosen from A/B/C/D above.
