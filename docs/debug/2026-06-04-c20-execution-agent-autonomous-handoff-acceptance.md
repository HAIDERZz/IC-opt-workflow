# C-20 Execution-Agent Autonomous Handoff Acceptance

Date: 2026-06-04

## Purpose

Validate the original supervisor-to-execution-agent workflow boundary:

```text
supervisor prepares concise task packet and clean project
-> fresh local execution-agent subagent runs the existing Hermes command
-> supervisor audits returned reports and manifests
```

C-20 intentionally did not add a new optimizer framework, did not hand-pick
candidate points, did not parse PSF in Python, did not rewrite OCEAN formulas,
and did not flatten the native Maestro/ADE netlist layout.

## Local-Only Workspace

```text
/tmp/ic_auto_opt_c20/bridge_test_inv
/tmp/ic_auto_opt_c20/evidence/execution_agent_autonomous_handoff_001/
```

The practice project was copied from the accepted C-18 project. Old `runs/`,
`reports/`, `state/`, `data/`, and stale optimizer ledger rows were removed.
The native exported netlist bundle was preserved.

## Attempt 1

The first local execution-agent subagent followed the command but judged success
only from command exit status and stdout.

Supervisor audit found:

- optimizer trace count: 100;
- result manifests: 100;
- result status counts: `failed=100`;
- metric manifests: 0;
- Spectre logs showed sandbox pipe/socket errors.

Decision:

Attempt 1 is rejected as real-tool evidence. It proved the task packet was too
weak because it did not require manifest-level acceptance checks.

Task packet correction:

- require non-sandbox real-tool execution;
- require result manifest count/status audit;
- require metric manifest count/status audit;
- require settings audit;
- state that command exit 0 is not sufficient.

## Attempt 2

The second local execution-agent subagent used the corrected task packet and
reported manifest-level results.

Command shape:

```text
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals 100 --cadence-cshrc CADENCE_CSHRC
```

Execution-agent report:

- command exit status: 0;
- optimizer evaluations: 100;
- trace rows: 100;
- result manifests: 100;
- result status counts: `succeeded=100`;
- metric manifests: 100;
- metric status counts: `succeeded=80`, `failed=20`;
- settings audit passed for `preset=ax`, `threads_per_run=10`,
  `parallel_jobs=10`, and `output_format=psfxl`;
- blocker reported: `real_057` and `real_075` had OCEAN command failures.

Supervisor audit confirmed:

- optimizer status counts: `31 feasible`, `49 constraint_failed`,
  `20 metric_check_failed`;
- batch count: 11;
- maximum worker metadata: 10;
- 18 metric failures were candidate-level scalar/non-scalar failures;
- 2 metric failures were real-tool OCEAN command/license failures.

The OCEAN command failures were:

```text
real_057: ocean return_code=35, missing scalar output, license checkout failure
real_075: ocean return_code=35, missing scalar output, license checkout failure
```

Best feasible candidate:

```text
run_id: real_015
parameters: FN=10, WN=2.3u, FP=2, WP=2.3u
metrics: rise=7.911498986368255e-11, fall=6.576741380755568e-11, DC=0.0002859220799323837
objective: 4.1425078203283664e-14
```

## Acceptance Decision

C-20 proves the autonomous handoff behavior:

- a fresh local execution-agent subagent can read a concise task packet;
- run the existing Hermes optimizer command;
- avoid hand-picked candidates and formula/layout changes;
- return report paths and manifest-level audit results;
- correctly surface a real-tool blocker instead of falsely claiming success.

C-20 does not prove a fully green 100-evaluation real-tool run under autonomous
execution-agent control, because 2 of 100 OCEAN metric extractions failed at the
tool/license layer.

## Next Product Step

Do not add broad workflow machinery.

The next narrow product step should address the real issue exposed by C-20:

```text
C-21: OCEAN Metric Extraction Retry / Concurrency Policy
```

Likely scope:

- retry OCEAN-only metric extraction for tool/license failures;
- keep Spectre results and candidate packages unchanged;
- do not retry candidate-level non-scalar metric failures;
- optionally cap OCEAN extraction concurrency separately from Spectre process
  concurrency if license contention continues.

