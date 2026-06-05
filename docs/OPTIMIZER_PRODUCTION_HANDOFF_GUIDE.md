# Optimizer Production Handoff Guide

Date: 2026-06-05

This is the short production guide for running the optimizer workflow through
the locked supervisor / Hermes workflow tooling / execution agent role model.

It is intentionally narrow. It describes the currently supported handoff path
and does not introduce a new optimizer framework.

## Roles

Supervisor agent:

- prepares and validates project contracts;
- generates the optimizer execution task packet;
- sends the task packet to the execution agent;
- accepts results only through Hermes workflow reports;
- decides whether to accept the best observed candidate or continue.

Hermes workflow tooling:

- writes deterministic task packets and manifests;
- runs optimizer acceptance, completion, and insight report checks;
- records machine-readable reports under `reports/`;
- does not run real Virtuoso/Spectre/OCEAN during supervisor audit commands.

Execution agent:

- reads `execution_package/OPTIMIZER_EXECUTION_TASK.md`;
- runs the exact optimizer command in the task packet;
- operates real Cadence tools only through the approved command path;
- returns manifests, reports, ledger, state, and failure evidence;
- does not hand-pick points or report success only in prose.

## Preconditions

- Read `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` before any real
  Virtuoso/Spectre/OCEAN/OpenBox/native-TuRBO/bridge execution. That file is the
  authoritative reference for known-good venvs, Cadence cshrc, non-sandbox
  execution, fresh workspace preparation, and closeout commands.
- Run `hermes-workflow check-toolchain-env` before OpenBox real execution when
  the execution venv has changed or after context compaction.
- `config/*.yaml` is already reviewed and valid.
- `metrics.yaml` contains approved OCEAN formulas.
- `netlists/exported/input.scs` and native Maestro/ADE sidecars are present.
- First real-run approval and real-tool contracts have already been satisfied.
- Cadence cshrc path is known, for example `/home/zzchen/cadence_ic231_env.csh`.
- Real Cadence execution is run outside restrictive sandboxes.
- OpenBox execution requires OpenBox and Hermes workflow tooling importable in
  the same execution environment.
- Fresh production workspaces need both `execution_package/execution_manifest.json`
  and an approved `supervisor_instruction.json` whose config hashes match that
  execution manifest.

Do not proceed if the project only has chat claims and no validated contract
files or Hermes reports.

## Backend Choice

Use native TuRBO when the user has not explicitly selected another backend:

```bash
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend native-turbo --max-evals 100 --cadence-cshrc CADENCE_CSHRC --parallel
```

Use OpenBox only when explicitly selected:

```bash
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --max-evals 100 --cadence-cshrc CADENCE_CSHRC --parallel
```

Continue an accepted OpenBox run only when the supervisor decides to add more
evaluations:

```bash
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --continuation --additional-evals 20 --cadence-cshrc CADENCE_CSHRC --parallel
```

Both backends must use the same approved variables, bounds, quantization, metric
formulas, Spectre settings, and manifest-level audit rules. Do not add hidden
coupling such as `FP=FN` unless it is present in the approved project contract.

## Supervisor Handoff Flow

1. Confirm or generate the standard execution manifest:

```bash
.venv/bin/hermes-workflow package PROJECT_DIR
```

If `supervisor_instruction.json` is copied from a known-good approved project,
the `approved_config_hashes` must exactly match
`execution_package/execution_manifest.json`.

2. Generate the optimizer execution task packet for a first optimizer run:

```bash
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend BACKEND --max-evals 100 --cadence-cshrc CADENCE_CSHRC --parallel
```

For an OpenBox continuation, use:

```bash
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --continuation --additional-evals N --cadence-cshrc CADENCE_CSHRC --parallel
```

3. Give the execution agent these files:

- `execution_package/OPTIMIZER_EXECUTION_TASK.md`
- `execution_package/optimizer_execution_manifest.json`

4. Wait for the execution agent to finish and return file artifacts.

5. Run the closeout command:

```bash
.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
```

6. Read:

- `reports/optimizer_finalize_report.json`
- `reports/optimizer_run_acceptance_report.json`
- `reports/optimizer_completion_report.json`
- `reports/optimizer_insight_report.md`
- `reports/optimizer_visuals/*.svg`

The final report is the supervisor-facing entry point. The individual reports
remain available for debugging.

## Execution Agent Flow

The execution agent must run the command rendered in
`OPTIMIZER_EXECUTION_TASK.md` exactly. It must not invent candidates.

Native TuRBO task packets call:

```bash
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals N --cadence-cshrc CADENCE_CSHRC
```

OpenBox task packets call:

```bash
hermes-workflow run-openbox-real PROJECT_DIR --max-evals N --batch-size B --parallel-jobs P --cadence-cshrc CADENCE_CSHRC
```

OpenBox continuation task packets call:

```bash
hermes-workflow continue-openbox-real PROJECT_DIR --additional-evals N --batch-size B --parallel-jobs P --cadence-cshrc CADENCE_CSHRC
```

Before OpenBox real execution, the execution agent must run the toolchain gate
printed in the packet. The current known-good OpenBox execution environment is:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

The real optimizer command must run with the OpenBox venv first in `PATH`,
Cadence cshrc sourced, writable `MPLCONFIGDIR`, and a non-sandbox/escalated
execution path.

After execution, the execution agent should run the audit commands printed in
the task packet, then report the paths and status. Chat text is not acceptance
evidence; the files are the evidence.

## Required Returned Artifacts

Native TuRBO:

- `reports/native_turbo_run_report.json`
- `reports/native_turbo_evaluations.jsonl`
- `state/optimizer_state.json`
- `ledger/experiment_ledger.jsonl`

OpenBox:

- `reports/optimizer_run_report.json`
- `reports/optimizer_evaluations.jsonl`
- `state/optimizer_state.json`
- `ledger/experiment_ledger.jsonl`
- `reports/optimizer_run_acceptance_report.json`
- `reports/optimizer_completion_report.json`
- `reports/optimizer_finalize_report.json`
- `reports/optimizer_insight_report.json`
- `reports/optimizer_insight_report.md`
- `reports/optimizer_visuals/*.svg`

Real-tool runs also produce per-run manifests under `runs/real/<run_id>/`.
Supervisor acceptance depends on those manifests, not on command exit status.

## Acceptance Rules

The run is production-accepted only when:

- `finalize-optimizer-run` exits zero;
- `reports/optimizer_finalize_report.json` has `"status": "pass"`;
- acceptance status is accepted;
- completion status is pass;
- insight status is pass.

The best candidate is always the best observed candidate, not a global optimum.
The supervisor should use the completion report decision and confidence fields
to decide whether to accept, continue, revise the search space, or escalate.

## Failure Handling

Treat these as different cases:

- `constraint_failed`: candidate was evaluated but did not satisfy approved specs.
- `metric_check_failed`: tool ran, but returned metrics were non-scalar or invalid.
- `real_check_failed`: real tool package or result manifest failed.
- dependency blocker: required backend or Cadence environment is unavailable.
- duplicate or quantization conflict: candidate generation collided with an
  existing approved grid point.

Do not convert these into Python waveform calculations. Fix the workflow,
environment, package, or search-space issue instead.

## Forbidden Actions

- Do not hand-pick optimizer points.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not change approved metric formulas.
- Do not flatten or replace the native Maestro/ADE netlist layout.
- Do not silently fall back from OpenBox to TuRBO.
- Do not claim success from command exit status alone.
- Do not commit raw `input.scs`, `ade_e.scs`, PSF/raw data, or full Cadence logs.

## Minimal Operator Checklist

- Confirm backend: `native-turbo` or `openbox`.
- Generate task packet with `package-optimizer-task`.
- For OpenBox continuation, use `--continuation --additional-evals N`.
- For OpenBox real execution, run the task packet's toolchain gate first.
- Execution agent runs the rendered command outside restrictive sandboxing.
- Execution agent preserves returned artifacts.
- Supervisor runs `finalize-optimizer-run`.
- Supervisor reads the finalize, completion, and insight reports.
- Supervisor records the next decision before launching another optimizer run.
