# C-64 Observable Execution-Agent Handoff Design

Status: implemented and verified-only

Date: 2026-06-07

## Goal

Make `/ic-opt PROJECT_DIR --real` prove an observable supervisor-agent to
independent execution-agent handoff, instead of only running the full optimizer
inside the supervisor agent process.

## Current Problem

C-63 proves this chain:

```text
User short command
-> Claude CLI /ic-opt skill
-> repo ic-opt shell automation core
-> real OpenBox/Spectre/OCEAN flow
-> report summary
```

The missing product boundary is here:

```text
package-optimizer-task
-> independent execution agent
-> supervisor-side audit
```

The existing `optimizer_flow.optimize_project()` creates the optimizer task
package but then directly calls `run_openbox_real_optimization()` in the same
Python process. That is correct for shell automation and debugging, but it does
not prove a separate execution-agent handoff.

## Design

Add one optional execution mode:

```text
direct
claude
```

`direct` preserves the current behavior.

`claude` changes only the step after `package-optimizer-task`:

```text
supervisor ic-opt
-> package/preflight/approval
-> package-optimizer-task
-> spawn independent Claude CLI execution-agent process
-> execution agent reads OPTIMIZER_EXECUTION_TASK.md
-> execution agent runs exactly the task command and audit commands
-> supervisor ic-opt resumes and runs its own closeout checks
```

The Claude execution agent receives a compact, deterministic prompt. It must not
ask the user to restate formulas, hand-pick points, rewrite OCEAN formulas,
parse PSF, or run `/ic-opt` recursively. It must execute the generated task
package command.

## Reports

The supervisor writes:

```text
reports/execution_agent_handoff_report.json
reports/execution_agent_handoff_transcript.txt
```

The JSON report includes:

- schema version;
- project directory;
- task path;
- manifest path;
- execution agent kind;
- command argv used to launch the agent;
- transcript path;
- exit code;
- started and finished timestamps;
- status;
- issues.

The transcript contains the execution-agent stdout and stderr.

## Product CLI

Add:

```bash
ic-opt PROJECT_DIR --real --execution-agent direct
ic-opt PROJECT_DIR --real --execution-agent claude
```

Default shell behavior remains `direct`.

The Claude CLI `/ic-opt` skill should pass `--execution-agent claude` by
default, so the product-shaped agent entry proves handoff unless the user
explicitly chooses otherwise.

## Non-Goals

- Do not add a daemon, database, queue, or workflow engine.
- Do not change OpenBox, TuRBO, Spectre, OCEAN, formulas, PSF handling, or
  multi-testbench aggregation.
- Do not implement Codex or non-Claude slash adapters in this step.
- Do not make final user acceptance automatic.
- Do not use fake optimizer runs as final acceptance.

## Acceptance

The final acceptance drill must use a fresh real project and one short user
command:

```text
/ic-opt PROJECT_DIR --real
```

Expected evidence:

- `reports/execution_agent_handoff_report.json` exists and has `status=pass`;
- transcript proves a separate Claude CLI execution-agent process ran;
- optimizer flow completes 100 real evaluations;
- supervisor closeout reports recommend a feasible best-observed run or stop
  for user review;
- global optimum is not claimed.

## Implementation Evidence

Evidence note:

```text
docs/CLAUDE_EXECUTION_AGENT_HANDOFF_2026-06-07.md
```

Fresh project:

```text
/tmp/ic_auto_opt_c64_handoff_zX9JrO/Mixer_opt_muti_tb
```

The one-line Claude command completed the handoff and real optimizer run:

```bash
claude -p --dangerously-skip-permissions "/ic-opt PROJECT --real"
```

Observed result:

- `reports/execution_agent_handoff_report.json`: `status=pass`,
  `execution_agent=claude`, `returncode=0`;
- `reports/optimizer_flow_run_report.json`: `status=pass`,
  `execution_agent=claude`, `handoff_report_path` present;
- 100 real OpenBox/Spectre/OCEAN evaluations;
- recommended feasible `real_051`;
- `global_optimum_claim=false`.
