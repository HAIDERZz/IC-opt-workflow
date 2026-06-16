# Requirement.md Driven Config Intake Design

Date: 2026-06-05

## Purpose

C-49 adds the project entry interface for routine IC optimization use.

The user should not provide chat-only instructions, hand-copy `input.scs`, or
decide which Maestro/ADE sidecar files are required. Instead, the user creates a
project directory, writes a strict `opt_requirement.md`, optionally writes
`constraints.md`, and gives a Maestro point-root path. The supervisor agent and
Hermes workflow tooling then build the existing project config structure from
that stable input.

This design follows the veriflow-cc style: file-based user intent first, then
agent/tooling pipeline. It keeps the existing Hermes YAML contracts as the
execution source of truth.

## Directory Model

User-created project root:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

Generated or imported by the agent/Hermes workflow:

```text
~/spectre_opt_prj/<project_name>/
├── config/
│   ├── project_config.yaml
│   ├── variables.yaml
│   ├── metrics.yaml
│   ├── spectre.yaml
│   └── optimizer.yaml
├── netlists/
│   ├── imported_maestro_point/
│   ├── exported/
│   └── templates/
├── execution_package/
├── ledger/
├── reports/
├── runs/
└── state/
```

The user owns the Markdown input files. Hermes owns generated config files,
reports, state, execution packages, and run artifacts.

## Input Files

### `opt_requirement.md`

Required. This is the canonical user optimization request.

It uses fixed Markdown headings with fenced YAML blocks for machine-critical
fields. Free prose may appear around those blocks, but the fields that generate
contracts must live inside the approved YAML blocks.

Required sections:

```text
# Optimization Requirement
## Project
## Maestro Source
## Design Variables
## Metrics
## Constraints
## Objective
## Spectre Settings
## Optimizer Settings
## Approval Checklist
```

The recommended format is:

````markdown
# Optimization Requirement

## Project

```yaml
project_name: bridge_test_inv_opt
description: Optimize inverter sizing from an existing Maestro testbench
backend: maestro_exported_spectre_deck
```

## Maestro Source

```yaml
maestro_point_root: /home/zzchen/simulation/.../Interactive.9/1/Virtuoso_Bridge_test_bridge_test_inv_1
virtuoso_library: Virtuoso_Bridge_test
cell: bridge_test_inv
design_view: schematic
maestro_view: maestro
test_name: tran_dc_test
corner: Nominal
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
```

## Metrics

```yaml
- name: rise
  unit: s
  result: tran
  ocean_expression: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
  required_signals:
    - /VOUT
```

## Constraints

```yaml
- metric: rise
  op: lt
  value: "80e-12 s"
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
```

## Optimizer Settings

```yaml
algorithm: openbox
max_evaluations: 100
batch_size: 10
random_seed: 13
failure_penalty: 1000000000.0
deduplicate_candidates: true
```

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
````

### `constraints.md`

Optional. This file captures user preferences, reasoning, and decision guidance
that should influence supervisor-agent interpretation and next-step choices.

Examples:

- acceptable runtime budget;
- priority between power, speed, area, and robustness;
- when to continue optimization;
- when to stop and ask the user;
- preferred report emphasis;
- known circuit caveats.

`constraints.md` is not automatically converted into Spectre parameters,
metrics, OCEAN formulas, or optimizer constraints. If a constraint affects real
execution, it must be reflected explicitly in `opt_requirement.md` and then in
the generated YAML contracts.

### `context/`

Optional. This may contain user notes, screenshots, prior reports, circuit
knowledge, or reference results. It is supervisor-agent guidance only unless a
later approved contract explicitly incorporates it.

## Maestro Point Root Import

The user provides a `maestro_point_root`, not a manually organized netlist
bundle.

Expected source shape:

```text
maestro_point_root/
├── netlist/
│   ├── input.scs
│   ├── ade_e.scs
│   └── ...
└── psf/
    └── ...
```

The proven source example is:

```text
/home/zzchen/simulation/Virtuoso_Bridge_test/bridge_test_inv/maestro/results/maestro/Interactive.9/1/Virtuoso_Bridge_test_bridge_test_inv_1
```

`maestro_point_root/netlist/` is the source of truth for standalone Spectre
replay. Hermes must preserve it as a bundle. The old `psf/` directory may be
used as reference evidence, but optimizer runs generate new PSF data under the
project directory.

Generated project shape after import:

```text
PROJECT_DIR/
├── netlists/
│   ├── imported_maestro_point/
│   │   └── netlist/
│   ├── exported/
│   │   ├── input.scs
│   │   ├── ade_e.scs
│   │   └── ...
│   └── templates/
│       └── template.scs
```

Hermes should copy the full source `netlist/` bundle into
`netlists/exported/`. It must not require the user to choose sidecars.

### Symlink Policy

Maestro point netlists can contain internal symlinks. One observed example is:

```text
netlist/exprOutputs.log -> ../../../exprOutputs.log.15.0.1
```

C-49 must not copy symlinks verbatim into the project, because existing run
package safety checks reject symlinks. The import step should safely materialize
allowed symlink targets as regular files.

Allowed symlink materialization:

- link target resolves inside the Maestro result history root;
- target is a regular file;
- target is copied as a regular file;
- the import report records the original link and resolved source.

Rejected symlink cases:

- target escapes the Maestro result history root;
- target is missing;
- target is a directory;
- target is not a regular file;
- symlink chain is ambiguous or unsafe.

## Generated YAML Contracts

The structured intake produces the existing YAML contracts:

```text
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
```

The generated YAML files remain the execution source of truth. Existing Hermes
validation, packaging, real-run preparation, optimizer handoff, closeout, and
reporting continue to consume these YAML files.

Mapping rules:

- `Project` and `Maestro Source` render `project_config.yaml`.
- `Design Variables` render `variables.yaml`.
- `Metrics`, `Constraints`, and `Objective` render `metrics.yaml`.
- `Spectre Settings` render `spectre.yaml`.
- `Optimizer Settings` render `optimizer.yaml`.

Metric expressions are copied exactly from `ocean_expression` into the OCEAN
contract fields. Hermes must not rewrite formula dialects or derive equivalent
Python functions.

## Approval And Ambiguity Rules

The intake must fail closed if required sections or required fields are missing.

The generated config should not be approved for real execution unless all
approval checklist booleans are true:

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```

If the supervisor agent is unsure how to map a user statement into a config
field, it must add a blocking issue rather than guessing.

`constraints.md` may inform report interpretation and continuation choices, but
it must not silently mutate generated YAML.

## Non-Goals

C-49 does not:

- implement a generic natural-language parser inside Hermes;
- let users hand-select Maestro sidecars;
- run real Spectre, OCEAN, Virtuoso, OpenBox, or bridge commands;
- change the Spectre/OCEAN adapter;
- change optimizer candidate generation;
- parse PSF;
- rewrite OCEAN formulas;
- replace existing YAML schemas;
- delete native TuRBO.

## Validation Scope

C-49 validation should prove:

- `opt_requirement.md` exists and required sections are present;
- fenced YAML blocks parse successfully;
- required intake fields exist;
- approval checklist blocks unapproved real execution;
- `maestro_point_root/netlist/input.scs` exists;
- full netlist bundle import works without leaving symlinks;
- unsafe symlink cases fail closed;
- generated `config/*.yaml` passes existing `hermes-workflow validate`;
- generated `template.scs` can be produced by existing `prepare-netlist`.

Real Spectre/OCEAN smoke from imported point roots belongs to the follow-up
practice task after C-49, unless the user explicitly requests another focused
real-tool validation.

## Recommended Follow-Up

After C-49:

1. run one user-selected project bootstrap drill from `opt_requirement.md`;
2. import the Maestro point root into the project directory;
3. generate and validate config YAML;
4. run one real Spectre/OCEAN single-point check;
5. then run the OpenBox optimizer handoff at the user-approved evaluation
   budget.
