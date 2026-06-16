---
name: ic-opt
description: Operate IC Auto Opt from a project directory. Use when the user asks an agent to doctor, run, continue, inspect, or explain a local or remote Spectre/Maestro/ADE optimization or fix-run project.
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

## Modes

Read `opt_requirement.md` before running.

- `Workflow.mode: optimize` runs an optimizer.
- `Workflow.mode: fix_run` runs user-specified fixed points and optional
  waveform CSV exports.
- If `Workflow` is absent, treat the file as an optimization requirement.

There is no separate product CLI switch for fix-run. The mode comes from the
requirement file.

## Do Not Override Requirement Values

Do not ask the user to restate formulas, variables, metric routes, testbench
paths, Spectre resources, optimizer settings, fixed points, waveform exports,
or process corners in chat.

Do not add CLI overrides for optimizer budget, batch size, candidate
parallelism, Spectre threads, optimizer CPU cap, algorithm, strategy,
initialization, output format, retention, objective, constraints, fixed points,
waveform exports, or corners.

`--continue N` is the only CLI value that changes the number of new
simulations. Use it only for an existing optimizer run.

`--ssh-profile PROFILE` selects the remote execution profile. It is not an
optimizer or resource override.

Do not hand-pick optimizer candidate points, rewrite OCEAN formulas, parse PSF
in Python, change the search space, or hardcode a Spectre version.

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

Optimization initial-run values stay in `opt_requirement.md`, including:

- `max_evaluations`, `batch_size`
- Spectre `parallel_jobs`, `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, `random_seed`
- `output_format: psfxl`
- testbenches, metric routes, objective, constraints
- Process Corners and multi-corner policies

Fix-run values also stay in `opt_requirement.md`, including:

- `Fixed Points`
- `Waveform Exports`
- Spectre settings and Process Corners
- approval checklist

The correct pnoise waveform expression form is:

```text
getData("NF" ?result "pnoise")
```

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

## Workflow Verification

Do not treat successful command exit as full workflow acceptance.

For optimization workflows, inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner optimization runs, inspect parent aggregate
manifests.

For fix-run workflows, inspect:

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

Confirm requirement values reached artifacts and execution:

- workflow mode
- fixed points or optimizer strategy
- process corners
- Spectre resources and `output_format: psfxl`
- license probe behavior
- sanitized Spectre/OCEAN `command_trace`
- waveform CSV export status for fix-run

Report pass/fail state, failed child count, selected run id, corner policy,
recommended parameters when optimizing, metrics, waveform CSV paths, warnings,
and artifact paths.

If doctor or real execution fails, report the failing item and relevant report
path. Do not continue by changing formulas, selecting candidates manually, or
editing the requirement without explicit user direction.
