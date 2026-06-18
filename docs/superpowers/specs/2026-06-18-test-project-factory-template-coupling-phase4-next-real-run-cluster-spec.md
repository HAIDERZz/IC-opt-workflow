# Phase 4 Spec: Next Real-Run Cluster Template Decoupling

Date: 2026-06-18
Status: ready for implementation prompt
Owner: Claude implementation, Codex planning/review

## Context

Phases 1-3 introduced the generic test project factory and migrated the first
real-run, recovery, metric-result, result-handoff, health, and optimizer-flow test
areas away from the packaged release template. Phase 3 intentionally deferred
`tests/test_next_real_run.py` because it is the hub of a four-file cluster:

- `tests/test_next_real_run.py`
- `tests/test_candidate_injection_real_run.py`
- `tests/test_optimizer_suggestion.py`
- `tests/test_optimizer_loop.py`

The three consumer files import helpers from `tests/test_next_real_run.py`, and
some also contain their own hardcoded old-template variable and metric names.
Migrating only the hub breaks the consumers, so this phase must migrate the
cluster as a unit.

## Problem

The cluster still assumes the old packaged example circuit:

- project name: `bridge_test_inv`
- variables: `FN`, `WN`, `FP`, `WP`
- metrics: `rise`, `fall`, `DC`
- a local `TEMPLATE_TEXT` netlist overlay
- exact four-variable candidate parameter dictionaries

Those assumptions are not the behavior under test. The real contracts are:

- preparing the next real run after `real_001` is recorded,
- preserving ledger/state consistency across `real_002+`,
- injecting explicit optimizer candidate requests,
- generating optimizer suggestions from initialization or TuRBO,
- running one optimizer-loop cycle and recording the fake result.

The tests should exercise those contracts against a valid generic project and
should derive variable/metric names from the generated project artifacts.

## Scope

Primary files in scope:

- `tests/test_next_real_run.py`
- `tests/test_candidate_injection_real_run.py`
- `tests/test_optimizer_suggestion.py`
- `tests/test_optimizer_loop.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Expected new test helper:

- `tests/real_run_cluster_helpers.py`

The helper should hold shared generic setup and fake-result helpers that are
currently exported from `tests/test_next_real_run.py`.

No production source files are in scope unless implementation proves a production
bug is blocking the migration. If that happens, stop and report before changing
production code.

## Requirements

1. Remove direct `create_project_from_template()` usage from
   `tests/test_next_real_run.py`.
2. Remove old release-template names from all four cluster files:
   `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, `rise`, `fall`, `DC`, and
   `TEMPLATE_TEXT`.
3. Create a shared test helper module for:
   - loading/writing JSON,
   - creating a generic approved project and preparing `real_001`,
   - writing fake real-run result manifests,
   - writing fake metric-result manifests from `metric_extraction_request.json`,
   - recording `real_001`,
   - building valid, missing, extra, duplicate, and invalid generic candidate
     parameter dictionaries.
4. The helper must use `tests/project_factory.py` as the project source of truth.
   It may rely on the generic factory contract, but ordinary assertions should
   derive variable and metric names from config, manifests, or requests.
5. Do not replace strong behavioral assertions with weak existence checks.
6. Candidate injection tests must continue to validate missing parameters, extra
   parameters, invalid integer values, out-of-bounds values, bad unit formatting,
   duplicate candidate IDs, duplicate parameter tuples, cleanup on write failure,
   CLI behavior, and fake-result recording.
7. Optimizer suggestion tests must continue to validate initialization fallback,
   prepared candidate handoff, bad candidate IDs, missing ledger/state, completed
   state, maximum-evaluation rejection, unresolved run rejection, TuRBO selection,
   CLI behavior, and no overwrite on competing writes.
8. Optimizer loop tests must continue to validate recorded cycles, ID allocation,
   adapter failure, result-check failure, metric-check failure, record failure,
   tool success, tool adapter failure, and empty budget rejection.
9. Remove `tests/test_next_real_run.py` from `ALLOWED_TEMPLATE_CALLERS`; the
   allowlist should shrink from 19 to 18.
10. Update the inventory report with Phase 4 status, the new helper, files
    migrated, guard count, exact verification commands, and remaining deferred
    work.

## Non-Goals

- Do not migrate approvals, packaging, backend, remote, adapter, retention,
  netlist, mock optimizer, native TuRBO, or OpenBox tests in this phase.
- Do not change packaged release templates or examples.
- Do not touch the release checkout at `../ic-auto-opt-workflow-v0.1`.
- Do not edit or stage `graphify-out/`.
- Do not commit, tag, or push.

## Acceptance Criteria

The implementation is acceptable only if all of the following are true:

- The four cluster files pass individually.
- The four cluster files contain no `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`,
  `TEMPLATE_TEXT`, `"rise"`, `"fall"`, or `"DC"` matches.
- `tests/test_next_real_run.py` no longer imports or calls
  `create_project_from_template()`.
- The three consumer files no longer import helpers from
  `tests.test_next_real_run`; shared helpers come from
  `tests.real_run_cluster_helpers`.
- `tests/test_template_coupling_guard.py` passes and the allowlist has 18 files.
- The Phase 1-4 regression group passes.
- The full suite passes.
- `ruff check src tests` passes.
- `git diff --check` is clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` remains clean.
