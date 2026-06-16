# Real-Run Failure Retry Policy Contract Design

Date: 2026-06-02

## Goal

Add C-10 so the workflow has an explicit contract for failed, partial, pending, and retried real-run packages.

C-10 protects the loop after C-9:

```text
prepare-next-real-run
-> execution agent runs C-7 adapter
-> check-real-run
-> check-metric-results
-> record-real-result OR C-10 recovery decision
-> prepare retry package OR abandon candidate OR stop
```

C-10 is contract-only. It does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter. It does not parse PSF, rewrite OCEAN formulas, or compute metric values. It only classifies file-contract state and writes deterministic recovery artifacts.

## Locked Role Model

C-10 follows `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

- The supervisor agent owns the decision to retry, abandon, stop, or revise contracts.
- Hermes workflow tooling owns deterministic classification, validation, report writing, and retry package preparation.
- The execution agent owns physical tool execution after a retry package exists.

Do not describe C-10 as an execution-agent retry loop. The execution agent may rerun tools only after the supervisor agent has used Hermes workflow tooling to create an approved retry package.

## Background

C-7 can produce either successful or failed real-run artifacts. C-5 and C-6 can validate whether those artifacts are structurally acceptable and whether OCEAN-produced scalar metrics satisfy the metric contract. C-8 records only checked successful metric results into optimizer ledger/state. C-9 prepares the next unique real-run package after C-8 has recorded a checked result.

The missing piece is failure control. Without C-10, a failed `real_002` can leave the workflow in an ambiguous state:

- the candidate is prepared but not ledger-recorded
- artifacts may be partial or failed
- C-9 may skip the prepared candidate and package another one
- a human may manually rerun tools and overwrite evidence
- an execution-agent prose message may be mistaken for workflow state

C-10 makes that state explicit and file-backed.

## Scope

Included:

- Add a real-run recovery assessment report.
- Add a per-run recovery decision artifact.
- Classify pending, failed, partial, metric-failed, contract-invalid, recordable, and already-recorded runs.
- Define which actions are allowed for each classification.
- Prepare a retry package for the same candidate without overwriting the failed run.
- Preserve failed-run artifacts as evidence.
- Guard `prepare-next-real-run` from advancing while unresolved real-run packages exist.
- Keep failed real runs out of the optimizer ledger unless a later explicit failure-penalty plan changes that policy.

Excluded:

- Running real Spectre or OCEAN.
- Calling the C-7 adapter.
- Parsing PSF or waveform databases.
- Rewriting or discovering OCEAN formulas.
- Computing metrics in Python.
- Adding failure-penalty ledger rows.
- Batch scheduling or multiple outstanding real runs.
- Automatic retry without supervisor decision.
- TuRBO/model-based optimizer updates.
- Multi-corner or sweep recovery policy.

## Design Options Considered

### Option A: Retry In The Same Run Directory

Retrying inside `runs/real/<run_id>/` would preserve the run id, but it risks overwriting the original failure evidence and conflicts with C-7's existing overwrite safety. It also makes it hard to prove which artifacts came from which attempt.

This option is rejected.

### Option B: Attempt Subdirectories Under One Run Id

Using `runs/real/<run_id>/attempts/attempt_002/` is semantically clean, but it requires changing C-5, C-6, C-7, C-8, and C-9 to resolve attempt paths. That is a larger migration than C-10 needs.

This option remains a future possibility.

### Option C: New Run Id For Each Retry, Same Candidate Identity

A retry writes a new `runs/real/real_###/` package, but preserves the original `candidate_id` and parameters. The new package declares `retry_of_run_id` and `retry_attempt_number`.

This is the chosen design. It preserves compatibility with the existing C-4/C-6/C-7/C-8 package shape, avoids overwrites, and keeps failed evidence immutable.

## Run State Classification

C-10 classifies a selected run id into exactly one state:

```text
pending_execution
contract_invalid
tool_result_missing
tool_result_failed
tool_result_partial
metric_result_missing
metric_result_failed
recordable_success
already_recorded
resolved_retry_prepared
resolved_abandoned
resolved_stopped
```

Meaning:

- `pending_execution`: prepared package exists, but no `result_manifest.json` or execution-attempt evidence exists yet.
- `contract_invalid`: prepared package, candidate, result handoff, or metric request is structurally invalid.
- `tool_result_missing`: execution-attempt evidence exists, such as adapter logs, stdout/stderr files, PSF directories, or metric directories, but `result_manifest.json` is absent.
- `tool_result_failed`: `result_manifest.json` exists with `status: "failed"` and the handoff is otherwise valid enough to identify the run.
- `tool_result_partial`: result manifest exists but required declared artifacts are missing or unsafe.
- `metric_result_missing`: real result exists, but metric result manifest is absent.
- `metric_result_failed`: OCEAN metric result manifest exists but `check-metric-results` fails, or one or more required metrics failed.
- `recordable_success`: `check-real-run` and `check-metric-results` pass and C-8 has not recorded the run yet.
- `already_recorded`: ledger already contains this `run_id` or candidate result.
- `resolved_retry_prepared`: the failed run has a recovery decision pointing to a prepared retry package.
- `resolved_abandoned`: the supervisor has explicitly abandoned this candidate after failure.
- `resolved_stopped`: the supervisor has explicitly stopped the workflow after failure.

The classification is based on files and deterministic checker outputs, not chat history.

## Allowed Actions

C-10 exposes only explicit supervisor-directed actions:

```text
retry_same_candidate
abandon_candidate
stop_workflow
revise_contracts
record_result
wait_for_execution
```

Allowed actions by state:

| State | Allowed actions |
| --- | --- |
| `pending_execution` | `wait_for_execution`, `stop_workflow` |
| `contract_invalid` | `revise_contracts`, `stop_workflow` |
| `tool_result_missing` | `retry_same_candidate`, `stop_workflow` |
| `tool_result_failed` | `retry_same_candidate`, `abandon_candidate`, `stop_workflow` |
| `tool_result_partial` | `retry_same_candidate`, `stop_workflow` |
| `metric_result_missing` | `retry_same_candidate`, `stop_workflow` |
| `metric_result_failed` | `retry_same_candidate`, `abandon_candidate`, `revise_contracts`, `stop_workflow` |
| `recordable_success` | `record_result` |
| `already_recorded` | no action required |
| `resolved_retry_prepared` | no action required until retry package is executed |
| `resolved_abandoned` | no action required; C-9 may prepare a different candidate |
| `resolved_stopped` | no action required; workflow remains stopped |

`retry_same_candidate` is not allowed after the retry budget is exhausted.

## Retry Budget

C-10 should start with a conservative fixed policy:

```text
max_attempts_per_candidate = 2
```

The original prepared run counts as attempt 1. One retry package is attempt 2.

The first implementation should not add a new YAML setting. A later plan may expose the retry budget in `optimizer.yaml` or `spectre.yaml` after the behavior is proven.

When the budget is exhausted, C-10 must remove `retry_same_candidate` from allowed actions and require one of:

- `abandon_candidate`
- `revise_contracts`
- `stop_workflow`

## Recovery Assessment Report

C-10 writes:

```text
reports/real_run_recovery_report.json
```

Recommended schema:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "run_id": "real_002",
  "candidate_id": "real_002",
  "classification": "metric_result_failed",
  "allowed_actions": ["retry_same_candidate", "abandon_candidate", "revise_contracts", "stop_workflow"],
  "recommended_action": "retry_same_candidate",
  "attempt_number": 1,
  "max_attempts_per_candidate": 2,
  "retry_budget_remaining": 1,
  "real_run_check_report": "reports/real_run_check_report.json",
  "metric_result_check_report": "reports/metric_result_check_report.json",
  "ledger_path": "ledger/experiment_ledger.jsonl",
  "recovery_decision": null,
  "issues": []
}
```

Report `status` means the recovery assessment itself is valid:

- `pass`: classification succeeded.
- `fail`: C-10 could not safely classify the run because required project state is invalid or unsafe.

The report does not itself authorize a retry. Retry still requires a recovery decision file written from an explicit supervisor action.

## Recovery Decision Artifact

C-10 writes a per-run decision:

```text
runs/real/<run_id>/recovery_decision.json
```

Recommended schema:

```json
{
  "schema_version": "1.0",
  "run_id": "real_002",
  "candidate_id": "real_002",
  "decision": "retry_same_candidate",
  "decided_at_utc": "2026-06-02T12:00:00Z",
  "decided_by": "supervisor_agent",
  "reason": "OCEAN metric result failed with missing scalar output",
  "source_recovery_report": "reports/real_run_recovery_report.json",
  "source_recovery_report_sha256": "...",
  "retry_run_id": "real_003",
  "issues": []
}
```

Valid decisions:

```text
retry_same_candidate
abandon_candidate
stop_workflow
revise_contracts
```

`record_result` is not a recovery decision. If a run is `recordable_success`, the supervisor should call C-8 `record-real-result`.

## Retry Package Contract

For `retry_same_candidate`, C-10 writes a new package:

```text
runs/real/<retry_run_id>/input.scs
runs/real/<retry_run_id>/candidate.json
runs/real/<retry_run_id>/metric_extraction_request.json
runs/real/<retry_run_id>/real_run_manifest.json
```

The retry package uses a new `run_id`, but preserves the same `candidate_id` and parameters as the failed package.

Example:

```text
failed package: runs/real/real_002, candidate_id real_002
retry package:  runs/real/real_003, candidate_id real_002
```

This is intentional:

- `run_id` identifies an execution package and its artifacts.
- `candidate_id` identifies the optimization candidate.
- a retry is a new execution attempt for the same candidate.

`candidate.json` should add retry provenance:

```json
{
  "schema_version": "1.0",
  "candidate_id": "real_002",
  "source": "retry_same_candidate",
  "candidate_index": 2,
  "parameters": {},
  "retry_of_run_id": "real_002",
  "retry_attempt_number": 2,
  "recovery_decision": "runs/real/real_002/recovery_decision.json"
}
```

`real_run_manifest.json` should add:

```json
{
  "run_id": "real_003",
  "candidate_id": "real_002",
  "status": "prepared",
  "package_kind": "retry",
  "retry_of_run_id": "real_002",
  "retry_attempt_number": 2,
  "recovery_decision": "runs/real/real_002/recovery_decision.json",
  "recovery_decision_sha256": "..."
}
```

The retry package must preserve the exact rendered `input.scs` content and exact metric extraction request formulas for the candidate unless a later `revise_contracts` path explicitly changes project contracts before a new approval cycle.

This preservation is literal file-contract preservation:

- retry preparation copies the failed run's already-rendered `input.scs` content into the retry package instead of re-rendering from a possibly changed template file
- retry preparation verifies the retry `metric_extraction_request.json` formula contract against the failed run's metric extraction request before accepting the retry package
- `runs`, `runs/real`, and `runs/real/<retry_run_id>` must not be symlinks; parent-directory symlink traversal is a contract violation even when the retry leaf path itself is not a symlink

## Interaction With C-9

C-10 should add an unresolved real-run guard before C-9 prepares another new candidate.

`prepare-next-real-run` must fail closed when any existing `runs/real/real_###/` directory is unresolved:

- prepared package without result and without recovery decision
- failed result without recovery decision
- metric failure without recovery decision
- partial or unsafe result artifacts
- retry package prepared but not executed
- `stop_workflow` decision exists
- `revise_contracts` decision exists and immutable config has not gone through a new approval flow

Resolved cases:

- `already_recorded`: C-9 may continue.
- `resolved_abandoned`: C-9 may continue and skip the prepared candidate parameters.
- `resolved_retry_prepared`: C-9 must wait for the retry package to be executed and recorded or resolved.

This preserves the single-candidate loop. Batch/multiple outstanding packages remain out of scope.

## Interaction With C-8

C-8 remains the only path that writes real successful results into:

```text
ledger/experiment_ledger.jsonl
state/optimizer_state.json
state/best_candidate.json
```

C-10 must not write optimizer ledger/state. Failed real runs are not ledger rows in C-10.

If a retry succeeds, C-8 records:

- `run_id`: the retry package run id, such as `real_003`
- `candidate_id`: the original candidate id, such as `real_002`
- parameters: copied from the original candidate

This preserves execution-attempt identity and candidate identity.

## API And CLI

Add library functions:

```python
def assess_real_run_recovery(
    project_dir: Path,
    *,
    run_id: str,
    persist_report: bool = True,
) -> RealRunRecoveryReport

def prepare_real_run_retry(
    project_dir: Path,
    *,
    failed_run_id: str,
    retry_run_id: str | None = None,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRetryPackage

def resolve_real_run_failure(
    project_dir: Path,
    *,
    run_id: str,
    decision: str,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRecoveryReport
```

Add CLI commands:

```bash
hermes-workflow assess-real-run-recovery PROJECT_DIR --run-id real_002
hermes-workflow prepare-real-run-retry PROJECT_DIR --failed-run-id real_002
hermes-workflow resolve-real-run-failure PROJECT_DIR --run-id real_002 --decision abandon_candidate --reason "metric formula needs redesign"
```

CLI failure output should print issues and report paths without a traceback.

## Error Handling

C-10 must fail closed and avoid writes when:

- project validation fails
- run id is invalid
- selected run directory is missing
- selected run directory is a symlink
- required prepared package files are missing or malformed
- candidate identity cannot be determined
- recovery report cannot classify the run safely
- requested decision is not allowed for the current classification
- retry budget is exhausted
- retry target run id already exists
- retry target run directory is a symlink
- retry package write would overwrite existing artifacts
- recovery decision already exists and no explicit future repair workflow is defined
- `runs` or `runs/real` is a symlink
- immutable config drift is detected

When preparing a retry package, C-10 should prepare all payloads before creating final files. If a write fails, it should not leave a partial package that C-7 could execute.

## Testing Strategy

Use synthetic project fixtures and fake result artifacts only.

Required tests:

- pending prepared package is classified as `pending_execution`
- successful checked run is classified as `recordable_success` before C-8
- ledger-recorded run is classified as `already_recorded`
- `result_manifest.status == "failed"` is classified as `tool_result_failed`
- missing result manifest with no execution-attempt evidence is classified as `pending_execution`
- missing result manifest with execution-attempt evidence is classified as `tool_result_missing`
- missing metric manifest is classified as `metric_result_missing`
- failed metric manifest is classified as `metric_result_failed`
- invalid prepared package is classified as `contract_invalid`
- retry decision writes `recovery_decision.json`
- retry package uses a new `run_id` and preserves original `candidate_id`
- retry package refuses existing target directories and symlinks
- retry budget prevents a third attempt
- abandon decision lets C-9 continue to a different candidate
- unresolved failed or pending package makes C-9 fail closed
- C-10 never writes optimizer ledger/state
- CLI pass and fail paths avoid tracebacks

Verification commands:

```bash
python3 -m pytest tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_real_result_record.py tests/test_cli.py -q
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

## Non-Goals

C-10 does not implement:

- real Cadence execution
- adapter retry invocation
- automatic retry
- overwrite-based retry
- failure-penalty ledger rows
- batch scheduling
- model-based optimizer updates
- formula repair
- metric formula discovery
- PSF parsing
- Maestro-managed optimization

## Acceptance Criteria

C-10 is acceptable when:

- every real-run package has a deterministic status: pending, recordable, recorded, failed, or explicitly resolved
- failed and partial real-run artifacts are preserved
- retries create a new package instead of overwriting old evidence
- retry packages remain compatible with C-7, C-5, C-6, and C-8
- C-9 cannot silently skip unresolved failed or pending real runs
- failed real runs do not enter the optimizer ledger
- supervisor decisions are written as files and can be audited
- all automated tests use fake artifacts and do not require real Cadence tools

## Next Scope After C-10

After C-10, the recommended next scope is C-11 local smoke:

```text
C-9 prepare-next-real-run
-> C-7 execution adapter on a known local test cell
-> C-5/C-6 checks
-> C-8 record-real-result
-> C-10 failure/retry path for one controlled failure case
```

That smoke should remain local-only evidence and should not require committing proprietary netlists or PSF data.
