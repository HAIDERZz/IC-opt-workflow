# OpenBox Backend Seam MVP Design

Date: 2026-06-05

## Goal

Add the smallest optimizer backend seam that lets the project evaluate OpenBox as an optimizer backend without replacing the working native TuRBO route.

C-27 should answer:

```text
Can OpenBox produce Hermes-compatible optimizer run artifacts through the same candidate/result/acceptance/completion contract shape?
```

It should not answer:

```text
Is OpenBox better than TuRBO on real IC simulations?
```

That real-tool comparison belongs after this seam can produce accepted fake-run artifacts.

## Evidence Basis

The local OpenBox evidence spike is recorded in:

```text
docs/debug/2026-06-05-openbox-backend-evidence-spike.md
```

Confirmed locally with a fake inverter evaluator:

- stepped integer and stepped real variables can be represented with OpenBox `q`;
- constrained observations can be recorded through OpenBox history;
- ask-and-tell can request one candidate at a time;
- `get_suggestions(batch_size=N)` can request a batch for bounded parallel execution;
- grid-aligned fake probes produced no duplicates or grid violations in the tested seed;
- real-valued grid entries can still appear as binary floats, so Hermes must keep deterministic parameter serialization.

## Non-Goals

- Do not replace or delete `src/hermes_workflow/native_turbo.py`.
- Do not run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or an execution agent.
- Do not parse PSF or waveform databases in Python.
- Do not rewrite OCEAN or ADE Calculator formulas.
- Do not change approved metrics, constraints, or objective expressions.
- Do not implement OpenBox real-tool acceptance in C-27.
- Do not introduce a daemon, database, service, distributed scheduler, or broad optimizer framework.
- Do not vendor OpenBox into this repository.
- Do not commit raw Cadence input decks, protected sidecars, PSF/raw data, or full logs.

## Design Principle

Use the proven Spectre/OCEAN workflow as the foundation and swap only the optimizer candidate-generation backend.

The route remains:

```text
optimizer backend suggests candidates
-> Hermes prepares approved candidate packages
-> execution agent or adapter runs real tools
-> Hermes records metrics/manifests
-> acceptance and completion reports summarize results
```

C-27 only proves the first and last parts with a fake evaluator:

```text
OpenBox backend suggests fake candidates
-> fake evaluator returns metrics/constraints
-> Hermes writes optimizer artifacts
-> check-optimizer-run accepts those artifacts
-> summarize-optimizer-run can read them
```

## Artifact Strategy

Current C-25/C-26 tooling reads TuRBO-specific artifact names:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
```

C-27 should add backend-neutral artifact names for new backends:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

Existing native TuRBO artifacts remain valid. Acceptance and completion readers should prefer the backend-neutral files when present and fall back to the existing native TuRBO paths for backward compatibility.

The backend-neutral report should keep the current minimal report shape, with an explicit backend field:

```json
{
  "schema_version": "1.0",
  "status": "completed",
  "backend": "openbox",
  "evaluation_count": 40,
  "best_candidate": {
    "evaluation_index": 17,
    "run_id": "fake_017",
    "selection_phase": "openbox_batch",
    "parameters": {
      "FN": "2",
      "WN": "1.6u",
      "FP": "2",
      "WP": "2u"
    },
    "status": "feasible",
    "objective": 794566.0135539863,
    "fom": 794566.0135539863
  },
  "evaluations": "reports/optimizer_evaluations.jsonl",
  "issues": [],
  "batch_summary": {
    "batch_count": 10,
    "max_batch_worker_count": 4,
    "status_counts": {
      "feasible": 24,
      "constraint_failed": 16
    }
  }
}
```

The evaluation JSONL rows should preserve the fields that downstream tooling already understands:

```json
{
  "evaluation_index": 17,
  "run_id": "fake_017",
  "selection_phase": "openbox_batch",
  "raw_x": [2.0, 1.6, 2.0],
  "parameters": {
    "FN": "2",
    "WN": "1.6u",
    "FP": "2",
    "WP": "2u"
  },
  "status": "feasible",
  "objective": 794566.0135539863,
  "fom": 794566.0135539863,
  "constraint_penalty": 0.0,
  "metrics": {
    "rise": 7.8e-11,
    "fall": 7.2e-11,
    "DC": 0.00018
  },
  "result_manifest": null,
  "metric_result_manifest": null,
  "issues": [],
  "batch_id": "batch_005",
  "batch_slot": 1,
  "batch_size": 4,
  "batch_worker_count": 4,
  "max_parallel_jobs": 4,
  "threads_per_run": null,
  "parallel_jobs": 4
}
```

For fake C-27 artifacts, manifest paths may be `null`. `check-optimizer-run` should accept manifest-free fake optimizer artifacts only when the report declares `backend = "openbox"` and `execution_mode = "fake"` or an equivalent explicit fake flag. Real-run acceptance must still require real result and metric manifests.

## OpenBox Backend Interface

C-27 should introduce a small internal backend interface rather than a broad framework.

The interface needs only these behaviors:

- load approved variables, metrics, constraints, and optimizer config;
- request a batch of candidates;
- serialize candidate parameters with existing Spectre-safe formatting rules;
- accept metric observations from an evaluator;
- write backend-neutral optimizer artifacts.

The OpenBox adapter should be import-lazy. If OpenBox is missing, commands that require it should fail with a clear dependency message. Existing TuRBO commands must continue to work without OpenBox installed.

## Variable Handling

Approved Hermes variables remain authoritative.

For C-27:

- integer variables map to stepped OpenBox integer variables;
- continuous-step variables map to stepped OpenBox real variables;
- compact Spectre unit strings remain the serialization boundary;
- raw OpenBox float suggestions must never be written directly into candidate requests or Spectre input files;
- derived parameters such as `FP = FN` may be represented in the fake evaluator or backend adapter, but C-27 must not create a new general expression engine.

The MVP can reuse existing `quantize_candidate` behavior from the native TuRBO module to avoid duplicating formatting logic. A later cleanup may move shared quantization into a backend-neutral helper only if the seam proves useful.

## Objective And Constraint Semantics

OpenBox minimizes objective values, matching the current native TuRBO objective convention.

Hermes remains responsible for deciding candidate status:

- missing or non-scalar metrics -> metric failure penalty;
- scalar metrics that violate constraints -> `constraint_failed`;
- scalar metrics satisfying constraints -> `feasible`;
- lower objective is better.

C-27 should not rely on OpenBox alone to enforce feasibility. The evaluator returns constraints to OpenBox for model learning, while Hermes still writes the canonical trace status and objective using the same rules C-25/C-26 understand.

## User-Level Behavior

C-27 should add a fake-only command or test helper before any real-tool command.

Preferred user-facing command:

```bash
hermes-workflow run-openbox-fake PROJECT_DIR --max-evals 40 --batch-size 4
```

The command writes:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

It should not write:

```text
runs/real/
ledger/
state/optimizer_state.json
```

The command is intentionally fake-only. A later real OpenBox runner may reuse the same backend seam, but C-27 should not add real execution options.

## Acceptance Path

C-27 should update existing read-only report tooling narrowly:

- `check-optimizer-run` can read backend-neutral fake OpenBox artifacts and accept them without real manifests;
- `check-optimizer-run` still requires manifests for real native TuRBO artifacts and future real OpenBox artifacts;
- `summarize-optimizer-run` can read accepted backend-neutral reports through the existing C-26 summary rules;
- old native TuRBO reports remain accepted through legacy fallback.

This keeps C-27 useful without forcing immediate CLI or artifact renames across all existing TuRBO paths.

## Dependency Policy

OpenBox is an optional backend dependency at this stage.

- Do not add OpenBox to the default install path until the fake seam and one real acceptance run are accepted.
- Keep imports lazy and error messages explicit.
- Unit tests should use injected fake OpenBox advisor objects where possible.
- One optional smoke may run only when OpenBox is available in the active environment; it should skip cleanly otherwise.

## Testing Strategy

Use fake projects and fake evaluators only.

Required test coverage:

- backend-neutral artifact loader prefers `reports/optimizer_run_report.json` over legacy native paths;
- legacy native TuRBO reports still load unchanged;
- OpenBox fake runner writes grid-safe parameter strings, not raw float reprs;
- OpenBox fake runner records constraints and feasible/constraint-failed statuses;
- batch metadata is present and bounded by requested batch size;
- `check-optimizer-run` accepts fake OpenBox artifacts only when the report explicitly marks fake execution;
- `check-optimizer-run` still rejects real-style rows that omit required manifests;
- `summarize-optimizer-run` can consume a C-25 accepted backend-neutral fake report.

Do not run real Cadence tools in C-27 tests.

## Route Alignment

C-27 aligns with the top-level goal because it keeps Hermes as a lightweight workflow contract layer and keeps the execution agent focused on tool-side work.

It also responds to the current backend decision point:

- TuRBO remains the implemented real backend;
- OpenBox is evaluated as a candidate-generation backend only;
- proven Spectre/OCEAN package, adapter, audit, and summary contracts remain intact;
- no speculative broad optimizer framework is introduced.

## C-27 Exit Criteria

C-27 is complete when:

- fake OpenBox artifacts can be generated in the backend-neutral report shape;
- C-25 acceptance can accept those fake artifacts without weakening real-run manifest checks;
- C-26 completion can summarize the accepted fake artifacts;
- legacy native TuRBO acceptance and completion tests still pass;
- docs clearly state that real OpenBox acceptance has not been run.

After C-27, the next decision should be one of:

- run one real 100-evaluation OpenBox backend acceptance;
- keep TuRBO as the only real backend and leave OpenBox experimental;
- add parameter-relationship reporting from accepted optimizer history before switching backend.
