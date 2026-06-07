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

The skill delegates to the implemented product shell command and appends
`--execution-agent claude` by default:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --execution-agent claude
```

The current skill proves the Claude runtime slash entrypoint plus observable
supervisor-agent to independent Claude CLI execution-agent handoff. Shell
`ic-opt` remains `--execution-agent direct` by default for operator/debug use.
Codex and other non-Claude runtimes still need their own adapters.
