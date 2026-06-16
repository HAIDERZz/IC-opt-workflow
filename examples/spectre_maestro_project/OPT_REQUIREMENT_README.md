# Writing `opt_requirement.md`

`opt_requirement.md` is the contract for a first optimizer run. Put optimizer
budget, batch size, Spectre parallelism, Spectre threads, optimizer CPU limit,
algorithm choice, metric formulas, bounds, and process corners in this file.
Do not use command-line flags to override those values for the first run.

The product command-line entry kept for run extension is continuation:
`ic-opt <project> --continue N`.

## Example Files

This directory contains four requirement templates. They are generated from the
same verified Mixer requirement and use the same OCEAN formulas after replacing
private Maestro result paths with placeholders.

| File | Use when |
| --- | --- |
| `opt_requirement.md` | one testbench, source point corner |
| `opt_requirement.multi_corner.md` | one testbench, multiple process corners |
| `opt_requirement.multi_testbench.md` | multiple testbenches, source point corner |
| `opt_requirement.multi_tb_corner.md` | multiple testbenches, multiple process corners |
| `opt_requirement.fix_run.md` | fixed-point simulation, no optimizer |

For a real project, copy one template to `<project>/opt_requirement.md`, then
replace `maestro_point_root`, project metadata, variable bounds, constraints,
and metric formulas with values from your circuit.

## Required Sections

Each required section must appear once and contain one fenced `yaml` block.

```text
Project
Maestro Source
Design Variables
Metrics
Constraints
Objective
Spectre Settings
Optimizer Settings
Approval Checklist
```

Multi-corner templates also include:

```text
Process Corners
```

## Maestro Source

Single-testbench projects use a top-level Maestro source:

```yaml
maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
virtuoso_library: Virtuoso_Bridge_test
cell: MixerCS_PSS_CG_Noise
design_view: schematic
maestro_view: maestro
test_name: Mixer_CS_CG_NF
corner: Nominal
```

Multi-testbench projects use `testbenches:`. Each metric then uses a
`testbench:` routing key.

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
    virtuoso_library: Virtuoso_Bridge_test
    cell: MixerCS_PSS_CG_Noise
    design_view: schematic
    maestro_view: maestro
    test_name: Mixer_CS_CG_NF
    corner: Nominal
```

`maestro_point_root` must be the Maestro/ADE result point directory that
contains `netlist/input.scs`. Do not point to `input.scs` directly.

## Process Corners

Use `Process Corners` when the same candidate must be evaluated across several
model sections or corner variables.

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: '27'
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: '125'
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: '-40'
```

Inside one candidate, the workflow runs each `testbench x corner` child and
aggregates the child metric results according to the objective and constraint
policies.

## Design Variables

Every variable is a separate YAML list item.

```yaml
- name: W
  kind: continuous_step
  lower: 0.6u
  upper: 1.2u
  step: 0.2u
- name: F
  kind: integer
  lower: '20'
  upper: '30'
  step: '2'
```

Supported kinds are `integer` and `continuous_step`. Variable names must match
the top-level `parameters` statement in the imported Spectre deck.

## Metrics

`ocean_expression` is copied into the OCEAN replay script. Hermes does not
rewrite or reinterpret Calculator/OCEAN formulas.

Single-testbench metric:

```yaml
- name: NF_3G
  unit: dB
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)
```

Multi-testbench metric:

```yaml
- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)
```

If the expression already names its result, such as
`getData("NF" ?result "pnoise")`, do not add a separate `result:` hint.

The optimizer metric path expects scalar values. Full waveform CSV export is a
separate characterization/export workflow, not an optimizer scalar metric.

## Constraints And Objective

Constraints reference metric names.

```yaml
- metric: NF_3G
  op: lt
  value: 9 dB
```

The objective expression references metric names, not OCEAN signals.

```yaml
direction: minimize
expression: -(0.2*min(max(0,min(1,10*(ln(BW/28e9)/ln(10))/0.6)),max(0,min(1,(MAX_GAIN-5.5)/2)),max(0,min(1,(9-NF_3G)/0.7)))+0.8*(0.20*max(0,min(1,10*(ln(BW/28e9)/ln(10))/0.6))+0.30*max(0,min(1,(MAX_GAIN-5.5)/2))+0.50*max(0,min(1,(9-NF_3G)/0.7))))
```

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 10
timeout_s: 7200
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

`threads_per_run` maps to Spectre `+mt`. `parallel_jobs` is candidate-level
Spectre process concurrency. Keep `batch_size <= parallel_jobs`.

`output_format` is `psfxl`.

## Optimizer Settings

```yaml
algorithm: turbo
strategy: turbo_trust_region
initialization: sobol
max_evaluations: 30
batch_size: 10
random_seed: 20260528
optimizer_cpu_threads: 32
failure_penalty: 1000000.0
deduplicate_candidates: true
```

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO is suitable when legal variable steps are fine enough that snapping a
continuous candidate to the legal grid is a small perturbation, for example
about `0.1u`. Avoid TuRBO for coarse finger-count-style grids or spaces that
produce many duplicate snapped candidates.

`random_baseline` is for diagnostics, not production optimization.

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```

All values must be `true` before real-tool execution.

## Fix-Run Mode

Fix-run mode runs Spectre/OCEAN simulations at user-specified design points
without an optimizer. Use it for characterization, verification, or waveform
export at known parameter values.

Set `Workflow.mode` to `fix_run` in `opt_requirement.md`:

```yaml
## Workflow
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

Run with the same command used for optimizer runs:

```bash
ic-opt PROJECT --real
```

The workflow detects `mode: fix_run` from the requirement file and dispatches
the fix-run path instead of the optimizer loop.

### What Comes From the Requirement File

- `Design Variables` — parameter declarations (bounds and steps)
- `Fixed Points` — one or more design points to simulate
- `Process Corners` — corners for each point (optional)
- `Waveform Exports` — OCEAN expressions to export as CSV

### Fix-Run Output

The output is a simulation archive, not an optimization report. There is no
`optimizer.yaml`, no `optimizer_state.json`, and no
`optimizer_decision_report.md`. Instead, inspect:

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

### Required Sections for Fix-Run

```text
Workflow
Project
Maestro Source
Design Variables
Spectre Settings
Fixed Points
Approval Checklist
```

At least one of `Metrics` or `Waveform Exports` must be present. `Optimizer
Settings`, `Constraints`, and `Objective` are not required in fix-run mode.

## Check The File

Run:

```bash
hermes-workflow check-requirement <project>
hermes-workflow prepare-from-requirement <project>
hermes-workflow validate <project>
hermes-workflow check-project-ready <project>
```

For production optimizer execution, read
`docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`.
