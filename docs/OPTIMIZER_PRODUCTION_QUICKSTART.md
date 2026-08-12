# Production Quickstart

Use this path for a real Maestro-exported Spectre/OCEAN optimization or
fix-run project.

This file is an English subset of `docs/USER_GUIDE_CN.md`, which is the
maintained primary reference; the full Chinese guide is authoritative and this
file is kept in sync with it, not the other way around.

## Install

Clone the repository, then install from the release root:

```bash
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
```

IC Auto Opt requires Python 3.11 or newer for the interpreter used to create
the virtual environment (`pyproject.toml` declares `requires-python = ">=3.11"`,
and the source uses 3.11-only syntax). EDA servers often ship an older default
`python3`; use the site's `python3.11` (or newer) command if so.

```bash
python3 -m venv .venv   # use python3.11 (or newer) here if the site python3 is older
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Check the entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## Prepare The Project

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

`opt_requirement.md` supplies workflow mode, budget, batch size, Spectre
resources, optimizer CPU cap, algorithm, strategy, initialization, output
format, testbenches, process corners, metrics, objective, constraints, fixed
points, and waveform exports.

For each testbench, run one known-good Maestro/ADE point first. Put the point
root in `opt_requirement.md`; it must contain:

```text
<maestro_point_root>/netlist/input.scs
```

The value should be the Maestro result point directory itself, not the
`input.scs` file and not the `psf/` directory. The usual shape is:

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

Example:

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

Use the actual `Interactive.N` number and final testbench directory produced by
your Maestro run.

Start from one of:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.openbox_gp_eic.md
examples/spectre_maestro_project/opt_requirement.turbo.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
examples/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md
examples/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
```

Use the explicit GP-EIC or TuRBO files when optimizer selection must be
unambiguous. Multi-testbench files demonstrate complete measurement routing.
History warm-start files cover source-point and multi-corner OpenBox reuse.
The three fix-run files cover waveform-only, metrics-only, and combined
multi-testbench fixed-point characterization.

In fix-run mode, `parallel_jobs` controls child testbench/corner concurrency
inside one fixed point. `threads_per_run` remains per Spectre process. Multiple
fixed points are still processed serially.

## Configure Cadence

**Local mode**: provide a `csh`/`tcsh` setup file through one of:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

The setup must expose `spectre`, `ocean`, and license tools.

**Remote mode**: the four-level lookup above does not apply.
`IC_OPT_CADENCE_CSHRC` and `~/.ic-opt/cadence_env.csh` are not consulted.
Remote mode only accepts one of:

```text
--cadence-cshrc PATH
<remote PROJECT_DIR>/cadence_env.csh
```

If `--cadence-cshrc` is not passed, the workflow falls back to
`cadence_env.csh` under the remote project root, resolved on the remote host.

## Run

Doctor gate:

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

Real run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

Optional local optimize-only dry orchestration gate (stops before the real
backend starts running Spectre/OCEAN candidates; not a continuation, not
fix-run, not a remote entrypoint):

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
```

Continuation:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Optional History Warm Start is for a new optimize project that references
previous same-circuit project directories through the `History Warm Start`
section in `opt_requirement.md`; the workflow renders that section to
`config/history_warm_start.yaml`.
It is not a CLI flag, is not supported for fix-run, and must not be combined
with `--continue N`. Treat `reports/history_warm_start_audit.json` and
`openbox.history_warm_start` in `reports/optimizer_run_report.json` as the
acceptance proof before saying previous history was applied.

Remote:

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

Every remote continuation re-runs remote Doctor on the current remote host
first; it only resumes the frozen snapshot, syncs history, and starts the
backend once environment, tooling, requirement, and dirty-state checks pass.

## Check Status

Before a real run, validate the requirement offline (no simulation):

```bash
./.venv/bin/hermes-workflow check-requirement PROJECT_DIR
```

During or after a long run, inspect progress, best observed result,
evaluation/status counts, and whether continuation is recommended:

```bash
./.venv/bin/hermes-workflow optimizer-status PROJECT_DIR
```

## Read Reports

Start with:

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/fix_run_report.json
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
```

`reports/optimizer_flow_run_report.json` is the top-level flow marker; the CLI
prints its path on both success and failure. Check its `status` field first.

The optimizer run report and evaluations jsonl are backend-specific and are
not both written by the same run:

- OpenBox: `reports/optimizer_run_report.json` +
  `reports/optimizer_evaluations.jsonl`
- native TuRBO: `reports/native_turbo_optimizer_report.json` +
  `reports/native_turbo_optimizer_evaluations.jsonl`

A native TuRBO project will never write `reports/optimizer_run_report.json`;
checking for it there does not mean the run failed.

For real Spectre/OCEAN evidence, inspect:

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

If `keep_successful_runs`/`keep_failed_runs` retention is `false`, the
`runs/real/<run_id>` directory itself is deleted after archiving; evidence is
preserved under `state/run_retention_evidence/<run_id>/` and
`state/run_retention/<run_id>.json` instead. A missing run directory does not
by itself mean the run failed — check the retention evidence first.

For multi-testbench or multi-corner runs, inspect parent aggregate manifests.

For fix-run, verify `reports/fix_run_report.json`, waveform export manifests,
and CSV files under each successful child run. Fix-run must not create
optimizer state or optimizer decision reports.

## Agent Use

Give the agent:

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

The agent should run the product CLI and verify artifacts before reporting
success.
