# Claude Prompt: Phase 6 Approval Gate Template Decoupling

You are working in:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Do not touch the release checkout:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`

Do not edit or stage `graphify-out/`.
Do not commit, tag, push, or publish.

## Goal

Implement Phase 6 of the Test Project Factory and Template Coupling Cleanup:
migrate the approval gate tests away from the packaged release template.

This phase covers exactly:

- `tests/test_approvals.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Read First

Read these files before editing:

- `docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase6-approval-gate-spec.md`
- `docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase6-approval-gate-plan.md`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- `tests/project_factory.py`
- `tests/report_helpers.py`
- `tests/test_template_coupling_guard.py`
- `tests/test_approvals.py`
- `src/hermes_workflow/approvals.py`
- `src/hermes_workflow/package.py`
- `src/hermes_workflow/reports.py`

If codegraph is available, use it to inspect:

- `tests/test_approvals.py`
- `decide_first_real_run`
- `decide_fix_run_real_run`
- `create_generic_project`
- `create_packaged_generic_project`
- `write_pass_reports`

If graphify is available and `graphify-out/` exists, use it only for orientation.
Source files and tests are authoritative.

## Strict Scope

You may modify:

- `tests/test_approvals.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Prefer local helper functions inside `tests/test_approvals.py`. Do not create a
shared helper unless you first prove more than one file needs it. Current audit
shows no source-level external consumers of `tests.test_approvals`.

If any other file appears necessary, stop and report options before editing it.
Do not modify production source in this phase.
Do not modify packaged templates or examples.
Do not modify the Phase 6 spec, plan, or this prompt.

## Required Behavior

1. Remove direct `create_project_from_template()` usage from
   `tests/test_approvals.py`.
2. Use `tests/project_factory.py` as the project source of truth:
   - `create_generic_project()` for unpackaged projects,
   - `create_packaged_generic_project()` for execution-manifest setup,
   - `workflow_mode="fix_run"` for fix-run approval tests.
3. Remove old release-template strings from `tests/test_approvals.py`:
   - `bridge_test_inv`
   - `FN`
   - `WN`
   - `FP`
   - `WP`
   - `create_project_from_template`
4. Preserve optimizer approval coverage:
   - approve path writes `approve_first_real_run`,
   - dry-run failure rejects and includes the report issue,
   - missing execution manifest rejects and writes `supervisor_instruction.json`,
   - invalid project config rejects after manifest load and keeps approved hashes,
   - invalid manifest JSON rejects with empty approved hashes,
   - manifest missing `immutable_config_files` rejects with empty approved hashes,
   - health report with real-run-started issue rejects,
   - missing preflight report cases reject with exact missing paths,
   - malformed present report still raises the strict loading exception,
   - missing project directory still writes a reject instruction,
   - optimizer mode still requires preflight reports.
5. Preserve fix-run approval coverage:
   - fix-run approval does not require optimizer preflight reports,
   - fix-run approval allows `prepare_fixed_candidate_real_run`,
   - fix-run approval forbids `run_standalone_spectre_optimizer`,
   - fix-run approval does not create or require `reports/dry_run_report.json`.
6. Derive approved variable names from generated `config/variables.yaml`.
   Do not introduce a new hardcoded fixture circuit.
7. Remove `tests/test_approvals.py` from `ALLOWED_TEMPLATE_CALLERS`; allowlist
   count should shrink from 16 to 15.
8. Update the inventory report with Phase 6 status and exact verification results.

## Implementation Guidance

In `tests/test_approvals.py`, add small local helpers:

- `_variable_names(project_dir)` reads `config/variables.yaml`.
- `_create_project(tmp_path, name=...)` uses `create_generic_project`.
- `_create_packaged_project(tmp_path, name=..., created_at_utc=...)` uses
  `create_packaged_generic_project`.
- `_create_packaged_fix_run_project(...)` uses
  `create_packaged_generic_project(..., workflow_mode="fix_run")`.
- `_write_pass_reports(project_dir)` calls `write_pass_reports` with derived
  variable names.
- `_write_netlist_pass_report(project_dir)` and `_write_dry_run_pass_report(project_dir)`
  should write generic partial preflight reports for missing-report tests.

Do not hand-write `config/workflow.yaml` or `config/fixed_points.yaml` in fix-run
tests. The generic factory already creates a valid fix-run project with generated
variable names.

Keep existing assertion strength. Do not weaken exact decision/reason/action
checks into broad smoke checks.

## Verification Commands

Run the baseline target test before editing:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_approvals.py -q
```

Run focused checks after migration:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_approvals.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_approvals.py \
  tests/test_template_coupling_guard.py \
  -q
```

Run the Phase 1-6 regression group:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py \
  tests/test_real_run.py \
  tests/test_real_run_recovery.py \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  tests/test_netlists.py \
  tests/test_dry_run.py \
  tests/test_approvals.py \
  -q
```

Run final checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Run drift checks:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_approvals.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_approvals\|tests.test_approvals" tests || true
```

Expected:

- No old-template matches in `tests/test_approvals.py`.
- No source-level cross-test imports from `tests.test_approvals`.
- Guard passes with allowlist count 15.
- Release checkout remains clean.

## Stop Conditions

Stop and report before broadening scope if:

- a production source change appears necessary,
- any other test file must be modified to make `tests/test_approvals.py` pass,
- `tests.test_approvals` has a source-level external consumer not found in the
  baseline audit,
- the generic factory must learn behavior that is specific to approval tests only,
- remote, adapter, backend, retention, or fix-run flow tests become involved,
- full-suite failures reveal a separate existing product bug.

## Final Report Required

Report:

- files modified,
- approval-test migration summary,
- helper functions added inside `tests/test_approvals.py`,
- optimizer approval coverage preserved,
- fix-run approval coverage preserved,
- guard allowlist count before and after,
- exact verification command results,
- drift grep results,
- release checkout status,
- confirmation that `graphify-out/` was untouched,
- any deferred work.

Do not claim the broader template-coupling cleanup is complete. Claim only Phase
6 if all acceptance criteria pass.
