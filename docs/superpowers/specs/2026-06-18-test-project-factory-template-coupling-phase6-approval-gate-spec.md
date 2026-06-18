# Phase 6 Spec: Approval Gate Template Decoupling

Date: 2026-06-18
Status: ready for implementation prompt
Owner: Claude implementation, Codex planning/review

## Context

After Phase 5, `ALLOWED_TEMPLATE_CALLERS` has 16 remaining files. The next
lowest-risk target is the approval gate test file:

- `tests/test_approvals.py`

This file verifies the decision layer that writes `supervisor_instruction.json`
before any real optimizer or fix-run execution is allowed. The production code
under test is intentionally small:

- `decide_first_real_run()` validates the execution manifest, immutable config
  hashes, project config, and optimizer preflight reports.
- `decide_fix_run_real_run()` validates the execution manifest and project config
  for fix-run mode, but does not require optimizer preflight reports.

The approval gate should not depend on the packaged release example circuit.

## Problem

`tests/test_approvals.py` still creates projects through
`create_project_from_template()` and carries old release-template assumptions:

- project names such as `bridge_test_inv`,
- fixed-point parameters `FN`, `WN`, `FP`, `WP`,
- manually written report payloads with old approved-variable names.

Those names are incidental. The behavior being tested is the approval contract:

- approve optimizer real run only after manifest, validation, and preflight pass,
- reject missing or malformed execution manifests,
- reject invalid project config while preserving manifest-approved hashes,
- reject missing or failing preflight reports in optimizer mode,
- keep fix-run approval distinct from optimizer approval,
- write the supervisor instruction deterministically.

Phase 6 should remove the packaged-template dependency without changing the
production approval logic.

## Scope

Primary files in scope:

- `tests/test_approvals.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed helper scope:

- Prefer local helper functions inside `tests/test_approvals.py`.
- Do not create a shared helper unless implementation proves more than one file
  needs the same logic. Current audit shows no external consumers of
  `tests.test_approvals`.

No production source files are in scope. If a production bug appears to block the
migration, stop and report it instead of changing production code.

## Requirements

1. Remove direct `create_project_from_template()` usage from
   `tests/test_approvals.py`.
2. Use `tests/project_factory.py` as the source of test projects:
   - `create_generic_project()` for unpackaged projects,
   - `create_packaged_generic_project()` for manifest/package setup,
   - `workflow_mode="fix_run"` for fix-run approval tests.
3. Remove old release-template strings from `tests/test_approvals.py`:
   `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, and `create_project_from_template`.
4. Preserve the existing optimizer approval coverage:
   - approve path writes `approve_first_real_run`,
   - dry-run failure rejects and includes the report issue,
   - missing execution manifest rejects and writes the instruction file,
   - invalid project config rejects after manifest load and keeps approved hashes,
   - invalid manifest JSON rejects with empty approved hashes,
   - manifest missing `immutable_config_files` rejects with empty approved hashes,
   - health report with real-run-started issue rejects,
   - missing preflight report cases reject with exact missing paths,
   - malformed present report still raises the strict loading exception,
   - missing project directory still writes a reject instruction,
   - optimizer mode still requires preflight reports.
5. Preserve the existing fix-run approval coverage:
   - fix-run approval does not require optimizer preflight reports,
   - fix-run approval allows `prepare_fixed_candidate_real_run`,
   - fix-run approval forbids `run_standalone_spectre_optimizer`,
   - fix-run approval does not create or require `reports/dry_run_report.json`.
6. Report payloads that mention approved variables must derive variable names
   from the generated generic project, rather than hardcoding a new fixture name.
7. Remove `tests/test_approvals.py` from `ALLOWED_TEMPLATE_CALLERS`; the allowlist
   should shrink from 16 to 15.
8. Update the inventory report with Phase 6 status, files migrated, guard count,
   exact verification commands, and remaining deferred work.

## Non-Goals

- Do not migrate `tests/test_optimizer_task_package.py`,
  `tests/test_run_retention.py`, `tests/test_fix_run_flow.py`,
  `tests/test_multi_testbench_aggregation.py`,
  `tests/test_optimizer_progress_state.py`, or `tests/real_run_smoke_helpers.py`
  in this phase.
- Do not migrate optimizer backend tests.
- Do not migrate remote or adapter tests.
- Do not change packaged release templates or examples.
- Do not touch the release checkout at `../ic-auto-opt-workflow-v0.1`.
- Do not edit or stage `graphify-out/`.
- Do not commit, tag, or push.

## Acceptance Criteria

The implementation is acceptable only if all of the following are true:

- `tests/test_approvals.py` passes individually.
- `tests/test_approvals.py` contains no
  `create_project_from_template`, `bridge_test_inv`, `FN`, `WN`, `FP`, or `WP`
  matches.
- `tests/test_template_coupling_guard.py` passes and the allowlist has 15 files.
- No external test imports from `tests.test_approvals`.
- The Phase 1-6 regression group passes.
- The full suite passes.
- `ruff check src tests` passes.
- `git diff --check` is clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` remains clean.
