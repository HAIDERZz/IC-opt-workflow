# Test Project Factory Template Coupling Inventory

Date: 2026-06-18
Phase: 1 (factory + guard + first migration wave)

This inventory records the state of direct `create_project_from_template()` usage
across `tests/` after Phase 1 of the Test Project Factory and Template Coupling
Cleanup. The generic factory (`tests/project_factory.py`) and the coupling guard
(`tests/test_template_coupling_guard.py`) are in place. Phase 1 migrates the files
that are genuinely decoupled from circuit-specific template contents and explicitly
defers files that still depend on them.

## Status summary

- Generic factory: `tests/project_factory.py` (creates a valid, template-independent
  project; verified by `tests/test_project_factory.py`).
- Coupling guard: `tests/test_template_coupling_guard.py` (fails on any
  non-allowlisted direct usage of `create_project_from_template`).
- `create_project_from_template()` remains the product/template API and is untouched.

## Migrated in this wave

These files no longer call `create_project_from_template()` and were removed from
`ALLOWED_TEMPLATE_CALLERS`:

- tests/test_health.py — needed only "a valid project"; assertions are
  project/variable/metric-name agnostic. Uses `create_generic_project(tmp_path)`.
- tests/test_optimizer_flow.py — the single usage
  (`test_optimize_project_dry_orchestration_uses_config_turbo_strategy_backend`)
  drives a fully mocked `optimize_project(..., dry_orchestration=True)` flow and
  asserts only on backend/strategy routing. Uses `create_generic_project(tmp_path)`.

## Intentionally template-based (do not migrate)

These tests verify template copy/packaging/init behavior and must keep using
`create_project_from_template()`:

- tests/test_package.py — template tree, packaged resources, `init` semantics.
- tests/test_cli.py — `hermes-workflow init` product behavior.

## Deferred from the proposed first wave (circuit-specific coupling)

The plan proposed these as a first wave, but reading the source showed each is
coupled to circuit-specific template contents (4 variables `FN/WN/FP/WP`, 3
metrics `rise/fall/DC`, project name `bridge_test_inv`, and/or specific optimizer
initialization candidate values). The generic factory deliberately produces exactly
2 variables / 2 metrics, so it cannot serve these tests without a per-test rewrite
of templates, fake manifests, and assertions. Per spec design principle 6 and plan
Task 3 Step 5 ("do not change tests that intentionally exercise four-variable
optimizer behavior; leave those for a later wave"), they are deferred and remain in
the guard allowlist.

- tests/test_metric_results.py — couples to the template's example metric name
  `rise` (the generic factory uses `metric_gain`/`metric_power`): ~17 references
  keyed on `rise`, including `persisted["metrics"]["rise"]["status"]`,
  `"requested metric is missing from metric results: rise"`,
  `"duplicate metric in metric results: rise"`, and a parametrize block of
  `"metric rise ..."` expected-issue strings. Migration requires renaming the
  example metric throughout. (This file does not use a `rise`/`fall`/`DC` triple;
  that coupling belongs to the real-run files below — `test_next_real_run.py`,
  `test_real_run.py`, `test_real_run_recovery.py`.)
- tests/test_next_real_run.py — asserts deterministic optimizer-init candidate
  `parameters == {"FN":"11","FP":"11","WN":"0.3u","WP":"2.9u"}` (4 variables) plus
  the `rise/fall/DC` metric result manifest.
- tests/test_real_run.py — asserts `manifest["project_name"] == "bridge_test_inv"`,
  candidate `{"FN":"2","WN":"0.3u","FP":"2","WP":"0.3u"}`, rendered `"FN=2"`, and
  `set(request_metrics) == {"rise","fall","DC"}`.
- tests/test_result_handoff.py — overlays an `FN/WN/FP/WP` template then calls
  `prepare_real_run`, which would reject the template against a `VAR_INT/VAR_WIDTH`
  config. Assertions themselves are largely name-agnostic, so this is the closest
  next candidate: migrating it only requires updating the module template overlay.
- tests/test_real_run_recovery.py — same `FN/WN/FP/WP` template + `rise/fall/DC`
  manifests + manual retry `parameters {"FN":...}`.
- tests/test_approvals.py (optional per plan) — 13 call sites with packaging +
  approval setup; deferred to a focused wave rather than a large edit.

## Remaining migration waves

### Real-run and metric-handoff contracts (closest, lowest-risk next)

- tests/test_result_handoff.py — name-agnostic assertions; needs template overlay update only.
- tests/test_metric_results.py — needs 2-metric rewrite of example metrics.
- tests/test_next_real_run.py — needs candidate-value assertions generalized.
- tests/test_real_run.py — needs project-name, candidate, and metric-name generalization.
- tests/test_real_run_recovery.py — needs template + metric + retry-parameter generalization.

### Approvals and packaging

- tests/test_approvals.py
- tests/test_optimizer_task_package.py
- tests/test_run_retention.py
- tests/test_netlists.py
- tests/test_dry_run.py
- tests/test_fix_run_flow.py
- tests/test_multi_testbench_aggregation.py
- tests/test_optimizer_progress_state.py
- tests/real_run_smoke_helpers.py

### Optimizer backends (deepest coupling)

- tests/test_openbox_backend.py
- tests/test_native_turbo.py
- tests/test_mock_optimizer.py

### Remote and adapter flows

- tests/test_remote_optimizer_flow.py
- tests/test_remote_fix_run_flow.py
- tests/test_remote_spectre_ocean.py
- tests/test_spectre_ocean_adapter.py
- tests/test_real_result_record.py

## How to continue

1. Pick one file from a wave above.
2. Replace its `create_project_from_template(...)` usage with the appropriate
   factory helper (`create_generic_project` / `create_packaged_generic_project` /
   `create_approved_generic_project`), updating any circuit-specific template
   overlays, fake manifests, and name-based assertions.
3. Remove the file from `ALLOWED_TEMPLATE_CALLERS`.
4. Run `tests/test_template_coupling_guard.py`, the file's tests, and the full
   suite before the next file.

The allowlist must shrink monotonically; the guard prevents any new unreviewed
direct usage from being introduced.

## Verification (Phase 1)

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_project_factory.py -q` -> `3 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_metric_results.py tests/test_next_real_run.py tests/test_real_run.py tests/test_result_handoff.py tests/test_real_run_recovery.py -q` -> `199 passed`
- `PYTHONPATH=src .venv/bin/python -m pytest -q` -> `1197 passed`
- `PYTHONPATH=src .venv/bin/python -m ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
