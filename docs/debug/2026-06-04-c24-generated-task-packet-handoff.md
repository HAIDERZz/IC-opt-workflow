# C-24 Generated Optimizer Task Packet Handoff Audit

Date: 2026-06-04

## Scope

C-24 validated that the Hermes-generated optimizer execution task packet from C-23 can drive the proven native TuRBO batch optimizer route and then be accepted by supervisor/Hermes manifest-level audit.

No raw input decks, PSF data, protected sidecars, or full Cadence logs are committed here. Raw evidence remains local under `/tmp`.

## Attempt 1

Workspace:

```text
/tmp/ic_auto_opt_c24/bridge_test_inv
```

Result: rejected.

The local worker-agent attempted the generated packet command, but Spectre ran in a sandboxed environment and failed before metric extraction. The failure was at the Spectre startup boundary, not OCEAN formula evaluation:

```text
cannot create pipe [Operation not permitted]
can't create server socket
```

Evidence summary:

- `100` real-run `result_manifest.json` files were produced.
- `0` `metric_result_manifest.json` files were produced.
- `native_turbo_optimizer_report.json` reported `100` metric-check failures.
- The run did not satisfy C-24 acceptance because command execution was not in the required non-sandbox Cadence environment.

## Attempt 2R

Workspace:

```text
/tmp/ic_auto_opt_c24_retry/bridge_test_inv
```

Command semantics from generated packet:

```text
hermes-workflow run-native-turbo /tmp/ic_auto_opt_c24_retry/bridge_test_inv --parallel --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

This rerun used the same generated task-packet semantics, but the command was executed through the approved non-sandbox real-tool path so Spectre/OCEAN could create the required pipes and sockets.

Result: accepted.

Audit summary:

- `native_turbo_optimizer_report.json` status: `completed`.
- Evaluation count: `100`.
- Batch count: `11`.
- Max batch worker count: `10`.
- Result manifests: `100`.
- Result manifest status: `100 succeeded`.
- Metric manifests: `100`.
- Metric manifest status: `79 succeeded`, `21 failed`.
- Optimizer status counts: `36 feasible`, `43 constraint_failed`, `21 metric_check_failed`.
- Spectre settings audit: all `100` result manifests used `preset=ax`, `threads_per_run=10`, and `output_format=psfxl`.
- Trace/report concurrency audit: `parallel_jobs=10`, `max_batch_worker_count=10`.

Best candidate:

```text
run_id: real_021
FN=10
WN=1.1u
FP=9
WP=0.5u
rise=7.29983959758093e-11
fall=7.454038697692739e-11
DC=0.0002918363655918434
objective=4.305718220077049e-14
```

## State/Ledger Note

`state/optimizer_state.json` is present, but currently behaves as a running optimizer snapshot rather than the canonical completion marker: its `status` remains `running` and `current_evaluations` counts recorded successful metric rows. This is consistent with earlier accepted C-18/C-21 evidence. C-24 acceptance is therefore based on `native_turbo_optimizer_report.json`, JSONL trace rows, result manifests, metric manifests, and settings audit, not on state status alone.

## Decision

C-24 is accepted.

The generated optimizer task packet is valid for the real workflow only when the execution agent runs Cadence tools in a non-sandbox real-tool environment. A sandboxed run may exit or produce files, but it is invalid evidence if Spectre cannot create required pipes/sockets.
