# Requirement Contract Backlog

Date: 2026-06-13

This document is the active repair backlog for the `opt_requirement.md` contract.
It records confirmed problems from the C-76/C-77/C-78 follow-up audit and the
real remote multi-corner run at:

`/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/e952aa46d52244ab`

The repair rule is now:

- Develop and verify in `ic-auto-opt-workflow` first.
- After real validation passes, sync the release package `ic-auto-opt-workflow-v0.1`.
- `opt_requirement.md` / generated config is the source of truth for user
  settings. CLI flags must not silently override workload or resource settings.
- Every requirement setting must either reach runtime behavior or be rejected by
  doctor/validation. No parsed-but-unused user setting is acceptable.

## Certainty Boundary

The issues below are confirmed from source audit and real artifacts. This is not
a claim that unknown bugs are impossible. Any new contract issue found during
repair must be appended here before fixing so the backlog remains the single
source of repair state.

## Confirmed Blockers

### B-01 CLI Overrides Break Requirement Source Of Truth

Status: spec/plan ready; implementation not started

Problem:
`ic-opt` and `hermes-workflow` still expose workload/resource override flags,
including `--max-evals`, `--batch-size`, and `--parallel-jobs`. Internal
`hermes-workflow optimize` also has `--max-evals` defaulting to `100`, which can
override `optimizer.max_evaluations` even when the user did not explicitly ask.

Impact:
The same requirement can run with different budgets/concurrency depending on
entrypoint. This caused requirement `parallel_jobs: 10` to coexist with runtime
`parallel_jobs: 8` in the real remote run.

Required fix:
Remove or fail-closed these CLI overrides for product and internal optimizer
entrypoints. Runtime budget, batch size, candidate concurrency, optimizer CPU
threads, Spectre threads, timeout, and algorithm mode must come from
`opt_requirement.md` / config.

Files to inspect/fix:

- `src/hermes_workflow/product_cli.py`
- `src/hermes_workflow/cli.py`
- `src/hermes_workflow/optimizer_flow.py`
- `src/hermes_workflow/remote_optimizer_flow.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`

Acceptance:

- Running without CLI workload/resource flags uses requirement values.
- Passing removed override flags fails with a clear diagnostic.
- Tests cover product CLI and internal CLI.
- Doctor no longer reports CLI as a valid source for these settings.

Dev progress 2026-06-13:

- Removed workload/resource override flags from product `ic-opt` and real optimizer `hermes-workflow` entrypoints.
- Removed `package-optimizer-task --max-evals/--additional-evals`.
- Removed `run-openbox-fake --max-evals/--batch-size`; fake runner now receives `None` so it resolves from config.
- `build_optimizer_execution_task_package()` now records `max_evals` from `config/optimizer.yaml` and does not accept external budget arguments.
- Updated remote doctor and bundled `ic-opt` skill guidance to point users to `opt_requirement.md` / `Spectre Settings.parallel_jobs`, not CLI flags.
- Targeted tests passed:
  `tests/test_cli.py tests/test_optimizer_task_package.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_product_cli.py tests/test_optimizer_flow.py`.
- Full pytest, ruff, and diff check passed after this fix set.

### B-02 `parallel_jobs` Has Wrong Contract Layer

Status: dev fixed (2026-06-14, second pass); full pytest passed; pending real-flow and release sync verification

Problem:
`parallel_jobs` is candidate-level optimizer concurrency, but it is stored under
`spectre` settings and written into prepared/request manifests. Single Spectre
child execution does not use this value.

Impact:
Scheduler, prepared manifest, metric request, and doctor can disagree about the
same field. The real run showed config/prepared `parallel_jobs: 10` but runtime
scheduler `parallel_jobs: 8`.

Required fix:
Move or reinterpret `parallel_jobs` as an optimizer/resource runtime setting,
not a single-run simulator metadata field. It should not be compared as part of
the Spectre child prepared/request precondition.

Spec/plan:

- `docs/superpowers/specs/2026-06-13-scheduler-parallelism-contract-cleanup-design.md`
- `docs/superpowers/plans/2026-06-13-scheduler-parallelism-contract-cleanup.md`

Files to inspect/fix:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/requirement_intake.py`
- `src/hermes_workflow/metric_requests.py`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/doctor_readiness.py`

Acceptance:

- `parallel_jobs` controls only candidate-level scheduler concurrency.
- Child `metric_extraction_request.json` and child precondition checks do not
  treat `parallel_jobs` as a Spectre command setting.
- Reports show the resolved candidate concurrency from requirement.

Dev progress 2026-06-14 (second pass for B-02):

- `prepare_real_run()` no longer writes `spectre.parallel_jobs` into
  `real_run_manifest.json`.
- `build_metric_extraction_request()` no longer writes `spectre.parallel_jobs`
  into `metric_extraction_request.json`.
- `_validate_spectre_request()` and `_validate_spectre_settings_match()` in the
  Spectre/OCEAN execution adapter no longer require or compare
  `spectre.parallel_jobs`. Local and remote adapters share the same precondition
  path through `load_adapter_context()`.
- `parallel_jobs` is preserved as a user-configurable input
  (`SpectreSettings.parallel_jobs` schema; `Spectre Settings.parallel_jobs` in
  `opt_requirement.md`). OpenBox and native TuRBO real evaluators continue to
  read it from `bundle.spectre.spectre.parallel_jobs` and use
  `max_workers = min(parallel_jobs, batch_size)` for the candidate batch.
- Multi-testbench / multi-corner child execution remains serial inside each
  candidate.
- Optimizer execution task package no longer lists `parallel_jobs` under
  `spectre_settings` and now exposes `manifest_payload["scheduler"]` with
  `candidate_parallelism`, `batch_size`, and `inside_candidate_execution:
  serial`. The rendered task markdown adds a `## Scheduler Settings` section
  and drops `parallel_jobs` from `## Spectre/OCEAN Settings Audit`.
- Remote doctor warning wording for high candidate concurrency now describes
  candidate-level scheduler parallelism instead of implying a Spectre runtime
  field. Structured issue code (`REMOTE_PARALLELISM_HIGH`) is unchanged.
- New tests pin behavior:
  `test_prepare_real_run_omits_parallel_jobs_from_spectre_runtime_contract`,
  `test_metric_request_omits_parallel_jobs_from_spectre_runtime_contract`,
  `test_adapter_accepts_missing_parallel_jobs_in_spectre_contract`,
  `test_adapter_still_rejects_threads_per_run_mismatch`,
  `test_remote_adapter_accepts_missing_parallel_jobs_in_spectre_contract`,
  `test_openbox_real_uses_requirement_parallel_jobs_for_candidate_workers`,
  `test_native_turbo_uses_requirement_parallel_jobs_for_candidate_workers`,
  `test_optimizer_task_package_does_not_label_parallel_jobs_as_spectre_setting`.
- Real remote validation has not been re-run for this second pass; pending.
- Release package `ic-auto-opt-workflow-v0.1` is not yet synced for these
  changes.

### B-03 Remote `timeout_s` Is Not Passed To SSH Runner

Status: planned

Plan:

- Spec: `docs/superpowers/specs/2026-06-14-optimizer-progress-state-contract-design.md`
- Plan: `docs/superpowers/plans/2026-06-14-optimizer-progress-state-contract.md`

Problem:
The local Spectre/OCEAN adapter passes `timeout_s` into subprocess execution.
The remote adapter calls `runner.run(command)` without passing `timeout_s`, even
though `RemoteSshRunner.run(..., timeout_s=...)` supports it.

Impact:
`timeout_s` has different behavior in local and remote mode.

Required fix:
Remote Spectre and OCEAN calls must pass the request timeout into the SSH runner
or explicitly use separate documented timeouts if that is the intended behavior.

Files to inspect/fix:

- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- `src/hermes_workflow/remote_ssh.py`
- `tests/test_remote_*`

Acceptance:

- Remote adapter tests assert runner receives `timeout_s`.
- Real remote command behavior is documented in the report.

Dev progress 2026-06-13:

- `run_remote_spectre_ocean_adapter()` now passes `context.request.spectre.timeout_s` to remote Spectre and OCEAN SSH runner calls.
- Added regression coverage in `tests/test_remote_spectre_ocean.py`.
- Targeted test passed: `tests/test_remote_spectre_ocean.py`.
- Full pytest, ruff, and diff check passed after this fix set.

### B-04 Multi-Testbench/Multi-Corner Parent Manifest Hardcodes Simulator Metadata

Status: dev fixed; full-suite passed; pending real-flow and release sync verification

Problem:
`multi_testbench_aggregation.py` writes parent `result_manifest.json` with
hardcoded simulator metadata:

- `engine: spectre_x`
- `preset: ax`
- `output_format: psfxl`
- `threads_per_run: 10`
- `timeout_s: 3600`

Impact:
The real 80-point remote run completed child simulations, but every parent run
failed handoff because prepared/request had `timeout_s: 7200` while parent
aggregate result had `timeout_s: 3600`.

Required fix:
Parent aggregate manifests must inherit simulator metadata from the real
prepared/request/child contract. No hardcoded simulator settings are allowed.

Files to inspect/fix:

- `src/hermes_workflow/multi_testbench_aggregation.py`
- `src/hermes_workflow/result_handoff.py`

Dev progress 2026-06-13:

- Parent aggregate `result_manifest.json` now builds `simulator` metadata from prepared/request `spectre` settings instead of hardcoding preset/thread/timeout.
- Added regression coverage for non-default `preset`, `output_format`, `threads_per_run`, and `timeout_s`.
- Targeted test passed: `tests/test_multi_testbench_aggregation.py`.
- Full pytest, ruff, and diff check passed after this fix set.
- `tests/test_multi_*`

Acceptance:

- Non-default preset, output format, threads, and timeout are preserved in parent
  aggregate result manifests.
- Real handoff accepts a multi-corner parent result when child runs succeeded.

### B-05 `require_license_check` Is Parsed But Not Enforced

Status: open

Problem:
`require_license_check` is required in `Spectre Settings`, but execution code
does not use it.

Impact:
The user can ask for a license check and the workflow will accept the setting
without enforcing it.

Required fix:
Either implement the license preflight behavior or reject this setting as
unsupported until implementation exists.

Files to inspect/fix:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/requirement_intake.py`
- `src/hermes_workflow/product_doctor.py`
- `src/hermes_workflow/remote_doctor.py`
- `src/hermes_workflow/toolchain_env.py`

Acceptance:

- If true, doctor/preflight verifies the intended license/tool readiness or
  fails with a clear diagnostic.
- If unsupported, validation fails instead of silently accepting it.

### B-06 `keep_failed_runs` And `keep_successful_runs` Are Parsed But Not Enforced

Status: dev fixed (2026-06-14); pending real-flow and release sync verification

Plan/spec:

- `docs/superpowers/specs/2026-06-14-run-retention-contract-cleanup-design.md`
- `docs/superpowers/plans/2026-06-14-run-retention-contract-cleanup.md`

Problem:
The settings are required and validated but no cleanup/retention path consumes
them.

Impact:
The user cannot rely on the retention policy they wrote in the requirement.

Required fix:
Implement retention cleanup after candidate finalization, or reject unsupported
values. The cleanup policy must work for local and remote cache/project copies.

Files to inspect/fix:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/remote_optimizer_flow.py`

Acceptance:

- Tests cover keep/remove behavior for successful and failed run directories.
- Remote sync does not resurrect directories that should have been removed.

Dev progress 2026-06-14:

- Added shared retention helper `src/hermes_workflow/run_retention.py` with
  `RunRetentionPolicy`, `RunRetentionDecision`, `load_run_retention_policy`,
  `apply_local_run_retention`, and `apply_remote_run_retention`. The helper
  reads `Spectre Settings.keep_failed_runs` / `keep_successful_runs` from the
  validated requirement bundle, validates the run id with the existing
  `RUN_ID_RE`, deletes only `runs/real/<run_id>`, and always writes
  `state/run_retention/<run_id>.json` with the decision (schema_version 1.0).
- Local TuRBO and OpenBox enforcement: `evaluate_real_candidate` and the
  batch evaluators in `native_turbo.py` and `openbox_backend.py` now call
  retention after finalization for both successful (`recorded`) and failed
  paths (`real_check_failed`, `metric_check_failed`, `metric_failed`,
  `record_failed`). Constraint-failed observations with valid metrics are
  classified as successful for retention.
- Remote wrapper: `remote_optimizer_flow.optimize_remote_project` and
  `continue_remote_project` wrap the existing `selected_adapter` with
  `_wrap_with_remote_retention`. The wrapper runs ONCE per `run_id` after the
  outer adapter returns (or raises), so multi-testbench / multi-corner runs
  delete the parent run root, not per-child. The remote command is exactly
  `rm -rf -- <quoted absolute path>` under `<remote_project_dir>/runs/real/`,
  with defense-in-depth checks against globs and out-of-project paths.
- Doctor visibility: `doctor_readiness.build_run_retention_summary` is added
  and surfaces under `resource_summary.run_retention` in both local
  (`product_doctor`) and remote (`remote_doctor`) JSON payloads.
- Decision report shape (`state/run_retention/<run_id>.json`) carries
  schema_version, run_id, candidate_id, run_status, policy_source,
  keep_failed_runs, keep_successful_runs, local_action, remote_action,
  local_run_dir, remote_run_dir, issues, decided_at_utc.
- Targeted pytest sets pass (`tests/test_run_retention.py`,
  `tests/test_native_turbo.py`, `tests/test_openbox_backend.py`,
  `tests/test_remote_optimizer_flow.py`, `tests/test_remote_spectre_ocean.py`,
  `tests/test_doctor_readiness.py`, `tests/test_product_doctor.py`,
  `tests/test_remote_doctor.py`). Real-flow validation against
  `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3` and the v0.1 release sync
  remain pending, per the plan's Tasks 6 and 7.

### B-07 OpenBox Ignores `optimizer.initialization`

Status: open

Problem:
Schema allows `initialization: sobol | latin_hypercube | random`, but OpenBox
Advisor is created with `init_strategy="sobol"` unconditionally.

Impact:
Users can request random or Latin hypercube initialization and still get Sobol.

Required fix:
Map requirement initialization into OpenBox `init_strategy`, or restrict schema
and docs to the only supported value.

Files to inspect/fix:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/mock_optimizer.py`
- `tests/test_openbox_*`

Acceptance:

- Tests prove each accepted initialization value reaches the backend, or invalid
  values are rejected at validation time.

### B-08 `output_format: psfascii` Is Accepted But Not Compatible With Current OCEAN Flow

Status: open

Problem:
Schema allows `psfascii` and `psfxl`, but metric request generation currently
accepts only OCEAN-ready `psfxl`.

Impact:
Users can write a schema-valid requirement that fails later in preparation.

Required fix:
Reject unsupported output formats early in doctor/validation or make the metric
flow support them.

Files to inspect/fix:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/metric_requests.py`
- `src/hermes_workflow/requirement_semantics.py`
- doctor tests

Acceptance:

- Unsupported output format fails before real optimization.

### B-09 State/Progress Contract Is Inconsistent

Status: dev fixed (2026-06-14); pending real local/remote validation and release sync verification

Dev progress 2026-06-14:

- Added shared `src/hermes_workflow/optimizer_progress_state.py` with
  `build_optimizer_progress_state` (pure builder) and
  `sync_optimizer_progress_state(project_dir)` (file IO).
- Wired the sync helper into both `openbox_backend.write_openbox_reports`
  and `native_turbo.write_native_turbo_reports`, so the same progress
  contract applies to OpenBox and native TuRBO and to local and remote
  flows that share these writers.
- Extended `OptimizerState` with `recorded_observation_count`,
  `failed_evaluation_count`, `status_counts`, and `progress_source`.
  Existing fields stay backward compatible (new fields have defaults).
  `current_evaluations` now means attempted optimizer evaluations, not
  ledger row count.
- Added `doctor_readiness.build_optimizer_progress_summary` and a new
  `OPTIMIZER_PROGRESS_STATE_MISMATCH` diagnostic. Both
  `product_doctor.run_product_doctor` and
  `remote_doctor.run_remote_doctor` now attach
  `optimizer_progress_summary` to the doctor JSON payload and surface
  the diagnostic when report/evaluations/state/ledger counts disagree.
- Verified existing `_sync_remote_history_to_cache` and
  `_sync_cache_reports_to_remote` already iterate over `state` in both
  directions, so the corrected `state/optimizer_state.json` is mirrored
  to local cache and the remote project automatically.
- Ledger remains usable-only: no synthetic ledger rows are added for
  failed traces. `state/best_candidate.json` remains optional and is
  preserved when present.

Real local/remote 10-point three-corner validation has NOT been run.
Run after release sync:

- local: `ic-opt PROJECT_DIR --real`
- remote: `ic-opt PROJECT_DIR --real --remote SSH_PROFILE`

Expected post-validation: `state.current_evaluations == 10`,
`state.recorded_observation_count == ledger row count`,
`state.failed_evaluation_count == 10 - ledger row count`, and the doctor
JSON includes a populated `optimizer_progress_summary` with no
`OPTIMIZER_PROGRESS_STATE_MISMATCH` diagnostic on a healthy run.

Problem:
Health/doctor still treats these as real-run state artifacts:

- `state/optimizer_state.json`
- `state/best_candidate.json`
- `ledger/experiment_ledger.jsonl`

The failed 80-point OpenBox run only left `state/health_check.json` because all
candidates failed `check_real_run` before `record_real_result` could write state.
The later 10-point local/remote validation showed the same contract split in a
clearer form: reports had 10 attempted evaluations, ledger/state had 7 recorded
observations, and `state/optimizer_state.json` still reported `running`.
Reports contain optimizer traces, but state and report contracts are not unified.

Impact:
Users cannot monitor progress from the legacy state path during failure-heavy
real runs.

Required fix:
Define one progress contract. Either restore progress/best/state writes for the
batch OpenBox path, or update health/doctor/README to make reports the canonical
progress source. Prefer writing batch progress state because users already look
under `state/`.

Files to inspect/fix:

- `src/hermes_workflow/health.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/doctor_readiness.py`

Acceptance:

- During a real run, progress artifacts are present and documented.
- Failed candidates do not erase visibility into total attempted evaluations.

### B-10 Actual Command Traceability Is Incomplete

Status: open

Problem:
Child logs show the real Spectre command, but child `result_manifest.json` does
not persist `argv` or command details beyond simulator metadata.

Impact:
Contract auditing requires reading logs instead of structured manifests.

Required fix:
Persist sanitized actual Spectre/OCEAN command argv or command summary in result
manifests/reports for local and remote adapters.

Files to inspect/fix:

- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- `src/hermes_workflow/metric_results.py`

Acceptance:

- A report can prove `preset`, `threads_per_run`, `output_format`, and timeout
  sources without grepping logs.

### B-11 Dev And Release Packages Are Not Synchronized

Status: open

Problem:
`ic-auto-opt-workflow` and `ic-auto-opt-workflow-v0.1` differ in core modules.
Dev-only modules:

- `doctor_readiness.py`
- `optimizer_effectiveness.py`
- `optimizer_strategy.py`

Different shared modules include:

- `__init__.py`
- `agent_runtime.py`
- `cli.py`
- `native_turbo.py`
- `openbox_backend.py`
- `optimizer_final_summary.py`
- `optimizer_flow.py`
- `optimizer_insights.py`
- `optimizer_status.py`
- `optimizer_task_package.py`
- `product_cli.py`
- `product_doctor.py`
- `remote_doctor.py`
- `remote_optimizer_flow.py`
- `schemas.py`
- `toolchain_env.py`

Also, `multi_testbench_aggregation.py` and `remote_spectre_ocean.py` are the same
in dev and release, so their confirmed bugs are already present in the release
package.

Required fix:
Do not patch release first. Fix dev, run targeted/unit/full/real validation,
then sync the release package deliberately and re-run release smoke.

Acceptance:

- Dev and release sync report is generated after fixes.
- Release package behavior matches dev for doctor, local, and remote optimizer
  paths.

## Confirmed Working Or Mostly Working Contract Paths

These paths are not marked fixed forever; they are current audit findings.

- Spectre `preset` reaches real command as `+preset=<value>`.
- Spectre `threads_per_run` reaches real command as `+mt=<value>`.
- Spectre `output_format` reaches real command as `-format <value>`.
- Design variables reach template rendering and OpenBox/TuRBO search spaces.
- Process corners reach netlist model section / variable rewrite.
- Multi-testbench and multi-corner child package expansion exists.
- Metrics and OCEAN expressions reach metric extraction requests.
- Constraints and objective are used by result recording / aggregation.
- OpenBox `surrogate_type`, `acq_type`, `acq_optimizer_type`, and
  `initial_trials` reach OpenBox Advisor.
- `optimizer_cpu_threads` reaches threadpool/environment limits.
- `failure_penalty` is used for failed observations.

## Repair Order

1. Remove CLI workload/resource overrides and make requirement the only source.
2. Fix `parallel_jobs` contract layer.
3. Fix parent aggregate manifest metadata inheritance.
4. Pass remote `timeout_s` to SSH runner.
5. Add/repair structured command traceability.
6. Fix or reject `require_license_check`.
7. Fix or reject run retention policy fields.
8. Fix or restrict OpenBox initialization.
9. Tighten unsupported output format validation.
10. Restore/define state progress contract.
11. Sync release package only after dev validation passes.

## Validation Gates

Before marking this backlog closed:

- Targeted tests for each blocker pass.
- Full pytest passes in dev package.
- Ruff passes.
- `git diff --check` passes.
- Doctor detects unsupported or unimplemented requirement settings.
- A small real remote multi-corner run reaches accepted handoff.
- A larger remote run proves batch progression and progress artifacts.
- Release package is synced from dev and smoke-tested.
