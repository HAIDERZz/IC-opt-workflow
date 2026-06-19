# Claude Prompt: R3 Remote Fix-Run Template-Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r3-remote-fix-run-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r3-remote-fix-run-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

## Goal

Migrate `tests/test_remote_fix_run_flow.py` away from direct packaged-template usage while preserving all 11 remote fix-run orchestration tests.

## Strict Scope

Allowed to modify:

```text
tests/test_remote_fix_run_flow.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_remote_optimizer_flow.py
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

In `tests/test_remote_fix_run_flow.py`:

1. Import `create_generic_project` from `tests.project_factory`.
2. Add local helpers:
   - `_read_yaml`
   - `_write_yaml`
   - `_fixed_points`
   - `_fixed_point_candidate_id`
   - `_fixed_point_parameters`
   - `_write_remote_waveform_exports`
   - `_create_remote_fix_run_project`
3. Build test projects with:

```python
create_generic_project(
    tmp_path,
    name="remote_fix_run_project",
    workflow_mode="fix_run",
    parallel_jobs=4,
)
```

4. Remove every local import/call of `create_project_from_template`.
5. Do not hand-write `workflow.yaml`, `fixed_points.yaml`, or `template.scs` in individual tests.
6. Replace hardcoded `FN/WN` fixed-point parameters with `_fixed_point_parameters(project_dir)`.
7. Replace hardcoded fixed-point candidate IDs with `_fixed_point_candidate_id(project_dir)` where needed.
8. Use `_create_remote_fix_run_project(tmp_path, name="remote_fix_run_parallel", waveform_exports=True)` for waveform artifact and child-parallelism tests.
9. Remove `_strip_optimizer_configs_for_remote_fix_run`; the generic fix-run factory already removes optimizer config.
10. Preserve all behavior assertions and all 11 tests.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_remote_fix_run_flow.py",
```

Expected allowlist count: `5 -> 4`.

In the inventory report:

- Add R3 Remote Fix-Run status and verification.
- Remove `tests/test_remote_fix_run_flow.py` from remaining waves.

## Required Verification

Run exactly:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_fix_run_flow.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_fix_run_flow\|tests.test_remote_fix_run_flow" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `11 passed, 13 warnings`
- guard: `1 passed`
- target plus guard: `12 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- drift grep: no output
- cross-import grep: no output
- direct template caller list:

```text
tests/test_package.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
tests/test_template_coupling_guard.py
```

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_remote_fix_run_flow.py`.
3. Guard allowlist count.
4. Exact verification results.
5. Drift grep result.
6. Cross-import grep result.
7. Direct template caller list.
8. Release checkout status.
9. Confirmation that no production files, release files, or `graphify-out/` were touched.
10. Remaining deferred allowlist files.

Do not commit, tag, push, or publish.
