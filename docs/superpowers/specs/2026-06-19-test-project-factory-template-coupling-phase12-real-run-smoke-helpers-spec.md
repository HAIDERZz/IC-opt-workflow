# Test Project Factory Template Coupling Phase 12 Spec

Date: 2026-06-19

## Objective

Decouple the shared real-run smoke helper module from direct packaged-template
project creation.

This phase targets `tests/real_run_smoke_helpers.py`. That module is imported by
local smoke, optimizer status/finalize/completion/acceptance, OpenBox, native
TuRBO, and remote Spectre/OCEAN tests. Because several consumers use fake
advisors with hardcoded old variable names, Phase 12 is a helper-consumer cluster:
the helper must migrate to the generic factory, and consumers may be adjusted only
where needed to keep their existing behavior green.

## Scope

Allowed files to modify:

- `tests/real_run_smoke_helpers.py`
- `tests/test_local_real_run_smoke.py`
- `tests/test_optimizer_acceptance.py`
- `tests/test_optimizer_completion.py`
- `tests/test_optimizer_finalize.py`
- `tests/test_optimizer_status.py`
- `tests/test_native_turbo.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/real_run_cluster_helpers.py`
- `tests/test_project_factory.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/result_handoff.py`

No production, release, prompt, plan, graph, or generated-output files may be
modified unless the implementation discovers a real blocker and stops for review.

## Requirements

### 1. Helper Migration

`tests/real_run_smoke_helpers.py` must stop importing or calling
`create_project_from_template()`.

Required behavior:

- Replace direct packaged-template setup with `create_approved_generic_project()`
  from `tests/project_factory.py`, followed by `prepare_real_run()`.
- Keep the public helper API stable unless a consumer edit in the allowed scope
  is required:
  - `write_json`
  - `load_json`
  - `create_approved_real_project`
  - `write_fake_result_manifest`
  - `write_fake_metric_result_manifest`
  - `record_checked_run`
  - `ledger_rows`
- Remove `TEMPLATE_TEXT`.
- Remove direct setup imports that become unnecessary:
  - `decide_first_real_run`
  - `build_execution_package`
  - `create_project_from_template`
  - `write_pass_reports`
- Keep `sha256_file`.

### 2. Generic Metric and Candidate Values

The helper must derive metric names and candidate ids from runtime artifacts:

- Candidate id and parameters from `runs/real/<run_id>/candidate.json`.
- Metric names and request metadata from
  `runs/real/<run_id>/metric_extraction_request.json`.

Add or reuse generic helper functions in `tests/real_run_smoke_helpers.py`:

- `variable_names(project_dir) -> tuple[str, str]`
- `metric_names_for_run(project_dir, run_id="real_001") -> tuple[str, str]`
- `default_metric_values(project_dir, run_id="real_001") -> dict[str, float]`
- `advisor_suggestion(project_dir, *, int_value: float, width_value: float) -> dict[str, float]`
- `advisor_batches(project_dir) -> list[list[dict[str, float]]]`

For generic factory defaults:

- Use `VAR_INT` and `VAR_WIDTH` from `config/variables.yaml`.
- Use the two metric names from the metric extraction request.
- Default fake metrics should be feasible for the generic factory constraint:
  first metric around `10.0`, second metric around `1.0e-6`.
- Failed metric cases must still allow `metric_status != "succeeded"` and
  `status != "succeeded"` paths.

Do not replace the old inverter fixture with a new circuit-specific fixture.
The helper should derive names from generated config/artifacts.

### 3. Consumer Compatibility

Consumers that only rely on helper-generated projects should keep their behavior:

- `tests/test_local_real_run_smoke.py`
- `tests/test_optimizer_acceptance.py`
- `tests/test_optimizer_completion.py`
- `tests/test_optimizer_finalize.py`
- `tests/test_optimizer_status.py`
- `tests/test_native_turbo.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_spectre_ocean.py`

Only change consumers when they break because the shared helper now creates a
generic two-variable project. Typical required change:

- Replace fake advisor hardcoded suggestions like
  `{"FN": 2, "WN": 0.2, "FP": 3, "WP": 0.4}` with
  `advisor_suggestion(project_dir, int_value=2, width_value=0.2)` or
  `advisor_batches(project_dir)`.
- Replace helper-backed assertions that expect old metric names with derived
  names from `metric_names_for_run()`.

Do not migrate direct `create_project_from_template()` calls that are unrelated
to `tests/real_run_smoke_helpers.py` in backend/remote files. Those files remain
allowlisted for later phases. Phase 12 shrinks only the helper module from the
guard.

### 4. Coupling Guard

Remove this file from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/real_run_smoke_helpers.py`

The allowlist count should shrink from 9 to 8.

The remaining allowlist should be:

- `tests/test_package.py`
- `tests/test_mock_optimizer.py`
- `tests/test_native_turbo.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_spectre_ocean_adapter.py`

### 5. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 12.
- Add a `Phase 12 status` section before Phase 11.
- State that `tests/real_run_smoke_helpers.py` was migrated.
- State whether any allowed consumer files were touched, and why.
- State that the allowlist changed from 9 to 8.
- Remove `tests/real_run_smoke_helpers.py` from the remaining migration waves.
- Add exact verification results.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`
- Existing specs/plans/prompts

Do not commit, tag, push, or publish. The user will ask separately when this
phase should be committed.

## Required Verification

Run these commands from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|TEMPLATE_TEXT\|parameters FN" tests/real_run_smoke_helpers.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.real_run_smoke_helpers\|tests.real_run_smoke_helpers" tests || true
```

Expected baseline before migration:

- Helper consumer group:
  `166 passed, 13 warnings`
- Full suite:
  `1194 passed, 13 warnings`
- Release checkout:
  clean

Expected after migration:

- Local smoke tests pass.
- Helper consumer group remains around `166 passed, 13 warnings` unless
  collection count changes due a deliberate parametrization cleanup.
- Guard: `1 passed`
- Phase 1-12 regression group passes.
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes.
- `git diff --check` is clean.
- Release checkout remains clean.
- Drift grep over `tests/real_run_smoke_helpers.py` prints no matches.
- Cross-import grep shows only the known consumer files and no new consumers.

If counts differ, record the actual counts and explain why.

## Stop Conditions

Stop and report instead of widening scope if:

- A production-code change appears necessary.
- `tests/project_factory.py` needs another behavior change.
- A consumer outside the allowed scope must be edited.
- The migration requires changing the product meaning of OpenBox/native/remote
  tests instead of only adapting test fixture names.
- Full-suite failures appear outside the touched surface and cannot be tied
  directly to this migration.
