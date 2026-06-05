# C-36 Stable OpenBox/Hermes Execution Environment Gate Design

Date: 2026-06-05

## Purpose

C-36 turns the C-34 known-good OpenBox/Hermes execution environment into a
small, repeatable environment gate.

This prevents repeated failures where OpenBox is run from the wrong venv,
Hermes workflow tooling is missing from the OpenBox venv, or real-tool commands
are attempted before the execution environment is known.

## Scope

Add a deterministic environment check that verifies:

- the OpenBox execution venv exists;
- the venv has a Python executable;
- the same Python can import `openbox` and `hermes_workflow.openbox_backend`;
- the venv contains `hermes-workflow`;
- the Cadence cshrc exists;
- the check can write a JSON report when requested.

The default OpenBox venv remains the C-34 proven path:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

The command must allow an explicit `--openbox-venv` override so a later stable
production venv can be checked without changing code.

## CLI

Add:

```bash
hermes-workflow check-toolchain-env \
  --openbox-venv /tmp/ic_auto_opt_openbox_spike/.venv \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh \
  --report /tmp/toolchain_environment_report.json
```

The command exits `0` when all checks pass and exits non-zero when any required
check fails.

## Out Of Scope

- Do not install OpenBox.
- Do not create or migrate a venv.
- Do not run Virtuoso, Spectre, OCEAN, OpenBox optimization, SSH, or
  `virtuoso-bridge-lite`.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not change optimizer backend behavior.
- Do not add broad workflow orchestration.

## Acceptance

- Unit tests cover pass/fail report behavior without requiring real OpenBox.
- CLI tests cover pass/fail status and report writing.
- The toolchain reference documents the new gate.
