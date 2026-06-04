# C-20 Execution-Agent Autonomous Handoff Acceptance Plan

> **For agents:** keep this scope narrow. C-20 validates the autonomous
> execution-agent handoff boundary using the existing C-18/C-19
> `run-native-turbo --parallel` path. It does not create a new optimizer
> framework.

## Goal

Prove that a fresh local execution-agent subagent can complete one real
100-evaluation optimizer run from a concise task packet, while the supervisor
agent only prepares the packet/project and audits returned artifacts.

## Scope Guard

Allowed:

- create one clean local practice workspace under `/tmp/ic_auto_opt_c20`;
- write one local-only execution task packet;
- dispatch one local worker subagent as the execution agent;
- run the existing command:

```text
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals 100 --cadence-cshrc CADENCE_CSHRC
```

- audit returned reports and real manifests;
- write one sanitized repo note under `docs/debug/`.

Forbidden:

- broad optimizer framework work;
- hand-picked candidates;
- replacing native `Turbo1.optimize()`;
- Python PSF parsing;
- OCEAN/Calculator formula rewriting;
- metric formula changes;
- flattening native Maestro/ADE netlist layout;
- committing raw `input.scs`, protected sidecars, PSF/raw data, full Cadence
  logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`;
- calling Claude as the execution agent.

## Task 1: Prepare Autonomous Handoff Packet

**Status:** Complete, verified-only.

- [x] Prepare `/tmp/ic_auto_opt_c20/bridge_test_inv` from the accepted C-18
  source project.
- [x] Preserve `netlists/exported/input.scs`, `ade_e.scs`, and `amap/`.
- [x] Remove old `runs/`, `reports/`, `state/`, `data/`, and stale optimizer
  ledger rows.
- [x] Write local-only `EXECUTION_AGENT_TASK.md` under `/tmp/ic_auto_opt_c20`.

## Task 2: Local Execution-Agent Run

**Status:** Complete, verified-only.

- [x] Dispatch a fresh local worker subagent.
- [x] Give it the C-20 task packet and only necessary path/command context.
- [x] Require it to run the existing Hermes command, not ad-hoc scripts.
- [x] Require returned stdout/stderr summaries and artifact paths.

Notes:

- Attempt 1 followed the command but ran real tools under sandbox restrictions
  and judged success from exit status/stdout only. Supervisor audit rejected it:
  100 result manifests were failed and metric manifests were missing.
- The local-only task packet was corrected to require non-sandbox execution and
  manifest-level audit.
- Attempt 2 ran through the corrected packet and returned report/trace paths,
  result/metric manifest status counts, settings audit, and a blocker.

## Task 3: Supervisor/Hermes Acceptance Audit

**Status:** Complete, verified-only.

- [x] Verify command completed 100 optimizer evaluations.
- [x] Verify returned report and trace exist.
- [x] Verify 100 real result manifests exist and succeeded.
- [x] Verify metric manifests exist and classify candidate-level metric failures.
- [x] Verify settings stayed `preset=ax`, `threads_per_run=10`,
  `parallel_jobs=10`, and `output_format=psfxl`.
- [x] Verify no formula rewrite, PSF parsing, hand-picked candidate list, or
  native layout flattening is evident.
- [x] Write sanitized acceptance note.

Supervisor audit result:

- Attempt 2 completed 100 optimizer evaluations and 100 trace rows.
- 100 result manifests succeeded.
- 100 metric manifests were produced: 80 succeeded and 20 failed.
- 18 metric failures were candidate-level scalar/non-scalar failures.
- 2 metric failures were OCEAN command/license failures:
  `real_057` and `real_075`.
- Settings audit passed for `preset=ax`, `threads_per_run=10`,
  `parallel_jobs=10`, and `output_format=psfxl`.
- Handoff behavior is accepted. Fully green real-tool acceptance is blocked by
  residual OCEAN command/license failures.

## Task 4: Closeout

**Status:** Complete, verified-only.

- [x] Update current-state and progress nodes.
- [x] Run verification.
- [ ] Commit plan, sanitized note, and progress files.
