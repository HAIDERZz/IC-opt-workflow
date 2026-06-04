# Execution-Agent Optimizer Practice Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that an execution agent can use the existing Hermes workflow package and `run-native-turbo --parallel` command to complete one real 100-evaluation optimizer run in the proven Virtuoso/Spectre/OCEAN environment.

**Architecture:** Do not add a new optimizer framework. Reuse the C-18 batch native TuRBO runner, the native Maestro/ADE netlist layout, and the existing Hermes validation/check/report contracts. C-19 validates the agent handoff loop: supervisor prepares a narrow task packet, execution agent runs the existing command, supervisor/Hermes audits the returned reports and only then decides whether a surgical bug fix is needed.

**Tech Stack:** Existing `hermes-workflow` CLI, local TuRBO, Cadence Spectre/OCEAN through `/home/zzchen/cadence_ic231_env.csh`, `/tmp` local-only evidence, sanitized repo docs, pytest/ruff/cadence checker only for repo changes.

---

## Scope Guard

Allowed:

- create one clean local practice workspace under `/tmp/ic_auto_opt_c19`;
- write one execution-agent handoff packet that names exact inputs, command, expected outputs, forbidden actions, and acceptance criteria;
- run one real `hermes-workflow run-native-turbo --parallel --max-evals 100` acceptance through the execution-agent boundary after user confirmation;
- preserve native Maestro/ADE exported netlist structure;
- audit Spectre settings consistency: `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, `output_format=psfxl`;
- write one sanitized acceptance note under `docs/debug/`;
- fix only blocking bugs discovered by the C-19 real handoff run.

Forbidden:

- broad optimizer framework work;
- daemon, service, database, scheduler, or multi-project orchestration;
- replacing TuRBO or changing objective semantics without a new user decision;
- hand-picking 100 points instead of using native `Turbo1.optimize()` through `run-native-turbo`;
- Python PSF parsing;
- OCEAN formula rewriting or translation;
- changing approved metric formulas to hide adapter bugs;
- flattening or redesigning the native Maestro/ADE netlist layout;
- committing raw `input.scs`, protected include sidecars, PSF/raw data, full Cadence logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.

## Required Reading

- `AGENTS.md`
- `docs/CURRENT_TASK_STATE.json`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- `docs/superpowers/plans/2026-06-04-batch-native-turbo-parallel-runner.md`
- `docs/debug/2026-06-04-batch-native-turbo-parallel-acceptance.md`
- `src/hermes_workflow/native_turbo.py`
- `tools/run_spectre_ocean_adapter.py`

## Shared Shell Variables

Use these names in Task 2 and Task 3:

```bash
export REPO=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
export C19_ROOT=/tmp/ic_auto_opt_c19
export C19_PROJECT=/tmp/ic_auto_opt_c19/bridge_test_inv
export C19_EVIDENCE=/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001
export C19_SOURCE_PROJECT=/tmp/ic_auto_opt_c18_batch_native_turbo_001/bridge_test_inv
export C19_CADENCE_CSHRC=/home/zzchen/cadence_ic231_env.csh
export HERMES=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/hermes-workflow
```

If `$HERMES` does not exist, use the project virtual environment that passed C-18. Do not replace Hermes CLI calls with ad-hoc Python scripts.

## Artifact Policy

Committed artifacts are limited to:

- this plan;
- `docs/CURRENT_TASK_STATE.json`;
- progress/checkpoint docs required by `AGENTS.md`;
- one sanitized C-19 acceptance note under `docs/debug/` after the real run.

All raw execution evidence stays local-only under:

```text
/tmp/ic_auto_opt_c19/
```

## Task 1: Prepare Execution-Agent Handoff Packet

**Risk:** Low. This task writes a precise task packet and does not run real tools.

**Status:** Complete, verified-only.

**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-execution-agent-optimizer-practice-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify as required by cadence checker: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify as required by cadence checker: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [x] **Step 1: Verify repo state**

Run:

```bash
cd "$REPO"
git status --short
python3 tools/check_development_cadence.py
git diff --check
```

Expected:

- cadence checker passes before the C-19 state update or reports only the expected current-node drift caused by this task;
- no protected local raw evidence is staged.

- [x] **Step 2: Write local-only handoff packet**

Create:

```text
/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/EXECUTION_AGENT_TASK.md
```

with this exact content:

```markdown
# Execution Agent Task: C-19 Optimizer Practice Acceptance

Run one real 100-evaluation optimizer acceptance using the existing Hermes command.

Repository:
`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Project:
`/tmp/ic_auto_opt_c19/bridge_test_inv`

Cadence environment:
`/home/zzchen/cadence_ic231_env.csh`

Command:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
.venv/bin/hermes-workflow run-native-turbo /tmp/ic_auto_opt_c19/bridge_test_inv --parallel --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

Required behavior:

- Use native `Turbo1.optimize()` through `run-native-turbo`.
- Do not hand-pick candidate points.
- Preserve native Maestro/ADE exported netlist structure.
- Keep Spectre settings at `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, and `output_format=psfxl`.
- Treat candidate-local non-scalar metrics as candidate failures or penalties, not workflow failures, when other candidates can produce valid scalar metrics.

Forbidden:

- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not change approved metric formulas.
- Do not flatten native netlist sidecars.
- Do not commit raw Cadence artifacts.

Return:

- `reports/native_turbo_summary.json`
- `reports/native_turbo_trace.jsonl`
- `state/optimizer_state.json`
- `data/real_results_ledger.jsonl`
- brief stdout/stderr summary
- any blocking failure reason
```

Expected:

- the packet exists only under `/tmp`;
- no repo raw artifacts are created.

- [x] **Step 3: Prepare a clean local project**

Run:

```bash
rm -rf "$C19_PROJECT"
mkdir -p "$C19_EVIDENCE"
test -d "$C19_SOURCE_PROJECT"
cp -a "$C19_SOURCE_PROJECT" "$C19_PROJECT"
rm -rf "$C19_PROJECT/runs" "$C19_PROJECT/reports" "$C19_PROJECT/state" "$C19_PROJECT/data"
```

Expected:

- `$C19_PROJECT/netlists/exported/input.scs` exists;
- `$C19_PROJECT/netlists/exported/ade_e.scs` exists when present in the source;
- `$C19_PROJECT/netlists/exported/amap/` remains when present in the source;
- prior C-18 run outputs are not copied.

- [x] **Step 4: Record Task 1 state and stop**

Update:

- plan checkbox for Task 1;
- `docs/CURRENT_TASK_STATE.json`;
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`;
- `docs/EXECUTION_PROGRESS_2026-05-29.md`;
- `docs/COMPACT_RESUME_CHECKPOINT.md`.

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- checks pass;
- only plan/progress files are modified;
- no real tools have run.

Commit:

```bash
git add docs/superpowers/plans/2026-06-04-execution-agent-optimizer-practice-acceptance.md docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "docs: prepare c19 execution handoff"
```

## Task 2: Real Execution-Agent Optimizer Run

**Risk:** High because this runs real Spectre/OCEAN, but it should not change repository code.

**Status:** Complete with blocker evidence, verified-only. The command exited before real Spectre/OCEAN execution with `optimizer state is missing`.

**Files:**

- Local-only: `/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/`
- Modify after run: `docs/superpowers/plans/2026-06-04-execution-agent-optimizer-practice-acceptance.md`
- Modify after run: `docs/CURRENT_TASK_STATE.json`
- Modify after run: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: User confirms real-tool execution**

Do not continue until the user confirms Task 2.

- [x] **Step 2: Run the existing optimizer command exactly once**

Run:

```bash
cd "$REPO"
"$HERMES" run-native-turbo "$C19_PROJECT" --parallel --max-evals 100 --cadence-cshrc "$C19_CADENCE_CSHRC" \
  > "$C19_EVIDENCE/run_native_turbo_stdout.txt" \
  2> "$C19_EVIDENCE/run_native_turbo_stderr.txt"
```

Expected:

- command exits 0, or exits non-zero with enough evidence to classify the blocker;
- no hand-picked candidate list is used;
- generated reports stay inside `$C19_PROJECT`.

Actual:

- command exited non-zero before launching real tools;
- stdout: `optimizer state is missing`;
- stderr was empty;
- no `native_turbo_summary.json`, `native_turbo_trace.jsonl`, `optimizer_state.json`, or `real_results_ledger.jsonl` was produced.

- [x] **Step 3: Capture local-only returned artifact hashes**

Run:

```bash
find "$C19_PROJECT" -maxdepth 3 \( -name 'native_turbo_summary.json' -o -name 'native_turbo_trace.jsonl' -o -name 'optimizer_state.json' -o -name 'real_results_ledger.jsonl' \) -type f -print \
  | sort \
  | xargs -r sha256sum \
  > "$C19_EVIDENCE/returned_artifact_hashes.sha256"
```

Expected:

- summary, trace, state, and ledger files are present if the run completed;
- hashes are local-only.

- [x] **Step 4: Record Task 2 state and stop**

Update only the active plan, current state, and next log. Do not write a sanitized final acceptance note until Task 3 audits the returned files.

## Task 3: Supervisor/Hermes Acceptance Audit

**Risk:** Medium. This task reads generated reports and writes one sanitized acceptance note.

**Status:** Complete, verified-only. Acceptance is blocked before real tools because the C-19 clean project kept stale C-18 `ledger/experiment_ledger.jsonl` while deleting `state/optimizer_state.json`.

**Files:**

- Create: `docs/debug/2026-06-04-c19-execution-agent-optimizer-acceptance.md`
- Modify: `docs/superpowers/plans/2026-06-04-execution-agent-optimizer-practice-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: Audit optimizer report shape and settings**

Run:

```bash
cd "$REPO"
python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

project = Path("/tmp/ic_auto_opt_c19/bridge_test_inv")
summary = json.loads((project / "reports/native_turbo_summary.json").read_text())
state = json.loads((project / "state/optimizer_state.json").read_text())
trace_path = project / "reports/native_turbo_trace.jsonl"
traces = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]

assert summary["evaluation_count"] == 100
assert len(traces) == 100
assert state["current_evaluations"] >= 1
assert summary["batch_summary"]["max_batch_worker_count"] <= 10

bad = [
    trace
    for trace in traces
    if trace.get("threads_per_run") != 10
    or trace.get("parallel_jobs") != 10
]
assert not bad, bad[:3]

print("evaluation_count", summary["evaluation_count"])
print("status_counts", summary["status_counts"])
print("batch_summary", summary["batch_summary"])
print("best", summary.get("best_candidate"))
PY
```

Expected:

- exactly 100 trace rows;
- no `threads_per_run` or `parallel_jobs` drift;
- best candidate is reported when at least one feasible candidate exists.

Actual:

- audit could not read `reports/native_turbo_summary.json` because Task 2 exited before report generation;
- `ledger/experiment_ledger.jsonl` still contained old C-18 rows;
- `state/optimizer_state.json` was missing;
- this inconsistent clean-copy state is the blocker.

- [x] **Step 2: Write sanitized acceptance note**

Create `docs/debug/2026-06-04-c19-execution-agent-optimizer-acceptance.md` with:

- command shape, not full raw logs;
- status counts;
- batch count and max worker count;
- Spectre settings audit;
- best candidate parameters and metrics if present;
- whether execution-agent handoff was accepted or blocked;
- blocking bug list if any.

- [x] **Step 3: Run repo verification**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence and diff checks pass;
- no raw Cadence artifacts are staged.

## Task 4: Surgical Fix Or Closeout

**Risk:** Depends on real evidence.

Only perform one of these branches.

### Branch A: Acceptance Passed

- [ ] Mark C-19 complete, verified-only.
- [ ] Commit the plan/progress/sanitized note.
- [ ] Recommend the next product step based on the accepted handoff path.

### Branch B: Acceptance Blocked By A Real Bug

- [ ] Write one concise blocker note under `docs/debug/`.
- [ ] Fix only the blocking code path proven by Task 2/3 evidence.
- [ ] Add the smallest targeted regression test.
- [ ] Re-run the failed C-19 command once.
- [ ] Commit the fix and sanitized evidence.

Forbidden in Branch B:

- no broad redesign;
- no new optimizer framework;
- no new debug framework;
- no metric formula changes unless the user explicitly approves a formula correction.
