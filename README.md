# IC Auto Opt Workflow

`ic-auto-opt-workflow` is a requirement-driven workflow for real IC
Spectre/OCEAN work. It supports two product modes:

- optimization: run an optimizer over approved design variables and metrics
- fix-run: run user-specified fixed design points and export requested
  waveform CSV artifacts without creating optimizer state

Both modes are selected in `PROJECT_DIR/opt_requirement.md`. The product CLI
does not use a separate fix-run switch.

## Product Entry

Doctor check:

```bash
ic-opt /path/to/project --doctor
```

Run the workflow described by `opt_requirement.md`:

```bash
ic-opt /path/to/project --real
```

Continue an existing optimization run:

```bash
ic-opt /path/to/project --real --continue N
```

Remote execution through an SSH profile:

```bash
ic-opt --ssh-profile PROFILE /remote/project --doctor
ic-opt --ssh-profile PROFILE /remote/project --real
```

`--continue N` is only for existing optimizer runs. First-run budget, batch
size, parallelism, Spectre thread count, optimizer CPU cap, algorithm, strategy,
initialization, process corners, output format, retention, objective,
constraints, fixed points, waveform exports, and metric routes all come from
`opt_requirement.md`.

### History Warm Start

Use `History Warm Start` when a new optimize project should learn from previous
same-circuit runs. This is different from `--continue N`: continuation only adds
budget to the same project and does not reread a changed `opt_requirement.md`.

```yaml
enabled: true
sources:
  - path: /path/to/previous_same_circuit_project
    label: round1
max_observations: 200
warm_start_strategy: topk
```

The section renders to `config/history_warm_start.yaml`. History warm-start is
optimize-only, cannot be combined with `--continue`, and is not supported for
fix-run. Current and previous projects must use the exact same variable names;
old objective and constraint values are not reused. Inspect
`reports/history_warm_start_audit.json`,
`reports/history_warm_start_audit.md`, and `openbox.history_warm_start` in
`reports/optimizer_run_report.json` before saying the history was applied.

### Optimizer Insight Report

Successful optimization flows run `visualize-optimizer-run` after optimizer
finalization and write:

```text
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
```

The HTML file is the first reader-facing report to inspect. The JSON file is
the machine-readable contract, and the Markdown file is a text fallback.

The report-layer Pareto/trade-off analyzer uses existing raw metrics from the
optimizer run. It does not enable OpenBox multi-objective optimizer mode, does
not change candidate selection, and does not rewrite the configured objective.

The Space Compression Advisory uses an OpenBox compressor dry-run on the
current variable contract and observed rows. Suggestions are advisory only:
they are not applied to optimizer execution. A user may copy reviewed suggested
ranges into a new `opt_requirement.md` for a later run.

## Project Directory

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. Use `constraints.md` for human guidance
and `context/` for notes, screenshots, or previous reports. Generated
directories such as `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, and
`state/` are created by the workflow.

## Requirement Templates

Start from one of these examples:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

The fix-run template is based on the real validated 15-corner Mixer
requirement. Replace only project-specific paths and circuit values.

## Workflow Modes

Optimization mode:

```yaml
Workflow:
  mode: optimize
```

If the `Workflow` section is omitted, the requirement is treated as an
optimization requirement for backward compatibility.

Fix-run mode:

```yaml
Workflow:
  mode: fix_run
  starting_run_id: real_001
```

Fix-run requirements include `Fixed Points` and optional `Waveform Exports`
sections. They do not include optimizer settings and do not create
`state/optimizer_state.json` or `reports/optimizer_decision_report.md`.

## Optimization Requirements

Optimization `opt_requirement.md` files define:

- Maestro/ADE point roots and testbench routes
- OCEAN scalar metric expressions
- design variables, legal ranges, and steps
- objective and constraints
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- license probe, retention, and artifact policy
- Process Corners and multi-corner policies

Production strategy choices are peers:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`random_baseline` is for diagnostics. See
`docs/OPTIMIZER_ALGORITHM_MODES.md`.

## Fix-Run Requirements

Fix-run `opt_requirement.md` files define:

- `Workflow.mode: fix_run`
- one or more fixed candidate points
- Maestro/ADE point roots and testbench routes
- Spectre settings and Process Corners
- optional waveform CSV exports, for example
  `getData("NF" ?result "pnoise")`
- the same approval checklist used by real optimization runs

The 15-corner fix-run example uses TT/SS/FF model sections and five corner
variable values per section. The `temperature` field in that example is a
generic netlist parameter override; the workflow does not special-case that
name.

In fix-run mode, Spectre `parallel_jobs` controls the maximum number of
testbench/corner child runs for one fixed point that may run concurrently.
`threads_per_run` remains the Spectre `+mt` thread count for each child process.
Fixed points are processed serially in this release, and there is no CLI
override for fix-run parallelism.

## Install

From the release root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Check entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## Cadence Environment

The Cadence/Spectre/OCEAN setup is user supplied. Configure it through one of:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

Use doctor before real runs:

```bash
ic-opt /path/to/project --doctor
```

When `require_license_check: true`, doctor runs the real Spectre/license probe
and writes `reports/license_probe_report.json`.

## Agent Use

For agent-assisted operation, give the agent:

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

The agent should use the same product CLI and inspect workflow artifacts before
reporting success.

## Workflow Evidence

Optimization evidence:

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

Fix-run evidence:

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

Multi-testbench and multi-corner optimization runs also write parent aggregate
manifests. Artifacts record requirement pass-through, command traces, license
probe status, selected candidate, and reported metrics.

## Current Release

Version `0.1.8` includes:

- local and remote fix-run workflow support
- fix-run child-level parallelism through `Spectre Settings.parallel_jobs`
- waveform CSV export manifests for fix-run child runs
- requirement template `opt_requirement.fix_run.md`
- requirement-driven local and remote optimization
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO
- multi-testbench and multi-corner support
- psfxl-only metric flow
- real license probe doctor gate
- sanitized Spectre/OCEAN command trace artifacts
- optimizer CPU thread-limit runtime audit
- release examples and agent skill guidance synchronized with the current CLI

See `RELEASE_NOTES_v0.1.8.md`.
