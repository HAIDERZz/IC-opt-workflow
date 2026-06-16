# Agent Optimizer Usage Manual

This guide explains how a user should ask an agent to run an IC optimization
with `ic-auto-opt-workflow`.

Use this document when you want a supervisor agent to help you optimize a real
Virtuoso/Maestro/Spectre circuit.

Current implementation boundary after C-65:

- Implemented: shell command `ic-opt PROJECT_DIR --real`.
- Implemented: Claude and OpenCode runtime adapter assets for
  `/ic-opt PROJECT_DIR --real`.
- Implemented: Hermes workflow task packages and execution-agent instructions.
- Implemented: repo-local installer command
  `hermes-workflow install-runtime-adapter`.
- Historical evidence: C-64 proved a Claude subprocess handoff through
  `--execution-agent claude`; this is not the C-65 default product target.
- Not implemented: Codex/OpenClaw/HermesAgent adapters and a public packaged
  installer.

Read `docs/AGENT_INTEGRATION_STATUS.md` before claiming the two-agent product
itself is complete. Read `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md` for the
detailed Chinese explanation of what the current `ic-opt` automation actually
does and what agent integration remains missing.

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

`opt_requirement.md` is also the only product entry for runtime and optimizer
resource settings: `max_evaluations`, `batch_size`, `parallel_jobs`,
`threads_per_run`, `optimizer_cpu_threads`, strategy, initialization, output
format, retention policy, and process corners. The agent must not ask the user
to put these values in the chat prompt or append CLI overrides such as
`--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads`, or `--strategy`.
Product continuation may use only `ic-opt PROJECT_DIR --real --continue N`;
all other values stay inherited from `opt_requirement.md` / generated config.

Multi-corner optimization is configured in `Process Corners` inside
`opt_requirement.md`; use
`examples/spectre_maestro_project/opt_requirement.multi_corner.md` or
`examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md` as the
release examples.

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

## 4. Current Product Invocation

The implemented product command is the shell CLI:

```text
ic-opt /home/zzchen/spectre_opt_prj/<project_name> --real
```

The implemented runtime-native product-shaped agent request is:

```text
/ic-opt /home/zzchen/spectre_opt_prj/<project_name> --real
```

after installing the matching runtime adapter. The current agent CLI should act
as supervisor and use its own native subagent/task mechanism for execution.

Install adapters from the repository root:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
./.venv/bin/hermes-workflow install-runtime-adapter opencode
```

The user-facing request should stay short. All machine-critical information
belongs in `opt_requirement.md`.

`hermes-workflow optimize` remains the lower-level developer/admin command
behind the product entrypoint:

```bash
hermes-workflow optimize /home/zzchen/spectre_opt_prj/<project_name> \
  --real \
  --cadence-cshrc /path/to/user_env.csh
```

The Cadence/Spectre/OCEAN environment path is still user supplied. The user may
provide it once, for example:

```bash
mkdir -p ~/.ic-opt
cp /path/to/user/cadence_env.csh ~/.ic-opt/cadence_env.csh
```

or by placing `cadence_env.csh` in `PROJECT_DIR`. After that, the supervisor can
use the short shell command `ic-opt PROJECT_DIR --real`. `ic-opt` discovers the
user-supplied cshrc in this order:

1. explicit `--cadence-cshrc PATH`;
2. `PROJECT_DIR/cadence_env.csh`;
3. environment variable `IC_OPT_CADENCE_CSHRC`;
4. `~/.ic-opt/cadence_env.csh`.

The supervisor agent must not ask the user to restate formulas, variables,
testbench paths, Spectre resources, or optimizer settings that are already
present in `opt_requirement.md`.

Do not validate product UX by giving the supervisor a long prompt that explains
the manual. Install the runtime adapter and use the short
`/ic-opt PROJECT_DIR --real` command.

## 5. Product Environment Model

Use one product-level Python virtualenv for `ic-auto-opt-workflow`, OpenBox,
TuRBO, and report dependencies.

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Do not create a Python virtualenv inside each user project. User project
directories are data and artifact directories only:

```text
~/spectre_opt_prj/<project_name>/
```

The Cadence/Spectre/OCEAN setup remains user/project supplied through a shell
setup path or the user's shell environment. Do not hardcode a Spectre version in
agent prompts, docs, or code.

Development-only environments such as `/tmp/ic_auto_opt_openbox_spike/.venv`
must not be part of the product workflow.

## 6. Agent Step 1: Intake And Readiness

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

## 7. Agent Step 2: Preferred One-Command Flow

For direct shell/operator use, run the single orchestration command:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

This command performs the approved package/preflight/approval gate, launches the
real OpenBox optimizer, runs the closeout report chain, and then stops for user
acceptance. It does not record final user acceptance automatically. This is
automation, not a two-agent product session.

For shell/operator use, `ic-opt` defaults to direct execution:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --execution-agent direct
```

For runtime-native agent use, `/ic-opt PROJECT_DIR --real` should prepare and
approve the package, dispatch the current CLI's native execution subagent for
the generated optimizer task package, then resume supervisor-side closeout.
The historical `--execution-agent claude` subprocess route remains a
development/acceptance fallback, not the default product model.

To test the offline gates only:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
```

## 8. Low-Level Debug Fallback: Build The Approved Execution Package

This section is for maintainers debugging a specific orchestration stage. It is
not the product user entrypoint. Product users and agents should use
`ic-opt PROJECT_DIR --real`; workload, resources, strategy, Spectre settings,
testbenches, corners, and retention policy come from `opt_requirement.md` /
generated config.

Before any real optimizer execution, the supervisor agent must build and approve
the file-contract package. Do not skip this gate.

```bash
./.venv/bin/hermes-workflow package PROJECT_DIR
./.venv/bin/hermes-workflow prepare-netlist PROJECT_DIR
./.venv/bin/hermes-workflow dry-run PROJECT_DIR
./.venv/bin/hermes-workflow preflight-health PROJECT_DIR
./.venv/bin/hermes-workflow approve PROJECT_DIR
./.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR \
  --backend openbox \
  --parallel \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

`--cadence-cshrc` is the user/project Cadence environment setup script. It must
come from the user environment or project configuration; do not hardcode a
Spectre version in prompts, docs, or code.

## 9. Low-Level Debug Fallback: Run Optimizer

For OpenBox real optimization during debugging:

```bash
./.venv/bin/hermes-workflow run-openbox-real PROJECT_DIR \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

Do not use this command to invent product-level workload or resource overrides.
In the product flow, exact values come from `opt_requirement.md` / generated
config.

Resource meanings:

- `parallel_jobs`: how many Spectre simulations may run at once.
- `threads_per_run`: Spectre `+mt` threads per simulation.
- `optimizer_cpu_threads`: Python/OpenBox optimizer CPU thread limit.

Use `openbox_auto` only as the default automatic mode. Treat
`openbox_gp_eic`, `openbox_prf_eic`, and `turbo_trust_region` as peer
production strategy choices. Choose `openbox_gp_eic` for smooth,
low-to-medium-dimensional constraint-aware IC optimization. Choose
`openbox_prf_eic` for stepped, integer-heavy, mixed, high-failure, or
non-smooth spaces. Choose `turbo_trust_region` only when legal variable
steps are fine enough that snapping continuous TuRBO candidates is a
small perturbation, for example about `0.1u`; avoid it for coarse steps,
finger-count-like integers, and categorical choices. Use
`random_baseline` only for sanity checks, pipeline debugging, or
algorithm comparisons.

`optimizer_cpu_threads` changes runtime and machine load, not optimizer
correctness. After the run, inspect
`PROJECT_DIR/reports/optimizer_effectiveness_audit.json` and the matching
section in `optimizer_insight_report.md` to see the requested strategy, the
resolved surrogate/acquisition settings, whether continuation replayed prior
observations into the model, and whether the latest batch was still
initialization or real BO progress.

The agent should not replace this with manually selected candidate points.

Status policy: after a long real optimizer starts, the execution agent should
avoid per-batch polling. It should report start, unexpected failure, completion,
and only low-frequency heartbeat status for long runs.

## 10. Manual Fallback: Close Out The Run

If using `hermes-workflow optimize ... --real`, these reports are already
generated. If running the manual fallback, after the optimizer run finishes the
agent should run:

```bash
./.venv/bin/hermes-workflow check-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow summarize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow visualize-optimizer-run PROJECT_DIR
./.venv/bin/hermes-workflow decide-optimizer-run PROJECT_DIR
```

Then the agent should read:

```text
PROJECT_DIR/reports/optimizer_effectiveness_audit.json
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

Important: `decide-optimizer-run` must not present a `constraint_failed`,
`metric_check_failed`, or `real_check_failed` candidate as the primary
recommended run when any feasible candidate exists.

## 11. User Decision Point

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

## 12. What The User Reads

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

## 13. How To Continue Optimization

Only continue if the decision report or the user asks for it.

Example:

```bash
./.venv/bin/hermes-workflow continue-openbox-real PROJECT_DIR \
  --additional-evals 100 \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

Do not add workload, resource, strategy, surrogate, acquisition, or acquisition
optimizer flags during product continuation. Product continuation is only
`ic-opt PROJECT_DIR --real --continue N`; everything except `N` is inherited from
the project's requirement-backed config so one optimizer history does not mix
different execution contracts.

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

## 14. How To Interpret Failures

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

## 15. Important Boundaries

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

## 16. Minimal Successful Session

A successful runtime-native production session looks like:

```text
1. User creates PROJECT_DIR and writes opt_requirement.md.
2. User sends `/ic-opt PROJECT_DIR --real` to Claude, OpenCode, or another
   supported runtime after installing its adapter.
3. Supervisor-side flow prepares/preflights/approves the package.
4. Same-runtime execution subagent runs the generated optimizer task.
5. Supervisor-side flow writes `optimizer_flow_run_report.json`, handoff
   report, and closeout reports.
6. Supervisor reports best observed feasible result and bottleneck.
7. User accepts or asks to continue.
8. Supervisor records decision and writes optimizer_final_summary.md.
9. readiness=ready_for_closeout_review.
```

At that point, the user can use the accepted candidate as the current optimized
design point, while remembering it is not a mathematical global optimum proof.

This is the C-65 product target. C-65 provides Claude and OpenCode adapter
assets; each runtime still needs a live native-subagent drill in the target
environment before claiming full production support for that runtime.
