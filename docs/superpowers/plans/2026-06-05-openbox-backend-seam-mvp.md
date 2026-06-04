# OpenBox Backend Seam MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow fake OpenBox backend seam that writes Hermes-compatible optimizer artifacts without replacing the working native TuRBO real-tool backend.

**Architecture:** Keep Spectre/OCEAN, candidate packaging, run acceptance, and completion reporting as the foundation. Add backend-neutral optimizer report/evaluation artifact loading, then build an optional OpenBox fake runner that can feed those artifacts into the existing C-25/C-26 read-only path.

**Tech Stack:** Python, Typer CLI, pytest, existing Hermes schemas, optional OpenBox import through lazy dependency handling.

---

## Boundaries

- Do not run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or an execution agent.
- Do not replace or delete `src/hermes_workflow/native_turbo.py`.
- Do not parse PSF or waveform data in Python.
- Do not rewrite OCEAN/ADE Calculator formulas.
- Do not vendor OpenBox or add it to required project dependencies.
- Do not create a daemon, service, database, distributed scheduler, or broad optimizer framework.
- Keep OpenBox real-tool acceptance out of C-27.

## File Map

- Create `src/hermes_workflow/optimizer_artifacts.py`
  - Own backend-neutral optimizer report/evaluation constants and loaders.
  - Prefer `reports/optimizer_run_report.json` and `reports/optimizer_evaluations.jsonl`.
  - Fall back to existing native TuRBO report paths for backward compatibility.
- Create `src/hermes_workflow/openbox_backend.py`
  - Own optional OpenBox fake runner.
  - Import OpenBox lazily.
  - Reuse existing Hermes quantization and objective/constraint scoring.
  - Write backend-neutral fake artifacts only.
- Modify `src/hermes_workflow/optimizer_acceptance.py`
  - Read optimizer artifacts through `optimizer_artifacts.py`.
  - Accept manifest-free fake OpenBox artifacts only when explicitly marked as fake.
  - Preserve strict manifest checks for real artifacts.
- Modify `src/hermes_workflow/optimizer_completion.py`
  - Read optimizer artifacts through `optimizer_artifacts.py`.
  - Preserve existing C-26 decision behavior.
- Modify `src/hermes_workflow/cli.py`
  - Add `hermes-workflow run-openbox-fake PROJECT_DIR --max-evals N --batch-size N`.
- Create `tests/test_optimizer_artifacts.py`
  - Backend-neutral artifact loader coverage.
- Create `tests/test_openbox_backend.py`
  - Fake OpenBox runner and optional-dependency coverage.
- Modify `tests/test_optimizer_acceptance.py`
  - Fake OpenBox acceptance and real-style missing-manifest rejection coverage.
- Modify `tests/test_optimizer_completion.py`
  - Completion report can summarize accepted backend-neutral fake artifacts.
- Modify `tests/test_cli.py` or add focused CLI tests where existing CLI patterns fit best.

---

### Task 1: Backend-Neutral Optimizer Artifact Loader

**Files:**
- Create: `src/hermes_workflow/optimizer_artifacts.py`
- Test: `tests/test_optimizer_artifacts.py`
- Modify: `src/hermes_workflow/optimizer_acceptance.py`
- Modify: `src/hermes_workflow/optimizer_completion.py`

- [x] **Step 1: Write tests for neutral-first and legacy fallback loading**

Add `tests/test_optimizer_artifacts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.optimizer_artifacts import (
    EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_EVALUATIONS_RELATIVE,
    LEGACY_NATIVE_REPORT_RELATIVE,
    REPORT_RELATIVE,
    load_optimizer_artifacts,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_loader_prefers_backend_neutral_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / REPORT_RELATIVE,
        {"status": "completed", "backend": "openbox", "evaluation_count": 1},
    )
    _write_jsonl(
        tmp_path / EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "feasible"}],
    )
    _write_json(
        tmp_path / LEGACY_NATIVE_REPORT_RELATIVE,
        {"status": "completed", "backend": "turbo", "evaluation_count": 99},
    )
    _write_jsonl(
        tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "legacy"}],
    )

    artifacts = load_optimizer_artifacts(tmp_path, [])

    assert artifacts.source == "backend_neutral"
    assert artifacts.report["backend"] == "openbox"
    assert artifacts.traces == [{"evaluation_index": 1, "status": "feasible"}]


def test_loader_falls_back_to_legacy_native_turbo_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / LEGACY_NATIVE_REPORT_RELATIVE,
        {"status": "completed", "evaluation_count": 1},
    )
    _write_jsonl(
        tmp_path / LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        [{"evaluation_index": 1, "status": "feasible"}],
    )

    artifacts = load_optimizer_artifacts(tmp_path, [])

    assert artifacts.source == "legacy_native_turbo"
    assert artifacts.report["status"] == "completed"
    assert artifacts.traces[0]["status"] == "feasible"
```

- [x] **Step 2: Run tests to confirm the loader module is missing**

Run:

```bash
python3 -m pytest tests/test_optimizer_artifacts.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'hermes_workflow.optimizer_artifacts'`.

- [x] **Step 3: Implement `optimizer_artifacts.py`**

Create `src/hermes_workflow/optimizer_artifacts.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPORT_RELATIVE = Path("reports/optimizer_run_report.json")
EVALUATIONS_RELATIVE = Path("reports/optimizer_evaluations.jsonl")
LEGACY_NATIVE_REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
LEGACY_NATIVE_EVALUATIONS_RELATIVE = Path("reports/native_turbo_optimizer_evaluations.jsonl")


@dataclass(frozen=True)
class OptimizerArtifacts:
    source: str
    report_relative: Path
    evaluations_relative: Path
    report: dict[str, Any]
    traces: list[dict[str, Any]]


def load_optimizer_artifacts(project_dir: str | Path, issues: list[str]) -> OptimizerArtifacts:
    project_root = Path(project_dir)
    neutral_report = project_root / REPORT_RELATIVE
    neutral_evaluations = project_root / EVALUATIONS_RELATIVE
    if neutral_report.exists() or neutral_evaluations.exists():
        return OptimizerArtifacts(
            source="backend_neutral",
            report_relative=REPORT_RELATIVE,
            evaluations_relative=EVALUATIONS_RELATIVE,
            report=_load_json(neutral_report, issues),
            traces=_load_jsonl(neutral_evaluations, issues),
        )

    return OptimizerArtifacts(
        source="legacy_native_turbo",
        report_relative=LEGACY_NATIVE_REPORT_RELATIVE,
        evaluations_relative=LEGACY_NATIVE_EVALUATIONS_RELATIVE,
        report=_load_json(project_root / LEGACY_NATIVE_REPORT_RELATIVE, issues),
        traces=_load_jsonl(project_root / LEGACY_NATIVE_EVALUATIONS_RELATIVE, issues),
    )


def _load_json(path: Path, issues: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(f"missing file: {path}")
        return {}
    except json.JSONDecodeError as exc:
        issues.append(f"invalid JSON: {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"JSON file must contain an object: {path}")
        return {}
    return payload


def _load_jsonl(path: Path, issues: list[str]) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(f"missing file: {path}")
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"invalid JSONL row: {path}:{line_number}: {exc}")
            continue
        if not isinstance(payload, dict):
            issues.append(f"JSONL row must contain an object: {path}:{line_number}")
            continue
        rows.append(payload)
    return rows
```

- [x] **Step 4: Refactor C-25/C-26 readers to use the loader without changing behavior**

In `src/hermes_workflow/optimizer_acceptance.py`, replace direct native report loading:

```python
from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts
```

Then inside `check_optimizer_run`:

```python
artifacts = load_optimizer_artifacts(project_root, issues)
native_report = artifacts.report
traces = artifacts.traces
```

In `src/hermes_workflow/optimizer_completion.py`, make the same change inside `summarize_optimizer_run`:

```python
from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts
```

```python
artifacts = load_optimizer_artifacts(project_root, issues)
native_report = artifacts.report
traces = artifacts.traces
```

Keep existing constant names in those modules only if tests still import them; otherwise remove unused native report constants.

- [x] **Step 5: Verify Task 1**

Run:

```bash
python3 -m pytest tests/test_optimizer_artifacts.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/optimizer_artifacts.py src/hermes_workflow/optimizer_acceptance.py src/hermes_workflow/optimizer_completion.py tests/test_optimizer_artifacts.py
```

Expected: all selected tests pass and ruff reports no issues.

---

### Task 2: Fake OpenBox Backend Runner Library

**Files:**
- Create: `src/hermes_workflow/openbox_backend.py`
- Test: `tests/test_openbox_backend.py`
- Reuse: `src/hermes_workflow/native_turbo.py`
- Reuse: `src/hermes_workflow/optimizer_artifacts.py`

- [x] **Step 1: Write tests with an injected advisor**

Add `tests/test_openbox_backend.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.openbox_backend import run_openbox_fake_optimization
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from tests.real_run_smoke_helpers import create_approved_real_project


class FakeAdvisor:
    def __init__(self) -> None:
        self.updated_batches = 0
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        batch = self._batches.pop(0)
        return batch[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        self.updated_batches += 1
        assert observations


def test_openbox_fake_runner_writes_backend_neutral_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    result = run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisor(),
    )

    report = json.loads((project_dir / REPORT_RELATIVE).read_text())
    rows = [
        json.loads(line)
        for line in (project_dir / EVALUATIONS_RELATIVE).read_text().splitlines()
    ]

    assert result.evaluation_count == 4
    assert report["backend"] == "openbox"
    assert report["execution_mode"] == "fake"
    assert report["evaluations"] == EVALUATIONS_RELATIVE.as_posix()
    assert len(rows) == 4
    assert rows[0]["parameters"]["WN"].endswith("u")
    assert rows[0]["result_manifest"] is None
    assert rows[0]["metric_result_manifest"] is None
    assert rows[0]["batch_id"] == "batch_001"


def test_openbox_fake_runner_requires_openbox_when_no_advisor_is_injected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import hermes_workflow.openbox_backend as module

    monkeypatch.setattr(module, "_load_openbox", lambda: (_ for _ in ()).throw(RuntimeError("OpenBox is not installed")))

    try:
        run_openbox_fake_optimization(create_approved_real_project(tmp_path), max_evals=1, batch_size=1)
    except RuntimeError as exc:
        assert "OpenBox is not installed" in str(exc)
    else:
        raise AssertionError("expected missing OpenBox dependency error")
```

- [x] **Step 2: Run tests to confirm the module is missing**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'hermes_workflow.openbox_backend'`.

- [x] **Step 3: Implement fake runner and report writer**

Create `src/hermes_workflow/openbox_backend.py`:

```python
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from hermes_workflow.native_turbo import (
    NativeTurboEvaluationTrace,
    NativeTurboRunResult,
    evaluate_candidate_objective,
    load_native_turbo_contract,
    quantize_candidate,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE, REPORT_RELATIVE
from tests.real_run_smoke_helpers import create_approved_real_project


OPENBOX_BACKEND = "openbox"
FAKE_EXECUTION_MODE = "fake"
OPENBOX_BATCH_PHASE = "openbox_batch"


AdvisorFactory = Callable[[object, int], object]


@dataclass(frozen=True)
class FakeMetricObservation:
    metrics: dict[str, float]
    issues: list[str]


def run_openbox_fake_optimization(
    project_dir: str | Path,
    *,
    max_evals: int,
    batch_size: int,
    advisor_factory: AdvisorFactory | None = None,
    random_seed: int | None = None,
) -> NativeTurboRunResult:
    project_root = Path(project_dir)
    contract = load_native_turbo_contract(project_root)
    seed = random_seed if random_seed is not None else contract.optimizer.optimizer.random_seed
    advisor = (
        advisor_factory(_build_openbox_space(contract.variables), seed)
        if advisor_factory is not None
        else _build_openbox_advisor(contract.variables, seed)
    )

    traces: list[NativeTurboEvaluationTrace] = []
    batch_index = 0
    while len(traces) < max_evals:
        batch_index += 1
        remaining = max_evals - len(traces)
        selected_batch_size = min(batch_size, remaining)
        suggestions = advisor.get_suggestions(batch_size=selected_batch_size)
        observations: list[Any] = []
        for slot, suggestion in enumerate(suggestions, start=1):
            evaluation_index = len(traces) + 1
            raw_x = _raw_values_from_suggestion(contract.variables, suggestion)
            parameters = quantize_candidate(contract.variables, raw_x)
            metric_observation = _fake_inverter_metrics(parameters)
            objective_eval = evaluate_candidate_objective(
                contract.metrics,
                contract.optimizer,
                metric_observation.metrics,
            )
            trace = NativeTurboEvaluationTrace(
                evaluation_index=evaluation_index,
                run_id=f"fake_{evaluation_index:03d}",
                selection_phase=OPENBOX_BATCH_PHASE,
                raw_x=raw_x,
                parameters=parameters,
                status=objective_eval.status,
                objective=objective_eval.objective,
                fom=objective_eval.fom,
                constraint_penalty=objective_eval.constraint_penalty,
                metrics=metric_observation.metrics,
                result_manifest=None,
                metric_result_manifest=None,
                issues=[*objective_eval.issues, *metric_observation.issues],
                batch_id=f"batch_{batch_index:03d}",
                batch_slot=slot,
                batch_size=selected_batch_size,
                batch_worker_count=selected_batch_size,
                max_parallel_jobs=batch_size,
                threads_per_run=None,
                parallel_jobs=batch_size,
            )
            traces.append(trace)
            observations.append(_make_openbox_observation(trace))
        advisor.update_observations(observations)

    result = NativeTurboRunResult(
        evaluation_count=len(traces),
        traces=traces,
        best_trace=_best_trace(traces),
    )
    report_path, evaluations_path = write_openbox_fake_reports(project_root, result)
    return NativeTurboRunResult(
        evaluation_count=result.evaluation_count,
        traces=result.traces,
        best_trace=result.best_trace,
        report_path=report_path,
        evaluations_path=evaluations_path,
    )
```

Then add helper functions in the same file:

- `_load_openbox()`: imports `openbox.Advisor`, `openbox.Observation`, and `openbox.space as sp`, raising `RuntimeError("OpenBox is not installed; install it in the active environment to run the OpenBox backend")` on `ImportError`.
- `_build_openbox_space(variables)`: maps integer variables to `sp.Int` and continuous-step variables to `sp.Real`; use numeric values without units only for OpenBox's internal space.
- `_build_openbox_advisor(variables, seed)`: creates `Advisor(..., num_objectives=1, num_constraints=len(metrics.constraints), initial_trials=2 * len(variables.variables), random_state=seed)`.
- `_raw_values_from_suggestion(variables, suggestion)`: returns raw numeric values in approved variable order.
- `_fake_inverter_metrics(parameters)`: deterministic fake model returning `rise`, `fall`, and `DC`.
- `_make_openbox_observation(trace)`: creates OpenBox `Observation` when OpenBox is installed; for injected fake advisors, returning a simple object with `objectives` and `constraints` is sufficient.
- `_best_trace(traces)`: returns the feasible trace with lowest objective, falling back to lowest finite objective.
- `write_openbox_fake_reports(project_dir, result)`: writes backend-neutral report and JSONL evaluation artifacts.

Keep the helper functions local to this file. Do not move shared quantization out of `native_turbo.py` during C-27.

- [x] **Step 4: Verify Task 2**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py tests/test_openbox_backend.py
```

Expected: tests pass without requiring OpenBox to be installed.

---

### Task 3: Acceptance And Completion Compatibility

**Files:**
- Modify: `src/hermes_workflow/optimizer_acceptance.py`
- Modify: `src/hermes_workflow/optimizer_completion.py`
- Test: `tests/test_optimizer_acceptance.py`
- Test: `tests/test_optimizer_completion.py`
- Test: `tests/test_openbox_backend.py`

- [x] **Step 1: Add acceptance tests for fake OpenBox and missing-manifest real rows**

In `tests/test_optimizer_acceptance.py`, add:

```python
import json
from pathlib import Path

from tests.real_run_smoke_helpers import create_approved_real_project


class FakeAdvisorForAcceptance:
    def __init__(self) -> None:
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def write_backend_neutral_optimizer_report(
    project_dir: Path,
    *,
    backend: str,
    execution_mode: str,
    rows: list[dict],
) -> None:
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "optimizer_run_report.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "backend": backend,
                "execution_mode": execution_mode,
                "evaluation_count": len(rows),
                "best_candidate": rows[0] if rows else None,
                "evaluations": "reports/optimizer_evaluations.jsonl",
                "issues": [],
                "batch_summary": {
                    "batch_count": 1,
                    "max_batch_worker_count": 1,
                    "status_counts": {"feasible": len(rows)},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "optimizer_evaluations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_check_optimizer_run_accepts_fake_openbox_without_manifests(
    tmp_path: Path,
) -> None:
    from hermes_workflow.openbox_backend import run_openbox_fake_optimization

    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForAcceptance(),
    )

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.result_manifest_count == 0
    assert report.metric_manifest_count == 0
    assert report.status_counts


def test_check_optimizer_run_rejects_real_backend_rows_without_manifests(
    tmp_path: Path,
) -> None:
    write_backend_neutral_optimizer_report(
        tmp_path,
        backend="openbox",
        execution_mode="real",
        rows=[{"evaluation_index": 1, "run_id": "real_001", "status": "feasible"}],
    )

    report = check_optimizer_run(tmp_path)

    assert report.status == "rejected"
    assert any("manifest" in issue for issue in report.issues)
```

- [x] **Step 2: Add completion test for accepted backend-neutral artifacts**

In `tests/test_optimizer_completion.py`, add:

```python
from pathlib import Path

from tests.real_run_smoke_helpers import create_approved_real_project


class FakeAdvisorForCompletion:
    def __init__(self) -> None:
        self._batches = [
            [
                {"FN": 2, "WN": 0.2, "WP": 0.4},
                {"FN": 4, "WN": 1.0, "WP": 1.2},
            ],
            [
                {"FN": 6, "WN": 1.4, "WP": 1.6},
                {"FN": 8, "WN": 2.0, "WP": 2.2},
            ],
        ]

    def get_suggestions(self, batch_size: int) -> list[dict[str, float]]:
        return self._batches.pop(0)[:batch_size]

    def update_observations(self, observations: list[object]) -> None:
        assert observations


def test_summarize_optimizer_run_reads_backend_neutral_report(
    tmp_path: Path,
) -> None:
    from hermes_workflow.openbox_backend import run_openbox_fake_optimization
    from hermes_workflow.optimizer_acceptance import check_optimizer_run

    project_dir = create_approved_real_project(tmp_path)
    run_openbox_fake_optimization(
        project_dir,
        max_evals=4,
        batch_size=2,
        advisor_factory=lambda _space, _seed: FakeAdvisorForCompletion(),
    )
    check_optimizer_run(project_dir)

    report = summarize_optimizer_run(project_dir)

    assert report.status == "pass"
    assert report.evaluation_count == 4
    assert report.best_observed is not None
```

- [x] **Step 3: Run tests to verify current acceptance rejects fake rows**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py::test_check_optimizer_run_accepts_fake_openbox_without_manifests -q
```

Expected: fails because `check_optimizer_run` currently requires real manifests for completed optimizer reports.

- [x] **Step 4: Implement fake-mode acceptance**

In `src/hermes_workflow/optimizer_acceptance.py`:

1. Use `load_optimizer_artifacts(project_root, issues)`.
2. Compute:

```python
is_fake = native_report.get("execution_mode") == "fake"
backend = _string_value(native_report.get("backend"))
```

3. When iterating trace rows, if `is_fake` is true:

```python
if result_relative or metric_relative:
    warnings.append(f"{run_id} fake row includes manifest paths")
continue
```

4. After the loop, skip the existing `no result manifests exist` rejection only when `is_fake` is true.
5. Reject fake mode unless `backend == "openbox"`.

Keep real-mode logic unchanged.

- [x] **Step 5: Update C-26 to use backend-neutral artifacts**

In `src/hermes_workflow/optimizer_completion.py`, after Task 1 loader refactor, no special fake-mode logic should be needed. Confirm the completion report reads the backend-neutral report and JSONL rows through `load_optimizer_artifacts`.

- [x] **Step 6: Verify Task 3**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/optimizer_acceptance.py src/hermes_workflow/optimizer_completion.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py
```

Expected: tests pass and ruff reports no issues.

---

### Task 4: CLI Wiring And Fake End-To-End Smoke

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Test: `tests/test_cli.py` or `tests/test_openbox_backend.py`
- Verify: existing C-25/C-26 tests

- [x] **Step 1: Add CLI tests**

Add focused CLI coverage using `CliRunner`:

```python
def test_run_openbox_fake_cli_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    import json
    from pathlib import Path

    from typer.testing import CliRunner
    import hermes_workflow.cli as cli_module

    project_dir = tmp_path / "bridge_test_inv"

    def fake_run(project_dir: Path, *, max_evals: int, batch_size: int):
        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "optimizer_run_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "backend": "openbox",
                    "execution_mode": "fake",
                    "evaluation_count": max_evals,
                    "best_candidate": None,
                    "evaluations": "reports/optimizer_evaluations.jsonl",
                    "issues": [],
                    "batch_summary": {"batch_count": 0, "max_batch_worker_count": batch_size, "status_counts": {}},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (reports_dir / "optimizer_evaluations.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(cli_module, "run_openbox_fake_optimization", fake_run)

    result = CliRunner().invoke(
        cli_module.app,
        ["run-openbox-fake", str(project_dir), "--max-evals", "4", "--batch-size", "2"],
    )

    assert result.exit_code == 0
    assert "optimizer_run_report.json" in result.output
```

- [x] **Step 2: Run CLI test to verify command is missing**

Run:

```bash
python3 -m pytest tests/test_cli.py::test_run_openbox_fake_cli_writes_artifacts -q
```

Expected: fails because `run-openbox-fake` is not registered.

- [x] **Step 3: Add CLI command**

In `src/hermes_workflow/cli.py`, import:

```python
from hermes_workflow.openbox_backend import run_openbox_fake_optimization
```

Add:

```python
@app.command("run-openbox-fake")
def run_openbox_fake(
    project_dir: Path,
    max_evals: int = typer.Option(40, "--max-evals", min=1),
    batch_size: int = typer.Option(4, "--batch-size", min=1),
) -> None:
    try:
        result = run_openbox_fake_optimization(
            project_dir,
            max_evals=max_evals,
            batch_size=batch_size,
        )
    except Exception as exc:
        _raise_cli_error(str(exc))
    typer.echo(
        "openbox fake optimizer artifacts written: "
        f"{result.report_path} and {result.evaluations_path}"
    )
```

Use existing CLI error helper patterns in `cli.py`; if the helper name differs, match the local pattern rather than introducing a second error style.

- [x] **Step 4: Run fake end-to-end smoke without real tools**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_cli.py -q
```

Expected: fake OpenBox runner can write artifacts, C-25 can accept them, and C-26 can summarize them without real manifests.

Implementation note: the missing-command red check was not kept as a separate
artifact because the focused CLI test and command registration were applied in
one small step. Final verification covers command registration, path output, and
fake artifact wiring.

- [x] **Step 5: Optional local OpenBox smoke**

Only if OpenBox is installed in the active environment, run:

```bash
python3 - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("openbox") else 2)
PY
```

If exit code is `0`, run one fake CLI command against a copied fixture project:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_openbox_fake_runner_writes_backend_neutral_artifacts -q
```

If OpenBox is not installed, record that the optional smoke was skipped. Do not install dependencies during Task 4 unless the user explicitly authorizes it.

---

### Task 5: Final Verification, Docs, And Review Gate

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-openbox-backend-seam-mvp.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Optional milestone update: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [x] **Step 1: Run focused verification**

Run:

```bash
python3 -m pytest tests/test_optimizer_artifacts.py tests/test_openbox_backend.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 -m pytest tests/test_native_turbo.py tests/test_optimizer_task_package.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```

Expected: all commands pass.

- [x] **Step 2: Update docs and plan status**

Update:

- checked boxes in `docs/superpowers/plans/2026-06-05-openbox-backend-seam-mvp.md`;
- `docs/CURRENT_TASK_STATE.json`:
  - `current_scope`: `C-27 OpenBox Backend Seam MVP`
  - `current_status`: C-27 complete, fake-only, verified-only or reviewed depending on review evidence
  - `active_spec`: `docs/superpowers/specs/2026-06-05-openbox-backend-seam-mvp-design.md`
  - `active_plan`: `docs/superpowers/plans/2026-06-05-openbox-backend-seam-mvp.md`
  - `next_allowed_action`: decide whether to run one real 100-evaluation OpenBox backend acceptance or keep OpenBox experimental
  - route audit: no real-tool route change; TuRBO remains real backend until real OpenBox acceptance exists
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: short C-27 completion entry.

Update `docs/COMPACT_RESUME_CHECKPOINT.md` only if the user is about to compact context or if the next action changes materially after C-27.

- [x] **Step 3: Review gate**

Because C-27 touches report-loading and acceptance behavior, request review if subagent tooling is available:

- spec compliance: fake OpenBox mode does not weaken real-run manifest checks;
- code quality: artifact loader and fake runner remain narrow and do not create a broad framework.

If no review tooling is available, mark `review_status = verified-only` and record that no real-tool or production backend replacement happened.

- [x] **Step 4: Commit**

Run:

```bash
git status --short
git add src/hermes_workflow/optimizer_artifacts.py src/hermes_workflow/openbox_backend.py src/hermes_workflow/optimizer_acceptance.py src/hermes_workflow/optimizer_completion.py src/hermes_workflow/cli.py tests/test_optimizer_artifacts.py tests/test_openbox_backend.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_cli.py docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-05-openbox-backend-seam-mvp.md
git commit -m "feat: add OpenBox fake backend seam"
```

Adjust the `git add` pathspec to include only files actually changed. Do not stage OpenBox clone files, `/tmp` evidence, raw input decks, Cadence logs, PSF/raw data, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.

## Self-Review Checklist

- Spec coverage:
  - backend-neutral artifacts: Task 1
  - fake OpenBox runner: Task 2
  - C-25/C-26 compatibility: Task 3
  - CLI fake smoke: Task 4
  - docs/final verification: Task 5
- Placeholder scan: no placeholder tasks are intentionally left open; each task has paths, commands, and expected results.
- Route alignment:
  - no real tools in C-27;
  - no TuRBO replacement;
  - no broad framework;
  - no PSF parsing or formula rewriting.
