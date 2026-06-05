# Production Optimizer Handoff Acceptance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run one production-style optimizer handoff using the C-33 guide, with supervisor packet generation, execution-agent command handoff, and Hermes finalize/audit closeout.

**Architecture:** Use `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` as the active spec. Keep native TuRBO and OpenBox as supported backend choices; do not change optimizer code. Task 1 prepares the handoff package only, and Task 2 requires explicit user approval before running real Cadence tools.

**Tech Stack:** Hermes workflow CLI, existing optimizer task packet generation, existing real-tool optimizer commands, existing `finalize-optimizer-run`, local `/tmp` evidence.

---

## Boundaries

- Do not run real Virtuoso, Spectre, OCEAN, SSH, or `virtuoso-bridge-lite` in Task 1.
- Do not hand-pick optimizer points.
- Do not replace TuRBO.
- Do not silently fall back between backends.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not commit raw `input.scs`, `ade_e.scs`, PSF/raw, or full Cadence logs.
- Do not commit local `/tmp` evidence.

## Backend For This Acceptance

Default backend for this acceptance is `openbox`, because the current recent production route already productized `run-openbox-real` and the user is evaluating OpenBox as the likely optimizer backend.

If OpenBox is unavailable in the execution environment, the execution agent must report a dependency blocker rather than falling back to native TuRBO.

## Task 1: Supervisor Packet Preparation

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Local-only evidence: `/tmp/ic_auto_opt_c34/`

- [x] Confirm the selected known-good project directory.

Use an existing real-tool-ready project directory that preserves native Maestro/ADE netlist layout and approved formulas:

```text
/tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv
```

- [x] Generate the optimizer task packet without running real tools.

Run from the repository root:

```bash
.venv/bin/hermes-workflow package-optimizer-task /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv --backend openbox --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
```

Expected output includes:

```text
execution_package/OPTIMIZER_EXECUTION_TASK.md
execution_package/optimizer_execution_manifest.json
```

- [x] Copy sanitized handoff evidence to `/tmp/ic_auto_opt_c34/`.

The local evidence directory should contain only:

```text
EXECUTION_TASK.md
optimizer_execution_manifest.json
task_packet_sha256.txt
```

No raw Cadence artifacts should be copied.

- [x] Verify the packet points to the OpenBox real command and post-run audit path.

Run:

```bash
grep -n "run-openbox-real\|check-optimizer-run\|summarize-optimizer-run\|Do not hand-pick" /tmp/ic_auto_opt_c34/EXECUTION_TASK.md
```

Expected: all four terms are present.

- [x] Stop before real-tool execution.

Report the generated command and ask for explicit user approval before Task 2.

## Task 2: Execution-Agent Real Run

**Files:**

- Local-only output: `/tmp/ic_auto_opt_c34/`
- Real project artifacts under the selected `/tmp` project directory

- [ ] Confirm explicit user approval to run real Cadence tools.

Required user wording must clearly allow real Spectre/OCEAN execution for C-34 Task 2.

- [ ] Run the exact command from `OPTIMIZER_EXECUTION_TASK.md`.

The expected command shape is:

```bash
hermes-workflow run-openbox-real /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

- [ ] Preserve command stdout/stderr summary and returned artifact paths.

Keep raw logs local-only under `/tmp/ic_auto_opt_c34/`.

- [ ] Stop on unexpected tool failure.

Expected candidate-level `constraint_failed` and `metric_check_failed` samples are not unexpected by themselves. Unexpected failures include missing optimizer reports, result manifest absence, command dependency blockers, or real-tool failures that prevent final audit.

Task 2 status as of 2026-06-05:

- [x] User approved entering Task 2 with "继续进行".
- [x] The generated OpenBox command was attempted.
- [x] The run stopped before real Spectre/OCEAN because OpenBox is not installed in the active execution environment.
- [x] Sanitized blocker note written to `docs/debug/2026-06-05-c34-production-openbox-handoff-dependency-blocker.md`.
- [ ] User decision required: install OpenBox in the active execution environment, regenerate/rerun with native TuRBO, or pause.

## Task 3: Supervisor Finalize And Closeout

**Files:**

- Modify: `docs/debug/<sanitized-c34-note>.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] Run final supervisor closeout.

```bash
.venv/bin/hermes-workflow finalize-optimizer-run /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv
```

- [ ] Archive a sanitized note.

The note must include backend, evaluation count, status distribution, best observed candidate, Spectre/OCEAN settings audit, finalize status, and next recommendation. It must not include raw netlists, PSF paths, or full Cadence logs.

- [ ] Run docs/checks before commit.

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

## Route Audit

- Active spec: `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md`
- Active plan: `docs/superpowers/plans/2026-06-05-production-optimizer-handoff-acceptance.md`
- Top-level plan: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: C-34 performs one guide-driven production handoff and uses existing optimizer packet, execution, and finalize/audit commands.
- Drift: none. It does not create a new optimizer framework or repeat backend validation outside the production handoff path.
