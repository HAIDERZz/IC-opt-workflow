# C-21 OCEAN Metric Extraction Retry Policy Plan

## Goal

Handle real-tool OCEAN metric extraction command/license failures exposed by
C-20 without expanding the optimizer framework.

## Evidence

C-20 autonomous handoff attempt 2 completed 100 Spectre runs successfully, but
2 metric extractions failed with OCEAN return code `35` and license checkout
errors. The failure was after Spectre succeeded and before scalar metrics were
available.

## Scope Guard

Allowed:

- retry OCEAN-only metric extraction after non-zero OCEAN return code;
- keep the already-completed Spectre result directory unchanged;
- record retry attempts in the metric result manifest;
- add focused adapter tests and one real-tool acceptance rerun.

Forbidden:

- rerun Spectre for OCEAN-only failures;
- retry candidate-level non-scalar metric failures;
- parse PSF in Python;
- rewrite OCEAN formulas;
- change metric formulas;
- hand-pick optimizer candidates;
- create scheduler/service/daemon/framework work.

## Task 1: Adapter OCEAN Retry Contract

**Status:** Complete, verified-only.

- [x] Add a focused failing test for transient OCEAN command failure followed
  by success.
- [x] Implement minimal OCEAN-only retry in the C-7 adapter.
- [x] Record OCEAN attempts and return codes in `metric_result_manifest.json`.
- [x] Verify existing OCEAN failure manifests still fail clearly when all
  attempts fail.

## Task 2: C-20 Regression Rerun

**Status:** Complete, verified-only.

- [x] Run one real `run-native-turbo --parallel --max-evals 100` acceptance on
  a clean `/tmp` project.
- [x] Confirm no OCEAN command/license failures remain after retry, or record
  the remaining failure count.
- [x] Do not require every candidate metric to be scalar; candidate-level
  metric failures remain legitimate optimizer outcomes.

Result: `/tmp/ic_auto_opt_c21/bridge_test_inv` completed 100 evaluations with
100 result manifests succeeded, 100 metric manifests produced, 86 metric
manifests succeeded, 14 candidate-level non-scalar metric failures, and 0 final
OCEAN command/license failures. This rerun did not need actual retries.

## Task 3: Closeout

**Status:** Complete, verified-only.

- [x] Write one sanitized debug note.
- [x] Update current-state/progress nodes.
- [x] Run verification and commit.
