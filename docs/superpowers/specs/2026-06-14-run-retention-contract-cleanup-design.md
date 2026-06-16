# B-06 Run Retention Contract Cleanup Design

Date: 2026-06-14
Status: planned
Package boundary: develop and verify in `ic-auto-opt-workflow` first. Do not patch or sync `ic-auto-opt-workflow-v0.1` until dev tests and real-flow validation pass.

## Problem

`opt_requirement.md` exposes two user settings under `Spectre Settings`:

```yaml
keep_failed_runs: true
keep_successful_runs: true
```

They are required by `src/hermes_workflow/schemas.py`, validated by `src/hermes_workflow/requirement_intake.py`, and present in the project template. Current optimizer execution does not enforce them. Real run directories under `runs/real/<run_id>` are retained regardless of success or failure, so the requirement contract currently accepts user intent without carrying it to runtime behavior.

This is the same class of bug as the earlier workload/resource contract issues: a field is parsed and appears user-configurable, but the workflow does not act on it.

## Current Flow Understanding

The optimizer flow prepares a candidate run under `runs/real/<run_id>`, runs either the local or remote Spectre/OCEAN adapter, checks the result, computes the objective, and records the result into ledger/state/report artifacts.

Relevant paths:

- `src/hermes_workflow/schemas.py`
  - `SpectreSettings.keep_failed_runs`
  - `SpectreSettings.keep_successful_runs`
- `src/hermes_workflow/requirement_intake.py`
  - requires both fields in `Spectre Settings`.
- `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
  - exposes both fields to users.
- `src/hermes_workflow/real_run.py`
  - creates `runs/real/<run_id>` and child testbench/corner run directories.
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
  - writes local `result_manifest.json` and `metrics/metric_result_manifest.json`.
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
  - runs remote Spectre/OCEAN, downloads artifacts into the local cache, and supports single and multi-testbench/multi-corner adapters.
- `src/hermes_workflow/native_turbo.py`
  - prepares real candidates, invokes the adapter, checks metrics, computes objective, and records results for native TuRBO.
- `src/hermes_workflow/openbox_backend.py`
  - prepares OpenBox batch candidates and delegates real execution through `execute_and_check_real_candidate`.
- `src/hermes_workflow/real_result_record.py`
  - writes ledger, optimizer state, and best-candidate state after a valid real observation.
- `src/hermes_workflow/remote_optimizer_flow.py`
  - injects the remote candidate adapter; remote flow should not reimplement optimizer logic.

There is no cleanup or retention policy application after candidate finalization today.

## Contract

The two settings control per-candidate real run directory retention:

- `keep_successful_runs: true`
  - Keep `runs/real/<run_id>` when the candidate produced a usable real observation.
- `keep_successful_runs: false`
  - Delete `runs/real/<run_id>` after the candidate has been checked and recorded.
- `keep_failed_runs: true`
  - Keep `runs/real/<run_id>` when the candidate failed during real execution, metric extraction, aggregation, or result checking.
- `keep_failed_runs: false`
  - Delete `runs/real/<run_id>` after failure has been classified and reported.

`successful` means the Spectre/OCEAN workflow produced usable metric results for the optimizer. It does not mean circuit constraints passed. A constraint-violating candidate with valid metrics is a successful observation and is controlled by `keep_successful_runs`.

`failed` means the workflow did not produce a usable real observation, including Spectre command failure, OCEAN command failure, missing metric output, aggregate `real_check_failed`, aggregate `metric_check_failed`, adapter precondition failure, or result-recording failure.

Retention cleanup must run only after candidate finalization. It must not delete the run directory before `check_real_run`, objective evaluation, metric aggregation, or `record_real_result` has consumed the artifacts.

## Required Behavior

Local:

1. Read retention policy from the existing validated config/requirement bundle.
2. After each candidate reaches final success/failure classification, apply the policy to `project_dir/runs/real/<run_id>`.
3. Keep durable state outside the run directory:
   - `ledger/experiment_ledger.jsonl`
   - `state/optimizer_state.json`
   - `state/best_candidate.json`
   - optimizer reports under `reports/`
   - a new per-run retention decision report under `state/run_retention/<run_id>.json`
4. If deletion is requested but fails, surface a structured failure in the optimizer result instead of silently pretending the policy was honored.

Remote:

1. Remote flow remains adapter injection only.
2. Single-testbench remote runs use `run_remote_spectre_ocean_adapter`.
3. Multi-testbench or multi-corner remote runs use `run_remote_multi_testbench_adapter`.
4. The remote adapter wrapper applies the same retention policy to the remote project run directory after artifacts have been downloaded and the remote candidate adapter has returned.
5. Local cache retention is still applied after local candidate finalization, because local cache artifacts are needed for result checking and recording.
6. Remote cleanup must be restricted to the exact remote run directory under `<remote_project_dir>/runs/<run_id>` or `<remote_project_dir>/runs/real/<run_id>`, matching the current remote adapter layout. It must never construct shell globs or delete outside the remote project root.

Reports:

Each applied retention decision must write `state/run_retention/<run_id>.json` with:

- `schema_version`
- `run_id`
- `candidate_id` if known
- `run_status`: `successful` or `failed`
- `policy_source`: `Spectre Settings`
- `keep_failed_runs`
- `keep_successful_runs`
- `local_action`: `kept`, `deleted`, `missing`, or `failed`
- `remote_action`: `kept`, `deleted`, `missing`, `failed`, or `not_applicable`
- `local_run_dir`
- `remote_run_dir` when applicable
- `issues`
- timestamp

Doctor/readiness output must summarize the retention policy so users can see the active setting before a run starts.

## Acceptance Criteria

- `keep_failed_runs` and `keep_successful_runs` are no longer parsed-only fields.
- Local OpenBox and native TuRBO real execution apply retention after candidate finalization.
- Remote OpenBox and native TuRBO real execution apply retention to both the local cache and the remote run directory.
- Multi-testbench and multi-corner runs delete or keep the whole candidate run root consistently, not a partial child directory set.
- Constraint-failed but metric-valid observations are treated as successful runs for retention.
- State, ledger, best-candidate, optimizer reports, and retention decision reports are not removed by run cleanup.
- Cleanup failure is visible in structured diagnostics or optimizer result issues.
- No new CLI flags are added for retention.
- No release package edits happen until dev package validation is complete.

## Non-Goals

- Do not change candidate/testbench/corner execution order.
- Do not add inner testbench or corner parallelism.
- Do not change OpenBox or TuRBO algorithm behavior.
- Do not change `parallel_jobs`, `threads_per_run`, `timeout_s`, or license-check semantics.
- Do not delete user source files, template netlists, config files, reports, ledger, or state.
- Do not implement a background sweeper for old historical runs.
- Do not sync `ic-auto-opt-workflow-v0.1` in this task.
