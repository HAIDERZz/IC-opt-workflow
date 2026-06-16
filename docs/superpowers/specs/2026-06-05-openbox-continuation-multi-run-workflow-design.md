# C-38 OpenBox Continuation / Multi-Run Optimizer Workflow Design

> Historical command notice: this old design spec may show obsolete
> workload/resource CLI flags. Current release product first runs read those
> values only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

Date: 2026-06-05

## Purpose

C-38 adds a narrow continuation workflow for the accepted OpenBox optimizer path.

The goal is to let a supervisor/execution-agent pair continue an already
accepted OpenBox run for another batch of evaluations without restarting the
optimizer as if no history existed.

This is not a new optimizer framework and does not replace the C-34/C-36
toolchain reference.

## Background

The current OpenBox production command can run one fixed-budget optimization:

```text
hermes-workflow run-openbox-real PROJECT_DIR --max-evals N ...
```

That path writes backend-neutral optimizer artifacts:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

However, a second invocation currently creates a fresh OpenBox advisor and a
fresh in-memory duplicate set. That means it can continue run numbering through
the existing real-run directories, but the optimizer model itself is not truly
conditioned on the previously observed samples.

## Design Principle

Continuation must be real enough to affect candidate generation:

```text
existing accepted optimizer traces
-> rebuild OpenBox observations from those traces
-> tell them to a new OpenBox advisor before asking for new suggestions
-> avoid previous candidate duplicates
-> evaluate only the requested additional candidates
-> write cumulative backend-neutral report/evaluation artifacts
```

The MVP intentionally does not serialize OpenBox internal state. Reconstructing
the advisor from accepted trace artifacts is simpler, transparent, and more
robust across OpenBox versions.

## Scope

### In Scope

- Add a continuation mode for OpenBox real optimization.
- Add the same continuation mode to the fake OpenBox runner for unit coverage.
- Load existing backend-neutral OpenBox traces from
  `reports/optimizer_evaluations.jsonl`.
- Warm-start the OpenBox advisor by converting prior traces into OpenBox
  observations.
- Seed duplicate detection with prior candidate parameter tuples.
- Continue candidate ids and evaluation indexes after the prior trace count.
- Continue real run ids after existing `runs/real/real_NNN` directories.
- Allow explicit OpenBox continuation candidate packaging to proceed from a
  prior `completed` optimizer state only when continuation mode is active,
  while preserving normal completed/stopped-state guards for non-continuation
  real-run preparation.
- Write cumulative optimizer artifacts containing prior and new traces.
- Record continuation metadata in `reports/optimizer_run_report.json`.
- Add CLI support for:

```text
hermes-workflow continue-openbox-real PROJECT_DIR --additional-evals N ...
```

- Extend OpenBox optimizer task packets so an execution agent can be handed a
  continuation task explicitly.

### Out Of Scope

- Serializing or restoring OpenBox internal surrogate model objects.
- Changing objective, constraint, metric, or Spectre/OCEAN semantics.
- Python PSF parsing.
- Rewriting OCEAN formulas.
- Replacing OpenBox or TuRBO.
- Adding a daemon, scheduler, database, or broad workflow engine.
- Running real tools as part of this contract implementation unless a later
  acceptance task explicitly asks for it.

## User-Facing Semantics

Initial run:

```text
run-openbox-real --max-evals 100
```

Continuation run:

```text
continue-openbox-real --additional-evals 50
```

The continuation command means "evaluate 50 new candidates after the existing
accepted trace history." It does not mean "make the total count 50."

The resulting report should show:

```json
{
  "evaluation_count": 150,
  "openbox": {
    "continuation": {
      "enabled": true,
      "prior_evaluation_count": 100,
      "additional_evals": 50,
      "target_total_evals": 150
    }
  }
}
```

## Acceptance Criteria

- A focused unit test proves continuation tells prior observations to the
  advisor before asking for new suggestions.
- A focused unit test proves new candidate ids/evaluation indexes continue from
  prior traces instead of restarting at 1.
- A focused unit test proves duplicate detection sees prior candidates.
- A focused unit test proves the continuation CLI calls the continuation runner
  with `additional_evals`.
- A task-package test proves an OpenBox continuation packet renders
  `continue-openbox-real` and `--additional-evals`.
- Existing OpenBox single-run behavior remains unchanged.
- Existing optimizer acceptance/completion/finalize commands continue to read
  the backend-neutral artifacts without a special continuation code path.
