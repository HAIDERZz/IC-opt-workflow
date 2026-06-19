# Claude Prompt: R4 Remote Optimizer Flow Template-Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r4-remote-optimizer-flow-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r4-remote-optimizer-flow-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Use codegraph and graphify if they are available to inspect relationships before editing. The expected finding is that `tests/test_remote_optimizer_flow.py` has no source-level consumers outside the template guard, so this phase should stay single-file plus guard and inventory. Do not delegate a broad rewrite; keep the change narrow.

## Goal

Migrate `tests/test_remote_optimizer_flow.py` away from direct packaged-template usage while preserving all 21 remote optimizer orchestration and continuation tests.

## Strict Scope

Allowed to modify:

```text
tests/test_remote_optimizer_flow.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_remote_fix_run_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_package.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

If an out-of-scope file appears necessary, stop and report the exact reason.

## Required Changes

In `tests/test_remote_optimizer_flow.py`:

1. Remove `create_project_from_template` import and all calls.
2. Import `yaml`.
3. Import `create_generic_project` from `tests.project_factory`.
4. Add local helpers:
   - `_read_yaml`
   - `_write_yaml`
   - `_create_remote_optimizer_project`
5. Convert `_set_optimizer_strategy` to structured YAML mutation.
6. Convert `_set_keep_flags_for_retention_remote` to structured YAML mutation.
7. Replace full-project setup in:
   - `test_optimize_remote_project_routes_turbo_strategy_through_remote_adapter`
   - `test_optimize_remote_project_allows_config_turbo_strategy_before_local_execution`
   - all five remote retention tests
   - `test_remote_optimizer_audit_records_remote_transport_mode`
8. Preserve all exact behavior assertions. Do not weaken path, argument, retention-command, or audit assertions.
9. Do not force continuation-only minimal cache tests into generic factory if they only need `execution_package/` plus optimizer history and mocked validation.
10. Keep all 21 tests passing.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_remote_optimizer_flow.py",
```

Expected allowlist count: `4 -> 3`.

In the inventory report:

- Add R4 Remote Optimizer Flow status and verification.
- Remove `tests/test_remote_optimizer_flow.py` from remaining waves.

## Required Verification

Run exactly:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_optimizer_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_optimizer_flow\|tests.test_remote_optimizer_flow" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `21 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `22 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep: no output
- cross-import grep: no output
- direct template caller list:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_remote_optimizer_flow.py`.
3. Guard allowlist count.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that no production files, release files, or `graphify-out/` were touched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
