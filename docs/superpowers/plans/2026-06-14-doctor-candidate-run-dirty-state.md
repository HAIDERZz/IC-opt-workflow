# D-01 Doctor Candidate Run Dirty-State Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation and review checkpoints. Use `superpowers:test-driven-development` for every code change. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Goal:** Stop doctor from reporting completed optimizer candidate directories as `INCOMPLETE_REAL_RUN` while preserving warnings for genuinely interrupted candidate runs.
>
> **Architecture:** Introduce one shared real-run directory classifier that distinguishes optimizer-level project reports from candidate-level completion markers. Local doctor gathers filesystem facts, remote doctor gathers equivalent SSH facts, and both call the same classifier. Existing dirty-state payload fields remain compatible.
>
> **Tech Stack:** Python 3.11, pytest, existing doctor readiness diagnostics, fake SSH runner tests.

Guardrails:

- Work only in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`.
- Do not edit `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`.
- Do not remove `INCOMPLETE_REAL_RUN`; make it accurate.
- Do not change optimizer execution, OpenBox/TuRBO logic, state/progress, retention, or multi-corner aggregation.
- Preserve local/remote doctor parity through shared classification semantics.

## Task 1: Add A Shared Candidate Run Classifier

**Files:**

- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `tests/test_doctor_readiness.py`

**Step 1: Write RED tests for local dirty-state classification**

Add tests:

```python
def test_dirty_state_does_not_warn_for_completed_candidate_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    run.mkdir(parents=True)
    (run / "candidate_request.json").write_text("{}", encoding="utf-8")
    (run / "result_manifest.json").write_text(
        '{"schema_version":"1.0","status":"succeeded","run_id":"real_001"}\n',
        encoding="utf-8",
    )

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert not any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)
```

Add another test for the current multi-testbench/multi-corner shape:

- create `runs/real/real_001/result_manifest.json`
- create one child `runs/real/real_001/testbenches/cg_nf/corners/tt/result_manifest.json`
- assert no `INCOMPLETE_REAL_RUN`

Keep the existing empty-directory test and add a started-but-no-result test:

```python
def test_dirty_state_warns_for_started_candidate_without_result_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = project / "runs" / "real" / "real_001"
    run.mkdir(parents=True)
    (run / "candidate_request.json").write_text("{}", encoding="utf-8")

    summary, diagnostics = build_dirty_state_summary(project)

    assert summary["has_incomplete_real_run"] is True
    assert any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)
```

**Step 2: Run local dirty-state tests and verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: the completed candidate run tests fail because current code requires optimizer-level report files inside `runs/real/<run_id>`.

**Step 3: Implement shared classifier**

In `doctor_readiness.py`, add a small dataclass or pure function, for example:

```python
@dataclass(frozen=True)
class RealRunDirFacts:
    name: str
    has_result_manifest: bool
    has_metric_result_manifest: bool
    has_optimizer_run_report: bool
    has_optimizer_completion_report: bool
    has_candidate_marker: bool

def is_incomplete_real_run_dir(facts: RealRunDirFacts) -> bool:
    if facts.has_result_manifest:
        return False
    if facts.has_metric_result_manifest:
        return False
    if facts.has_optimizer_run_report or facts.has_optimizer_completion_report:
        return False
    return True
```

Use it in `build_dirty_state_summary()` instead of checking only optimizer-level report files.

**Step 4: Run local tests and verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with `fix: classify completed candidate runs in local doctor` if committing is allowed.

## Task 2: Apply The Same Classifier To Remote Doctor

**Files:**

- Modify: `src/hermes_workflow/remote_doctor.py`
- Modify: `tests/test_remote_doctor.py`

**Step 1: Write RED tests for remote dirty-state classification**

Use the existing fake SSH runner pattern in `tests/test_remote_doctor.py`.

Add a test where remote `runs/real` contains `real_001`, and SSH probes report:

- `runs/real/real_001/result_manifest.json` exists
- `runs/real/real_001/optimizer_run_report.json` does not exist
- `runs/real/real_001/optimizer_completion_report.json` does not exist

Expected:

- remote doctor `dirty_state.has_incomplete_real_run` is `False`
- no structured issue with `code == "INCOMPLETE_REAL_RUN"`

Add a second test where `real_001` exists but `result_manifest.json` and metric manifest do not exist.

Expected:

- `dirty_state.has_incomplete_real_run` is `True`
- one `INCOMPLETE_REAL_RUN` diagnostic exists

**Step 2: Run remote doctor tests and verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_doctor.py -q
```

Expected: completed-candidate remote test fails under current logic.

**Step 3: Gather remote facts and call shared classifier**

In `_build_remote_dirty_state()`:

- keep existing SSH directory listing
- for each `runs/real/<name>`, probe:
  - `result_manifest.json`
  - `metrics/metric_result_manifest.json`
  - `optimizer_run_report.json`
  - `optimizer_completion_report.json`
  - optionally `candidate_request.json` or `candidate.json` for diagnostics
- build `RealRunDirFacts`
- call `is_incomplete_real_run_dir(facts)`

Do not duplicate local classification logic.

**Step 4: Run remote tests and verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_doctor.py tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with `fix: classify completed candidate runs in remote doctor` if committing is allowed.

## Task 3: Preserve Product Doctor Payload Compatibility

**Files:**

- Modify tests only unless implementation breaks payload shape:
  - `tests/test_product_doctor.py`
  - `tests/test_remote_doctor.py`

**Step 1: Add payload regression tests**

Assert that doctor reports still include:

- `dirty_state.has_runs`
- `dirty_state.has_incomplete_real_run`
- `dirty_state.has_optimizer_state`
- `dirty_state.has_optimizer_run_report`
- `dirty_state.has_optimizer_evaluations`

For a completed candidate run project, assert:

```python
payload["dirty_state"]["has_runs"] is True
payload["dirty_state"]["has_incomplete_real_run"] is False
```

**Step 2: Run payload tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: PASS after Tasks 1 and 2.

- [ ] Commit with `test: preserve doctor dirty-state payload shape` if committing is allowed.

## Task 4: Real Validation Against B-09 Projects

**Files:**

- No product code changes expected.

**Step 1: Run local doctor on completed B-09 project**

Run:

```bash
./.venv/bin/ic-opt /tmp/ic_opt_local10_3corner_b09_20260614_050335 --doctor
```

Expected:

- command exits 0
- no `INCOMPLETE_REAL_RUN` warning
- `reports/ic_opt_doctor_report.json` has no structured issue with `code == "INCOMPLETE_REAL_RUN"`
- `optimizer_progress_summary` remains:
  - `report_evaluation_count == 10`
  - `evaluation_trace_count == 10`
  - `state_current_evaluations == 10`
  - `ledger_row_count == 7`

**Step 2: Run remote doctor on completed B-09 remote project**

Run:

```bash
./.venv/bin/ic-opt /home/zzchen/remote_opt/Mixer_CS_validation_b09_remote10_20260614_050335 --doctor --ssh-profile zzchen@10.113.216.131
```

Expected:

- command exits 0
- no `INCOMPLETE_REAL_RUN` warning
- `REMOTE_PARALLELISM_HIGH` may remain because `parallel_jobs=10`
- remote report and local cache report have no `INCOMPLETE_REAL_RUN`

**Step 3: Verify structured issue codes directly**

Run:

```bash
./.venv/bin/python - <<'PY'
import json
from pathlib import Path

paths = [
    Path("/tmp/ic_opt_local10_3corner_b09_20260614_050335/reports/ic_opt_doctor_report.json"),
    Path("/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/6262d2d3ddf1e488/reports/ic_opt_doctor_report.json"),
    Path("/home/zzchen/remote_opt/Mixer_CS_validation_b09_remote10_20260614_050335/reports/ic_opt_doctor_report.json"),
]
for path in paths:
    payload = json.loads(path.read_text())
    codes = [item.get("code") for item in payload.get("structured_issues", [])]
    print(path, codes)
    assert "INCOMPLETE_REAL_RUN" not in codes
PY
```

Expected: PASS.

- [ ] Record real validation evidence in the final report.

## Task 5: Full Verification

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: PASS.

**Step 2: Run full suite**

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 3: Run lint**

Run:

```bash
./.venv/bin/python -m ruff check src tests
```

Expected: PASS.

**Step 4: Run whitespace check**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

**Step 5: Final report**

Report:

- files changed
- RED/GREEN evidence
- local doctor real validation result
- remote doctor real validation result
- any remaining warnings, especially `REMOTE_PARALLELISM_HIGH`
- release package untouched
