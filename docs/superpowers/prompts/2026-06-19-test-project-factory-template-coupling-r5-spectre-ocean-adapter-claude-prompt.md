# Claude Prompt: R5 Spectre/OCEAN Adapter Template-Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r5-spectre-ocean-adapter-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r5-spectre-ocean-adapter-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Use codegraph and graphify if available before editing. The important relationship is that `_create_ready_corner_project` from `tests/test_spectre_ocean_adapter.py` is imported by `tests/test_real_run.py`, `tests/test_remote_spectre_ocean.py`, and `tests/test_remote_spectre_ocean_waveform.py`; R5 must preserve that helper API and verify those consumers.

## Goal

Migrate `tests/test_spectre_ocean_adapter.py` away from direct packaged-template usage while preserving all 87 local Spectre/OCEAN adapter tests and consumer compatibility.

## Strict Scope

Allowed to modify:

```text
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_real_run.py
tests/test_remote_spectre_ocean.py
tests/test_remote_spectre_ocean_waveform.py
tests/test_package.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

If an out-of-scope file appears necessary, stop and report the exact reason.

## Required Changes

In `tests/test_spectre_ocean_adapter.py`:

1. Remove `create_project_from_template` import and all calls.
2. Remove `TEMPLATE_TEXT`.
3. Import `create_approved_generic_project` from `tests.project_factory`.
4. Rewrite `_create_ready_real_run_project(tmp_path)` so it builds an approved generic project and calls `prepare_real_run`.
5. Keep `_create_ready_corner_project(tmp_path)` name and signature unchanged.
6. Keep `_create_ready_multi_testbench_project(tmp_path)` and `_create_ready_corner_project(tmp_path)` requirement-driven unless a target failure proves otherwise.
7. Replace hardcoded old project-name assertions such as `cwd.name == "bridge_test_inv"` with a project-root contract assertion.
8. Replace hardcoded old Spectre setting assertions like `+mt=10` or `threads_per_run == 10` with values derived from the prepared request/config.
9. Do not rewrite pure parser tests solely because they use arbitrary TSV metric labels like `rise` or `fall`.
10. Preserve exact behavior assertions wherever values are still available.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_spectre_ocean_adapter.py",
```

Expected allowlist count: `3 -> 2`.

In the inventory report:

- Add R5 Spectre/OCEAN Adapter status and verification.
- Remove `tests/test_spectre_ocean_adapter.py` from remaining waves.

## Required Verification

Run exactly:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_real_run.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" tests/test_spectre_ocean_adapter.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_spectre_ocean_adapter\|tests.test_spectre_ocean_adapter" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `87 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `88 passed, 13 warnings`
- consumer regression group: `161 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep: no output for the listed template-coupling tokens
- cross-import grep: known consumers only (`tests/test_real_run.py`, `tests/test_remote_spectre_ocean.py`, `tests/test_remote_spectre_ocean_waveform.py`)
- direct template caller list:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
```

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_spectre_ocean_adapter.py`.
3. Helper compatibility status.
4. Guard allowlist count.
5. Exact verification results.
6. Drift grep result.
7. Cross-import grep result.
8. Direct template caller list.
9. Release checkout status.
10. Confirmation that no production files, release files, or `graphify-out/` were touched.
11. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
