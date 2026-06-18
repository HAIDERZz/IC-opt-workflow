# Claude Prompt: Test Project Factory and Template Coupling Cleanup Phase 3

You are working in:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Do not touch the release checkout:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`

Do not edit or stage `graphify-out/`.

## Goal

Implement Phase 3 of the Test Project Factory and Template Coupling Cleanup:
migrate the real-run package / next-run / recovery tests away from
`create_project_from_template()` and old release-template assumptions.

Read these files first:

- `docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase3-real-run-spec.md`
- `docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase3-real-run-plan.md`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_template_coupling_guard.py`
- `tests/test_real_run.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run_recovery.py`

If codegraph is available, use it to inspect callers/callees for the target
helper functions. If graphify is available and `graphify-out/` exists, use it to
orient yourself around the dependency graph, but treat source files and tests as
authoritative.

## Strict Scope

Primary files you may modify:

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

If any other file appears necessary, stop and report the issue with options.

Do not modify production source in this phase.
Do not modify packaged templates or examples.
Do not commit, tag, push, or publish.

## Required Behavior

1. Remove direct `create_project_from_template()` usage from:
   - `tests/test_real_run.py`
   - `tests/test_next_real_run.py`
   - `tests/test_real_run_recovery.py`
2. Replace project setup with `tests/project_factory.py` helpers.
3. Remove old release-template strings from the target files:
   - `bridge_test_inv`
   - `FN`
   - `WN`
   - `FP`
   - `WP`
   - `TEMPLATE_TEXT`
   - `"rise"`
   - `"fall"`
   - `"DC"`
4. Fake result manifests must derive metric names from
   `metric_extraction_request.json`.
5. Candidate and parameter assertions must derive from generated generic project
   config/manifests where practical. Do not replace strong checks with weak
   existence checks.
6. Preserve the existing real-run, next-run, ledger/state, and recovery behavior
   contracts.
7. Remove the three migrated files from `ALLOWED_TEMPLATE_CALLERS`; the allowlist
   should shrink from 21 to 18.
8. Update the inventory report with Phase 3 status and exact verification
   results.

## Known Risk

The target files export helpers used by other tests:

- `tests/test_next_real_run.py` is imported by:
  - `tests/test_candidate_injection_real_run.py`
  - `tests/test_optimizer_loop.py`
  - `tests/test_optimizer_suggestion.py`
- `tests/test_real_run_recovery.py` is imported by:
  - `tests/test_cli.py`

Audit those imports before deleting or changing helper signatures. Prefer keeping
helper APIs compatible. If compatibility would keep old template text inside a
migrated target file, localize the helper in the importing test or create a small
shared helper. Keep any scope expansion minimal and document it in the final
report and inventory.

## Verification Commands

Use the repo venv:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_next_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_run_recovery.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_cli.py tests/test_candidate_injection_real_run.py tests/test_optimizer_loop.py tests/test_optimizer_suggestion.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py \
  tests/test_real_run.py \
  tests/test_next_real_run.py \
  tests/test_real_run_recovery.py \
  tests/test_cli.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_loop.py \
  tests/test_optimizer_suggestion.py \
  -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Run these drift checks:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py || true
grep -n '"rise"\|"fall"\|"DC"' \
  tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py || true
grep -R -n "from tests.test_real_run_recovery\|from tests.test_next_real_run\|from tests.test_real_run" tests || true
```

Expected:

- The first two greps have no target-file matches.
- The import grep may have remaining intentional helper imports, but all such
  imports must be explained and covered by passing tests.

## Final Report Required

Report:

- files modified,
- exact migration summary per target file,
- guard allowlist count before and after,
- any scope expansion and why it was necessary,
- exact verification command results,
- release checkout status,
- whether `graphify-out/` was untouched,
- any deferred work.

Do not claim the broader template-coupling cleanup is complete. Claim only Phase
3 if all acceptance criteria pass.
