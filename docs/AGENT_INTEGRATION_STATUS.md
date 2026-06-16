# Agent integration status

Date: 2026-06-16

The maintained product entrypoint is:

```bash
ic-opt PROJECT_DIR --real
```

Continuation:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Agent-assisted operation uses the same product CLI. Give the agent
`skills/ic-opt/SKILL.md` and `PROJECT_DIR`; the agent should run the CLI, inspect
artifacts, and report evidence.

## Current workflow capabilities

- Local and remote real optimization through `ic-opt`.
- Local and remote doctor gates with license probe support.
- Requirement-driven budget, batch size, parallel jobs, Spectre threads,
  optimizer CPU cap, algorithm, strategy, initialization, output format,
  retention, testbench, and process-corner settings.
- Continuation through `--continue N`.
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO.
- Multi-testbench and multi-corner candidate evaluation.
- Sanitized Spectre/OCEAN `command_trace` in child and aggregate manifests.
- Optimizer CPU thread-limit audit in optimizer reports.

See also:

```text
docs/AGENT_OPTIMIZER_USAGE_MANUAL.md
docs/TOOLCHAIN_EXECUTION_REFERENCE.md
docs/OPTIMIZER_ALGORITHM_MODES.md
docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md
```
