# Agent Integration Status

Date: 2026-06-16

The maintained agent entry is:

```text
skills/ic-opt/SKILL.md
```

Agent-assisted operation uses the same product CLI as a human operator.

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
```

Remote execution uses:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

## Current Capability

- local and remote real optimization through `ic-opt`
- local and remote doctor gates with license probe support
- requirement-driven budget, batch size, parallel jobs, Spectre threads,
  optimizer CPU cap, algorithm, strategy, initialization, output format,
  retention, testbench routes, and process-corner settings
- continuation through `--continue N`
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO
- multi-testbench and multi-corner candidate evaluation
- sanitized Spectre/OCEAN `command_trace` in child and aggregate manifests
- optimizer CPU thread-limit audit in optimizer reports

## Related Docs

```text
docs/AGENT_OPTIMIZER_USAGE_MANUAL.md
docs/TOOLCHAIN_EXECUTION_REFERENCE.md
docs/OPTIMIZER_ALGORITHM_MODES.md
docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md
```
