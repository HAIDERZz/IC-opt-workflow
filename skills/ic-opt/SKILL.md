---
name: ic-opt
description: Operate IC Auto Opt from a project directory. Use when the user asks an agent to doctor, run, continue, inspect, or explain a local or remote Spectre/Maestro/ADE optimization project.
---

# IC Auto Opt Agent Operator

Operate the `ic-opt` product CLI and inspect artifacts. The agent is an
operator and report interpreter:

```text
User -> agent -> ic-opt CLI -> reports/artifacts -> agent explains result
```

`PROJECT_DIR/opt_requirement.md` is the source of truth for initial-run
machine-critical settings. Optional human guidance can live in
`PROJECT_DIR/constraints.md`.

## Do Not Override Requirement Values

Do not ask the user to restate formulas, variables, metric routes, testbench
paths, Spectre resources, optimizer settings, or process corners in chat.

Do not add CLI overrides for optimizer budget, batch size, candidate
parallelism, Spectre threads, optimizer CPU cap, algorithm, strategy,
initialization, output format, retention, objective, constraints, or corners.

`--continue N` is the only CLI value that changes the number of new simulations.
Use it only for an existing run.

`--ssh-profile PROFILE` selects the remote execution profile. It is not an
optimizer or resource override.

Do not hand-pick candidate points, rewrite OCEAN formulas, parse PSF in Python,
change the search space, or hardcode a Spectre version.

## Commands

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

Use `--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup path.

## Requirement Fields

Initial-run values stay in `opt_requirement.md`, including:

- `max_evaluations`, `batch_size`
- Spectre `parallel_jobs`, `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, `random_seed`
- `output_format: psfxl`
- testbenches, metric routes, objective, constraints
- Process Corners and multi-corner policies

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

## Workflow Verification

Do not treat successful command exit as full workflow acceptance. Inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner runs, inspect parent aggregate manifests.

Confirm requirement values reached artifacts and execution:

- algorithm, strategy, initialization, random seed
- budget, batch size
- parallelism, Spectre threads
- optimizer CPU cap
- process corners
- `output_format: psfxl`
- license probe behavior
- sanitized Spectre/OCEAN `command_trace`

Report pass/fail state, failed evaluation counts, selected run id, selected
corner or worst-case policy, recommended parameters, metrics, warnings, and
artifact paths.

If doctor or real execution fails, report the failing item and relevant report
path. Do not continue by changing formulas, selecting candidates manually, or
editing the requirement without explicit user direction.
