# Claude Prompt: Phase 5 Netlist and Dry-Run Preflight Template Decoupling

You are working in:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Do not touch the release checkout:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`

Do not edit or stage `graphify-out/`.
Do not commit, tag, push, or publish.

## Goal

Implement Phase 5 of the Test Project Factory and Template Coupling Cleanup:
migrate the netlist and dry-run preflight tests away from the packaged release
template.

This phase covers exactly:

- `tests/test_netlists.py`
- `tests/test_dry_run.py`
- new helper `tests/netlist_dry_run_helpers.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Read First

Read these files before editing:

- `docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase5-netlist-dry-run-spec.md`
- `docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase5-netlist-dry-run-plan.md`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- `tests/project_factory.py`
- `tests/test_template_coupling_guard.py`
- `tests/test_netlists.py`
- `tests/test_dry_run.py`
- `src/hermes_workflow/netlists.py`
- `src/hermes_workflow/dry_run.py`

If codegraph is available, use it to inspect `prepare_netlist`,
`render_corner_netlist_template`, and `run_dry_run`. If graphify is available and
`graphify-out/` exists, use it for orientation only. Source files and tests are
authoritative.

## Strict Scope

You may modify:

- `tests/netlist_dry_run_helpers.py` (new)
- `tests/test_netlists.py`
- `tests/test_dry_run.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

If any other file appears necessary, stop and report options before editing it.
Do not modify production source in this phase.
Do not modify packaged templates or examples.

## Required Behavior

1. Remove direct `create_project_from_template()` usage from
   `tests/test_netlists.py` and `tests/test_dry_run.py`.
2. Use `tests/project_factory.py` through a small helper module:
   `tests/netlist_dry_run_helpers.py`.
3. Remove old release-template strings from the target files and helper:
   - `bridge_test_inv`
   - `FN`
   - `WN`
   - `FP`
   - `WP`
   - `TEMPLATE_TEXT`
4. Preserve netlist behavior coverage:
   - top-level parameter templating,
   - continuation-line templating,
   - no templating of instance/subckt assignments,
   - missing exported input,
   - missing approved variable,
   - duplicate approved variable,
   - whitespace-unit handling,
   - fail-closed subckt parameter detection,
   - pure corner rendering,
   - multi-testbench corner template generation.
5. Preserve dry-run behavior coverage:
   - lower-bound candidate rendering,
   - missing template,
   - missing/unexpected/malformed placeholders,
   - stale render cleanup,
   - false-but-evaluable constraint,
   - no optimizer artifacts,
   - render write failure.
6. Remove `tests/test_netlists.py` and `tests/test_dry_run.py` from
   `ALLOWED_TEMPLATE_CALLERS`; allowlist count should shrink from 18 to 16.
7. Update the inventory report with Phase 5 status and exact verification results.

## Implementation Guidance

Use generated variable names from `config/variables.yaml`. Do not introduce a new
scattered hardcoded circuit shape. It is acceptable for pure
`render_corner_netlist_template()` tests to use arbitrary generic names like `F`,
`W`, `temperature`, or `vdd`, because those tests are not exercising the packaged
release template.

For dry-run constraint tests, parse `config/metrics.yaml` and mutate the first
constraint to a false but valid value such as `0 W`. Keep the existing assertion
that dry-run passes because the constraint is evaluable.

For multi-testbench netlist tests, set `testbench: tb1` on all generic metrics by
parsing and writing `config/metrics.yaml`, rather than text-replacing old metric
formula names.

## Verification Commands

Run focused checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_netlists.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_dry_run.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Run target and regression checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_netlists.py tests/test_dry_run.py -q
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
  tests/test_netlists.py tests/test_dry_run.py tests/netlist_dry_run_helpers.py || true
grep -R -n "from tests.test_netlists\|from tests.test_dry_run" tests || true
```

Expected:

- No old-template matches in target files or helper.
- No cross-test imports from the migrated files.
- Guard passes with allowlist count 16.
- Release checkout remains clean.

## Final Report Required

Report:

- files created and modified,
- migration summary for `tests/test_netlists.py`,
- migration summary for `tests/test_dry_run.py`,
- helper API created,
- guard allowlist count before and after,
- exact verification command results,
- drift grep results,
- release checkout status,
- confirmation that `graphify-out/` was untouched,
- any deferred work.

Do not claim the broader template-coupling cleanup is complete. Claim only Phase
5 if all acceptance criteria pass.
