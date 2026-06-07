# Optimization Requirement

## Project

```yaml
project_name: bridge_test_inv
description: Optimize inverter sizing from an existing Maestro testbench
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
maestro_point_root: /absolute/path/to/maestro/results/maestro/Interactive.N/1/LIB_CELL_1
virtuoso_library: Virtuoso_Bridge_test
cell: bridge_test_inv
design_view: schematic
maestro_view: maestro
test_name: tran_dc_test  # optional metadata
corner: Nominal          # optional metadata
```

## Design Variables

```yaml
- name: FN
  kind: integer
  lower: "2"
  upper: "12"
  step: "1"
- name: WN
  kind: continuous_step
  lower: "0.3u"
  upper: "3u"
  step: "0.2u"
- name: FP
  kind: integer
  lower: "2"
  upper: "12"
  step: "1"
- name: WP
  kind: continuous_step
  lower: "0.3u"
  upper: "3u"
  step: "0.2u"
```

## Metrics

```yaml
- name: rise
  unit: s
  ocean_expression: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
  result: tran           # optional selectResult hint
  required_signals:
    - /VOUT              # optional diagnostic hint
- name: fall
  unit: s
  ocean_expression: fallTime(VT("/VOUT") 0.9 nil 0 nil 10 90 nil "time")
  result: tran           # optional selectResult hint
  required_signals:
    - /VOUT              # optional diagnostic hint
- name: DC
  unit: W
  ocean_expression: VDC("/VDD") * IDC("/M0/S")
  result: tran           # optional selectResult hint
  required_signals:
    - /VDD               # optional diagnostic hint
    - /M0/S              # optional diagnostic hint
```

## Constraints

```yaml
- metric: rise
  op: lt
  value: "80e-12 s"
- metric: fall
  op: lt
  value: "80e-12 s"
- metric: DC
  op: lt
  value: "4e-4 W"
```

## Objective

```yaml
direction: minimize
expression: "(rise + fall) * DC"
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
initialization: sobol
max_evaluations: 100
batch_size: 10
random_seed: 20260528
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
