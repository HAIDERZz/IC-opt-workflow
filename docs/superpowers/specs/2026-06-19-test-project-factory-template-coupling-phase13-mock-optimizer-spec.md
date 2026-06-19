# Test Project Factory Template Coupling Phase 13 Spec

Date: 2026-06-19

## Objective

Decouple `tests/test_mock_optimizer.py` from the packaged release template.

This phase targets the remaining direct `create_project_from_template()` usage in
the mock optimizer test module. `mock_optimizer.py` is already generic: candidate
generation reads `VariablesConfig`, metric generation hashes declared metric
names, and objective/constraint evaluation reads `MetricsConfig`. The tests
should prove that generic behavior without depending on the old inverter
template.

## Scope

Allowed files to modify:

- `tests/test_mock_optimizer.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `src/hermes_workflow/mock_optimizer.py`
- `src/hermes_workflow/validate.py`
- `src/hermes_workflow/schemas.py`

No production, release, prompt, plan, graph, or generated-output files may be
modified unless the implementation discovers a real blocker and stops for review.

## Requirements

### 1. Direct Template Call Removal

`tests/test_mock_optimizer.py` must stop importing and calling
`create_project_from_template()`.

Required behavior:

- Use `create_generic_project()` from `tests/project_factory.py` for project-backed
  tests.
- Do not use another circuit-specific project or copied template text.
- Add small helpers to derive variable names from `config/variables.yaml` and
  candidate parameters from those names.
- Use structured YAML mutation for tests that need a small variable grid.

The migrated file should not contain these old packaged-template tokens:

- `create_project_from_template`
- `bridge_test_inv`
- `FN`
- `WN`
- `FP`
- `WP`
- `rise`
- `fall`
- `DC`

Use neutral names for schema-only tests, for example `PARAM_A`, `PARAM_B`,
`metric_a`, `metric_b`, `metric_c`, or domain-neutral names already present such
as `delay` and `gain`.

### 2. Preserve Schema and Helper Coverage

Preserve existing coverage:

- `LedgerRow` model validation, extra-field rejection, simulation-status
  validation, real-constraint-fail acceptance, bool-as-int rejection.
- `BestCandidate` model validation and bool-as-int rejection.
- `OptimizerState` validation, status validation, null best candidate, and
  bool-as-int rejection.
- `evaluate_objective()` arithmetic, single metric, literals, negation, division,
  power, modulo, safe math functions, unknown metric rejection, unsupported
  function rejection, unsupported literal rejection, syntax error rejection, and
  maximize-is-call-site-responsibility behavior.
- Integer/continuous grid helpers.
- `_deduplicate()`.
- `write_ledger_row()`, `write_optimizer_state()`, `write_best_candidate()`, and
  `write_health_check()`.

These schema/helper tests do not need real project setup. Convert their fixtures
to neutral names instead of deriving from `create_generic_project()`.

### 3. Preserve Project-Backed Mock Optimizer Coverage

Project-backed tests must use the generic factory and keep behavior assertions:

- `generate_candidates()` returns requested counts.
- Sobol/random/Latin-hypercube initialization remains reproducible.
- Candidate values stay on the declared grid.
- Candidate generation deduplicates and refills.
- `compute_mock_metrics()` is deterministic for same params, changes for
  different params, returns all declared metrics, and returns positive floats.
- `evaluate_constraints()` works against project metrics and returns false when a
  declared metric is missing.
- `run_mock_optimization()` writes ledger/state/best/health artifacts.
- Run state completes with expected evaluation counts and project name.
- Max-evaluation and seed overrides are respected.
- Mock ledger rows remain valid and omit real-result fields.

All variable and metric assertions in project-backed tests must be derived from
the generic project config or runtime output.

### 4. Coupling Guard

Remove this file from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/test_mock_optimizer.py`

The allowlist count should shrink from 8 to 7.

The remaining allowlist should be:

- `tests/test_package.py`
- `tests/test_native_turbo.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_spectre_ocean_adapter.py`

### 5. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 13.
- Add a `Phase 13 status` section before Phase 12.
- State that `tests/test_mock_optimizer.py` was migrated.
- State that the allowlist changed from 8 to 7.
- Remove `tests/test_mock_optimizer.py` from the remaining migration waves.
- Add exact verification results.

Also remove or update the stale Phase 12 "known remaining issue" text if it still
claims the waveform sibling is failing; Phase 12b fixed that and full suite is
green.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_native_turbo.py`
- `tests/test_openbox_backend.py`
- remote/adapter tests
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`
- Existing specs/plans/prompts

Do not commit, tag, push, or publish. The user will ask separately when this
phase should be committed.

## Required Verification

Run from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_mock_optimizer.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_mock_optimizer\|tests.test_mock_optimizer" tests || true
```

Expected baseline before migration:

- `tests/test_mock_optimizer.py`: `83 passed`
- Full suite: `1194 passed, 13 warnings`
- Release checkout: clean

Expected after migration:

- `tests/test_mock_optimizer.py`: `83 passed`
- Guard: `1 passed`
- Target plus guard: `84 passed`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes.
- `git diff --check` is clean.
- Release checkout remains clean.
- Drift grep over `tests/test_mock_optimizer.py` prints no matches.
- Cross-import grep prints no source-level consumers except the guard before it
  is updated; after guard update it should print no source-level matches.

If counts differ, record the actual counts and explain why.

## Stop Conditions

Stop and report instead of widening scope if:

- Production code appears necessary.
- `tests/project_factory.py` needs another behavior change.
- Any test outside the three allowed files must be edited.
- Full-suite failures appear outside this phase and cannot be tied directly to
  the migration.
