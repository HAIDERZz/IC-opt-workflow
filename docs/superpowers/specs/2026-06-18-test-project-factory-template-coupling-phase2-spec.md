# Test Project Factory Template Coupling Phase 2 Spec

## Problem

Phase 1 created `tests/project_factory.py`, proved it with
`tests/test_project_factory.py`, and added
`tests/test_template_coupling_guard.py` to make direct
`create_project_from_template()` usage explicit.

The allowlist is still intentionally large. Two low-risk files remain coupled to
the release template even though they test real-run handoff and metric-result
contracts rather than packaged template behavior:

- `tests/test_result_handoff.py`
- `tests/test_metric_results.py`

Both files currently build projects with `create_project_from_template()`, then
overlay or assert template-specific names such as `bridge_test_inv`,
`FN/WN/FP/WP`, and `rise`.

This keeps unrelated handoff-contract tests sensitive to release-template edits.

## Goal

Migrate exactly these two files to the generic project factory:

- `tests/test_result_handoff.py`
- `tests/test_metric_results.py`

After this phase:

- Neither file should import or call `create_project_from_template()`.
- Neither file should need inverter-specific template overlays.
- Both files should use the generic factory project shape from
  `tests/project_factory.py`.
- `tests/test_template_coupling_guard.py` should remove both files from
  `ALLOWED_TEMPLATE_CALLERS`.
- The Phase 1 inventory should be updated to record the Phase 2 migration.

## Non-Goals

Do not:

- Change product runtime behavior under `src/hermes_workflow/`.
- Touch release checkout `../ic-auto-opt-workflow-v0.1`.
- Touch or stage `graphify-out/`.
- Migrate optimizer backend tests in this phase.
- Migrate remote tests in this phase.
- Migrate `tests/test_real_run.py`, `tests/test_next_real_run.py`, or
  `tests/test_real_run_recovery.py` in this phase.
- Add a new factory abstraction unless the two target files both need it.
- Change packaged examples or release templates.

## Scope

### In Scope

1. `tests/test_result_handoff.py`
   - Replace its template-based project helper with
     `create_approved_generic_project()`.
   - Remove `create_project_from_template`, `build_execution_package`,
     `decide_first_real_run`, and `write_pass_reports` imports if they become
     unused.
   - Remove the `FN/WN/FP/WP` template overlay if the generic factory template is
     sufficient.
   - Preserve all result-handoff contract assertions.

2. `tests/test_metric_results.py`
   - Replace `_create_ready_project()` with a generic factory based setup.
   - Remove hardcoded `"rise"` expectations by deriving the first requested
     metric name from `metric_extraction_request.json`.
   - Keep `_default_metric_entries()` request-driven.
   - Preserve malformed-manifest, identity-drift, scalar validation, path-safety,
     and waveform-export tests.

3. `tests/test_template_coupling_guard.py`
   - Remove `tests/test_result_handoff.py`.
   - Remove `tests/test_metric_results.py`.

4. `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
   - Add a Phase 2 section.
   - Move the two files from deferred status to migrated status.
   - Keep all other deferrals intact.

### Out of Scope

Leave these files allowlisted for later phases:

- `tests/test_next_real_run.py`
- `tests/test_real_run.py`
- `tests/test_real_run_recovery.py`
- `tests/test_approvals.py`
- backend, remote, adapter, and retention files already listed in the inventory.

## Design Constraints

1. The production API `create_project_from_template()` remains healthy and
   unchanged. This phase only removes inappropriate test-fixture usage.
2. The generic factory remains template-independent. Do not change it to imitate
   the current release example.
3. Test assertions should use project data produced by the generic project when
   the name is not the behavior under test.
4. If an expected issue string includes a metric name, derive the metric name
   from the request file:

   ```python
   def _first_metric_name(project_dir: Path) -> str:
       request = _load_json(
           project_dir
           / "runs"
           / "real"
           / "real_001"
           / "metric_extraction_request.json"
       )
       return request["metrics"][0]["name"]
   ```

5. The guard allowlist must shrink monotonically. Do not add new files to the
   allowlist in this phase.
6. Do not weaken assertions to make migration easier. Replace circuit names with
   generic names only where the circuit name was incidental.

## Acceptance Criteria

Phase 2 is complete when all of the following are true:

- `tests/test_result_handoff.py` has no `create_project_from_template` reference.
- `tests/test_metric_results.py` has no `create_project_from_template` reference.
- `tests/test_template_coupling_guard.py` no longer allowlists either target file.
- Both target files pass independently:

  ```bash
  PYTHONPATH=src ./.venv/bin/python -m pytest \
    tests/test_result_handoff.py tests/test_metric_results.py -q
  ```

- Factory and guard tests still pass:

  ```bash
  PYTHONPATH=src ./.venv/bin/python -m pytest \
    tests/test_project_factory.py tests/test_template_coupling_guard.py -q
  ```

- The broader first-wave safety suite passes:

  ```bash
  PYTHONPATH=src ./.venv/bin/python -m pytest \
    tests/test_project_factory.py \
    tests/test_template_coupling_guard.py \
    tests/test_health.py \
    tests/test_optimizer_flow.py \
    tests/test_result_handoff.py \
    tests/test_metric_results.py -q
  ```

- Full suite passes:

  ```bash
  PYTHONPATH=src ./.venv/bin/python -m pytest -q
  ```

- Ruff passes:

  ```bash
  PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
  ```

- Whitespace check is clean:

  ```bash
  git diff --check
  ```

- Release checkout remains clean:

  ```bash
  git -C ../ic-auto-opt-workflow-v0.1 status --short
  ```

## Expected End State

The Phase 2 diff should be limited to:

- `tests/test_result_handoff.py`
- `tests/test_metric_results.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

No production files should change in this phase.
