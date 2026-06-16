# C-46 Real-Scale Optimizer Status Handoff

Date: 2026-06-05

## Goal

Run the current production OpenBox handoff at a realistic 100-evaluation scale
from a fresh workspace, then close out with `optimizer-status`.

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: uses the current accepted packet/status production route and the
  known-good OpenBox/Spectre/OCEAN environment.
- Drift: none intended. Do not hand-pick points, change formulas, parse PSF,
  rewrite OCEAN formulas, or create a new optimizer framework.

## Workspace

Source for clean `config/` and `netlists/`:

```text
/tmp/ic_auto_opt_c34_clean2/bridge_test_inv
```

C-46 workspace:

```text
/tmp/ic_auto_opt_c46_real_scale_status_handoff_001/bridge_test_inv
```

## Steps

- [x] Prepare a clean workspace with only `config/`, `netlists/`, and matching
  `supervisor_instruction.json`.
- [x] Run `validate`, `package`, and `package-optimizer-task --backend openbox
  --max-evals 100`.
- [x] Confirm the generated packet includes `optimizer-status`.
- [x] Run `check-toolchain-env`.
- [x] Run the real OpenBox/Spectre/OCEAN command with the known-good venv,
  Cadence cshrc, writable `MPLCONFIGDIR`, `parallel_jobs=10`, and
  `threads_per_run=10`.
- [x] Run `check-optimizer-run`, `summarize-optimizer-run`,
  `finalize-optimizer-run`, and `optimizer-status`.
- [x] Record sanitized evidence under `docs/debug/`.
- [x] Update current state/progress at the end of the flow and commit.

## Stop Conditions

Stop for user intervention if an unexpected package, tool, license, Spectre,
OCEAN, or metric-extraction infrastructure failure appears. Candidate
`constraint_failed` or `metric_check_failed` statuses are optimizer outcomes,
not stop conditions by themselves.
