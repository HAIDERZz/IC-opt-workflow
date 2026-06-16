# Real-Tool Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the C-13 single-candidate suggestion path against the real working Spectre + OCEAN chain.

**Architecture:** Use the proven native Maestro/ADE netlist layout and existing Hermes workflow contracts. Prepare one first-run seed package with a known-good lower-bound point, ask `suggest-candidate` for the next candidate request after that seed is recorded, prepare that explicit candidate package, run the C-7 adapter, then check and record through existing Hermes commands.

**Tech Stack:** Python 3, existing `hermes-workflow` CLI, `tools/run_spectre_ocean_adapter.py`, Cadence Spectre/OCEAN from `/home/zzchen/cadence_ic231_env.csh`, local-only `/tmp` evidence, pytest/ruff/cadence checker for repo-side verification.

---

## Scope Guard

This is C-14 real-tool acceptance for the already-reviewed C-13 MVP.

Allowed:

- Create one clean local practice project under `/tmp/ic_auto_opt_c14`.
- Use a local acceptance-only `variables.yaml` lower-bound seed so C-4 `prepare-real-run` creates a known-good `real_001`.
- Run `hermes-workflow suggest-candidate` to write one candidate request.
- Run `hermes-workflow prepare-real-run` to prepare `real_001`.
- Run `hermes-workflow prepare-candidate-real-run` to prepare `real_002` after `suggest-candidate`.
- Run the C-7 Spectre/OCEAN adapter for `real_001` and `real_002`.
- Run `check-real-run`, `check-metric-results`, and `record-real-result`.
- If `real_002` is a candidate-level metric failure, run `assess-real-run-recovery` and record the evidence without rewriting formulas.

Forbidden:

- Do not create a broad optimizer framework.
- Do not add batch orchestration, daemon/service behavior, or new optimizer algorithms.
- Do not change approved metric formulas.
- Do not parse PSF or waveform databases in Python.
- Do not flatten or redesign the Maestro/ADE netlist layout.
- Do not commit raw `input.scs`, protected include sidecars, PSF/raw data, full Cadence logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.
- Do not continue from a failed real-tool step by editing returned manifests by hand.

## Required Reading

- `AGENTS.md`
- `docs/CURRENT_TASK_STATE.json`
- `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md`
- `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`
- `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md`
- `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`
- `docs/superpowers/plans/2026-06-03-optimizer-practice-first.md`
- `src/hermes_workflow/optimizer_suggestion.py`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `tools/run_spectre_ocean_adapter.py`

## Shared Shell Variables

Use these variables when executing the plan:

```bash
export REPO=/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
export C14_ROOT=/tmp/ic_auto_opt_c14
export C14_PROJECT=/tmp/ic_auto_opt_c14/bridge_test_inv
export C14_EVIDENCE=/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001
export C14_SOURCE_NETLIST=/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv/netlists/exported
export C14_CADENCE_CSHRC=/home/zzchen/cadence_ic231_env.csh
export HERMES=/home/zzchen/.venvs/openclaw/bin/hermes-workflow
```

If `$HERMES` does not exist, stop and activate or install the project CLI. Do not replace Hermes CLI calls with ad-hoc Python snippets.

## Artifact Policy

Committed files may be limited to sanitized docs and task-state updates:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/debug/2026-06-04-c14-real-tool-acceptance-result.md`
- `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`

Local-only evidence stays under:

```text
/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001/
```

## Task 1: Clean Acceptance Workspace And First-Run Seed Package

**Risk:** Medium. This prepares one approved local project and one first-run seed package. It must not run Spectre or OCEAN.

**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: Confirm repo and CLI state**

Run:

```bash
cd "$REPO"
git status --short
python3 tools/check_development_cadence.py
test -x "$HERMES"
"$HERMES" --version
```

Expected:

- cadence check passes;
- `hermes-workflow --version` exits 0;
- untracked OCEAN research/evidence files may remain untracked;
- no unexpected tracked changes are present.

- [x] **Step 2: Create clean local workspace**

Run:

```bash
rm -rf "$C14_PROJECT"
mkdir -p "$C14_EVIDENCE"
"$HERMES" init "$C14_PROJECT"
```

Expected:

- `$C14_PROJECT/config/project_config.yaml` exists;
- `$C14_PROJECT/netlists/exported/` exists.

- [x] **Step 3: Copy the known-good exported netlist bundle into the local project**

Run:

```bash
test -f "$C14_SOURCE_NETLIST/input.scs"
cp -a "$C14_SOURCE_NETLIST"/. "$C14_PROJECT/netlists/exported"/
sha256sum "$C14_PROJECT/netlists/exported/input.scs" > "$C14_EVIDENCE/exported_input_scs.sha256"
find "$C14_PROJECT/netlists/exported" -maxdepth 3 \( -type f -o -type d \) \
  > "$C14_EVIDENCE/exported_netlist_tree.txt"
```

Expected:

- `$C14_PROJECT/netlists/exported/input.scs` exists;
- sidecars such as `ade_e.scs` and `amap/` remain inside `netlists/exported/`;
- only `/tmp` evidence files are written.

If `$C14_SOURCE_NETLIST` is missing, stop and ask the user to provide or re-export the known-good `bridge_test_inv` netlist bundle. Do not copy raw decks into the repository.

- [x] **Step 4: Set local acceptance-only known-good lower bounds**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

import yaml

path = Path("/tmp/ic_auto_opt_c14/bridge_test_inv/config/variables.yaml")
payload = yaml.safe_load(path.read_text())
lower_by_name = {
    "FN": "4",
    "WN": "0.6u",
    "FP": "4",
    "WP": "1.2u",
}
for variable in payload["variables"]:
    name = variable["name"]
    if name in lower_by_name:
        variable["lower"] = lower_by_name[name]
path.write_text(yaml.safe_dump(payload, sort_keys=False))
PY
rg -n "lower: '?4'?|lower: 0.6u|lower: 1.2u|upper: '?12'?|upper: 3u" \
  "$C14_PROJECT/config/variables.yaml"
```

Expected:

- `FN` and `FP` lower bounds are `4`;
- `WN` lower bound is `0.6u`;
- `WP` lower bound is `1.2u`;
- upper bounds remain broad enough for `suggest-candidate` to produce a later unique candidate;
- this change is local to `/tmp/ic_auto_opt_c14` and is not committed.

- [x] **Step 5: Run Hermes preflight and approval**

Run:

```bash
"$HERMES" validate "$C14_PROJECT"
"$HERMES" package "$C14_PROJECT"
"$HERMES" prepare-netlist "$C14_PROJECT"
"$HERMES" dry-run "$C14_PROJECT"
"$HERMES" preflight-health "$C14_PROJECT"
"$HERMES" approve "$C14_PROJECT"
```

Expected:

- each command exits 0;
- `supervisor_instruction.json` contains `approve_first_real_run`;
- no real tool has run yet.

- [x] **Step 6: Prepare first real-run seed package**

Run:

```bash
"$HERMES" prepare-real-run "$C14_PROJECT" --run-id real_001
```

Expected:

- `runs/real/real_001/netlist/input.scs` exists;
- `runs/real/real_001/netlist/ade_e.scs` exists;
- `runs/real/real_001/netlist/amap/` exists;
- `runs/real/real_001/candidate.json` records `FN=4`, `WN=0.6u`, `FP=4`, and `WP=1.2u`;
- `runs/real/real_001/metric_extraction_request.json` keeps approved OCEAN formulas unchanged.

- [x] **Step 7: Record Task 1 state and stop**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's Task 1 checkboxes

Set next allowed action:

```text
wait for user confirmation, then execute C-14 Task 2 seed real-tool run
```

Do not start Task 2 without user confirmation because Task 2 runs real Spectre/OCEAN.

## Task 2: Seed Real-Tool Run And Record

**Risk:** High. This runs real Spectre/OCEAN through the existing C-7 adapter.

**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: Run the C-7 adapter for `real_001`**

Run:

```bash
cd "$REPO"
csh -fc "source $C14_CADENCE_CSHRC; cd $REPO; /home/zzchen/.venvs/openclaw/bin/python tools/run_spectre_ocean_adapter.py $C14_PROJECT --run-id real_001" \
  > "$C14_EVIDENCE/real_001_adapter.txt" 2>&1
cat "$C14_EVIDENCE/real_001_adapter.txt"
```

Expected:

- adapter exits 0;
- output includes `succeeded: run_id=real_001`;
- `runs/real/real_001/result_manifest.json` exists;
- `runs/real/real_001/metric_result_manifest.json` exists.

If this fails, stop and compare against the known-good C-7 closure evidence before making code changes.

Task 2 execution note:

- First adapter attempt failed inside the Codex sandbox with Spectre stderr `cannot create pipe [Operation not permitted]` and Spectre fatal `can't create server socket`.
- The failing command matched the known-good C-7 closure Spectre command, and the failure occurred before OCEAN.
- The adapter was rerun outside the sandbox through the approved Cadence `csh -fc` path with `--allow-overwrite`, and it succeeded without code, formula, or netlist-layout changes.
- Root cause: sandbox restriction on Spectre pipe/socket creation, not adapter command drift or OCEAN formula drift.

- [x] **Step 2: Run Hermes checks and record seed result**

Run:

```bash
"$HERMES" check-real-run "$C14_PROJECT" --run-id real_001
"$HERMES" check-metric-results "$C14_PROJECT" --run-id real_001
"$HERMES" record-real-result "$C14_PROJECT" --run-id real_001
```

Expected:

- all commands exit 0;
- `ledger/experiment_ledger.jsonl` has one checked row;
- `state/optimizer_state.json` has `current_evaluations` equal to `1`.

- [x] **Step 3: Capture sanitized seed evidence**

Run:

```bash
sha256sum \
  "$C14_PROJECT/runs/real/real_001/result_manifest.json" \
  "$C14_PROJECT/runs/real/real_001/metric_result_manifest.json" \
  "$C14_PROJECT/ledger/experiment_ledger.jsonl" \
  "$C14_PROJECT/state/optimizer_state.json" \
  > "$C14_EVIDENCE/real_001_returned_hashes.sha256"
```

Expected:

- hash file exists under `/tmp`;
- no raw PSF or full Cadence log is staged.

- [x] **Step 4: Record Task 2 state and stop**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's Task 2 checkboxes

Set next allowed action:

```text
wait for user confirmation, then execute C-14 Task 3 suggest and package real_002
```

## Task 3: Suggest Candidate And Prepare `real_002`

**Risk:** Medium. This exercises C-13 and candidate-injection package creation without running real tools.

**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: Run `suggest-candidate`**

Run:

```bash
"$HERMES" suggest-candidate "$C14_PROJECT" --candidate-id candidate_000002 \
  > "$C14_EVIDENCE/suggest_candidate_000002.txt" 2>&1
cat "$C14_EVIDENCE/suggest_candidate_000002.txt"
```

Expected:

- command exits 0;
- output includes `candidate id: candidate_000002`;
- `candidate_requests/candidate_000002.json` exists.

- [x] **Step 2: Inspect the candidate request shape without changing it**

Run:

```bash
python3 -m json.tool "$C14_PROJECT/candidate_requests/candidate_000002.json" \
  > "$C14_EVIDENCE/candidate_000002.pretty.json"
rg -n '"candidate_id"|"parameters"|"selection_mode"|"ledger_sha256"|"optimizer_state_sha256"' \
  "$C14_EVIDENCE/candidate_000002.pretty.json"
```

Expected:

- JSON is valid;
- candidate id is `candidate_000002`;
- parameters are present;
- provenance hashes are present.

- [x] **Step 3: Prepare candidate real-run package**

Run:

```bash
"$HERMES" prepare-candidate-real-run \
  "$C14_PROJECT" \
  --candidate-file "$C14_PROJECT/candidate_requests/candidate_000002.json" \
  --run-id real_002
```

Expected:

- `runs/real/real_002/netlist/input.scs` exists;
- `runs/real/real_002/candidate_request.json` exists;
- `runs/real/real_002/candidate.json` has `candidate_id` equal to `candidate_000002`;
- native netlist sidecars remain under `runs/real/real_002/netlist/`.

- [x] **Step 4: Record Task 3 state and stop**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's Task 3 checkboxes

Task 3 execution note:

- `suggest-candidate` wrote `candidate_requests/candidate_000002.json`.
- The selection mode was `initialization_fallback`, as expected with one checked ledger row.
- `prepare-candidate-real-run` prepared `runs/real/real_002` with `candidate_request.json`, `candidate.json`, native netlist sidecars, and unchanged approved OCEAN formulas.

Set next allowed action:

```text
wait for user confirmation, then execute C-14 Task 4 real_002 real-tool acceptance
```

Do not start Task 4 without user confirmation because Task 4 runs real Spectre/OCEAN.

## Task 4: Run Suggested Candidate Through Real Tools

**Risk:** High. This is the actual C-13 acceptance path through the real adapter.

**Files:**

- Modify: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [x] **Step 1: Run the C-7 adapter for `real_002`**

Run:

```bash
cd "$REPO"
csh -fc "source $C14_CADENCE_CSHRC; cd $REPO; /home/zzchen/.venvs/openclaw/bin/python tools/run_spectre_ocean_adapter.py $C14_PROJECT --run-id real_002" \
  > "$C14_EVIDENCE/real_002_adapter.txt" 2>&1
cat "$C14_EVIDENCE/real_002_adapter.txt"
```

Expected:

- preferred: adapter exits 0 and prints `succeeded: run_id=real_002`;
- if adapter fails, stop and compare with `real_001` plus C-7 closure evidence before code changes.

- [x] **Step 2: Run Hermes checks**

Run:

```bash
"$HERMES" check-real-run "$C14_PROJECT" --run-id real_002
"$HERMES" check-metric-results "$C14_PROJECT" --run-id real_002
```

Expected:

- preferred: both commands exit 0;
- if `check-real-run` fails, stop because the execution handoff is invalid;
- if `check-metric-results` fails after `check-real-run` passes, run Step 4 before deciding on code changes.

- [x] **Step 3: Record suggested candidate result when checks pass**

Run only if both Step 2 checks pass:

```bash
"$HERMES" record-real-result "$C14_PROJECT" --run-id real_002
```

Expected:

- command exits 0;
- `ledger/experiment_ledger.jsonl` has rows for `real_001` and `real_002`;
- `state/optimizer_state.json` has `current_evaluations` equal to `2`.

- [x] **Step 4: Classify a metric failure without changing formulas**

Not needed. `check-real-run` and `check-metric-results` both passed for `real_002`.

Run only if `check-real-run` passes but `check-metric-results` fails:

```bash
"$HERMES" assess-real-run-recovery "$C14_PROJECT" --run-id real_002 \
  > "$C14_EVIDENCE/real_002_recovery.txt" 2>&1
cat "$C14_EVIDENCE/real_002_recovery.txt"
```

Expected:

- recovery report is written;
- no manual manifest repair is performed;
- no OCEAN formula is changed;
- the result is recorded as a focused follow-up decision, not hidden as a C-13 success.

- [x] **Step 5: Capture sanitized `real_002` evidence**

Run:

```bash
find "$C14_PROJECT/runs/real/real_002" -maxdepth 3 -type f \
  | sort \
  > "$C14_EVIDENCE/real_002_file_list.txt"
sha256sum \
  "$C14_PROJECT/runs/real/real_002/candidate.json" \
  "$C14_PROJECT/runs/real/real_002/candidate_request.json" \
  "$C14_PROJECT/runs/real/real_002/real_run_manifest.json" \
  > "$C14_EVIDENCE/real_002_package_hashes.sha256"
```

Expected:

- local-only evidence exists under `/tmp`;
- no raw Cadence data is staged.

- [x] **Step 6: Record Task 4 state and stop**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's Task 4 checkboxes

Task 4 execution note:

- `real_002` ran through the C-7 Spectre/OCEAN adapter outside the sandbox and succeeded.
- `check-real-run`, `check-metric-results`, and `record-real-result` passed.
- OCEAN returned scalar values for `rise`, `fall`, and `DC`.
- The recorded ledger row has `simulation_status = real_constraint_fail`, meaning scalar extraction worked but the candidate did not satisfy configured constraints.

Set next allowed action:

```text
wait for user confirmation, then execute C-14 Task 5 acceptance decision and docs
```

## Task 5: Acceptance Decision And Sanitized Closeout

**Risk:** Low to medium. This records what happened and decides whether productization can continue.

**Files:**

- Create or modify: `docs/debug/2026-06-04-c14-real-tool-acceptance-result.md`
- Modify: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify if milestone-level summary is needed: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify if context compaction is likely: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [x] **Step 1: Write sanitized acceptance note**

Create `docs/debug/2026-06-04-c14-real-tool-acceptance-result.md` with this structure:

````markdown
# C-14 Real-Tool Acceptance Result

Date: 2026-06-04

## Scope

Accepted path:

```text
suggest-candidate
-> prepare-candidate-real-run
-> C-7 Spectre/OCEAN adapter
-> check-real-run
-> check-metric-results
-> record-real-result or recovery classification
```

## Local Evidence

```text
/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001/
```

## Result

- Seed `real_001`: <pass/fail and one-line reason>
- Suggested `real_002`: <pass/fail/classified and one-line reason>
- Ledger state: <row count or reason no row was recorded>

## Decision

Choose one:

- Proceed to narrow optimizer loop productization.
- Add focused failure-penalty/non-scalar candidate handling.
- Fix a specific C-7 adapter or contract bug found by this run.

## Safety

Python did not parse PSF data.
Approved OCEAN formulas were not rewritten.
Native Maestro/ADE netlist layout was preserved.
Raw Cadence artifacts remain local-only.
````

Replace each angle-bracket field with the actual observed result before committing. Keep the note sanitized.

- [x] **Step 2: Run repo-side verification**

Run:

```bash
cd "$REPO"
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- cadence check passes;
- whitespace check is clean;
- raw Cadence files, `docs/OCEAN_DOC_*`, and `docs/toolchain_evidence/` remain untracked or unstaged.

- [x] **Step 3: Commit sanitized docs only if user wants a commit**

If committing, use explicit pathspecs:

```bash
git add \
  docs/debug/2026-06-04-c14-real-tool-acceptance-result.md \
  docs/CURRENT_TASK_STATE.json \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/EXECUTION_PROGRESS_2026-05-29.md \
  docs/COMPACT_RESUME_CHECKPOINT.md \
  docs/superpowers/plans/2026-06-04-real-tool-acceptance.md
git commit -m "docs: record C14 real tool acceptance"
```

Expected:

- only sanitized docs are staged;
- no raw deck, sidecar, PSF/raw, full log, OCEAN research report, or toolchain evidence directory is committed.

## Acceptance Criteria

C-14 is accepted if:

- `real_001` seed run passes adapter, checks, and record.
- `suggest-candidate` writes `candidate_requests/candidate_000002.json` from recorded ledger/state.
- `prepare-candidate-real-run` packages that request as `real_002`.
- `real_002` is run by the C-7 adapter without changing approved formulas or layout.
- Hermes tooling either records `real_002` after valid metric checks or clearly classifies the failure through existing recovery contracts.
- The closeout note states whether the next scope is optimizer loop productization or a focused bug/failure-handling fix.

C-14 is not accepted if:

- the workflow requires Python PSF parsing;
- formulas are rewritten to make the run pass;
- native Maestro/ADE layout is replaced;
- returned manifests are manually edited;
- raw Cadence artifacts are committed.
