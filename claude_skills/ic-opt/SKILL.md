---
name: ic-opt
description: Run the IC Auto Opt real optimization workflow from a strict opt_requirement.md project. Trigger when the user enters "/ic-opt PROJECT_DIR --real". This skill runs the implemented ic-opt shell product command, reads optimizer reports, and reports the result without hand-picking candidates or asking for formula details.
---

# IC Auto Opt Product Entrypoint

This skill IS the user-facing entrypoint. Execute immediately; do not write a
plan first and do not ask the user to restate the requirement.

User command:

```text
/ic-opt PROJECT_DIR --real [optional ic-opt flags]
```

`PROJECT_DIR` must contain `opt_requirement.md` and a user-supplied Cadence env
anchor discoverable by the product CLI, usually `PROJECT_DIR/cadence_env.csh`.

## Hard Boundaries

- Run a real workflow. Do not run fake or mock optimizer commands.
- Do not hand-pick candidate points.
- Do not rewrite OCEAN formulas.
- Do not parse PSF in Python.
- Do not hardcode a Spectre version in the prompt or command.
- Do not create a per-project Python virtualenv.
- Do not automatically accept the final candidate for the user.
- Do not poll after every optimizer batch; let the product command run.

## Argument Parsing

Parse `$ARGUMENTS` as:

```bash
PROJECT_DIR="${ARGUMENTS%% --*}"
PROJECT_DIR="$(echo "$PROJECT_DIR" | xargs)"
FLAGS="${ARGUMENTS#"$PROJECT_DIR"}"
FLAGS="$(echo "$FLAGS" | xargs)"
```

If `PROJECT_DIR` is empty, fail with a short message asking for:

```text
/ic-opt PROJECT_DIR --real
```

If `FLAGS` does not contain `--real`, append `--real`.

## Locate The Workflow Repo

Use the first path that contains executable `.venv/bin/ic-opt`:

```bash
if [ -x "${IC_OPT_WORKFLOW_REPO:-}/.venv/bin/ic-opt" ]; then
  REPO="${IC_OPT_WORKFLOW_REPO}"
elif [ -x "$PWD/.venv/bin/ic-opt" ] && [ -f "$PWD/pyproject.toml" ]; then
  REPO="$PWD"
elif [ -x "/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/ic-opt" ]; then
  REPO="/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow"
else
  echo "ic-auto-opt-workflow product environment not found. Set IC_OPT_WORKFLOW_REPO."
  exit 1
fi
```

## Run

Run exactly one product command:

```bash
cd "$REPO"
"$REPO/.venv/bin/ic-opt" "$PROJECT_DIR" $FLAGS
```

This command owns markdown intake, YAML generation, Maestro point-root import,
contract validation, package/preflight/approval, real OpenBox/Spectre/OCEAN
optimization, artifact checks, visualization, and decision reporting.

## Report

After the command exits successfully, read:

```text
PROJECT_DIR/reports/optimizer_decision_report.md
PROJECT_DIR/reports/optimizer_flow_run_report.json
```

Report only:

- whether the flow passed;
- evaluation count and status counts;
- recommended run id and action;
- recommended parameters and metrics;
- global optimum claim;
- warnings or user decision required;
- report paths.

If the command fails, report the failed flow step and the relevant report path.
Do not continue by running lower-level commands unless the failure message
explicitly tells you to do so.
