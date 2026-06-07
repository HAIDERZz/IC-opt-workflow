# Runtime-Native Agent Adapters

These assets make `/ic-opt PROJECT_DIR --doctor`, `/ic-opt PROJECT_DIR --real`,
and `/ic-opt PROJECT_DIR --continue M` work inside a specific agent CLI without
requiring that CLI to launch another CLI as the execution agent.

The product model is:

```text
User -> current runtime supervisor agent -> same-runtime execution subagent
```

The shell commands `ic-opt PROJECT_DIR --doctor`, `ic-opt PROJECT_DIR --real`,
and `ic-opt PROJECT_DIR --continue M` remain the deterministic automation core
for direct operator/debug use. Runtime adapters wrap that core with the active
CLI's own subagent mechanism.

## Claude

Install:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
```

Then use in Claude:

```text
/ic-opt PROJECT_DIR --doctor
/ic-opt PROJECT_DIR --real
/ic-opt PROJECT_DIR --continue 40
```

## OpenCode

Install:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter opencode
```

This copies:

```text
~/.config/opencode/command/ic-opt.md
~/.config/opencode/agents/ic-opt-execution.md
```

OpenCode command files use the `command/` directory, and OpenCode agent files
use the `agents/` directory. The `/ic-opt` command acts as the supervisor prompt
and instructs OpenCode to delegate real execution to the `ic-opt-execution`
subagent.

## Boundary

The historical C-64 `--execution-agent claude` subprocess route remains useful
for development acceptance, but it is not the default product target after
C-65.
