# C-36 Stable OpenBox/Hermes Execution Environment Gate

Date: 2026-06-05

Design spec:

```text
docs/superpowers/specs/2026-06-05-stable-openbox-hermes-execution-environment-gate-design.md
```

## Goal

Productize the C-34 known-good OpenBox/Hermes execution environment as a small
preflight gate. This is not an optimizer run.

## Tasks

- [x] Task 1: Add environment report model and checker.
  - Verify with focused unit tests using an injected Python probe runner.

- [x] Task 2: Add `hermes-workflow check-toolchain-env`.
  - Verify pass/fail CLI behavior and JSON report writing.

- [x] Task 3: Sync toolchain docs and progress state.
  - Update `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`,
    `docs/CURRENT_TASK_STATE.json`, and required progress files.

- [x] Task 4: Final verification and commit.
  - Run targeted tests, cadence checker, and diff checks.

## Completion Notes

- Added `src/hermes_workflow/toolchain_env.py`.
- Added CLI `hermes-workflow check-toolchain-env`.
- Verified the current C-34 OpenBox/Hermes venv with:

```bash
.venv/bin/hermes-workflow check-toolchain-env --openbox-venv /tmp/ic_auto_opt_openbox_spike/.venv --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --report /tmp/toolchain_environment_report_c36.json
```

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-stable-openbox-hermes-execution-environment-gate-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment:
  C-36 supports the proven real-tool execution route by preventing repeated
  venv/sandbox setup failures before execution.
- Drift:
  None. This plan adds a preflight gate only; it does not change optimizer
  backends, Spectre/OCEAN execution, formulas, or report semantics.
