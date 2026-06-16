# B-09 Optimizer Progress State Contract Design

Date: 2026-06-14
Status: planned
Package boundary: develop and verify in `ic-auto-opt-workflow` first. Do not patch or sync `ic-auto-opt-workflow-v0.1` until dev tests and real local/remote validation pass.

## Problem

The optimizer currently exposes multiple progress artifacts with different meanings:

- `reports/optimizer_run_report.json`
- `reports/optimizer_evaluations.jsonl`
- `ledger/experiment_ledger.jsonl`
- `state/optimizer_state.json`
- `state/best_candidate.json`

After the real 10-point multi-corner validation, local and remote optimizer reports correctly showed 10 completed evaluations, but `state/optimizer_state.json` still showed:

```json
{
  "status": "running",
  "current_evaluations": 7,
  "max_evaluations": 10
}
```

The observed trace distribution was:

- 10 optimizer attempts
- 7 usable metric observations written to the ledger
- 3 failed evaluations visible in `optimizer_evaluations.jsonl`
- no feasible best candidate, so `state/best_candidate.json` was absent

The absence of `best_candidate.json` is valid when no feasible candidate exists. The incorrect part is that `optimizer_state.json.current_evaluations` currently reflects recorded ledger rows, while the optimizer reports reflect attempted optimizer evaluations.

## Source Findings

`src/hermes_workflow/schemas.py` defines `OptimizerState` with only one count field:

- `current_evaluations`
- `max_evaluations`
- `best_candidate_id`
- `status`

There is no field to distinguish attempted evaluations from recorded observations or failed evaluations.

`src/hermes_workflow/real_result_record.py` writes `ledger/experiment_ledger.jsonl`, `state/best_candidate.json`, and `state/optimizer_state.json` only after `check_real_run`, metric checking, constraint evaluation, and objective evaluation produce a usable record. This is correct for the ledger, but incorrect as the only source of optimizer progress.

`src/hermes_workflow/native_turbo.py` and `src/hermes_workflow/openbox_backend.py` write complete optimizer traces to:

- `reports/optimizer_run_report.json`
- `reports/optimizer_evaluations.jsonl`

Those reports include workflow failures and metric failures. They currently do not synchronize `state/optimizer_state.json` from the full trace set.

`src/hermes_workflow/optimizer_acceptance.py` and `src/hermes_workflow/optimizer_completion.py` use the optimizer report and evaluation traces as the source of truth. They do not rely on `state/optimizer_state.json`, which is why completion/acceptance can say 10 while state says 7.

Doctor/readiness currently checks for artifact presence, but does not detect that state count and report count disagree.

## Required Contract

The optimizer progress contract must make the meanings explicit:

- attempted evaluations: optimizer candidates attempted by OpenBox or TuRBO; source is `optimizer_evaluations.jsonl` and `optimizer_run_report.evaluation_count`.
- recorded observations: usable observations with metric/objective data written to `ledger/experiment_ledger.jsonl`.
- failed evaluations: attempted evaluations that did not become recorded observations.
- feasible best candidate: best feasible observation if one exists.

`state/optimizer_state.json` must become a progress summary, not a ledger-row proxy.

Required state semantics:

- `current_evaluations` means attempted optimizer evaluations.
- `max_evaluations` is the configured optimizer budget from requirement/config.
- `status` is `completed` when the optimizer report is completed and `current_evaluations >= max_evaluations`, or when the optimizer completed early with an explicit reason.
- `recorded_observation_count` is the number of ledger rows.
- `failed_evaluation_count` is attempted minus recorded observations, or a count derived from failed trace statuses when available.
- `status_counts` summarizes trace statuses from `optimizer_evaluations.jsonl`.
- `progress_source` identifies the source artifact, normally `reports/optimizer_evaluations.jsonl`.
- `best_candidate_id` remains nullable. It must be `null` when there is no feasible best candidate.

The ledger must not be padded with fake failed rows just to make counts match. `ledger/experiment_ledger.jsonl` remains the record of usable metric/objective observations.

## Local And Remote Parity

Remote mode must not implement a separate optimizer progress model. Remote flow must continue to inject the local or remote candidate adapter into the same OpenBox/TuRBO optimizer path. The shared progress-state synchronization must run in the optimizer/report path so local and remote inherit the same semantics.

If remote closeout copies reports/state back and forth, the updated `state/optimizer_state.json` must be present in both:

- local remote cache under `~/.ic-opt/remote_runs/...`
- remote project directory

## Non-Goals

- Do not change OpenBox or TuRBO candidate generation.
- Do not change objective, constraints, metrics, or multi-corner aggregation.
- Do not treat a missing `best_candidate.json` as a failure when no feasible candidate exists.
- Do not create fake ledger rows for workflow failures.
- Do not add CLI flags.
- Do not edit or sync the release package before dev validation.

## Acceptance Criteria

1. A run with 10 attempted traces, 7 recorded ledger observations, and 3 failed traces writes `state/optimizer_state.json` with:
   - `current_evaluations: 10`
   - `recorded_observation_count: 7`
   - `failed_evaluation_count: 3`
   - `status_counts` matching the trace statuses
   - `status: "completed"` when the optimizer report completed
2. `ledger/experiment_ledger.jsonl` still contains only the 7 usable observations.
3. `state/best_candidate.json` is optional and absent/null when no feasible candidate exists.
4. OpenBox and native TuRBO both use the same progress-state synchronization helper.
5. Doctor/readiness reports a structured diagnostic when:
   - `optimizer_run_report.evaluation_count` differs from `optimizer_state.current_evaluations`
   - `optimizer_evaluations.jsonl` row count differs from either value
   - `recorded_observation_count` differs from ledger row count
6. Local and remote 10-point, three-corner validation both show matching attempted/recorded/failed counts in state, report, evaluations, and ledger.

## Validation Scope

Unit and integration tests must reproduce the observed bug without requiring Spectre:

- fake 10-trace OpenBox/TuRBO reports
- 7 ledger rows
- 3 failed traces
- no feasible best candidate

After tests pass, run real validation on the existing sample project:

- local 10-point three-corner run
- remote 10-point three-corner run

Expected real validation evidence:

- `reports/optimizer_run_report.json.status == "completed"`
- `reports/optimizer_run_report.json.evaluation_count == 10`
- `reports/optimizer_evaluations.jsonl` has 10 rows
- `state/optimizer_state.json.current_evaluations == 10`
- `state/optimizer_state.json.recorded_observation_count == ledger row count`
- `state/optimizer_state.json.failed_evaluation_count == 10 - ledger row count`
- local and remote artifacts agree
