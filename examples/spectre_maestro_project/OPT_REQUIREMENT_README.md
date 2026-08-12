# Writing `opt_requirement.md`

`opt_requirement.md` is the machine-checked contract for a first real workflow
run. It selects the workflow mode and carries every value that may change the
simulation or optimization. First-run CLI flags do not override those values.

Unknown sections, unknown fields, duplicate YAML keys, misspelled names, and
sections that do not apply to the selected mode fail closed. A parsed field is
never intentionally accepted and then silently ignored.

## Supported Modes

- `mode: optimize`: optimizer-driven search using OpenBox or native TuRBO.
- `mode: fix_run`: fixed-point Spectre/OCEAN characterization with scalar
  Metrics, waveform CSV exports, or both.

Local and remote/SSH execution use the same requirement. Transport is not a
separate workflow mode. Continuation also has no separate requirement template:

```bash
ic-opt <project> --real --continue N
```

This file is copied into the rendered project, so every `ic-opt` command shown
below is the bare command name; run it as `./.venv/bin/ic-opt` from the tool
checkout root, or activate that virtual environment first, so `ic-opt`
resolves on `PATH`.

Continuation extends the generated project backend and does not reread a
changed `opt_requirement.md`. History Warm Start creates a new optimize project
and is a different capability.

## Complete Template Matrix

The eleven templates cover each distinct workflow, topology, output, history,
corner, and production optimizer contract without duplicating the full
Cartesian product.

| File | Workflow and coverage |
| --- | --- |
| `opt_requirement.md` | OpenBox PRF-EIC; one testbench; source/nominal corner |
| `opt_requirement.openbox_gp_eic.md` | complete OpenBox GP-EIC settings |
| `opt_requirement.turbo.md` | complete native TuRBO trust-region settings |
| `opt_requirement.multi_corner.md` | one testbench; multiple process corners |
| `opt_requirement.multi_testbench.md` | multiple testbenches; source/nominal corner (`openbox_auto` compatibility strategy; new production requirements should use `openbox_prf_eic`/`openbox_gp_eic`) |
| `opt_requirement.multi_tb_corner.md` | multiple testbenches and process corners |
| `opt_requirement.history_warm_start.md` | multi-testbench OpenBox history warm start (`openbox_auto` compatibility strategy; new production requirements should use `openbox_prf_eic`/`openbox_gp_eic`) |
| `opt_requirement.history_warm_start.multi_corner.md` | single-testbench, multi-corner OpenBox history warm start |
| `opt_requirement.fix_run.md` | waveform-only; one testbench; 15 corners; one fixed point |
| `opt_requirement.fix_run.metrics_only.md` | metrics-only; one testbench; multiple fixed points |
| `opt_requirement.fix_run.multi_testbench.metrics_waveform.md` | routed Metrics plus Waveform Exports; multiple testbenches, corners, and fixed points |

Copy the closest file to `<project>/opt_requirement.md`, then replace all
private paths, formulas, model sections, variable ranges, fixed points, and
circuit-specific values. Examples are contracts, not universal circuit data.

## Section Applicability

Every section appears at most once and contains exactly one fenced `yaml` block.

Optimize requires:

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

Optimize optionally accepts:

```text
Workflow
Process Corners
History Warm Start
```

Fix-run requires:

```text
Workflow
Project
Maestro Source
Design Variables
Spectre Settings
Fixed Points
Approval Checklist
```

Fix-run optionally accepts `Process Corners`, `Metrics`, and `Waveform Exports`,
but at least one of Metrics or Waveform Exports must be present. Fix-run rejects
Objective, Constraints, Optimizer Settings, and History Warm Start. Optimize
rejects Fixed Points and Waveform Exports.

## Workflow

All new optimize templates make the mode explicit:

```yaml
schema_version: "1.0"
mode: optimize
```

`starting_run_id` is not supported for optimize. Legacy optimize requirements
may omit the entire Workflow section; omission still means `mode: optimize`.

Fix-run uses:

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

Fix-run `starting_run_id` must match `real_NNN`. It controls the first fixed
point run ID; later points increment it in list order. It defaults to
`real_001` when omitted. Requirement validation rejects a starting ID and point
count whose final sequential ID would exceed `real_999`.

## Project

```yaml
project_name: mixer_cg_nf_opt
description: Human-readable project purpose
backend: maestro_exported_spectre_deck
```

`project_name` is an identifier. The only supported project backend is
`maestro_exported_spectre_deck`.

## Maestro Source and Testbench Routes

A single-testbench project uses top-level fields:

```yaml
maestro_point_root: /home/username/simulation/<project>/maestro/results/maestro/Interactive.N/1/<test_name>
virtuoso_library: Virtuoso_Bridge_test
cell: MixerCS_PSS_CG_Noise
design_view: schematic
maestro_view: maestro
test_name: Mixer_CS_CG_NF
corner: Nominal
```

A multi-testbench project uses named entries:

```yaml
testbenches:
  - id: cg_nf
    maestro_point_root: /home/username/simulation/<project>/maestro/results/maestro/Interactive.N/1/<test_name>
    virtuoso_library: Virtuoso_Bridge_test
    cell: MixerCS_PSS_CG_Noise
    design_view: schematic
    maestro_view: maestro
    test_name: Mixer_CS_CG_NF
    corner: Nominal
```

`maestro_point_root` is the result point directory containing
`netlist/input.scs`; it is not the `input.scs` file and not `psf/`.
`corner` identifies the imported point's base corner for child-deck rendering.
The library, cell, view, and test-name fields are preserved as package
provenance; the workflow does not query Maestro to prove that they match the
directory. Review them against the source point before approval.

For a top-level single testbench, Metrics and Waveform Exports omit
`testbench`. When `Maestro Source.testbenches` is used, every Metric and
Waveform Export must declare a `testbench` equal to one of the listed IDs.

## Process Corners

Without this section, the workflow creates one nominal child from the imported
source deck. Optimize multi-corner requirements use aggregation policies:

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
```

- `objective_policy` is `nominal` or `worst_case`, and is optimize-only.
- `constraint_policy` is `nominal` or `all_corners`, and is optimize-only.
- `objective_policy: nominal` requires an explicit corner whose `id` is
  `nominal`; YAML order is not used as a substitute for that identity.

Fix-run characterizes and reports every child independently, so it has no
objective or Constraint aggregation policy. A fix-run multi-corner section
must omit both policy fields:

```yaml
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: '27'
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: '125'
```

The renderer supplies internal `nominal`/`nominal` values only to satisfy the
shared generated-config schema; they do not select or discard fix-run child
results.

Corner entry fields have the same rendering meaning in both workflows:

- `model_section` replaces the section on active `include ... section=...`
  statements and fails if no such statement is found. It must be a non-empty
  compact token: whitespace, quotes, backslashes, explicit YAML `null`, and
  line breaks fail preflight before any deck is written.
- `variables` replace top-level Spectre parameters by exact name and fail when
  a requested name is absent. Every key must match the Spectre-safe identifier
  form `[A-Za-z_][A-Za-z0-9_]*`; every value must be a non-empty, single-line
  compact token without whitespace, quotes, or backslashes. An explicitly null
  `variables` field fails; omit the field when no override is required.
  `temperature` has no special meaning.
- `description` is optional metadata; it does not change simulation behavior.

`model_file` is also supported:

```yaml
  - id: ss_external_model
    model_file: /absolute/path/to/model.scs
    model_section: Post_simu_top_ss
```

`model_file` is supported only when the imported deck has exactly one active
`include ... section=...` line. Zero matches and multiple matches both fail
closed; the field does not silently choose one include or rewrite several
different model paths. For a multi-include deck, import a Maestro point with
the intended model setup instead.
The value must be an absolute POSIX path and a compact token without whitespace,
quotes, backslashes, explicit YAML `null`, or line breaks. This is required
because the renderer also supports an unquoted source `include` statement and
must not create an injectable or syntactically split replacement.

The workflow does not copy the referenced model file. Before netlist rendering,
local requirement/CLI preflight requires it to be a readable regular file on
the local machine. Remote doctor, fresh remote preparation, and frozen-snapshot
restore instead run the equivalent strict `test -f && test -r` probe through
SSH on the Remote Host. They never consult a same-named Controller path. A
frozen snapshot rechecks the external model because the model itself is not a
Materialized Artifact stored in that snapshot. SSH transport/protocol errors
are not reported as a missing file; they fail closed as transport errors.

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
```

Kinds are `integer` and `continuous_step`. Bounds and step use SPICE numeric
syntax. Lower must not exceed upper and step must be positive. An integer range
must be exactly divisible by its step. Continuous candidates are generated as
`lower + k * step <= upper`, so a continuous upper bound may be off-grid; every
generated or fixed value must still lie on the generated grid. A continuous
variable's lower, upper, and step values must use the same unit suffix.

## Metrics

Single-testbench scalar metric:

```yaml
- name: NF_3G
  unit: dB
  result: pnoise
  ocean_expression: 'value(getData("NF") 3e+09)'
  required_signals:
    - NF
```

Multi-testbench metrics add `testbench: cg_nf`. `result` is optional and emits
`selectResult('pnoise)` (SKILL reference-symbol form, no closing quote)
before the formula. It is normally omitted when the formula already contains
`?result`. `required_signals` is provenance and
History Warm Start compatibility metadata; the workflow does not inspect PSF
to prove those names exist. Formula errors, nil, waveform objects, and
non-finite scalar values fail the metric.

Metric nil and non-finite policies are fixed to `fail` and are not requirement
fields. See `METRICS.md` for the complete field contract.

## Constraints

Operators are `lt`, `le`, `gt`, and `ge`:

```yaml
- metric: NF_3G
  op: lt
  value: 9 dB
```

The referenced Metric must exist. The Constraint value must contain a finite
number, whitespace, and exactly the same unit string as that Metric. There is
no implicit conversion between dB, dBm, Hz, seconds, farads, or any other
units.

The optional project-root `constraints.md` is separate human/supervisor
guidance. Its presence and hash are recorded as the requirement intake
report's `constraints_md_present` and `constraints_md_sha256` fields, but its
prose is not translated into machine Constraints. Every enforced threshold
must therefore appear in the `## Constraints` YAML block above.

## Objective

```yaml
direction: minimize
expression: NF_3G
```

Directions are `minimize` and `maximize`. Expressions may reference declared
Metric names, finite numeric literals, parentheses, unary `+`/`-`, arithmetic
`+`, `-`, `*`, `/`, `%`, `**`, and these functions:

```text
min  max  ln
```

`min` and `max` need at least one argument; `ln` takes one positive argument.
Function domains must be valid and the final result must be a finite real
scalar. Attributes, indexing, comprehensions, keywords, arbitrary function
calls, and undeclared names are rejected.

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 8
timeout_s: 7200
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

`engine` and `preset` select the Spectre invocation; `preset` is one of `cx`,
`ax`, `mx`, `lx`, or `vx` (a closed set, like every other field in this
document). `threads_per_run` maps to Spectre `+mt`. In optimize, `parallel_jobs` is
candidate-level process concurrency. In fix-run, it is testbench/corner child
concurrency inside one fixed point; fixed points remain serial. The supported
output format is `psfxl`.

`keep_successful_runs` and `keep_failed_runs` control retention by completed
run outcome. Fix-run applies the decision after every fixed point. A remote
fix-run applies it to both the remote run directories and the downloaded local
snapshot. The fix-run report and `state/run_retention/<run_id>.json` preserve
the audit decision; deleted fix-run artifact paths are provenance, not
optimizer continuation evidence.

## Optimizer Settings

Every production template declares an explicit strategy. Supported production
pairs are:

```yaml
algorithm: openbox
strategy: openbox_gp_eic
```

```yaml
algorithm: openbox
strategy: openbox_prf_eic
```

```yaml
algorithm: turbo
strategy: turbo_trust_region
```

`openbox_auto` remains an explicit compatibility strategy used by sanitized
templates whose validated source run used OpenBox automatic model selection.
Do not omit strategy in a new production requirement. `random_baseline` is for
diagnostic plumbing checks, not production optimization.

Omitting `strategy` does not fail closed at the schema level: it is an
optional field, and omission falls through to a backend default strategy
resolution. This is a deliberately retained compatibility path for legacy
requirements, not a recommended way to write a new one.

`initialization` is `sobol`, `latin_hypercube`, or `random`.
`max_evaluations`, `batch_size`, and `optimizer_cpu_threads` are positive
integers; `random_seed` is the reproducibility seed; `failure_penalty` is a
positive floating-point optimizer penalty. `deduplicate_candidates` must be
`true`.
These fields are optimizer controls, while Spectre process and thread limits
remain in Spectre Settings. `batch_size` may not exceed Spectre
`parallel_jobs`. Native TuRBO also requires `max_evaluations` to be at least
twice the number of Design Variables.

OpenBox advanced fields are:

```yaml
openbox:
  surrogate_type: gp
  acq_type: eic
  acq_optimizer_type: random_scipy
  initial_trials: auto
```

With `openbox_auto`, these fields customize automatic model selection. With
`openbox_gp_eic` or `openbox_prf_eic`, `surrogate_type`, `acq_type`, and
`acq_optimizer_type` must agree with the named preset or validation fails;
`initial_trials` may still override the preset's automatic trial count.

Native TuRBO settings are:

```yaml
turbo:
  snap_to_step: true
  duplicate_handling: resample
```

`snap_to_step` and `duplicate_handling` are not tunable fields: schema
currently accepts only the literal values shown above (`true` and
`resample`), the same way nil/non-finite policy is a fixed literal rather
than a choice.

Use the complete GP-EIC and TuRBO templates rather than changing only the
algorithm name in another file.

## Fix-Run Fixed Points

```yaml
schema_version: "1.0"
points:
  - candidate_id: user_point_001
    parameters:
      F: '24'
      W: 0.8u
```

Every point must provide every Design Variable exactly once and may not add an
undeclared top-level Spectre parameter. Values are checked before simulation
for compatible unit suffix, bounds, and step-grid alignment. `candidate_id`
values must be unique and use only letters, digits, `_`, `.`, and `-`.

## Fix-Run Waveform Exports

Single-testbench export:

```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

Multi-testbench exports add a valid `testbench` route. CSV is the only output
format. `nil_policy: fail` is the only supported policy: missing/nil waveform
data fails the child instead of silently accepting incomplete evidence.
`nil_policy: skip` is not a supported requirement value. Export names must be
unique, and expressions must be non-empty and may not contain `outfile(`,
`system(`, or `{{` template placeholders.

## History Warm Start

History Warm Start is optimize-only and OpenBox-only:

```yaml
enabled: true
sources:
  - path: /absolute/path/to/previous_same_circuit_project
    label: round1
max_observations: 80
warm_start_strategy: topk
```

It renders to `config/history_warm_start.yaml`. Enabled history with native
TuRBO or fix-run is rejected. Current and source projects must have exactly the
same variable names and compatible Metric definitions. Metric compatibility
includes name, unit, formula, testbench route, `result`, `required_signals`, and
OCEAN contract metadata. Old objective and Constraint values are not reused;
raw historical Metrics are evaluated under the current requirement. Points
outside the current variable space are recorded as `out_of_current_space`.

Metric name matching for this compatibility check is case-sensitive and
exact. A source project that defines a metric as `P1dB` and a current project
that defines the same metric as `P1DB` are treated as incompatible metric
definitions, and the corresponding history points are dropped rather than
matched. Use the same metric name casing across a source and current project
pair before relying on warm start.

Inspect `reports/history_warm_start_audit.json`,
`reports/history_warm_start_audit.md`, and `openbox.history_warm_start` in
`reports/optimizer_run_report.json` before claiming history was applied.

## Approval Checklist

```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```

All four values must be exactly `true` before real-tool execution.
For a waveform-only fix-run, `metric_formulas_user_approved` also records the
user's approval of every Waveform Export expression despite the legacy field
name.

## Check the Requirement

```bash
ic-opt <project> --doctor
hermes-workflow check-requirement <project>
hermes-workflow prepare-from-requirement <project>
hermes-workflow validate <project>
hermes-workflow check-project-ready <project>
```

`ic-opt <project> --doctor` is the backend-aware Product Doctor gate: it
resolves the requirement's actual strategy/backend and checks the Controller
optimizer runtime (Native TuRBO, OpenBox, or random-baseline dependencies) and
Remote toolchain readiness that applies to it. The four `hermes-workflow`
commands only validate the requirement/config parsing layer -- section
presence, YAML shape, unit and bounds checks, and rendered config content --
and are not a substitute for the doctor gate. Do not treat parsing alone as
engineering acceptance. For production, inspect the rendered configs/netlists
and the real local or remote result manifests and reports for the selected
topology, corner matrix, output contract, and backend.
