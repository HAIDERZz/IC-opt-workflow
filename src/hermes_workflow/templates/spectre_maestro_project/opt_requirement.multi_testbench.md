# Multi-Testbench Optimization Requirement

Use this reference when one optimizer candidate needs metrics from more than
one Maestro/ADE testbench. Each `maestro_point_root` must point to a
single-point Maestro/ADE result directory that contains `netlist/input.scs`.

## Project

```yaml
project_name: mixer_multi_tb_opt
description: Optimize one Mixer candidate across CG/NF/BW, IIP3, and P1dB testbenches
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: CG_NF_Test
    corner: Nominal

  - id: iip3
    maestro_point_root: /absolute/path/to/IIP3_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: IIP3_Test
    corner: Nominal

  - id: p1db
    maestro_point_root: /absolute/path/to/P1dB_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: P1dB_Test
    corner: Nominal
```

## Design Variables

```yaml
- name: F
  kind: integer
  lower: "14"
  upper: "30"
  step: "2"
- name: W
  kind: continuous_step
  lower: "0.4u"
  upper: "2u"
  step: "0.2u"
- name: L
  kind: continuous_step
  lower: "30n"
  upper: "50n"
  step: "10n"
- name: VB_LO
  kind: continuous_step
  lower: "150m"
  upper: "350m"
  step: "20m"
```

## Metrics

```yaml
- name: BW
  unit: Hz
  testbench: cg_nf
  ocean_expression: bandwidth(db20(v("/MIXER_P" ?result "pac") - v("/MIXER_N" ?result "pac")) 3 "low")

- name: MAX_GAIN
  unit: dB
  testbench: cg_nf
  ocean_expression: ymax(db20(v("/MIXER_P" ?result "pac") - v("/MIXER_N" ?result "pac")))

- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)

- name: IIP3
  unit: dBm
  testbench: iip3
  ocean_expression: value(getData("IIP3" ?result "iip3") 3e+09)

- name: P1DB
  unit: dBm
  testbench: p1db
  ocean_expression: value(getData("P1dB" ?result "p1db") 3e+09)
```

## Constraints

```yaml
- metric: BW
  op: gt
  value: "18e9 Hz"
- metric: MAX_GAIN
  op: gt
  value: "4 dB"
- metric: NF_3G
  op: lt
  value: "12 dB"
- metric: IIP3
  op: gt
  value: "-5 dBm"
- metric: P1DB
  op: gt
  value: "-15 dBm"
```

## Objective

```yaml
direction: minimize
expression: "NF_3G / (MAX_GAIN * BW)"
```

## Process Corners

```yaml
objective_policy: nominal
constraint_policy: nominal
corners:
  - id: nominal
```

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 10
timeout_s: 3600
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

## Optimizer Settings

```yaml
algorithm: openbox
strategy: openbox_auto
initialization: sobol
max_evaluations: 100
batch_size: 10
random_seed: 20260528
optimizer_cpu_threads: 4
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
