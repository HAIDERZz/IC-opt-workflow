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

The intended role model is:

```text
user -> current runtime supervisor agent -> same-runtime execution subagent
```

The supervisor agent should perform preparation, approval, and report reading.
The execution subagent should run only the approved command from the generated
optimizer task package.

## Included Runtime Assets

This package includes starter assets for:

- Claude: `claude_skills/ic-opt/`
- OpenCode-style runtimes: `agent_runtime/opencode/`

These assets are templates. Each runtime may require local installation steps
before `/ic-opt` becomes available.

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

v0.1 packages the command-line product flow and starter agent runtime assets.
Users can run the automation directly with `ic-opt`. Runtime-native two-agent
behavior should be validated in the target user's own agent environment before
claiming full integration for that runtime.
