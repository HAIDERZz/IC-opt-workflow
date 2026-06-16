# Writing `opt_requirement.md`

`opt_requirement.md` is the contract for the first real workflow run. It
selects the mode and carries the machine-critical values for that mode. Do not
use command-line flags to override those values for the first run.

Supported modes:

- `mode: optimize`: optimizer-driven search
- `mode: fix_run`: fixed-point Spectre/OCEAN characterization and waveform CSV
  export

The product command-line entry kept for optimizer run extension is
continuation:

```bash
ic-opt <project> --real --continue N
```

## Example Files

This directory contains five requirement templates.

| File | Use when |
| --- | --- |
| `opt_requirement.md` | one testbench optimization, source point corner |
| `opt_requirement.multi_corner.md` | one testbench optimization, multiple process corners |
| `opt_requirement.multi_testbench.md` | multiple testbench optimization, source point corner |
| `opt_requirement.multi_tb_corner.md` | multiple testbench optimization, multiple process corners |
| `opt_requirement.fix_run.md` | fixed point run across 15 process/corner-variable combinations with waveform CSV export |

The fix-run template is based on a real validated local and remote 15-corner
Mixer requirement. For a real project, copy the relevant template to
`<project>/opt_requirement.md`, then replace private paths and circuit-specific
values.

## Shared Sections

Each section must appear once and contain one fenced `yaml` block.

All real workflow requirements use:

```text
Workflow
Project
Maestro Source
Spectre Settings
Approval Checklist
```

Optimization requirements also use:

```text
Design Variables
Metrics
Constraints
Objective
Optimizer Settings
```

Fix-run requirements also use:

```text
Fixed Points
Waveform Exports
```

Multi-corner templates include:

```text
Process Corners
```

## Workflow

Optimization:

```yaml
schema_version: "1.0"
mode: optimize
starting_run_id: real_001
```

Fix-run:

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

If the `Workflow` section is omitted, the file is treated as an optimization
requirement for backward compatibility.

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

Multi-testbench projects use `testbenches:`. Each metric or waveform export
then uses a `testbench:` routing key.

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /absolute/path/to/CG_NF_Test/point_root
    virtuoso_library: Virtuoso_Bridge_test
    cell: MixerCS_PSS_CG_Noise
    design_view: maestro
    maestro_view: maestro
    test_name: Mixer_CS_CG_NF
    corner: Nominal
```

`maestro_point_root` must be the Maestro/ADE result point directory that
contains `netlist/input.scs`. Do not point to `input.scs` directly.

## Process Corners

Use `Process Corners` when the same candidate or fixed point must be evaluated
across several model sections or corner variables.

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

`variables` are generic netlist parameter overrides. A variable named
`temperature` is not special-cased by the workflow.

## Optimization Metrics

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

Optimizer metrics are scalar. Full waveform CSV export belongs in fix-run
`Waveform Exports`.

## Fix-Run Fixed Points

`Fixed Points` lists the exact parameters to simulate:

```yaml
schema_version: "1.0"
points:
  - candidate_id: user_point_001
    parameters:
      F: '24'
      W: 0.8u
      L: 30n
```

Each parameter name must match a design variable or a top-level Spectre
parameter in the imported deck.

## Fix-Run Waveform Exports

`Waveform Exports` lists OCEAN waveform expressions to export as CSV:

```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    testbench: cg_nf
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

`nil_policy: fail` makes a missing waveform fail the child run instead of
silently producing incomplete evidence.

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 1
timeout_s: 7200
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

`threads_per_run` maps to Spectre `+mt`. `parallel_jobs` is Spectre process
concurrency for candidate or fixed-point children. `output_format` is `psfxl`.

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

`random_baseline` is for diagnostics, not production optimization.

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```

All values must be `true` before real-tool execution.

## Check The File

Run:

```bash
hermes-workflow check-requirement <project>
hermes-workflow prepare-from-requirement <project>
hermes-workflow validate <project>
hermes-workflow check-project-ready <project>
```

For production execution, read `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`.
