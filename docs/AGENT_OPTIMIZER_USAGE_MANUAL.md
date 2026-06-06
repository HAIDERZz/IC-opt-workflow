# Agent Optimizer Usage Manual

This guide explains how a user should ask an agent to run an IC optimization
with `ic-auto-opt-workflow`.

Use this document when you want a supervisor agent to help you optimize a real
Virtuoso/Maestro/Spectre circuit.

## 1. What You Prepare

Create one project directory:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. `constraints.md` and `context/` are
optional but recommended.

Do not manually create these generated directories:

```text
config/
netlists/
runs/
reports/
ledger/
state/
execution_package/
```

Hermes creates them.

## 2. What Must Be In opt_requirement.md

`opt_requirement.md` is the machine-critical optimization request.

It must define:

- project identity;
- one or more Maestro/ADE point roots;
- design variables and legal ranges;
- OCEAN metric expressions;
- constraints;
- objective or FoM;
- Spectre settings;
- optimizer settings;
- approval checklist.

For each Maestro/ADE testbench, first run one known-good point in Maestro. Then
put the point-root path in `opt_requirement.md`.

The point root must contain:

```text
<maestro_point_root>/netlist/input.scs
```

For multi-testbench circuits, such as a mixer, define named testbenches:

```text
cg_nf -> CG / NF / BW
iip3  -> IIP3
p1db  -> P1dB
```

Each metric then declares which testbench should evaluate it.

## 3. What Goes In constraints.md

`constraints.md` is for human guidance to the supervisor agent.

Good examples:

- which metric matters most if tradeoffs appear;
- which variable ranges are physically suspicious;
- whether runtime or accuracy is more important;
- what result quality is acceptable for a first pass;
- notes about known bad bias regions or unstable simulations.

Do not put machine-critical formulas only in `constraints.md`. Formulas,
variable ranges, and resource settings belong in `opt_requirement.md`.

## 4. Give This Prompt To The Supervisor Agent

Use a request like this:

```text
Please run an IC optimizer workflow for:

PROJECT_DIR = /home/zzchen/spectre_opt_prj/<project_name>

Follow ic-auto-opt-workflow/docs/AGENT_OPTIMIZER_USAGE_MANUAL.md and
docs/OPTIMIZER_PRODUCTION_QUICKSTART.md.

Use opt_requirement.md as the source of truth.
Use constraints.md only as supervisor guidance.

Do not hand-pick optimizer points.
Do not rewrite OCEAN formulas.
Do not parse PSF in Python.
Do not merge multiple testbenches into one synthetic Spectre deck.
Do not commit raw Cadence netlists, PSF data, or full Cadence logs.

First run the intake/readiness checks.
If the project is ready, run the optimizer with the approved settings.
After the optimizer finishes, generate the decision report and final summary.
Stop and report if readiness fails, real-tool execution fails structurally, or
the final decision needs user approval.
```

## 5. Agent Step 1: Intake And Readiness

The agent should enter the repo:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Then run:

```bash
./.venv/bin/hermes-workflow check-requirement PROJECT_DIR
./.venv/bin/hermes-workflow prepare-from-requirement PROJECT_DIR
./.venv/bin/hermes-workflow validate PROJECT_DIR
./.venv/bin/hermes-workflow check-project-ready PROJECT_DIR
```

Expected state before the first optimizer run:

```text
project readiness: pass
readiness: ready_for_first_run
```

If this fails, the agent should stop and report the exact failing item.

Typical user-side fixes:

- wrong `maestro_point_root`;
- missing `netlist/input.scs`;
- duplicate variable names or duplicate YAML keys;
- metric routes point to unknown testbench ids;
- OCEAN formula or constraint names do not match declared metrics.

## 6. Agent Step 2: Run Optimizer

For OpenBox real optimization:

```bash
./.venv/bin/hermes-workflow run-openbox-real PROJECT_DIR \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

The exact values should come from `opt_requirement.md` unless the user
explicitly changes them.

Resource meanings:

- `parallel_jobs`: how many Spectre simulations may run at once.
- `threads_per_run`: Spectre `+mt` threads per simulation.
- `optimizer_cpu_threads`: Python/OpenBox optimizer CPU thread limit.

The agent should not replace this with manually selected candidate points.

## 7. Agent Step 3: Close Out The Run

After the optimizer run finishes, the agent should run:

```bash
./.venv/bin/hermes-workflow check-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow summarize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow visualize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow decide-optimizer-run PROJECT_DIR
```

Then the agent should read:

```text
PROJECT_DIR/reports/optimizer_decision_report.md
PROJECT_DIR/reports/optimizer_insight_report.md
```

The agent should tell the user:

- best observed candidate;
- parameter values;
- metric values;
- feasible / constraint_failed / metric_check_failed counts;
- bottleneck metric;
- whether the run should be accepted, continued, or sent back for user review;
- whether the result is only best observed.

## 8. User Decision Point

The supervisor agent should ask for user confirmation before recording the final
decision unless the user already gave explicit acceptance rules.

Common decisions:

```text
accept_best_observed
continue_more_evals
stop_for_user_review
change_constraints_or_fom
expand_search_space
```

If the user accepts the current result, run:

```bash
./.venv/bin/hermes-workflow record-optimizer-decision PROJECT_DIR \
  --decision accept_best_observed \
  --reason "User accepted the current best observed optimizer result."

./.venv/bin/hermes-workflow write-optimizer-final-summary PROJECT_DIR
./.venv/bin/hermes-workflow check-project-ready PROJECT_DIR
```

Expected final state:

```text
project readiness: pass
readiness: ready_for_closeout_review
```

## 9. What The User Reads

Primary final report:

```text
PROJECT_DIR/reports/optimizer_final_summary.md
```

Detailed reports:

```text
PROJECT_DIR/reports/optimizer_decision_report.md
PROJECT_DIR/reports/optimizer_insight_report.md
PROJECT_DIR/reports/project_readiness_report.json
```

Visual artifacts are usually under:

```text
PROJECT_DIR/reports/optimizer_visuals/
PROJECT_DIR/reports/openbox_advanced_visualization/
```

## 10. How To Continue Optimization

Only continue if the decision report or the user asks for it.

Example:

```bash
./.venv/bin/hermes-workflow continue-openbox-real PROJECT_DIR \
  --additional-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

Then rerun the closeout chain:

```bash
./.venv/bin/hermes-workflow check-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow summarize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow visualize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow decide-optimizer-run PROJECT_DIR
```

Do not restart from scratch unless the user changes variables, formulas,
constraints, objective, or Maestro point roots.

## 11. How To Interpret Failures

`constraint_failed` means:

```text
Spectre/OCEAN produced scalar metrics, but the candidate did not meet the
declared constraints.
```

This is usually a valid optimizer sample.

`metric_check_failed` means:

```text
The candidate ran far enough to reach metric extraction, but one or more
required metrics were missing, non-scalar, NaN, or invalid.
```

This may be a user formula issue, an invalid candidate region, or an expected
case where the circuit behavior makes the metric undefined.

`real_check_failed` means:

```text
The real tool result or manifest failed structurally.
```

This is usually a tool, environment, netlist, license, or execution problem.

Few or zero feasible points usually means:

- constraints are too strict;
- search space misses feasible regions;
- FoM or metric formula needs review;
- initial Maestro point roots and formulas do not match;
- optimizer budget is too small for the space.

## 12. Important Boundaries

The agent must keep these rules:

- The result is `best observed`, not global optimum.
- Use OpenBox/native optimizer candidate generation, not hand-picked points.
- Preserve each Maestro/ADE testbench bundle.
- Do not synthesize one combined Spectre deck for multiple testbenches.
- Do not parse PSF in Python.
- Do not rewrite approved OCEAN formulas.
- Do not change precision or parallel settings silently.
- Do not commit raw Cadence netlists, protected sidecars, PSF data, or full
  Cadence logs.

## 13. Minimal Successful Session

A successful first production session looks like:

```text
1. User creates PROJECT_DIR and writes opt_requirement.md.
2. Agent runs intake/readiness commands.
3. readiness=ready_for_first_run.
4. Agent runs run-openbox-real.
5. Agent runs closeout report chain.
6. Agent reports best observed result and bottleneck.
7. User accepts or asks to continue.
8. Agent records decision and writes optimizer_final_summary.md.
9. readiness=ready_for_closeout_review.
```

At that point, the user can use the accepted candidate as the current optimized
design point, while remembering it is not a mathematical global optimum proof.
