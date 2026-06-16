# D-01 Doctor Candidate Run Dirty-State Cleanup Design

Date: 2026-06-14
Status: planned
Package boundary: develop and verify in `ic-auto-opt-workflow` first. Do not patch or sync `ic-auto-opt-workflow-v0.1` until dev tests and real-flow validation pass.

## Problem

After the B-09 real local/remote 10-point, three-corner validation completed successfully, local and remote doctor still emitted:

```text
INCOMPLETE_REAL_RUN: real_001
...
INCOMPLETE_REAL_RUN: real_010
```

Those warnings are false positives. Each `runs/real/real_00x` directory is an optimizer candidate run directory, not an optimizer run root. A completed multi-testbench/multi-corner candidate directory contains candidate-level artifacts such as:

- `runs/real/<run_id>/result_manifest.json`
- `runs/real/<run_id>/metrics/metric_result_manifest.json`
- `runs/real/<run_id>/multi_testbench_aggregation_report.json`
- `runs/real/<run_id>/testbenches/<testbench>/corners/<corner>/result_manifest.json`

Optimizer-level reports live at the project root under `reports/`, not inside each candidate directory.

## Source Findings

Local doctor:

- `src/hermes_workflow/doctor_readiness.py::build_dirty_state_summary()` iterates `project_dir / "runs" / "real"`.
- For each child directory, it treats the directory as incomplete unless that directory contains `optimizer_run_report.json` or `optimizer_completion_report.json`.
- This was valid only for an older mental model where a `runs/real/<run_id>` directory could be considered an optimizer run root.
- It is wrong for the current candidate-level run layout.

Remote doctor:

- `src/hermes_workflow/remote_doctor.py::_build_remote_dirty_state()` applies the same optimizer-report-in-candidate-dir check through SSH file probes.
- This creates the same false warning for remote project directories and the local remote cache.

Existing tests:

- `tests/test_doctor_readiness.py::test_dirty_state_warns_on_incomplete_real_run()` only covers an empty `runs/real/real_001` directory.
- Existing tests do not cover a completed candidate run directory that has `result_manifest.json` but no optimizer-level reports.
- Therefore the false positive survived unit tests.

## Required Contract

Doctor dirty-state checks must distinguish these concepts:

- **Optimizer project state:** project-level artifacts under `reports/`, `state/`, and `ledger/`.
- **Candidate run directory:** `runs/real/<run_id>` containing one optimizer candidate evaluation.
- **Completed candidate run:** a candidate run directory with a candidate-level completion artifact, primarily `result_manifest.json`.
- **Interrupted candidate run:** a candidate run directory with no candidate-level result manifest or completion marker.

`INCOMPLETE_REAL_RUN` should mean:

> A candidate run directory under `runs/real/<run_id>` appears to have been started but did not reach a candidate-level final artifact.

It must not mean:

> The candidate directory does not contain optimizer-level reports.

## Completion Markers

A candidate run directory is complete if any of these are true:

- `runs/real/<run_id>/result_manifest.json` exists.
- `runs/real/<run_id>/metrics/metric_result_manifest.json` exists and the codebase intentionally supports metric-only failure recording.
- legacy compatibility: `runs/real/<run_id>/optimizer_run_report.json` or `runs/real/<run_id>/optimizer_completion_report.json` exists.

For the current multi-testbench/multi-corner flow, `result_manifest.json` is the required primary marker. Child corner result manifests alone are not enough to declare the parent candidate finalized, because aggregation may still have been interrupted.

An empty `runs/real/<run_id>` directory must still warn.

A directory with `candidate_request.json` or `candidate.json` but no `result_manifest.json` must still warn.

## Local And Remote Parity

Local and remote doctor must share the same classification semantics.

Recommended structure:

- Add a small shared classifier in `doctor_readiness.py`, such as `classify_real_run_dir_dirty_state(...)`.
- Local doctor gathers facts from the local filesystem.
- Remote doctor gathers the same facts through SSH probes and passes them to the shared classifier.

Remote doctor must not invent a separate rule.

## Non-Goals

- Do not change optimizer execution.
- Do not change OpenBox, TuRBO, multi-corner aggregation, retention, or state/progress contracts.
- Do not remove `INCOMPLETE_REAL_RUN` entirely.
- Do not stop warning for genuinely interrupted candidate directories.
- Do not edit or sync the release package before dev validation.

## Acceptance Criteria

1. A completed candidate directory with `runs/real/real_001/result_manifest.json` and no optimizer-level report files does not emit `INCOMPLETE_REAL_RUN`.
2. A completed multi-testbench/multi-corner candidate directory with child manifests and parent `result_manifest.json` does not emit `INCOMPLETE_REAL_RUN`.
3. An empty `runs/real/real_001` directory still emits `INCOMPLETE_REAL_RUN`.
4. A started candidate directory with `candidate_request.json` but no `result_manifest.json` still emits `INCOMPLETE_REAL_RUN`.
5. Remote doctor uses the same classification rule with fake SSH tests.
6. Re-running doctor on the B-09 real validation projects no longer emits `INCOMPLETE_REAL_RUN` for the 10 completed candidate directories.
7. Other doctor diagnostics still work, including `REMOTE_PARALLELISM_HIGH`.

## Validation Scope

Unit tests must cover local and remote fake projects.

Real validation should use the already completed B-09 projects:

- local: `/tmp/ic_opt_local10_3corner_b09_20260614_050335`
- remote project: `/home/zzchen/remote_opt/Mixer_CS_validation_b09_remote10_20260614_050335`
- remote local cache: `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/6262d2d3ddf1e488`

Expected real validation evidence:

- local doctor has no `INCOMPLETE_REAL_RUN` codes.
- remote doctor has no `INCOMPLETE_REAL_RUN` codes.
- remote doctor may still emit `REMOTE_PARALLELISM_HIGH` because `parallel_jobs=10`.
