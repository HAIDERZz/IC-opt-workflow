# Agent Integration Status

This document describes the v0.1 public release boundary for agent use.

## Implemented Core

The deterministic automation core is:

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --continue M
```

The doctor command runs a lightweight project/environment check and writes
`reports/ic_opt_doctor_report.json`. The real command reads
`PROJECT_DIR/opt_requirement.md`, prepares the project, runs the approved
optimizer flow, and writes reports under `PROJECT_DIR/reports/`.
The continuation command adds M more real evaluations to an existing optimizer
history and refreshes the decision/insight reports.

## Intended Agent Model

For an agent runtime that supports commands or skills, the user-facing shape is:

```text
/ic-opt PROJECT_DIR --doctor
/ic-opt PROJECT_DIR --real
/ic-opt PROJECT_DIR --continue M
```

The intended default role model is:

```text
user -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

The agent should operate `ic-opt`, wait for completion, read reports, and explain
the result. Native same-runtime subagents are optional advanced mode only when
the user explicitly requests them and the runtime supports them.

## Included Agent Assets

This package includes:

- platform-neutral skill: `skills/ic-opt/`

The skill is not limited to one agent platform. Runtime-specific adapters are not
part of the core release boundary; users may adapt the same `SKILL.md` to their
own agent environment if needed.

## Hard Boundaries

Agents must not:

- rewrite approved OCEAN formulas;
- parse PSF directly in Python;
- hand-pick optimizer candidates;
- hardcode Spectre versions or local paths;
- create a Python virtualenv inside each user project;
- change `parallel_jobs`, `threads_per_run`, or optimizer CPU settings during
  continuation unless the user explicitly asks for a resource change.

## Current v0.1 Claim

v0.1 packages the command-line product flow and a platform-neutral agent skill.
Users and agents can run the automation directly with `ic-opt`. Optional
runtime-native subagent behavior should be validated in the target user's own
agent environment before claiming support for that optional mode.
