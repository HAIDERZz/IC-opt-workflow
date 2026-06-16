# Optimizer Run Acceptance Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `hermes-workflow check-optimizer-run PROJECT_DIR`, a deterministic supervisor/Hermes audit for completed native TuRBO optimizer handoff artifacts.

**Architecture:** Reuse the existing native TuRBO report, JSONL trace, result manifests, metric manifests, state, and ledger artifacts. The new checker reads and cross-checks returned files, writes one sanitized acceptance report, and never runs real tools.

**Tech Stack:** Python 3.11+, existing Hermes workflow modules, Typer CLI, pytest, ruff.

---

## Scope Guard

Allowed:

- read existing native optimizer reports and traces;
- read existing real-run result and metric manifests;
- summarize status counts, settings consistency, best candidate, and issues;
- write `reports/optimizer_run_acceptance_report.json`;
- expose `hermes-workflow check-optimizer-run PROJECT_DIR`.

Forbidden:

- run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or execution agents;
- rerun candidates or retry OCEAN;
- create a scheduler, daemon, database, service, or broad optimizer framework;
- parse PSF or waveform data in Python;
- rewrite OCEAN formulas;
- change approved metric formulas;
- flatten or replace the native Maestro/ADE netlist layout;
- commit raw Cadence artifacts.

## File Plan

- Create: `src/hermes_workflow/optimizer_acceptance.py`
  - Library function and report model for optimizer-run acceptance audit.
- Modify: `src/hermes_workflow/cli.py`
  - Add `check-optimizer-run` command.
- Create: `tests/test_optimizer_acceptance.py`
  - Focused fake-artifact tests for accepted and rejected optimizer runs.
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify as needed: this plan file.

## Task 1: Library Acceptance Report

**Risk:** Medium. Deterministic report/check logic, no real tools.

**Status:** Complete, verified-only.

**Files:**

- Create: `src/hermes_workflow/optimizer_acceptance.py`
- Create: `tests/test_optimizer_acceptance.py`

- [x] **Step 1: Write accepted-run fixture test**

Add a helper in `tests/test_optimizer_acceptance.py` that writes a minimal fake project:

```python
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

The accepted fixture should include:

- `reports/native_turbo_optimizer_report.json` with `status = completed`, `evaluation_count = 2`, `batch_summary.status_counts = {"feasible": 1, "metric_check_failed": 1}`;
- `reports/native_turbo_optimizer_evaluations.jsonl` with two trace rows;
- `runs/real/real_001/result_manifest.json` with `status = succeeded`;
- `runs/real/real_001/metrics/metric_result_manifest.json` with `status = succeeded`;
- `runs/real/real_002/result_manifest.json` with `status = succeeded`;
- `runs/real/real_002/metrics/metric_result_manifest.json` with `status = failed`;
- optional `state/optimizer_state.json` with `status = running`;
- `ledger/experiment_ledger.jsonl` with one line.

Test:

```python
def test_check_optimizer_run_accepts_completed_manifest_audit(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)

    report = check_optimizer_run(project_dir)

    assert report.status == "accepted"
    assert report.evaluation_count == 2
    assert report.result_manifest_count == 2
    assert report.metric_manifest_count == 2
    assert report.status_counts == {"feasible": 1, "metric_check_failed": 1}
    assert report.settings["preset"] == "ax"
    assert report.settings["threads_per_run"] == 10
    assert report.settings["parallel_jobs"] == 10
    assert report.settings["output_format"] == "psfxl"
    assert report.issues == []
    assert report.report_path == project_dir / "reports/optimizer_run_acceptance_report.json"
```

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py -q
```

Expected: fail because `optimizer_acceptance` does not exist.

- [x] **Step 2: Implement minimal report model and checker**

Create `src/hermes_workflow/optimizer_acceptance.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPORT_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")


@dataclass(frozen=True)
class OptimizerRunAcceptanceReport:
    status: str
    evaluation_count: int
    result_manifest_count: int
    metric_manifest_count: int
    status_counts: dict[str, int]
    settings: dict[str, Any]
    best_candidate: dict[str, Any] | None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None
```

Implement:

```python
def check_optimizer_run(project_dir: str | Path) -> OptimizerRunAcceptanceReport:
    ...
```

Minimum behavior for Task 1:

- load native report and JSONL trace;
- reject if native report missing, unreadable, or `status != completed`;
- reject if trace row count does not equal `evaluation_count`;
- count trace statuses;
- find result and metric manifests from trace paths;
- accept candidate-level metric failures when the trace status is `metric_check_failed`;
- collect settings from result manifests and trace metadata;
- write `reports/optimizer_run_acceptance_report.json`;
- do not reject solely because `state/optimizer_state.json` says `running`.

- [x] **Step 3: Verify Task 1**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py -q
python3 -m ruff check src/hermes_workflow/optimizer_acceptance.py tests/test_optimizer_acceptance.py
```

Expected: pass.

## Task 2: Rejection Cases

**Risk:** Medium. Acceptance logic safety.

**Status:** Complete, verified-only.

**Files:**

- Modify: `tests/test_optimizer_acceptance.py`
- Modify: `src/hermes_workflow/optimizer_acceptance.py`

- [x] **Step 1: Add focused rejection tests**

Add tests for:

```python
def test_check_optimizer_run_rejects_trace_count_mismatch(tmp_path: Path) -> None:
    ...

def test_check_optimizer_run_rejects_missing_result_manifest(tmp_path: Path) -> None:
    ...

def test_check_optimizer_run_rejects_spectre_setting_drift(tmp_path: Path) -> None:
    ...
```

Expected rejected report shape:

```python
assert report.status == "rejected"
assert any("evaluation count mismatch" in issue for issue in report.issues)
```

- [x] **Step 2: Implement missing guards**

Update `check_optimizer_run()` so these cases are blocking issues:

- native report `evaluation_count` does not match JSONL rows;
- trace row references a missing result manifest;
- successful result manifest lacks metric manifest;
- settings drift across result manifests;
- report says completed but no result manifests succeeded.

- [x] **Step 3: Verify Task 2**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py -q
python3 -m ruff check src/hermes_workflow/optimizer_acceptance.py tests/test_optimizer_acceptance.py
```

Expected: pass.

## Task 3: CLI Wiring

**Risk:** Medium. CLI integration only; no real tools.

**Status:** Complete, verified-only.

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_optimizer_acceptance.py`

- [x] **Step 1: Add CLI test**

Add:

```python
def test_check_optimizer_run_cli_writes_acceptance_report(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)

    result = runner.invoke(app, ["check-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "reports/optimizer_run_acceptance_report.json" in result.stdout
    assert (project_dir / "reports/optimizer_run_acceptance_report.json").exists()
```

Add a rejection CLI test:

```python
def test_check_optimizer_run_cli_exits_nonzero_for_rejected_run(tmp_path: Path) -> None:
    project_dir = _write_minimal_optimizer_run(tmp_path)
    (project_dir / "reports/native_turbo_optimizer_evaluations.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(app, ["check-optimizer-run", str(project_dir)])

    assert result.exit_code == 1
    assert "optimizer run rejected" in result.stdout
```

- [x] **Step 2: Add CLI command**

In `src/hermes_workflow/cli.py`, add:

```python
@app.command("check-optimizer-run")
def check_optimizer_run_command(project_dir: Path) -> None:
    ...
```

The command should:

- call `optimizer_acceptance.check_optimizer_run(project_dir)`;
- print the relative report path;
- exit `0` when `status == accepted`;
- exit `1` when `status == rejected`;
- not run real tools.

- [x] **Step 3: Verify Task 3**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/optimizer_acceptance.py tests/test_optimizer_acceptance.py
```

Expected: pass.

## Task 4: Local C-24 Shape Smoke And Docs

**Risk:** Low-to-medium. Local artifact shape check; no real tools.

**Status:** Complete, verified-only.

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: this plan file.

- [x] **Step 1: Run checker on accepted C-24 retry workspace if available**

If `/tmp/ic_auto_opt_c24_retry/bridge_test_inv` exists, run:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c24_retry/bridge_test_inv
```

Expected:

```text
reports/optimizer_run_acceptance_report.json
optimizer run accepted
```

If the local `/tmp` workspace is absent, skip this step and state that C-24
shape smoke was skipped because raw evidence is local-only.

- [x] **Step 2: Final verification**

Run:

```bash
python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py tests/test_native_turbo.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: pass, with only intended tracked changes.

- [x] **Step 3: Commit**

Use explicit pathspecs:

```bash
git add \
  src/hermes_workflow/optimizer_acceptance.py \
  src/hermes_workflow/cli.py \
  tests/test_optimizer_acceptance.py \
  docs/CURRENT_TASK_STATE.json \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/superpowers/plans/2026-06-04-optimizer-run-acceptance-audit.md
git commit -m "feat: add optimizer run acceptance audit"
```

## Self-Review

- Spec coverage: covers deterministic report/trace/manifest audit, CLI output, candidate-level metric failure handling, state snapshot handling, and C-24 evidence basis.
- Boundary check: no real tools, optimizer algorithm, scheduler, PSF parser, formula rewrite, or native-layout replacement.
- Drift check: this plan productizes the C-24 manual supervisor/Hermes audit; it does not add a new optimizer route.

## Completion Note

- Implemented `src/hermes_workflow/optimizer_acceptance.py`.
- Added `hermes-workflow check-optimizer-run PROJECT_DIR`.
- Added focused fake-artifact tests for accepted runs, trace/report mismatch,
  missing manifests, Spectre setting drift, result failure/status mismatch,
  candidate-level metric failures, and CLI exit behavior.
- Local C-24 shape smoke passed on
  `/tmp/ic_auto_opt_c24_retry/bridge_test_inv`:
  `optimizer run accepted`.
- Final verification passed:
  `python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py tests/test_native_turbo.py -q`,
  `python3 -m ruff check src tests tools`,
  `python3 tools/check_development_cadence.py`, and `git diff --check`.
