# Agent Integration Status

Date: 2026-06-07

This document fixes the current product-status boundary.

For the detailed Chinese explanation of the implemented automation path and the
remaining agent-product gap, read `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

## Current Implemented State

Implemented and real-tool validated:

- Shell/product CLI: `ic-opt PROJECT_DIR --real`.
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

## Not Yet Implemented

Not implemented:

- A real slash command named `/ic-opt` in Codex, Claude CLI, or another agent
  runtime.
- Automatic supervisor-agent to execution-agent dispatch.
- A local agent plugin/skill wrapper that lets the user type only
  `/ic-opt PROJECT_DIR --real` in the supervisor chat and then hides the repo
  path, command details, and handoff sequence.
- A production handoff runner that proves the supervisor agent calls an
  execution agent rather than simply running the full CLI itself.

Therefore the current project is not yet the final two-agent product. It is a
working optimization automation core plus documentation and task-package
contracts that can support agent orchestration.

## Current User Interaction

Current supported interaction is:

```text
User -> supervisor agent:
Run the ic-auto-opt workflow on PROJECT_DIR.
```

The supervisor agent then runs the implemented shell command:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
./.venv/bin/ic-opt PROJECT_DIR --real
```

This is useful, but it means the supervisor agent is operating a CLI automation
engine. It does not prove a two-agent product by itself.

## Target User Interaction

Target final interaction is:

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

Next product work should be C-63 or equivalent:

1. Choose the agent runtime target for the first real `/ic-opt` integration
   proof.
2. Add a small invocation wrapper or skill/plugin command that maps
   `/ic-opt PROJECT_DIR --real` to the repo `ic-opt` command.
3. Define exactly how the supervisor invokes an execution agent, or explicitly
   decide that the product is a single-agent CLI operator instead.
4. Run a real end-to-end drill where the user gives only the short command and
   the supervisor/execution-agent boundary is observable.

Do not claim the two-agent product is complete until that drill passes.
