# Runtime Agent Adapters

These assets make `/ic-opt PROJECT_DIR --doctor`, `/ic-opt PROJECT_DIR --real`,
and `/ic-opt PROJECT_DIR --continue M` easier to use inside agent CLIs.

Default product model:

```text
User -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

The shell commands `ic-opt PROJECT_DIR --doctor`, `ic-opt PROJECT_DIR --real`,
and `ic-opt PROJECT_DIR --continue M` remain the deterministic automation core.
Runtime adapters teach the active agent how to operate that core without asking
the user to restate formulas, variables, metric routes, or Spectre settings.

Optional advanced model:

```text
User -> current agent -> same-runtime native subagent -> ic-opt CLI
```

Use the optional subagent path only when the user explicitly requests it and the
runtime has stable native subagent/task support.

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

The `/ic-opt` command is the default single-agent operator prompt. The
`ic-opt-execution` subagent remains available for explicit optional subagent
mode, not as the default route.

## Boundary

Do not make a product flow depend on one agent CLI launching another agent CLI.
The historical Claude subprocess route is development evidence and fallback
debug tooling, not the default user experience.
