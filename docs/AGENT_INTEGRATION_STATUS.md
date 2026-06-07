# Agent Integration Status

Date: 2026-06-07

This document fixes the current product-status boundary.

For the detailed Chinese explanation of the implemented automation path and the
remaining agent-product gap, read `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

## Current Implemented State

Implemented and real-tool validated:

- Shell/product CLI: `ic-opt PROJECT_DIR --real`.
- Claude CLI skill entrypoint, when installed:
  `/ic-opt PROJECT_DIR --real`.
- Lower-level CLI: `hermes-workflow optimize PROJECT_DIR --real`.
- File-based user input through `opt_requirement.md` plus optional
  `constraints.md`.
- Product-level Python environment through `requirements-product.txt`.
- Project-local or user-level Cadence cshrc anchor discovery.
- Real OpenBox/Spectre/OCEAN optimizer flow.
- Multi-testbench candidate evaluation and metric aggregation.
- Optimizer decision, insight, visualization, and final-summary reports.

C-60 real evidence:

```text
/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb
```

ran:

```bash
./.venv/bin/ic-opt PROJECT --real --max-evals 100 --batch-size 10 --parallel-jobs 10
```

without `--cadence-cshrc`, completed 100 real evaluations, and recommended
feasible `real_051`.

C-63 Claude CLI slash-skill evidence:

```text
docs/CLAUDE_IC_OPT_REAL_LANDING_2026-06-07.md
```

Fresh project:

```text
/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb
```

ran through Claude CLI:

```bash
claude -p --dangerously-skip-permissions "/ic-opt PROJECT --real"
```

after installing `claude_skills/ic-opt` into `~/.claude/skills/ic-opt`, completed
100 real evaluations, and recommended feasible `real_051`.

## Not Yet Implemented

Not implemented:

- Automatic supervisor-agent to execution-agent dispatch.
- A real slash command named `/ic-opt` in Codex or other non-Claude agent
  runtimes.
- A packaged installer that installs the Claude skill on a clean machine.
- A production handoff runner that proves the supervisor agent calls an
  execution agent rather than simply running the full CLI itself.

Therefore the current project is a working shell automation core plus a first
Claude CLI slash-skill entrypoint. It is not yet the final two-agent product.

## Current User Interaction

Current supported Claude interaction after installing `claude_skills/ic-opt`:

```text
User -> supervisor agent:
/ic-opt PROJECT_DIR --real
```

The Claude skill then runs the implemented shell command:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
./.venv/bin/ic-opt PROJECT_DIR --real
```

This proves the first agent-facing slash entrypoint. It still means the
supervisor agent is operating a CLI automation engine. It does not prove a
separate execution-agent handoff by itself.

## Target User Interaction

Target two-agent interaction, if the product keeps the two-agent architecture:

```text
User -> supervisor agent:
/ic-opt PROJECT_DIR --real

Supervisor agent:
validates request, prepares package, dispatches execution work, audits reports,
and returns only the final result summary or a user-decision question.

Execution agent:
runs approved real OpenBox/Spectre/OCEAN work from the generated package and
returns artifacts, without asking the user for formulas or hand-picking points.
```

The less the user needs to talk to the agent, the better.

## Required Next Product Work

Next product work should be C-64 or equivalent:

1. Decide whether the first public product target is single-agent slash skill
   plus deterministic shell automation, or two-agent supervisor/execution
   dispatch.
2. If two-agent remains required, define exactly how the supervisor invokes an
   execution agent, or explicitly
   decide that the product is a single-agent CLI operator instead.
3. Run a real end-to-end drill where the user gives only the short command and
   the supervisor/execution-agent boundary is observable.

Do not claim the two-agent product is complete until that drill passes.
