# Phase 3 Spec: Real-Run Package and Recovery Test Decoupling

Date: 2026-06-18
Status: ready for implementation prompt
Owner: Claude implementation, Codex planning/review

## Context

Phase 1 introduced `tests/project_factory.py`, `tests/test_project_factory.py`, and
`tests/test_template_coupling_guard.py`. Phase 2 migrated the metric-result and
result-handoff tests away from `create_project_from_template()` and shrank the
guard allowlist from 23 files to 21 files.

The next lowest-risk group is the real-run package path:

- `tests/test_real_run.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run_recovery.py`

These files still build projects from the packaged release template and then
overlay circuit-specific test contents (`bridge_test_inv`, `FN/WN/FP/WP`,
`rise/fall/DC`, and hardcoded optimizer-init candidate values). That makes the
tests fail for the wrong reason whenever the release template changes, and it
keeps product-template validation mixed with real-run behavior validation.

## Problem

The three Phase 3 target files are not testing the packaged template itself.
They are testing:

- first real-run package construction,
- next real-run package construction after a recorded result,
- ledger/state validation around real-run continuation,
- failed-result recovery and retry behavior.

Those contracts should be exercised with a valid generic project created by the
test factory. The current tests instead rely on the release example circuit. This
causes two concrete problems:

- Template updates create broad test failures unrelated to the real-run contract.
- Remaining `create_project_from_template()` usage keeps growing as a hidden
  cross-test helper dependency.

## Scope

Primary files in scope:

- `tests/test_real_run.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run_recovery.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed narrow scope expansion:

- `tests/test_cli.py`, only if its imports from `tests.test_real_run_recovery`
  break after the migration.
- `tests/test_candidate_injection_real_run.py`, `tests/test_optimizer_loop.py`,
  and `tests/test_optimizer_suggestion.py`, only if their imports from
  `tests.test_next_real_run` break after the migration.

No production source files are in scope unless implementation proves that a
production bug is blocking the migration. If that happens, stop and report the
finding instead of silently broadening the change.

## Requirements

1. Remove direct `create_project_from_template()` usage from all three Phase 3
   target files.
2. Replace template-based setup with the appropriate factory helper:
   `create_generic_project()`, `create_packaged_generic_project()`, or
   `create_approved_generic_project()`.
3. Preserve the real-run behavior assertions. Do not weaken tests into "file
   exists" checks if the old test asserted a specific contract.
4. Derive variable and metric names from the generated project config,
   `candidate.json`, `real_run_manifest.json`, or
   `metric_extraction_request.json` whenever practical.
5. Target files must not contain release-template-specific strings:
   `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, `rise`, `fall`, `DC`, or
   `TEMPLATE_TEXT`.
6. Fake result manifests must use the metric names requested by the generated
   run, not hardcoded release-template metric names.
7. Retry/failure tests must use parameters compatible with the generic factory
   variables.
8. Exported helper functions currently imported by non-target tests must remain
   usable, or the importing test must receive a minimal local helper copy or
   a small shared helper. Do not leave brittle cross-test imports broken.
9. Remove the three target files from `ALLOWED_TEMPLATE_CALLERS`; the allowlist
   should shrink from 21 to 18.
10. Update the inventory report with Phase 3 status, files migrated, remaining
    allowlist count, scope expansions if any, and exact verification commands.

## Non-Goals

- Do not migrate backend, remote, adapter, approval, package, netlist, retention,
  or optimizer-backend tests in this phase.
- Do not change packaged release templates or examples.
- Do not touch the release checkout at `../ic-auto-opt-workflow-v0.1`.
- Do not stage or edit `graphify-out/`.
- Do not commit, tag, or push.

## Acceptance Criteria

The implementation is acceptable only if all of the following are true:

- `tests/test_real_run.py`, `tests/test_next_real_run.py`, and
  `tests/test_real_run_recovery.py` no longer call
  `create_project_from_template()`.
- The same three files no longer contain `bridge_test_inv`, `FN`, `WN`, `FP`,
  `WP`, `"rise"`, `"fall"`, `"DC"`, or `TEMPLATE_TEXT`.
- `tests/test_template_coupling_guard.py` passes and its allowlist has 18 files.
- Existing helper consumers still pass:
  `tests/test_cli.py`, `tests/test_candidate_injection_real_run.py`,
  `tests/test_optimizer_loop.py`, and `tests/test_optimizer_suggestion.py`.
- The focused Phase 3 tests pass.
- The full suite passes.
- `ruff check src tests` passes.
- `git diff --check` is clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` remains clean.
