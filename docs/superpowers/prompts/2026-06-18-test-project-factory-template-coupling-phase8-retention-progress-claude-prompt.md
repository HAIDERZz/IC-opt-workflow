# Claude Prompt: Phase 8 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 8 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase8-retention-progress-spec.md
docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase8-retention-progress-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_project_factory.py
tests/test_run_retention.py
tests/test_optimizer_progress_state.py
tests/test_template_coupling_guard.py
src/hermes_workflow/run_retention.py
src/hermes_workflow/optimizer_progress_state.py
```

If codegraph and graphify are available, use them for orientation only. The source files and tests above are authoritative. Do not use graphify output as a reason to widen scope.

## Objective

Migrate these two files away from direct `create_project_from_template()` usage:

```text
tests/test_run_retention.py
tests/test_optimizer_progress_state.py
```

Both files should use `tests/project_factory.py` and should not carry old packaged-template assumptions such as `bridge_test_inv`, `FN`, `WN`, `FP`, `WP`, or `rise`.

## Strict Scope

Allowed to modify only:

```text
tests/test_run_retention.py
tests/test_optimizer_progress_state.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
tests/project_factory.py
tests/test_project_factory.py
tests/test_package.py
tests/test_cli.py
```

Do not commit, tag, push, or publish.

## Required Implementation

### tests/test_run_retention.py

- Replace `from hermes_workflow.package import create_project_from_template` with `from tests.project_factory import create_generic_project`.
- Import `yaml`.
- Add:

```python
def _create_retention_project(tmp_path: Path) -> Path:
    return create_generic_project(tmp_path, name="retention_project")
```

- Replace `_set_keep_flags()` string replacement with structured YAML mutation:

```python
def _set_keep_flags(
    project_dir: Path, *, keep_failed_runs: bool, keep_successful_runs: bool
) -> None:
    """Edit config/spectre.yaml to set the two retention flags."""
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    spectre = payload.setdefault("spectre", {})
    spectre["keep_failed_runs"] = keep_failed_runs
    spectre["keep_successful_runs"] = keep_successful_runs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- Replace every:

```python
project_dir = tmp_path / "project"
create_project_from_template(project_dir)
```

with:

```python
project_dir = _create_retention_project(tmp_path)
```

- Preserve all current behavior assertions.

### tests/test_optimizer_progress_state.py

- Replace `create_project_from_template` import with `create_generic_project`.
- Import `yaml`.
- Add constants:

```python
PROJECT_NAME = "progress_project"
MAX_EVALUATIONS = 10
BATCH_SIZE = 2
```

- Delete `_set_optimizer_max_evaluations()`.
- Add helpers:

```python
def _create_progress_project(tmp_path: Path) -> Path:
    return create_generic_project(
        tmp_path,
        name=PROJECT_NAME,
        max_evaluations=MAX_EVALUATIONS,
        batch_size=BATCH_SIZE,
    )


def _read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    variables = payload.get("variables")
    assert isinstance(variables, list)
    names: list[str] = []
    for entry in variables:
        assert isinstance(entry, dict)
        name = entry.get("name")
        assert isinstance(name, str)
        names.append(name)
    assert names
    return tuple(names)


def _metric_names(project_dir: Path) -> tuple[str, ...]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    metrics = payload.get("metrics")
    assert isinstance(metrics, list)
    names: list[str] = []
    for entry in metrics:
        assert isinstance(entry, dict)
        name = entry.get("name")
        assert isinstance(name, str)
        names.append(name)
    assert names
    return tuple(names)
```

- In `_write_artifacts_for_progress()`, derive names:

```python
variable_name = _variable_names(project_dir)[0]
metric_name = _metric_names(project_dir)[0]
```

- Change fake ledger rows:

```python
"parameters": {variable_name: "2"},
"metrics": {metric_name: 1.0e-12},
```

- Replace every `project_name="bridge_test_inv"` with `project_name=PROJECT_NAME`.
- Replace sync-test setup:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
_set_optimizer_max_evaluations(project_dir, 10)
```

with:

```python
project_dir = _create_progress_project(tmp_path)
```

- Replace existing state payload `"project_name": "bridge_test_inv"` with `"project_name": PROJECT_NAME`.
- Preserve all current behavior assertions.

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/test_optimizer_progress_state.py",
"tests/test_run_retention.py",
```

Expected allowlist count: `14 -> 12`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 8 status, update the phase list, remove the two files from remaining waves, and add exact verification results.

## Required Verification

Run these commands from repo root:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise" tests/test_run_retention.py tests/test_optimizer_progress_state.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_run_retention\|tests.test_run_retention\|from tests.test_optimizer_progress_state\|tests.test_optimizer_progress_state" tests || true
git status --short
```

Expected results:

- target pair: `28 passed`
- guard: `1 passed`
- target pair plus guard: `29 passed`
- Phase 1-8 regression group: about `322 passed`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over the two migrated files: no output
- cross-import grep: no source-level matches
- changed files only:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/test_optimizer_progress_state.py
tests/test_run_retention.py
tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- Any test outside the four allowed files needs to change.
- `tests/project_factory.py` needs another behavior change.
- Remote, adapter, backend, fix-run, or multi-testbench flows become involved.
- The full suite fails outside this phase and the failure is not directly caused by these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_run_retention.py`.
3. Migration summary for `tests/test_optimizer_progress_state.py`.
4. Guard allowlist count `14 -> 12`.
5. Exact verification commands and pass/fail counts.
6. Drift grep result.
7. Cross-import grep result.
8. Release checkout status.
9. Confirmation that `graphify-out/` was untouched.
10. Remaining deferred allowlist files.

Claim only Phase 8 completion. Do not claim the broader template-coupling cleanup is complete.
