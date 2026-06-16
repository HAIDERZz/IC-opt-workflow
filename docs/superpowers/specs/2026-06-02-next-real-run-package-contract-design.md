# Next Real-Run Package Contract Design

Date: 2026-06-02

## Goal

Add C-9 so Hermes workflow tooling can prepare the next real-run package after a checked real result has been recorded.

C-9 closes the single-candidate loop shape:

```text
approve
-> prepare-real-run real_001
-> execution agent runs C-7 adapter
-> check-real-run
-> check-metric-results
-> record-real-result
-> prepare-next-real-run real_002
```

C-9 is still contract-only. It does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter. It only writes the next `runs/real/<run_id>/` package that an execution agent can later consume.

## Locked Role Model

C-9 follows `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

- The supervisor agent calls Hermes workflow tooling and reads machine-readable reports.
- Hermes workflow tooling validates contracts and writes deterministic package files.
- The execution agent runs approved physical tools through the C-7 execution-side adapter.

Do not describe C-9 as a Hermes agent action. Hermes remains the deterministic tooling layer.

## Background

C-4 prepares the first real-run package using the lower-bound candidate. C-7 executes a prepared package through standalone Spectre and batch OCEAN. C-8 records a checked real result into the optimizer ledger and state.

After C-8, the workflow needs a deterministic way to package the next candidate. C-9 adds that step without introducing a full model-based optimizer yet.

The first C-9 version should use the same deterministic candidate sequence already proven by Plan B:

```text
optimizer.yaml initialization + random_seed + variable grids
-> generate_candidates(...)
-> skip candidates already recorded or already prepared
-> write next real-run package
```

This is intentionally simpler than a full TuRBO/model-update implementation. It gives the project an end-to-end real-loop contract while keeping optimization policy transparent and testable.

## Scope

Included:

- Add a library function that prepares the next real-run package after C-8.
- Add a CLI command, `hermes-workflow prepare-next-real-run`.
- Validate immutable config hashes against the approved execution manifest and supervisor instruction.
- Read the real-result ledger strictly.
- Read optimizer state strictly when present.
- Refuse to prepare a next package unless the previous checked result count is below `optimizer.max_evaluations`.
- Generate the deterministic candidate sequence from `optimizer.yaml`.
- Skip candidates already present in real-result ledger rows.
- Skip candidates already prepared in existing `runs/real/<run_id>/candidate.json` files.
- Select the next unique candidate and write a standard C-4/C-6-compatible package.
- Write `input.scs`, `candidate.json`, `metric_extraction_request.json`, and `real_run_manifest.json`.
- Preserve exact approved OCEAN formulas by reusing C-6 metric request generation.
- Refuse to overwrite an existing run package.
- Clean up partial run directories after write failure.

Excluded:

- Running real Virtuoso, Spectre, OCEAN, SSH, Claude CLI, or `virtuoso-bridge-lite`.
- Calling the C-7 execution adapter.
- Parsing PSF or waveform databases.
- Rewriting or discovering OCEAN formulas.
- Computing real metrics in Python.
- Adding failure-penalty rows.
- Retrying failed real tool runs.
- Batch/multi-candidate real-run scheduling.
- TuRBO model fitting, Gaussian processes, trust-region updates, or acquisition functions.
- Sweep/corner/family aggregation.

## Real Tool Name Boundary

C-9 does not need local Cadence executable names or paths.

The package it writes must still carry the already approved real backend identity from existing contracts:

- `spectre.engine`, currently `spectre_x`
- `spectre.output_format`, expected by C-7 as `psfxl`
- metric request backend, `spectre_ocean_batch`
- metric request mode, `nograph_replay`
- exact OCEAN expressions from `metrics.yaml`

Those values tell the execution agent and C-7 adapter what kind of real tool execution is expected. They do not authorize C-9 to run the tools.

## Inputs

C-9 reads:

- `config/project_config.yaml`
- `config/variables.yaml`
- `config/metrics.yaml`
- `config/spectre.yaml`
- `config/optimizer.yaml`
- `execution_package/execution_manifest.json`
- `supervisor_instruction.json`
- `netlists/templates/template.scs`
- `ledger/experiment_ledger.jsonl`
- `state/optimizer_state.json`, when present
- existing `runs/real/*/candidate.json`, when present

The first-real-run approval remains sufficient for the real optimization sequence as long as immutable config hashes remain unchanged. C-9 must fail closed on config hash drift.

## Outputs

For a selected next run id, C-9 writes:

```text
runs/real/<run_id>/input.scs
runs/real/<run_id>/candidate.json
runs/real/<run_id>/metric_extraction_request.json
runs/real/<run_id>/real_run_manifest.json
```

The output shape remains compatible with:

```text
tools/run_spectre_ocean_adapter.py
hermes-workflow check-real-run
hermes-workflow check-metric-results
hermes-workflow record-real-result
```

No optimizer ledger or state files are written by C-9. Ledger/state writes remain C-8's responsibility after a checked real result is available.

## Run Id Policy

Default selection:

- Inspect existing `runs/real/real_[0-9][0-9][0-9]` directories.
- Select the smallest positive unused id, formatted as `real_002`, `real_003`, and so on.
- `real_001` remains reserved for C-4 first-real-run semantics.

CLI override:

- `--run-id real_###` may be provided.
- The override must match the existing run id pattern.
- The override must not already have a `real_run_manifest.json`.
- The override may not be `real_001`; callers should use `prepare-real-run` for the first package.

This policy avoids coupling run ids to chat history and tolerates a missing or manually removed failed run directory. The ledger and candidate dedupe checks still prevent reusing evaluated candidates.

## Candidate Selection Policy

C-9 uses the existing Plan B candidate generator:

```python
generate_candidates(
    bundle,
    n_candidates=bundle.optimizer.optimizer.max_evaluations,
    seed=bundle.optimizer.optimizer.random_seed,
    initialization=bundle.optimizer.optimizer.initialization.value,
)
```

Candidate ids should match the real run id by default. For example, `real_002` writes:

```json
{
  "schema_version": "1.0",
  "candidate_id": "real_002",
  "source": "deterministic_initialization_sequence",
  "candidate_index": 2,
  "parameters": {
    "...": "..."
  }
}
```

Selection rules:

- Build a set of parameter tuples from strict ledger rows.
- Build a set of parameter tuples from existing prepared real-run `candidate.json` files.
- Iterate the deterministic candidate sequence in order.
- Pick the first candidate whose parameter tuple is not in either set.
- Store the one-based `candidate_index` from the deterministic sequence.
- Fail closed if no unique candidate remains.

The first generated sequence item may equal the lower-bound `real_001` candidate or may differ, depending on the configured initialization method. C-9 must not assume it is identical. It relies on explicit dedupe against ledger and prepared candidates.

## Optimizer State Policy

C-9 reads `state/optimizer_state.json` when present and validates it as `OptimizerState`.

It must fail closed when:

- `current_evaluations >= max_evaluations`
- state `max_evaluations`, `batch_size`, `random_seed`, `algorithm`, or `initialization` disagrees with `optimizer.yaml`
- state `status` is `completed` or `stopped`
- strict ledger row count and state `current_evaluations` disagree

If state is absent but the ledger has exactly one valid real-result row, C-9 may continue. This allows recovery from a missing derived state file after a successful C-8 ledger append, but the implementation should prefer the normal state-present path.

## Manifest Additions

`real_run_manifest.json` should preserve the existing C-4 fields and update candidate provenance:

```json
{
  "candidate_source": "deterministic_initialization_sequence",
  "candidate_index": 2,
  "selection_policy": "next_unique_from_optimizer_initialization_sequence",
  "ledger_snapshot_sha256": "...",
  "optimizer_state_sha256": "...",
  "previous_evaluations": 1
}
```

`optimizer_state_sha256` may be `null` when state is absent and the recovery rule above is used.

`ledger_snapshot_sha256` should hash the exact current ledger file bytes, or a stable empty-ledger marker when the ledger file is absent. For normal C-9 usage after C-8, the ledger file should exist.

## Error Handling

C-9 must fail closed and avoid output writes when:

- project validation fails
- supervisor instruction is missing or not `approve_first_real_run`
- immutable config hashes drift
- execution manifest and supervisor-approved hashes disagree
- `template.scs` is missing
- ledger has invalid JSON or invalid row schema
- optimizer state has invalid JSON or invalid schema
- optimizer state disagrees with `optimizer.yaml`
- maximum evaluations have already been reached
- selected run id is invalid or already prepared
- candidate sequence has no unique remaining candidate
- template rendering leaves unresolved placeholders
- metric request generation fails

If a write fails after the run directory is created, C-9 should remove the partial run directory, matching C-4 cleanup behavior.

## CLI

Add:

```bash
hermes-workflow prepare-next-real-run PROJECT_DIR [--run-id real_###]
```

Passing output:

```text
next real run package prepared
run: runs/real/real_002
manifest: runs/real/real_002/real_run_manifest.json
candidate: runs/real/real_002/candidate.json
```

Failure output should mirror existing CLI style: print the error message and exit with code 1.

## Testing Strategy

Use unit tests with synthetic project fixtures only. Do not run real Cadence tools.

Required test classes:

- happy path after a recorded `real_001` result prepares `real_002`
- selected candidate is unique against ledger rows
- selected candidate is unique against already prepared run packages
- refuses when max evaluations reached
- refuses invalid ledger rows
- refuses optimizer state/config drift
- refuses overwrite of existing run package
- refuses `--run-id real_001`
- cleans up partial run directory after a forced write failure
- generated package passes existing `check_real_run` and `check_metric_results` after fake C-7 result artifacts are supplied

Verification commands:

```bash
python3 -m pytest tests/test_next_real_run.py -q
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

## Review Gates

C-9 is medium-to-high risk because it writes next real-run packages and controls candidate progression.

Use Risk-Tiered Batch Gates:

- High risk tasks: run local tests plus code-quality review after candidate selection and package write logic.
- Medium risk tasks: batch CLI and integration tests into one review gate.
- Low risk docs/progress updates: local verification first, final combined review at the end.

No review gate may require real Spectre/OCEAN execution.

## Non-Goals

C-9 does not implement:

- real tool integration
- local Cadence smoke
- failure/retry policy
- failure-penalty rows
- model-based optimizer updates
- batch scheduling
- formula discovery
- formula rewriting
- PSF parsing

## Next Scope After C-9

After C-9, the natural next scopes are:

- failure/retry policy for failed real-run packages
- a local smoke that chains C-9 package generation through C-7/C-8 on a known test cell
- model-based optimizer policy beyond deterministic initialization sequence
- batch/multi-candidate scheduling
