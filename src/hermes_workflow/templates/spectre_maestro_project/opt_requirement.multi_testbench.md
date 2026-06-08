# Multi-Testbench Optimization Requirement

Use this reference when one optimizer candidate needs metrics from more than
one Maestro/ADE testbench. Each `maestro_point_root` must point to a
single-point Maestro/ADE result directory that contains `netlist/input.scs`.
The correct directory is the leaf run directory that usually contains both
`netlist/` and `psf/`, for example
`.../results/maestro/Interactive.45/1/<run_name>/`. Do not use the parent
`Interactive.<N>` directory or the `netlist/` subdirectory itself.
The same evaluation model also supports a single testbench; use this file only
when one candidate needs metrics from multiple Maestro/ADE setups.

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
  ocean_expression: bandwidth(db(((vh('pac "/IF_P" '-1) - vh('pac "/IF_N" '-1)) / (vh('pac "/RF_P" '(0)) - vh('pac "/RF_N" '(0))))) 3 "low")

- name: MAX_GAIN
  unit: dB
  testbench: cg_nf
  ocean_expression: ymax(ymax(db(((vh('pac "/IF_P" '-1) - vh('pac "/IF_N" '-1)) / (vh('pac "/RF_P" '(0)) - vh('pac "/RF_N" '(0)))))))

- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)

- name: IIP3
  unit: dBm
  testbench: iip3
  ocean_expression: rapidIIPN("pac_ip3")

- name: P1DB
  unit: dBm
  testbench: p1db
  ocean_expression: compressionVRI((v("/IF_P" ?result "pss_fd") - v("/IF_N" ?result "pss_fd")) '1 ?rport resultParam("PORT2:r" ?result "pss_fd") ?gcomp 1)
```

## Constraints

```yaml
- metric: BW
  op: gt
  value: "19e9 Hz"
- metric: MAX_GAIN
  op: gt
  value: "4 dB"
- metric: NF_3G
  op: lt
  value: "12 dB"
- metric: IIP3
  op: gt
  value: "0 dBm"
- metric: P1DB
  op: gt
  value: "-2 dBm"
```

## Objective

```yaml
direction: maximize
expression: >-
  0.7*min(
    max(0,min(1,10*(ln(BW/19e9)/ln(10))/0.5)),
    max(0,min(1,(MAX_GAIN-4)/0.5)),
    max(0,min(1,(12-NF_3G)/0.1)),
    max(0,min(1,(IIP3-0)/0.5)),
    max(0,min(1,(P1DB+2)/0.5))
  )
  +0.3*(
    0.15*max(0,min(1,10*(ln(BW/19e9)/ln(10))/0.5))
    +0.10*max(0,min(1,(MAX_GAIN-4)/0.5))
    +0.25*max(0,min(1,(12-NF_3G)/0.1))
    +0.30*max(0,min(1,(IIP3-0)/0.5))
    +0.20*max(0,min(1,(P1DB+2)/0.5))
  )
```

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 12
timeout_s: 3600
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

## Optimizer Settings

```yaml
algorithm: openbox
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
