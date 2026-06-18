# Phase 7 Spec: Optimizer Task Package Template Decoupling

Date: 2026-06-18
Status: ready for implementation prompt
Owner: Claude implementation, Codex planning/review

## Context

After Phase 6, `ALLOWED_TEMPLATE_CALLERS` has 15 remaining files. The next
focused target is:

- `tests/test_optimizer_task_package.py`

This file validates the optimizer execution task package: generated task
markdown, optimizer execution manifest, scheduler settings, backend/strategy
routing, CLI entrypoint behavior, shell-safe absolute paths, and forbidden-action
section placement.

The file is large enough to deserve its own phase. Do not combine it with
run-retention or progress-state migration.

## Problem

`tests/test_optimizer_task_package.py` still builds projects through
`create_project_from_template()` and carries old release-template assumptions:

- project name `bridge_test_inv`,
- template defaults such as `max_evaluations: 100`, `batch_size: 10`, and
  `parallel_jobs: 10`,
- text replacement against the old `config/optimizer.yaml` formatting.

The behavior under test is generic:

- `build_optimizer_execution_task_package()` reads validated project config,
- optimizer backend and strategy are derived from arguments plus config,
- scheduler and Spectre/OCEAN settings are split correctly,
- CLI packaging writes task and manifest artifacts,
- generated commands use absolute shell-safe paths,
- task markdown keeps required behavior and forbidden actions in the right
  sections.

Phase 7 should remove the packaged-template dependency without changing
production package generation logic.

## Scope

Primary files in scope:

- `tests/test_optimizer_task_package.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed helper scope:

- Prefer local helper functions inside `tests/test_optimizer_task_package.py`.
- Do not create a shared helper unless implementation proves more than one file
  needs the same logic. Current audit shows no external consumers of
  `tests.test_optimizer_task_package`.

No production source files are in scope. If a production bug appears to block the
migration, stop and report it instead of changing production code.

## Requirements

1. Remove direct `create_project_from_template()` usage from
   `tests/test_optimizer_task_package.py`.
2. Use `tests/project_factory.py` as the project source of truth.
3. Preserve the test's existing optimizer-task coverage:
   - native TuRBO task and manifest writing,
   - OpenBox task and manifest writing,
   - config-driven `turbo_trust_region` backend routing,
   - config-driven `openbox_prf_eic` strategy routing,
   - OpenBox continuation package,
   - CLI package generation for native and OpenBox,
   - shell-safe absolute command paths,
   - scheduler settings not mislabeled as Spectre/OCEAN settings,
   - forbidden actions kept out of required behavior,
   - OpenBox fallback rule kept in required behavior,
   - explicit OpenBox strategy included in task and manifest.
4. Preserve intentional numeric package behavior by creating the generic project
   with explicit test settings where needed:
   - `max_evaluations=100`,
   - `batch_size=10`,
   - `parallel_jobs=10`.
5. Do not hardcode a new stale circuit. Assertions that depend on config values
   should derive them from generated `config/optimizer.yaml` and
   `config/spectre.yaml` when practical.
6. Replace text replacement of `config/optimizer.yaml` with structured YAML
   mutation.
7. Remove old release-template strings from the target file:
   `create_project_from_template`, `bridge_test_inv`, `FN`, `WN`, `FP`, and `WP`.
8. Remove `tests/test_optimizer_task_package.py` from
   `ALLOWED_TEMPLATE_CALLERS`; the allowlist should shrink from 15 to 14.
9. Update the inventory report with Phase 7 status, files migrated, guard count,
   exact verification commands, and remaining deferred work.

## Non-Goals

- Do not migrate `tests/test_run_retention.py`,
  `tests/test_optimizer_progress_state.py`, `tests/test_fix_run_flow.py`,
  `tests/test_multi_testbench_aggregation.py`, or
  `tests/real_run_smoke_helpers.py` in this phase.
- Do not migrate optimizer backend tests.
- Do not migrate remote or adapter tests.
- Do not change packaged release templates or examples.
- Do not touch the release checkout at `../ic-auto-opt-workflow-v0.1`.
- Do not edit or stage `graphify-out/`.
- Do not commit, tag, or push.

## Acceptance Criteria

The implementation is acceptable only if all of the following are true:

- `tests/test_optimizer_task_package.py` passes individually.
- `tests/test_optimizer_task_package.py` contains no
  `create_project_from_template`, `bridge_test_inv`, `FN`, `WN`, `FP`, or `WP`
  matches.
- `tests/test_template_coupling_guard.py` passes and the allowlist has 14 files.
- No external test imports from `tests.test_optimizer_task_package`.
- The Phase 1-7 regression group passes.
- The full suite passes.
- `ruff check src tests` passes.
- `git diff --check` is clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` remains clean.
