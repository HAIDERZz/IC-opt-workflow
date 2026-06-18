# Next Real-Run Cluster Template Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `test_next_real_run.py` and its three consumers from old release-template assumptions to the generic test project factory.

**Architecture:** Introduce one test-only helper module for the shared generic real-run fixture, fake result manifests, and candidate parameter builders. Then migrate the hub and consumers together so no test file imports helpers from another test file and the template-coupling guard can shrink.

**Tech Stack:** Python 3.11, pytest, Typer `CliRunner`, repo-local `tests/project_factory.py`, existing Hermes workflow APIs.

---

## File Structure

- Create `tests/real_run_cluster_helpers.py`
  - Shared JSON helpers.
  - Generic project setup for this cluster.
  - Fake result and metric-result manifest writers.
  - Generic candidate parameter helpers.
  - `record_real_001()` for baseline ledger/state setup.
- Modify `tests/test_next_real_run.py`
  - Remove packaged-template setup and old-template fake metrics.
  - Import shared helper functions.
  - Generalize next-run assertions.
- Modify `tests/test_candidate_injection_real_run.py`
  - Import shared helper functions.
  - Generalize candidate request parameters and expected errors.
  - Generalize fake metric values and ledger assertions.
- Modify `tests/test_optimizer_suggestion.py`
  - Import shared helper functions.
  - Generalize initialization/TuRBO parameter assertions and ledger rows.
- Modify `tests/test_optimizer_loop.py`
  - Import shared helper functions.
  - Keep optimizer-loop status assertions unchanged.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_next_real_run.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Record Phase 4 status and remaining deferred files.

## Task 0: Baseline Audit

**Files:**
- Read: `tests/test_next_real_run.py`
- Read: `tests/test_candidate_injection_real_run.py`
- Read: `tests/test_optimizer_suggestion.py`
- Read: `tests/test_optimizer_loop.py`
- Read: `tests/project_factory.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm worktree and release checkout state**

Run:

```bash
git status --short
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Dev checkout has only expected planning files or implementation files.
- Release checkout prints no modified files.

- [ ] **Step 2: Confirm current coupling matches the spec**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -n '"rise"\|"fall"\|"DC"' \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -R -n "from tests.test_next_real_run" tests || true
```

Expected before migration:

- Matches appear in the target cluster.
- Import matches show the three consumer files.

## Task 1: Create Shared Generic Real-Run Cluster Helper

**Files:**
- Create: `tests/real_run_cluster_helpers.py`
- Test: `tests/test_project_factory.py`

- [ ] **Step 1: Create helper module with generic setup and JSON functions**

Add `tests/real_run_cluster_helpers.py` with these responsibilities:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import RealResultRecordStatus, RealRunCheckStatus
from hermes_workflow.result_handoff import check_real_run
from tests.project_factory import create_approved_generic_project

DEFAULT_CREATED_AT_UTC = "2026-06-02T00:00:00Z"
DEFAULT_REAL_001_PREPARED_AT_UTC = "2026-06-02T00:20:00Z"
DEFAULT_REAL_001_RECORDED_AT_UTC = "2026-06-02T00:40:00Z"

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc=DEFAULT_CREATED_AT_UTC,
        max_evaluations=12,
    )
    prepare_real_run(project_dir, created_at_utc=DEFAULT_REAL_001_PREPARED_AT_UTC)
    return project_dir
```

This is the minimum helper shell. Later steps add functions as each migrated test
needs them.

- [ ] **Step 2: Add variable and metric lookup helpers**

Extend the helper with:

```python
def variable_names(project_dir: Path) -> tuple[str, str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    names = tuple(variable["name"] for variable in payload["variables"])
    assert len(names) == 2
    return names  # type: ignore[return-value]

def metric_names_for_run(project_dir: Path, run_id: str = "real_001") -> list[str]:
    request = load_json(
        project_dir / "runs" / "real" / run_id / "metric_extraction_request.json"
    )
    return [metric["name"] for metric in request["metrics"]]

def default_metric_values(project_dir: Path, run_id: str = "real_001") -> dict[str, float]:
    names = metric_names_for_run(project_dir, run_id)
    values: dict[str, float] = {}
    for index, name in enumerate(names):
        values[name] = 10.0 if index == 0 else 1.0e-6
    return values
```

If `mypy` is not part of this repo's checks, the `type: ignore` can be avoided by
returning `(names[0], names[1])` instead of casting.

- [ ] **Step 3: Add candidate parameter helpers**

Extend the helper with:

```python
def valid_candidate_parameters(
    project_dir: Path,
    *,
    int_value: str = "3",
    width_value: str = "0.3u",
) -> dict[str, str]:
    int_name, width_name = variable_names(project_dir)
    return {int_name: int_value, width_name: width_value}

def missing_candidate_parameters(project_dir: Path) -> dict[str, str]:
    int_name, _width_name = variable_names(project_dir)
    return {int_name: "3"}

def extra_candidate_parameters(project_dir: Path) -> dict[str, str]:
    params = valid_candidate_parameters(project_dir)
    params["EXTRA"] = "1"
    return params

def invalid_candidate_cases(project_dir: Path) -> list[tuple[dict[str, str], str]]:
    int_name, width_name = variable_names(project_dir)
    return [
        ({int_name: "1.5", width_name: "0.3u"}, f"{int_name} must be an integer"),
        ({int_name: "99", width_name: "0.3u"}, f"{int_name} is outside approved bounds"),
        ({int_name: "3", width_name: "0.3 um"}, f"{width_name} must use a Spectre-safe attached unit suffix"),
        ({int_name: "3", width_name: " 0.3u "}, f"{width_name} must use compact Spectre-safe formatting"),
        ({int_name: "3", width_name: "0.35u"}, f"{width_name} is not aligned to approved step"),
    ]
```

Keep these values inside the helper so the test files do not scatter new
template-like assumptions.

- [ ] **Step 4: Add fake result writers and baseline recorder**

Move the generic versions of the existing fake-result logic into the helper:

```python
def write_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = load_json(run_dir / "real_run_manifest.json")
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (psf_dir / "spectre.out").write_text("sanitized spectre output\n", encoding="utf-8")
    (metrics_dir / "ocean.log").write_text("sanitized ocean log\n", encoding="utf-8")
    (metrics_dir / "ocean_scalars.tsv").write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
        encoding="utf-8",
    )
    (run_dir / "spectre.stdout").write_text("sanitized stdout\n", encoding="utf-8")
    (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": prepared["candidate_id"],
            "status": "succeeded",
            "started_at_utc": "2026-06-02T00:30:00Z",
            "completed_at_utc": "2026-06-02T00:31:00Z",
            "simulator": {
                "engine": "spectre_x",
                "preset": "ax",
                "command_label": "spectre_ocean_adapter",
            },
            "prepared_input_scs": prepared["rendered_input_scs"],
            "prepared_input_sha256": prepared["rendered_input_sha256"],
            "log_file": f"runs/real/{run_id}/spectre.stdout",
            "artifact_files": [
                f"runs/real/{run_id}/spectre.stderr",
                f"runs/real/{run_id}/psf/spectre.out",
                f"runs/real/{run_id}/metrics/ocean.log",
                f"runs/real/{run_id}/metrics/ocean_scalars.tsv",
            ],
            "result_data": {
                "kind": "spectre_psf",
                "psf_dir": f"runs/real/{run_id}/psf",
                "spectre_out": f"runs/real/{run_id}/psf/spectre.out",
            },
            "metric_result_manifest": (
                f"runs/real/{run_id}/metrics/metric_result_manifest.json"
            ),
        },
    )

def write_metric_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = load_json(request_path)
    candidate = load_json(run_dir / "candidate.json")
    metrics_dir = run_dir / "metrics"
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = default_metric_values(project_dir, run_id)
    write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": candidate["candidate_id"],
            "backend": "spectre_ocean_batch",
            "status": "succeeded",
            "request_file": f"runs/real/{run_id}/metric_extraction_request.json",
            "request_sha256": sha256_file(request_path),
            "psf_dir": f"runs/real/{run_id}/psf",
            "ocean": {
                "mode": "nograph_replay",
                "return_code": 0,
                "script_file": f"runs/real/{run_id}/metrics/metric_probe.ocn",
                "script_sha256": sha256_file(script_path),
                "log_file": f"runs/real/{run_id}/metrics/ocean.log",
                "scalar_output_file": f"runs/real/{run_id}/metrics/ocean_scalars.tsv",
            },
            "metrics": [
                {
                    "name": name,
                    "status": "succeeded",
                    "value": value,
                    "value_text": f"{value:.12g}",
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name].get("result"),
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [],
                }
                for name, value in values.items()
            ],
            "issues": [],
        },
    )

def record_real_001(project_dir: Path) -> None:
    write_result_manifest(project_dir)
    write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS
    report = record_real_result(
        project_dir,
        recorded_at_utc=DEFAULT_REAL_001_RECORDED_AT_UTC,
    )
    assert report.status == RealResultRecordStatus.PASS
```

- [ ] **Step 5: Run a small smoke check**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py -q
```

Expected:

- `3 passed`

## Task 2: Migrate `tests/test_next_real_run.py`

**Files:**
- Modify: `tests/test_next_real_run.py`
- Test: `tests/test_next_real_run.py`

- [ ] **Step 1: Replace imports and delete local template setup**

Remove imports for:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from tests.report_helpers import write_pass_reports
```

Import shared helpers:

```python
from tests.real_run_cluster_helpers import (
    create_ready_project,
    load_json,
    record_real_001,
    variable_names,
    write_json,
    write_metric_result_manifest,
    write_result_manifest,
)
```

Remove local helper definitions that the shared helper now owns:

- `_write_json`
- `_load_json`
- `_create_ready_project`
- `_write_result_manifest`
- `_write_metric_result_manifest`
- `_record_real_001`
- local `TEMPLATE_TEXT`

For minimal churn, either update call sites to the new helper names or alias them
near the imports:

```python
_write_json = write_json
_load_json = load_json
_create_ready_project = create_ready_project
_record_real_001 = record_real_001
_write_result_manifest = write_result_manifest
_write_metric_result_manifest = write_metric_result_manifest
```

Prefer direct names if the file remains readable.

- [ ] **Step 2: Generalize coerced ledger metric mutation**

Replace the old hardcoded metric mutation with:

```python
metric_name = next(iter(row["metrics"]))
row["metrics"][metric_name] = str(row["metrics"][metric_name])
```

The assertion remains:

```python
with pytest.raises(ValueError, match="ledger row 1 is invalid"):
    prepare_next_real_run(project_dir)
```

- [ ] **Step 3: Generalize `real_002` package assertions**

In `test_prepare_next_real_run_writes_real_002_package`, replace the exact old
candidate dictionary with assertions tied to the generic project:

```python
expected_names = set(variable_names(project_dir))
assert set(candidate["parameters"]) == expected_names
assert all(candidate["parameters"][name] for name in expected_names)
assert candidate["parameters"] != load_json(
    project_dir / "runs" / "real" / "real_001" / "candidate.json"
)["parameters"]
```

Keep the existing checks for run ID, candidate source, candidate index,
selection policy, ledger snapshot hash, optimizer state hash, metric request
path, and lock cleanup.

- [ ] **Step 4: Run the migrated file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_next_real_run.py -q
```

Expected:

- All tests in `tests/test_next_real_run.py` pass.

## Task 3: Migrate `tests/test_candidate_injection_real_run.py`

**Files:**
- Modify: `tests/test_candidate_injection_real_run.py`
- Test: `tests/test_candidate_injection_real_run.py`

- [ ] **Step 1: Replace imports from `tests.test_next_real_run`**

Replace:

```python
from tests.test_next_real_run import _create_ready_project, _record_real_001
```

with:

```python
from tests.real_run_cluster_helpers import (
    create_ready_project,
    extra_candidate_parameters,
    invalid_candidate_cases,
    load_json,
    missing_candidate_parameters,
    record_real_001,
    valid_candidate_parameters,
    variable_names,
    write_json,
    write_metric_result_manifest,
    write_result_manifest,
)
```

Update call sites to use `create_ready_project()` and `record_real_001()`.

- [ ] **Step 2: Generalize `_candidate_request()`**

Change the helper so the default parameter dictionary comes from the generic
project:

```python
def _candidate_request(
    project_dir: Path,
    *,
    candidate_id: str = "candidate_000009",
    parameters: dict[str, str] | None = None,
    source: str = "optimizer_turbo_suggestion",
) -> Path:
    path = project_dir / "candidate_requests" / f"{candidate_id}.json"
    write_json(
        path,
        {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "source": source,
            "parameters": parameters or valid_candidate_parameters(project_dir),
            "metadata": {"optimizer": "turbo", "evaluation_index": 9},
        },
    )
    return path
```

- [ ] **Step 3: Reuse shared fake result writers**

Replace local candidate result and metric-result writers with thin wrappers, if
needed for current function names:

```python
def _write_candidate_result_manifest(project_dir: Path, *, run_id: str) -> None:
    write_result_manifest(project_dir, run_id=run_id)

def _write_candidate_metric_result_manifest(project_dir: Path, *, run_id: str) -> None:
    write_metric_result_manifest(project_dir, run_id=run_id)
```

This keeps `tests/test_optimizer_loop.py` imports stable while removing duplicated
old metric names.

- [ ] **Step 4: Generalize missing, extra, and invalid parameter tests**

Use the helper functions:

```python
parameters=missing_candidate_parameters(project_dir)
parameters=extra_candidate_parameters(project_dir)
```

For invalid values, replace the static `pytest.mark.parametrize` values with a
loop inside the test:

```python
def test_prepare_candidate_real_run_rejects_invalid_values(tmp_path: Path) -> None:
    project_dir = create_ready_project(tmp_path)
    record_real_001(project_dir)
    for parameters, message in invalid_candidate_cases(project_dir):
        request = _candidate_request(project_dir, parameters=parameters)
        with pytest.raises(ValueError, match=re.escape(message)):
            prepare_candidate_real_run(project_dir, candidate_file=request)
        request.unlink()
```

Add `import re` if using `re.escape`.

- [ ] **Step 5: Generalize candidate and ledger assertions**

Replace exact old dictionaries with `valid_candidate_parameters(project_dir)` or
data loaded from generated artifacts:

```python
expected_parameters = valid_candidate_parameters(project_dir)
assert candidate["parameters"] == expected_parameters
```

For duplicate ledger parameter tests, load the recorded baseline parameters:

```python
first_candidate = load_json(project_dir / "runs" / "real" / "real_001" / "candidate.json")
request = _candidate_request(project_dir, parameters=first_candidate["parameters"])
```

For prepared duplicate tests, create distinct valid generic parameters by passing
different `int_value` / `width_value` values within factory bounds.

- [ ] **Step 6: Run candidate injection tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_candidate_injection_real_run.py -q
```

Expected:

- All candidate injection tests pass.

## Task 4: Migrate `tests/test_optimizer_suggestion.py`

**Files:**
- Modify: `tests/test_optimizer_suggestion.py`
- Test: `tests/test_optimizer_suggestion.py`

- [ ] **Step 1: Replace imports from `tests.test_next_real_run`**

Replace:

```python
from tests.test_next_real_run import _create_ready_project, _load_json, _record_real_001
```

with:

```python
from tests.real_run_cluster_helpers import (
    create_ready_project,
    load_json,
    record_real_001,
    valid_candidate_parameters,
    variable_names,
    write_json,
)
```

Update call sites.

- [ ] **Step 2: Generalize initialization fallback assertion**

Replace the old not-equal dictionary with a generic baseline comparison:

```python
baseline = load_json(
    project_dir / "runs" / "real" / "real_001" / "candidate.json"
)["parameters"]
assert set(payload["parameters"]) == set(variable_names(project_dir))
assert payload["parameters"] != baseline
```

- [ ] **Step 3: Generalize maximum-evaluations ledger rows**

Replace hardcoded four-variable rows with a small valid generic sequence:

```python
def _sample_parameters(project_dir: Path, index: int) -> dict[str, str]:
    int_values = ["1", "2", "3", "4", "5", "1", "2", "3"]
    width_values = ["0.1u", "0.2u", "0.3u", "0.4u", "0.5u", "0.2u", "0.3u", "0.4u"]
    return valid_candidate_parameters(
        project_dir,
        int_value=int_values[index],
        width_value=width_values[index],
    )
```

Use `_sample_parameters(project_dir, index)` when writing synthetic ledger rows.

- [ ] **Step 4: Generalize TuRBO monkeypatch and assertion**

The generic project has two variables. Replace the old four-value raw candidate
with two values:

```python
monkeypatch.setattr(
    "hermes_workflow.optimizer_suggestion._suggest_turbo_raw_candidate",
    lambda *args, **kwargs: [3.0, 0.3],
)
```

Then assert against generated generic parameters:

```python
assert payload["parameters"] == valid_candidate_parameters(project_dir)
```

If the actual formatter returns an equivalent unit-normalized string, use the
actual generated value from the passing helper contract and keep the assertion
exact.

- [ ] **Step 5: Run optimizer suggestion tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_suggestion.py -q
```

Expected:

- All optimizer suggestion tests pass.

## Task 5: Migrate `tests/test_optimizer_loop.py`

**Files:**
- Modify: `tests/test_optimizer_loop.py`
- Test: `tests/test_optimizer_loop.py`

- [ ] **Step 1: Replace imports from `tests.test_next_real_run`**

Replace:

```python
from tests.test_next_real_run import _create_ready_project, _record_real_001
```

with:

```python
from tests.real_run_cluster_helpers import create_ready_project, record_real_001
```

Keep imports from `tests.test_candidate_injection_real_run` only if the wrapper
functions remain there for backward compatibility.

- [ ] **Step 2: Update helper call sites**

Replace:

```python
project_dir = _create_ready_project(tmp_path)
_record_real_001(project_dir)
```

with:

```python
project_dir = create_ready_project(tmp_path)
record_real_001(project_dir)
```

The status, run ID, candidate ID, report, and ledger-count assertions should
remain the same.

- [ ] **Step 3: Run optimizer loop tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_loop.py -q
```

Expected:

- All optimizer loop tests pass.

## Task 6: Shrink Guard and Update Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove `test_next_real_run.py` from the allowlist**

In `tests/test_template_coupling_guard.py`, remove:

```python
"tests/test_next_real_run.py",
```

Expected allowlist count after this change: 18.

- [ ] **Step 2: Update inventory**

Update
`docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
with:

- Phase 4 status.
- New helper file.
- Four migrated cluster files.
- Guard count 19 -> 18.
- Exact verification command results.
- Remaining deferred groups.

Keep prior Phase 1-3 history intact.

- [ ] **Step 3: Run guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

- `1 passed`

## Task 7: Cluster and Full Verification

**Files:**
- Verify: cluster tests, guard, full suite, release checkout

- [ ] **Step 1: Run cluster tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  -q
```

Expected:

- All tests in the four-file cluster pass.

- [ ] **Step 2: Run drift checks**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT" \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -n '"rise"\|"fall"\|"DC"' \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py || true
grep -R -n "from tests.test_next_real_run" tests || true
```

Expected:

- No matches in the first two commands.
- No cross-test imports from `tests.test_next_real_run`.

- [ ] **Step 3: Run Phase 1-4 regression group**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py \
  tests/test_real_run.py \
  tests/test_real_run_recovery.py \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  -q
```

Expected:

- Regression group passes.

- [ ] **Step 4: Run final checks**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Full suite passes.
- Ruff passes.
- Diff check is clean.
- Release checkout prints no modified files.

## Stop Conditions

Stop and report instead of broadening scope if:

- a production source change appears necessary,
- a consumer requires migration of additional unrelated tests,
- a backend-specific optimizer test becomes involved,
- the generic factory needs behavior beyond its two-variable/two-metric contract,
- full-suite failures reveal a separate existing product bug.
