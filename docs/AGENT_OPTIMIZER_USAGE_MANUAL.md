# Agent Workflow Usage Manual

This manual describes how an agent should operate IC Auto Opt v0.1.8.

The agent is an operator and report reader. It should use the product CLI,
inspect workflow artifacts, and report evidence. It should not invent optimizer
settings, rewrite formulas, choose candidate points by hand, or treat a command
exit code as workflow acceptance.

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
machine-critical settings. It selects the workflow mode:

- `mode: optimize` for optimizer runs
- `mode: fix_run` for fixed-point characterization and waveform CSV export

Optimization values stay in `opt_requirement.md`:

- Maestro/ADE point roots and testbench routes
- OCEAN scalar metric expressions
- design variables, ranges, and legal steps
- constraints and objective
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- retention policy, license probe, and Process Corners

Fix-run values also stay in `opt_requirement.md`:

- fixed candidate points
- Spectre settings and Process Corners
- waveform exports such as `getData("NF" ?result "pnoise")`
- approval checklist

The product CLI keeps one value-changing continuation entry for existing
optimizer runs:

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
- identify whether the workflow mode is optimize or fix-run
- run doctor before real execution when validating an environment
- use product CLI commands instead of low-level developer commands
- inspect reports and manifests before reporting success
- report command status, failed child count, run id, corner policy, metrics,
  waveform CSV paths, warnings, and artifact paths

The agent must not:

- ask the user to restate formulas, variable ranges, Spectre resources,
  optimizer settings, fixed points, waveform exports, or process corners in chat
- add CLI overrides for budget, batch size, parallelism, Spectre threads,
  optimizer CPU cap, algorithm, strategy, initialization, output format,
  retention, objective, constraints, fixed points, waveform exports, or corners
- hand-pick optimizer candidate points
- rewrite OCEAN formulas
- parse PSF in Python
- change the search space, objective, constraints, or metric routes
- claim a fix-run succeeded without inspecting `reports/fix_run_report.json`

## Optimizer Modes

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO is a fit when legal variable steps are fine enough that snapping a
continuous candidate to the legal grid is a small perturbation. Prefer
`openbox_prf_eic` for coarse integer grids, categorical choices, or
duplicate-heavy snapped spaces.

`random_baseline` is diagnostic.

## Fix-Run Artifact Checklist

For fix-run workflows, inspect:

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

Confirm:

- `workflow_mode` is `fix_run`
- expected testbench/corner child count matches the requirement
- waveform exports were written for every successful child
- all failures appear in `child_issues`
- optimizer state and optimizer decision reports were not created

## Optimization Artifact Checklist

For optimizer workflows, inspect:

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
