# Multi-Testbench Single-Corner Optimization Requirement

Use this template when each optimizer candidate must be evaluated by more than
one Maestro/ADE testbench at each testbench source point corner.

## Project

```yaml
project_name: mixer_multi_tb_opt
description: Optimize one Mixer candidate across CG/NF and gain testbenches
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /absolute/path/to/Mixer_CS_CG_NF/point_root
    virtuoso_library: Virtuoso_Bridge_test
    cell: MixerCS_PSS_CG_Noise
    design_view: maestro
    maestro_view: maestro
    test_name: Mixer_CS_CG_NF
    corner: Nominal
  - id: gain
    maestro_point_root: /absolute/path/to/Mixer_CS_GAIN/point_root
    virtuoso_library: Virtuoso_Bridge_test
    cell: MixerCS_PSS_Gain
    design_view: maestro
    maestro_view: maestro
    test_name: Mixer_CS_GAIN
    corner: Nominal
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

## Metrics

```yaml
- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: 'value(getData("NF" ?result "pnoise") 3e+09)'
- name: MAX_GAIN
  unit: dB
  testbench: gain
  ocean_expression: 'ymax(getData("gain" ?result "pac"))'
```

## Constraints

```yaml
- metric: NF_3G
  op: lt
  value: 9 dB
- metric: MAX_GAIN
  op: gt
  value: 5 dB
```

## Objective

```yaml
direction: minimize
expression: NF_3G - 0.1 * MAX_GAIN
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

## Optimizer Settings

```yaml
algorithm: openbox
strategy: openbox_prf_eic
initialization: sobol
max_evaluations: 30
batch_size: 10
random_seed: 20260528
optimizer_cpu_threads: 32
failure_penalty: 1000000.0
deduplicate_candidates: true
```

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
