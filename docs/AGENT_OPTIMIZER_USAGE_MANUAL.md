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

For fix-run, Spectre `parallel_jobs` is child-level concurrency inside one
fixed point: at most that many testbench/corner child Spectre/OCEAN runs are in
flight. `threads_per_run` remains per Spectre process. Fixed points are still
processed serially, and agents must not invent a CLI override for this setting.

The product CLI keeps one value-changing continuation entry for existing
optimizer runs:

```bash
ic-opt PROJECT_DIR --real --continue N
```

All other values stay inherited from `opt_requirement.md` and generated config.

## History Warm Start

If `opt_requirement.md` contains `## History Warm Start`, treat it as a new
optimize-project warm-start from previous same-circuit projects. It renders to
`config/history_warm_start.yaml`. Do not recommend it for fix-run, and do not
combine it with `--continue N`; continuation only extends an existing optimizer
project and does not reread a changed requirement.

The first release of history warm-start is strict: current and previous projects
must have exactly the same variable names, no variable-name mapping, and matching
required metric definitions. Old objective and constraint values are not reused;
old raw metrics are re-evaluated with the current requirement. Old points outside
the current variable space are rejected as `out_of_current_space`.

History application is an OpenBox backend feature. Do not tell the user that a
native TuRBO run consumed history warm-start data. For TuRBO, expect the history
application report to be absent or `not_available`; choose OpenBox when previous
project history must guide new candidate suggestions.

After a run, inspect:

```text
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
openbox.history_warm_start in reports/optimizer_run_report.json
```

Do not say history was applied just because the config exists. Check
`accepted_observation_count`, `applied_observation_count`, `applied_to_advisor`,
`application_mode`, and `not_applied_reason`. Unconstrained single-objective
projects may use `transfer_learning_history`; constrained IC projects use
`initial_configurations_from_history`.

## Optimizer Insight Report

After optimize/finalize, inspect `reports/optimizer_insight_report.html` first
when advising the user. The workflow also writes:

```text
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
```

Use the HTML report for orientation, but do not base detailed engineering
recommendations on the HTML alone. Inspect the dense artifacts when answering
trade-off, history, or next-range questions. Some backend-specific JSONL files
are only present for the backend that ran:

```text
reports/optimizer_insight_report.json
reports/optimizer_run_report.json
reports/history_warm_start_audit.json
reports/optimizer_evaluations.jsonl
reports/native_turbo_optimizer_evaluations.jsonl
ledger/experiment_ledger.jsonl
runs/**/metric_result_manifest.json
```

Treat scripted HTML notes as summaries. Verify exact counts, raw metric values,
and parameter combinations in JSON/JSONL before making recommendations.

Treat Pareto and space-compression sections as report-layer guidance only.
The Pareto/trade-off analyzer uses existing raw metrics; it does not enable
OpenBox multi-objective optimizer mode, does not change candidate selection,
and does not rewrite the configured objective.

The Space Compression Advisory uses an OpenBox compressor dry-run. Suggested
ranges are advisory only and are not applied to optimizer execution. If the user
accepts a suggestion, they must copy the reviewed range into a new
`opt_requirement.md` for a later run.

For native TuRBO runs, retain the backend-neutral parts of the insight report:
best point, actual measured metrics, evaluation/status counts, plots,
raw-metric trade-off summaries, and advisory space-compression dry-runs when
the required artifacts exist. OpenBox-specific sections such as history
warm-start application, advanced surrogate visualization, and parameter
importance are not expected for TuRBO and may appear as `not_available`.

If an objective expression directly multiplies or divides signed/log-domain
metrics such as dB or dBm, especially values that may cross zero, warn that the
ranking may be hard to interpret. The workflow preserves the user's objective;
do not rewrite it. Suggest linear-domain or normalized terms only as a reviewed
next-requirement choice.

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
- `parallel_jobs` and `threads_per_run` were inherited from the requirement
- waveform exports were written for every successful child
- all failures appear in `child_issues`
- optimizer state and optimizer decision reports were not created

## Optimization Artifact Checklist

For optimizer workflows, inspect:

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
reports/optimizer_evaluations.jsonl
reports/native_turbo_optimizer_evaluations.jsonl
ledger/experiment_ledger.jsonl
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
