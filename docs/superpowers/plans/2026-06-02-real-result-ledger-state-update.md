# Real Result Ledger State Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build C-8 so Hermes workflow tooling can record a checked real Spectre + OCEAN result into optimizer ledger and state files without invoking real tools.

**Architecture:** Add a contract-only `real_result_record` module that reruns `check_real_run()` and `check_metric_results()`, derives metrics/objective/constraints from checked reports, appends one real ledger row, updates optimizer state, and updates best candidate when appropriate. Extend existing ledger/report schemas rather than creating a separate real-result history. Add a `hermes-workflow record-real-result` CLI command that formats pass/fail output only.

**Tech Stack:** Python 3.11+, Pydantic v2 models in `schemas.py` and `reports.py`, existing `mock_optimizer` writer/evaluation helpers, existing C-5/C-6 checkers, pytest, ruff.

---

## Required Reading

- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`
- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/mock_optimizer.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/cli.py`
- `tests/test_metric_results.py`
- `tests/test_mock_optimizer.py`

## Execution Model

Use Subagent-Driven Development.

Risk-tiered gates:

- Task 1 is high risk because it changes shared ledger/report schemas. Run focused schema tests and code-quality review.
- Task 2 is high risk because it controls fail-closed behavior before state writes. Run focused no-write tests and code-quality review.
- Task 3 is high risk because it writes ledger/state/best candidate files. Run focused success-path tests and code-quality review.
- Task 4 is high risk because it handles duplicate protection and best-candidate comparison. Run focused regression tests and code-quality review.
- Task 5 is medium risk CLI wiring. Run CLI tests and combine review with Task 6 if needed.
- Task 6 is low/medium risk docs and final verification. Run one final combined review.

No task may call real Virtuoso, real Spectre, real OCEAN, SSH, Claude CLI as execution agent, or network access. Tests must use sanitized fake result artifacts only.

## File Map

- Modify `src/hermes_workflow/schemas.py`: extend `LedgerRow` with optional real-result provenance fields and real simulation statuses.
- Modify `src/hermes_workflow/reports.py`: add `RealResultRecordStatus`, `RealResultRecordFlags`, and `RealResultRecordReport`.
- Create `src/hermes_workflow/real_result_record.py`: C-8 library entry point and helper functions.
- Modify `src/hermes_workflow/cli.py`: add `record-real-result` command.
- Create `tests/test_real_result_record.py`: contract, failure, duplicate, state, best-candidate tests.
- Modify `tests/test_cli.py`: record-real-result CLI pass/fail smoke.
- Modify `tests/test_mock_optimizer.py`: ledger backwards-compatibility and new real status coverage.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`, `docs/EXECUTION_PROGRESS_2026-05-29.md`, `docs/COMPACT_RESUME_CHECKPOINT.md`, and `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: record C-8 implementation status after completion.
- Modify this plan file as tasks complete.

## Contract Constants

Use these constants in `real_result_record.py`:

```python
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
BEST_CANDIDATE_PATH = "state/best_candidate.json"
RECORD_REPORT_PATH = "reports/real_result_record_report.json"
RESULT_MANIFEST_NAME = "result_manifest.json"
METRIC_RESULT_MANIFEST_NAME = "metrics/metric_result_manifest.json"
```

Use these simulation statuses:

```python
REAL_PASS = "real_pass"
REAL_CONSTRAINT_FAIL = "real_constraint_fail"
```

Do not add `real_error` in C-8.

---

## Task 1: Extend Ledger And Record Report Schemas

**Files:**

- Modify: `src/hermes_workflow/schemas.py`
- Modify: `src/hermes_workflow/reports.py`
- Create: `tests/test_real_result_record.py`
- Modify: `tests/test_mock_optimizer.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [x] **Step 1: Write failing schema tests**

Create `tests/test_real_result_record.py` with imports and initial tests:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.reports import (
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
)
from hermes_workflow.schemas import LedgerRow


def test_ledger_row_accepts_real_result_provenance() -> None:
    row = LedgerRow(
        candidate_id="real_001",
        parameters={"FN": "2", "WN": "0.3 um", "FP": "2", "WP": "0.3 um"},
        metrics={"rise": 1.25e-10, "fall": 1.45e-10, "DC": 3.2e-4},
        constraints_passed=True,
        objective=3.2e-4,
        batch_id=1,
        simulation_status="real_pass",
        timestamp_utc="2026-06-02T12:00:00Z",
        result_source="real",
        run_id="real_001",
        result_manifest="runs/real/real_001/result_manifest.json",
        metric_result_manifest=(
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
    )

    assert row.result_source == "real"
    assert row.run_id == "real_001"
    assert row.simulation_status == "real_pass"


def test_ledger_row_still_accepts_existing_mock_payload() -> None:
    row = LedgerRow(
        candidate_id="cand_001",
        parameters={"FN": "4"},
        metrics={"rise": 52.0},
        constraints_passed=True,
        objective=52.0,
        batch_id=1,
        simulation_status="mock_pass",
        timestamp_utc="2026-05-29T12:00:00Z",
    )

    assert row.result_source is None
    assert row.run_id is None


@pytest.mark.parametrize(
    "bad_status",
    ["real_error", "spectre_failed", "pass", ""],
)
def test_ledger_row_rejects_unapproved_real_statuses(bad_status: str) -> None:
    with pytest.raises(ValidationError, match="simulation_status must be one of"):
        LedgerRow(
            candidate_id="real_001",
            parameters={"FN": "2"},
            metrics={"rise": 1.25e-10},
            constraints_passed=True,
            objective=1.25e-10,
            batch_id=1,
            simulation_status=bad_status,
            timestamp_utc="2026-06-02T12:00:00Z",
            result_source="real",
            run_id="real_001",
        )


def test_real_result_record_report_schema_accepts_pass_report() -> None:
    report = RealResultRecordReport(
        schema_version="1.0",
        status=RealResultRecordStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        ledger_path="ledger/experiment_ledger.jsonl",
        optimizer_state_path="state/optimizer_state.json",
        best_candidate_path="state/best_candidate.json",
        checks=RealResultRecordFlags(
            real_run_check_ok=True,
            metric_result_check_ok=True,
            candidate_ok=True,
            duplicate_ok=True,
            objective_ok=True,
            constraints_ok=True,
            ledger_write_ok=True,
            state_write_ok=True,
        ),
        issues=[],
    )

    assert report.status == RealResultRecordStatus.PASS
    assert report.checks.ledger_write_ok is True
```

Append to `tests/test_mock_optimizer.py`:

```python
def test_ledger_row_accepts_real_constraint_fail_status() -> None:
    row = LedgerRow(
        candidate_id="real_001",
        parameters={"FN": "2"},
        metrics={"rise": 1.0},
        constraints_passed=False,
        objective=1.0,
        batch_id=1,
        simulation_status="real_constraint_fail",
        timestamp_utc="2026-06-02T12:00:00Z",
        result_source="real",
        run_id="real_001",
    )

    assert row.simulation_status == "real_constraint_fail"
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py tests/test_mock_optimizer.py::test_ledger_row_accepts_real_constraint_fail_status -q
```

Expected: FAIL because real ledger fields and real result report schemas do not exist yet.

- [x] **Step 3: Extend `LedgerRow`**

Modify `src/hermes_workflow/schemas.py`:

```python
class ResultSource(StrEnum):
    MOCK = "mock"
    REAL = "real"
```

Then update `LedgerRow`:

```python
class LedgerRow(StrictModel):
    candidate_id: str
    parameters: dict[str, str]
    metrics: dict[str, float]
    constraints_passed: bool
    objective: float
    batch_id: StrictInt
    simulation_status: str
    timestamp_utc: str
    result_source: ResultSource | None = None
    run_id: str | None = None
    result_manifest: str | None = None
    metric_result_manifest: str | None = None

    @field_validator("simulation_status")
    @classmethod
    def _status_is_recognized(cls, value: str) -> str:
        allowed = {
            "mock_pass",
            "mock_constraint_fail",
            "mock_error",
            "real_pass",
            "real_constraint_fail",
        }
        if value not in allowed:
            raise ValueError(f"simulation_status must be one of {allowed}")
        return value
```

- [x] **Step 4: Add record report schemas**

Modify `src/hermes_workflow/reports.py`:

```python
class RealResultRecordStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class RealResultRecordFlags(StrictReport):
    real_run_check_ok: bool = False
    metric_result_check_ok: bool = False
    candidate_ok: bool = False
    duplicate_ok: bool = False
    objective_ok: bool = False
    constraints_ok: bool = False
    ledger_write_ok: bool = False
    state_write_ok: bool = False


class RealResultRecordReport(StrictReport):
    schema_version: str
    status: RealResultRecordStatus
    run_id: str
    candidate_id: str | None
    ledger_path: str
    optimizer_state_path: str
    best_candidate_path: str | None
    checks: RealResultRecordFlags
    issues: list[str] = Field(default_factory=list)
```

- [x] **Step 5: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py tests/test_mock_optimizer.py::test_ledger_row_accepts_real_constraint_fail_status -q
```

Expected: PASS.

- [x] **Step 6: Run shared schema/writer tests**

Run:

```bash
python3 -m pytest tests/test_mock_optimizer.py tests/test_validate.py -q
python3 -m ruff check src/hermes_workflow/schemas.py src/hermes_workflow/reports.py tests/test_real_result_record.py tests/test_mock_optimizer.py
git diff --check
```

Expected: all pass, ruff clean, no diff-check output.

Update this task's checkboxes to `[x]` after verification and review gate approval.

---

## Task 2: Fail-Closed Record Preconditions

**Files:**

- Create: `src/hermes_workflow/real_result_record.py`
- Modify: `tests/test_real_result_record.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [ ] **Step 1: Add sanitized project helpers**

Append these helpers to `tests/test_real_result_record.py`. Reuse C-6/C-7 fake handoff helpers rather than real tools:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import MetricResultCheckStatus, RealRunCheckStatus
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-02T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir


def _write_result_manifest(project_dir: Path) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    prepared = _load_json(run_dir / "real_run_manifest.json")
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
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
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
        "log_file": "runs/real/real_001/spectre.stdout",
        "artifact_files": [
            "runs/real/real_001/spectre.stderr",
            "runs/real/real_001/psf/spectre.out",
            "runs/real/real_001/metrics/ocean.log",
            "runs/real/real_001/metrics/ocean_scalars.tsv",
        ],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": "runs/real/real_001/psf",
            "spectre_out": "runs/real/real_001/psf/spectre.out",
        },
        "metric_result_manifest": (
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
    }
    _write_json(run_dir / "result_manifest.json", payload)


def _write_metric_result_manifest(
    project_dir: Path,
    *,
    values: dict[str, float] | None = None,
) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    metric_values = values or {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
        "backend": "spectre_ocean_batch",
        "status": "succeeded",
        "request_file": "runs/real/real_001/metric_extraction_request.json",
        "request_sha256": sha256_file(request_path),
        "psf_dir": "runs/real/real_001/psf",
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0,
            "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
            "script_sha256": sha256_file(script_path),
            "log_file": "runs/real/real_001/metrics/ocean.log",
            "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv",
        },
        "metrics": [
            {
                "name": name,
                "status": "succeeded",
                "value": value,
                "value_text": f"{value:.12g}",
                "unit": request_by_name[name]["unit"],
                "result": request_by_name[name]["result"],
                "expression": request_by_name[name]["expression"],
                "expression_sha256": request_by_name[name]["expression_sha256"],
                "expression_source": request_by_name[name]["expression_source"],
                "issues": [],
            }
            for name, value in metric_values.items()
        ],
        "issues": [],
    }
    _write_json(metrics_dir / "metric_result_manifest.json", payload)


def _write_valid_checked_result(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS
```

- [ ] **Step 2: Write failing precondition tests**

Append:

```python
def test_record_real_result_rejects_missing_result_manifest_without_writes(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)

    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T12:00:00Z",
    )

    assert report.status == RealResultRecordStatus.FAIL
    assert "result manifest is missing" in report.issues
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    persisted = _load_json(project_dir / "reports" / "real_result_record_report.json")
    assert persisted["status"] == "fail"


def test_record_real_result_rejects_missing_metric_manifest_without_writes(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)

    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T12:00:00Z",
    )

    assert report.status == RealResultRecordStatus.FAIL
    assert any("metric result manifest" in issue for issue in report.issues)
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py::test_record_real_result_rejects_missing_result_manifest_without_writes tests/test_real_result_record.py::test_record_real_result_rejects_missing_metric_manifest_without_writes -q
```

Expected: FAIL because `real_result_record` does not exist or `record_real_result()` is unimplemented.

- [ ] **Step 4: Implement fail-closed skeleton**

Create `src/hermes_workflow/real_result_record.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealResultRecordFlags,
    RealResultRecordReport,
    RealResultRecordStatus,
    RealRunCheckStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.validate import assert_valid_project


DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
BEST_CANDIDATE_PATH = "state/best_candidate.json"
RECORD_REPORT_PATH = "reports/real_result_record_report.json"


def record_real_result(
    project_dir: Path,
    *,
    run_id: str | None = None,
    recorded_at_utc: str | None = None,
) -> RealResultRecordReport:
    project_dir = Path(project_dir)
    selected_run_id = run_id or DEFAULT_RUN_ID
    _recorded_at = recorded_at_utc or _utc_now()
    issues: list[str] = []
    checks = RealResultRecordFlags()
    candidate_id: str | None = None

    try:
        assert_valid_project(project_dir)
    except (OSError, ValueError) as exc:
        issues.append(str(exc))

    if not issues:
        real_report = check_real_run(project_dir, run_id=selected_run_id)
        checks.real_run_check_ok = real_report.status == RealRunCheckStatus.PASS
        candidate_id = real_report.candidate_id
        if real_report.status != RealRunCheckStatus.PASS:
            issues.extend(real_report.issues)

    if not issues:
        metric_report = check_metric_results(project_dir, run_id=selected_run_id)
        checks.metric_result_check_ok = (
            metric_report.status == MetricResultCheckStatus.PASS
        )
        candidate_id = metric_report.candidate_id or candidate_id
        if metric_report.status != MetricResultCheckStatus.PASS:
            issues.extend(metric_report.issues)

    report = RealResultRecordReport(
        schema_version="1.0",
        status=RealResultRecordStatus.FAIL,
        run_id=selected_run_id,
        candidate_id=candidate_id,
        ledger_path=LEDGER_PATH,
        optimizer_state_path=OPTIMIZER_STATE_PATH,
        best_candidate_path=None,
        checks=checks,
        issues=issues,
    )
    _write_report(project_dir, report)
    return report


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_report(project_dir: Path, report: RealResultRecordReport) -> Path:
    report_path = project_dir / RECORD_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report_path
```

- [ ] **Step 5: Run precondition tests**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py::test_record_real_result_rejects_missing_result_manifest_without_writes tests/test_real_result_record.py::test_record_real_result_rejects_missing_metric_manifest_without_writes -q
```

Expected: PASS.

- [ ] **Step 6: Run checker integration tests**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py tests/test_metric_results.py tests/test_result_handoff.py -q
python3 -m ruff check src/hermes_workflow/real_result_record.py tests/test_real_result_record.py
git diff --check
```

Expected: all pass, ruff clean, no diff-check output.

Update this task's checkboxes to `[x]` after verification and review gate approval.

---

## Task 3: Record Successful Real Result Into Ledger And State

**Files:**

- Modify: `src/hermes_workflow/real_result_record.py`
- Modify: `tests/test_real_result_record.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [ ] **Step 1: Write success-path test**

Append:

```python
def test_record_real_result_writes_ledger_state_best_and_report(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(project_dir)

    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T12:00:00Z",
    )

    assert report.status == RealResultRecordStatus.PASS
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    state_path = project_dir / "state" / "optimizer_state.json"
    best_path = project_dir / "state" / "best_candidate.json"
    assert ledger_path.exists()
    assert state_path.exists()
    assert best_path.exists()

    row = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    assert row["candidate_id"] == "real_001"
    assert row["run_id"] == "real_001"
    assert row["result_source"] == "real"
    assert row["simulation_status"] == "real_pass"
    assert row["batch_id"] == 1
    assert row["metrics"]["rise"] == pytest.approx(1.0e-12)
    assert row["metrics"]["fall"] == pytest.approx(1.0e-12)
    assert row["metrics"]["DC"] == pytest.approx(1.0e-6)
    assert row["constraints_passed"] is True

    state = _load_json(state_path)
    assert state["current_evaluations"] == 1
    assert state["best_candidate_id"] == "real_001"
    assert state["status"] == "running"
    assert state["started_at_utc"] == "2026-06-02T12:00:00Z"
    assert state["updated_at_utc"] == "2026-06-02T12:00:00Z"

    best = _load_json(best_path)
    assert best["candidate_id"] == "real_001"
    assert best["parameters"] == {
        "FN": "2",
        "WN": "0.3 um",
        "FP": "2",
        "WP": "0.3 um",
    }
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py::test_record_real_result_writes_ledger_state_best_and_report -q
```

Expected: FAIL because success-path writing is not implemented.

- [ ] **Step 3: Implement metric extraction and candidate loading**

In `real_result_record.py`, add:

```python
import json
import math

from pydantic import ValidationError

from hermes_workflow.mock_optimizer import (
    evaluate_constraints,
    evaluate_objective_from_config,
    write_best_candidate,
    write_ledger_row,
    write_optimizer_state,
)
from hermes_workflow.reports import MetricResultCheckReport
from hermes_workflow.schemas import BestCandidate, LedgerRow, OptimizerState
```

Add helpers:

```python
def _load_json(path: Path, label: str, issues: list[str]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        issues.append(f"{label} cannot be read: {exc}")
    except json.JSONDecodeError as exc:
        issues.append(f"{label} is invalid JSON: {exc.msg}")
    return None


def _candidate_parameters(
    project_dir: Path,
    run_id: str,
    candidate_id: str | None,
    issues: list[str],
) -> dict[str, str] | None:
    payload = _load_json(
        project_dir / REAL_RUN_ROOT / run_id / "candidate.json",
        "candidate file",
        issues,
    )
    if payload is None:
        return None
    if payload.get("candidate_id") != candidate_id:
        issues.append("candidate id mismatch")
        return None
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parameters.items()
    ):
        issues.append("candidate parameters are invalid")
        return None
    return parameters


def _checked_metric_values(
    metric_report: MetricResultCheckReport,
    issues: list[str],
) -> dict[str, float] | None:
    metrics: dict[str, float] = {}
    for name, checked in metric_report.metrics.items():
        if checked.value is None or not math.isfinite(checked.value):
            issues.append(f"metric {name} value is not finite")
            return None
        metrics[name] = float(checked.value)
    return metrics
```

- [ ] **Step 4: Implement success-path record assembly**

Inside `record_real_result()`, after both checkers pass:

```python
bundle = assert_valid_project(project_dir)
metric_report = check_metric_results(project_dir, run_id=selected_run_id)
candidate_id = metric_report.candidate_id
parameters = _candidate_parameters(project_dir, selected_run_id, candidate_id, issues)
metrics = _checked_metric_values(metric_report, issues)
```

Then derive constraints/objective and row:

```python
constraints_passed = evaluate_constraints(bundle.metrics, metrics)
checks.constraints_ok = True
objective_value = evaluate_objective_from_config(bundle.metrics, metrics)
if bundle.metrics.objective.direction.value == "maximize":
    objective_value = -objective_value
checks.objective_ok = True
simulation_status = REAL_PASS if constraints_passed else REAL_CONSTRAINT_FAIL
row = LedgerRow(
    candidate_id=candidate_id,
    parameters=parameters,
    metrics=metrics,
    constraints_passed=constraints_passed,
    objective=objective_value,
    batch_id=_next_batch_id(project_dir, bundle.optimizer.optimizer.batch_size),
    simulation_status=simulation_status,
    timestamp_utc=recorded_at,
    result_source="real",
    run_id=selected_run_id,
    result_manifest=f"{REAL_RUN_ROOT}/{selected_run_id}/{RESULT_MANIFEST_NAME}",
    metric_result_manifest=(
        f"{REAL_RUN_ROOT}/{selected_run_id}/{METRIC_RESULT_MANIFEST_NAME}"
    ),
)
```

Add `_next_batch_id()`:

```python
def _next_batch_id(project_dir: Path, batch_size: int) -> int:
    existing_count = _count_valid_ledger_rows(project_dir)
    return (existing_count // batch_size) + 1
```

For Task 3, `_count_valid_ledger_rows()` may return `0`; full duplicate and invalid-ledger handling comes in Task 4.

- [ ] **Step 5: Implement state and best writes**

Add:

```python
def _new_optimizer_state(
    bundle,
    *,
    current_evaluations: int,
    best_candidate_id: str | None,
    recorded_at_utc: str,
) -> OptimizerState:
    optimizer = bundle.optimizer.optimizer
    status = (
        "completed"
        if current_evaluations >= optimizer.max_evaluations
        else "running"
    )
    started_at = _existing_started_at(bundle.project_dir) or recorded_at_utc
    return OptimizerState(
        schema_version="1.0",
        project_name=bundle.project_config.project.name,
        algorithm=optimizer.algorithm.value,
        initialization=optimizer.initialization.value,
        current_evaluations=current_evaluations,
        max_evaluations=optimizer.max_evaluations,
        batch_size=optimizer.batch_size,
        random_seed=optimizer.random_seed,
        best_candidate_id=best_candidate_id,
        status=status,
        started_at_utc=started_at,
        updated_at_utc=recorded_at_utc,
    )
```

For Task 3, write current row as best when `constraints_passed` is true:

```python
best_candidate = None
best_candidate_id = None
if row.constraints_passed:
    best_candidate = BestCandidate(
        candidate_id=row.candidate_id,
        parameters=row.parameters,
        metrics=row.metrics,
        constraints_passed=row.constraints_passed,
        objective=row.objective,
        batch_id=row.batch_id,
        timestamp_utc=row.timestamp_utc,
    )
    write_best_candidate(project_dir, best_candidate)
    best_candidate_id = row.candidate_id
```

Then:

```python
write_ledger_row(project_dir, row)
checks.ledger_write_ok = True
state = _new_optimizer_state(
    bundle,
    current_evaluations=_count_valid_ledger_rows(project_dir),
    best_candidate_id=best_candidate_id,
    recorded_at_utc=recorded_at,
)
write_optimizer_state(project_dir, state)
checks.state_write_ok = True
```

The final implementation may reorder best/state after ledger as required by the spec; tests should verify the output, not internal order.

- [ ] **Step 6: Run success-path test**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py::test_record_real_result_writes_ledger_state_best_and_report -q
```

Expected: PASS.

- [ ] **Step 7: Run focused real-result tests**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py -q
python3 -m ruff check src/hermes_workflow/real_result_record.py tests/test_real_result_record.py
git diff --check
```

Expected: all pass, ruff clean, no diff-check output.

Update this task's checkboxes to `[x]` after verification and review gate approval.

---

## Task 4: Duplicate Protection And Best-Candidate Comparison

**Files:**

- Modify: `src/hermes_workflow/real_result_record.py`
- Modify: `tests/test_real_result_record.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [ ] **Step 1: Add duplicate protection tests**

Append:

```python
def test_record_real_result_rejects_duplicate_run_without_append(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(project_dir)
    first = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:00:00Z")
    assert first.status == RealResultRecordStatus.PASS

    second = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:01:00Z")

    assert second.status == RealResultRecordStatus.FAIL
    assert "ledger already contains run_id real_001" in second.issues
    lines = (project_dir / "ledger" / "experiment_ledger.jsonl").read_text(
        encoding="utf-8"
    ).strip().split("\n")
    assert len(lines) == 1


def test_record_real_result_rejects_duplicate_candidate_without_append(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(project_dir)
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "candidate_id": "real_001",
                "parameters": {"FN": "2"},
                "metrics": {"rise": 1.0},
                "constraints_passed": True,
                "objective": 1.0,
                "batch_id": 1,
                "simulation_status": "mock_pass",
                "timestamp_utc": "2026-06-02T11:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:00:00Z")

    assert report.status == RealResultRecordStatus.FAIL
    assert "ledger already contains candidate_id real_001" in report.issues
    assert len(ledger_path.read_text(encoding="utf-8").strip().split("\n")) == 1
```

- [ ] **Step 2: Add best-candidate comparison tests**

Append:

```python
def test_constraint_failing_real_result_does_not_update_best(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(
        project_dir,
    )
    _write_metric_result_manifest(
        project_dir,
        values={"rise": 1.0, "fall": 1.0, "DC": 1.0},
    )

    report = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:00:00Z")

    assert report.status == RealResultRecordStatus.PASS
    row = json.loads(
        (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert row["simulation_status"] == "real_constraint_fail"
    assert not (project_dir / "state" / "best_candidate.json").exists()
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    assert state["best_candidate_id"] is None


def test_worse_feasible_real_result_preserves_existing_best(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    best_path = project_dir / "state" / "best_candidate.json"
    best_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        best_path,
        {
            "candidate_id": "cand_999",
            "parameters": {"FN": "4"},
            "metrics": {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-9},
            "constraints_passed": True,
            "objective": 1.0e-9,
            "batch_id": 1,
            "timestamp_utc": "2026-06-02T11:00:00Z",
        },
    )
    _write_valid_checked_result(project_dir)
    _write_metric_result_manifest(
        project_dir,
        values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6},
    )

    report = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:00:00Z")

    assert report.status == RealResultRecordStatus.PASS
    best = _load_json(best_path)
    assert best["candidate_id"] == "cand_999"
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    assert state["best_candidate_id"] == "cand_999"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py::test_record_real_result_rejects_duplicate_run_without_append tests/test_real_result_record.py::test_record_real_result_rejects_duplicate_candidate_without_append tests/test_real_result_record.py::test_constraint_failing_real_result_does_not_update_best tests/test_real_result_record.py::test_worse_feasible_real_result_preserves_existing_best -q
```

Expected: FAIL until duplicate and best-comparison logic is implemented.

- [ ] **Step 4: Implement ledger reading and duplicate checks**

Add:

```python
def _read_ledger_rows(project_dir: Path, issues: list[str]) -> list[LedgerRow]:
    path = project_dir / LEDGER_PATH
    if not path.exists():
        return []
    rows: list[LedgerRow] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            rows.append(LedgerRow.model_validate(payload))
        except (json.JSONDecodeError, ValidationError) as exc:
            issues.append(f"ledger row {line_number} is invalid: {exc}")
            return []
    return rows


def _check_duplicates(
    rows: list[LedgerRow],
    *,
    run_id: str,
    candidate_id: str,
    issues: list[str],
) -> bool:
    for row in rows:
        if row.run_id == run_id:
            issues.append(f"ledger already contains run_id {run_id}")
        if row.candidate_id == candidate_id:
            issues.append(f"ledger already contains candidate_id {candidate_id}")
    return not issues
```

Call `_read_ledger_rows()` and `_check_duplicates()` before constructing writes. Set `checks.duplicate_ok = True` only when no duplicates are found.

- [ ] **Step 5: Implement existing best comparison**

Add:

```python
def _load_best_candidate(project_dir: Path, issues: list[str]) -> BestCandidate | None:
    path = project_dir / BEST_CANDIDATE_PATH
    if not path.exists():
        return None
    payload = _load_json(path, "best candidate", issues)
    if payload is None:
        return None
    try:
        return BestCandidate.model_validate(payload)
    except ValidationError as exc:
        issues.append(f"best candidate is invalid: {exc}")
        return None


def _choose_best(
    existing: BestCandidate | None,
    current: LedgerRow,
) -> BestCandidate | None:
    if existing is not None and (
        not current.constraints_passed or current.objective >= existing.objective
    ):
        return existing
    if not current.constraints_passed:
        return existing
    return BestCandidate(
        candidate_id=current.candidate_id,
        parameters=current.parameters,
        metrics=current.metrics,
        constraints_passed=current.constraints_passed,
        objective=current.objective,
        batch_id=current.batch_id,
        timestamp_utc=current.timestamp_utc,
    )
```

Use `_choose_best()` before writing `best_candidate.json`.

- [ ] **Step 6: Add maximize objective regression**

Append a test that edits `config/metrics.yaml` from `direction: minimize` to `direction: maximize`, writes a valid result, and asserts the ledger objective is the negated configured objective:

```python
def test_record_real_result_normalizes_maximize_objective(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8").replace(
            "direction: minimize",
            "direction: maximize",
        ),
        encoding="utf-8",
    )
    _write_valid_checked_result(project_dir)
    _write_metric_result_manifest(
        project_dir,
        values={"rise": 1.0e-12, "fall": 1.0e-12, "DC": 2.0e-6},
    )

    report = record_real_result(project_dir, recorded_at_utc="2026-06-02T12:00:00Z")

    assert report.status == RealResultRecordStatus.PASS
    row = json.loads(
        (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert row["objective"] < 0
```

- [ ] **Step 7: Run hardening tests**

Run:

```bash
python3 -m pytest tests/test_real_result_record.py -q
python3 -m pytest tests/test_mock_optimizer.py tests/test_metric_results.py -q
python3 -m ruff check src/hermes_workflow/real_result_record.py tests/test_real_result_record.py
git diff --check
```

Expected: all pass, ruff clean, no diff-check output.

Update this task's checkboxes to `[x]` after verification and review gate approval.

---

## Task 5: CLI Integration

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [ ] **Step 1: Add CLI pass/fail tests**

Append to `tests/test_cli.py`:

```python
def test_cli_record_real_result_passes_for_valid_checked_result(
    tmp_path: Path,
) -> None:
    from tests.test_real_result_record import (
        _create_ready_project,
        _write_valid_checked_result,
    )

    project_dir = _create_ready_project(tmp_path)
    _write_valid_checked_result(project_dir)

    result = runner.invoke(
        app,
        ["record-real-result", str(project_dir), "--run-id", "real_001"],
    )

    assert result.exit_code == 0
    assert "real result recorded" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "ledger: ledger/experiment_ledger.jsonl" in result.stdout
    assert "state: state/optimizer_state.json" in result.stdout
    assert "report: reports/real_result_record_report.json" in result.stdout


def test_cli_record_real_result_reports_failure_without_traceback(
    tmp_path: Path,
) -> None:
    from tests.test_real_result_record import _create_ready_project

    project_dir = _create_ready_project(tmp_path)

    result = runner.invoke(app, ["record-real-result", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "real result record failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/real_result_record_report.json" in result.stdout
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_cli.py::test_cli_record_real_result_passes_for_valid_checked_result tests/test_cli.py::test_cli_record_real_result_reports_failure_without_traceback -q
```

Expected: FAIL because CLI command does not exist.

- [ ] **Step 3: Add CLI command**

Modify `src/hermes_workflow/cli.py`:

```python
from hermes_workflow.real_result_record import record_real_result
```

Add command after `check-metric-results`:

```python
@app.command("record-real-result")
def record_real_result_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with checked real result artifacts."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Real-run package id such as real_001."),
    ] = None,
) -> None:
    try:
        report = record_real_result(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("real result recorded")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo(f"ledger: {report.ledger_path}")
        typer.echo(f"state: {report.optimizer_state_path}")
        typer.echo("report: reports/real_result_record_report.json")
        return

    typer.echo("real result record failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/real_result_record_report.json")
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python3 -m pytest tests/test_cli.py::test_cli_record_real_result_passes_for_valid_checked_result tests/test_cli.py::test_cli_record_real_result_reports_failure_without_traceback -q
```

Expected: PASS.

- [ ] **Step 5: Run related CLI/checker tests**

Run:

```bash
python3 -m pytest tests/test_cli.py tests/test_real_result_record.py tests/test_metric_results.py tests/test_result_handoff.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/real_result_record.py tests/test_cli.py tests/test_real_result_record.py
git diff --check
```

Expected: all pass, ruff clean, no diff-check output.

Update this task's checkboxes to `[x]` after verification and review gate approval.

---

## Task 6: Docs, Progress, Full Verification, And Final Review

**Files:**

- Modify: `README.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

- [ ] **Step 1: Update README**

Add after `check-metric-results`:

```markdown
After both handoff checks pass, record the checked real result into optimizer state:

```bash
hermes-workflow record-real-result projects/bridge_test_inv --run-id real_001
```

`record-real-result` appends a real evaluation row and updates optimizer state from checked contract files only. It does not run Spectre, run OCEAN, parse PSF, or generate the next candidate.
```

- [ ] **Step 2: Update overview and checkpoints**

Record:

```text
C-8 records checked real metric results into ledger/state after `check-real-run` and `check-metric-results` pass.
It remains contract-only and does not call real tools.
Next scope after C-8 is C-9 next-candidate generation or failure/retry policy.
```

- [ ] **Step 3: Run full verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected:

```text
pytest: all tests passed
ruff: All checks passed!
git diff --check: no output
```

- [ ] **Step 4: Run final combined review gate**

Use the project's established review path. The review request must include:

```text
Review C-8 real result ledger/state update.
Focus on:
- contract-only boundary
- no real tool invocation
- no PSF parsing or formula recomputation
- check-real-run and check-metric-results must pass before writes
- duplicate run_id/candidate_id protection
- ledger/state/best candidate consistency
- backwards compatibility for existing mock ledger rows
- CLI failure surface without traceback
```

- [ ] **Step 5: Fix review findings**

If review returns Critical or Important findings, fix them, rerun focused tests, rerun full verification, then rerun the review gate.

- [ ] **Step 6: Mark C-8 complete**

Update this task's checkboxes to `[x]` after final verification and review approval.

## Plan Self-Review

- Spec coverage: Tasks cover schema/report contracts, fail-closed preconditions, rerun checkers, metric/objective derivation, duplicate protection, ledger append, optimizer state update, best candidate update, CLI wiring, docs, and final review.
- Boundary check: No task calls Virtuoso, Spectre, OCEAN, SSH, Claude CLI, or C-7 adapter. Tests use fake sanitized result files.
- Backwards compatibility: Task 1 keeps existing mock ledger rows valid while adding optional real-result provenance.
- Safety check: Task 2 and Task 4 verify no ledger/state writes happen on failed checks or duplicate attempts.
- Next scope: C-9 next-candidate generation and failure/retry policy remain out of C-8.
