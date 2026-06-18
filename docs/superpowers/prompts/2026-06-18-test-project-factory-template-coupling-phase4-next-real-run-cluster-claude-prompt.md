# Claude Prompt: Phase 4 Next Real-Run Cluster Template Decoupling

You are working in:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Do not touch the release checkout:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`

Do not edit or stage `graphify-out/`.
Do not commit, tag, push, or publish.

## Goal

Implement Phase 4 of the Test Project Factory and Template Coupling Cleanup:
migrate the `test_next_real_run.py` cluster away from old release-template
assumptions.

This phase covers exactly this cluster:

- `tests/test_next_real_run.py`
- `tests/test_candidate_injection_real_run.py`
- `tests/test_optimizer_suggestion.py`
- `tests/test_optimizer_loop.py`

## Read First

Read these files before editing:

- `docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase4-next-real-run-cluster-spec.md`
- `docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase4-next-real-run-cluster-plan.md`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_template_coupling_guard.py`
- `tests/test_next_real_run.py`
- `tests/test_candidate_injection_real_run.py`
- `tests/test_optimizer_suggestion.py`
- `tests/test_optimizer_loop.py`

If codegraph is available, use it to inspect callers/callees for
`_create_ready_project`, `_record_real_001`, and candidate-result helper imports.
If graphify is available and `graphify-out/` exists, use it for orientation only.
Source files and tests are authoritative.

## Strict Scope

You may modify:

- `tests/real_run_cluster_helpers.py` (new)
- `tests/test_next_real_run.py`
- `tests/test_candidate_injection_real_run.py`
- `tests/test_optimizer_suggestion.py`
- `tests/test_optimizer_loop.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

If any other file appears necessary, stop and report options before editing it.
Do not modify production source in this phase.
Do not modify packaged templates or examples.

## Required Behavior

1. Remove direct `create_project_from_template()` usage from
   `tests/test_next_real_run.py`.
2. Remove old release-template strings from all four cluster files:
   - `bridge_test_inv`
   - `FN`
   - `WN`
   - `FP`
   - `WP`
   - `TEMPLATE_TEXT`
   - `"rise"`
   - `"fall"`
   - `"DC"`
3. Create `tests/real_run_cluster_helpers.py` for shared generic setup and fake
   result helpers. Do not keep importing test helpers from `tests.test_next_real_run`.
4. Use `tests/project_factory.py` as the project source of truth.
5. Derive variable and metric names from generated config/manifests/requests
   wherever practical.
6. Preserve existing behavior coverage:
   - next real-run package creation and ledger/state validation,
   - candidate injection validation and duplicate checks,
   - optimizer suggestion initialization/TuRBO behavior,
   - optimizer-loop success and failure statuses.
7. Remove `tests/test_next_real_run.py` from `ALLOWED_TEMPLATE_CALLERS`; the
   allowlist should shrink from 19 to 18.
8. Update the inventory report with Phase 4 status and exact verification results.

## Implementation Guidance

Use a test-only helper module rather than moving old template text into consumer
files. The helper should provide:

- `create_ready_project(tmp_path)`
- `record_real_001(project_dir)`
- `load_json(path)`
- `write_json(path, payload)`
- `variable_names(project_dir)`
- `metric_names_for_run(project_dir, run_id="real_001")`
- `valid_candidate_parameters(project_dir, int_value="3", width_value="0.3u")`
- `missing_candidate_parameters(project_dir)`
- `extra_candidate_parameters(project_dir)`
- `invalid_candidate_cases(project_dir)`
- `write_result_manifest(project_dir, run_id="real_001")`
- `write_metric_result_manifest(project_dir, run_id="real_001")`

The generic factory currently creates two variables and two metrics. Keep any
factory-specific value choices inside the helper so the test files themselves do
not become a new set of scattered stale constants.

For optimizer suggestion tests that need multiple finite observations, generate
unique generic parameter pairs within the factory bounds. Do not assume the old
four-variable candidate shape.

For TuRBO monkeypatch tests, return a raw candidate vector with two values, then
assert the exact formatted generic parameter dictionary produced by the code.

## Verification Commands

Run focused checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_next_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_candidate_injection_real_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_suggestion.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_loop.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Run cluster and regression checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  -q
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
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -n '"rise"\|"fall"\|"DC"' \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -R -n "from tests.test_next_real_run" tests || true
```

Expected:

- No old-template matches in the four cluster files.
- No imports from `tests.test_next_real_run`.
- Guard passes with allowlist count 18.
- Release checkout remains clean.

## Final Report Required

Report:

- files created and modified,
- migration summary for each of the four cluster files,
- helper API created,
- guard allowlist count before and after,
- exact verification command results,
- drift grep results,
- release checkout status,
- confirmation that `graphify-out/` was untouched,
- any deferred work.

Do not claim the broader template-coupling cleanup is complete. Claim only Phase
4 if all acceptance criteria pass.
