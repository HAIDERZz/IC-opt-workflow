# Claude Prompt: R6 Remote Spectre/OCEAN Template-Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Use these documents:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-r6-remote-spectre-ocean-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-r6-remote-spectre-ocean-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Use codegraph and graphify if available before editing. The important relationship is that `tests/test_remote_spectre_ocean_waveform.py` imports `FakeRunner`, `_ocean_scalars_tsv`, `_request_for_metrics_dir`, and `create_approved_real_project` from `tests/test_remote_spectre_ocean.py`; R6 must preserve these imports and verify the waveform consumer.

## Goal

Migrate `tests/test_remote_spectre_ocean.py` away from direct packaged-template usage and remove legacy `rise/fall/DC` scalar fallbacks.

## Strict Scope

Allowed to modify:

```text
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_remote_spectre_ocean_waveform.py
tests/test_spectre_ocean_adapter.py
tests/test_package.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

If `tests/test_remote_spectre_ocean_waveform.py` appears necessary to edit, stop and report the exact reason.

## Required Changes

In `tests/test_remote_spectre_ocean.py`:

1. Remove `create_project_from_template` import and all calls.
2. Import `yaml`.
3. Import `create_generic_project` from `tests.project_factory`.
4. Add `_variable_names(project_dir)`.
5. Rewrite `_create_ready_multi_corner_single_testbench_project(...)` to use `create_generic_project`, existing generic `template.scs`, structured `process_corners.yaml`, `build_execution_package`, `write_pass_reports(..., variable_names=_variable_names(project_dir))`, `decide_first_real_run`, and `prepare_real_run`.
6. Remove legacy fallback rows from `_ocean_scalars_tsv`; if request is `None`, raise `AssertionError`.
7. Remove legacy fallback rows from `MetricFailFakeRunner`; if request is `None`, raise `AssertionError`.
8. Remove `MultiTestbenchFakeRunner._resolve_metric_names` fallback `["rise", "fall", "DC"]`; derive names from request or raise.
9. Rename stale local variables such as `fall_metric` to generic names like `failed_metric`.
10. Remove stale comments/docstrings mentioning legacy `rise/fall/DC`, `create_project_from_template`, or `bridge_test_inv`.
11. Preserve all helper names imported by `tests/test_remote_spectre_ocean_waveform.py`.

In `tests/test_template_coupling_guard.py`:

Remove:

```python
"tests/test_remote_spectre_ocean.py",
```

Expected allowlist count: `2 -> 1`.

In the inventory report:

- Add R6 Remote Spectre/OCEAN status and verification.
- Remove `tests/test_remote_spectre_ocean.py` from remaining waves.
- State that only `tests/test_package.py` remains as an intentional direct packaged-template caller.

## Required Verification

Run exactly:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_remote_spectre_ocean.py || true
grep -nE "\b(rise|fall|DC)\b" tests/test_remote_spectre_ocean.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_remote_spectre_ocean\|tests.test_remote_spectre_ocean" tests || true
rg -l "create_project_from_template" tests | sort
git status --short
```

Expected:

- target: `38 passed, 13 warnings`
- target plus waveform consumer: `45 passed, 13 warnings`
- guard: `1 passed`
- target plus waveform plus guard: `46 passed, 13 warnings`
- full suite: `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout: no output
- template-coupling grep: no output
- legacy `rise/fall/DC` grep: no output
- cross-import grep: known waveform consumer only
- direct template caller list:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_remote_spectre_ocean.py`.
3. Waveform helper compatibility status.
4. Legacy fallback cleanup status.
5. Guard allowlist count.
6. Exact verification results.
7. Drift grep result.
8. Cross-import grep result.
9. Direct template caller list.
10. Release checkout status.
11. Confirmation that no production files, release files, or `graphify-out/` were touched.
12. Remaining direct template caller: `tests/test_package.py` only.

Do not commit, tag, push, or publish.
