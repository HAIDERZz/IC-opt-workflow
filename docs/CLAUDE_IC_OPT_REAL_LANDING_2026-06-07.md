# Claude `/ic-opt` Real Landing Evidence 2026-06-07

Status: passed

## Goal

Validate a real agent-facing entrypoint with Claude CLI:

```text
/ic-opt PROJECT_DIR --real
```

The validation must not use fake runs and must not reuse an already-generated
project.

## Fresh Project

Project:

```text
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb
```

Initial files before the run:

```text
cadence_env.csh
opt_requirement.md
```

No `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, or `state/` were
pre-copied.

## First Attempt

Command:

```bash
claude -p "/ic-opt /tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb --real"
```

Result:

```text
Unknown command: /ic-opt
```

Root cause:

Claude CLI had no installed `ic-opt` skill or command.

## Fix

Added product skill source:

```text
claude_skills/ic-opt/SKILL.md
```

Installed locally for the test:

```bash
ln -sfn /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/claude_skills/ic-opt /home/zzchen/.claude/skills/ic-opt
```

## Real Run

Command:

```bash
claude -p --dangerously-skip-permissions "/ic-opt /tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb --real"
```

The permission bypass was used only to let the non-interactive Claude CLI run
the product shell command and real EDA tools without prompts during this local
acceptance drill.

## Result

Claude CLI completed the real flow and reported:

- Flow status: all 16 steps passed.
- Evaluations: 100.
- Status counts: 16 feasible, 68 constraint_failed, 16 metric_check_failed.
- Recommended run: `real_051`.
- Recommended action: `accept_best_observed_or_continue`.
- Recommended parameters: `F=30`, `L=40n`, `VB_LO=310m`, `W=0.8u`.
- Recommended metrics:
  - `BW=19.59 GHz`
  - `IIP3=3.28 dBm`
  - `MAX_GAIN=4.03 dB`
  - `NF_3G=11.80 dB`
  - `P1DB=-0.87 dBm`
- Bottleneck: `MAX_GAIN`.
- Global optimum claim: no.
- Warning: configured objective best candidate `real_057` was
  `constraint_failed` and was ignored as the primary recommendation.

Reports:

```text
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb/reports/optimizer_flow_run_report.json
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb/reports/optimizer_decision_report.md
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb/reports/openbox_advanced_visualization/history/hermes_openbox_real/
```

## Boundary

This proves the first Claude CLI slash-skill landing:

```text
User short command -> Claude CLI `/ic-opt` skill -> repo `ic-opt` shell product
command -> real OpenBox/Spectre/OCEAN flow -> report summary
```

This does not prove automatic supervisor-agent to execution-agent dispatch.
The current `/ic-opt` skill runs the product automation core from the supervisor
agent session. A separate execution-agent handoff remains future work unless
the product is intentionally scoped as a single-agent CLI operator.
