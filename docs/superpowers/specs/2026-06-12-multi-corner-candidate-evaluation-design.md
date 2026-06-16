# C-76 Multi-Corner Candidate Evaluation Design

Date: 2026-06-12

## Decision

Add process-corner evaluation as an optional axis in the existing candidate
evaluation model.

This is not a new CLI mode. Users continue to run:

```bash
ic-opt PROJECT --doctor
ic-opt PROJECT --real
ic-opt PROJECT --continue 40
ic-opt --ssh-profile PROFILE PROJECT --real
```

Whether a project uses process corners is determined by `opt_requirement.md`
and the generated project config, the same way multi-testbench behavior is
determined today.

## Target Model

Current model:

```text
candidate -> testbench -> metrics -> constraints/objective
```

New model:

```text
candidate -> testbench -> corner -> metrics -> aggregation -> constraints/objective
```

Degenerate cases must remain natural:

```text
single testbench, no corners:
candidate -> default_testbench -> nominal -> metrics

multi-testbench, no corners:
candidate -> tb1/tb2/tb3 -> nominal -> metrics

single testbench, multi-corner:
candidate -> default_testbench -> tt/ff/ss -> metrics

multi-testbench, multi-corner:
candidate -> tb1/tb2/tb3 -> tt/ff/ss -> metrics
```

## Non-Negotiable Invariants

1. Multi-corner coverage is declared through `Process Corners` in `opt_requirement.md`.
2. `parallel_jobs` remains candidate-level concurrency.
3. Testbench and corner execution inside one candidate is serial by default.
4. Runtime concurrency must not multiply by `testbench_count` or
   `corner_count`.
5. Local and remote execution must use the same project contracts and manifest
   semantics.
6. Remote mode must remain a transport wrapper around canonical local
   Spectre/OCEAN behavior.
7. Multi-corner must not rewrite OCEAN formulas.
8. Multi-corner must not require live Virtuoso or Maestro GUI during optimizer
   execution.
9. Monte Carlo is out of scope for C-76.
10. Existing single-corner projects must continue to run without changes.

## Requirement Contract

Add an optional `Process Corners` section to `opt_requirement.md`.

Example:

```yaml
Process Corners:
  objective_policy: worst_case
  constraint_policy: all_corners
  corners:
    - id: tt
      model_section: Post_simu_top_tt
      variables:
        temperature: "27"
    - id: ff
      model_section: Post_simu_top_ff
      variables:
        temperature: "0"
    - id: ss
      model_section: Post_simu_top_ss
      variables:
        temperature: "125"
```

If `Process Corners` is missing, the project behaves as if it had:

```yaml
Process Corners:
  objective_policy: nominal
  constraint_policy: nominal
  corners:
    - id: nominal
```

### Corner Fields

Required per corner:

- `id`: stable identifier, safe for path names.

Optional per corner:

- `model_section`: full Spectre model section name supplied by the user.
- `model_file`: full model file path if the corner changes model file.
- `variables`: mapping of parameter names to values, for example
  `temperature`, `vdd`, or PDK-specific variables.
- `description`: human-readable note for reports.

The product must not guess PDK section names. The user provides full section
names.

## Netlist Handling

C-76 should generate corner-specific netlist templates without modifying the
source Maestro/ADE point root.

For each testbench and corner, create a deterministic template under the
project execution package. A concrete path shape can be:

```text
netlists/testbenches/<testbench_id>/corners/<corner_id>/template.scs
```

Rules:

- If `model_section` is supplied, update only the intended model include line.
- If `model_file` is supplied, update the model include file path plus section.
- If `variables` are supplied, update parameter values using the existing
  parameter injection machinery where possible.
- Never perform broad text replacement across the whole netlist.
- Preserve original source netlist for audit.

## Evaluation Semantics

For one candidate:

```text
for each testbench:
  for each corner:
    run Spectre/OCEAN
aggregate all child manifests
evaluate candidate status
```

Execution is serial inside the candidate.

Candidate status:

- `real_check_failed`: any required child run fails at the tool level.
- `metric_check_failed`: any required metric is missing, non-scalar, or
  unparsable in any required child run.
- `constraint_failed`: all required tool/metric checks pass, but one or more
  constraints fail under the selected `constraint_policy`.
- `feasible`: all required tool/metric checks pass and all constraints pass.

## Aggregation Policies

### Constraint Policy

Initial supported values:

- `nominal`: evaluate constraints only on the nominal/default corner.
- `all_corners`: every required corner must satisfy all hard constraints.

Default:

- no corner config: `nominal`
- with multiple corners: `all_corners`

### Objective Policy

Initial supported values:

- `nominal`: objective is evaluated from the nominal/default corner.
- `worst_case`: objective is the pessimistic value across corners.

For minimize objectives:

```text
worst_case = max(corner_objective_values)
```

For maximize objectives, the product already converts to minimized objective
internally. The worst-case decision should be applied after converting to the
internal minimized objective.

Default:

- no corner config: `nominal`
- with multiple corners: `worst_case`

## Report Requirements

Reports must show:

- selected corner policies;
- corner list and user-provided section names;
- best observed candidate;
- per-corner metrics for the best candidate;
- worst failing corner for constraint failures;
- status counts split by aggregate status;
- optional breakdown table by testbench and corner;
- if no feasible candidates exist, whether failure is dominated by a specific
  testbench, corner, metric, or constraint.

## Remote Mode Requirements

Remote mode must preserve the same evaluation matrix:

```text
candidate -> testbench -> corner
```

Only Spectre/OCEAN execution and file transfer are remote. OpenBox,
aggregation, reporting, and decision logic remain local.

Remote child run artifacts should be mirrored back under the same local cache
shape as local runs, with enough path information to distinguish:

```text
run_id
testbench_id
corner_id
```

## Monte Carlo Boundary

Monte Carlo is not part of C-76.

Rationale:

- Monte Carlo is expensive and noisy for every optimizer candidate.
- Maestro/ADE already owns Monte Carlo setup, sampling, and yield semantics.
- C-76 should keep optimizer candidate evaluation deterministic.

Future work should treat Monte Carlo as post-optimization acceptance:

```text
optimize nominal/multi-corner -> choose top candidates -> run Maestro MC
acceptance -> report yield/distribution
```

## Acceptance Criteria

C-76 is accepted when:

1. Existing single-corner single-testbench tests pass unchanged.
2. Existing multi-testbench tests pass unchanged.
3. A project without `Process Corners` produces the same config semantics as
   before.
4. A project with two corners creates distinct corner-aware run contexts.
5. One candidate with two testbenches and three corners produces six child run
   records but does not exceed one child run at a time within that candidate.
6. `parallel_jobs` remains the maximum number of concurrently evaluated
   candidates.
7. `all_corners` constraint policy fails a candidate if any corner violates a
   required constraint.
8. `worst_case` objective policy selects the pessimistic corner objective.
9. Remote and local aggregation produce the same candidate-level status for the
   same child manifests.
10. Reports clearly identify best candidate, worst corner, and failure
    distribution.
