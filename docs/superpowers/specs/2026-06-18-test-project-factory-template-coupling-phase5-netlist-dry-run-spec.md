# Phase 5 Spec: Netlist and Dry-Run Preflight Template Decoupling

Date: 2026-06-18
Status: ready for implementation prompt
Owner: Claude implementation, Codex planning/review

## Context

After Phase 4, `ALLOWED_TEMPLATE_CALLERS` has 18 remaining files. The next
lowest-risk part of the "Approvals and packaging" wave is the preflight pair:

- `tests/test_netlists.py`
- `tests/test_dry_run.py`

These tests validate project preflight behavior before approvals and packaging:
netlist templating, forbidden setup detection, corner template rendering, dry-run
placeholder checks, mock metrics/objective/constraint evaluability, and dry-run
artifact cleanup.

They are foundational for later approval/package migration, but they should not
depend on the packaged release example circuit.

## Problem

The two files still build projects with `create_project_from_template()` and rely
on the old release-template circuit shape:

- project name `bridge_test_inv`
- variables `FN`, `WN`, `FP`, `WP`
- hand-written `TEMPLATE_TEXT`-style netlists
- metric/constraint fixture text inherited from the release template

The product behavior under test is generic:

- approved variables are templated only at top-level parameter declarations,
- missing/duplicate/misplaced approved variables produce clear failure reports,
- process-corner rendering rewrites model sections/files and arbitrary variables,
- dry-run renders the lower-bound candidate and reports placeholder issues,
- dry-run does not write optimizer artifacts.

Those contracts can be tested with `tests/project_factory.py` and generated
generic variables instead of the packaged release template.

## Scope

Primary files in scope:

- `tests/test_netlists.py`
- `tests/test_dry_run.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Expected new helper:

- `tests/netlist_dry_run_helpers.py`

No production source files are in scope. If a production bug appears to block
the migration, stop and report it instead of changing production code.

## Requirements

1. Remove direct `create_project_from_template()` usage from
   `tests/test_netlists.py` and `tests/test_dry_run.py`.
2. Replace project setup with `tests/project_factory.py`, through a small shared
   helper module used only by these tests.
3. Remove old release-template strings from both target files and the helper:
   `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, and `TEMPLATE_TEXT`.
4. `tests/test_dry_run.py` must preserve coverage for:
   - lower-bound candidate rendering,
   - missing template failure,
   - missing approved placeholder failure,
   - unexpected placeholder failure,
   - malformed unresolved placeholder failure,
   - stale rendered file cleanup,
   - false-but-evaluable constraints,
   - no optimizer artifacts written,
   - render write failure.
5. `tests/test_netlists.py` must preserve coverage for:
   - single-line parameter templating,
   - backslash-continued parameter templating,
   - not templating instance/subckt parameter assignments,
   - missing exported input report,
   - missing approved variable report,
   - duplicate approved variable report,
   - whitespace-unit templating,
   - fail-closed subckt parameter assignments,
   - pure `render_corner_netlist_template()` behavior,
   - multi-testbench corner template generation and skip behavior.
6. Assertions should derive approved variable names from generated config rather
   than hardcoding a new scattered variable set.
7. Remove both target files from `ALLOWED_TEMPLATE_CALLERS`; the allowlist should
   shrink from 18 to 16.
8. Update the inventory report with Phase 5 status, files migrated, helper
   created, guard count, exact verification commands, and remaining deferred work.

## Non-Goals

- Do not migrate `tests/test_approvals.py`, `tests/test_optimizer_task_package.py`,
  `tests/test_run_retention.py`, `tests/test_fix_run_flow.py`,
  `tests/test_multi_testbench_aggregation.py`, `tests/test_optimizer_progress_state.py`,
  or `tests/real_run_smoke_helpers.py` in this phase.
- Do not migrate optimizer backend tests.
- Do not migrate remote or adapter tests.
- Do not change packaged release templates or examples.
- Do not touch the release checkout at `../ic-auto-opt-workflow-v0.1`.
- Do not edit or stage `graphify-out/`.
- Do not commit, tag, or push.

## Acceptance Criteria

The implementation is acceptable only if all of the following are true:

- `tests/test_netlists.py` and `tests/test_dry_run.py` pass individually.
- The two target files and `tests/netlist_dry_run_helpers.py` contain no
  `create_project_from_template`, `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, or
  `TEMPLATE_TEXT` matches.
- `tests/test_template_coupling_guard.py` passes and the allowlist has 16 files.
- The Phase 1-5 regression group passes.
- The full suite passes.
- `ruff check src tests` passes.
- `git diff --check` is clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` remains clean.
