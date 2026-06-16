# C-45 Fresh Optimizer Status Handoff Drill

Date: 2026-06-05

Active spec:

```text
docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md
```

## Goal

Run one fresh production-style OpenBox handoff from a clean workspace using the
updated C-44 packet and close it out with `optimizer-status`.

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: validates the current production handoff path after C-44 by using
  a fresh workspace, generated packet, real OpenBox/Spectre/OCEAN execution,
  manifest-level audit, finalization, and supervisor status summary.
- Drift: none intended. Do not hand-pick optimizer points, alter variables,
  change formulas, parse PSF, rewrite OCEAN formulas, or create a new framework.

## Workspace

Source for clean `config/` and `netlists/`:

```text
/tmp/ic_auto_opt_c34_clean2/bridge_test_inv
```

C-45 drill workspace:

```text
/tmp/ic_auto_opt_c45_fresh_status_handoff_001/bridge_test_inv
```

Only `config/`, `netlists/`, and the matching approved
`supervisor_instruction.json` are copied from the known-good source. Do not copy
old `ledger/`, `state/`, `reports/`, or `runs/`.

## Task 1: Fresh Workspace And Packet

- [x] Prepare the clean C-45 workspace.
- [x] Run `validate`, `package`, and `package-optimizer-task --backend openbox
  --max-evals 10`.
- [x] Verify the generated packet includes `optimizer-status` in task text and
  manifest audit commands.

## Task 2: Real Execution And Closeout

- [x] Run `check-toolchain-env`.
- [x] Run the generated OpenBox real command with the known-good OpenBox venv,
  Cadence cshrc, writable `MPLCONFIGDIR`, and non-sandbox/escalated execution.
- [x] Run `check-optimizer-run`, `summarize-optimizer-run`,
  `finalize-optimizer-run`, and `optimizer-status`.
- [x] Stop for user intervention if an unexpected tool/license/metric/package
  failure appears.

## Task 3: Sync Route Documents

- [x] Record sanitized evidence under `docs/debug/`.
- [x] Update `docs/CURRENT_TASK_STATE.json`,
  `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`,
  `docs/EXECUTION_PROGRESS_2026-05-29.md`,
  `docs/COMPACT_RESUME_CHECKPOINT.md`, and this plan.
- [x] Sync top-level plan current node and AGENTS.md if they contain stale
  route guidance.
- [x] Run cadence and diff checks, then commit.

## Acceptance

- C-45 adds 10 real OpenBox-generated evaluations from a fresh workspace.
- The generated task packet includes `optimizer-status`.
- `optimizer-status` prints the final supervisor summary after finalization.
- No raw Cadence artifacts, PSF/raw data, protected sidecars, or full logs are
  committed.
