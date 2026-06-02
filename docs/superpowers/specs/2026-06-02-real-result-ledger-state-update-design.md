# Real Result Ledger State Update Design

Date: 2026-06-02

## Purpose

C-8 records a checked real simulation result into optimizer ledger and state files.

The feature closes the deterministic handoff after C-7:

```text
prepare-real-run
-> execution agent runs C-7 Spectre + OCEAN adapter
-> check-real-run
-> check-metric-results
-> C-8 record-real-result
-> ledger/experiment_ledger.jsonl + state/optimizer_state.json + state/best_candidate.json
```

C-8 is contract-only. It does not call Virtuoso, Spectre, OCEAN, SSH, Claude CLI, or the C-7 adapter. It consumes already written project files and already validated report data.

## Locked Role Boundary

The supervisor agent owns the decision to record a real result. Hermes workflow tooling owns deterministic validation and file writes. The execution agent owns physical tool execution before this step.

C-8 must preserve these boundaries:

- The supervisor agent may call `hermes-workflow record-real-result`.
- Hermes workflow tooling may rerun deterministic `check-real-run` and `check-metric-results`.
- Hermes workflow tooling may append ledger rows and update optimizer state after both checks pass.
- Hermes workflow tooling must not run real Cadence tools.
- Hermes workflow tooling must not parse PSF or waveform data.
- Hermes workflow tooling must not translate or recompute OCEAN/Calculator formulas in Python.

## Inputs

For a selected run id, defaulting to `real_001`, C-8 reads:

```text
config/*.yaml
runs/real/<run_id>/candidate.json
runs/real/<run_id>/real_run_manifest.json
runs/real/<run_id>/result_manifest.json
runs/real/<run_id>/metric_extraction_request.json
runs/real/<run_id>/metrics/metric_result_manifest.json
reports/real_run_check_report.json
reports/metric_result_check_report.json
ledger/experiment_ledger.jsonl
state/optimizer_state.json
state/best_candidate.json
```

The reports are not trusted as stale files. The record operation should rerun `check_real_run()` and `check_metric_results()` before writing optimizer files. If either report returns fail, C-8 must not write ledger or state.

## Outputs

C-8 writes or updates:

```text
ledger/experiment_ledger.jsonl
state/optimizer_state.json
state/best_candidate.json
reports/real_result_record_report.json
```

`reports/real_result_record_report.json` is a machine-readable report recording whether the ledger/state update happened and why.

## Ledger Contract

C-8 should extend the existing `LedgerRow` model instead of creating a separate ledger file. Keeping one ledger preserves a single optimizer history across mock and real evaluations.

Existing fields stay required:

```text
candidate_id
parameters
metrics
constraints_passed
objective
batch_id
simulation_status
timestamp_utc
```

New optional fields should be added:

```text
result_source: "mock" | "real"
run_id: string | null
result_manifest: string | null
metric_result_manifest: string | null
```

Backwards compatibility:

- Existing mock rows without the new fields remain valid.
- Mock optimizer rows may continue to write `result_source: "mock"` or omit the optional real-result fields.

Simulation status values should become:

```text
mock_pass
mock_constraint_fail
mock_error
real_pass
real_constraint_fail
```

`real_error` is intentionally not introduced in C-8. Real simulator or metric extraction failures should fail closed before ledger append. Failure-penalty rows belong to a later failure-recovery plan.

## State Contract

C-8 reuses existing `OptimizerState` and `BestCandidate`.

State update rules:

- `current_evaluations` becomes the number of valid ledger rows after append.
- `best_candidate_id` points to `state/best_candidate.json` when a feasible real result becomes the best known candidate.
- `status` stays `running` until `current_evaluations >= optimizer.max_evaluations`, then becomes `completed`.
- `started_at_utc` is preserved from existing state when present; otherwise it is initialized to the record timestamp.
- `updated_at_utc` is set to the record timestamp.

Best candidate update rules:

- Only rows with `constraints_passed: true` are eligible.
- Objective values use the same normalized minimization convention as the mock optimizer: maximize objectives are negated before comparison.
- If there is no existing feasible best candidate, the current feasible row becomes best.
- If the current feasible row has a lower normalized objective than the existing best, it replaces best.
- Constraint-failing rows are recorded in the ledger but do not replace best.

## Metric And Objective Derivation

C-8 derives metrics from `MetricResultCheckReport.metrics`.

Required behavior:

- Every metric used by the configured objective and constraints must be present.
- Every metric value must be finite.
- Constraint evaluation uses the existing `evaluate_constraints()` helper.
- Objective evaluation uses the existing objective expression evaluator through `evaluate_objective_from_config()`.
- The written `metrics` dictionary contains scalar float values only.

C-8 does not read OCEAN scalar TSV directly. That parsing already belongs to C-7 and C-6 validation.

## Duplicate Protection

The record operation must fail closed if the ledger already contains:

- the same `run_id`, or
- the same `candidate_id`.

This prevents accidental double append after repeated CLI calls.

If a caller wants to intentionally re-record a result, that needs a later explicit repair workflow. C-8 should not provide `--force`.

## API And CLI

Add a library function with this signature:

```python
def record_real_result(
    project_dir: Path,
    *,
    run_id: str | None = None,
    recorded_at_utc: str | None = None,
) -> RealResultRecordReport
```

Add a CLI command:

```bash
hermes-workflow record-real-result projects/bridge_test_inv --run-id real_001
```

Success output should be concise:

```text
real result recorded
run: runs/real/real_001
ledger: ledger/experiment_ledger.jsonl
state: state/optimizer_state.json
report: reports/real_result_record_report.json
```

Failure output should include issues and the report path without a traceback.

## Failure Behavior

C-8 must write a failed `reports/real_result_record_report.json` and avoid ledger/state writes when:

- config validation fails
- `check-real-run` fails
- `check-metric-results` fails
- `candidate.json` is missing or invalid
- candidate id mismatches the selected run result
- metric values are missing or non-finite
- objective evaluation fails
- constraints cannot be evaluated
- ledger already contains the same run id or candidate id
- existing ledger contains invalid JSON

`state/best_candidate.json` is a derived file, not the source of truth. C-8 should
derive best-candidate state from valid ledger rows plus the current checked row. A
stale or invalid `best_candidate.json` should be repaired from the ledger-derived
best candidate, or removed when no feasible ledger-derived best exists.

The implementation should prepare all derived payloads before any state-changing write. The ledger is the source of truth, and optimizer state is derived from ledger content. After precondition checks and payload preparation pass, write in this order:

```text
experiment_ledger.jsonl append
best_candidate.json when needed
optimizer_state.json
real_result_record_report.json
```

If a derived state write fails after ledger append, the exception may propagate and a later repair workflow can rebuild state from the ledger. C-8 must still guarantee no ledger/state writes occur for validation and precondition failures.

## Testing Strategy

Automated tests use sanitized fake result files only.

Required tests:

- pass path records a checked real result and writes ledger/state/report
- `record-real-result` reruns deterministic checkers before writing
- duplicate run id is rejected without appending
- duplicate candidate id is rejected without appending
- failed `check-real-run` prevents writes
- failed `check-metric-results` prevents writes
- constraint-failing real result appends ledger row but does not update best
- feasible better real result updates `best_candidate.json`
- feasible worse real result preserves existing best
- maximize objective uses normalized minimization before comparison
- CLI pass and fail paths avoid tracebacks

Verification commands:

```bash
python3 -m pytest tests/test_real_result_record.py tests/test_cli.py tests/test_mock_optimizer.py -q
python3 -m ruff check src tests tools
git diff --check
```

## Non-Goals

C-8 does not implement:

- next-candidate generation
- TuRBO model update
- batch scheduling
- retry policy
- failure-penalty ledger rows
- real Cadence tool invocation
- real adapter smoke tests
- PSF parsing
- formula discovery
- formula approval

## Next Scope After C-8

After C-8, the natural next scopes are:

- C-9 next-candidate generation from optimizer state
- failure and retry policy for failed real runs
- local smoke connecting C-7 adapter output into C-8 record flow
- batch/multi-run support
