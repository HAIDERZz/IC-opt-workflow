# C-63 Claude `/ic-opt` Real Landing

Status: completed, verified-only

Date: 2026-06-07

## Goal

Make the first real agent-facing `/ic-opt PROJECT_DIR --real` entrypoint work
in Claude CLI and prove it with a fresh real Mixer multi-testbench run.

## Implementation

- Added `claude_skills/ic-opt/SKILL.md`.
- Added `claude_skills/README.md`.
- Installed the skill locally by linking it to `~/.claude/skills/ic-opt` for
  the acceptance run.

## Evidence

Evidence note:

```text
docs/CLAUDE_IC_OPT_REAL_LANDING_2026-06-07.md
```

Fresh project:

```text
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb
```

Initial files:

```text
cadence_env.csh
opt_requirement.md
```

Final command:

```bash
claude -p --dangerously-skip-permissions "/ic-opt /tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb --real"
```

Result:

- 100 real evaluations.
- 16 feasible, 68 constraint_failed, 16 metric_check_failed.
- Recommended feasible `real_051`.
- Flow summary from Claude CLI matched `optimizer_decision_report.md`.

## Boundary

This completes the first Claude CLI slash-skill product landing.

It does not complete automatic supervisor-agent to execution-agent dispatch.
The skill currently delegates to the implemented shell automation core from the
supervisor agent session.

## Next

Decide whether the product target remains:

1. single-agent slash skill + deterministic shell automation core; or
2. two-agent supervisor/execution dispatch with a separate execution-agent
   runner.

Do not add optimizer features until that product boundary is decided.
