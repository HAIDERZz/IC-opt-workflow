---
name: ic-opt
description: Operate IC Auto Opt Workflow from a project directory. Trigger when the user asks to run "/ic-opt PROJECT --doctor", "/ic-opt PROJECT --real", "/ic-opt PROJECT --continue M", or asks an agent to optimize a Spectre/Maestro/ADE IC project with ic-opt. The default path is one current agent running the deterministic ic-opt CLI and explaining reports; same-runtime subagent execution is optional only when explicitly requested.
---

# IC Auto Opt Agent Operator

Use this skill to operate `ic-opt` for a user. The product is a deterministic
CLI workflow; the agent is the operator and report interpreter.

Default route:

```text
User -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

Optional advanced route:

```text
User -> current agent -> same-runtime native subagent -> ic-opt CLI
```

Use the optional route only when the user explicitly asks for subagent execution
and the current runtime provides a native task/subagent tool.

## User Commands

Accept these forms:

```text
/ic-opt PROJECT --doctor
/ic-opt PROJECT --real [ic-opt flags]
/ic-opt PROJECT --continue M [ic-opt flags]
```

If the user gives only a project path and asks to optimize, use `--real`.
If the user says "add/run/continue M more points", use `--continue M`.
If the user asks to check readiness, use `--doctor`.

Do not ask the user to restate formulas, variables, metric routes, testbench
paths, Spectre resources, or optimizer settings. Those belong in
`PROJECT/opt_requirement.md` and optional `PROJECT/constraints.md`.

## Locate The CLI

Use the first available command:

```bash
"$IC_OPT_WORKFLOW_REPO/.venv/bin/ic-opt"
"$PWD/.venv/bin/ic-opt"        # when PWD is the workflow repo
ic-opt                         # when installed on PATH
```

If no command is available, tell the user to install IC Auto Opt Workflow or set
`IC_OPT_WORKFLOW_REPO`. Do not create a Python virtualenv inside the user
project directory.

## Default Flow

For doctor:

```bash
ic-opt PROJECT --doctor
```

Stop after doctor and report pass/fail plus the failing item if any.

For real optimization:

```bash
ic-opt PROJECT --real [user flags]
```

For continuation:

```bash
ic-opt PROJECT --continue M [user flags]
```

Do not translate continuation into a lower-level `hermes-workflow` command for
normal users. Do not restart from scratch unless the user changed variables,
constraints, objective, metric formulas, or Maestro point roots.

## Optional Subagent Mode

If the user explicitly requests native subagent execution:

1. Run the supervisor gate:

   ```bash
   ic-opt PROJECT --real [user flags] --dry-orchestration
   ```

   or for continuation:

   ```bash
   ic-opt PROJECT --continue M [user flags] --dry-orchestration
   ```

2. Dispatch the same-runtime native subagent, if available, with only:

   ```text
   Read PROJECT/execution_package/OPTIMIZER_EXECUTION_TASK.md and
   PROJECT/execution_package/optimizer_execution_manifest.json.
   Run only the approved command from the manifest. Do not hand-pick
   candidates, rewrite formulas, parse PSF, change resources, or invoke another
   CLI agent. Report command status and artifact paths.
   ```

3. The current agent remains responsible for closeout and explanation.

If native subagent support is unavailable, report that clearly and use the
default single-agent CLI route only if the user agrees or did not require a
subagent.

## Hard Boundaries

- Do not hand-pick candidate points.
- Do not rewrite OCEAN formulas.
- Do not parse PSF in Python.
- Do not hardcode a Spectre version.
- Do not create a per-project Python virtualenv.
- Do not silently change `parallel_jobs`, `threads_per_run`, precision, or FoM.
- Do not poll every optimizer batch; report start, unexpected failure,
  completion, and only low-frequency heartbeat status for long runs.
- Do not present failed candidates as the primary recommendation when feasible
  candidates exist.
- Do not claim global optimum. Say "best observed" unless there is an exhaustive
  proof.

## Report To User

After `--real` or `--continue`, read:

```text
PROJECT/reports/optimizer_decision_report.md
PROJECT/reports/optimizer_insight_report.md
```

Summarize only:

- whether the flow passed;
- evaluation count and status counts;
- recommended action and run id;
- recommended parameters and metrics;
- bottleneck and warnings;
- whether the result is best observed only;
- whether to accept, continue, inspect failures, revise constraints/FoM, or
  expand the search space;
- report paths.

If a step fails, report the failed step and relevant artifact path. Do not
continue by inventing candidates or editing formulas.
