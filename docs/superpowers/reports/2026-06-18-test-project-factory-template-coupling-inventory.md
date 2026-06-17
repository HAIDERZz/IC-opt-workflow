# Test Project Factory Template Coupling Inventory

Date: 2026-06-18
Phases: 1 (factory + guard + first wave) and 2 (real-run handoff + metric-result contracts)

This inventory records the state of direct `create_project_from_template()` usage
across `tests/` after Phases 1-2 of the Test Project Factory and Template Coupling
Cleanup. The generic factory (`tests/project_factory.py`) and the coupling guard
(`tests/test_template_coupling_guard.py`) are in place. Phase 1 migrated the files
that are genuinely decoupled from circuit-specific template contents; Phase 2
migrated the real-run handoff and metric-result contract tests by deriving
incidental metric names from generated request files rather than hardcoding them.
Remaining coupled files are explicitly deferred.

## Status summary

- Generic factory: `tests/project_factory.py` (creates a valid, template-independent
  project; verified by `tests/test_project_factory.py`).
- Coupling guard: `tests/test_template_coupling_guard.py` (fails on any
  non-allowlisted direct usage of `create_project_from_template`).
- `create_project_from_template()` remains the product/template API and is untouched.

## Phase 2 status

Migrated away from direct `create_project_from_template()` usage:

- tests/test_result_handoff.py — now uses `create_approved_generic_project()` +
  `prepare_real_run()`; result-handoff setup no longer overlays an `FN/WN/FP/WP`
  template. All `check_real_run()` contract assertions are preserved (30 tests);
  the simulator-setting drift tests still detect real drift against the generic
  factory's `spectre.yaml` (`output_format=psfxl`, `threads_per_run=2`).
- tests/test_metric_results.py — now uses `create_approved_generic_project()` +
  `prepare_real_run()`; expected-issue strings and assertions derive the metric
  name from `metric_extraction_request.json` (via new `_first_metric_name()` /
  `_metric_names()` helpers) instead of hardcoding `rise`; standalone
  `MetricExtractionRequest` model payloads use `metric_gain`; the waveform-export
  manifest uses `VAR_INT`/`VAR_WIDTH` parameters; the malformed-shape test uses
  `not_a_metric_list`. 56 tests preserved; no assertion was weakened.

Both files were removed from `ALLOWED_TEMPLATE_CALLERS`.

### Scope note (test_cli.py)

Deleting `TEMPLATE_TEXT` from `tests/test_metric_results.py` (Phase 2 plan Task 3
Step 2) exposed a latent cross-test coupling: `tests/test_cli.py` imported
`TEMPLATE_TEXT` from `tests.test_metric_results` for its intentionally
template-based CLI test (`test_cli_check_metric_results_passes_for_valid_fake_ocean_results`,
which drives `hermes-workflow init` to materialize the release template). To keep
the full suite green without re-introducing circuit-specific content into the
migrated file, `tests/test_cli.py` was given its own module-level `TEMPLATE_TEXT`
(matching the convention every other test file already follows) and the
cross-test import was trimmed to the three still-shared helpers
(`_load_json`, `_write_result_manifest`, `_write_metric_result_manifest`). This is
the only change outside the original four-file scope; it is behavior-preserving
(`test_cli.py` remains template-based; it is not migrated).

## Migrated in Phase 1

These files no longer call `create_project_from_template()` and were removed from
`ALLOWED_TEMPLATE_CALLERS`:

- tests/test_health.py — needed only "a valid project"; assertions are
  project/variable/metric-name agnostic. Uses `create_generic_project(tmp_path)`.
- tests/test_optimizer_flow.py — the single usage
  (`test_optimize_project_dry_orchestration_uses_config_turbo_strategy_backend`)
  drives a fully mocked `optimize_project(..., dry_orchestration=True)` flow and
  asserts only on backend/strategy routing. Uses `create_generic_project(tmp_path)`.

## Intentionally template-based (do not migrate)

These tests intentionally depend on the packaged release template:
`tests/test_package.py` calls `create_project_from_template()` directly;
`tests/test_cli.py` drives `hermes-workflow init`, which materializes the release
template through the CLI (no direct call). Neither should be migrated to the
generic factory.

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

- tests/test_next_real_run.py — asserts deterministic optimizer-init candidate
  `parameters == {"FN":"11","FP":"11","WN":"0.3u","WP":"2.9u"}` (4 variables) plus
  the `rise/fall/DC` metric result manifest.
- tests/test_real_run.py — asserts `manifest["project_name"] == "bridge_test_inv"`,
  candidate `{"FN":"2","WN":"0.3u","FP":"2","WP":"0.3u"}`, rendered `"FN=2"`, and
  `set(request_metrics) == {"rise","fall","DC"}`.
- tests/test_real_run_recovery.py — same `FN/WN/FP/WP` template + `rise/fall/DC`
  manifests + manual retry `parameters {"FN":...}`.
- tests/test_approvals.py (optional per plan) — 13 call sites with packaging +
  approval setup; deferred to a focused wave rather than a large edit.

## Remaining migration waves

### Real-run and metric-handoff contracts (closest, lowest-risk next)

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

## Verification

### Phase 2

- `pytest tests/test_result_handoff.py -q` -> `30 passed`
- `pytest tests/test_metric_results.py -q` -> `56 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py -q` -> `4 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py -q` -> `102 passed`
- `pytest -q` -> `1197 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|FN|WN|FP|WP` over `tests/test_result_handoff.py tests/test_metric_results.py` -> no matches
- grep `"rise"` over `tests/test_metric_results.py` -> no matches

### Phase 1 (historical)

- `pytest tests/test_project_factory.py -q` -> `3 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_metric_results.py tests/test_next_real_run.py tests/test_real_run.py tests/test_result_handoff.py tests/test_real_run_recovery.py -q` -> `199 passed`
- `pytest -q` -> `1197 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
