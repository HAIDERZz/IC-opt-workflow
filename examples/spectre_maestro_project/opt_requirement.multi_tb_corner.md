# Multi-Testbench Multi-Corner Optimization Requirement

Use this reference when one optimizer candidate needs metrics from multiple
Maestro/ADE testbenches and each candidate should also be checked across
multiple process corners. Multi-corner is configured in `Process Corners`. Inside one candidate, the
workflow runs `testbench x corner` serially, so `parallel_jobs`
still means candidate-level concurrency only.

Monte Carlo is intentionally deferred from this flow. Use it after optimization
as follow-up validation on the chosen candidate.

## Project

```yaml
project_name: mixer_multi_tb_corner_opt
description: Optimize one Mixer candidate across CG/NF/BW, IIP3, and P1dB testbenches plus TT/SS/FF corners
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
    virtuoso_library: MixerLib
    cell: mixer_top
    design_view: schematic
    maestro_view: maestro
    test_name: CG_NF_Test
    corner: Nominal
  - id: iip3
    maestro_point_root: /absolute/path/to/IIP3_Test/point_root
    virtuoso_library: MixerLib
    cell: mixer_top
    design_view: schematic
    maestro_view: maestro
    test_name: IIP3_Test
    corner: Nominal
  - id: p1db
    maestro_point_root: /absolute/path/to/P1dB_Test/point_root
    virtuoso_library: MixerLib
    cell: mixer_top
    design_view: schematic
    maestro_view: maestro
    test_name: P1dB_Test
    corner: Nominal
```

## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: "-40"
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
  ocean_expression: bandwidth(db(((vh('pac 3 "low")))))
- name: MAX_GAIN
  unit: dB
  testbench: cg_nf
  ocean_expression: ymax(ymax(db(((vh('pac'))))))
- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("NF" "pnoise") 3e+09)
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
  + 0.3*(
    0.15*max(0,min(1,10*(ln(BW/19e9)/ln(10))/0.5)) +
    0.10*max(0,min(1,(MAX_GAIN-4)/0.5)) +
    0.25*max(0,min(1,(12-NF_3G)/0.1)) +
    0.30*max(0,min(1,(IIP3-0)/0.5)) +
    0.20*max(0,min(1,(P1DB+2)/0.5))
  )
```

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 6
timeout_s: 3600
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

## Optimizer Settings

```yaml
algorithm: openbox
strategy: openbox_prf_eic
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
