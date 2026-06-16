# IC Auto Opt Workflow

`ic-auto-opt-workflow` is a file-driven IC optimization workflow for
Maestro-exported Spectre/OCEAN projects.

The implemented shell product command is:

```bash
ic-opt /path/to/project --real
```

The runtime-native agent entrypoint, after installing the adapter for your
agent CLI, is:

```text
/ic-opt /path/to/project --real
```

The project has been exercised on a real multi-testbench Mixer optimization
flow with OpenBox, Spectre, OCEAN, and post-run visualization/reporting.

Important agent-integration boundary: `ic-opt` is the deterministic automation
core. Runtime adapters make the current agent CLI act as supervisor and
delegate real execution to that same CLI's native subagent/task mechanism.
C-64's `--execution-agent claude` subprocess handoff remains development
evidence, not the C-65 default product target. See
`docs/AGENT_INTEGRATION_STATUS.md` before describing runtime support.

For the detailed Chinese explanation of what the automation does, what evidence
proves it, and which runtime adapters are still missing, read
`docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

## What This Project Does

- Reads a strict `opt_requirement.md` from a user project directory.
- Safely imports native Maestro/ADE point-root netlist bundles.
- Preserves each testbench as its own Spectre/OCEAN run context.
- Uses OpenBox or native optimizer backends to generate candidates.
- Runs approved real Spectre/OCEAN evaluations through workflow contracts.
- Aggregates scalar OCEAN metric results across one or more testbenches.
- Writes optimizer acceptance, decision, visualization, and final-summary
  reports.

Hermes workflow tooling does not parse PSF data and does not rewrite approved
OCEAN formulas.

## Current Product Contract

- `opt_requirement.md` is the only product entry for workload, optimizer budget
  (`max_evaluations`), optimizer batch size, Spectre parallelism
  (`parallel_jobs`), Spectre threads (`threads_per_run`), optimizer CPU thread
  limit (`optimizer_cpu_threads`), optimizer strategy, initialization,
  process-corner policy, output format, retention policy, and metric contracts.
- The product CLI does not accept initial-run overrides for those values. Do not
  use or document `--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads`,
  or `--strategy` on `ic-opt PROJECT --real`.
- Product continuation keeps one CLI delta: `ic-opt PROJECT --real --continue N`
  adds `N` more evaluations. All other values are inherited from the project
  requirement/generated config.
- Multi-corner optimization is configured in `opt_requirement.md` through
  `Process Corners`; no `--multi-corner` switch exists. See
  `examples/spectre_maestro_project/opt_requirement.multi_corner.md` and
  `examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`.
- Production strategy choices are peers: `openbox_gp_eic`,
  `openbox_prf_eic`, and `turbo_trust_region`. `openbox_auto` is the
  default automatic mode, and `random_baseline` is diagnostic only. Use
  `turbo_trust_region` when legal variable steps are fine enough that
  snapping continuous TuRBO candidates is a small perturbation, for example
  about `0.1u`; avoid it for coarse steps, finger-count-like integers, and
  categorical choices. See `docs/OPTIMIZER_ALGORITHM_MODES.md`.
  `RELEASE_NOTES_v0.1.7.md`.

## Install

Use one product-level Python environment for the repo and optimizer
dependencies. Do not create a Python virtualenv inside each user optimization
project.

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Expected entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

Install an agent runtime adapter once.

For Claude:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
```

For OpenCode:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter opencode
```

Then use the short agent command:

```text
/ic-opt /path/to/project --real
```

For direct shell/operator debugging, use:

```bash
ic-opt /path/to/project --real
```

## Cadence Environment

The Cadence/Spectre/OCEAN setup is user supplied. Configure it once before using
the short product command.

Recommended user-level setup:

```bash
mkdir -p ~/.ic-opt
cp /path/to/user/cadence_env.csh ~/.ic-opt/cadence_env.csh
```

Project-local setup is also supported:

```text
/path/to/project/cadence_env.csh
```

Discovery order for `ic-opt`:

1. explicit `--cadence-cshrc PATH`;
2. `PROJECT_DIR/cadence_env.csh`;
3. `IC_OPT_CADENCE_CSHRC`;
4. `~/.ic-opt/cadence_env.csh`.

`ic-opt` does not infer `.bashrc`/`.zshrc` content and does not hardcode a
Spectre version.

## Remote SSH Mode

Use this when your Cadence/Spectre/OCEAN environment is on a Linux EDA server,
but you want to run `ic-opt`, OpenBox, and report viewing from your own
workstation.

First configure passwordless SSH yourself:

```bash
ssh lab true
```

Then run:

```bash
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --doctor
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --real
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --real --continue 40
```

The project path is the Linux server path. Reports are written on the server
under `PROJECT/reports/` and mirrored locally under `~/.ic-opt/remote_runs/`.

## User Project Layout

Recommended layout:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. `constraints.md` is for human guidance to
the supervisor agent. Do not hand-build generated directories such as
`config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, or `state/`.

For each testbench, first run one known-good Maestro/ADE point and put the point
root in `opt_requirement.md`. The point root must contain:

```text
<maestro_point_root>/netlist/input.scs
```

Multi-testbench projects route each metric to a named testbench; Hermes keeps
those native netlist bundles separate and aggregates scalar metric manifests at
candidate level.

## Run

Preferred product command:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> --real
```

Offline gate check without launching Spectre/OCEAN/OpenBox:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> --real --dry-orchestration
```

The product CLI is the contract for normal users: initial real runs read workload
and resources from `opt_requirement.md`, and continuation accepts only
`--continue N` as a CLI delta. Low-level `hermes-workflow` commands are
development/debugging tools for maintainers inspecting a specific pipeline stage;
do not present them as product usage and do not use them to override the user's
requirement contract.

```bash
./.venv/bin/hermes-workflow optimize ~/spectre_opt_prj/<project_name> --real
```

For product continuation after a completed run:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> --real --continue 40
```

Do not copy workload, resource, or strategy flags into product continuation
commands. `parallel_jobs`, `batch_size`, optimizer strategy, Spectre settings,
and retention policy come from `opt_requirement.md` / generated config.

## Read Results

Primary reports:

```text
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
```

Visual artifacts are under:

```text
reports/optimizer_visuals/
reports/openbox_advanced_visualization/
```

The accepted candidate is a best-observed point under the evaluated samples and
configured objective. It is not a mathematical proof of global optimum.

## Proven Product Evidence

C-60 real product acceptance used a fresh Mixer multi-testbench project with a
project-local `cadence_env.csh` and ran:

```bash
./.venv/bin/ic-opt PROJECT --real
```

It completed 100 real OpenBox/Spectre/OCEAN evaluations, generated OpenBox
advanced visualization, and recommended a feasible best-observed candidate.

C-64 Claude subprocess handoff acceptance used a fresh Mixer multi-testbench
project with
only `opt_requirement.md` and `cadence_env.csh`, then ran:

```bash
claude -p --dangerously-skip-permissions "/ic-opt PROJECT --real"
```

The historical `/ic-opt` skill appended `--execution-agent claude`; the flow wrote
`reports/execution_agent_handoff_report.json` with `status=pass`,
`execution_agent=claude`, `returncode=0`, completed 100 real evaluations, and
recommended feasible `real_051`. C-65 keeps that route as acceptance evidence
and development fallback, while product adapters target runtime-native
same-CLI subagent delegation.

## Documentation

- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: shortest production workflow.
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`: supervisor/execution-agent operating
  manual.
- `docs/OPTIMIZER_ALGORITHM_MODES.md`: supported optimizer strategy selection,
  including peer production choices `openbox_gp_eic`, `openbox_prf_eic`, and
  `turbo_trust_region`.
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`: multi-corner aggregation flow
  and what the optimizer sees.
- `docs/AGENT_INTEGRATION_STATUS.md`: current implemented agent boundary and
  remaining runtime-specific adapter work.
- `docs/AGENT_USER_QUICKSTART_CN.md`: beginner-friendly Chinese guide for IC
  users running the agent workflow.
- `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`: detailed Chinese status and
  architecture explanation with evidence references.
- `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`:
  `opt_requirement.md` format reference.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: mandatory real-tool execution
  reference for development and debugging.
- `docs/PRODUCT_RELEASE_CHECKLIST.md`: release sanity checklist.
- `RELEASE_NOTES_v0.1.7.md`: current release contract and fixed bug summary.

## Boundaries

- Do not parse PSF in Python.
- Do not rewrite approved OCEAN formulas.
- Do not merge multiple testbenches into a synthetic Spectre deck.
- Do not hand-pick optimizer points for backend acceptance.
- Do not create per-project Python virtualenvs.
- Do not commit raw `input.scs`, protected sidecars, PSF data, or full Cadence
  logs.
