---
name: ic-opt
description: Run IC Auto Opt from a strict opt_requirement.md project. Trigger when the user enters "/ic-opt PROJECT_DIR --real". The current Claude runtime acts as supervisor and delegates real execution to a native Claude subagent/task when available.
---

# IC Auto Opt Runtime-Native Entrypoint

This skill is the Claude-facing `/ic-opt` entrypoint.

User command:

```text
/ic-opt PROJECT_DIR --real [optional ic-opt flags]
```

The user should not need to write a long prompt. Machine-critical setup belongs
in `PROJECT_DIR/opt_requirement.md`, and optional human guidance belongs in
`PROJECT_DIR/constraints.md`.

## Hard Boundaries

- Use the current Claude runtime as supervisor.
- Delegate the real optimizer execution to a native Claude subagent/task when
  that tool is available.
- Do not launch another `claude -p` process as the product execution agent.
- Do not hand-pick candidate points.
- Do not rewrite OCEAN formulas.
- Do not parse PSF in Python.
- Do not hardcode a Spectre version.
- Do not create a per-project Python virtualenv.
- Do not automatically record final user acceptance.
- Do not poll after every optimizer batch.

## Parse Arguments

Parse `$ARGUMENTS` as:

```text
PROJECT_DIR --real [optional ic-opt flags]
```

If `PROJECT_DIR` is empty, stop and ask for:

```text
/ic-opt PROJECT_DIR --real
```

If flags do not include `--real`, append `--real`.

Do not append `--execution-agent claude`. The historical C-64 subprocess route
is a development/acceptance fallback, not the C-65 product default.

## Locate The Workflow Repo

Use the first path that contains executable `.venv/bin/ic-opt`:

```bash
if [ -x "${IC_OPT_WORKFLOW_REPO:-}/.venv/bin/ic-opt" ]; then
  REPO="${IC_OPT_WORKFLOW_REPO}"
elif [ -x "$PWD/.venv/bin/ic-opt" ] && [ -f "$PWD/pyproject.toml" ]; then
  REPO="$PWD"
else
  echo "ic-auto-opt-workflow product environment not found. Set IC_OPT_WORKFLOW_REPO."
  exit 1
fi
```

## Supervisor Gate

Run the deterministic supervisor preparation gate:

```bash
cd "$REPO"
"$REPO/.venv/bin/ic-opt" "$PROJECT_DIR" $FLAGS --dry-orchestration
```

This reads `opt_requirement.md`, generates YAML/config, imports Maestro point
roots, validates contracts, packages/preflights/approves the run, and writes:

```text
PROJECT_DIR/execution_package/OPTIMIZER_EXECUTION_TASK.md
PROJECT_DIR/execution_package/optimizer_execution_manifest.json
```

If the user explicitly included `--dry-orchestration`, stop here and report the
supervisor gate result. Do not dispatch the execution subagent for a dry
orchestration check.

## Native Execution Subagent

After the supervisor gate passes, use Claude's native subagent/task mechanism.
Give the execution subagent only this scoped task:

```text
You are the IC Auto Opt execution agent.

Repo: REPO
Project: PROJECT_DIR

Read PROJECT_DIR/execution_package/OPTIMIZER_EXECUTION_TASK.md and
PROJECT_DIR/execution_package/optimizer_execution_manifest.json.

Run only the approved optimizer command from the manifest, from REPO, with
REPO/.venv/bin first in PATH. Use the Cadence setup path recorded in the
manifest. Do not hand-pick candidates. Do not rewrite formulas. Do not parse
PSF. Do not invoke another CLI agent. Report command status and artifact paths
back to the supervisor.
```

If the native subagent/task tool is unavailable or denied, stop and report:

```text
Runtime-native execution subagent dispatch is unavailable in this Claude
session. Direct shell ic-opt can run the automation core, but that is not the
two-agent product route.
```

## Supervisor Closeout

After the execution subagent reports completion, run the closeout chain from
`REPO`:

```bash
"$REPO/.venv/bin/hermes-workflow" check-optimizer-run "$PROJECT_DIR"
"$REPO/.venv/bin/hermes-workflow" summarize-optimizer-run "$PROJECT_DIR"
"$REPO/.venv/bin/hermes-workflow" finalize-optimizer-run "$PROJECT_DIR"
"$REPO/.venv/bin/hermes-workflow" visualize-optimizer-run "$PROJECT_DIR"
"$REPO/.venv/bin/hermes-workflow" decide-optimizer-run "$PROJECT_DIR"
```

## Report

Read:

```text
PROJECT_DIR/reports/optimizer_decision_report.md
PROJECT_DIR/reports/optimizer_insight_report.md
```

Report only:

- whether the flow passed;
- evaluation count and status counts;
- recommended run id and action;
- recommended parameters and metrics;
- global optimum claim;
- bottleneck and warnings;
- user decision required;
- report paths.

If any step fails, report the failed step and the relevant report path. Do not
continue by manually selecting candidates or changing formulas.
