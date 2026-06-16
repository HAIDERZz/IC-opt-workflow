---
name: ic-opt
description: Operate IC Auto Opt from a project directory. Use when the user asks an agent to doctor, run, continue, or inspect a local or remote Spectre/Maestro/ADE optimization project.
---

# IC Auto Opt Agent Operator

Operate the deterministic `ic-opt` product CLI and inspect its artifacts. The
agent is an operator and report interpreter:

```text
User -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

## Product Contract

- `PROJECT_DIR/opt_requirement.md` is the source of truth for initial-run
  machine-critical settings.
- Optional human guidance can live in `PROJECT_DIR/constraints.md`.
- Do not ask the user to restate formulas, variables, metric routes,
  testbench paths, Spectre resources, optimizer settings, or process corners in
  chat.
- Do not add CLI overrides for optimizer budget, batch size, candidate
  parallelism, Spectre threads, optimizer CPU cap, algorithm, strategy,
  initialization, output format, retention, objective, constraints, or corners.
- `--continue N` is the only CLI value that changes the number of new
  simulations. It appends N more evaluations to an existing run.
- `--ssh-profile PROFILE` selects the remote execution profile. It is not an
  optimizer/resource override.
- Do not hand-pick candidate points, rewrite OCEAN formulas, parse PSF in
  Python, change the search space, or hardcode a Spectre version.

## Commands

Local doctor:

```bash
ic-opt PROJECT_DIR --doctor
```

Local real run:

```bash
ic-opt PROJECT_DIR --real
```

Local continuation:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Remote doctor:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
```

Remote real run:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

Remote continuation:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

Use `--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup path. If the user asks to check readiness, use doctor. If the user
asks to optimize and gives only a project path, use `--real`. If the user says
"add", "run", or "continue" N more points, use `--real --continue N`.

## Requirement Fields To Respect

Initial-run values stay in `opt_requirement.md`, including:

- `max_evaluations`, `batch_size`
- Spectre `parallel_jobs`, `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, `random_seed`
- `output_format: psfxl`
- testbenches, metric routes, objective, constraints
- Process Corners and multi-corner policies

Use only the product commands listed above. If a needed setting is not one of
those CLI controls, it belongs in `opt_requirement.md`.

## Optimizer Modes

Explain these as peer production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic mode. `random_baseline` is diagnostic.
TuRBO is a fit when legal variable steps are fine enough that snapping
continuous candidates to the legal grid is a small perturbation, for example
about `0.1u`; avoid it for coarse steps, finger-count-like integers,
categorical choices, and duplicate-heavy snapped spaces.

## Workflow Verification

Do not treat a successful command exit as full workflow acceptance. Inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner runs, inspect parent aggregate manifests.
Confirm that requirement values reached artifacts and execution: algorithm,
strategy, initialization, random seed, budget, batch size, parallelism, Spectre
threads, optimizer CPU cap, process corners, `output_format: psfxl`, license
probe behavior, and sanitized Spectre/OCEAN `command_trace`.

## Reporting

Report:

- pass/fail state and failed command when relevant;
- evaluation counts and status counts;
- selected run id;
- selected corner or worst-case policy result when present;
- recommended parameters and metrics;
- warnings and bottlenecks;
- artifact paths used as evidence.

If doctor or real execution fails, report the failing item and relevant report
path. Do not continue by changing formulas, selecting candidates manually, or
editing the requirement without explicit user direction.
