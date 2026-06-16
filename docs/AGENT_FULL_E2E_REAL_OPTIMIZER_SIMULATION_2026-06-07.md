# Agent Full E2E Real Optimizer Simulation 2026-06-07

> Historical command notice: command examples in this evidence note may show
> old workload/resource CLI flags. Current release product first runs read those
> values only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

Status: complete, verified-only, stopped for user review.

This simulation tested the complete user -> supervisor agent -> execution agent
-> real optimizer -> supervisor -> user loop with a fresh user-only project.
Unlike the earlier closeout-only simulation, this run executed the real
OpenBox/Spectre/OCEAN optimizer path.

## User Project

Fresh project:

```text
/tmp/ic_auto_opt_agent_e2e_g2qieZ/Mixer_opt_muti_tb_full
```

Initial user-owned input:

```text
opt_requirement.md
```

The project started without `config/`, `netlists/`, `runs/`, `reports/`,
`ledger/`, `state/`, or `execution_package/`.

## Roles

Supervisor agent:

```text
agent_id: 019e9dff-8503-7652-9ec0-f640b6236f27
nickname: Rawls
```

Execution agent:

```text
agent_id: 019e9e04-04c2-7c81-a43c-56539ae2dd98
nickname: Pascal
```

Coordinator role:

```text
Simulated user and monitored both agents.
```

## Flow

The intended flow was:

```text
user instruction
-> supervisor prepares project
-> supervisor issues execution request
-> execution agent runs full 100-eval optimizer
-> execution agent reports artifacts
-> supervisor interprets reports
-> supervisor reports to user
```

## Supervisor Preparation

The supervisor first ran:

```text
check-requirement
prepare-from-requirement
validate
check-project-ready
```

This produced:

```text
project readiness: pass
readiness: ready_for_first_run
multi_testbench_netlists: pass - 3 testbench netlist bundles are ready
```

### Supervisor Drift Found

The first execution handoff was incomplete.

The supervisor skipped:

```text
package
prepare-netlist
dry-run
preflight-health
approve
package-optimizer-task
```

The execution agent therefore failed before evaluations with:

```text
execution manifest is missing
```

This was valid drift detection. The root cause was not Cadence, Spectre, OCEAN,
or OpenBox. The root cause was the supervisor handoff missing the deterministic
package/preflight/approval gate required by the real-run contract.

The supervisor corrected this by running the missing offline commands:

```text
package
prepare-netlist
dry-run
preflight-health
approve
package-optimizer-task --backend openbox --max-evals 100 --parallel
check-project-ready
```

After correction, these handoff artifacts existed:

```text
execution_package/execution_manifest.json
execution_package/EXECUTION_TASK.md
execution_package/optimizer_execution_manifest.json
execution_package/OPTIMIZER_EXECUTION_TASK.md
supervisor_instruction.json
```

## Execution

The execution agent then ran the full real optimizer workflow.

Execution was not reduced to a smoke test.

Run settings:

```text
backend: OpenBox
max_evals: 100
batch_size: 10
parallel_jobs: 12
threads_per_run: 10
optimizer_cpu_threads: 4
random_seed: 20260528
Spectre override: 25.1
```

Execution completed:

```text
reports/optimizer_evaluations.jsonl: 100 rows
reports/optimizer_run_acceptance_report.json: accepted
reports/optimizer_run_report.json: completed
```

Status counts:

```text
feasible: 19
constraint_failed: 65
metric_check_failed: 16
real_check_failed: 0
```

The execution agent did not hand-pick points, rewrite OCEAN formulas, parse PSF,
or merge testbenches.

## Report Results

`optimizer-status` reported:

```text
decision: accept_best_observed
confidence: medium
global optimum claim: false
best observed: real_066
evaluations: 100
continuation recommended: false
plateau detected: true
```

Best feasible observed candidate:

```text
run_id: real_066
parameters:
  F=26
  W=1u
  L=40n
  VB_LO=310m
metrics:
  BW=19171311625.11458
  MAX_GAIN=4.242801858394763
  NF_3G=11.81241967045868
  IIP3=3.206487765822459
  P1DB=-0.8997623115419788
objective=-0.0503357919658288
```

Margins are thin:

```text
BW: about 0.171 GHz above 19 GHz
MAX_GAIN: about 0.243 dB above 4 dB
NF_3G: about 0.188 dB below 12 dB
```

## Decision Conflict Found

The decision report recommended a different point:

```text
recommended_run: real_057
status: constraint_failed
action: review_best_feasible_or_continue
confidence: low
```

`real_057` violates multiple constraints:

```text
BW=15.174 GHz < 19 GHz
MAX_GAIN=0.806 dB < 4 dB
NF_3G=12.842 dB > 12 dB
```

Supervisor interpretation:

```text
Do not accept real_057.
Consider real_066 as the current best feasible observed candidate.
Stop for user review before recording final acceptance.
```

This is a product issue in the decision-report path: `decide-optimizer-run`
can recommend a constraint-failed candidate when configured-objective ranking
is computed over all evaluable samples. It should either feasibility-filter the
recommended run or make infeasible recommendations impossible to mistake for
an accepted optimizer result.

## Final Project State

Because the simulated user did not approve final acceptance, no final summary
was recorded.

`check-project-ready` after the run reported:

```text
project readiness: pass
readiness: ready_for_first_run
optimizer_final_summary: warning - final optimizer summary is not present yet
```

This is coherent with the stop-for-user-review state, but the label
`ready_for_first_run` is not ideal after a completed optimizer run. A future
state such as `awaiting_user_decision` would be clearer.

## Behavior Drift Assessment

Observed supervisor drift:

- First handoff skipped package/preflight/approval.
- Corrected after execution-agent failure.

Observed execution-agent behavior:

- Correctly stopped on missing execution manifest.
- Correctly reran after supervisor provided the missing handoff artifacts.
- Completed 100 real evaluations.
- Did not reduce to a smoke run.
- Did not hand-pick points.
- Did not rewrite formulas or parse PSF.

Observed product/tooling issues:

1. The production manual and quickstart must include the full
   package/preflight/approval gate before real optimizer execution.
2. `decide-optimizer-run` must not present a constraint-failed candidate as the
   recommended run without a stronger guard.
3. `check-project-ready` needs a clearer post-run/pre-final-summary readiness
   state.
4. Legacy state artifacts may remain stale relative to optimizer closeout
   reports; final reports should remain the supervisor-facing source of truth.

## Verdict

The complete real tool flow can run end to end through 100 multi-testbench
evaluations, but the full agent workflow is not yet fully production-safe.

The next narrow fix should target the two blocking usability issues exposed by
this real simulation:

```text
1. Add package/preflight/approval to the production manuals and agent usage
   manual before run-openbox-real.
2. Harden decide-optimizer-run so it cannot recommend constraint_failed points
   as the primary recommended run.
```

Do not treat this simulation as a final accepted optimizer result until the
user explicitly approves `real_066` or requests continuation.
