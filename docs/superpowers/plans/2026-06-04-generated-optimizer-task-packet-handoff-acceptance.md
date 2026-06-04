# Generated Optimizer Task Packet Handoff Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the C-23 Hermes-generated optimizer execution-agent task packet can drive the proven `run-native-turbo --parallel` flow through a local worker-agent handoff and supervisor/Hermes manifest-level audit.

**Architecture:** Reuse the existing native TuRBO runner and C-7 Spectre/OCEAN adapter path. Hermes generates the task packet; a local execution agent receives only that packet and runs the exact command; the supervisor/Hermes side accepts or rejects the run from returned manifests and reports, not from command exit status alone.

**Tech Stack:** Existing `hermes-workflow package-optimizer-task`, `hermes-workflow run-native-turbo --parallel`, local worker agent, Cadence cshrc, existing reports/manifests, pytest/ruff for contract regression.

---

## Scope Guard

Allowed:

- prepare one clean local C-24 workspace under `/tmp`;
- generate one optimizer task packet with `hermes-workflow package-optimizer-task`;
- hand the generated task packet to one local worker agent;
- let the worker run the existing `run-native-turbo --parallel --max-evals 100` path after explicit task step confirmation;
- audit returned reports, trace rows, result manifests, metric manifests, and Spectre settings.

Forbidden:

- call Claude CLI as the execution agent;
- create a new optimizer algorithm or scheduler;
- hand-pick candidate points;
- parse PSF in Python;
- rewrite OCEAN formulas;
- change approved metric formulas;
- flatten or replace the native Maestro/ADE netlist layout;
- treat command exit status alone as acceptance evidence;
- commit raw input decks, protected sidecars, PSF/raw data, full Cadence logs, or local `/tmp` evidence.

## File Plan

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify as milestone anchor: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify as route anchor: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Create if the run happens: `docs/debug/2026-06-04-c24-generated-task-packet-handoff.md`
- No production code changes are expected unless the acceptance run exposes a concrete bug.

## Task 1: Workspace And Generated Packet Gate

**Risk:** Low. Local file preparation only; no real tools.

**Status:** Complete.

- [x] **Step 1: Prepare local workspace**

Use a clean `/tmp/ic_auto_opt_c24/bridge_test_inv` workspace based on the latest accepted real-tool project shape. Preserve native `netlists/exported/input.scs`, `ade_e.scs`, and `amap/`. Remove stale `runs/`, `reports/`, `state/`, and `ledger/` outputs unless the selected source intentionally provides a clean initial state.

- [x] **Step 2: Generate the C-23 optimizer task packet**

Run from the repo:

```bash
.venv/bin/hermes-workflow package-optimizer-task /tmp/ic_auto_opt_c24/bridge_test_inv --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
```

Expected outputs:

```text
/tmp/ic_auto_opt_c24/bridge_test_inv/execution_package/OPTIMIZER_EXECUTION_TASK.md
/tmp/ic_auto_opt_c24/bridge_test_inv/execution_package/optimizer_execution_manifest.json
```

- [x] **Step 3: Gate the packet before worker handoff**

Verify:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Acceptance:

- task packet uses absolute project and Cadence cshrc paths;
- packet contains manifest-level audit requirement;
- packet forbids hand-picked points, PSF parsing, and OCEAN formula rewriting;
- no real Spectre/OCEAN/Virtuoso/worker execution has occurred in Task 1.

Task 1 result:

- Initial workspace: `/tmp/ic_auto_opt_c24/bridge_test_inv`.
- Retry workspace used for accepted rerun: `/tmp/ic_auto_opt_c24_retry/bridge_test_inv`.
- Generated packet artifacts:
  - `execution_package/OPTIMIZER_EXECUTION_TASK.md`
  - `execution_package/optimizer_execution_manifest.json`
- Packet used absolute project and Cadence cshrc paths, preserved the existing `run-native-turbo --parallel` route, and kept manifest-level audit as required behavior.

## Task 2: Local Worker-Agent Execution

**Risk:** High. Real tools and local worker-agent handoff.

**Status:** Complete after one rejected sandbox attempt and one accepted non-sandbox rerun.

- [x] **Step 1: Dispatch one local worker agent**

Give the worker only:

```text
/tmp/ic_auto_opt_c24/bridge_test_inv/execution_package/OPTIMIZER_EXECUTION_TASK.md
/tmp/ic_auto_opt_c24/bridge_test_inv/execution_package/optimizer_execution_manifest.json
```

The worker must not receive hidden chat context. It must run the command from the generated packet, use non-sandbox Cadence execution if required, and return artifact paths plus a concise manifest-level summary.

- [x] **Step 2: Run the generated command**

Expected command shape:

```bash
hermes-workflow run-native-turbo /tmp/ic_auto_opt_c24/bridge_test_inv --parallel --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

Acceptance is not based on exit status alone. The worker must return:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
state/optimizer_state.json
ledger/experiment_ledger.jsonl
```

Task 2 result:

- First attempt on `/tmp/ic_auto_opt_c24/bridge_test_inv` was rejected. Spectre failed in the sandbox before metric extraction with `cannot create pipe [Operation not permitted]` and `can't create server socket`.
- Rerun `Task 2R` on `/tmp/ic_auto_opt_c24_retry/bridge_test_inv` used the same generated packet semantics and ran through the approved non-sandbox real-tool path.
- Rerun completed `100` optimizer evaluations and returned the required report, trace, state, and ledger artifacts.

## Task 3: Supervisor/Hermes Acceptance Audit

**Risk:** Medium. Audit only; no rerun unless the returned evidence is incomplete.

**Status:** Complete.

- [x] **Step 1: Audit returned artifacts**

Check:

- `native_turbo_optimizer_report.json` exists and is readable;
- `native_turbo_optimizer_evaluations.jsonl` row count matches the reported evaluation count;
- result manifests exist for real-tool evaluations and are not accepted from command exit status alone;
- metric manifests either pass or are classified as candidate-level failures/tool failures;
- Spectre settings are consistent: `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, `output_format=psfxl`;
- no worker evidence indicates hand-picked candidate points, PSF parsing, or formula rewriting.

- [x] **Step 2: Write sanitized audit note**

Write only sanitized summary evidence to:

```text
docs/debug/2026-06-04-c24-generated-task-packet-handoff.md
```

Do not commit raw local artifacts.

Task 3 result:

- Sanitized audit note: `docs/debug/2026-06-04-c24-generated-task-packet-handoff.md`.
- Accepted report: `/tmp/ic_auto_opt_c24_retry/bridge_test_inv/reports/native_turbo_optimizer_report.json`.
- Evaluation count: `100`.
- Result manifests: `100`, all succeeded.
- Metric manifests: `100`, with `79 succeeded` and `21 failed` candidate-level metric results.
- Optimizer status counts: `36 feasible`, `43 constraint_failed`, `21 metric_check_failed`.
- Settings audit: `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, `output_format=psfxl`.
- Best accepted candidate: `real_021`, `FN=10`, `WN=1.1u`, `FP=9`, `WP=0.5u`, objective `4.305718220077049e-14`.

## Task 4: Closeout Or Focused Fix Decision

**Risk:** Low-to-medium. Docs and decision.

**Status:** Complete.

- [x] **Step 1: If accepted, close C-24**

Record that the generated task packet handoff path is accepted.

- [x] **Step 2: If blocked, write the smallest bug fix scope**

If C-24 exposes a bug, write one narrow fix scope tied to the observed failure. Do not create a broad execution framework.

- [x] **Step 3: Final verification**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

For code changes, also run focused pytest/ruff before any commit.

Task 4 result:

- C-24 is accepted.
- No production code fix was required.
- The only observed blocker was an invalid sandbox execution environment in the first worker attempt. The accepted route requires non-sandbox Cadence execution for Spectre/OCEAN.
- No raw local Cadence artifacts were committed.
