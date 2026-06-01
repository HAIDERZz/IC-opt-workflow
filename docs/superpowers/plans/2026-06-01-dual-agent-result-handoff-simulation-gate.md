# Dual-Agent Result Handoff Simulation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and document a one-time C-5.5 dual-agent simulation gate that validates the C-4/C-5 result handoff workflow before real tool adapters.

**Architecture:** Prepare a sanitized temporary Hermes project through the existing CLI, produce a C-4 first real-run package, and run five scenario-specific rehearsals. Each scenario uses a simulated execution-agent role to write returned handoff files and a simulated Hermes-observer role to judge only `hermes-workflow check-real-run` plus `reports/real_run_check_report.json`; the durable output is a docs simulation report, not product code.

**Tech Stack:** Python 3.11+, existing `hermes-workflow` CLI, pytest, ruff, Codex multi-agent roles, Markdown docs.

---

## Execution Model

Use `superpowers:subagent-driven-development` to preserve the role split. C-5.5 is not a product-code feature; it is a workflow behavior gate.

Use this sequence:

1. Controller prepares a sanitized temporary project under `/tmp`.
2. Controller copies the prepared project into one directory per scenario.
3. For each scenario, dispatch a fresh execution-agent role.
4. For each scenario, dispatch a fresh Hermes-observer role.
5. Controller writes the final simulation report from actual observed results.
6. Controller updates checkpoint/progress docs.
7. Controller runs local verification and one combined docs/spec review.

Do not copy or commit real decks, logs, PSF data, or proprietary simulator output from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example
```

Do not add long-lived product code unless the simulation reveals a C-5 bug. If a C-5 bug is found, stop this plan and open a focused C-5 fix plan before continuing.

## File Map

- Read: `docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`
- Read: `docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md`
- Read: `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`
- Create: `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: this plan file as tasks are completed.

Temporary files:

- Create under `/tmp/c5_5_dual_agent_result_handoff.*`
- Do not commit temporary project directories.
- Do not delete unrelated `/tmp` directories.

## Scenario Matrix

| Scenario | Execution-agent behavior | Expected observer result |
| --- | --- | --- |
| `happy_path` | Valid `status: "succeeded"` handoff | `check-real-run` exits 0, report `pass` |
| `valid_failure` | Valid `status: "failed"` handoff | `check-real-run` exits 0, report `pass` |
| `unsafe_path` | Manifest declares absolute or traversal artifact path | `check-real-run` exits 1, report `fail` |
| `mutated_deck` | Valid handoff plus modified `input.scs` | `check-real-run` exits 1, report `fail` |
| `identity_mismatch` | Manifest has wrong `candidate_id` or `run_id` | `check-real-run` exits 1, report `fail` |

## Shared Role Prompt Fragments

Use this execution-agent contract in every execution-agent prompt:

```text
You are the simulated execution-agent role for C-5.5.

Project directory: use the absolute scenario project directory printed by the controller.
Scenario: use the scenario name named by the controller.

Allowed:
- Read runs/real/real_001/input.scs
- Read runs/real/real_001/candidate.json
- Read runs/real/real_001/real_run_manifest.json
- Write sanitized fake runs/real/real_001/spectre.log
- Write sanitized fake files under runs/real/real_001/artifacts/
- Write runs/real/real_001/result_manifest.json
- Intentionally violate the returned file contract only when the scenario instructs it

Forbidden:
- Do not run Spectre, Virtuoso, shell simulator commands, or license tools
- Do not modify config/*.yaml
- Do not modify execution_package/
- Do not modify runs/real/real_001/real_run_manifest.json
- Do not modify runs/real/real_001/candidate.json
- Do not modify runs/real/real_001/input.scs except in the mutated_deck scenario
- Do not write ledger/ or state/ optimizer files
- Do not claim success without writing files

After writing files, return:
STATUS: DONE / BLOCKED
FILES_WRITTEN: project-relative file paths
SCENARIO_NOTES: one short paragraph
```

Use this Hermes-observer contract in every Hermes-observer prompt:

```text
You are the simulated Hermes-observer role for C-5.5.

Project directory: use the absolute scenario project directory printed by the controller.
Scenario: use the scenario name named by the controller.
Expected outcome: use the expected outcome text named by the controller.

Allowed:
- Run hermes-workflow check-real-run PROJECT_DIR
- Read reports/real_run_check_report.json
- Report the check-real-run exit code, report status, result_status, and issues

Forbidden:
- Do not trust execution-agent prose
- Do not repair the returned handoff
- Do not modify result files before checking
- Do not run Spectre, Virtuoso, metric extraction, or optimizer code
- Do not append ledger rows or write optimizer state

Return:
STATUS: DONE / BLOCKED
CHECK_EXIT_CODE: integer
REPORT_STATUS: pass / fail / missing
RESULT_STATUS: succeeded / failed / null / missing
ISSUES: exact issue strings from real_run_check_report.json
MATCHED_EXPECTATION: yes / no
OBSERVER_NOTES: one short paragraph
```

## Task 1: Prepare Sanitized Simulation Workspace

**Files:**
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/base_project`
- Temporary: `/tmp/c5_5_sim_root.txt`

- [x] **Step 1: Verify the repository is clean**

Run:

```bash
git status --short
```

Expected:

```text
no output
```

- [x] **Step 2: Create a temporary simulation root**

Run:

```bash
SIM_ROOT="$(mktemp -d /tmp/c5_5_dual_agent_result_handoff.XXXXXX)"
printf '%s\n' "$SIM_ROOT" > /tmp/c5_5_sim_root.txt
printf '%s\n' "$SIM_ROOT"
```

Expected:

```text
/tmp/c5_5_dual_agent_result_handoff.<random-suffix>
```

- [x] **Step 3: Create the base Hermes project**

Run:

```bash
hermes-workflow init "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
/tmp/c5_5_dual_agent_result_handoff.<random-suffix>/base_project
```

- [x] **Step 4: Write a sanitized exported Spectre deck**

Run:

```bash
mkdir -p "$(cat /tmp/c5_5_sim_root.txt)/base_project/netlists/exported"
tee "$(cat /tmp/c5_5_sim_root.txt)/base_project/netlists/exported/input.scs" >/dev/null <<'EOF'
simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
EOF
```

Expected:

```text
no output
```

- [x] **Step 5: Run the normal pre-approval and C-4 route**

Run these commands:

```bash
hermes-workflow validate "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
validation passed
```

```bash
hermes-workflow package "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
execution_package/execution_manifest.json
```

```bash
hermes-workflow prepare-netlist "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
netlist preparation passed
```

```bash
hermes-workflow dry-run "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
dry run passed
```

```bash
hermes-workflow preflight-health "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
preflight health passed
```

```bash
hermes-workflow approve "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
approve_first_real_run
```

```bash
hermes-workflow prepare-real-run "$(cat /tmp/c5_5_sim_root.txt)/base_project"
```

Expected:

```text
real run package prepared
run: runs/real/real_001
manifest: runs/real/real_001/real_run_manifest.json
```

- [x] **Step 6: Confirm no result handoff exists yet**

Run:

```bash
test ! -e "$(cat /tmp/c5_5_sim_root.txt)/base_project/runs/real/real_001/result_manifest.json"
```

Expected:

```text
no output
```

- [x] **Step 7: Create scenario project copies**

Run:

```bash
for scenario in happy_path valid_failure unsafe_path mutated_deck identity_mismatch; do
  cp -a "$(cat /tmp/c5_5_sim_root.txt)/base_project" "$(cat /tmp/c5_5_sim_root.txt)/$scenario"
done
```

Expected:

```text
no output
```

- [x] **Step 8: No commit for Task 1**

Task 1 creates temporary simulation state only. Do not commit.

## Task 2: Run Passing Handoff Scenarios

**Files:**
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/happy_path`
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/valid_failure`

- [x] **Step 1: Dispatch execution-agent for `happy_path`**

Spawn a fresh execution-agent role with the shared execution-agent contract and this scenario instruction:

```text
Scenario-specific instruction:

Write a valid returned handoff for a successful simulated run.

Required files:
- runs/real/real_001/spectre.log
- runs/real/real_001/artifacts/psf_summary.txt
- runs/real/real_001/result_manifest.json

The result manifest must:
- use schema_version "1.0"
- use run_id "real_001"
- use candidate_id from runs/real/real_001/real_run_manifest.json
- use status "succeeded"
- use UTC timestamps with Z suffix and no microseconds
- use simulator engine "spectre_x", preset "ax", command_label "external_spectre_run"
- use prepared_input_scs from real_run_manifest.json rendered_input_scs
- use prepared_input_sha256 from real_run_manifest.json rendered_input_sha256
- declare log_file "runs/real/real_001/spectre.log"
- declare artifact_files ["runs/real/real_001/artifacts/psf_summary.txt"]
```

Expected execution-agent result:

```text
STATUS: DONE
FILES_WRITTEN includes result_manifest.json, spectre.log, artifacts/psf_summary.txt
```

- [x] **Step 2: Dispatch Hermes-observer for `happy_path`**

Spawn a fresh Hermes-observer role with:

```text
Project directory: /tmp/.../happy_path
Scenario: happy_path
Expected outcome: check-real-run exits 0 and report status is pass
```

Expected observer result:

```text
CHECK_EXIT_CODE: 0
REPORT_STATUS: pass
RESULT_STATUS: succeeded
ISSUES: []
MATCHED_EXPECTATION: yes
```

- [x] **Step 3: Dispatch execution-agent for `valid_failure`**

Spawn a fresh execution-agent role with the shared execution-agent contract and this scenario instruction:

```text
Scenario-specific instruction:

Write a valid returned handoff for a simulated run that failed in the simulator.

Required files:
- runs/real/real_001/spectre.log
- runs/real/real_001/artifacts/psf_summary.txt
- runs/real/real_001/result_manifest.json

The result manifest must be structurally valid and must set status "failed".
The log may say "sanitized simulated Spectre failure".
All path, candidate, run, and prepared-input hash fields must match the prepared real_run_manifest.json.
```

Expected execution-agent result:

```text
STATUS: DONE
FILES_WRITTEN includes result_manifest.json, spectre.log, artifacts/psf_summary.txt
```

- [x] **Step 4: Dispatch Hermes-observer for `valid_failure`**

Spawn a fresh Hermes-observer role with:

```text
Project directory: /tmp/.../valid_failure
Scenario: valid_failure
Expected outcome: check-real-run exits 0 and report status is pass with result_status failed
```

Expected observer result:

```text
CHECK_EXIT_CODE: 0
REPORT_STATUS: pass
RESULT_STATUS: failed
ISSUES: []
MATCHED_EXPECTATION: yes
```

- [x] **Step 5: Controller records passing scenario observations**

Record these actual values in a controller note for the final report:

```text
Scenario: happy_path
Execution-agent status:
Files written:
Observer exit code:
Observer report status:
Observer result_status:
Observer issues:
Matched expectation:

Scenario: valid_failure
Execution-agent status:
Files written:
Observer exit code:
Observer report status:
Observer result_status:
Observer issues:
Matched expectation:
```

Do not commit this temporary note. The final report in Task 4 will contain the actual values.

## Task 3: Run Rejection Scenarios

**Files:**
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/unsafe_path`
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/mutated_deck`
- Temporary: `/tmp/c5_5_dual_agent_result_handoff.*/identity_mismatch`

- [x] **Step 1: Dispatch execution-agent for `unsafe_path`**

Spawn a fresh execution-agent role with the shared execution-agent contract and this scenario instruction:

```text
Scenario-specific instruction:

Write a returned handoff that intentionally declares an unsafe artifact path.

Required files:
- runs/real/real_001/spectre.log
- runs/real/real_001/artifacts/psf_summary.txt
- runs/real/real_001/result_manifest.json

The result manifest should otherwise be valid, but set:
- log_file to "/tmp/c5_5_outside_spectre.log"

Do not create /tmp/c5_5_outside_spectre.log.
All other candidate, run, and prepared-input hash fields should match real_run_manifest.json.
```

Expected execution-agent result:

```text
STATUS: DONE
FILES_WRITTEN includes result_manifest.json and in-project sanitized artifacts
```

- [x] **Step 2: Dispatch Hermes-observer for `unsafe_path`**

Spawn a fresh Hermes-observer role with:

```text
Project directory: /tmp/.../unsafe_path
Scenario: unsafe_path
Expected outcome: check-real-run exits 1 and report status is fail with unsafe path issue
```

Expected observer result:

```text
CHECK_EXIT_CODE: 1
REPORT_STATUS: fail
ISSUES includes result artifact path is unsafe: /tmp/c5_5_outside_spectre.log
MATCHED_EXPECTATION: yes
```

- [x] **Step 3: Dispatch execution-agent for `mutated_deck`**

Spawn a fresh execution-agent role with the shared execution-agent contract and this scenario instruction:

```text
Scenario-specific instruction:

Write an otherwise valid returned handoff, then intentionally mutate the prepared deck.

Required files:
- runs/real/real_001/spectre.log
- runs/real/real_001/artifacts/psf_summary.txt
- runs/real/real_001/result_manifest.json

The result manifest should use the original prepared_input_sha256 from real_run_manifest.json.
After writing result_manifest.json, append this exact line to runs/real/real_001/input.scs:

// c5.5 simulated post-prepare mutation
```

Expected execution-agent result:

```text
STATUS: DONE
FILES_WRITTEN includes result_manifest.json, spectre.log, artifacts/psf_summary.txt, input.scs mutation
```

- [x] **Step 4: Dispatch Hermes-observer for `mutated_deck`**

Spawn a fresh Hermes-observer role with:

```text
Project directory: /tmp/.../mutated_deck
Scenario: mutated_deck
Expected outcome: check-real-run exits 1 and report status is fail with prepared input hash mismatch
```

Expected observer result:

```text
CHECK_EXIT_CODE: 1
REPORT_STATUS: fail
ISSUES includes prepared input hash mismatch
MATCHED_EXPECTATION: yes
```

- [x] **Step 5: Dispatch execution-agent for `identity_mismatch`**

Spawn a fresh execution-agent role with the shared execution-agent contract and this scenario instruction:

```text
Scenario-specific instruction:

Write a returned handoff with an isolated candidate identity mismatch.

Required files:
- runs/real/real_001/spectre.log
- runs/real/real_001/artifacts/psf_summary.txt
- runs/real/real_001/result_manifest.json

The result manifest should otherwise be valid, but set:
- candidate_id to "wrong_candidate"

Keep run_id as "real_001".
All path and prepared-input hash fields should match real_run_manifest.json.
```

Expected execution-agent result:

```text
STATUS: DONE
FILES_WRITTEN includes result_manifest.json, spectre.log, artifacts/psf_summary.txt
```

- [x] **Step 6: Dispatch Hermes-observer for `identity_mismatch`**

Spawn a fresh Hermes-observer role with:

```text
Project directory: /tmp/.../identity_mismatch
Scenario: identity_mismatch
Expected outcome: check-real-run exits 1 and report status is fail with candidate identity issue
```

Expected observer result:

```text
CHECK_EXIT_CODE: 1
REPORT_STATUS: fail
ISSUES includes result candidate_id does not match prepared candidate
MATCHED_EXPECTATION: yes
```

- [x] **Step 7: Controller records rejection scenario observations**

Record these actual values in a controller note for the final report:

```text
Scenario: unsafe_path
Execution-agent status:
Files written:
Observer exit code:
Observer report status:
Observer issues:
Matched expectation:

Scenario: mutated_deck
Execution-agent status:
Files written:
Observer exit code:
Observer report status:
Observer issues:
Matched expectation:

Scenario: identity_mismatch
Execution-agent status:
Files written:
Observer exit code:
Observer report status:
Observer issues:
Matched expectation:
```

Do not commit this temporary note. The final report in Task 4 will contain the actual values.

## Task 4: Write Simulation Report and Progress Docs

**Files:**
- Create: `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`

- [x] **Step 1: Create the simulation report**

Create `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md` with actual observed values from Tasks 1-3. Use this exact heading structure:

```markdown
# C-5.5 Dual-Agent Result Handoff Simulation Report

## Summary

## Repository

## Scope

## Temporary Workspace

## Preparation Commands

## Role Prompt Summary

## Scenario Results

| Scenario | Expected | Observed Exit | Report Status | Issues | Assessment |
| --- | --- | --- | --- | --- | --- |

## Scenario Notes

### happy_path

### valid_failure

### unsafe_path

### mutated_deck

### identity_mismatch

## Behavior Findings

## C-5 Bugs Discovered

## Deferred Minor Improvements

## Next Recommended Scope
```

Report requirements:

- Use the actual temporary workspace path from `/tmp/c5_5_sim_root.txt`.
- Include the actual `check-real-run` exit code for every scenario.
- Include the actual `status`, `result_status`, and `issues` from each `real_run_check_report.json`.
- State whether the Hermes-observer role used only the CLI and report.
- State that no real Spectre, Virtuoso, Claude CLI, Hermes service, metric extraction, ledger append, or optimizer state write occurred.
- If all scenarios matched expectations, write `C-5.5 simulation gate: passed` in the Summary.
- If any scenario did not match expectations, write `C-5.5 simulation gate: failed` in the Summary and record the blocking issue.

- [x] **Step 2: Update next development log**

Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`:

- Change current scope to `Plan C-5.5, dual-agent result handoff simulation gate`.
- Change current status to either `C-5.5 complete` or `C-5.5 blocked` based on Task 4 Step 1.
- Link `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`.
- If passed, set next required action to `confirm C-6 real metric result contract scope`.
- If blocked, set next required action to the focused C-5 fix or prompt hardening named in the report.

- [x] **Step 3: Update compact checkpoint**

Modify `docs/COMPACT_RESUME_CHECKPOINT.md`:

- Add the C-5.5 design spec path.
- Add this implementation plan path.
- Add the simulation report path after the report exists.
- Record whether C-5.5 passed or blocked.
- Preserve the warning not to commit real `input.scs` examples.

- [x] **Step 4: Update execution progress**

Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`:

- Add a `Plan C-5.5: Dual-Agent Result Handoff Simulation Gate` section after the C-5 section.
- Record the five scenarios and pass/fail outcomes.
- Link the simulation report.
- Record the next recommended scope.

- [x] **Step 5: Mark Task 4 progress in this plan**

Change completed Task 4 checkboxes in this plan from unchecked to checked after the report and progress docs are updated.

- [x] **Step 6: Verify docs diff**

Run:

```bash
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/COMPACT_RESUME_CHECKPOINT.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md
git commit -m "docs: record dual agent result handoff simulation"
```

## Task 5: Final Verification and Review

**Files:**
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`

- [ ] **Step 1: Run full local verification**

Run:

```bash
pytest -q
```

Expected:

```text
211 passed
```

If the test count changes because other committed tests exist, verify that the output has zero failures and record the actual count in the final response.

Run:

```bash
ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 2: Run one combined docs/spec review**

Run:

```bash
claude -p "Review Plan C C-5.5 dual-agent result handoff simulation against docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md, docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md, and docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md. Focus on whether the simulation actually validates the role split, whether the report is complete, whether scope stayed clear of real Spectre/Virtuoso/metric/optimizer work, and whether progress docs point to the correct next step. Return Critical, Important, and Minor findings."
```

Expected:

```text
No Critical findings.
No Important findings.
```

Fix Critical and Important findings before closing C-5.5. Record Minor findings as deferred if they do not block the simulation gate.

- [ ] **Step 3: Update closeout docs**

Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` and `docs/COMPACT_RESUME_CHECKPOINT.md` with:

```text
C-5.5 final verification: pytest -q passed; ruff check . passed; combined docs/spec review passed with no Critical or Important findings.
```

Use the actual pytest count from Step 1.

- [ ] **Step 4: Mark Task 5 progress in this plan**

Change completed Task 5 checkboxes in this plan from unchecked to checked.

- [ ] **Step 5: Commit closeout docs**

Run:

```bash
git add docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md
git commit -m "docs: close dual agent result handoff simulation"
```

## Self-Review Checklist

- Spec coverage:
  - Temporary sanitized project preparation is Task 1.
  - Happy-path and valid simulator failure scenarios are Task 2.
  - Unsafe path, mutated deck, and identity mismatch scenarios are Task 3.
  - Simulation report and progress docs are Task 4.
  - Final verification and review are Task 5.
- Scope control:
  - No task runs real Spectre, real Virtuoso, real Claude CLI as execution agent, real Hermes service, metric extraction, ledger append, or optimizer state update.
  - No task commits real `input.scs`, Spectre logs, PSF data, or proprietary outputs.
  - No long-lived product code is added unless a C-5 bug is discovered and a separate fix plan is opened.
- Type and path consistency:
  - Design spec path: `docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`.
  - Plan path: `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`.
  - Simulation report path: `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`.
  - Temporary workspace path prefix: `/tmp/c5_5_dual_agent_result_handoff.*`.
