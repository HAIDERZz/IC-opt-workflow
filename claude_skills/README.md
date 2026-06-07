# Claude Skills

This directory contains Claude Code skill entrypoints for the product-facing
agent UX.

## Install `/ic-opt`

From the repository root:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$PWD/claude_skills/ic-opt" ~/.claude/skills/ic-opt
```

Then a Claude CLI or Claude Code session can run:

```text
/ic-opt PROJECT_DIR --real
```

The skill delegates to the implemented product shell command:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

The current skill proves a first agent-facing slash entrypoint. It does not yet
prove automatic supervisor-agent to execution-agent dispatch; the skill runs
the product automation core from the supervisor agent session.
