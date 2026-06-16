# Single-Testbench Single-Corner Optimization Requirement

Template derived from the verified Mixer requirement. Replace only the Maestro/ADE point path and bounds that belong to your circuit. This mode evaluates one testbench at the source point corner.

## Project

```yaml
project_name: mixer_cg_nf_opt
description: Optimize one Mixer CG/NF/BW testbench from one Maestro/ADE point
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
virtuoso_library: Virtuoso_Bridge_test
cell: MixerCS_PSS_CG_Noise
design_view: schematic
maestro_view: maestro
test_name: Mixer_CS_CG_NF
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
- name: FCS
  kind: integer
  lower: '40'
  upper: '56'
  step: '2'
- name: WCS
  kind: continuous_step
  lower: 0.6u
  upper: 1.2u
  step: 0.2u
- name: LCS
  kind: continuous_step
  lower: 30n
  upper: 50n
  step: 10n
- name: VB_RF
  kind: continuous_step
  lower: 300m
  upper: 440m
  step: 20m
```

## Metrics

```yaml
- name: BW
  unit: Hz
  ocean_expression: bandwidth(db((harmonic((v("/IF_P" ?result "pac") - v("/IF_N" ?result "pac")) '-1) / harmonic(drplPacVolGnExpDen("(v(\"/RF_P\" ?result \"pac\")-v(\"/RF_N\" ?result \"pac\"))" '(0) nil) '-1))) 3 "low")
- name: MAX_GAIN
  unit: dB
  ocean_expression: ymax(db((harmonic((v("/IF_P" ?result "pac") - v("/IF_N" ?result "pac")) '-1) / harmonic(drplPacVolGnExpDen("(v(\"/RF_P\" ?result \"pac\")-v(\"/RF_N\" ?result \"pac\"))" '(0) nil) '-1))))
- name: NF_3G
  unit: dB
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)
```

## Constraints

```yaml
- metric: BW
  op: gt
  value: 28e9 Hz
- metric: MAX_GAIN
  op: gt
  value: 5.5 dB
- metric: NF_3G
  op: lt
  value: 9 dB
```

## Objective

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

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
