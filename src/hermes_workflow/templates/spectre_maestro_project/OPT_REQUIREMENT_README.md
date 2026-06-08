# Opt Requirement README

This file explains how to write `opt_requirement.md` for an IC optimization
project.

The goal is to make user input file-based and repeatable. Do not describe the
optimization only in chat. Put machine-critical settings in
`opt_requirement.md`, then let Hermes render the standard YAML contracts and
import the Maestro/ADE netlist bundle.

## Project Directory

Recommended user-created directory:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

User-owned files:

- `opt_requirement.md`: required, canonical optimization request.
- `constraints.md`: optional supervisor-agent guidance.
- `context/`: optional notes, screenshots, prior reports, or circuit context.

Generated/imported files:

```text
config/
netlists/exported/
netlists/templates/
reports/
runs/
ledger/
state/
execution_package/
```

Do not hand-build these generated directories unless a task explicitly asks you
to.

## Basic Workflow

1. Build and run one known-good Maestro/ADE single-point testbench.
2. Find the resulting `maestro_point_root`.
3. Write `opt_requirement.md` in the project directory.
4. Optionally write `constraints.md`.
5. Run:

```bash
hermes-workflow check-requirement ~/spectre_opt_prj/<project_name>
hermes-workflow prepare-from-requirement ~/spectre_opt_prj/<project_name>
hermes-workflow validate ~/spectre_opt_prj/<project_name>
hermes-workflow check-project-ready ~/spectre_opt_prj/<project_name>
```

For the full production command sequence, including optimizer execution,
decision recording, final summary generation, and continuation boundaries, read
`docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`.

## Required Sections

`opt_requirement.md` must contain these headings exactly once:

```text
Project
Maestro Source
Design Variables
Metrics
Constraints
Objective
Spectre Settings
Optimizer Settings
Approval Checklist
```

Each section must contain exactly one fenced `yaml` block.

## Maestro Source

`maestro_point_root` is the important field. It should point to the Maestro/ADE
single-point result directory that contains `netlist/input.scs`.

How to find the correct directory:

1. In Maestro/ADE, run one known-good simulation point for the testbench.
2. In the filesystem, go to that testbench's Maestro result tree, usually shaped
   like:

```text
~/simulation/<library>/<cell>/<test_name>/results/maestro/Interactive.<N>/<point>/<run_name>/
```

3. Use the leaf `<run_name>/` directory as `maestro_point_root`.

The quick check is:

```bash
ls <maestro_point_root>
# expected: netlist/  psf/

ls <maestro_point_root>/netlist/input.scs
# expected: the file exists
```

For example, if the ADE result tree is:

```text
.../results/maestro/Interactive.45/1/<run_name>/
```

then `maestro_point_root` should be exactly that leaf directory. Do not point it
to `Interactive.45`, `Interactive.45/1`, the `netlist/` subdirectory, or the
`psf/` subdirectory.

The following fields are metadata used for traceability and reports:

```yaml
virtuoso_library: Virtuoso_Bridge_test
cell: bridge_test_inv
design_view: schematic
maestro_view: maestro
test_name: tran_dc_test
corner: Nominal
```

Use the real values when known. `test_name` and `corner` do not change Spectre
or OCEAN execution; they identify which Maestro setup the imported netlist came
from.

For circuits that need multiple Maestro/ADE testbenches for one candidate, use
`opt_requirement.multi_testbench.md` as the reference. In that form,
`Maestro Source` contains a `testbenches:` list, and each metric declares a
`testbench:` routing key. The routing key only decides which child Spectre/OCEAN
run evaluates the formula; it is not part of the OCEAN expression.

The workflow supports one or more testbenches. A single testbench is the normal
special case and can use the simpler top-level `maestro_point_root` form. Use
`testbenches:` only when one candidate's metrics must be collected from multiple
Maestro/ADE point roots. The file format has no fixed maximum count; simulation
time, license availability, disk usage, and `parallel_jobs` are the practical
limits.

After `prepare-from-requirement`, multi-testbench projects should pass:

```bash
hermes-workflow check-project-ready ~/spectre_opt_prj/<project_name>
```

Before the first optimizer run, the expected readiness is
`ready_for_first_run`. After optimizer closeout and final summary generation,
the expected readiness is `ready_for_closeout_review`.

## Metrics

The minimum metric format is:

```yaml
- name: NF_3G
  unit: dB
  ocean_expression: value(getData("NF" ?result "pnoise") 3e+09)
```

`name` is the optimizer metric name. In the example above, `NF_3G` means the
noise figure sampled at 3 GHz. It does not need to match the internal OCEAN data
object name.

Optional fields:

```yaml
  result: pnoise
  required_signals:
    - /IF_P
    - /IF_N
```

- `result` is only a `selectResult(...)` hint for formulas that need it. If the
  formula already contains an explicit result selector, such as
  `getData("NF" ?result "pnoise")`, omit `result`.
- `required_signals` is only a human/audit diagnostic hint. It is not used to
  decide whether the formula is correct and is not required for dataset-style
  formulas.

Never rewrite an ADE/Maestro-approved formula into another dialect just to fill
these optional fields. The authoritative metric is `ocean_expression`.

## Design Variables

Every variable must be a separate YAML list item:

```yaml
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
```

Do not put two variable names in the same item. Duplicate YAML keys are rejected
because they can silently overwrite earlier values.

`prepare-from-requirement` renders `config/*.yaml`, imports the Maestro
netlist bundle, and generates `netlists/templates/template.scs` through the
existing netlist templating path.

It does not run Spectre, OCEAN, Virtuoso, OpenBox, or an execution agent.

## Maestro Point Root

Provide the point-root directory, not a hand-picked `input.scs`.

Expected shape:

```text
maestro_point_root/
├── netlist/
│   ├── input.scs
│   ├── ade_e.scs
│   └── ...
└── psf/
    └── ...
```

Typical example:

```text
/path/to/simulation/<lib>/<cell>/maestro/results/maestro/Interactive.9/1/<lib>_<cell>_1
```

Hermes copies the full `maestro_point_root/netlist/` bundle into
`netlists/exported/`. Users should not choose sidecar files manually.

Maestro netlists may contain symlinks such as:

```text
netlist/exprOutputs.log -> ../../../exprOutputs.log.15.0.1
```

Hermes materializes safe Maestro-history symlinks as regular files. Unsafe
symlinks are rejected.

## Required `opt_requirement.md` Structure

The file must contain these sections exactly once:

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

Each `##` section must contain exactly one fenced YAML block:

````markdown
## Project

```yaml
project_name: bridge_test_inv
description: Optimize inverter sizing from an existing Maestro testbench
backend: maestro_exported_spectre_deck
```
````

Free prose outside YAML blocks is allowed, but Hermes only reads the fenced
YAML blocks.

## Section Reference

### Project

```yaml
project_name: bridge_test_inv
description: Optimize inverter sizing from an existing Maestro testbench
backend: maestro_exported_spectre_deck
```

Rules:

- `project_name` must be a simple identifier: letters, numbers, underscore,
  not starting with a number.
- `backend` must be `maestro_exported_spectre_deck`.

### Maestro Source

```yaml
maestro_point_root: /absolute/path/to/maestro/results/maestro/Interactive.9/1/LIB_CELL_1
virtuoso_library: Virtuoso_Bridge_test
cell: bridge_test_inv
design_view: schematic
maestro_view: maestro
test_name: tran_dc_test
corner: Nominal
```

Rules:

- `maestro_point_root` must contain `netlist/input.scs`.
- Use an absolute path.
- Do not point directly to `input.scs`.
- Do not point directly to `psf/`.

### Design Variables

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

Supported `kind` values:

- `integer`
- `continuous_step`

Rules:

- Variable names must match `[A-Za-z_][A-Za-z0-9_]*`.
- Values should be strings.
- Continuous values must use Spectre-safe attached unit suffixes:
  - good: `"0.3u"`
  - bad: `"0.3 um"`
- Every listed variable must appear exactly once in the top-level
  `parameters` statement of the imported `input.scs`.
- Variables are independent optimization variables in this contract.

### Metrics

```yaml
- name: rise
  unit: s
  result: tran
  ocean_expression: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
  required_signals:
    - /VOUT
```

Rules:

- `name` is the metric identifier used by constraints and objective.
- `result` is the OCEAN result/analysis name, such as `tran`, `dc`, `ac`,
  `pss`, or `pac`.
- `ocean_expression` is copied exactly into the metric contract.
- Hermes does not rewrite OCEAN formulas.
- Python must not reimplement Calculator/OCEAN formulas.
- `required_signals` documents the expected result signals for review and
  failure diagnosis.

### Constraints

```yaml
- metric: rise
  op: lt
  value: "80e-12 s"
```

Supported operators:

- `lt`
- `le`
- `gt`
- `ge`

Rules:

- `metric` must reference a metric declared in `## Metrics`.
- Values should include units when that helps user review.
- Constraints define feasibility. The optimizer should first seek feasible
  points, then compare objective values among feasible points.

### Objective

Simple lower-is-better FoM:

```yaml
direction: minimize
expression: "(rise + fall) * DC"
```

For `direction: minimize`, smaller expression values are better.

Higher-is-better normalized score:

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

For `direction: maximize`, larger expression values are better. Internally, the
optimizer still minimizes, so feasible candidates use `objective = -FoM`. Reports
show both the user FoM and the internal minimized objective.

Supported directions:

- `minimize`
- `maximize`

Rules:

- Expression may use metric names and arithmetic operators.
- Supported objective functions are `min(...)`, `max(...)`, and `ln(...)`.
- Do not reference undeclared metrics.
- This is the FoM comparison expression, not an OCEAN formula.
- Write the expression using metric names, not OCEAN expressions. OCEAN belongs
  in `## Metrics`; `## Objective` combines already extracted scalar metrics.

### Spectre Settings

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

Rules:

- `preset` maps to Spectre X preset, for example `ax`.
- `threads_per_run` maps to Spectre `+mt` for a single Spectre process.
- `parallel_jobs` is the maximum number of Spectre processes launched at the
  same time.
- Keep `batch_size <= parallel_jobs`.
- Do not confuse `threads_per_run` with optimizer batch parallelism.

### Optimizer Settings

```yaml
algorithm: openbox
initialization: sobol
max_evaluations: 100
batch_size: 10
random_seed: 20260528
failure_penalty: 1000000.0
deduplicate_candidates: true
```

Recommended algorithm:

- `openbox`

Rules:

- `max_evaluations` is the total budget for the run.
- `batch_size` is how many candidates the optimizer asks for per batch.
- `deduplicate_candidates` must be `true`.
- Use a fixed `random_seed` for reproducibility.

### Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```

All values must be `true`.

This is intentional. It prevents accidental real-tool execution when formulas,
source path, bounds, or resource settings have not been reviewed.

## `constraints.md`

`constraints.md` is optional. It is for supervisor-agent guidance, not direct
contract generation.

Good uses:

- runtime budget preference;
- when to continue optimization;
- when to stop and ask the user;
- preferred report emphasis;
- known circuit caveats;
- user-level design intent.

Bad uses:

- hidden metric formulas;
- hidden Spectre settings;
- hidden optimizer bounds;
- hidden hard constraints.

If a rule affects actual execution, put it in `opt_requirement.md`.

## Common Failures

### `opt_requirement.md is missing`

The project directory does not contain `opt_requirement.md`.

### `required section is missing`

One of the required headings is absent or misspelled.

### `must contain exactly one fenced yaml block`

Each required section needs exactly one block beginning with:

````markdown
```yaml
````

and ending with:

````markdown
```
````

### `maestro_point_root/netlist/input.scs is missing`

The path is not a valid Maestro point root. Check that you provided the point
directory, not `psf/` and not `input.scs`.

### `approved variable was not found in top-level parameters`

The variable exists in `opt_requirement.md`, but the imported `input.scs` does
not expose it in the top-level `parameters` statement.

### `must use a Spectre-safe attached unit suffix`

Use `"0.3u"`, not `"0.3 um"`.

## Minimal Command Check

After writing `opt_requirement.md`, run:

```bash
hermes-workflow check-requirement ~/spectre_opt_prj/<project_name>
```

After it passes, run:

```bash
hermes-workflow prepare-from-requirement ~/spectre_opt_prj/<project_name>
```

Expected generated files include:

```text
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
netlists/exported/input.scs
netlists/templates/template.scs
reports/requirement_intake_report.json
reports/maestro_point_import_report.json
reports/netlist_preparation_report.json
```

Only after this bootstrap path passes should the user approve a real
Spectre/OCEAN single-point smoke or optimizer run.
