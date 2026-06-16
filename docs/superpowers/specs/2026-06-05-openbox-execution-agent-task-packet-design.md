# OpenBox Execution-Agent Task Packet Design

> Historical command notice: this old design spec may show obsolete
> workload/resource CLI flags. Current release product first runs read those
> values only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

Date: 2026-06-05

## Status

Design scope for C-30. This is a narrow handoff-package update after C-29.

## Context

C-29 productized the OpenBox real optimizer backend:

```text
OpenBox ask-and-tell
-> Hermes candidate package
-> Spectre/OCEAN real execution
-> backend-neutral optimizer artifacts
-> check-optimizer-run
-> summarize-optimizer-run
```

The existing `package-optimizer-task` command still writes an execution-agent
task packet for the native TuRBO command only. C-30 adds an OpenBox backend
variant so a real execution agent can receive the same standard package style
without guessing command names, dependency expectations, returned artifacts, or
audit requirements.

## Scope

C-30 updates only the optimizer execution-agent package contract:

- keep the existing native TuRBO task packet as the default;
- add an explicit OpenBox backend option;
- render backend-specific execution instructions;
- record backend and command metadata in
  `execution_package/optimizer_execution_manifest.json`;
- keep required returned artifacts backend-neutral where possible;
- require the execution agent to run supervisor audit commands after execution.

## Non-Goals

- Do not replace TuRBO.
- Do not make OpenBox the global default optimizer.
- Do not run real Virtuoso, Spectre, OCEAN, SSH, or virtuoso-bridge in C-30.
- Do not introduce a new workflow engine, daemon, database, or service.
- Do not add optimizer algorithm logic.
- Do not parse PSF in Python.
- Do not rewrite OCEAN or ADE Calculator formulas.
- Do not hand-pick candidate points.
- Do not commit raw Cadence artifacts.

## Backend Modes

### Native TuRBO

Default behavior remains:

```bash
hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals N --cadence-cshrc CSHRC
```

The generated task continues to require native `Turbo1.optimize()` use.

### OpenBox

The new explicit backend renders:

```bash
hermes-workflow run-openbox-real PROJECT_DIR --max-evals N --batch-size B --parallel-jobs P --cadence-cshrc CSHRC
```

The package must state:

- OpenBox must be installed/importable in the execution environment.
- If OpenBox is unavailable, report a dependency blocker.
- Do not silently fall back to TuRBO or manual candidate selection.
- Do not hand-pick candidates.
- Run `check-optimizer-run` and `summarize-optimizer-run` after execution.

## Manifest Additions

`optimizer_execution_manifest.json` gains:

```json
{
  "backend": "native_turbo | openbox",
  "audit_commands": [
    ["hermes-workflow", "check-optimizer-run", "PROJECT_DIR"],
    ["hermes-workflow", "summarize-optimizer-run", "PROJECT_DIR"]
  ]
}
```

For OpenBox it also records:

```json
{
  "batch_size": 10,
  "parallel_jobs": 10
}
```

## Acceptance Criteria

- Existing native TuRBO package tests pass unchanged by default.
- `package-optimizer-task --backend openbox` writes an OpenBox command.
- OpenBox package text includes dependency-blocker instructions.
- OpenBox package text includes post-run audit commands.
- OpenBox package text forbids silent fallback and manual candidate selection.
- Manifest records backend, command, audit commands, and required returned
  artifacts.
- No real tools are run by tests or package generation.

## Route Audit

- Active top-level direction: lightweight agent workflow around proven
  Cadence/Spectre/OCEAN behavior.
- Alignment: C-30 only improves the execution-agent handoff for the C-29
  backend and keeps the existing supervisor audit layer.
- Drift: none intended. TuRBO remains available and default.
