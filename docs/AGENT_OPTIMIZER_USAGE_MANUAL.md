# Agent Workflow Usage Manual

This manual describes how an agent should operate IC Auto Opt v0.1.10.

The agent is an operator and report reader. It should use the product CLI,
inspect workflow artifacts, and report evidence. It should not invent optimizer
settings, rewrite formulas, choose candidate points by hand, or treat a command
exit code as workflow acceptance.

The agent is also an IC optimization advisor. It should combine the user's
circuit notes, topology knowledge, specifications, and constraints with IC Auto
Opt reports and raw artifacts, then explain what the results imply for the next
optimization step.

## Document Map

- `README.md`: install path, local/remote split, command shapes, product scope.
- `docs/USER_GUIDE_CN.md`: complete Chinese user guide.
- `docs/AGENT_USER_QUICKSTART_CN.md`: compact agent checklist.
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`: detailed agent behavior rules.
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: production execution sequence.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: CLI, Cadence setup, and evidence files.
- `docs/OPTIMIZER_ALGORITHM_MODES.md`: OpenBox and TuRBO strategy selection.
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`: process-corner aggregation.
- `docs/TROUBLESHOOTING_CN.md`: failure diagnosis.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`: requirement
  section contract and template selection.
- `examples/spectre_maestro_project/*.md`: real validated sanitized
  requirements. Use these as examples instead of inventing snippets.

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

For each Maestro/ADE testbench, the point root is the result point directory
itself, not `input.scs` and not `psf/`. It must contain `netlist/input.scs`.
A typical path is:

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

Example:

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

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
The command continues the backend already stored in the project: OpenBox stays
OpenBox and native TuRBO stays native TuRBO. Never convert native history into
an OpenBox continuation or restart TuRBO initialization under the same project.
For Remote continuation, the product reruns Remote Doctor once for the current
attempt before frozen-snapshot restore, history synchronization, or backend
dispatch; do not bypass that gate with a cached doctor result from an earlier
attempt.

## Requirement Modes

| User goal | Template | Mode |
| --- | --- | --- |
| Single testbench, source-point corner optimization | `opt_requirement.md` | `optimize` |
| Explicit OpenBox GP-EIC optimization | `opt_requirement.openbox_gp_eic.md` | `optimize` |
| Explicit native TuRBO optimization | `opt_requirement.turbo.md` | `optimize` |
| Single testbench, multiple process corners | `opt_requirement.multi_corner.md` | `optimize` |
| Multiple testbenches, source-point corner | `opt_requirement.multi_testbench.md` | `optimize` |
| Multiple testbenches and multiple process corners | `opt_requirement.multi_tb_corner.md` | `optimize` |
| New same-circuit run using previous project history | `opt_requirement.history_warm_start.md` | `optimize` + History Warm Start |
| Multi-corner run using previous same-circuit history | `opt_requirement.history_warm_start.multi_corner.md` | `optimize` + History Warm Start |
| User-specified fixed points and waveform CSV export | `opt_requirement.fix_run.md` | `fix_run` |
| Fixed points with scalar Metrics only | `opt_requirement.fix_run.metrics_only.md` | `fix_run` |
| Multi-testbench fixed points with Metrics and Waveforms | `opt_requirement.fix_run.multi_testbench.metrics_waveform.md` | `fix_run` |

## History Warm Start

If `opt_requirement.md` contains `## History Warm Start`, treat it as a new
optimize-project warm-start from previous same-circuit projects. It renders to
`config/history_warm_start.yaml`. Do not recommend it for fix-run, and do not
combine it with `--continue N`; continuation only extends an existing optimizer
project and does not reread a changed requirement.

Enabled History Warm Start is OpenBox-only and is rejected for native TuRBO.
For native TuRBO, use `--continue N`; do not claim warm-start data was consumed.

Use `examples/spectre_maestro_project/opt_requirement.history_warm_start.md`
as the checked example when the user asks for a new same-circuit history run.
It is a sanitized version of a verified second-round multi-testbench Mixer
requirement, not a synthetic minimal snippet.

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
- use user-provided circuit knowledge together with report evidence
- explain next-step choices such as continuing the same project, creating a new
  requirement with adjusted ranges, switching backend, revising the objective,
  or running fix-run waveform export

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
