# Candidate-Injection Package Contract Design

Date: 2026-06-04

## Goal

Add a narrow Hermes workflow contract that prepares a real-run package for an explicitly supplied optimizer candidate.

The immediate productization gap from optimizer practice is:

```text
optimizer-selected parameters
-> deterministic runs/real/<run_id>/ package for that exact candidate
-> existing C-7 Spectre/OCEAN adapter
-> existing check-real-run/check-metric-results/record-real-result
```

This design does not add a new optimizer algorithm. It only adds the missing package-preparation contract so future optimizer-side code does not need to rewrite `config/variables.yaml` or create one isolated project per candidate.

## Background

Optimizer Practice-First Task 4 proved the real route:

```text
local Turbo1
-> Hermes package/check/record contracts
-> C-7 Spectre/OCEAN adapter
-> OCEAN scalar metrics
-> finite objective returned to TuRBO
```

The proof used `/tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py`. It ran `9` evaluations with `n_init=8`, `max_evals=9`, and `batch_size=1`. All `9` evaluations produced OCEAN scalar metrics and finite objectives. The best post-initial TuRBO candidate was:

```text
FN = 12
WN = 1.3u
FP = 2
WP = 2.5u
objective = 4.183168953894332e-14
```

The practice workaround created one isolated project per candidate and locked each candidate into `config/variables.yaml` by setting lower and upper bounds to the same value. That is valid evidence, but it is not the product interface. Project-level variable bounds are the design space contract and should not be mutated to express one optimizer suggestion.

## Locked Role Model

This scope follows `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

- The supervisor agent approves workflow progression and reads reports.
- Hermes workflow tooling validates file contracts and prepares deterministic run packages.
- The execution agent runs physical tools only after a package exists.

Hermes workflow tooling does not run Spectre, OCEAN, SSH, Claude CLI, or `virtuoso-bridge-lite` in this scope.

## Scope

Included:

- Add a candidate-injection request file contract.
- Add a Hermes library path that prepares a real-run package for an explicit candidate request.
- Add a CLI command for this package-preparation path.
- Validate candidate parameters against `config/variables.yaml` without changing that file.
- Reuse the proven real-run package shape:

```text
runs/real/<run_id>/netlist/input.scs
runs/real/<run_id>/candidate.json
runs/real/<run_id>/candidate_request.json
runs/real/<run_id>/metric_extraction_request.json
runs/real/<run_id>/real_run_manifest.json
```

- Preserve the C-7 closure layout: Spectre runs from `runs/real/<run_id>/netlist/` and writes PSF to sibling `runs/real/<run_id>/psf/`.
- Reuse existing metric request generation so approved OCEAN formulas stay unchanged.
- Reuse C-10 unresolved-run guard semantics before preparing a new candidate package.
- Refuse duplicate candidate ids and duplicate parameter tuples.
- Refuse to overwrite an existing run package.
- Clean up partial run directories after write failure.

Excluded:

- Replacing C-4 first real-run preparation.
- Replacing C-9 deterministic next-run preparation.
- Running real Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- Parsing PSF or waveform databases.
- Rewriting or discovering OCEAN formulas.
- Computing metrics in Python.
- Adding TuRBO, Gaussian process, acquisition, trust-region, or optimizer-state update logic.
- Writing optimizer ledger/state.
- Recording failure-penalty rows.
- Batch scheduling multiple outstanding real-run packages.
- Sweep, corner, or family aggregation.

## Design Options Considered

### Option A: Continue Rewriting `config/variables.yaml`

The practice script proved this can run, but it mutates the project-level design-space contract for every candidate. That makes audit trails noisy and risks confusing bounds with chosen values.

This option is rejected.

### Option B: Extend `prepare-next-real-run` With Inline Parameters

Adding parameter flags to `prepare-next-real-run` would reduce the number of commands, but it would mix two different candidate sources: deterministic Hermes-generated next candidates and externally selected optimizer candidates. That makes logs and reports harder to interpret.

This option is rejected for the first productization step.

### Option C: Add A Focused Candidate-Injection Command

Add a separate package-preparation command that consumes one candidate request file and writes one standard real-run package.

This is the chosen design. It keeps the deterministic C-9 route intact, makes optimizer-selected candidates explicit, and gives future optimizer adapters a narrow file-contract boundary.

## Candidate Request Contract

The supervisor or optimizer-side adapter supplies one JSON request file:

```json
{
  "schema_version": "1.0",
  "candidate_id": "candidate_000009",
  "source": "optimizer_turbo_suggestion",
  "parameters": {
    "FN": "12",
    "WN": "1.3u",
    "FP": "2",
    "WP": "2.5u"
  },
  "metadata": {
    "optimizer": "turbo",
    "evaluation_index": 9
  }
}
```

Required fields:

- `schema_version`: must be `"1.0"`.
- `candidate_id`: non-empty safe identifier using letters, digits, `_`, `.`, or `-`.
- `source`: non-empty string describing who selected the candidate.
- `parameters`: object with exactly the same variable names as `config/variables.yaml`.

Optional field:

- `metadata`: object copied into `candidate.json` for traceability. Hermes does not interpret optimizer internals from this field.

The candidate request file is copied into the run package as:

```text
runs/real/<run_id>/candidate_request.json
```

The package records the copied request SHA-256. The copied file, not the caller's original path, is the durable package evidence.

## Candidate Validation

Candidate parameters must be strings and must validate against `config/variables.yaml`:

- Every configured variable must be present exactly once.
- No extra parameter names are allowed.
- `integer` variables must be integer strings, within inclusive bounds, and aligned to `step`.
- `continuous_step` variables must use compact Spectre-safe unit formatting such as `0.3u`, not whitespace-separated values such as `0.3 um`.
- `continuous_step` values must be within inclusive bounds and aligned to `step`.
- Candidate parameter strings are preserved as supplied after validation; Hermes does not canonicalize them into a different unit spelling.

Validation must fail before any run directory is written.

## Placement In The Workflow

This contract starts after at least one checked real result has been recorded.

The normal flow is:

```text
C-4 prepare-real-run real_001
-> C-7 execute real_001
-> check-real-run
-> check-metric-results
-> C-8 record-real-result
-> candidate-injection package contract for real_002+
```

This scope does not replace C-4. `real_001` remains the first approved real-run package path unless a later design deliberately changes first-run policy.

Before preparing an injected candidate package, Hermes must:

- validate the project bundle;
- verify approval/config hashes remain valid;
- verify there is no unresolved real-run package according to C-10 semantics;
- verify at least one checked real-result ledger row exists;
- verify the optimizer maximum evaluation budget has not been reached.

## Run Id Policy

Default selection:

- Inspect existing `runs/real/real_[0-9][0-9][0-9]` directories.
- Select the smallest unused run id greater than `real_001`.

CLI override:

- `--run-id real_###` may be provided.
- The override must match the run id pattern.
- The override must be greater than `real_001`.
- The override must not already exist as a prepared or partial run package.

Retries remain C-10's responsibility. This command must not be used to retry the same candidate after a failed package.

## Dedupe Policy

Hermes must reject candidate injection when:

- the candidate id already appears in an existing `runs/real/*/candidate.json`;
- the candidate id already appears in `ledger/experiment_ledger.jsonl`;
- the parameter tuple already appears in an existing prepared package;
- the parameter tuple already appears in a valid ledger row.

Parameter tuple comparison uses variable names from `config/variables.yaml` in order and exact validated string values.

This keeps optimizer-side dedupe bugs from creating duplicate real runs.

## Package Outputs

For the selected run id, Hermes writes:

```text
runs/real/<run_id>/netlist/input.scs
runs/real/<run_id>/candidate_request.json
runs/real/<run_id>/candidate.json
runs/real/<run_id>/metric_extraction_request.json
runs/real/<run_id>/real_run_manifest.json
```

The netlist directory must also contain the safe exported sidecars required by the Maestro/ADE deck, matching the C-7 closure path.

`candidate.json` should look like:

```json
{
  "schema_version": "1.0",
  "candidate_id": "candidate_000009",
  "source": "explicit_candidate_request",
  "requested_source": "optimizer_turbo_suggestion",
  "parameters": {
    "FN": "12",
    "WN": "1.3u",
    "FP": "2",
    "WP": "2.5u"
  },
  "candidate_request_file": "runs/real/real_002/candidate_request.json",
  "candidate_request_sha256": "...",
  "metadata": {
    "optimizer": "turbo",
    "evaluation_index": 9
  }
}
```

`real_run_manifest.json` should preserve existing C-4/C-6/C-9 fields and add:

```json
{
  "candidate_source": "explicit_candidate_request",
  "selection_policy": "explicit_candidate_injection",
  "candidate_request_file": "runs/real/real_002/candidate_request.json",
  "candidate_request_sha256": "...",
  "ledger_snapshot_sha256": "...",
  "optimizer_state_sha256": "...",
  "previous_evaluations": 1
}
```

`optimizer_state_sha256` may be `null` only when the implementation already permits ledger-only recovery for the equivalent C-9 state check. Normal operation should have optimizer state.

## CLI

Add:

```bash
hermes-workflow prepare-candidate-real-run PROJECT_DIR --candidate-file PATH [--run-id real_###]
```

Passing output:

```text
candidate real run package prepared
run: runs/real/real_002
manifest: runs/real/real_002/real_run_manifest.json
candidate: runs/real/real_002/candidate.json
candidate request: runs/real/real_002/candidate_request.json
```

Failure output should follow existing Hermes CLI style: print the error message and exit with code `1`.

## Error Handling

The command must fail closed and avoid output writes when:

- project validation fails;
- approval or immutable config hash checks fail;
- unresolved real-run packages exist;
- no checked real-result ledger row exists;
- optimizer budget is exhausted;
- candidate request JSON is missing, malformed, or schema-invalid;
- candidate id is unsafe or duplicated;
- candidate parameters are missing, extra, out of bounds, or step-invalid;
- run id is invalid, `real_001`, already prepared, or partially occupied;
- exported netlist sidecars are unsafe;
- template rendering leaves unresolved placeholders;
- metric request generation fails.

If a write fails after creating `runs/real/<run_id>/`, Hermes should remove the partial run directory unless the directory existed before the command started.

## Testing Strategy

Use synthetic fixtures and fake C-7 artifacts only. Do not run real Cadence tools.

Required tests:

- happy path after recorded `real_001` prepares explicit candidate package for `real_002`;
- package preserves ADE-style `netlist/` sidecars and sibling `psf` expectation;
- `candidate_request.json` is copied and hashed;
- `candidate.json`, `real_run_manifest.json`, and `metric_extraction_request.json` agree on run id, candidate id, paths, and hashes;
- `config/variables.yaml` is not modified;
- rejects missing, extra, out-of-bounds, step-invalid, or whitespace-unit parameters;
- rejects duplicate candidate id from ledger;
- rejects duplicate parameter tuple from ledger;
- rejects duplicate candidate id from prepared run package;
- rejects duplicate parameter tuple from prepared run package;
- rejects unresolved real-run packages;
- rejects `--run-id real_001`;
- cleans up partial run directory after forced write failure;
- generated package can pass existing `check-real-run`, `check-metric-results`, and `record-real-result` once fake C-7 result artifacts are supplied.

Verification commands:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
python3 -m pytest tests/test_next_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```

## Review Gate

This scope is high risk when implemented because it writes real-run packages and controls candidate progression. The implementation should use spec-compliance and code-quality review before any task is marked `reviewed`.

The design spec itself is docs-only and may remain `verified-only`.

## Next Step

After this design is accepted, write a focused implementation plan. The first implementation plan should keep tasks narrow:

1. candidate request schema and validation;
2. library package preparation reusing the existing C-4/C-6/C-9 package writer pieces;
3. CLI wiring and focused tests;
4. local smoke with fake C-7 artifacts only.

Do not start Hermes optimizer algorithm productization until this candidate-injection contract is implemented and verified.
