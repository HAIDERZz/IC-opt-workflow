# Test Project Factory Template Coupling Phase 8 Spec

Date: 2026-06-18

## Objective

Decouple the remaining local state-maintenance tests from the packaged release template:

- `tests/test_run_retention.py`
- `tests/test_optimizer_progress_state.py`

Both files currently use `create_project_from_template()` only to obtain a valid project tree and a few config files. They should instead use `tests/project_factory.py`, derive incidental variable/metric/project names from generated artifacts, and remain product-behavior equivalent.

## Scope

Allowed files to modify:

- `tests/test_run_retention.py`
- `tests/test_optimizer_progress_state.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `src/hermes_workflow/run_retention.py`
- `src/hermes_workflow/optimizer_progress_state.py`
- `tests/report_helpers.py`

No other source, test, release, prompt, plan, graph, or generated-output files may be modified unless the implementation discovers a real blocker and stops for review first.

## Requirements

### 1. Run Retention Tests

`tests/test_run_retention.py` must stop importing and calling `create_project_from_template()`.

Required behavior:

- Create projects through `create_generic_project()` from `tests.project_factory`.
- Keep all existing run-retention behavior assertions:
  - `load_run_retention_policy()` reads `keep_failed_runs` / `keep_successful_runs` from `config/spectre.yaml`.
  - successful runs are kept or deleted based on `keep_successful_runs`.
  - failed runs are kept or deleted based on `keep_failed_runs`.
  - decision reports keep the required schema fields and values.
  - missing local run directories report `local_action == "missing"`.
  - unsafe run ids are rejected.
  - local deletion failures record `local_action == "failed"` and preserve the issue.
  - local/remote retention merge order preserves local and remote fields.
  - remote issues survive local merge.
- Mutate `config/spectre.yaml` through structured YAML parsing/writing, not string replacement.
- Keep remote runner stubs local to the file; do not introduce new shared helpers for this phase.
- Keep project names incidental. Do not assert on or introduce `bridge_test_inv`.

### 2. Optimizer Progress State Tests

`tests/test_optimizer_progress_state.py` must stop importing and calling `create_project_from_template()`.

Required behavior:

- Create sync-test projects through `create_generic_project()` with explicit project settings:
  - `name="progress_project"`
  - `max_evaluations=10`
  - `batch_size=2`
- Remove the string-replacement helper that edits `max_evaluations: 100`.
- Keep all existing optimizer progress behavior assertions:
  - attempted count is used as current evaluations.
  - failed count equals attempted minus recorded observations.
  - status is `running` when attempts remain under budget.
  - `completed_early=True` produces completed status under budget.
  - existing best candidate id is preserved.
  - status counts match traces.
  - `sync_optimizer_progress_state()` reads optimizer artifacts and writes `state/optimizer_state.json`.
  - existing `started_at_utc` is preserved.
- Derive fake ledger variable and metric names from generated config:
  - variables from `config/variables.yaml`
  - metrics from `config/metrics.yaml`
- Do not hardcode `FN`, `WN`, `FP`, `WP`, `rise`, `fall`, `DC`, or `bridge_test_inv`.
- Pure `build_optimizer_progress_state()` tests may use a local neutral constant such as `PROJECT_NAME = "progress_project"`.

### 3. Coupling Guard

Remove these two files from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/test_run_retention.py`
- `tests/test_optimizer_progress_state.py`

The allowlist count should shrink from 14 to 12.

### 4. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 8.
- Add a `Phase 8 status` section before the Phase 7 section.
- State that `test_run_retention.py` and `test_optimizer_progress_state.py` were migrated.
- State that the allowlist changed from 14 to 12.
- Move both files out of the remaining migration waves.
- Add exact verification results after running the commands in this spec.

## Non-Goals

Do not modify:

- Production code under `src/`
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`
- Existing Phase 8 spec/plan/prompt files once generated
- Backend tests
- Remote tests
- Adapter tests
- `tests/test_fix_run_flow.py`
- `tests/test_multi_testbench_aggregation.py`
- `tests/real_run_smoke_helpers.py`
- `tests/test_package.py`
- `tests/test_cli.py`

Do not commit, tag, push, or publish. The user will ask separately when a phase should be committed.

## Required Verification

Run these commands from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_run_retention.py tests/test_optimizer_progress_state.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_run_retention\|tests.test_run_retention\|from tests.test_optimizer_progress_state\|tests.test_optimizer_progress_state" tests || true
```

Expected baseline before migration:

- Target pair: `28 passed`
- Guard: `1 passed`
- Release checkout: clean

Expected after migration:

- Target pair remains `28 passed`
- Target pair plus guard: `29 passed`
- Phase 1-8 regression group: about `322 passed`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes
- `git diff --check` is clean
- Release checkout remains clean
- Drift grep over the two migrated files prints no matches
- Cross-import grep prints only `tests/test_template_coupling_guard.py` if the guard still names the files before the allowlist edit; after the allowlist edit it should print no source-level dependencies on either migrated module

If any count differs because a prior phase changed collection counts, record the real count and explain the reason in the final report.

## Stop Conditions

Stop and report instead of widening scope if:

- A production-code change appears necessary.
- Any test outside the four allowed files must be edited.
- `tests/project_factory.py` needs another behavior change.
- A remote, adapter, backend, fix-run, or multi-testbench flow becomes part of the fix.
- The full suite fails outside the touched surface and the failure is not directly caused by this migration.
