# IC Auto Opt Workflow

`ic-auto-opt-workflow` is a file-driven IC optimization workflow for
Maestro-exported Spectre/OCEAN projects.

The product goal is simple:

```bash
ic-opt /path/to/project --real
```

The project has been exercised on a real multi-testbench Mixer optimization
flow with OpenBox, Spectre, OCEAN, and post-run visualization/reporting.

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
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

Offline gate check without launching Spectre/OCEAN/OpenBox:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

The lower-level implementation command remains available for development and
audit work:

```bash
./.venv/bin/hermes-workflow optimize ~/spectre_opt_prj/<project_name> --real
```

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
./.venv/bin/ic-opt PROJECT --real --max-evals 100 --batch-size 10 --parallel-jobs 10
```

It completed 100 real OpenBox/Spectre/OCEAN evaluations, generated OpenBox
advanced visualization, and recommended a feasible best-observed candidate.

## Documentation

- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: shortest production workflow.
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`: supervisor/execution-agent operating
  manual.
- `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`:
  `opt_requirement.md` format reference.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: mandatory real-tool execution
  reference for development and debugging.
- `docs/PRODUCT_RELEASE_CHECKLIST.md`: release sanity checklist.

## Boundaries

- Do not parse PSF in Python.
- Do not rewrite approved OCEAN formulas.
- Do not merge multiple testbenches into a synthetic Spectre deck.
- Do not hand-pick optimizer points for backend acceptance.
- Do not create per-project Python virtualenvs.
- Do not commit raw `input.scs`, protected sidecars, PSF data, or full Cadence
  logs.
