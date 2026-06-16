# Single-Candidate Optimizer Suggestion MVP Design

Date: 2026-06-04

## Purpose

This spec defines the narrow C-13 MVP for turning the proven optimizer practice flow into one product feature:

```text
existing project config + real-run ledger/state
-> suggest exactly one optimizer candidate request
-> existing candidate-injection package contract
-> existing real-tool execution path
```

The goal is not to build a full optimizer framework. The goal is to let the supervisor agent ask Hermes workflow tooling for the next single candidate in a way that can immediately be tested in the real Virtuoso/Spectre/OCEAN loop.

## Route Decision

The project now keeps the already-built contracts and moves toward practical use faster:

- Keep the existing file-contract layers.
- Preserve native Maestro/ADE/Spectre/OCEAN result layout.
- Use the candidate-injection package contract as the handoff boundary.
- Add only the missing single-candidate suggestion step.
- Validate with real tool usage in the next phase instead of adding speculative orchestration.

C-13 is therefore contract-first but intentionally small. C-14 should perform the real-tool acceptance flow.

## Inputs

The suggestion step reads an existing Hermes project directory and uses only project-owned files:

- `config/variables.yaml`
- `config/optimizer.yaml`
- `ledger/experiment_ledger.jsonl`
- `state/optimizer_state.json`
- existing real-run recovery/check state used by the C-10 unresolved-run guard

It must not read PSF data. It must not reinterpret Calculator or OCEAN formulas.

## Output

The output is exactly one candidate request JSON compatible with the existing candidate-injection package contract:

```json
{
  "schema_version": "1.0",
  "candidate_id": "candidate_000010",
  "source": "optimizer_turbo_suggestion",
  "parameters": {
    "FN": "12",
    "WN": "1.3u",
    "FP": "2",
    "WP": "2.5u"
  },
  "metadata": {
    "optimizer": "turbo",
    "selection_mode": "turbo",
    "evaluation_index": 10,
    "ledger_rows_seen": 9,
    "optimizer_state_sha256": "<sha256>",
    "ledger_sha256": "<sha256>"
  }
}
```

Default output path:

```text
candidate_requests/<candidate_id>.json
```

The suggestion command must not create `runs/real/<run_id>`. Existing `prepare-candidate-real-run` owns that package creation step.

## CLI

Add one command:

```text
hermes-workflow suggest-candidate PROJECT_DIR [--candidate-id ID] [--output PATH]
```

Behavior:

- Validate the project before suggesting.
- Refuse to overwrite an existing output file unless an explicit existing local pattern already supports overwrite; otherwise keep overwrite out of scope.
- Write one candidate request atomically.
- Print the output path and candidate id on success.
- Return a clear nonzero failure on invalid or unsafe state.

## Selection Policy

The MVP must be evidence-led and deterministic.

Preferred path:

- If `config/optimizer.yaml` selects TuRBO and the current history is sufficient for the local TuRBO implementation, use the local TuRBO suggestion path proven during optimizer practice-first validation.

Fallback path:

- If TuRBO cannot yet suggest because there are not enough valid observations, use the existing initialization candidate-generation behavior already present in the project.
- The fallback must be explicit in output metadata as `selection_mode: "initialization_fallback"`.
- Do not invent a new optimization algorithm.

Ledger interpretation:

- Recorded rows with finite objectives/metrics may be used as observations.
- Recorded rows whose parameters were evaluated but did not produce usable finite metrics must still count for de-duplication.
- A candidate that fails project performance goals is not a tooling failure if the real tool flow completed and returned interpretable status.

## Safety Rules

The command fails closed when:

- The project directory is invalid.
- Required config, ledger, or optimizer state files are missing.
- The C-10 unresolved real-run guard reports an unresolved real-run state.
- Optimizer state says the campaign is complete, stopped, or at max evaluations.
- No unique candidate remains inside the configured bounds.
- The generated candidate violates `variables.yaml` bounds, step, allowed name, or Spectre unit formatting rules.
- The output file already exists.

Failure must leave no partial candidate request file.

## Out Of Scope

C-13 does not include:

- Real Virtuoso, Spectre, OCEAN, SSH, or execution-agent invocation.
- Automatic call to `prepare-candidate-real-run`.
- Batch candidate generation.
- Continuous optimizer loop orchestration.
- New optimizer ledger/state schemas beyond fields strictly needed for this command.
- Multi-corner, sweep, or family optimization.
- PSF parsing.
- Python reimplementation of Calculator/OCEAN formulas.
- Replacement of native Maestro/ADE result layout.

## Minimal Implementation Shape

Expected module shape:

```text
src/hermes_workflow/optimizer_suggestion.py
```

Expected public function shape:

```python
suggest_candidate_request(project_dir, *, candidate_id=None, output_path=None)
```

The implementation should reuse existing helpers for:

- project path resolution
- YAML/JSON reading
- candidate validation
- duplicate detection
- candidate request writing
- unresolved real-run guard logic

Do not create a separate workflow engine for this.

## Tests

C-13 tests should stay local and fast:

- Missing ledger/state fails closed.
- Unresolved real-run state fails closed.
- Completed or max-evaluation state fails closed.
- A valid project writes exactly one candidate request.
- The candidate request can be passed to `prepare-candidate-real-run`.
- Duplicate parameter sets are skipped or rejected according to existing candidate-injection behavior.
- Output overwrite is rejected.

No real-tool tests belong in C-13.

## Real-Tool Acceptance In C-14

The next phase should immediately validate the feature against the real working path:

```text
suggest-candidate
-> prepare-candidate-real-run
-> Spectre/OCEAN adapter
-> check-real-run
-> check-metric-results
-> record-real-result
```

The first C-14 practice case should use the proven `bridge_test_inv` setup and should preserve the known-good Maestro/ADE/Spectre/OCEAN file layout.

## Acceptance Criteria

C-13 is complete when:

- `hermes-workflow suggest-candidate PROJECT_DIR` writes one valid candidate request.
- The output validates under the candidate-injection package contract.
- The output can be consumed by `prepare-candidate-real-run` without manual edits.
- Local tests cover failure and happy paths.
- No real-tool invocation is added to C-13.
- The implementation remains a thin bridge from optimizer state to candidate request, not a new optimizer framework.
