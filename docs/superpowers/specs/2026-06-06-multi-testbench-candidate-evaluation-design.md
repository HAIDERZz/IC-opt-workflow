# Multi-Testbench Candidate Evaluation Design

Date: 2026-06-06

## Purpose

C-50 extends the proven single-testbench Spectre/OCEAN optimizer route to the
real Mixer use case where one circuit candidate must be evaluated by multiple
Maestro/ADE testbenches.

The first target is narrow: one optimizer candidate, one shared parameter set,
multiple preserved Maestro point-root netlist bundles, multiple Spectre/OCEAN
child runs, and one aggregated metric set for objective/constraint evaluation.

This is not a new optimizer framework. OpenBox/native TuRBO still generate
candidates. The C-7 Spectre/OCEAN adapter still runs standalone Spectre and
batch OCEAN. Hermes still validates manifests and records scalar outputs only.

## Problem

A Mixer cannot always be characterized by one testbench:

- CG/NF/BW may come from one pss/pac/pnoise testbench.
- IIP3 may require another testbench.
- P1dB may require another testbench.

The optimizer objective and constraints may depend on metrics from all of these
testbenches. Therefore a candidate cannot be accepted, rejected, or ranked from
only one Spectre/OCEAN run.

## Design Principle

Preserve the known-good Maestro/ADE foundation per testbench. Do not flatten
multiple testbenches into one synthetic Spectre deck and do not require the user
to hand-copy sidecars.

Each testbench has its own approved `maestro_point_root` and imported netlist
bundle. The same approved candidate parameters are rendered into every
testbench bundle. Metrics are computed by OCEAN from each child run and then
merged by metric name into one candidate-level observation.

## User Intake Shape

C-50 extends `opt_requirement.md` with an optional multi-testbench section. The
single-testbench C-49 shape remains valid.

Recommended multi-testbench source block:

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /path/to/CG_NF_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: CG_NF_Test
    corner: Nominal
  - id: iip3
    maestro_point_root: /path/to/IIP3_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: IIP3_Test
    corner: Nominal
  - id: p1db
    maestro_point_root: /path/to/P1dB_Test/point_root
    virtuoso_library: MixerLib
    cell: Mixer
    design_view: schematic
    maestro_view: maestro
    test_name: P1dB_Test
    corner: Nominal
```

Metrics declare which testbench produces them:

```yaml
- name: NF_3G
  unit: dB
  testbench: cg_nf
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)

- name: IIP3
  unit: dBm
  testbench: iip3
  ocean_expression: value(...)
```

`testbench` is not part of the OCEAN formula. It is a routing key that tells
Hermes and the execution agent which child run should evaluate that formula.

## Generated Project Shape

Single-testbench projects keep the current layout.

Multi-testbench projects add a testbench namespace under `netlists/` and
`runs/real/<run_id>/`:

```text
PROJECT_DIR/
├── config/
│   ├── project_config.yaml
│   ├── testbenches.yaml
│   ├── variables.yaml
│   ├── metrics.yaml
│   ├── spectre.yaml
│   └── optimizer.yaml
├── netlists/testbenches/
│   ├── cg_nf/
│   │   ├── exported/
│   │   └── templates/template.scs
│   ├── iip3/
│   │   ├── exported/
│   │   └── templates/template.scs
│   └── p1db/
│       ├── exported/
│       └── templates/template.scs
└── runs/real/real_001/
    ├── candidate.json
    ├── testbenches/
    │   ├── cg_nf/
    │   │   ├── netlist/input.scs
    │   │   ├── psf/
    │   │   ├── result_manifest.json
    │   │   └── metrics/metric_result_manifest.json
    │   ├── iip3/
    │   └── p1db/
    ├── result_manifest.json
    └── metrics/metric_result_manifest.json
```

The top-level manifests aggregate child manifest status. Existing single-run
manifest readers should continue to work after C-50 by seeing the candidate as
one real run with aggregated status and metrics.

## Execution Flow

For each optimizer candidate:

```text
candidate parameters
-> render the same parameters into every required testbench template
-> run each child Spectre/OCEAN job
-> collect each child metric_result_manifest.json
-> merge scalar metrics by approved metric name
-> evaluate constraints and objective once at candidate level
-> record one optimizer observation
```

The child jobs may run concurrently, but the global `spectre.parallel_jobs`
limit applies across all candidates and all testbenches. It is not multiplied
per testbench.

`spectre.threads_per_run` remains the single-Spectre `+mt` setting.
`optimizer.optimizer_cpu_threads` remains the Python optimizer math/threadpool
limit. It does not control Spectre child jobs.

## Failure Semantics

Candidate-level outcomes:

- `feasible`: all required metrics are scalar and constraints pass.
- `constraint_failed`: all required metrics are scalar, but one or more
  constraints fail.
- `metric_check_failed`: one or more required child metrics are missing,
  non-scalar, failed, nil, or non-finite.
- `real_check_failed`: one or more child Spectre/OCEAN tool runs fail before a
  valid metric manifest can be checked.

Partial child metrics should be preserved in child manifests and the aggregate
report, but a candidate should not be ranked as feasible unless all required
metrics for the objective and constraints are present.

## Non-Goals

C-50 does not:

- rewrite formulas;
- parse PSF;
- merge testbenches into one Spectre deck;
- create a new optimizer algorithm;
- change OpenBox/native TuRBO candidate generation;
- implement corners/sweeps/families;
- support metric name collisions;
- add a production scheduler beyond the existing global `parallel_jobs` cap.

## First Evidence Target

The first real evidence should use the user Mixer project and two testbenches
only:

```text
cg_nf + one additional user-provided point-root
```

The acceptance target is one approved candidate evaluated by both testbenches,
with one aggregated metric manifest. A full 100-point multi-testbench optimizer
run comes only after that single-candidate multi-testbench smoke succeeds.
