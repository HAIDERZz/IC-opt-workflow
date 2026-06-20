# Production Quickstart

Use this path for a real Maestro-exported Spectre/OCEAN optimization or
fix-run project.

## Install

From the release root:

```bash
python3 -m venv .venv
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
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

Use `opt_requirement.multi_testbench.md` and `opt_requirement.multi_tb_corner.md`
for real-run-based Mixer multi-testbench structures with separate CG/NF/BW,
IIP3, and P1dB metric ownership. Use `opt_requirement.history_warm_start.md`
for a verified second-round same-circuit history run. Use
`opt_requirement.fix_run.md` for fixed-point characterization and waveform CSV
export. It is based on a real validated 15-corner Mixer requirement.

In fix-run mode, `parallel_jobs` controls child testbench/corner concurrency
inside one fixed point. `threads_per_run` remains per Spectre process. Multiple
fixed points are still processed serially.

## Configure Cadence

Provide a `csh`/`tcsh` setup file through one of:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

The setup must expose `spectre`, `ocean`, and license tools.

## Run

Doctor gate:

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

Real run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
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
```

## Read Reports

Start with:

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/fix_run_report.json
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
```

For real Spectre/OCEAN evidence, inspect:

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

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
