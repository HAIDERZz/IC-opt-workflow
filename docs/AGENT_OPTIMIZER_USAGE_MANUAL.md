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
- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`: product role and terminology.
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

Only `opt_requirement.md` is required. `constraints.md` is read by requirement
intake, hashed, and synced to the remote cache for remote runs. `context/` has
no code that reads it in this release — it is a pure human-reading convention
and remote prepare does not sync it. Generated directories and files such as
`config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, `state/`,
`execution_package/`, and the project-root `supervisor_instruction.json` are
created by the workflow — `execution_package/` and
`supervisor_instruction.json` are the approval-gate evidence written before a
real backend starts.

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
- `Approval Checklist` — a required section for optimize projects, not only
  for fix-run

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
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

All other values stay inherited from `opt_requirement.md` and generated config.
The command continues the backend already stored in the project: OpenBox stays
OpenBox and native TuRBO stays native TuRBO. Never convert native history into
an OpenBox continuation or restart TuRBO initialization under the same project.
For Remote continuation, the product reruns Remote Doctor once for the current
attempt before frozen-snapshot restore, history synchronization, or backend
dispatch; do not bypass that gate with a cached doctor result from an earlier
attempt.

Remote continuation has three more implemented gates besides the Remote Doctor
rerun, and any one of them can stop `--continue N` before it extends the run:

- **Remote attempt lock**: `state/remote_attempt.lock` gives one Controller
  attempt exclusive ownership. Locks are deliberately never stolen
  automatically (`RemoteAttemptLockedError`); check the lock's owner metadata
  and remove the lock directory manually before retrying.
- **Missing optimizer history**: fails with `cannot continue without optimizer
  history: <path> is missing or empty` when the resolved backend's evaluation
  history file is absent or empty.
- **Rejected prior acceptance**: before extending history, continuation
  re-checks the existing run's acceptance status and fails with `prior
  optimizer history acceptance rejected: ...` if it is not `accepted`.

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
`config/history_warm_start.yaml`. `history_warm_start.enabled: true` on a
`fix_run` project is a hard requirement/project validation failure ("only
supported for optimize workflow"), not just a recommendation against it. Do
not combine it with `--continue N` either: continuation re-validates the
current requirement, but does not re-materialize requirement changes into
this run's execution config, so a warm-start section added (or changed)
there has no effect on a continuation run.

Enabled History Warm Start is rejected during validation for any resolved
backend other than OpenBox — native TuRBO and `random_baseline` alike, not
native TuRBO only. For native TuRBO, use `--continue N`; do not claim
warm-start data was consumed.

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
`initial_configurations_from_history`. The payload also echoes
`warm_start_strategy` (the only supported value is `topk`) alongside `enabled`,
`audit`, and `audit_markdown` pointer fields.

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
trade-off, history, or next-range questions. The run report and evaluations
log are backend-specific: only one main report `.json` and one evaluations
`.jsonl` pair is present, matching the resolved backend:

```text
reports/optimizer_insight_report.json
reports/optimizer_run_report.json
reports/native_turbo_optimizer_report.json
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

`ic-opt` is not on PATH. Run it from the tool repository root as
`./.venv/bin/ic-opt`, or `source .venv/bin/activate` first. Requires Python
3.11+.

Local:

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
./.venv/bin/ic-opt PROJECT_DIR --real
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Remote:

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`--ssh-profile PROFILE` selects the remote execution profile. It is not an
optimizer or resource override.

Use `--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup path. Cadence setup is looked up as `--cadence-cshrc` when given,
otherwise `<REMOTE_PROJECT_DIR>/cadence_env.csh` on the remote host.

`./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration` is a local
optimize-only first-run gate: it stops before real Spectre/OCEAN candidate
execution and reports `stopped_before` (`run-openbox-real` or
`run-native-turbo-real`) in `reports/optimizer_flow_run_report.json`. It does
not support continuation, fix-run, or remote mode.

### Remote Artifact Locations

Remote runs keep the authoritative report/run tree on the remote host at
`PROJECT_DIR/reports/...` (also `runs/`, `ledger/`, `state/`). The Controller
mirrors the same tree into a local cache at
`~/.ic-opt/remote_runs/<ssh_profile>/<sha256[:16] of profile+remote path>/`,
which also holds the frozen snapshot used for the run. The CLI prints both
paths after a remote run or doctor pass (`local report: ...` then `remote
report: ...`); read those printed paths instead of recomputing the digest.

### Monitoring A Long-Running Optimizer Run

The product CLI has no progress subcommand. While a run is in flight, read
`state/optimizer_state.json` and `state/best_candidate.json` directly, or use
the developer CLI's `hermes-workflow optimizer-status` command as an accepted
exception to "use product CLI instead of low-level developer commands" —
it is a read-only status query, not a workflow-changing action.

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
- `algorithm: openbox`, `strategy: openbox_auto` — this is the default an
  OpenBox project resolves to when `strategy` is omitted, and it is used
  explicitly by the sanitized `opt_requirement.multi_testbench.md` and
  `opt_requirement.history_warm_start.md` templates. Do not treat
  `openbox_auto` in a requirement as an invalid or unrecognized value.
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO is a fit when legal variable steps are fine enough that snapping a
continuous candidate to the legal grid is a small perturbation. Prefer
`openbox_prf_eic` for coarse integer grids, categorical choices, or
duplicate-heavy snapped spaces.

`random_baseline` is diagnostic.

## Fix-Run Artifact Checklist

For fix-run workflows, inspect `reports/fix_run_report.json` first. Its
`points[]` array is the authoritative source of artifact paths for each fixed
point — `run_id`, `scalar_metric_manifest_paths`, `waveform_export_manifest_paths`,
and `csv_artifact_paths` — because the on-disk layout depends on the project
shape (testbenches × corners, testbenches only, corners only, or neither) and
`<run_id>` increments per fixed point starting at `real_001` (`real_002`,
`real_003`, ...), it does not stay fixed at `real_001`.

Confirm:

- `workflow_mode` is `fix_run`
- expected testbench/corner child count matches the requirement
- waveform exports were written for every successful child
- all failures appear in `child_issues`
- optimizer state and optimizer decision reports were not created

`FixRunReport` does not carry `parallel_jobs` or `threads_per_run` fields, so
do not ask to "confirm they were inherited" from the report alone:
`threads_per_run` can be read from a child's
`result_manifest.json.command_trace` (the Spectre `+mt=<n>` flag);
`parallel_jobs` is not recorded in any run artifact and can only be compared
against the requirement's `Spectre Settings.parallel_jobs` or the rendered
`config/spectre.yaml`.

## Optimization Artifact Checklist

`reports/optimizer_flow_run_report.json` is the final success marker for an
optimizer workflow run — a passing status is only published after parent/child
manifests are verified. Do not treat a zero exit code as a substitute for
reading it.

For optimizer workflows, inspect:

```text
reports/optimizer_flow_run_report.json
reports/optimizer_run_acceptance_report.json
reports/optimizer_completion_report.json
reports/optimizer_finalize_report.json
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/native_turbo_optimizer_report.json
reports/optimizer_decision_report.json
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

`supervisor_instruction.json` at the project root is the approval-gate record
(`decision` and `reason` fields), written before the real backend starts; check
it first if a run fails at the `approve` step.

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
