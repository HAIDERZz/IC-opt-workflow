# Test Project Factory Template Coupling Phase 9 Spec

Date: 2026-06-18

## Objective

Decouple the local fix-run orchestration test file from the packaged release template:

- `tests/test_fix_run_flow.py`

This phase should use the generic test project factory's existing `workflow_mode="fix_run"` support instead of hand-writing an inverter-style template and fixed points. The test behavior should remain the same: local fix-run orchestration, approval wiring, report fields, waveform gates, cadence cshrc propagation, and child-level parallelism must all stay covered.

## Scope

Allowed files to modify:

- `tests/test_fix_run_flow.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `src/hermes_workflow/fix_run_flow.py`
- `src/hermes_workflow/fix_run_models.py`

No other production, test, release, prompt, plan, graph, or generated-output files may be modified unless the implementation discovers a real blocker and stops for review first.

## Requirements

### 1. Fix-Run Flow Test Migration

`tests/test_fix_run_flow.py` must stop importing and calling `create_project_from_template()`.

Required behavior:

- Create fix-run projects through `create_generic_project(..., workflow_mode="fix_run")`.
- Remove the local inverter `TEMPLATE_TEXT` and `_write_template()` helper.
- Derive fixed-point candidate ids and parameters from `config/fixed_points.yaml`.
- Do not hardcode old variable names: `FN`, `WN`, `FP`, `WP`.
- Do not hardcode old project names such as `fix_run_test_inv` or `bridge_test_inv`.
- Keep the single-point helper and two-point helper local to the file.
- Preserve all existing fix-run behavior assertions:
  - product doctor is called when license check is required.
  - one fixed point creates one candidate request with the configured candidate id and parameters.
  - two fixed points allocate `real_001` and `real_002`.
  - child adapter path is invoked.
  - `reports/fix_run_report.json` is written.
  - no optimizer state is created by fix-run.
  - `FixRunReport` / `FixRunPointReport` structure is returned.
  - waveform manifest and CSV paths are collected.
  - fix-run approval, not optimizer approval, is used.
  - adapter failures and missing waveform CSV fail the parent report.
  - `cadence_cshrc` reaches the adapter.
  - `parallel_jobs > 1` runs children concurrently.
  - `parallel_jobs == 1` keeps child runs serial.
  - one failed child is preserved and fails the parent report.
- Keep `cg_nf`, `tt`, `ss`, `ff`, `nf_pnoise`, and waveform path names where they are testing child-run or waveform-export behavior rather than old optimizer-template coupling.

### 2. Coupling Guard

Remove this file from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/test_fix_run_flow.py`

The allowlist count should shrink from 12 to 11.

### 3. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 9.
- Add a `Phase 9 status` section before the Phase 8 section.
- State that `tests/test_fix_run_flow.py` was migrated.
- State that the allowlist changed from 12 to 11.
- Remove `tests/test_fix_run_flow.py` from the remaining migration waves.
- Add exact verification results after running the commands in this spec.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_multi_testbench_aggregation.py`
- `tests/real_run_smoke_helpers.py`
- Backend tests
- Remote tests
- Adapter tests
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

Do not commit, tag, push, or publish. The user will ask separately when this phase should be committed.

## Required Verification

Run these commands from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|fix_run_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_fix_run_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_fix_run_flow\|tests.test_fix_run_flow" tests || true
```

Expected baseline before migration:

- `tests/test_fix_run_flow.py`: `17 passed`
- Cross-import grep: only `tests/test_template_coupling_guard.py`
- Release checkout: clean

Expected after migration:

- `tests/test_fix_run_flow.py`: `17 passed`
- Guard: `1 passed`
- Target plus guard: `18 passed`
- Phase 1-9 regression group: about `339 passed`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes
- `git diff --check` is clean
- Release checkout remains clean
- Drift grep over `tests/test_fix_run_flow.py` prints no matches
- Cross-import grep prints no source-level dependencies on `tests/test_fix_run_flow.py`

If any count differs because a prior phase changed collection counts, record the real count and explain the reason in the final report.

## Stop Conditions

Stop and report instead of widening scope if:

- A production-code change appears necessary.
- `tests/project_factory.py` needs another behavior change.
- Any test outside the three allowed files must be edited.
- `tests/real_run_smoke_helpers.py`, backend tests, remote tests, adapter tests, or multi-testbench aggregation tests become part of the fix.
- Full-suite failures appear outside the touched surface and cannot be tied directly to this migration.
