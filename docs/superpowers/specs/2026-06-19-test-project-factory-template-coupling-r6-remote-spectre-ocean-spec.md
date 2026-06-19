# R6 Remote Spectre/OCEAN Template-Coupling Cleanup Spec

## Objective

Migrate `tests/test_remote_spectre_ocean.py` away from direct packaged-template usage while preserving all remote Spectre/OCEAN adapter and multi-testbench orchestration coverage.

R6 must remove `tests/test_remote_spectre_ocean.py` from `ALLOWED_TEMPLATE_CALLERS`, leaving only the intentionally template-based package tests as direct `create_project_from_template()` users.

## Current State

R5 Spectre/OCEAN Adapter has been committed as:

```text
7389385 test: decouple spectre ocean adapter tests from template
```

The remaining direct test callers of `create_project_from_template()` are:

```text
tests/test_package.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
```

Remote Spectre/OCEAN baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected:

```text
38 passed, 13 warnings
```

Consumer baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
45 passed, 13 warnings
```

Target plus consumer plus guard baseline:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
46 passed, 13 warnings
```

## In Scope

Allowed files:

- `tests/test_remote_spectre_ocean.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Out of Scope

Do not modify:

- `src/`
- `tests/project_factory.py`
- `tests/test_remote_spectre_ocean_waveform.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_package.py`
- release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

If `tests/test_remote_spectre_ocean_waveform.py` appears to require edits, stop and report the exact reason. First preserve the helper API imported from `tests/test_remote_spectre_ocean.py`.

## Required Behavior

### Remote Spectre/OCEAN Tests Remain Behavior-Equivalent

All 38 tests in `tests/test_remote_spectre_ocean.py` must still pass. Coverage must remain for:

- Remote single-run Spectre/OCEAN execution and timeout forwarding.
- Remote corner-aware child runs.
- Remote command quoting and canonical local argv.
- Spectre failure, Ocean failure, upload failure, download failure, and runtime exception paths.
- Local fallback manifests when remote download fails.
- Multi-testbench remote adapter execution.
- Multi-corner multi-testbench and single-testbench multi-corner child execution.
- Aggregate manifest content and metric failure propagation.
- Parallel job non-multiplication.
- Command trace contracts and CSHRC secrecy.
- Missing PSF artifact failure.
- Metric row failure propagation.
- Remote waveform helper compatibility through `tests/test_remote_spectre_ocean_waveform.py`.

### Helper Compatibility Is Required

`tests/test_remote_spectre_ocean_waveform.py` imports from `tests/test_remote_spectre_ocean.py`:

```python
FakeRunner
_ocean_scalars_tsv
_request_for_metrics_dir
create_approved_real_project
```

Keep those names importable with compatible behavior.

### Generic Project Factory Is the Source of Truth for Direct Project Setup

Use:

```python
from tests.project_factory import create_generic_project
```

Replace `_create_ready_multi_corner_single_testbench_project` so it no longer calls `create_project_from_template()` or writes an `FN/WN/FP/WP` template.

Suggested shape:

```python
def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return tuple(variable["name"] for variable in payload["variables"])


def _create_ready_multi_corner_single_testbench_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name="remote_single_tb_corner_project",
    )
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_text = (project_dir / "netlists" / "templates" / "template.scs").read_text(
        encoding="utf-8"
    )
    for corner_id in corner_ids:
        corner_template = project_dir / "netlists" / "corners" / corner_id / "template.scs"
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-13T00:20:00Z")
    return project_dir
```

You may adjust helper names or factor small local helpers, but do not change the public helper signature used by tests.

### Legacy Fallbacks Must Be Removed

Remove the old fallback behavior that fabricates `rise/fall/DC` rows when no request is found.

For `_ocean_scalars_tsv`, use fail-fast behavior:

```python
def _ocean_scalars_tsv(request: dict | None) -> str:
    if request is None:
        raise AssertionError("metric request is required to build ocean_scalars.tsv")
    ...
```

For `MetricFailFakeRunner`, if `_request_for_metrics_dir(...)` returns `None`, raise `AssertionError` instead of writing legacy rows.

For `MultiTestbenchFakeRunner._resolve_metric_names`, remove the `["rise", "fall", "DC"]` fallback. Prefer resolving from `metric_extraction_request.json`; otherwise raise `AssertionError`.

Do not leave comments that say the code falls back to legacy `rise/fall/DC` behavior.

### Remove Old Template Coupling

`tests/test_remote_spectre_ocean.py` must not import or call `create_project_from_template`.

Remove these template-coupling tokens from the file:

- `create_project_from_template`
- `bridge_test_inv`
- `FN`
- `WN`
- `FP`
- `WP`

R6 should also remove legacy standalone `rise/fall/DC` fallback rows from this file.

### Guard and Inventory Updated

Remove `tests/test_remote_spectre_ocean.py` from `ALLOWED_TEMPLATE_CALLERS`.

Expected guard count:

```text
2 -> 1
```

Update the inventory report:

- Add R6 Remote Spectre/OCEAN status with exact verification results.
- Remove `tests/test_remote_spectre_ocean.py` from remaining migration waves.
- State that only `tests/test_package.py` remains as an intentional direct packaged-template caller.

## Required Verification

Run:

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
grep -nE "\\b(rise|fall|DC)\\b" tests/test_remote_spectre_ocean.py || true
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
- release checkout status: no output
- template-coupling grep over `tests/test_remote_spectre_ocean.py`: no output
- legacy fallback grep over `tests/test_remote_spectre_ocean.py`: no output unless the match is in an unrelated English word; fix comments/names if practical
- cross-import grep: known consumer only `tests/test_remote_spectre_ocean_waveform.py`
- direct template caller list contains only:

```text
tests/test_package.py
tests/test_template_coupling_guard.py
```

## Stop Conditions

Stop and report before editing outside scope if:

- `tests/test_remote_spectre_ocean_waveform.py` must change.
- Production `src/` changes appear necessary.
- `tests/project_factory.py` cannot represent the single-testbench multi-corner project shape.
- Removing legacy fallback rows reveals a real missing `metric_extraction_request.json` in normal remote paths.
- Assertions would need to become broad truthiness or type-only checks where exact values are currently available.
