# Agent Integration Status

Date: 2026-06-16

## Product Model

The product model is:

```text
User -> current agent CLI supervisor -> same-runtime execution subagent
```

The shell product entrypoint is:

```bash
ic-opt PROJECT_DIR --real
```

The runtime-native agent entrypoint, after installing the adapter, is:

```text
/ic-opt PROJECT_DIR --real
```

Continuation keeps one CLI budget delta:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Initial-run workload, resource, optimizer, Spectre, metric, retention, and
process-corner values must come from `opt_requirement.md` and generated config.
Do not add product CLI overrides for those values.

## Runtime Adapter Assets

Claude adapter source:

```text
claude_skills/ic-opt/
```

OpenCode adapter source:

```text
agent_runtime/opencode/command/ic-opt.md
agent_runtime/opencode/agents/ic-opt-execution.md
```

Installer/check commands:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
./.venv/bin/hermes-workflow install-runtime-adapter opencode
./.venv/bin/hermes-workflow runtime-adapter-status
```

- Product `ic-opt PROJECT_DIR --real` flow.
- Local and remote doctor gates, including real license probe when required.
- Peer production strategy routing for `openbox_gp_eic`,
  `openbox_prf_eic`, and `turbo_trust_region`; `openbox_auto` is the
  default automatic mode and `random_baseline` is diagnostic only.
- Multi-testbench and multi-corner candidate evaluation.
- Requirement-driven initialization pass-through for OpenBox and native TuRBO.
- Sanitized Spectre/OCEAN command trace in child and aggregate manifests.
- CPU thread-limit runtime audit in optimizer reports.
- Optimizer decision, insight, visualization, and final-summary reports.

## Evidence Boundary

Older C-60/C-64/C-66 evidence may mention product commands with workload or
resource flags. Those commands are historical evidence only. The current product
contract is requirement-driven first run plus `--continue N` for continuation.

Current release evidence and bug-fix summary are in:

```text
RELEASE_NOTES_v0.1.7.md
docs/CURRENT_BUGFIX_PROGRESS.md
docs/OPTIMIZER_ALGORITHM_MODES.md
docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md
```
