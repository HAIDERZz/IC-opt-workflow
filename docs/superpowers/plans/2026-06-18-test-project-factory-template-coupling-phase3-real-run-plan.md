# Phase 3 Plan: Real-Run Package and Recovery Test Decoupling

Date: 2026-06-18
Spec:
`docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase3-real-run-spec.md`

## Task 0: Baseline and Scope Audit

1. Confirm the working tree before editing:
   `git status --short`.
2. Confirm the release checkout is untouched:
   `git -C ../ic-auto-opt-workflow-v0.1 status --short`.
3. Inspect the target files and current allowlist:
   - `tests/test_real_run.py`
   - `tests/test_next_real_run.py`
   - `tests/test_real_run_recovery.py`
   - `tests/test_template_coupling_guard.py`
4. Audit external imports of target-file helpers:
   - `tests/test_cli.py`
   - `tests/test_candidate_injection_real_run.py`
   - `tests/test_optimizer_loop.py`
   - `tests/test_optimizer_suggestion.py`
5. If codegraph is available, use it to inspect callers/callees for the target
   helper functions. If graphify is available and `graphify-out/` exists, use it
   as an orientation aid only; source files and tests are authoritative.

## Task 1: Migrate `tests/test_real_run.py`

1. Replace `_create_project()` / `_approve_project()` setup with the generic
   project factory.
2. Remove the local `TEMPLATE_TEXT` overlay and any manual release-template
   netlist setup.
3. Preserve tests for:
   - default testbench/corner behavior,
   - real-run manifest contents,
   - candidate metadata,
   - rendered netlist without unresolved placeholders,
   - metric extraction request contents,
   - invalid config/state failure paths.
4. Replace release-template assertions with config-derived or manifest-derived
   assertions:
   - project name from `project_dir.name`,
   - candidate parameter names from `candidate.json` or `variables.yaml`,
   - metric names from `metric_extraction_request.json`.
5. Run `pytest tests/test_real_run.py -q`.

## Task 2: Migrate `tests/test_next_real_run.py`

1. Replace `_create_ready_project()` with a generic approved project plus
   `prepare_real_run()`.
2. Update `_write_metric_result_manifest()` to emit succeeded metrics based on
   `metric_extraction_request.json`.
3. Update `_record_real_001()` so it records a generic successful first run.
4. Preserve next-run contracts:
   - refusing unresolved runs,
   - invalid ledger handling,
   - optimizer-state drift detection,
   - B-09 recorded-observation-count behavior,
   - `real_002` package creation,
   - duplicate/override protections.
5. Replace exact old four-variable candidate assertions with generic assertions
   tied to the generated factory project. It is acceptable to assert exact values
   if they come from the generic factory contract rather than the release
   template.
6. Run:
   - `pytest tests/test_next_real_run.py -q`
   - `pytest tests/test_candidate_injection_real_run.py tests/test_optimizer_loop.py tests/test_optimizer_suggestion.py -q`
7. If imported helper behavior breaks those consumer files, keep the helper API
   compatible when practical. If compatibility would make the migrated file
   carry old template text, move the helper into the consumer or a small shared
   helper and document the scope expansion.

## Task 3: Migrate `tests/test_real_run_recovery.py`

1. Replace `_create_ready_project()` with a generic approved project plus
   `prepare_real_run()`.
2. Update result and metric-result manifest helpers so they derive metric names
   from the current run request.
3. Convert failed-run and retry payloads to generic factory variables.
4. Preserve recovery contracts:
   - failed result detection,
   - retry package generation,
   - retry candidate metadata,
   - recovery report status,
   - state/ledger preservation,
   - failure issue propagation.
5. Run `pytest tests/test_real_run_recovery.py -q`.
6. Run `pytest tests/test_cli.py -q`. If CLI imports from this file break, apply
   the smallest helper-localization change needed and record it in the inventory.

## Task 4: Shrink Guard and Update Inventory

1. Remove these three files from `ALLOWED_TEMPLATE_CALLERS`:
   - `tests/test_real_run.py`
   - `tests/test_next_real_run.py`
   - `tests/test_real_run_recovery.py`
2. Confirm the guard allowlist count is 18.
3. Update
   `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
   with:
   - Phase 3 status,
   - files migrated,
   - exact scope expansions, if any,
   - remaining migration waves,
   - exact verification commands and results.

## Task 5: Verification

Run the focused checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_next_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_run_recovery.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_cli.py tests/test_candidate_injection_real_run.py tests/test_optimizer_loop.py tests/test_optimizer_suggestion.py tests/test_template_coupling_guard.py -q
```

Run the phase regression group:

```bash
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
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py || true
grep -n '"rise"\| "fall"\| "DC"' \
  tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py || true
grep -R -n "from tests.test_real_run_recovery\|from tests.test_next_real_run\|from tests.test_real_run" tests || true
```

Expected result:

- The first two greps show no release-template-specific matches in target files.
- The import grep may show intentional helper imports, but every remaining import
  must be explained by passing consumer tests and documented in the inventory.

## Stop Conditions

Stop and report instead of expanding scope if:

- a production source change appears necessary,
- a target file requires a large behavior rewrite unrelated to template coupling,
- a consumer file needs more than a small helper-localization edit,
- full-suite failures reveal a separate existing product bug.
