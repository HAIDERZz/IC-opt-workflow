# Claude Prompt: Phase 13 Test Project Factory Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is Phase 13 of the Test Project Factory and Template Coupling Cleanup.

## Read First

Read these files before editing:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-phase13-mock-optimizer-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-phase13-mock-optimizer-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_project_factory.py
tests/test_mock_optimizer.py
tests/test_template_coupling_guard.py
src/hermes_workflow/mock_optimizer.py
src/hermes_workflow/validate.py
src/hermes_workflow/schemas.py
```

If codegraph and graphify are available, use them for orientation only. Source
files and tests are authoritative. Do not use graph output as a reason to widen
scope.

## Objective

Migrate:

```text
tests/test_mock_optimizer.py
```

away from direct `create_project_from_template()` usage and old inverter-template
assumptions. The production mock optimizer is generic; tests should use
`create_generic_project()` or neutral in-memory fixtures.

## Strict Scope

Allowed to modify only:

```text
tests/test_mock_optimizer.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/project_factory.py
tests/test_project_factory.py
tests/test_native_turbo.py
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

In `tests/test_mock_optimizer.py`:

1. Remove:

```python
from hermes_workflow.package import create_project_from_template
```

2. Add:

```python
import yaml
from tests.project_factory import create_generic_project
```

3. Add helpers near the top:

```python
def _create_mock_project(tmp_path: Path, **kwargs: object) -> Path:
    return create_generic_project(tmp_path, name="mock_optimizer_project", **kwargs)

def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload

def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

def _variable_names(project_dir: Path) -> tuple[str, str]:
    payload = _read_yaml(project_dir / "config" / "variables.yaml")
    names = [variable["name"] for variable in payload["variables"]]
    assert len(names) == 2
    return names[0], names[1]

def _metric_names(project_dir: Path) -> tuple[str, str]:
    payload = _read_yaml(project_dir / "config" / "metrics.yaml")
    names = [metric["name"] for metric in payload["metrics"]]
    assert len(names) == 2
    return names[0], names[1]

def _candidate_parameters(
    project_dir: Path,
    *,
    int_value: str = "3",
    width_value: str = "0.3u",
) -> dict[str, str]:
    int_name, width_name = _variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}

def _small_grid_project(tmp_path: Path) -> Path:
    project_dir = _create_mock_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    variables = _read_yaml(variables_path)
    int_name, width_name = _variable_names(project_dir)
    variables["variables"] = [
        {"name": int_name, "kind": "integer", "lower": "2", "upper": "3", "step": "1"},
        {"name": width_name, "kind": "continuous_step", "lower": "0.3u", "upper": "0.3u", "step": "0.2u"},
    ]
    _write_yaml(variables_path, variables)
    return project_dir
```

4. Replace schema-only fixtures with neutral names:

- parameters: `PARAM_A`, `PARAM_B`
- metrics: `metric_a`, `metric_b`, `metric_c`
- project name: `mock_optimizer_project`

5. Replace objective-expression fixture:

```python
METRICS = {"metric_a": 52.0, "metric_b": 43.0, "metric_c": 120.0}
```

Update all expressions to use `metric_a`, `metric_b`, `metric_c`.

6. Replace every project-backed:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
```

with:

```python
project_dir = _create_mock_project(tmp_path)
```

7. Derive variable/metric assertions:

- Candidate key checks use `_variable_names(project_dir)`.
- Candidate parameter fixtures use `_candidate_parameters(project_dir, ...)`.
- Missing-metric constraint test uses `_metric_names(project_dir)`.
- Small-grid refill test uses `_small_grid_project(tmp_path)`.
- `run_mock_optimization` project-name assertion uses `project_dir.name`.

8. Remove all old tokens from the file:

```text
create_project_from_template
bridge_test_inv
FN
WN
FP
WP
rise
fall
DC
```

### tests/test_template_coupling_guard.py

Remove:

```python
"tests/test_mock_optimizer.py",
```

Expected allowlist count: `8 -> 7`.

### Inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Add Phase 13 status, remove `tests/test_mock_optimizer.py` from remaining waves,
record verification results, and update stale Phase 12 waveform wording to point
to the Phase 12b fix if needed.

## Required Verification

Run:

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
git status --short
```

Expected:

- target file: `83 passed`
- guard: `1 passed`
- target plus guard: `84 passed`
- full suite: about `1194 passed, 13 warnings`
- ruff: `All checks passed!`
- `git diff --check`: clean
- release checkout status: no output
- drift grep over `tests/test_mock_optimizer.py`: no output
- cross-import grep: no source-level matches after guard update
- changed files only:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/test_mock_optimizer.py
tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

## Stop and Ask If

Stop and report instead of widening scope if:

- Production code under `src/` needs to change.
- `tests/project_factory.py` needs a behavior change.
- Any test outside the three allowed files needs to change.
- The full suite fails outside this phase and the failure is not directly caused
  by these edits.

## Final Report Format

Return:

1. Files modified.
2. Migration summary for `tests/test_mock_optimizer.py`.
3. Guard allowlist count `8 -> 7`.
4. Exact verification commands and pass/fail counts.
5. Drift grep result.
6. Cross-import grep result.
7. Release checkout status.
8. Confirmation that `graphify-out/` was untouched.
9. Remaining deferred allowlist files.

Claim only Phase 13 completion. Do not claim the broader template-coupling cleanup
is complete.
