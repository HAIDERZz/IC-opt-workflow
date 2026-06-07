# Agent Integration Status

Date: 2026-06-07

This document fixes the current product-status boundary.

## Product Model After C-65

The target user interaction is:

```text
User -> current agent CLI supervisor -> same-runtime execution subagent
```

Examples:

- In Claude, the current Claude conversation is the supervisor and should use a
  Claude-native subagent/task for execution.
- In OpenCode, the current OpenCode primary agent is the supervisor and should
  use an OpenCode subagent for execution.

The product should not require OpenCode/Codex/HermesAgent to launch `claude -p`
as the execution agent. Cross-CLI execution can remain a development fallback,
but it is not the default landing shape.

## Implemented Core

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

The shell route is deterministic automation. It is useful for operators,
debugging, and as the core that runtime-native agents wrap.

## Runtime Adapter Assets

Implemented by C-65:

- Claude adapter source: `claude_skills/ic-opt/`.
- OpenCode adapter source:
  - `agent_runtime/opencode/command/ic-opt.md`;
  - `agent_runtime/opencode/agents/ic-opt-execution.md`.
- Installer/check commands:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
./.venv/bin/hermes-workflow install-runtime-adapter opencode
./.venv/bin/hermes-workflow runtime-adapter-status
```

After installing an adapter, the intended user command is:

```text
/ic-opt PROJECT_DIR --real
```

The adapter instructs the current runtime supervisor to:

1. run the supervisor preparation gate with `--dry-orchestration`;
2. dispatch the runtime-native execution subagent to run the generated
   `OPTIMIZER_EXECUTION_TASK.md`;
3. run supervisor closeout;
4. report the decision.

## Real Evidence

C-60 real shell evidence:

```text
/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb
```

ran:

```bash
./.venv/bin/ic-opt PROJECT --real --max-evals 100 --batch-size 10 --parallel-jobs 10
```

without `--cadence-cshrc`, completed 100 real evaluations, and recommended
feasible `real_051`.

C-63 Claude slash-skill evidence:

```text
docs/CLAUDE_IC_OPT_REAL_LANDING_2026-06-07.md
```

proved a short Claude `/ic-opt PROJECT --real` entrypoint could run the real
automation core on a fresh project and recommend feasible `real_051`.

C-64 Claude subprocess handoff evidence:

```text
docs/CLAUDE_EXECUTION_AGENT_HANDOFF_2026-06-07.md
```

proved that the generated optimizer package can be executed by an independent
Claude CLI process and then closed out by the supervisor-side flow. This is
valuable acceptance evidence, but after C-65 it is classified as a
development/acceptance route rather than the default product target.

C-66 Claude continuation validation:

```text
docs/CLAUDE_IC_OPT_CONTINUATION_VALIDATION_2026-06-07.md
```

proved that a fresh Claude `/ic-opt PROJECT --real` run can complete 100 real
OpenBox/Spectre/OCEAN evaluations and that the follow-up short request
`请再进行40个点的优化` is routed to `continue-openbox-real --additional-evals
40`. The continuation did not append evaluations because OpenBox could not fill
the requested unique candidate batch after the prior 100-evaluation run.

## Not Yet Fully Proven

Still requiring a live runtime drill before claiming full support:

- Claude native subagent/task execution of the C-65 skill in the target user's
  actual Claude environment.
- OpenCode native subagent execution of the C-65 command/agent assets.
- Codex/OpenClaw/HermesAgent adapters.
- Packaged release installer beyond the repo-local
  `install-runtime-adapter` command.
- Product-ready continuation after a prior run when OpenBox cannot fill the
  requested unique candidate batch.
- Automatic final user acceptance.

## User Boundary

The less the user needs to talk to the agent, the better.

The user should prepare:

```text
PROJECT_DIR/opt_requirement.md
PROJECT_DIR/cadence_env.csh or ~/.ic-opt/cadence_env.csh
```

Then the user should say only:

```text
/ic-opt PROJECT_DIR --real
```

The supervisor agent should not ask for formulas, variables, testbench paths,
or optimizer settings already present in `opt_requirement.md`.
