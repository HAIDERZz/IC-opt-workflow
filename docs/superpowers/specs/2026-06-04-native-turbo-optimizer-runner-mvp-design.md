# Native TuRBO Optimizer Runner MVP Design

Date: 2026-06-04

## Goal

Add the smallest product feature that turns the verified optimizer practice into
a reusable Hermes workflow tool.

The feature should run native local `Turbo1.optimize()` and use the existing
Hermes + Spectre + OCEAN real evaluation path as the black-box objective.

## Non-Goals

- Do not create a broad optimizer framework.
- Do not create a daemon, service, distributed scheduler, or database.
- Do not replace TuRBO.
- Do not use Hermes' previous one-candidate suggestion loop as the optimizer.
- Do not parse PSF or waveform data in Python.
- Do not rewrite Calculator/OCEAN formulas.
- Do not flatten or redesign the Maestro/ADE netlist layout.
- Do not commit raw Cadence decks, sidecars, PSF/raw data, or full logs.

## Confirmed Practice Basis

The design is based on the successful 2026-06-04 real practice:

```text
docs/debug/2026-06-04-optimizer-skill-real-flow-practice.md
```

That practice showed:

- `Turbo1.optimize()` can drive the flow.
- Spectre/OCEAN can evaluate each real candidate.
- Scalar metrics and finite objectives can be returned to TuRBO.
- Duplicate quantized candidates are a real problem.
- Metric non-scalar candidates must become finite penalty observations.

## User-Level Behavior

The MVP should expose one narrow command:

```bash
hermes-workflow run-native-turbo PROJECT_DIR \
  --max-evals 100 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

The command runs sequentially by default. That means:

- one Spectre process at a time;
- each Spectre process uses `spectre.threads_per_run` as `+mt`;
- simultaneous Spectre processes must not exceed `spectre.parallel_jobs`.

The MVP may accept `--max-evals` for practice, but it must read bounds, steps,
constraints, objective expression, failure penalty, and Spectre settings from
approved project config.

## Objective Semantics

The objective is feasibility-first.

For each candidate:

```text
if metrics are missing, non-scalar, non-finite, or tool execution fails:
    objective = failure_penalty
elif any spec constraint is violated:
    objective = failure_penalty + normalized_violation_score
else:
    objective = configured FOM
```

This keeps the optimizer's first priority on meeting minimum specs. FOM only
orders candidates that satisfy the specs.

## Candidate Flow

`Turbo1.optimize()` produces continuous `x`.

The runner converts `x` into approved variables by:

- rounding integer variables to their approved integer grid;
- snapping `continuous_step` variables to their approved step grid;
- formatting continuous values with compact Spectre-safe unit suffixes.

The runner must de-duplicate after quantization. A duplicate candidate must not
silently consume a real Spectre budget if a replacement can be generated inside
the current budget attempt.

MVP replacement behavior:

- try a bounded number of TuRBO-adjacent perturbations around the current `x`;
- if still duplicate, draw bounded random grid candidates;
- if no unique candidate remains, return finite duplicate penalty and record the
  duplicate status.

## First Candidate Package

The runner must support the first optimizer-selected candidate without requiring
a lower-bound seed ledger row.

MVP implementation may add a narrow first-explicit-candidate package helper that
reuses the existing real-run package writer and the existing approval/hash
guards. It must not mutate project-level variable bounds.

## Result Trace

The runner writes a compact trace under the project:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
```

Each evaluation records:

- evaluation index and run id;
- selection phase: initialization or turbo trust-region;
- raw continuous `x`;
- quantized parameters;
- status;
- metric values if available;
- constraint violations;
- FOM;
- returned objective;
- result/metric manifest paths;
- concise issues.

Raw Cadence artifacts remain under `runs/real/<run_id>/` and are not copied into
docs.

## Error Handling

The runner keeps optimizing when a candidate fails in a candidate-local way:

- metric non-scalar;
- missing scalar metric;
- constraint violation;
- duplicate candidate after bounded replacement attempts.

The runner stops only for workflow-level failures:

- project validation failure;
- immutable config drift;
- unsafe paths or symlinks;
- approval/hash mismatch;
- no unique candidates left;
- repeated tool failures that indicate environment failure rather than candidate
  behavior.

## Tests

Unit tests should use fake evaluators and fake runners first:

- quantization and compact unit formatting;
- duplicate de-duplication and bounded replacement;
- feasibility-first objective;
- first explicit candidate package behavior;
- trace writing.

Real Spectre/OCEAN acceptance remains a separate explicit practice run and must
not be required for ordinary test execution.

## Route Alignment

This MVP directly supports the original project goal: give an agentic workflow a
stable file-contract path for IC optimization while keeping real Cadence metric
calculation authoritative.

It keeps the execution side simple:

```text
Supervisor/Hermes decides and records
-> native TuRBO runner selects candidates
-> existing Spectre/OCEAN adapter evaluates
-> Hermes checks and records
```

The execution agent remains useful for non-scripted Virtuoso/Maestro operations
and for future cell setup/export work. The native runner is justified for the
repeated mechanical optimization loop because practice showed that this part is
better as deterministic code than as repeated agent behavior.
