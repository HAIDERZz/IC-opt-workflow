# Batch Native TuRBO Parallel Runner Design

Date: 2026-06-04

## Goal

Extend the C-17 native TuRBO runner so TuRBO can evaluate batch candidates with
parallel Spectre/OCEAN workers.

This is the smallest useful step after C-17. C-17 proved the native
`Turbo1.optimize()` route, but it ran one Spectre/OCEAN evaluation at a time.
C-18 should keep the same optimizer route and make the expensive real-tool
evaluation step run in parallel up to the approved project cap.

## Non-Goals

- Do not create a daemon, service, database, queue system, or distributed
  scheduler.
- Do not replace TuRBO.
- Do not return to the older one-candidate suggestion loop as the optimizer
  driver.
- Do not parse PSF or waveform data in Python.
- Do not rewrite Calculator/OCEAN formulas.
- Do not flatten or redesign the native Maestro/ADE netlist layout.
- Do not commit raw Cadence decks, protected sidecars, PSF/raw data, or full
  logs.

## Confirmed TuRBO Behavior

The local TuRBO implementation accepts `batch_size` and selects a batch of
candidates, but `Turbo1.optimize()` evaluates that batch by calling the
objective one candidate at a time:

```python
fX_next = np.array([[self.f(x)] for x in X_next])
```

Therefore, simply setting `batch_size=10` is not enough. Hermes needs a
batch-aware adapter around the TuRBO evaluation point so a selected candidate
batch can be evaluated concurrently.

## User-Level Behavior

The MVP should expose a narrow command variant or option on the existing native
runner:

```bash
hermes-workflow run-native-turbo PROJECT_DIR \
  --max-evals 100 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh \
  --parallel
```

The command reads:

- `config/optimizer.yaml` for `batch_size`;
- `config/spectre.yaml` for `threads_per_run` and `parallel_jobs`;
- approved variables, metrics, constraints, and formulas from the existing
  project contracts.

For the current `bridge_test_inv` template, the intended settings are:

```text
optimizer.batch_size = 10
spectre.threads_per_run = 10
spectre.parallel_jobs = 10
```

Meaning:

- each Spectre process uses `threads_per_run` as `+mt=10`;
- at most `parallel_jobs=10` Spectre/OCEAN evaluations may run at once;
- the batch runner may evaluate up to `min(batch_size, parallel_jobs)` real
  candidates concurrently.

## Architecture

C-18 should build directly on `src/hermes_workflow/native_turbo.py`.

The narrow design is:

```text
TuRBO batch candidate generation
-> Hermes quantize/de-duplicate/replacement for each slot
-> prepare real-run packages sequentially
-> run Spectre/OCEAN adapters concurrently up to parallel_jobs
-> check result and metric manifests per run
-> record ledger/state sequentially
-> return objective list to TuRBO in original candidate order
```

Only the real-tool adapter calls run in parallel. File-contract preparation and
ledger/state recording stay sequential to avoid shared-file races.

## Batch-Aware TuRBO Adapter

The current C-17 runner passes a scalar objective `f(x)` into `Turbo1`.
C-18 needs a small batch-aware wrapper around the local `Turbo1` implementation.

The wrapper should preserve TuRBO's candidate generation logic and only replace
the point where a batch is evaluated.

Required behavior:

- initialization points may be evaluated as one or more parallel batches;
- trust-region `X_next` batches should be evaluated in parallel;
- final partial batch must not exceed `max_evals`;
- returned objective values must be handed back to TuRBO in the same order as
  the raw candidates.

The wrapper may live in `native_turbo.py` for the MVP. It should not fork the
TuRBO project or reimplement TuRBO's algorithm broadly.

## Candidate Handling

For each raw candidate in a batch:

- quantize to approved variables;
- format compact Spectre-safe units;
- de-duplicate against all previous candidates and earlier candidates in the
  same batch;
- use bounded replacement candidates when a quantized duplicate appears;
- if no unique replacement exists, return finite duplicate penalty for that
  slot without launching Spectre.

Run IDs and candidate IDs are allocated before parallel execution:

```text
candidate_000001 -> real_001
candidate_000002 -> real_002
...
```

Each trace entry records:

- `batch_id`;
- `batch_slot`;
- `batch_size`;
- selected phase: initialization or trust region;
- raw `x`;
- quantized parameters;
- status;
- objective;
- manifest paths;
- concise issues.

## Parallel Real Evaluation

The parallel evaluator should use a bounded local executor. A Python
`ThreadPoolExecutor` is acceptable because each worker mainly launches external
Spectre/OCEAN subprocesses and waits for files.

The maximum worker count is:

```text
min(optimizer.batch_size, spectre.parallel_jobs)
```

Each worker may:

- run the C-7 adapter for its assigned `run_id`;
- run `check-real-run`;
- run `check-metric-results`;
- return a candidate-local observation.

Each worker must not:

- write optimizer ledger/state;
- mutate shared project config;
- parse PSF;
- rewrite formulas;
- flatten netlist layout.

After all workers in a batch finish, Hermes records successful/checked results
sequentially in run-id order. Candidate-local failures are resolved through the
existing recovery decision path and become finite penalties.

## Failure Semantics

C-18 keeps C-17's feasibility-first objective:

```text
metric/tool candidate-local failure -> failure_penalty
constraint violation -> failure_penalty + normalized violation
feasible candidate -> configured FOM
```

Candidate-local failures include:

- metric non-scalar;
- missing metric scalar;
- duplicate candidate after bounded replacement attempts;
- individual Spectre/OCEAN result failure that Hermes can classify through
  manifests.

Workflow-level failures should stop the runner after the current batch is
classified:

- unsafe paths or symlinks;
- approval/hash/config drift;
- repeated adapter/environment failures with no classifiable returned manifests;
- inability to write reports;
- ledger/state write failure.

The runner should not silently consume a full 100-evaluation budget when the
environment is broken.

## Reports

Reuse the C-17 report locations:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
```

Add batch-level fields rather than new broad report families:

- `batch_id`;
- `batch_slot`;
- `batch_worker_count`;
- `max_parallel_jobs`;
- `threads_per_run`;
- `parallel_jobs`;
- `batch_size`.

The top-level report should summarize:

- total evaluations requested and completed;
- number of batches;
- maximum observed active workers;
- status counts;
- best candidate;
- Spectre settings used.

## Real Acceptance

After unit/fake tests pass, run one real acceptance on a clean `/tmp` project:

- `bridge_test_inv`;
- known-good C-7 exported netlist bundle;
- `max_evals=100`;
- `optimizer.batch_size=10`;
- `spectre.parallel_jobs=10`;
- `spectre.threads_per_run=10`;
- `preset=ax`;
- `output_format=psfxl`;
- approved formulas unchanged.

Acceptance requires:

- the command completes;
- at least one trust-region batch is evaluated;
- no more than `parallel_jobs` Spectre/OCEAN evaluations are active at once;
- every trace row includes batch metadata;
- best candidate is reported;
- metric failures and duplicate penalties are visible;
- raw Cadence artifacts remain local-only.

## Route Alignment

C-18 stays aligned with the corrected practice-first route:

```text
native TuRBO selects candidates
-> Hermes prepares approved packages
-> Spectre/OCEAN computes authoritative scalar metrics
-> Hermes validates and records
```

This feature makes the optimizer useful at real scale without turning the
project into a broad framework. It keeps the execution side deterministic for
the repeated mechanical optimization loop while preserving the execution-agent
boundary for Virtuoso/Maestro setup, export, and future non-scripted tool work.
