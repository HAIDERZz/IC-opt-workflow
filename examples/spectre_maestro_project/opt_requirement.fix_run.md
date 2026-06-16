# Fix-Run Simulation Requirement

Run Spectre/OCEAN simulations at user-specified design points and export
waveform data. This mode does not run an optimizer. All variables, fixed
points, process corners, and waveform expressions come from this file.

## Workflow

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

## Project

```yaml
project_name: mixer_fix_run_example
description: Fix-run example — simulate fixed Mixer points and export pnoise waveforms
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
maestro_point_root: /path/to/maestro/CG_NF_Test/point_root
virtuoso_library: Example_Library
cell: MixerCS_PSS_CG_Noise
design_view: schematic
maestro_view: maestro
test_name: Mixer_CS_CG_NF
corner: tt
```

## Design Variables

```yaml
- name: F
  kind: integer
  lower: '20'
  upper: '30'
  step: '2'
- name: W
  kind: continuous_step
  lower: 0.6u
  upper: 1.2u
  step: 0.2u
- name: L
  kind: continuous_step
  lower: 30n
  upper: 40n
  step: 10n
- name: VB_LO
  kind: continuous_step
  lower: 280m
  upper: 400m
  step: 20m
```

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 4
parallel_jobs: 1
timeout_s: 3600
require_license_check: true
keep_failed_runs: false
keep_successful_runs: true
```

## Process Corners

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

## Fixed Points

```yaml
schema_version: "1.0"
points:
  - candidate_id: nominal_point
    parameters:
      F: '24'
      W: 0.8u
      L: 30n
      VB_LO: 340m
```

## Waveform Exports

```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    testbench: Mixer_CS_CG_NF
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
