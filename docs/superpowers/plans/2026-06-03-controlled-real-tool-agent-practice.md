# Controlled Real-Tool/Agent Practice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute C-12 as one controlled real-tool/agent practice that proves an approved Hermes real-run package can pass through the C-7 Spectre + OCEAN adapter and return through Hermes check/record contracts.

**Architecture:** Keep Hermes workflow tooling responsible for prepare/check/record and keep real Spectre/OCEAN execution at the execution-agent/C-7 adapter boundary. Use one known cell, one local practice project, one run id, and local-only evidence by default. Stop after each task for user review; do not widen into optimization loops or PSS/PAC practice.

**Tech Stack:** Python 3.11+, existing `hermes-workflow` CLI, `tools/run_spectre_ocean_adapter.py`, Cadence Spectre/OCEAN environment loaded by the execution shell, pytest/ruff/cadence checker for repo-side verification, local-only evidence under `/tmp` or untracked `docs/toolchain_evidence/`.

---

## Required Reading

- `AGENTS.md`
- `docs/CURRENT_TASK_STATE.json`
- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`
- `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`
- `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`
- `docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md`
- `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- `README.md`
- `src/hermes_workflow/cli.py`
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `tools/run_spectre_ocean_adapter.py`

Before implementation, run codegraph for the current task. If codegraph is unavailable or stale, state the reason and use `rg` plus focused file reads.

## Execution Model

Use Subagent-Driven Development. Stop after every task with:

- work completed
- files changed
- commands run
- review/evidence status
- commit hash or explicit no-commit reason
- route audit against the C-12 spec and top-level plan

Risk-tiered gates:

- Task 1 is low/medium risk. It prepares local paths and confirms input gates. Do not run real tools.
- Task 2 is medium risk. It runs Hermes workflow tooling only and prepares one approved package. Do not run Spectre/OCEAN.
- Task 3 is high risk. It runs the real C-7 adapter through the execution-agent boundary. Require explicit user confirmation immediately before this task.
- Task 4 is high risk. It validates and records real returned artifacts. Run spec-compliance and code-quality/evidence review after the task.
- Task 5 is low/medium risk docs/final gate. It records sanitized conclusions and keeps proprietary evidence uncommitted unless the user explicitly approves exact files.

Do not start the next task until the user confirms.

## File And Artifact Map

Committed files that may be modified:

- `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`

Runtime local-only paths:

```text
/tmp/ic_auto_opt_c12/bridge_test_inv
/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice
```

Optional local-only evidence path:

```text
docs/toolchain_evidence/2026-06-03-c12-controlled-real-tool-agent-practice/
```

Do not stage or commit:

```text
docs/OCEAN_DOC_*
docs/toolchain_evidence/
/tmp/ic_auto_opt_c12/
raw input.scs
PSF/raw directories
Spectre logs
OCEAN logs
screenshots
license-sensitive or path-sensitive tool output
```

## Shared Shell Variables

When executing C-12 tasks, define these variables in the shell running the task:

```bash
export REPO=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
export C12_ROOT=/tmp/ic_auto_opt_c12
export C12_PROJECT=/tmp/ic_auto_opt_c12/bridge_test_inv
export C12_EVIDENCE=/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice
export C12_CADENCE_CSHRC=/home/zzchen/cadence_ic231_env.csh
export HERMES=hermes-workflow
```

If `hermes-workflow` is not on `PATH`, stop and install or activate the local project environment before continuing. Do not substitute hand-written Python snippets for Hermes CLI commands.

## Task 1: Practice Workspace And Input Gate

**Files:**

- Modify: `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

This task prepares the local practice workspace and confirms the fixed cell/deck/formula gates. It does not run real Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, Claude CLI, or the C-7 adapter.

- [x] **Step 1: Confirm route and repo state**

Run:

```bash
cd "$REPO"
git status --short
python3 tools/check_development_cadence.py
```

Expected:

- cadence checker passes
- `git status --short` shows no unexpected tracked changes
- local OCEAN research/evidence files may remain untracked

- [x] **Step 2: Create local practice directories**

Run:

```bash
mkdir -p "$C12_ROOT" "$C12_EVIDENCE"
printf '%s\n' \
  "repo=$REPO" \
  "project=$C12_PROJECT" \
  "evidence=$C12_EVIDENCE" \
  "cadence_cshrc=$C12_CADENCE_CSHRC" \
  > "$C12_EVIDENCE/session_paths.txt"
```

Expected:

- `/tmp/ic_auto_opt_c12` exists
- `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/session_paths.txt` exists

- [x] **Step 3: Confirm Hermes CLI availability**

Run:

```bash
command -v "$HERMES"
"$HERMES" --version
```

Expected:

- `command -v` prints an executable path
- `hermes-workflow --version` exits 0

If either command fails, stop and report an environment setup blocker. Do not replace Hermes CLI with ad-hoc Python.

- [x] **Step 4: Initialize the local C-12 project**

Run:

```bash
rm -rf "$C12_PROJECT"
"$HERMES" init "$C12_PROJECT"
```

Expected:

- `"$C12_PROJECT/config/project_config.yaml"` exists
- `"$C12_PROJECT/netlists/exported"` exists

This `rm -rf` targets only `/tmp/ic_auto_opt_c12/bridge_test_inv`. Do not run destructive cleanup on repository paths.

- [x] **Step 5: Confirm the fixed cell contract**

Run:

```bash
rg -n "Virtuoso_Bridge_test|bridge_test_inv|tran_dc_test" "$C12_PROJECT/config/project_config.yaml"
```

Expected output includes:

```text
Virtuoso_Bridge_test
bridge_test_inv
tran_dc_test
```

- [x] **Step 6: Confirm approved formula contract text**

Run:

```bash
rg -n "riseTime|fallTime|VDC|IDC|expression_source: user_approved" "$C12_PROJECT/config/metrics.yaml"
```

Expected:

- `riseTime(...)` appears
- `fallTime(...)` appears
- `VDC("/VDD") * IDC("/M0/S")` appears
- each metric has `expression_source: user_approved`

If the formulas are not acceptable for the real exported deck, stop and ask the user for the approved C-12 `metrics.yaml` before continuing. Do not discover or rewrite formulas during C-12 execution.

- [ ] **Step 7: Confirm exported input deck is present**

Run:

```bash
test -f "$C12_PROJECT/netlists/exported/input.scs"
```

Expected: command exits 0.

If this fails, stop and ask the user or execution agent to place the real exported `input.scs` at:

```text
/tmp/ic_auto_opt_c12/bridge_test_inv/netlists/exported/input.scs
```

Do not copy local `input.scs` examples into the repository and do not commit the deck.

Task 1 stopped here on 2026-06-03: the file was missing after `hermes-workflow init`, so Step 8 and later steps must wait until the real exported deck is placed at the path above.

- [ ] **Step 8: Capture local-only input hash**

Run:

```bash
sha256sum "$C12_PROJECT/netlists/exported/input.scs" > "$C12_EVIDENCE/exported_input_scs.sha256"
```

Expected:

- `$C12_EVIDENCE/exported_input_scs.sha256` exists
- only the hash file is created under `/tmp`; it is not staged

- [ ] **Step 9: Update progress docs for Task 1**

Record:

```text
C-12 Task 1 checkpoint: local practice workspace created under /tmp, fixed cell contract and approved formula gate checked, exported input.scs presence/hash captured locally. No real tools, C-7 adapter, SSH, bridge, PSF parsing, or formula rewriting were used.
```

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- this plan's Task 1 checkboxes

Set `review_status` to `verified-only` until review evidence is recorded.

- [ ] **Step 10: Verify and commit Task 1 docs**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence checker passes
- diff check is clean
- only intentional docs/status files are staged for commit
- local evidence remains unstaged

Commit:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md
git commit -m "docs: record c12 practice input gate"
```

Stop and report Task 1 status to the user.

## Task 2: Hermes Preflight And Approved Real-Run Package

**Files:**

- Modify: `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

This task runs Hermes workflow tooling only. It prepares the approved package but does not run Spectre, OCEAN, SSH, bridge, Claude CLI, or the C-7 adapter.

- [ ] **Step 1: Validate the project contract**

Run:

```bash
cd "$REPO"
"$HERMES" validate "$C12_PROJECT" | tee "$C12_EVIDENCE/01_validate.txt"
```

Expected:

- command exits 0
- output reports a valid project

- [ ] **Step 2: Build the execution package**

Run:

```bash
"$HERMES" package "$C12_PROJECT" | tee "$C12_EVIDENCE/02_package.txt"
```

Expected:

- command exits 0
- output includes `execution_package/execution_manifest.json`

- [ ] **Step 3: Prepare the netlist template**

Run:

```bash
"$HERMES" prepare-netlist "$C12_PROJECT" | tee "$C12_EVIDENCE/03_prepare_netlist.txt"
```

Expected:

- command exits 0
- output includes `netlist preparation passed`
- `"$C12_PROJECT/reports/netlist_preparation_report.json"` exists
- `"$C12_PROJECT/netlists/templates/template.scs"` exists

- [ ] **Step 4: Run deterministic dry-run**

Run:

```bash
"$HERMES" dry-run "$C12_PROJECT" | tee "$C12_EVIDENCE/04_dry_run.txt"
```

Expected:

- command exits 0
- output includes `dry run passed`
- `"$C12_PROJECT/reports/dry_run_report.json"` exists

- [ ] **Step 5: Run preflight health**

Run:

```bash
"$HERMES" preflight-health "$C12_PROJECT" | tee "$C12_EVIDENCE/05_preflight_health.txt"
```

Expected:

- command exits 0
- output includes `preflight health passed`
- `"$C12_PROJECT/state/health_check.json"` exists

- [ ] **Step 6: Approve the first real run**

Run:

```bash
"$HERMES" approve "$C12_PROJECT" | tee "$C12_EVIDENCE/06_approve.txt"
```

Expected:

- command exits 0
- output is `approve_first_real_run`
- `"$C12_PROJECT/reports/supervisor_instruction.json"` exists

- [ ] **Step 7: Prepare `real_001`**

Run:

```bash
"$HERMES" prepare-real-run "$C12_PROJECT" --run-id real_001 | tee "$C12_EVIDENCE/07_prepare_real_run.txt"
```

Expected:

- command exits 0
- output includes `real run package prepared`
- `"$C12_PROJECT/runs/real/real_001/input.scs"` exists
- `"$C12_PROJECT/runs/real/real_001/real_run_manifest.json"` exists
- `"$C12_PROJECT/runs/real/real_001/metric_extraction_request.json"` exists

- [ ] **Step 8: Capture package hashes locally**

Run:

```bash
sha256sum \
  "$C12_PROJECT/runs/real/real_001/input.scs" \
  "$C12_PROJECT/runs/real/real_001/real_run_manifest.json" \
  "$C12_PROJECT/runs/real/real_001/metric_extraction_request.json" \
  > "$C12_EVIDENCE/real_001_pre_execution_hashes.sha256"
```

Expected:

- hash file exists under `$C12_EVIDENCE`
- no raw deck or manifest is committed

- [ ] **Step 9: Update progress docs for Task 2**

Record:

```text
C-12 Task 2 checkpoint: Hermes validate/package/prepare-netlist/dry-run/preflight-health/approve/prepare-real-run completed for real_001. The approved package exists locally under /tmp. No real Spectre/OCEAN execution, C-7 adapter invocation, PSF parsing, or formula rewriting occurred.
```

Update the same node files as Task 1 and mark Task 2 checkboxes in this plan.

- [ ] **Step 10: Verify and commit Task 2 docs**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence checker passes
- diff check is clean
- local evidence remains unstaged

Commit:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md
git commit -m "docs: record c12 approved real run package"
```

Stop and report Task 2 status to the user.

## Task 3: Execution-Agent C-7 Adapter Invocation

**Files:**

- Modify: `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

This is the first C-12 task that may run real Spectre and OCEAN. It must not start until the user explicitly confirms that real-tool execution is allowed for C-12 Task 3.

- [ ] **Step 1: Request and record user go-ahead**

Before running any real-tool command, ask the user:

```text
确认是否允许执行 C-12 Task 3：通过 execution-agent/C-7 adapter 边界运行真实 Spectre + OCEAN，用于 real_001 单点 practice？
```

Expected: user explicitly confirms.

If the user does not confirm, stop with `blocked-no-subagent` or `verified-only` status as appropriate. Do not run Task 3.

- [ ] **Step 2: Confirm Cadence setup file exists**

Run:

```bash
test -f "$C12_CADENCE_CSHRC"
```

Expected: command exits 0.

If it fails, stop and report an environment setup blocker.

- [ ] **Step 3: Confirm Spectre and OCEAN are visible in the execution shell**

Run:

```bash
csh -lc "source $C12_CADENCE_CSHRC; which spectre; which ocean"
```

Expected:

- command exits 0
- output includes paths for `spectre` and `ocean`

This checks tool visibility only. It does not run simulations.

- [ ] **Step 4: Record execution-agent boundary**

Write this line to `$C12_EVIDENCE/08_execution_boundary.txt`:

```bash
printf '%s\n' \
  "phase=execution-agent" \
  "command=tools/run_spectre_ocean_adapter.py" \
  "run_id=real_001" \
  "project=$C12_PROJECT" \
  "cadence_cshrc=$C12_CADENCE_CSHRC" \
  > "$C12_EVIDENCE/08_execution_boundary.txt"
```

Expected: boundary evidence file exists locally.

- [ ] **Step 5: Run the C-7 adapter through the execution shell**

Run:

```bash
csh -lc "source $C12_CADENCE_CSHRC; cd $REPO; python tools/run_spectre_ocean_adapter.py $C12_PROJECT --run-id real_001" \
  | tee "$C12_EVIDENCE/09_adapter_run.txt"
```

Expected success path:

- command exits 0
- output includes `succeeded: run_id=real_001`
- `"$C12_PROJECT/runs/real/real_001/result_manifest.json"` exists
- `"$C12_PROJECT/runs/real/real_001/metrics/metric_result_manifest.json"` exists
- `"$C12_PROJECT/runs/real/real_001/psf"` exists
- `"$C12_PROJECT/runs/real/real_001/metrics/ocean_scalars.tsv"` exists

Expected failure path:

- command exits 1 or 2
- result or metric manifest may indicate failure or be absent depending on precondition/tool failure
- stop after Step 6 and proceed to Task 4 failure handling instead of hand-editing returned artifacts

- [ ] **Step 6: Capture returned artifact hashes locally**

Run:

```bash
find "$C12_PROJECT/runs/real/real_001" \
  -maxdepth 3 \
  -type f \
  \( -name '*.json' -o -name '*.tsv' -o -name '*.stdout' -o -name '*.stderr' -o -name '*.out' -o -name '*.log' \) \
  -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "$C12_EVIDENCE/real_001_returned_artifact_hashes.sha256"
```

Expected:

- hash file exists locally
- raw artifacts remain uncommitted

- [ ] **Step 7: Update progress docs for Task 3**

Record one of these exact status lines:

```text
C-12 Task 3 checkpoint: execution-agent/C-7 adapter invocation succeeded for real_001. Returned artifacts are local-only; Hermes checks are pending.
```

or:

```text
C-12 Task 3 checkpoint: execution-agent/C-7 adapter invocation failed or was blocked for real_001. Returned artifacts/logs were preserved locally; Hermes failure checks and recovery assessment are pending.
```

Also record:

```text
No manual manifest repair, PSF parsing, or formula rewriting occurred.
```

- [ ] **Step 8: Verify and commit Task 3 docs**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence checker passes
- diff check is clean
- local evidence remains unstaged

Commit:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md
git commit -m "docs: record c12 adapter practice"
```

Stop and report Task 3 status to the user.

## Task 4: Hermes Check, Record, Or Recovery Assessment

**Files:**

- Modify: `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

This task returns to Hermes workflow tooling. It does not run Spectre/OCEAN. It must validate original adapter outputs; do not edit manifests to force a pass.

- [ ] **Step 1: Run real-run handoff check**

Run:

```bash
"$HERMES" check-real-run "$C12_PROJECT" --run-id real_001 | tee "$C12_EVIDENCE/10_check_real_run.txt"
```

Expected success path:

- command exits 0
- output includes `real run handoff check passed`
- `"$C12_PROJECT/reports/real_run_check_report.json"` exists

If it exits nonzero, preserve the report and continue to Step 4 recovery assessment.

- [ ] **Step 2: Run metric result check**

Run only if Step 1 passed:

```bash
"$HERMES" check-metric-results "$C12_PROJECT" --run-id real_001 | tee "$C12_EVIDENCE/11_check_metric_results.txt"
```

Expected success path:

- command exits 0
- output includes `metric result check passed`
- `"$C12_PROJECT/reports/metric_result_check_report.json"` exists

If it exits nonzero, preserve the report and continue to Step 4 recovery assessment.

- [ ] **Step 3: Record checked real result**

Run only if Steps 1 and 2 passed:

```bash
"$HERMES" record-real-result "$C12_PROJECT" --run-id real_001 | tee "$C12_EVIDENCE/12_record_real_result.txt"
```

Expected:

- command exits 0
- output includes `real result recorded`
- `"$C12_PROJECT/ledger/experiment_ledger.jsonl"` exists
- `"$C12_PROJECT/state/optimizer_state.json"` exists
- `"$C12_PROJECT/reports/real_result_record_report.json"` exists

- [ ] **Step 4: Assess recovery if any check or record step failed**

Run only if Step 1, 2, or 3 failed:

```bash
"$HERMES" assess-real-run-recovery "$C12_PROJECT" --run-id real_001 | tee "$C12_EVIDENCE/13_assess_recovery.txt"
```

Expected:

- command writes `"$C12_PROJECT/reports/real_run_recovery_report.json"`
- report classifies the unresolved run
- no optimizer ledger/state row is appended for a failed or unchecked result

Do not run `prepare-real-run-retry` inside C-12 unless the user explicitly requests a retry scope after reviewing the evidence.

- [ ] **Step 5: Capture Hermes report hashes locally**

Run:

```bash
find "$C12_PROJECT/reports" "$C12_PROJECT/state" "$C12_PROJECT/ledger" \
  -maxdepth 2 \
  -type f \
  -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "$C12_EVIDENCE/hermes_report_state_hashes.sha256"
```

Expected:

- hash file exists locally
- raw reports remain local unless the user approves a sanitized summary

- [ ] **Step 6: Request review gate**

Request spec-compliance and code-quality/evidence review.

Review prompt must include:

```text
Review C-12 controlled real-tool/agent practice Task 4. Verify that real tool execution happened only through the execution-agent/C-7 adapter boundary, Hermes workflow tooling only performed prepare/check/record/recovery operations, returned artifacts were not manually repaired, Python did not parse PSF or rewrite formulas, and local proprietary evidence remains unstaged.
```

Expected:

- spec-compliance review passes before code-quality/evidence review
- any findings are fixed or recorded as blockers before proceeding

- [ ] **Step 7: Update progress docs for Task 4**

Record one of these exact status lines:

```text
C-12 Task 4 checkpoint: Hermes check-real-run, check-metric-results, and record-real-result passed for real_001. One checked real result was recorded locally.
```

or:

```text
C-12 Task 4 checkpoint: Hermes validation or recording failed for real_001. Recovery assessment was written locally and no unchecked result was recorded.
```

Also record review evidence and route audit.

- [ ] **Step 8: Verify and commit Task 4 docs**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence checker passes
- diff check is clean
- local evidence remains unstaged

Commit:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md
git commit -m "docs: record c12 hermes verification"
```

Stop and report Task 4 status to the user.

## Task 5: Sanitized Evidence Summary And Final Gate

**Files:**

- Modify: `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`

This task records the conclusion. It may create a sanitized summary only if it contains no raw deck, model, PSF, license, log, or sensitive local path details.

- [ ] **Step 1: Draft a local-only evidence summary**

Create a local summary at:

```text
/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/C12_EVIDENCE_SUMMARY.md
```

Required sections:

```text
# C-12 Controlled Real-Tool/Agent Practice Evidence Summary

## Scope

## Git And Environment

## Project And Run

## Hermes Preflight

## Execution-Agent Adapter Result

## Hermes Check/Record Or Recovery Result

## Formula Safety

## Artifact Commit Policy

## Conclusion
```

Do not include raw `input.scs`, PSF contents, full Spectre logs, full OCEAN logs, license strings, host secrets, or unredacted proprietary paths.

- [ ] **Step 2: Decide whether a sanitized committed summary is allowed**

Ask the user:

```text
C-12 evidence summary is available locally under /tmp. Do you approve committing a sanitized summary, and if so, which exact file path should be committed?
```

Expected:

- if user approves, commit only the exact sanitized summary path the user names
- if user does not approve, keep all evidence local-only and record that decision

- [ ] **Step 3: Update final project status**

If the C-12 practice succeeded, record:

```text
C-12 controlled real-tool/agent practice is complete and reviewed. One approved real-run package passed through the execution-agent/C-7 Spectre + OCEAN adapter boundary and returned through Hermes check-real-run, check-metric-results, and record-real-result. The next scope decision is whether to repeat with PSS/PAC/PNoise, test a true dual-agent handoff, or design a small multi-candidate real optimization loop.
```

If the C-12 practice was blocked or failed, record:

```text
C-12 controlled real-tool/agent practice is blocked or failed with preserved local evidence. The next scope should be a focused diagnostic plan for the recorded blocker, not a broader optimizer loop.
```

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- this plan's Task 5 checkboxes

- [ ] **Step 4: Run final local repository checks**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- pytest passes
- ruff passes
- cadence checker passes
- diff check is clean
- `git status --short` shows only intentional docs/status changes and local untracked evidence paths

- [ ] **Step 5: Request final review gate**

Request final spec-compliance and code-quality/evidence review.

Review prompt must include:

```text
Review C-12 controlled real-tool/agent practice final gate. Verify route alignment with docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md and docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md. Confirm no raw proprietary artifacts are staged, no PSF parsing or formula rewriting occurred, and the next recommended scope follows the actual evidence outcome.
```

Expected:

- both reviews pass, or findings are fixed and re-reviewed

- [ ] **Step 6: Commit final C-12 status**

Run:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md
git commit -m "docs: record c12 controlled practice final gate"
```

If the user approved a sanitized summary, include only that exact file in `git add`.

Stop and report final C-12 status to the user.

## Plan Self-Review

Spec coverage:

- One known cell and one run are covered by Tasks 1-3.
- Hermes prepare/check/record boundaries are covered by Tasks 2 and 4.
- Execution-agent/C-7 adapter ownership is isolated in Task 3.
- Failure handling and recovery assessment are covered by Task 4.
- Local-only evidence and commit policy are covered by Tasks 1, 3, 4, and 5.
- Final next-scope decision is covered by Task 5.

Placeholder scan:

- No deferred placeholder markers or incomplete sections are present.

Type and command consistency:

- Hermes commands match `README.md` and `src/hermes_workflow/cli.py`.
- Adapter command matches `tools/run_spectre_ocean_adapter.py`.
- C-7 command construction requires the execution shell to have `spectre` and `ocean` on `PATH`; Task 3 checks this before adapter invocation.

Route alignment:

- C-12 allows real Spectre/OCEAN only after user confirmation and only through the execution-agent/C-7 adapter boundary.
- Hermes workflow tooling still never parses PSF, rewrites formulas, or runs physical tools inside validators.
- The plan does not authorize multi-candidate optimization, PSS/PAC practice, Maestro sweep, or dual-agent autonomy.
