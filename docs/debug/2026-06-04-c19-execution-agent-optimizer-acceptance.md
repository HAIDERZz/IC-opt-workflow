# C-19 Execution-Agent Optimizer Acceptance Audit

Date: 2026-06-04

## Initial Status

Blocked before real Spectre/OCEAN execution.

## Command Shape

```text
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals 100 --cadence-cshrc CADENCE_CSHRC
```

Concrete local project:

```text
/tmp/ic_auto_opt_c19/bridge_test_inv
```

## Observed Result

- Exit status: non-zero.
- stdout: `optimizer state is missing`.
- stderr: empty.
- No native TuRBO summary, trace, optimizer state, or real-results ledger was produced.
- No Spectre/OCEAN process was reached.

Local-only evidence:

```text
/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/run_native_turbo_stdout.txt
/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/run_native_turbo_stderr.txt
/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/returned_artifact_hashes.sha256
```

## Root Cause

C-19 Task 1 copied the accepted C-18 project, removed `state/`, `runs/`,
`reports/`, and `data/`, but left the old `ledger/experiment_ledger.jsonl`.

That made the project internally inconsistent:

```text
ledger/experiment_ledger.jsonl exists with previous C-18 rows
state/optimizer_state.json is missing
```

`prepare_explicit_candidate_real_run()` allows a first optimizer candidate when
both ledger and state are absent, but if ledger rows exist it requires
`state/optimizer_state.json` so ledger/state consistency can be checked. The
C-19 practice project failed this guard before any real tool invocation.

## Acceptance Decision

C-19 real execution-agent acceptance is blocked, not failed at the physical
tool boundary.

This blocker is not caused by:

- Spectre command settings;
- OCEAN formula compatibility;
- metric extraction;
- TuRBO candidate generation;
- execution-agent behavior after tool launch.

## Smallest Corrective Action

Use C-19 Task 4 Branch B.

The narrow fix should correct clean project preparation so a fresh
`run-native-turbo` handoff starts from a consistent empty optimizer state:

- remove stale `ledger/experiment_ledger.jsonl` when preparing a clean C-19
  practice project, or
- initialize an empty optimizer state and matching empty ledger through an
  existing Hermes contract if that becomes the preferred product behavior.

The first option is the smallest practice-flow correction for C-19 because the
run is intended to start a fresh 100-evaluation optimizer acceptance, not resume
C-18 history.

Do not change formulas, parse PSF, replace TuRBO, or create a new optimizer
framework.

## Task 4 Closure

Status: accepted after a narrow blocker fix and one clean rerun.

Fixes applied:

- C-19 clean project preparation now removes stale
  `ledger/experiment_ledger.jsonl` when starting from the accepted C-18
  project. The C-19 acceptance is a fresh handoff, not a resume of C-18
  optimizer history.
- Native TuRBO candidate quantization now clamps continuous-step candidates to
  the last approved grid step when the configured upper bound is intentionally
  off-grid. Example: `lower=0.3u`, `upper=3u`, `step=0.2u` clamps high raw
  values to `2.9u`, not `3u`.

One sandbox-only rerun attempt reached 100 evaluations but all Spectre runs
failed with Cadence pipe/socket errors. This was not accepted as project
evidence because Spectre was run inside the Codex sandbox.

The final rerun used the same Hermes command outside the sandbox:

```text
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals 100 --cadence-cshrc CADENCE_CSHRC
```

Acceptance summary:

- command exit status: 0;
- optimizer evaluations: 100;
- real result manifests: 100;
- metric result manifests: 100;
- result manifest status counts: `succeeded=100`;
- metric manifest status counts: `succeeded=79`, `failed=21`;
- optimizer status counts: `feasible=33`, `constraint_failed=46`,
  `metric_check_failed=21`;
- batch count: 11;
- maximum worker metadata: 10;
- Spectre settings audit across all result manifests:
  `preset=ax`, `threads_per_run=10`, `output_format=psfxl`;
- trace parallel audit: `parallel_jobs=10`, `threads_per_run=10`;
- no Python PSF parsing, OCEAN formula rewrite, metric-formula change, or
  native Maestro/ADE layout flattening occurred.

Best accepted candidate:

```text
run_id: real_041
parameters: FN=8, WN=2.3u, FP=9, WP=0.5u
metrics: rise=7.272202316589962e-11, fall=6.636203994189362e-11, DC=0.0002997894042795048
objective: 4.169592842385839e-14
```

Acceptance decision:

C-19 execution-agent optimizer acceptance passes. The supervisor-to-execution
handoff is viable when the execution agent runs the existing
`run-native-turbo --parallel` command on a clean project that preserves the
native Maestro/ADE netlist layout.
