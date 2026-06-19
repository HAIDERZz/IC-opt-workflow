# Test Project Factory Template Coupling R1 Native TuRBO Spec

Date: 2026-06-19

## Objective

Decouple `tests/test_native_turbo.py` from the packaged release template while
preserving Native TuRBO behavior coverage.

The production Native TuRBO path is generic: it reads variables, metrics,
optimizer settings, and Spectre parallelism from validated project config. The
tests should prove that behavior without relying on the old inverter template
(`bridge_test_inv`, `FN/WN/FP/WP`, `rise/fall/DC`).

## Current Baseline

At the start of this phase:

- `tests/test_native_turbo.py` passes: `49 passed, 13 warnings`.
- `tests/test_native_turbo.py` directly calls `create_project_from_template()`.
- The guard allowlist has 7 entries after Phase 13:
  - `tests/test_package.py`
  - `tests/test_native_turbo.py`
  - `tests/test_openbox_backend.py`
  - `tests/test_remote_fix_run_flow.py`
  - `tests/test_remote_optimizer_flow.py`
  - `tests/test_remote_spectre_ocean.py`
  - `tests/test_spectre_ocean_adapter.py`

## Scope

Allowed to modify:

- `tests/test_native_turbo.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed to create for phase handoff only if missing:

- `docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r1-native-turbo-spec.md`
- `docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r1-native-turbo-plan.md`
- `docs/superpowers/prompts/2026-06-19-test-project-factory-template-coupling-r1-native-turbo-claude-prompt.md`

Allowed to read:

- `tests/project_factory.py`
- `tests/real_run_smoke_helpers.py`
- `tests/real_run_cluster_helpers.py`
- `tests/test_multi_testbench_aggregation.py`
- `tests/test_requirement_intake.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/validate.py`
- `src/hermes_workflow/schemas.py`

Do not modify:

- `src/`
- `tests/project_factory.py`
- `tests/real_run_smoke_helpers.py`
- `tests/test_openbox_backend.py`
- remote/adapter tests
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

## Requirements

### 1. Remove Direct Packaged Template Usage

`tests/test_native_turbo.py` must stop importing and calling
`create_project_from_template()`.

Use `create_generic_project()` or `create_approved_generic_project()` from
`tests/project_factory.py` for project-backed tests. Existing
`create_approved_real_project()` from `tests.real_run_smoke_helpers` may remain;
it is already generic after Phase 12.

### 2. Preserve Standalone Native TuRBO Unit Coverage

Preserve all current standalone coverage:

- `load_native_turbo_contract()`
- `quantize_candidate()`
- `evaluate_candidate_objective()`
- `NativeTurboRunner`
- duplicate candidate replacement and skip behavior
- workflow-level failure limit
- `NativeTurboBatchRunner`
- `_default_batch_turbo_factory()`
- `_initial_unit_design()` for Sobol/random/Latin-hypercube behavior
- `write_native_turbo_reports()`

Standalone in-memory variable names should use neutral names such as
`VAR_INT` and `VAR_WIDTH`, not `FN/WN`. Standalone metric names may use
domain-neutral names such as `delay/gain` or generic factory names such as
`metric_gain/metric_power`.

### 3. Preserve Project-Backed Optimizer Coverage

Project-backed tests must use generic projects and derive assertions from config
or runtime output:

- compact trace file writing
- batch size and scheduler behavior
- adapter argument pass-through
- optimizer CPU thread limits
- parallel_jobs vs batch_size worker cap
- CLI dispatch for serial and parallel Native TuRBO
- real candidate evaluator and batch evaluator behavior
- run retention integration
- optimizer progress-state sync
- report initialization and runtime thread-limit audit fields

### 4. Preserve Multi-Testbench Requirement Fixtures

Do not migrate tests that intentionally use requirement-intake fixtures such as
`_copy_multi_testbench_requirement_project()`. Those are not packaged-template
calls. However, any hardcoded old variable payload inside those tests must be
derived from the generated project config if it is used as a candidate parameter
payload.

### 5. Use Structured YAML Mutation

Replace string replacement helpers for config mutation with structured YAML
mutation where practical:

- optimizer `batch_size`, `max_evaluations`, `optimizer_cpu_threads`,
  `initialization`
- Spectre `parallel_jobs`, `keep_failed_runs`, `keep_successful_runs`

This avoids assumptions about old template defaults such as `batch_size: 10` and
`parallel_jobs: 10`.

### 6. Coupling Guard

Remove `tests/test_native_turbo.py` from `ALLOWED_TEMPLATE_CALLERS`.

Expected allowlist after this phase:

- `tests/test_package.py`
- `tests/test_openbox_backend.py`
- `tests/test_remote_fix_run_flow.py`
- `tests/test_remote_optimizer_flow.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_spectre_ocean_adapter.py`

Allowlist count: `7 -> 6`.

### 7. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Add an R1/Native TuRBO status section before Phase 13.
- State that `tests/test_native_turbo.py` was migrated.
- State that allowlist changed `7 -> 6`.
- Remove `tests/test_native_turbo.py` from remaining migration waves.
- Record exact verification results.

## Drift Rules

After migration, this grep over `tests/test_native_turbo.py` should print no
matches:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_native_turbo.py || true
```

If a parser-only or algorithm-only fixture needs a metric-like name, use neutral
names such as `delay_a`, `delay_b`, `metric_gain`, or `metric_power`.

## Required Verification

Run from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_native_turbo.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_native_turbo\|tests.test_native_turbo" tests || true
```

Expected:

- target file: `49 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `50 passed, 13 warnings`
- full suite: about `1194 passed, 13 warnings`
- ruff passes
- `git diff --check` is clean
- release checkout status has no output
- drift grep over `tests/test_native_turbo.py` has no matches
- cross-import grep has no source-level consumers unless the guard still lists the file before it is updated

## Stop Conditions

Stop and report instead of widening scope if:

- Production code appears necessary.
- `tests/project_factory.py` or `tests/real_run_smoke_helpers.py` must change.
- `tests/test_openbox_backend.py` or any remote/adapter test must change.
- Full-suite failures appear outside this phase and cannot be tied directly to
  this migration.

Do not commit, tag, push, or publish. The user will ask separately or Codex will
commit only after independent verification.

