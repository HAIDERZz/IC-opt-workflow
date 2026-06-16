# Agent Optimizer Usage Manual

This manual describes how an agent should operate IC Auto Opt v0.1.7.

The agent is an operator and report reader. It should use the product CLI,
inspect workflow artifacts, and report evidence. It should not invent optimizer
settings, rewrite formulas, or choose candidate points by hand.

## Project Inputs

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. `constraints.md` and `context/` are for
human guidance and supporting notes. Generated directories such as `config/`,
`netlists/`, `runs/`, `reports/`, `ledger/`, and `state/` are created by the
workflow.

## Requirement Contract

`opt_requirement.md` is the only product entry for initial-run
machine-critical settings:

- Maestro/ADE point roots and testbench routes
- OCEAN metric expressions
- design variables, ranges, and legal steps
- constraints and objective
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- retention policy
- license probe requirement
- Process Corners and multi-corner policies

The product CLI keeps one value-changing continuation entry:

```bash
ic-opt PROJECT_DIR --real --continue N
```

All other values stay inherited from `opt_requirement.md` and generated config.

## Product Commands

Local:

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
```

Remote:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`--ssh-profile PROFILE` selects the remote execution profile. It is not an
optimizer or resource override.

Use `--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup path.

## Agent Behavior

The agent should:

- read `opt_requirement.md` before running
- run doctor before real execution when validating an environment
- use product CLI commands instead of low-level developer commands
- inspect reports and manifests before reporting success
- report command status, evaluation counts, selected run id, corner policy,
  recommended parameters, metrics, warnings, and artifact paths

The agent must not:

- ask the user to restate formulas, variable ranges, Spectre resources,
  optimizer settings, or process corners in chat
- add CLI overrides for budget, batch size, parallelism, Spectre threads,
  optimizer CPU cap, algorithm, strategy, initialization, output format,
  retention, objective, constraints, or corners
- hand-pick candidate points
- rewrite OCEAN formulas
- parse PSF in Python
- change the search space, objective, constraints, or metric routes
- treat a zero exit code as acceptance without artifact inspection

## Optimizer Modes

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO is a fit when legal variable steps are fine enough that snapping a
continuous candidate to the legal grid is a small perturbation, for example
about `0.1u`. Prefer `openbox_prf_eic` for coarse integer grids, categorical
choices, or duplicate-heavy snapped spaces.

`random_baseline` is diagnostic.

## Multi-Corner Runs

Multi-corner optimization is configured in the `Process Corners` section of
`opt_requirement.md`. Use:

```text
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

The agent should inspect aggregate artifacts and report objective policy,
constraint policy, selected run, corner-level metrics, and worst-case or
all-corners constraint result.

## Artifact Acceptance Checklist

For real workflow acceptance, inspect at least:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner projects, inspect the parent aggregate
manifest. Confirm requirement values reached artifacts and execution:

- algorithm, strategy, initialization, and random seed
- budget and batch size
- Spectre parallelism and threads
- optimizer CPU cap
- process corners
- `output_format: psfxl`
- license probe behavior
- sanitized Spectre/OCEAN `command_trace`
