---
name: ic-opt
description: Operate IC Auto Opt Workflow from a project directory. Trigger when the user asks to run "/ic-opt PROJECT --doctor", "/ic-opt PROJECT --real", "/ic-opt PROJECT --continue M", "/ic-opt --ssh-profile PROFILE PROJECT --real", or asks an agent to optimize a Spectre/Maestro/ADE IC project with ic-opt. The default path is one current agent running the deterministic ic-opt CLI and explaining reports; same-runtime subagent execution is optional only when explicitly requested.
---

# IC Auto Opt Agent Operator

Use this skill to operate `ic-opt` for a user. The product is a deterministic
CLI workflow; the agent is the operator and report interpreter.

This skill is platform-neutral. It can be used by any agent runtime that can run
shell commands and read files.

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
/ic-opt --ssh-profile PROFILE REMOTE_PROJECT --doctor
/ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real [ic-opt flags]
/ic-opt --ssh-profile PROFILE REMOTE_PROJECT --continue M [ic-opt flags]
```

If the user gives only a project path and asks to optimize, use `--real`.
If the user says "add/run/continue M more points", use `--continue M`.
If the user asks to check readiness, use `--doctor`.
If the user says the project is on a remote EDA server, use remote mode with
`--ssh-profile PROFILE`. `PROFILE` is any OpenSSH target the local machine can
use, preferably a `~/.ssh/config` alias such as `eda-lab`. If the SSH profile is
missing, ask only for the profile name. Do not collect passwords. Tell the user
to configure passwordless SSH, accept the host key once with `ssh PROFILE true`,
and verify `ssh -o BatchMode=yes PROFILE true`.

Do not ask the user to restate formulas, variables, metric routes, testbench
paths, Spectre resources, or optimizer settings. Those belong in
`PROJECT/opt_requirement.md` and optional `PROJECT/constraints.md`.

## Mandatory Preflight Gate

Before any fresh `--real` run, run doctor first unless the user explicitly says
doctor already passed for the same unchanged project:

```bash
ic-opt PROJECT --doctor
```

For remote projects:

```bash
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --doctor
```

Treat doctor as the structured requirement and project-folder check. It catches
common `opt_requirement.md` mistakes, missing Maestro/ADE point roots, missing
`cadence_env.csh`, broken SSH readiness, and generated-config errors before
real Spectre/OCEAN work starts.

If doctor fails:

- stop before `--real`;
- report the failing item and the exact file/path involved;
- tell the user what to fix in `opt_requirement.md`, `constraints.md`,
  `cadence_env.csh`, SSH, or Maestro/ADE point roots;
- do not silently rewrite OCEAN formulas, variable ranges, FoM, or resource
  settings.

For continuation, doctor is optional when the existing run history is already
accepted and the user only asks to add points. Run doctor again if the user
changed variables, constraints, FoM, metric formulas, testbench paths, or remote
profile.

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
ic-opt PROJECT --doctor
ic-opt PROJECT --real [user flags]
```

For continuation:

```bash
ic-opt PROJECT --continue M [user flags]
```

For remote projects:

```bash
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --doctor
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real [user flags]
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --continue M [user flags]
```

In remote mode, `REMOTE_PROJECT` is the project directory on the Linux EDA
server. Do not copy the project locally unless the user explicitly requests a
backup. Do not install this Python package, OpenBox, or a virtualenv on the EDA
server. The local CLI mirrors reports under
`~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/` and also uploads
reports back to `REMOTE_PROJECT/reports/`.
Before a remote real run, prefer `ic-opt --ssh-profile PROFILE REMOTE_PROJECT
--doctor`. If SSH fails, report the exact SSH readiness command the user should
fix first instead of changing optimizer settings.

Remote parallelism guidance:

- `parallel_jobs` is candidate-level concurrency, not per-testbench concurrency.
- Multi-testbench candidates run their configured testbenches inside each
  candidate; increasing `parallel_jobs` multiplies total remote tool pressure.
- For normal remote multi-testbench use, prefer conservative values such as
  `--parallel-jobs 4` to `--parallel-jobs 8`.
- High values such as 24 or 36 can trigger SSH server limits, for example
  `kex_exchange_identification: Connection closed by remote host`. Treat those
  as remote transport/tool failures, not circuit-performance failures.
- `optimizer_cpu_threads` limits optimizer-side Python/OpenBox CPU use; it does
  not limit Spectre/OCEAN process count or SSH connection count.

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
- In remote mode, do not install Python packages on the remote EDA server.
- Do not silently change `parallel_jobs`, `threads_per_run`, precision, or FoM.
- Do not skip doctor before a fresh real run on a new or changed project.
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

For remote mode, prefer the local mirrored report path printed by `ic-opt`.
If the local mirror is unavailable, read the same files under
`REMOTE_PROJECT/reports/` through SSH.

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

## Common Error Triage

Use `docs/TROUBLESHOOTING_CN.md` for the full table. The short rules are:

- `opt_requirement.md` parse/validation failure: run `--doctor`, point the user
  to the exact section/key, and stop before real tools.
- `maestro_point_root` errors: the path must be the leaf Maestro/ADE run
  directory containing `netlist/input.scs` and `psf/`.
- OCEAN metric `non_scalar` or non-finite scalar: the formula returned a
  waveform/list/undefined value for that candidate; ask the user to fix the
  OCEAN scalar expression or metric definition.
- `Host key verification failed`: ask the user to run `ssh PROFILE true` once
  and accept the correct host key.
- `Permission denied` or BatchMode SSH failure: passwordless SSH is not ready;
  ask the user to fix `authorized_keys` or `~/.ssh/config`.
- `kex_exchange_identification` / remote SSH connection closed under high
  parallelism: lower `parallel_jobs` to 4-8 for normal remote runs.
- `result_manifest.json missing`: with current versions this should not happen
  for handled tool/SSH failures. If it appears, tell the user to update the
  package and preserve the run directory for debugging.
