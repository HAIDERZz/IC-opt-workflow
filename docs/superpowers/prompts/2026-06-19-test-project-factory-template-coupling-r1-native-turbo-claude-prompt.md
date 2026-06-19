# Claude Prompt: R1 Native TuRBO Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is R1 of the remaining Test Project Factory and Template Coupling Cleanup.
Phase 13 is already committed. Do not touch the release checkout.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r1-native-turbo-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r1-native-turbo-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
docs/superpowers/plans/2026-06-19-template-coupling-remaining-total-plan.md
tests/test_native_turbo.py
tests/test_template_coupling_guard.py
tests/project_factory.py
tests/real_run_smoke_helpers.py
src/hermes_workflow/native_turbo.py
src/hermes_workflow/validate.py
src/hermes_workflow/schemas.py
```

If codegraph and graphify are available, use them only for orientation. Source
files and tests are authoritative. The existing `graphify-out/` may be stale; do
not modify it.

## Objective

Migrate:

```text
tests/test_native_turbo.py
```

away from direct `create_project_from_template()` usage and old packaged-template
assumptions (`bridge_test_inv`, `FN/WN/FP/WP`, `rise/fall/DC`), while preserving
all Native TuRBO behavior coverage.

## Strict Scope

Allowed to modify only:

```text
tests/test_native_turbo.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/real_run_smoke_helpers.py
tests/test_openbox_backend.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

Do not commit, tag, push, or publish.

## Required Implementation

In `tests/test_native_turbo.py`:

1. Remove direct `create_project_from_template` import and calls.
2. Add `yaml` plus `create_generic_project` from `tests.project_factory`.
   Import `create_approved_generic_project` only if the final implementation
   actually uses it.
3. Add local helpers:
   - `_read_yaml`
   - `_write_yaml`
   - `_create_native_project`
   - `_variable_names`
   - `_metric_names`
   - `_candidate_parameters`
   - `_passing_metric_values`
   - `_constraint_failing_metric_values`
   - `_set_optimizer_value`
   - `_set_spectre_value`
4. Rename standalone in-memory variable fixtures from `FN/WN` to neutral names,
   preferably `VAR_INT/VAR_WIDTH`.
5. Replace old project-backed setup with generic factory projects.
6. Derive candidate parameter keys and metric names from generated config.
7. Replace old metric values with generic metric values:
   - pass: `metric_gain=1.0`, `metric_power=1.0e-4`
   - constraint fail: `metric_gain=1.0`, `metric_power=1.0`
8. Use structured YAML mutation for optimizer and Spectre config edits.
9. Keep requirement-intake multi-testbench fixtures where they are intentional,
   but remove hardcoded old candidate payloads from those tests by deriving
   variable names from the generated config.
10. Preserve all 49 tests and their behavior coverage.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_native_turbo.py",
```

Expected allowlist count: `7 -> 6`.

In the inventory report:

- Add R1 Native TuRBO status.
- Remove `tests/test_native_turbo.py` from remaining waves.
- Record exact verification results.

## Required Verification

Run:

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
git status --short
```

Expected:

- target file: `49 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `50 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep over `tests/test_native_turbo.py`: no output
- cross-import grep: no source-level matches

Existing untracked `graphify-out/` may appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` or `tests/real_run_smoke_helpers.py` needs to change.
- `tests/test_openbox_backend.py` or remote/adapter tests need to change.
- Full-suite failures appear outside this phase and are not directly caused by
  these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_native_turbo.py`.
3. Guard allowlist count `7 -> 6`.
4. Exact verification commands and pass/fail counts.
5. Drift grep result.
6. Cross-import grep result.
7. Release checkout status.
8. Confirmation that `graphify-out/` was untouched.
9. Remaining deferred allowlist files.

Claim only R1 Native TuRBO completion. Do not claim the broader cleanup is
complete.
