# OpenBox Real Backend Acceptance Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run one narrow real-tool OpenBox acceptance spike and decide whether OpenBox deserves production backend work.

**Architecture:** Do not replace TuRBO. Build a local-only OpenBox ask-and-tell runner under `/tmp`, feed its candidates into the existing Spectre/OCEAN candidate evaluator, write C-27 backend-neutral artifacts, then use C-25/C-26 to audit and summarize the result.

**Tech Stack:** Python, OpenBox, existing Hermes workflow APIs, existing Spectre/OCEAN adapter, pytest/ruff for repo checks.

---

## Boundaries

- Do not modify production optimizer code during Tasks 1-3 unless a blocker proves a small compatibility fix is necessary.
- Do not replace or delete `src/hermes_workflow/native_turbo.py`.
- Do not run real tools before Task 2 and explicit user approval.
- Do not parse PSF or waveform files in Python.
- Do not rewrite OCEAN formulas.
- Do not commit raw Cadence artifacts.
- Do not create a broad optimizer framework.

## File Map

- Create local-only script under `/tmp/ic_auto_opt_c28_openbox_real/`.
- Create sanitized evidence note: `docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md`.
- Modify progress state files:
  - `docs/CURRENT_TASK_STATE.json`
  - `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
  - `docs/EXECUTION_PROGRESS_2026-05-29.md`
  - `docs/COMPACT_RESUME_CHECKPOINT.md` only if context compaction is expected.

No production Python module is planned for C-28.

---

### Task 1: Environment And Known-Good Project Gate

**Files:**
- Local-only: `/tmp/ic_auto_opt_c28_openbox_real/`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [ ] **Step 1: Confirm OpenBox import path**

Run in the intended Python environment:

```bash
python3 - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("openbox") else 2)
PY
```

Expected:

- Exit `0`: proceed.
- Exit `2`: stop and ask the user whether to use an existing OpenBox venv or install OpenBox in an isolated environment.

- [ ] **Step 2: Prepare a local-only known-good project**

Use the same native Maestro/ADE/Spectre layout that passed previous TuRBO real acceptance. The local project must live under:

```text
/tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv
```

It must preserve:

```text
netlists/exported/input.scs
netlists/exported/ade_e.scs
netlists/exported/amap/
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
```

It must remove stale generated state before the spike:

```text
runs/
reports/
state/
ledger/experiment_ledger.jsonl
```

- [ ] **Step 3: Record Task 1 status**

Update `docs/CURRENT_TASK_STATE.json`:

```json
{
  "current_scope": "C-28 OpenBox Real Backend Acceptance Spike",
  "current_status": "C-28 Task 1 environment and known-good project gate complete or blocked.",
  "active_spec": "docs/superpowers/specs/2026-06-05-openbox-real-backend-acceptance-spike-design.md",
  "active_plan": "docs/superpowers/plans/2026-06-05-openbox-real-backend-acceptance-spike.md",
  "next_allowed_action": "execute C-28 Task 2 real OpenBox ask-and-tell run only after user confirms real-tool execution"
}
```

- [ ] **Step 4: Verify Task 1**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: cadence and diff checks pass; raw local project artifacts are not staged.

---

### Task 2: Local-Only OpenBox Ask-And-Tell Real Run

**Files:**
- Local-only script: `/tmp/ic_auto_opt_c28_openbox_real/run_openbox_real_spike.py`
- Local-only run artifacts under `/tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv/`

- [ ] **Step 1: Create a local-only spike script**

The script must:

- Import existing Hermes APIs from the repo.
- Load the approved project contract.
- Use OpenBox ask-and-tell or batch suggestions.
- Convert suggestions into approved parameter values through existing Hermes quantization.
- Evaluate each batch with the existing real candidate evaluator.
- Write backend-neutral artifacts:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

The script must not:

- Parse PSF.
- Rewrite metric formulas.
- Hand-pick candidates.
- Change Spectre settings.

- [ ] **Step 2: Run one real OpenBox batch optimizer acceptance**

Run only after explicit user confirmation:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; .venv/bin/python /tmp/ic_auto_opt_c28_openbox_real/run_openbox_real_spike.py /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10'
```

Expected:

- 100 attempted optimizer evaluations unless a true setup/tool blocker occurs.
- `reports/optimizer_run_report.json` exists.
- `reports/optimizer_evaluations.jsonl` exists.
- Every successful Spectre run records consistent `preset`, `threads_per_run`, `parallel_jobs`, and `output_format`.

Stop immediately for:

- OpenBox API mismatch that prevents ask-and-tell.
- Missing Cadence/OpenBox environment.
- Repeated true real-tool failures not seen in TuRBO route.
- Any evidence that the script is hand-picking points rather than using OpenBox suggestions.

---

### Task 3: Supervisor/Hermes Audit And TuRBO Baseline Comparison

**Files:**
- Existing CLI outputs under `/tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv/reports/`
- Create: `docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md`

- [ ] **Step 1: Run C-25 acceptance**

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv
```

Expected:

- Exit `0` if artifacts are acceptable.
- Writes `reports/optimizer_run_acceptance_report.json`.

- [ ] **Step 2: Run C-26 completion decision**

```bash
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv
```

Expected:

- Writes `reports/optimizer_completion_report.json`.
- Reports `best_observed`, not global optimum unless the full finite grid was exhausted.

- [ ] **Step 3: Compare against TuRBO baseline**

Use the accepted TuRBO baseline records in `docs/CURRENT_TASK_STATE.json` and existing debug notes.

Compare:

- evaluation count
- feasible count
- constraint_failed count
- metric_check_failed count
- real_check_failed count
- duplicate/quantization issues
- best observed candidate and objective
- C-26 continuation decision
- Spectre settings audit

- [ ] **Step 4: Write sanitized evidence note**

Create:

```text
docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md
```

It must include:

```text
Decision: proceed_to_openbox_productization | keep_openbox_fake_only_for_now | reject_openbox_real_backend_for_now
Run directory: /tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv
Counts: feasible / constraint_failed / metric_check_failed / real_check_failed
Best observed candidate:
Spectre settings audit:
C-25 result:
C-26 decision:
TuRBO baseline comparison:
Issues:
```

Do not paste raw Cadence logs.

---

### Task 4: Closeout And Next-Step Decision

**Files:**
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`

- [ ] **Step 1: Update state**

Set `current_scope` to:

```text
C-28 OpenBox Real Backend Acceptance Spike
```

Set `next_allowed_action` according to the evidence:

- `write C-29 OpenBox productization plan` if decision is `proceed_to_openbox_productization`.
- `pause OpenBox real backend and keep TuRBO real route` if decision is `keep_openbox_fake_only_for_now`.
- `reject OpenBox real backend for now` if decision is `reject_openbox_real_backend_for_now`.

- [ ] **Step 2: Run final local checks**

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- Cadence and diff checks pass.
- No raw local artifacts are staged.

- [ ] **Step 3: Commit docs-only closeout if evidence note is written**

Only commit sanitized docs and state updates:

```bash
git add docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md \
  docs/CURRENT_TASK_STATE.json \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/EXECUTION_PROGRESS_2026-05-29.md
git commit -m "docs: record OpenBox real backend acceptance spike"
```

If Task 2 is blocked before real execution, commit only the planning/state docs if useful and report the blocker.
