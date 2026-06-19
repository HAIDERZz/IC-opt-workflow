# Test Project Factory Template Coupling Phase 13 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `tests/test_mock_optimizer.py` from the packaged release
template while preserving mock optimizer behavior coverage.

**Architecture:** Replace project-backed setup with `create_generic_project()`.
Schema-only and expression-only tests should use neutral in-memory fixtures. The
project-backed tests derive variable and metric names from generated generic
config, then assert behavior against those names.

**Tech Stack:** Python, pytest, PyYAML, `tests/project_factory.py`,
`hermes_workflow.mock_optimizer`.

---

## File Structure

- Modify `tests/test_mock_optimizer.py`
  - Import `yaml` and `create_generic_project`.
  - Remove `create_project_from_template`.
  - Add generic config helpers.
  - Replace old schema/objective fixtures with neutral names.
  - Replace project-backed template setup with generic factory setup.

- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_mock_optimizer.py` from the allowlist.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add Phase 13 status and verification.
  - Remove stale Phase 12 waveform failure wording if still present.

## Task 0: Baseline Check

**Files:**
- Read: `tests/test_mock_optimizer.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm target file is green before edits**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py -q
```

Expected:

```text
83 passed
```

- [ ] **Step 2: Confirm direct-template and old-token coupling**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_mock_optimizer.py || true
```

Expected before edits: many matches. The migration is complete only when this
command prints no matches.

- [ ] **Step 3: Confirm no external consumers**

Run:

```bash
grep -R --exclude-dir=__pycache__ -n "from tests.test_mock_optimizer\|tests.test_mock_optimizer" tests || true
```

Expected before edits: only the allowlist entry in
`tests/test_template_coupling_guard.py`.

## Task 1: Add Generic Test Helpers

**Files:**
- Modify: `tests/test_mock_optimizer.py`

- [ ] **Step 1: Update imports**

Remove:

```python
from hermes_workflow.package import create_project_from_template
```

Add:

```python
import yaml

from tests.project_factory import create_generic_project
```

- [ ] **Step 2: Add helper functions after imports**

Add:

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
        {
            "name": int_name,
            "kind": "integer",
            "lower": "2",
            "upper": "3",
            "step": "1",
        },
        {
            "name": width_name,
            "kind": "continuous_step",
            "lower": "0.3u",
            "upper": "0.3u",
            "step": "0.2u",
        },
    ]
    _write_yaml(variables_path, variables)
    return project_dir
```

## Task 2: Neutralize Schema and Objective Fixtures

**Files:**
- Modify: `tests/test_mock_optimizer.py`
- Test: `tests/test_mock_optimizer.py`

- [ ] **Step 1: Replace schema fixture dictionaries**

Replace `VALID_LEDGER_ROW`, `VALID_BEST_CANDIDATE`, and
`VALID_OPTIMIZER_STATE` with neutral names:

```python
VALID_LEDGER_ROW = {
    "candidate_id": "cand_001",
    "parameters": {"PARAM_A": "4", "PARAM_B": "1.0u"},
    "metrics": {"metric_a": 52.0, "metric_b": 43.0, "metric_c": 120.0},
    "constraints_passed": True,
    "objective": 11400.0,
    "batch_id": 1,
    "simulation_status": "mock_pass",
    "timestamp_utc": "2026-05-29T12:00:00Z",
}

VALID_BEST_CANDIDATE = {
    "candidate_id": "cand_001",
    "parameters": {"PARAM_A": "4", "PARAM_B": "1.0u"},
    "metrics": {"metric_a": 52.0, "metric_b": 43.0, "metric_c": 120.0},
    "constraints_passed": True,
    "objective": 11400.0,
    "batch_id": 1,
    "timestamp_utc": "2026-05-29T12:00:00Z",
}

VALID_OPTIMIZER_STATE = {
    "schema_version": "1.0",
    "project_name": "mock_optimizer_project",
    "algorithm": "turbo",
    "initialization": "sobol",
    "current_evaluations": 6,
    "max_evaluations": 100,
    "batch_size": 10,
    "random_seed": 20260528,
    "best_candidate_id": "cand_001",
    "status": "completed",
    "started_at_utc": "2026-05-29T12:00:00Z",
    "updated_at_utc": "2026-05-29T12:00:01Z",
}
```

- [ ] **Step 2: Update schema assertions**

Replace assertions like:

```python
assert row.parameters["FN"] == "4"
assert row.metrics["rise"] == 52.0
assert candidate.metrics["DC"] == 120.0
assert state.project_name == "bridge_test_inv"
```

with:

```python
assert row.parameters["PARAM_A"] == "4"
assert row.metrics["metric_a"] == 52.0
assert candidate.metrics["metric_c"] == 120.0
assert state.project_name == "mock_optimizer_project"
```

- [ ] **Step 3: Replace objective fixture metrics**

Change:

```python
METRICS = {"rise": 52.0, "fall": 43.0, "DC": 120.0}
```

to:

```python
METRICS = {"metric_a": 52.0, "metric_b": 43.0, "metric_c": 120.0}
```

Update all `evaluate_objective()` expressions accordingly:

- `(metric_a + metric_b) * metric_c`
- `metric_a`
- `metric_a + 10.0`
- `metric_a * 2`
- `-metric_a`
- `metric_a / metric_b`
- `metric_a ** 2`
- `metric_a % metric_b`
- `-min(max(metric_a, metric_b), ln(metric_c))`
- unknown metric case: `metric_a + unknown_metric`
- unsupported function case: `abs(metric_a)`
- unsupported literal cases with `metric_a`

- [ ] **Step 4: Update pure write helper tests**

For `write_ledger_row`, `write_optimizer_state`, and `write_best_candidate` tests,
replace old parameter/metric/project names with neutral names. Example:

```python
parameters={"PARAM_A": "4", "PARAM_B": "1.0u"}
metrics={"metric_a": 52.0, "metric_b": 43.0}
project_name="mock_optimizer_project"
```

- [ ] **Step 5: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py -q
```

Expected: failures may remain in project-backed tests until Task 3.

## Task 3: Migrate Candidate and Metric Project Tests

**Files:**
- Modify: `tests/test_mock_optimizer.py`
- Test: `tests/test_mock_optimizer.py`

- [ ] **Step 1: Replace `create_project_from_template()` in candidate tests**

For candidate-generation tests, replace:

```python
project_dir = tmp_path / "bridge_test_inv"
create_project_from_template(project_dir)
bundle = assert_valid_project(project_dir)
```

with:

```python
project_dir = _create_mock_project(tmp_path)
bundle = assert_valid_project(project_dir)
```

- [ ] **Step 2: Derive candidate variable assertions**

Replace old checks:

```python
assert "FN" in candidate
assert "WN" in candidate
assert "FP" in candidate
assert "WP" in candidate
```

with:

```python
for name in _variable_names(project_dir):
    assert name in candidate
```

For grid tests, use:

```python
int_name, _width_name = _variable_names(project_dir)
integer_grid = {str(v) for v in generate_integer_grid(1, 5, 1)}
for candidate in candidates:
    assert candidate[int_name] in integer_grid
```

The generic factory integer variable bounds are 1..5.

- [ ] **Step 3: Update deduplication test to neutral names**

Use:

```python
candidates = [
    {"PARAM_A": "4", "PARAM_B": "1.0u"},
    {"PARAM_A": "4", "PARAM_B": "1.0u"},
    {"PARAM_A": "6", "PARAM_B": "1.2u"},
]
```

- [ ] **Step 4: Update refill-after-deduplication test**

Use `_small_grid_project(tmp_path)`:

```python
project_dir = _small_grid_project(tmp_path)
bundle = assert_valid_project(project_dir)
int_name, _width_name = _variable_names(project_dir)

candidates = generate_candidates(
    bundle,
    n_candidates=2,
    seed=3,
    initialization="random",
)

assert len(candidates) == 2
assert {candidate[int_name] for candidate in candidates} == {"2", "3"}
```

- [ ] **Step 5: Update compute-metric tests**

Use:

```python
project_dir = _create_mock_project(tmp_path)
bundle = assert_valid_project(project_dir)
params = _candidate_parameters(project_dir, int_value="3", width_value="0.3u")
```

For different metrics:

```python
params_a = _candidate_parameters(project_dir, int_value="2", width_value="0.2u")
params_b = _candidate_parameters(project_dir, int_value="5", width_value="0.5u")
```

Keep assertions for determinism, declared metrics, positivity, and float values.

- [ ] **Step 6: Update project-backed constraint tests**

Use generic factory project and derived params:

```python
project_dir = _create_mock_project(tmp_path)
bundle = assert_valid_project(project_dir)
params = _candidate_parameters(project_dir)
metrics = compute_mock_metrics(bundle.metrics, bundle.variables, params)
result = evaluate_constraints(bundle.metrics, metrics)
assert isinstance(result, bool)
```

For missing metric:

```python
first_metric, _second_metric = _metric_names(project_dir)
partial_metrics = {first_metric: 50.0}
assert evaluate_constraints(bundle.metrics, partial_metrics) is False
```

For the pure unit-suffix constraint test, rename the metric from old `rise` to
`delay`.

- [ ] **Step 7: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py -q
```

Expected: remaining failures, if any, should be in run-mock-optimization tests.

## Task 4: Migrate Run Mock Optimization Tests

**Files:**
- Modify: `tests/test_mock_optimizer.py`
- Test: `tests/test_mock_optimizer.py`

- [ ] **Step 1: Replace project setup**

In every `TestRunMockOptimization` test, replace old setup with:

```python
project_dir = _create_mock_project(tmp_path)
```

- [ ] **Step 2: Update project-name assertion**

Replace:

```python
assert state.project_name == "bridge_test_inv"
```

with:

```python
assert state.project_name == project_dir.name
```

- [ ] **Step 3: Keep artifact and row-shape assertions**

Do not weaken artifact assertions. Keep checks for:

- `ledger/experiment_ledger.jsonl`
- `state/optimizer_state.json`
- `state/best_candidate.json`
- `state/health_check.json`
- row keys
- no real-result fields in mock ledger rows

- [ ] **Step 4: Run target file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py -q
```

Expected:

```text
83 passed
```

- [ ] **Step 5: Run drift grep**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" tests/test_mock_optimizer.py || true
```

Expected: no output.

## Task 5: Shrink the Coupling Guard

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Test: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Remove `tests/test_mock_optimizer.py` from allowlist**

Remove:

```python
"tests/test_mock_optimizer.py",
```

After the edit the allowlist should contain 7 files:

```python
ALLOWED_TEMPLATE_CALLERS = {
    "tests/test_package.py",
    "tests/test_native_turbo.py",
    "tests/test_openbox_backend.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_spectre_ocean_adapter.py",
}
```

- [ ] **Step 2: Run guard and target-plus-guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_mock_optimizer.py tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
84 passed
```

## Task 6: Update Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Update phase list**

Change the phase summary ending to include Phase 13:

```markdown
12 (real-run smoke helpers), and 13 (mock optimizer)
```

- [ ] **Step 2: Add Phase 13 status before Phase 12**

Add:

```markdown
## Phase 13 status

Migrated `tests/test_mock_optimizer.py` away from direct
`create_project_from_template()` usage. Project-backed tests now create generic
projects through `create_generic_project()` and derive variable/metric names from
generated config. Schema-only, objective-expression, and pure writer tests use
neutral in-memory parameter and metric names instead of old packaged-template
names.

Coverage preserved: schema validation, objective expression evaluation,
integer/continuous grid helpers, candidate generation and deduplication,
deterministic mock metrics, constraint evaluation, mock ledger/state/best/health
writers, and end-to-end `run_mock_optimization()` artifact writing.

`tests/test_mock_optimizer.py` was removed from `ALLOWED_TEMPLATE_CALLERS`
(allowlist 8 -> 7).
```

- [ ] **Step 3: Remove stale Phase 12 known issue text if present**

If Phase 12 still contains a paragraph saying `tests/test_remote_spectre_ocean_waveform.py`
has 6 failures, replace it with a one-sentence reference to the Phase 12b
addendum:

```markdown
The initial Phase 12 full-suite failure in
`tests/test_remote_spectre_ocean_waveform.py` was resolved by the Phase 12b
scope extension below.
```

- [ ] **Step 4: Remove `tests/test_mock_optimizer.py` from remaining waves**

The optimizer backend wave should no longer list `tests/test_mock_optimizer.py`.

- [ ] **Step 5: Add Phase 13 verification**

Record exact results for:

```markdown
- `pytest tests/test_mock_optimizer.py -q` -> `83 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_mock_optimizer.py tests/test_template_coupling_guard.py -q` -> `84 passed`
- `pytest -q` -> ...
- `ruff check src tests` -> ...
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean
- grep forbidden tokens over `tests/test_mock_optimizer.py` -> no matches
- grep cross-imports -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 8 -> 7.
```

## Task 7: Full Verification and Final Report

**Files:**
- Verify: target, guard, full suite, release checkout

- [ ] **Step 1: Run full suite**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

- [ ] **Step 2: Run ruff**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: clean.

- [ ] **Step 4: Confirm release checkout stayed untouched**

Run:

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 5: Final git status**

Run:

```bash
git status --short
```

Expected changed files:

```text
 M docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
 M tests/test_mock_optimizer.py
 M tests/test_template_coupling_guard.py
```

Existing untracked `graphify-out/` may still appear. Do not stage or modify it.

- [ ] **Step 6: Final report**

Include:

- Files modified.
- Migration summary.
- Guard allowlist count `8 -> 7`.
- Exact verification commands and pass/fail counts.
- Drift grep result.
- Cross-import grep result.
- Release checkout status.
- Confirmation that `graphify-out/` was untouched.
- Remaining deferred allowlist files:

```text
tests/test_package.py
tests/test_native_turbo.py
tests/test_openbox_backend.py
tests/test_remote_fix_run_flow.py
tests/test_remote_optimizer_flow.py
tests/test_remote_spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

Do not commit, tag, push, or publish.

## Stop Conditions

Stop and report before widening scope if:

- Production code under `src/` appears necessary.
- `tests/project_factory.py` must change.
- Any test outside the three allowed files must change.
- Full-suite failures appear outside this phase and cannot be tied directly to
  this migration.
