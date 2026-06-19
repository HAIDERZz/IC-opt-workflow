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

## History Warm Start

If `opt_requirement.md` contains `## History Warm Start`, treat it as a new
optimize-project warm-start from previous same-circuit projects. It renders to
`config/history_warm_start.yaml`. Do not run it with `--continue N`; continuation
only adds budget to the same optimizer project and does not reread a changed
requirement. Do not use it for fix-run.

The first supported contract is strict: current and previous projects must have
exactly the same variable names, no variable-name mapping, and matching required
metric definitions. Previous objective and constraint results are not reused;
old raw metrics are re-evaluated against the current requirement. Points outside
the current variable space are rejected as `out_of_current_space`.

After the run, inspect:

```text
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
openbox.history_warm_start in reports/optimizer_run_report.json
```

When reporting, distinguish accepted history from applied history:
`accepted_observation_count` means the audit found compatible old rows;
`applied_observation_count` means data actually reached OpenBox Advisor.
Unconstrained single-objective projects may use `transfer_learning_history`.
Constrained IC projects use `initial_configurations_from_history`. If
`applied_to_advisor` is false, report `not_applied_reason`.

## Optimizer Insight Report

After optimize/finalize, inspect `reports/optimizer_insight_report.html` first
when advising the user. The workflow also writes:

```text
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
```

Treat Pareto and space-compression sections as report-layer guidance only. The
Pareto/trade-off analyzer uses existing raw metrics; it does not enable OpenBox
multi-objective optimizer mode, change candidate selection, or rewrite the
configured objective. The Space Compression Advisory uses an OpenBox compressor
dry-run. Suggested ranges are advisory only and are not applied to optimizer
execution; a user must copy reviewed ranges into a new `opt_requirement.md` for
a later run.

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

For fix-run, `Spectre Settings.parallel_jobs` controls how many
testbench/corner child runs for one fixed point may run concurrently.
`Spectre Settings.threads_per_run` remains the thread count for each Spectre
process. Fixed points are still processed serially in this release. There is no
CLI override for fix-run parallelism.

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
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
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
