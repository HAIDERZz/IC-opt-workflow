# Claude Runtime Adapter

This directory contains the Claude skill used by C-65's runtime-native product
route.

Install from the repository root:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
```

Then a Claude CLI or Claude Code session can run:

```text
/ic-opt PROJECT_DIR --real
```

The skill treats Claude as the supervisor agent. It first runs the deterministic
Hermes supervisor gate, which generates and approves the optimizer execution
package. Then it asks Claude to use its own native subagent/task mechanism to
execute `PROJECT_DIR/execution_package/OPTIMIZER_EXECUTION_TASK.md`. After the
subagent returns, the supervisor runs closeout and reports the decision.

The historical C-64 `--execution-agent claude` subprocess route remains useful
as development acceptance evidence, but it is not the C-65 default product
target.
