# OpenBox Production Backend Design

Date: 2026-06-05

## Status

Design scope approved by C-28 evidence, not yet implemented.

## Context

C-28 proved that OpenBox ask-and-tell can drive the existing Hermes
Spectre/OCEAN execution path for a real 100-evaluation optimizer run. The run
used the approved four-variable search space from `variables.yaml`, produced
backend-neutral artifacts accepted by C-25, and received a C-26
`accept_best_observed` decision.

The C-29 goal is to productize only the evidence-backed part of that spike:
OpenBox candidate generation and ask-and-tell observation updates. The real
tool execution path stays the existing Hermes path:

```text
OpenBox suggestion
-> Hermes quantization and candidate package
-> existing Spectre/OCEAN adapter
-> check-real-run / check-metric-results / record-real-result
-> backend-neutral optimizer artifacts
-> C-25 acceptance
-> C-26 completion decision
```

TuRBO remains available during and after C-29. Replacing TuRBO as the default
optimizer is a later explicit decision.

## Non-Negotiable Boundaries

- Do not delete or replace `src/hermes_workflow/native_turbo.py`.
- Do not change approved `metrics.yaml` formulas.
- Do not parse PSF or waveform data in Python.
- Do not rewrite OCEAN/Calculator expressions.
- Do not flatten or redesign native Maestro/ADE netlist layout.
- Do not add hidden search-space constraints such as `FN=FP`.
- Do not hand-pick optimizer candidates in the backend.
- Do not introduce a daemon, service, database, or broad optimizer framework.
- Do not commit raw Cadence artifacts.

## Productized Behavior

### Command

C-29 adds one real backend command:

```bash
hermes-workflow run-openbox-real PROJECT_DIR \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

The command is intentionally parallel to the proven native command:

```bash
hermes-workflow run-native-turbo PROJECT_DIR --parallel ...
```

It must fail closed with a clear message when OpenBox is unavailable in the
active Python environment.

### Search Space

The OpenBox search space is derived from the approved Hermes
`config/variables.yaml`.

Integer variables:

```text
lower, upper, step -> OpenBox Int(..., q=step)
```

Stepped continuous variables:

```text
lower, upper, step -> OpenBox Real(..., q=step)
```

OpenBox requires `(upper - lower)` to be divisible by `q`. Hermes already
defines the actual legal grid through quantization:

```text
effective_upper = lower + floor((upper - lower) / step) * step
```

For `0.3u..3u step 0.2u`, the effective upper is `2.9u`. C-29 must use this
effective upper for OpenBox while preserving the original approved
`variables.yaml` contract.

### Candidate Generation

OpenBox must provide candidates through its ask-and-tell API:

```text
advisor.get_suggestions(batch_size=N)
advisor.update_observations(observations)
```

The backend converts each OpenBox suggestion into approved parameter text by
calling the existing Hermes quantization path. It must not add circuit-specific
constraints that are absent from `variables.yaml`.

Duplicate quantized candidates are handled by requesting replacement
suggestions up to a bounded replacement budget. If the budget is exhausted, the
run fails closed before pretending a duplicate was evaluated.

### Real Execution

The backend reuses existing real-run functions:

- `prepare_explicit_candidate_real_run(...)`
- `execute_and_check_real_candidate(...)`
- `record_real_result(...)`

Candidate packages use:

```text
source = "openbox_optimizer"
metadata.optimizer = "openbox"
selection_phase = "openbox_batch"
```

The implementation prepares a batch sequentially, executes candidates through a
bounded thread pool, and records ledger/state sequentially after checks finish.
This preserves the current real-run package and state-write safety model.

### Objective And Constraints

OpenBox objective values are the same scalar values used by C-17/C-18:

- feasible point: objective from `evaluate_candidate_objective(...)`
- constraint failure: finite failure penalty plus normalized constraint penalty
- metric check failure: finite failure penalty
- real tool failure: finite failure penalty and real failure status

OpenBox constraint observations use residuals derived from approved
`metrics.yaml` constraints:

```text
lt/le: metric_value - threshold
gt/ge: threshold - metric_value
```

OpenBox treats residuals `<= 0` as feasible.

### Artifacts

C-29 writes the same backend-neutral artifacts introduced in C-27:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

The report uses:

```json
{
  "backend": "openbox",
  "execution_mode": "real",
  "status": "completed"
}
```

Existing C-25 and C-26 commands must accept and summarize those artifacts
without OpenBox-specific special cases beyond backend-neutral loading.

## File Map

Modify:

- `src/hermes_workflow/openbox_backend.py`
  - add production OpenBox space construction with effective grid upper bounds
  - add ask-and-tell real runner
  - keep fake runner support
- `src/hermes_workflow/cli.py`
  - add `run-openbox-real`
- `tests/test_openbox_backend.py`
  - cover space construction, no hidden coupling, duplicate replacement, real
    runner with fake evaluator, report writing
- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`

Optional only if required by tests:

- `src/hermes_workflow/native_turbo.py`
  - expose a tiny shared helper that is already duplicated by OpenBox code

## Acceptance Criteria

- `run-openbox-real` exists and delegates to productized code, not a `/tmp`
  script.
- OpenBox search space uses the same effective grid as Hermes quantization.
- `FN`, `WN`, `FP`, and `WP` remain independent unless the approved
  `variables.yaml` changes.
- A fake-adapter test proves the runner prepares real candidate packages,
  executes through the existing evaluator boundary, records results
  sequentially, and writes backend-neutral artifacts.
- A dependency-gate test proves missing OpenBox fails with a clear error.
- C-25 accepts OpenBox real artifacts created by tests.
- C-26 summarizes OpenBox real artifacts created by tests.
- A real-tool acceptance run is planned as a separate explicit task after code
  lands and user confirms real execution.

## Route Audit

- Active top-level direction: practice-first, lightweight workflow around
  existing Cadence/Spectre/OCEAN behavior.
- Alignment: C-29 productizes only a proven OpenBox candidate-generation path
  and keeps the existing real-tool execution path.
- Drift: none intended. TuRBO remains implemented; OpenBox default selection is
  not changed in C-29.
