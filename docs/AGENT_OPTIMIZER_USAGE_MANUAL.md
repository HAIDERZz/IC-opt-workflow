# Agent Optimizer Usage Manual

This guide explains how an AI agent should operate IC Auto Opt Workflow for a
real Spectre/Maestro/ADE optimization project.

Current product position:

- `ic-opt` is the deterministic automation core.
- A human can run `ic-opt` directly.
- An agent can run `ic-opt` for the user, wait for completion, read reports, and
  explain the result.
- Native subagent execution is optional advanced behavior, not the default
  product route.

Default model:

```text
User -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

Optional model:

```text
User -> current agent -> same-runtime native subagent -> ic-opt CLI
```

Do not make the normal workflow depend on one agent CLI launching another agent
CLI.

## 1. What The User Prepares

The user creates one project directory:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. `constraints.md` and `context/` are
optional guidance.

Do not manually create generated directories such as:

```text
config/
netlists/
runs/
reports/
ledger/
state/
execution_package/
```

`ic-opt` creates them.

## 2. What Must Be In opt_requirement.md

`opt_requirement.md` is the machine-critical optimization request. It defines:

- project identity;
- one or more Maestro/ADE point roots;
- design variables and legal ranges;
- OCEAN metric expressions;
- constraints;
- FoM/objective;
- Spectre settings;
- optimizer settings;
- approval checklist.

The agent must not ask the user to restate this information in chat.

For each Maestro/ADE testbench, the user should first run one known-good point
in Maestro/ADE. The `maestro_point_root` must be the leaf run directory that
contains:

```text
<maestro_point_root>/netlist/input.scs
```

Usually it also contains:

```text
netlist/
psf/
```

## 3. Locate The ic-opt Command

Use the first available command:

```bash
"$IC_OPT_WORKFLOW_REPO/.venv/bin/ic-opt"
"$PWD/.venv/bin/ic-opt"        # when PWD is the workflow repo
ic-opt                         # when installed on PATH
```

If no command is available, ask the user to install IC Auto Opt Workflow or set
`IC_OPT_WORKFLOW_REPO`.

Do not create a Python virtualenv inside the user project directory. The
workflow uses one product-level Python environment.

## 4. Normal Agent Commands

Doctor/readiness check:

```bash
ic-opt PROJECT_DIR --doctor
```

First real optimization:

```bash
ic-opt PROJECT_DIR --real
```

Continuation:

```bash
ic-opt PROJECT_DIR --continue M
```

If the user says "optimize this project" and provides a project path, use
`--real`. If the user asks to "run 40 more points", use `--continue 40`.

Do not expose lower-level `hermes-workflow` commands to normal users unless
debugging the product command.

## 5. Doctor Mode

Run:

```bash
ic-opt PROJECT_DIR --doctor
```

Stop after doctor. Report pass/fail and the failing item. Doctor mode should
not start Spectre/OCEAN.

Common user-side fixes:

- wrong `maestro_point_root`;
- missing `netlist/input.scs`;
- invalid `opt_requirement.md` section format;
- duplicate variable names or duplicate YAML keys;
- metric routes point to unknown testbench ids;
- OCEAN formula names do not match declared metrics;
- Cadence environment path is missing.

## 6. Real Optimization Mode

Run:

```bash
ic-opt PROJECT_DIR --real
```

The product command handles:

- requirement intake;
- config rendering;
- Maestro/ADE point-root import;
- package/preflight/approval gates;
- OpenBox optimization;
- Spectre/OCEAN execution;
- metric extraction;
- optimizer closeout;
- decision and insight reports.

The agent should not rebuild this flow manually unless debugging.

## 7. Continuation Mode

Run:

```bash
ic-opt PROJECT_DIR --continue M
```

Continuation adds M more evaluations to the existing optimizer history. Do not
restart from scratch unless the user changed variables, formulas, constraints,
objective, or Maestro point roots.

Do not add `--parallel-jobs` during continuation unless the user explicitly asks
to change resources. Mixed resource settings can invalidate history audits.

## 8. Optional Native Subagent Mode

Use native subagent execution only when the user explicitly asks for it and the
current agent runtime provides a stable native task/subagent tool.

For optional subagent mode:

1. Run dry orchestration:

   ```bash
   ic-opt PROJECT_DIR --real --dry-orchestration
   ```

   or:

   ```bash
   ic-opt PROJECT_DIR --continue M --dry-orchestration
   ```

2. Dispatch the same-runtime native subagent with only:

   ```text
   Read PROJECT_DIR/execution_package/OPTIMIZER_EXECUTION_TASK.md and
   PROJECT_DIR/execution_package/optimizer_execution_manifest.json.
   Run only the approved command from the manifest. Do not hand-pick candidates,
   rewrite formulas, parse PSF, change resource settings, or invoke another CLI
   agent. Report command status and artifact paths.
   ```

3. The supervisor/current agent reads reports and explains the result.

If subagent dispatch is unavailable, report that clearly and use the default
single-agent CLI route only if the user agrees or did not require subagent mode.

## 9. What To Read After A Run

Primary reports:

```text
PROJECT_DIR/reports/optimizer_decision_report.md
PROJECT_DIR/reports/optimizer_insight_report.md
```

Other useful artifacts:

```text
PROJECT_DIR/reports/optimizer_final_summary.md
PROJECT_DIR/reports/project_readiness_report.json
PROJECT_DIR/reports/optimizer_visuals/
PROJECT_DIR/reports/openbox_advanced_visualization/
```

## 10. What To Tell The User

Report concisely:

- whether the flow passed;
- evaluation count and status counts;
- best observed feasible run id;
- recommended action;
- recommended parameters;
- key metrics;
- bottleneck and warnings;
- whether the result is best observed only;
- whether to accept, continue, inspect failures, revise constraints/FoM, or
  expand the search space;
- report paths.

Do not claim a global optimum unless the run was an exhaustive sweep with proof.

## 11. User Decision Point

Common user decisions:

```text
accept_best_observed
continue_more_evals
stop_for_user_review
change_constraints_or_fom
expand_search_space
```

If the user asks to continue, run:

```bash
ic-opt PROJECT_DIR --continue M
```

If the user accepts the current result, the agent may record final acceptance
only after explicit user confirmation.

## 12. Failure Interpretation

`constraint_failed`:

```text
Spectre/OCEAN produced scalar metrics, but the candidate did not meet declared
constraints.
```

This is usually a valid optimizer sample.

`metric_check_failed`:

```text
The candidate reached metric extraction, but one or more metrics were missing,
non-scalar, NaN, or invalid.
```

This may be a formula issue, invalid candidate region, or expected undefined
behavior.

`real_check_failed`:

```text
The real tool result or manifest failed structurally.
```

This usually points to environment, license, netlist, tool, or execution
problems.

## 13. Hard Agent Boundaries

The agent must not:

- hand-pick optimizer candidates;
- rewrite approved OCEAN formulas;
- parse PSF in Python;
- hardcode Spectre versions;
- create per-project Python virtualenvs;
- silently change precision, `threads_per_run`, `parallel_jobs`, or FoM;
- poll every optimizer batch;
- recommend failed candidates as primary results when feasible candidates exist;
- commit raw Cadence netlists, PSF data, protected sidecars, or full Cadence
  logs;
- claim global optimum.

## 14. Minimal Successful Session

```text
1. User creates PROJECT_DIR and writes opt_requirement.md.
2. User sends /ic-opt PROJECT_DIR --real.
3. Agent runs ic-opt PROJECT_DIR --real.
4. Agent waits for completion.
5. Agent reads optimizer_decision_report.md and optimizer_insight_report.md.
6. Agent reports best observed feasible result and next action.
7. User accepts or asks to continue.
```

This is the product skill target: the agent uses the workflow tool well instead
of trying to become the workflow.
