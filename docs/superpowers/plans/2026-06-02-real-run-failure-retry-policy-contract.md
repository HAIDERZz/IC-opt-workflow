# Real-Run Failure Retry Policy Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build C-10 so failed, partial, pending, retried, abandoned, stopped, and recordable real-run packages have deterministic file-backed recovery state.

**Architecture:** Add a contract-only recovery layer beside the existing real-run package, handoff, metric-result, record, and next-run modules. C-10 classifies existing run directories with existing Hermes checkers, writes explicit supervisor recovery decisions, prepares retry packages without overwriting failed evidence, and guards C-9 from advancing past unresolved real-run packages. It never invokes real tools, never calls the C-7 adapter, never parses PSF, and never writes optimizer ledger/state.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, pytest, ruff, existing `hermes_workflow` modules and fake-file test fixtures.

---

## Required Reading

- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`
- `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`
- `docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`
- `src/hermes_workflow/reports.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/cli.py`
- `tests/test_next_real_run.py`
- `tests/test_real_result_record.py`

## Execution Model

Use Subagent-Driven Development.

Risk-tiered gates:

- Task 1 is high risk because it adds report contracts. Run focused tests and code-quality review.
- Task 2 is high risk because it classifies workflow state. Run focused tests and spec/code-quality review.
- Task 3 is high risk because it writes recovery decisions and retry packages. Run focused tests and spec/code-quality review.
- Task 4 is high risk because it blocks C-9 progression. Run focused tests and spec/code-quality review.
- Task 5 is medium risk CLI wiring. Batch local verification with Task 4 if Task 4 review has passed.
- Task 6 is low risk docs/progress. Run local checks and final combined review.

No task may call real Virtuoso, Spectre, OCEAN, SSH, Claude CLI as an execution agent, `virtuoso-bridge-lite`, or network access.

## File Map

- Modify `src/hermes_workflow/reports.py`: add recovery report enums/models.
- Create `src/hermes_workflow/real_run_recovery.py`: assessment, allowed actions, decision writing, retry package preparation, unresolved-run guard.
- Modify `src/hermes_workflow/real_run.py`: allow retry package candidate ids to differ from run ids, and call the C-10 unresolved-run guard before C-9 prepares a new candidate.
- Modify `src/hermes_workflow/cli.py`: add `assess-real-run-recovery`, `prepare-real-run-retry`, and `resolve-real-run-failure`.
- Create `tests/test_real_run_recovery.py`: synthetic recovery and retry coverage.
- Modify `tests/test_next_real_run.py`: unresolved-run guard coverage.
- Modify `tests/test_cli.py`: CLI pass/fail coverage.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: record C-10 layer after implementation.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-10 implementation status.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: record compact-resume node.
- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: update next-development handoff.
- Modify this plan file as task checkboxes complete.

## Shared Constants

Use these constants in `real_run_recovery.py`:

```python
RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_SCHEMA_VERSION = "1.0"
REAL_RUN_ROOT = "runs/real"
RECOVERY_REPORT = "reports/real_run_recovery_report.json"
REAL_RUN_CHECK_REPORT = "reports/real_run_check_report.json"
METRIC_RESULT_CHECK_REPORT = "reports/metric_result_check_report.json"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
RECOVERY_DECISION_NAME = "recovery_decision.json"
MAX_ATTEMPTS_PER_CANDIDATE = 2
EXECUTION_EVIDENCE_NAMES = (
    "result_manifest.tmp",
    "spectre.stdout",
    "spectre.stderr",
    "psf",
    "metrics",
)
```

Use existing constants from `real_run.py` and `metric_results.py` where practical. Keep C-10 constants scoped to `real_run_recovery.py` to avoid expanding unrelated modules.

---

## Task 1: Recovery Report Schemas

**Files:**

- Modify: `src/hermes_workflow/reports.py`
- Create: `tests/test_real_run_recovery.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [x] **Step 1: Write failing schema tests**

Create `tests/test_real_run_recovery.py` with imports and report schema tests:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.reports import (
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunRecoveryReport,
    RealRunRecoveryStatus,
)


def test_recovery_report_schema_accepts_classification_and_actions() -> None:
    report = RealRunRecoveryReport.model_validate(
        {
            "schema_version": "1.0",
            "status": "pass",
            "run_id": "real_002",
            "candidate_id": "real_002",
            "classification": "metric_result_failed",
            "allowed_actions": [
                "retry_same_candidate",
                "abandon_candidate",
                "revise_contracts",
                "stop_workflow",
            ],
            "recommended_action": "retry_same_candidate",
            "attempt_number": 1,
            "max_attempts_per_candidate": 2,
            "retry_budget_remaining": 1,
            "real_run_check_report": "reports/real_run_check_report.json",
            "metric_result_check_report": "reports/metric_result_check_report.json",
            "ledger_path": "ledger/experiment_ledger.jsonl",
            "recovery_decision": None,
            "issues": [],
        }
    )

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_FAILED
    assert report.allowed_actions == [
        RealRunRecoveryAction.RETRY_SAME_CANDIDATE,
        RealRunRecoveryAction.ABANDON_CANDIDATE,
        RealRunRecoveryAction.REVISE_CONTRACTS,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]


def test_recovery_report_schema_forbids_unknown_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "status": "pass",
        "run_id": "real_002",
        "candidate_id": "real_002",
        "classification": "pending_execution",
        "allowed_actions": ["wait_for_execution", "stop_workflow"],
        "recommended_action": "wait_for_execution",
        "attempt_number": 1,
        "max_attempts_per_candidate": 2,
        "retry_budget_remaining": 1,
        "real_run_check_report": "reports/real_run_check_report.json",
        "metric_result_check_report": "reports/metric_result_check_report.json",
        "ledger_path": "ledger/experiment_ledger.jsonl",
        "recovery_decision": None,
        "issues": [],
        "unexpected": True,
    }

    with pytest.raises(ValueError):
        RealRunRecoveryReport.model_validate(payload)
```

- [x] **Step 2: Run schema tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py::test_recovery_report_schema_accepts_classification_and_actions tests/test_real_run_recovery.py::test_recovery_report_schema_forbids_unknown_fields -q
```

Expected: import failure for `RealRunRecoveryAction`, `RealRunRecoveryClassification`, `RealRunRecoveryReport`, and `RealRunRecoveryStatus`.

- [x] **Step 3: Add recovery enums and report model**

Modify `src/hermes_workflow/reports.py` after `RealResultRecordStatus`:

```python
class RealRunRecoveryStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class RealRunRecoveryClassification(StrEnum):
    PENDING_EXECUTION = "pending_execution"
    CONTRACT_INVALID = "contract_invalid"
    TOOL_RESULT_MISSING = "tool_result_missing"
    TOOL_RESULT_FAILED = "tool_result_failed"
    TOOL_RESULT_PARTIAL = "tool_result_partial"
    METRIC_RESULT_MISSING = "metric_result_missing"
    METRIC_RESULT_FAILED = "metric_result_failed"
    RECORDABLE_SUCCESS = "recordable_success"
    ALREADY_RECORDED = "already_recorded"
    RESOLVED_RETRY_PREPARED = "resolved_retry_prepared"
    RESOLVED_ABANDONED = "resolved_abandoned"
    RESOLVED_STOPPED = "resolved_stopped"


class RealRunRecoveryAction(StrEnum):
    RETRY_SAME_CANDIDATE = "retry_same_candidate"
    ABANDON_CANDIDATE = "abandon_candidate"
    STOP_WORKFLOW = "stop_workflow"
    REVISE_CONTRACTS = "revise_contracts"
    RECORD_RESULT = "record_result"
    WAIT_FOR_EXECUTION = "wait_for_execution"
```

Add after `RealResultRecordReport`:

```python
class RealRunRecoveryReport(StrictReport):
    schema_version: str
    status: RealRunRecoveryStatus
    run_id: str
    candidate_id: str | None
    classification: RealRunRecoveryClassification
    allowed_actions: list[RealRunRecoveryAction] = Field(default_factory=list)
    recommended_action: RealRunRecoveryAction | None
    attempt_number: int = Field(ge=1)
    max_attempts_per_candidate: int = Field(ge=1)
    retry_budget_remaining: int = Field(ge=0)
    real_run_check_report: str
    metric_result_check_report: str
    ledger_path: str
    recovery_decision: str | None
    issues: list[str] = Field(default_factory=list)
```

- [x] **Step 4: Run schema tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py::test_recovery_report_schema_accepts_classification_and_actions tests/test_real_run_recovery.py::test_recovery_report_schema_forbids_unknown_fields -q
```

Expected: 2 tests pass.

- [x] **Step 5: Run focused lint**

Run:

```bash
python3 -m ruff check src/hermes_workflow/reports.py tests/test_real_run_recovery.py
```

Expected: all checks pass.

- [x] **Step 6: Commit Task 1**

```bash
git add src/hermes_workflow/reports.py tests/test_real_run_recovery.py docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "feat: add real run recovery report schema"
```

- [x] **Step 7: Task 1 review gate**

Run code-quality review focused on:

```text
Review C-10 Task 1 recovery report schemas.

Check:
- enum values exactly match the C-10 design spec
- report model is strict and file-contract safe
- no real tool invocation is introduced
- tests prove strict schema behavior
```

---

## Task 2: Recovery Assessment Classifier

**Files:**

- Create: `src/hermes_workflow/real_run_recovery.py`
- Modify: `tests/test_real_run_recovery.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [x] **Step 1: Add test fixture helpers**

Append to `tests/test_real_run_recovery.py`:

```python
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_next_real_run, prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_result_manifest(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    candidate_id: str | None = None,
    status: str = "succeeded",
    include_artifacts: bool = True,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = _load_json(run_dir / "real_run_manifest.json")
    selected_candidate_id = candidate_id or prepared["candidate_id"]
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    if include_artifacts:
        psf_dir.mkdir(parents=True, exist_ok=True)
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (psf_dir / "spectre.out").write_text(
            "sanitized spectre output\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean.log").write_text(
            "sanitized ocean log\n",
            encoding="utf-8",
        )
        (metrics_dir / "ocean_scalars.tsv").write_text(
            "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stdout").write_text(
            "sanitized stdout\n",
            encoding="utf-8",
        )
        (run_dir / "spectre.stderr").write_text("", encoding="utf-8")
    _write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "status": status,
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


def _write_metric_result_manifest(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    candidate_id: str | None = None,
    status: str = "succeeded",
    metric_status: str = "succeeded",
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
    selected_candidate_id = candidate_id or request["candidate_id"]
    _write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "backend": "spectre_ocean_batch",
            "status": status,
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
                    "status": metric_status,
                    "value": value if metric_status == "succeeded" else None,
                    "value_text": f"{value:.12g}" if metric_status == "succeeded" else None,
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name]["result"],
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [] if metric_status == "succeeded" else ["scalar failed"],
                }
                for name, value in values.items()
            ],
            "issues": [] if status == "succeeded" else ["ocean failed"],
        },
    )


def _record_real_001(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status.value == "pass"
    assert check_metric_results(project_dir).status.value == "pass"
    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T00:40:00Z",
    )
    assert report.status.value == "pass"
```

- [x] **Step 2: Add failing classification tests**

Append:

```python
from hermes_workflow.real_run_recovery import assess_real_run_recovery


def test_assess_recovery_classifies_pending_execution(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.status == RealRunRecoveryStatus.PASS
    assert report.classification == RealRunRecoveryClassification.PENDING_EXECUTION
    assert report.allowed_actions == [
        RealRunRecoveryAction.WAIT_FOR_EXECUTION,
        RealRunRecoveryAction.STOP_WORKFLOW,
    ]
    assert report.recommended_action == RealRunRecoveryAction.WAIT_FOR_EXECUTION


def test_assess_recovery_classifies_missing_result_after_evidence(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    (run_dir / "spectre.stdout").write_text("tool started\n", encoding="utf-8")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_MISSING
    assert RealRunRecoveryAction.RETRY_SAME_CANDIDATE in report.allowed_actions


def test_assess_recovery_classifies_failed_tool_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_FAILED
    assert report.recommended_action == RealRunRecoveryAction.RETRY_SAME_CANDIDATE


def test_assess_recovery_classifies_partial_tool_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, include_artifacts=False)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.TOOL_RESULT_PARTIAL
    assert "result artifact is missing" in " ".join(report.issues)


def test_assess_recovery_classifies_missing_metric_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_MISSING


def test_assess_recovery_classifies_failed_metric_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(
        project_dir,
        status="failed",
        metric_status="failed",
    )

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.METRIC_RESULT_FAILED
    assert RealRunRecoveryAction.REVISE_CONTRACTS in report.allowed_actions


def test_assess_recovery_classifies_recordable_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.RECORDABLE_SUCCESS
    assert report.allowed_actions == [RealRunRecoveryAction.RECORD_RESULT]


def test_assess_recovery_classifies_already_recorded(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    report = assess_real_run_recovery(project_dir, run_id="real_001")

    assert report.classification == RealRunRecoveryClassification.ALREADY_RECORDED
    assert report.allowed_actions == []
```

- [x] **Step 3: Run classification tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py -q
```

Expected: import failure for `hermes_workflow.real_run_recovery`.

- [x] **Step 4: Implement `real_run_recovery.py` classifier**

Create `src/hermes_workflow/real_run_recovery.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealRunRecoveryAction,
    RealRunRecoveryClassification,
    RealRunRecoveryReport,
    RealRunRecoveryStatus,
)
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.schemas import LedgerRow
from hermes_workflow.validate import assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_SCHEMA_VERSION = "1.0"
REAL_RUN_ROOT = "runs/real"
RECOVERY_REPORT = "reports/real_run_recovery_report.json"
REAL_RUN_CHECK_REPORT = "reports/real_run_check_report.json"
METRIC_RESULT_CHECK_REPORT = "reports/metric_result_check_report.json"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
RECOVERY_DECISION_NAME = "recovery_decision.json"
MAX_ATTEMPTS_PER_CANDIDATE = 2
EXECUTION_EVIDENCE_NAMES = (
    "result_manifest.tmp",
    "spectre.stdout",
    "spectre.stderr",
    "psf",
    "metrics",
)


@dataclass(frozen=True)
class _Assessment:
    classification: RealRunRecoveryClassification
    candidate_id: str | None
    issues: list[str]


def assess_real_run_recovery(
    project_dir: Path,
    *,
    run_id: str,
    persist_report: bool = True,
) -> RealRunRecoveryReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id)
    bundle = assert_valid_project(project_dir)
    run_dir = _project_path(bundle.project_dir, f"{REAL_RUN_ROOT}/{selected_run_id}")
    report_path = _project_path(bundle.project_dir, RECOVERY_REPORT)
    if persist_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        assessment = _classify_run(project_dir, selected_run_id, run_dir)
        status = RealRunRecoveryStatus.PASS
    except Exception as exc:
        assessment = _Assessment(
            classification=RealRunRecoveryClassification.CONTRACT_INVALID,
            candidate_id=None,
            issues=[str(exc)],
        )
        status = RealRunRecoveryStatus.FAIL

    attempt_number = _attempt_number(project_dir, assessment.candidate_id, selected_run_id)
    retry_budget_remaining = max(0, MAX_ATTEMPTS_PER_CANDIDATE - attempt_number)
    allowed_actions = _allowed_actions(
        assessment.classification,
        retry_budget_remaining=retry_budget_remaining,
    )
    report = RealRunRecoveryReport(
        schema_version=DEFAULT_SCHEMA_VERSION,
        status=status,
        run_id=selected_run_id,
        candidate_id=assessment.candidate_id,
        classification=assessment.classification,
        allowed_actions=allowed_actions,
        recommended_action=allowed_actions[0] if allowed_actions else None,
        attempt_number=attempt_number,
        max_attempts_per_candidate=MAX_ATTEMPTS_PER_CANDIDATE,
        retry_budget_remaining=retry_budget_remaining,
        real_run_check_report=REAL_RUN_CHECK_REPORT,
        metric_result_check_report=METRIC_RESULT_CHECK_REPORT,
        ledger_path=LEDGER_PATH,
        recovery_decision=_decision_relative(selected_run_id)
        if (run_dir / RECOVERY_DECISION_NAME).exists()
        else None,
        issues=assessment.issues,
    )
    if persist_report:
        _write_report(report_path, report)
    return report
```

Continue the module with exact helper behavior:

```python
def _classify_run(project_dir: Path, run_id: str, run_dir: Path) -> _Assessment:
    if not run_dir.exists():
        raise FileNotFoundError(f"real run directory is missing: {run_dir}")
    if run_dir.is_symlink():
        raise FileExistsError(f"real run directory must not be a symlink: {run_dir}")

    prepared = _load_json(run_dir / "real_run_manifest.json")
    candidate = _load_json(run_dir / "candidate.json")
    candidate_id = _candidate_id(prepared, candidate)
    decision = _load_optional_json(run_dir / RECOVERY_DECISION_NAME)
    if decision is not None:
        return _classify_resolved(project_dir, run_id, run_dir, candidate_id, decision)

    if _ledger_has_run_or_candidate(project_dir, run_id, candidate_id):
        return _Assessment(
            RealRunRecoveryClassification.ALREADY_RECORDED,
            candidate_id,
            [],
        )

    result_path = run_dir / "result_manifest.json"
    if not result_path.exists():
        classification = (
            RealRunRecoveryClassification.TOOL_RESULT_MISSING
            if _has_execution_evidence(run_dir)
            else RealRunRecoveryClassification.PENDING_EXECUTION
        )
        return _Assessment(classification, candidate_id, [])

    result_payload = _load_json(result_path)
    if result_payload.get("status") == "failed":
        real_report = check_real_run(project_dir, run_id=run_id, persist_report=True)
        if real_report.status != RealRunCheckStatus.PASS:
            return _Assessment(
                RealRunRecoveryClassification.TOOL_RESULT_PARTIAL,
                candidate_id,
                real_report.issues,
            )
        return _Assessment(
            RealRunRecoveryClassification.TOOL_RESULT_FAILED,
            candidate_id,
            [],
        )

    real_report = check_real_run(project_dir, run_id=run_id, persist_report=True)
    if real_report.status != RealRunCheckStatus.PASS:
        return _Assessment(
            RealRunRecoveryClassification.TOOL_RESULT_PARTIAL,
            candidate_id,
            real_report.issues,
        )

    metric_manifest_path = run_dir / "metrics" / "metric_result_manifest.json"
    if not metric_manifest_path.exists():
        return _Assessment(
            RealRunRecoveryClassification.METRIC_RESULT_MISSING,
            candidate_id,
            [],
        )

    metric_report = check_metric_results(project_dir, run_id=run_id, persist_report=True)
    if metric_report.status != MetricResultCheckStatus.PASS:
        return _Assessment(
            RealRunRecoveryClassification.METRIC_RESULT_FAILED,
            candidate_id,
            metric_report.issues,
        )

    return _Assessment(
        RealRunRecoveryClassification.RECORDABLE_SUCCESS,
        candidate_id,
        [],
    )


def _classify_resolved(
    project_dir: Path,
    run_id: str,
    run_dir: Path,
    candidate_id: str | None,
    decision: dict,
) -> _Assessment:
    decision_value = decision.get("decision")
    if decision_value == RealRunRecoveryAction.ABANDON_CANDIDATE.value:
        return _Assessment(RealRunRecoveryClassification.RESOLVED_ABANDONED, candidate_id, [])
    if decision_value == RealRunRecoveryAction.STOP_WORKFLOW.value:
        return _Assessment(RealRunRecoveryClassification.RESOLVED_STOPPED, candidate_id, [])
    if decision_value == RealRunRecoveryAction.RETRY_SAME_CANDIDATE.value:
        retry_run_id = decision.get("retry_run_id")
        if not isinstance(retry_run_id, str) or not RUN_ID_RE.match(retry_run_id):
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                ["retry decision has invalid retry_run_id"],
            )
        retry_manifest = (
            project_dir
            / REAL_RUN_ROOT
            / retry_run_id
            / "real_run_manifest.json"
        )
        if not retry_manifest.exists():
            return _Assessment(
                RealRunRecoveryClassification.CONTRACT_INVALID,
                candidate_id,
                ["retry decision does not point to a prepared retry package"],
            )
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_RETRY_PREPARED,
            candidate_id,
            [],
        )
    if decision_value == RealRunRecoveryAction.REVISE_CONTRACTS.value:
        return _Assessment(
            RealRunRecoveryClassification.RESOLVED_STOPPED,
            candidate_id,
            ["contract revision decision requires a new approval flow"],
        )
    return _Assessment(
        RealRunRecoveryClassification.CONTRACT_INVALID,
        candidate_id,
        ["recovery decision is invalid"],
    )
```

Add helpers:

```python
def _allowed_actions(
    classification: RealRunRecoveryClassification,
    *,
    retry_budget_remaining: int,
) -> list[RealRunRecoveryAction]:
    retry_actions: list[RealRunRecoveryAction] = (
        [RealRunRecoveryAction.RETRY_SAME_CANDIDATE]
        if retry_budget_remaining > 0
        else []
    )
    table: dict[RealRunRecoveryClassification, list[RealRunRecoveryAction]] = {
        RealRunRecoveryClassification.PENDING_EXECUTION: [
            RealRunRecoveryAction.WAIT_FOR_EXECUTION,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.CONTRACT_INVALID: [
            RealRunRecoveryAction.REVISE_CONTRACTS,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_MISSING: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_FAILED: [
            *retry_actions,
            RealRunRecoveryAction.ABANDON_CANDIDATE,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.TOOL_RESULT_PARTIAL: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.METRIC_RESULT_MISSING: [
            *retry_actions,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.METRIC_RESULT_FAILED: [
            *retry_actions,
            RealRunRecoveryAction.ABANDON_CANDIDATE,
            RealRunRecoveryAction.REVISE_CONTRACTS,
            RealRunRecoveryAction.STOP_WORKFLOW,
        ],
        RealRunRecoveryClassification.RECORDABLE_SUCCESS: [
            RealRunRecoveryAction.RECORD_RESULT,
        ],
        RealRunRecoveryClassification.ALREADY_RECORDED: [],
        RealRunRecoveryClassification.RESOLVED_RETRY_PREPARED: [],
        RealRunRecoveryClassification.RESOLVED_ABANDONED: [],
        RealRunRecoveryClassification.RESOLVED_STOPPED: [],
    }
    return table[classification]


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _project_path(project_dir: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must be project-relative and safe: {relative_path}")
    return project_dir / Path(*path.parts)


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"JSON file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON file is invalid: {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return _load_json(path)


def _candidate_id(prepared: dict, candidate: dict) -> str:
    prepared_candidate_id = prepared.get("candidate_id")
    candidate_candidate_id = candidate.get("candidate_id")
    if not isinstance(prepared_candidate_id, str):
        raise ValueError("prepared manifest candidate_id is invalid")
    if prepared_candidate_id != candidate_candidate_id:
        raise ValueError("candidate_id mismatch between manifest and candidate")
    return prepared_candidate_id


def _has_execution_evidence(run_dir: Path) -> bool:
    return any((run_dir / name).exists() for name in EXECUTION_EVIDENCE_NAMES)


def _ledger_rows(project_dir: Path) -> list[LedgerRow]:
    ledger_path = project_dir / LEDGER_PATH
    if not ledger_path.exists():
        return []
    rows: list[LedgerRow] = []
    for line_number, raw_line in enumerate(
        ledger_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not raw_line.strip():
            continue
        try:
            rows.append(LedgerRow.model_validate(json.loads(raw_line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"ledger row {line_number} is invalid: {exc}") from exc
    return rows


def _ledger_has_run_or_candidate(
    project_dir: Path,
    run_id: str,
    candidate_id: str | None,
) -> bool:
    for row in _ledger_rows(project_dir):
        if row.run_id == run_id or row.candidate_id == candidate_id:
            return True
    return False


def _attempt_number(project_dir: Path, candidate_id: str | None, run_id: str) -> int:
    if candidate_id is None:
        return 1
    root = project_dir / REAL_RUN_ROOT
    if not root.exists():
        return 1
    attempts = 0
    for run_dir in root.iterdir():
        if not RUN_ID_RE.match(run_dir.name) or run_dir.is_symlink():
            continue
        candidate_path = run_dir / "candidate.json"
        if not candidate_path.exists():
            continue
        try:
            candidate = _load_json(candidate_path)
        except (OSError, ValueError):
            continue
        if candidate.get("candidate_id") == candidate_id:
            attempts += 1
    return max(1, attempts)


def _decision_relative(run_id: str) -> str:
    return f"{REAL_RUN_ROOT}/{run_id}/{RECOVERY_DECISION_NAME}"


def _write_report(path: Path, report: RealRunRecoveryReport) -> None:
    path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
```

- [x] **Step 5: Run classification tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py -q
```

Expected: schema and classification tests pass.

- [x] **Step 6: Run focused compatibility tests**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py tests/test_real_result_record.py tests/test_next_real_run.py -q
python3 -m ruff check src/hermes_workflow/reports.py src/hermes_workflow/real_run_recovery.py tests/test_real_run_recovery.py
```

Expected: all tests pass and ruff is clean.

- [x] **Step 7: Commit Task 2**

```bash
git add src/hermes_workflow/real_run_recovery.py tests/test_real_run_recovery.py docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "feat: classify real run recovery state"
```

- [x] **Step 8: Task 2 review gate**

Run spec and code-quality reviews focused on:

```text
Review C-10 Task 2 recovery classifier.

Check:
- classification states match the C-10 design spec
- classification uses files and existing Hermes checkers, not chat state
- pending vs tool_result_missing is correctly distinguished by execution evidence
- already_recorded is derived from strict ledger rows
- no real tools, C-7 adapter calls, PSF parsing, formula rewriting, or ledger/state writes occur
- reports are persisted safely and deterministically
```

---

## Task 3: Recovery Decisions And Retry Packages

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Modify: `src/hermes_workflow/real_run_recovery.py`
- Modify: `tests/test_real_run_recovery.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [ ] **Step 1: Add failing decision and retry tests**

Append to `tests/test_real_run_recovery.py`:

```python
from hermes_workflow.real_run_recovery import (
    prepare_real_run_retry,
    resolve_real_run_failure,
)


def test_prepare_retry_writes_decision_and_new_package_same_candidate(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    retry = prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="spectre exited non-zero",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    failed_decision = _load_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    )
    retry_candidate = _load_json(
        project_dir / "runs" / "real" / "real_002" / "candidate.json"
    )
    retry_manifest = _load_json(
        project_dir / "runs" / "real" / "real_002" / "real_run_manifest.json"
    )
    retry_request = _load_json(
        project_dir / "runs" / "real" / "real_002" / "metric_extraction_request.json"
    )

    assert retry.run_id == "real_002"
    assert failed_decision["decision"] == "retry_same_candidate"
    assert failed_decision["retry_run_id"] == "real_002"
    assert retry_candidate["candidate_id"] == "real_001"
    assert retry_candidate["retry_of_run_id"] == "real_001"
    assert retry_candidate["retry_attempt_number"] == 2
    assert retry_manifest["run_id"] == "real_002"
    assert retry_manifest["candidate_id"] == "real_001"
    assert retry_manifest["package_kind"] == "retry"
    assert retry_request["run_id"] == "real_002"
    assert retry_request["candidate_id"] == "real_001"


def test_prepare_retry_preserves_rendered_input(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    original = (
        project_dir / "runs" / "real" / "real_001" / "input.scs"
    ).read_text(encoding="utf-8")

    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="try once more",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    retry_text = (
        project_dir / "runs" / "real" / "real_002" / "input.scs"
    ).read_text(encoding="utf-8")
    assert retry_text == original


def test_prepare_retry_refuses_existing_target(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    target = project_dir / "runs" / "real" / "real_002"
    target.mkdir(parents=True)
    (target / "leftover.txt").write_text("old data\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="real run directory is not empty"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert (target / "leftover.txt").read_text(encoding="utf-8") == "old data\n"


def test_prepare_retry_refuses_symlink_target(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = project_dir / "runs" / "real" / "real_002"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileExistsError, match="must not be a symlink"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_001",
            retry_run_id="real_002",
            reason="try once more",
        )

    assert list(outside.iterdir()) == []


def test_prepare_retry_refuses_third_attempt(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")
    prepare_real_run_retry(
        project_dir,
        failed_run_id="real_001",
        retry_run_id="real_002",
        reason="first retry",
        decided_at_utc="2026-06-02T01:00:00Z",
    )
    _write_result_manifest(
        project_dir,
        run_id="real_002",
        candidate_id="real_001",
        status="failed",
    )

    with pytest.raises(ValueError, match="retry budget is exhausted"):
        prepare_real_run_retry(
            project_dir,
            failed_run_id="real_002",
            retry_run_id="real_003",
            reason="third attempt",
        )


def test_resolve_abandon_writes_decision_without_retry(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    report = resolve_real_run_failure(
        project_dir,
        run_id="real_001",
        decision="abandon_candidate",
        reason="candidate is not worth retrying",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    decision = _load_json(
        project_dir / "runs" / "real" / "real_001" / "recovery_decision.json"
    )
    assert decision["decision"] == "abandon_candidate"
    assert "retry_run_id" not in decision
    assert report.classification == RealRunRecoveryClassification.RESOLVED_ABANDONED
```

- [ ] **Step 2: Run new tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py::test_prepare_retry_writes_decision_and_new_package_same_candidate tests/test_real_run_recovery.py::test_resolve_abandon_writes_decision_without_retry -q
```

Expected: import failure for `prepare_real_run_retry` and `resolve_real_run_failure`.

- [ ] **Step 3: Refactor `real_run.py` package writer for retry candidate identity**

Modify `_write_real_run_package()` in `src/hermes_workflow/real_run.py`:

```python
        candidate_id = str(candidate["candidate_id"])
        metric_request_payload = build_metric_extraction_request(
            bundle,
            run_id=selected_run_id,
            candidate_id=candidate_id,
            prepared_input_scs=rendered_relative,
            prepared_input_sha256=sha256_file(rendered_path),
        )
```

Modify `_build_manifest()` signature to accept `candidate_id: str`:

```python
def _build_manifest(
    bundle: ContractBundle,
    run_id: str,
    candidate_id: str,
    created_at_utc: str,
    instruction: dict,
    approved_hashes: dict[str, str],
    template_relative: str,
    rendered_relative: str,
    candidate_relative: str,
    metric_request_relative: str,
    template_path: Path,
    rendered_path: Path,
    metric_request_path: Path,
) -> dict:
```

Pass `candidate_id` from `_write_real_run_package()`:

```python
        manifest_payload = _build_manifest(
            bundle,
            selected_run_id,
            candidate_id,
            created_at_utc,
            instruction,
            approved_hashes,
            template_relative,
            rendered_relative,
            candidate_relative,
            metric_request_relative,
            template_path,
            rendered_path,
            metric_request_path,
        )
```

Change the manifest field:

```python
        "candidate_id": candidate_id,
```

Existing first-run and next-run behavior remains unchanged because their candidate payloads already use `candidate_id == run_id`.

- [ ] **Step 4: Implement decision and retry functions**

Extend `src/hermes_workflow/real_run_recovery.py` imports:

```python
from datetime import UTC, datetime

from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import (
    RealRunPackage,
    _approved_hashes,
    _assert_approved,
    _assert_config_hashes,
    _load_execution_manifest,
    _load_supervisor_instruction,
    _next_unused_run_id,
    _write_real_run_package,
)
```

Add:

```python
@dataclass(frozen=True)
class RealRunRetryPackage:
    run_id: str
    failed_run_id: str
    decision_path: Path
    package: RealRunPackage
```

Add public functions:

```python
def prepare_real_run_retry(
    project_dir: Path,
    *,
    failed_run_id: str,
    retry_run_id: str | None = None,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRetryPackage:
    project_dir = Path(project_dir)
    selected_failed_run_id = _validate_run_id(failed_run_id)
    assessment = assess_real_run_recovery(
        project_dir,
        run_id=selected_failed_run_id,
        persist_report=True,
    )
    if RealRunRecoveryAction.RETRY_SAME_CANDIDATE not in assessment.allowed_actions:
        raise ValueError("retry_same_candidate is not allowed for this run")
    if assessment.retry_budget_remaining <= 0:
        raise ValueError("retry budget is exhausted")

    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)
    bundle = assert_valid_project(project_dir)

    selected_retry_run_id = _validate_run_id(retry_run_id or _next_unused_run_id(project_dir))
    if selected_retry_run_id == selected_failed_run_id:
        raise ValueError("retry run_id must differ from failed run_id")

    failed_run_dir = project_dir / REAL_RUN_ROOT / selected_failed_run_id
    failed_candidate = _load_json(failed_run_dir / "candidate.json")
    failed_parameters = failed_candidate.get("parameters")
    if not isinstance(failed_parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in failed_parameters.items()
    ):
        raise ValueError("failed run candidate parameters are invalid")
    candidate_id = assessment.candidate_id
    if candidate_id is None:
        raise ValueError("failed run candidate_id is unknown")

    decision_path = failed_run_dir / RECOVERY_DECISION_NAME
    if decision_path.exists():
        raise FileExistsError(f"recovery decision already exists: {decision_path}")

    decision_payload = _decision_payload(
        project_dir,
        run_id=selected_failed_run_id,
        candidate_id=candidate_id,
        decision=RealRunRecoveryAction.RETRY_SAME_CANDIDATE,
        reason=reason,
        decided_at_utc=decided_at_utc or _utc_now(),
        retry_run_id=selected_retry_run_id,
    )
    decision_path.write_text(
        json.dumps(decision_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    retry_candidate = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "source": "retry_same_candidate",
        "candidate_index": failed_candidate.get("candidate_index"),
        "parameters": failed_parameters,
        "retry_of_run_id": selected_failed_run_id,
        "retry_attempt_number": assessment.attempt_number + 1,
        "recovery_decision": _decision_relative(selected_failed_run_id),
    }
    try:
        package = _write_real_run_package(
            bundle,
            selected_retry_run_id,
            retry_candidate,
            decided_at_utc or _utc_now(),
            instruction,
            approved_hashes,
            manifest_extra={
                "package_kind": "retry",
                "retry_of_run_id": selected_failed_run_id,
                "retry_attempt_number": assessment.attempt_number + 1,
                "recovery_decision": _decision_relative(selected_failed_run_id),
                "recovery_decision_sha256": sha256_file(decision_path),
            },
        )
    except Exception:
        decision_path.unlink(missing_ok=True)
        raise
    return RealRunRetryPackage(
        run_id=selected_retry_run_id,
        failed_run_id=selected_failed_run_id,
        decision_path=decision_path,
        package=package,
    )


def resolve_real_run_failure(
    project_dir: Path,
    *,
    run_id: str,
    decision: str,
    reason: str,
    decided_at_utc: str | None = None,
) -> RealRunRecoveryReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id)
    action = RealRunRecoveryAction(decision)
    if action == RealRunRecoveryAction.RETRY_SAME_CANDIDATE:
        raise ValueError("use prepare_real_run_retry for retry_same_candidate")
    if action in {
        RealRunRecoveryAction.RECORD_RESULT,
        RealRunRecoveryAction.WAIT_FOR_EXECUTION,
    }:
        raise ValueError(f"{action.value} is not a recovery decision")

    assessment = assess_real_run_recovery(
        project_dir,
        run_id=selected_run_id,
        persist_report=True,
    )
    if action not in assessment.allowed_actions:
        raise ValueError(f"{action.value} is not allowed for this run")

    run_dir = project_dir / REAL_RUN_ROOT / selected_run_id
    decision_path = run_dir / RECOVERY_DECISION_NAME
    if decision_path.exists():
        raise FileExistsError(f"recovery decision already exists: {decision_path}")
    if assessment.candidate_id is None:
        raise ValueError("run candidate_id is unknown")
    payload = _decision_payload(
        project_dir,
        run_id=selected_run_id,
        candidate_id=assessment.candidate_id,
        decision=action,
        reason=reason,
        decided_at_utc=decided_at_utc or _utc_now(),
        retry_run_id=None,
    )
    decision_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return assess_real_run_recovery(project_dir, run_id=selected_run_id)
```

Add helpers:

```python
def _decision_payload(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str,
    decision: RealRunRecoveryAction,
    reason: str,
    decided_at_utc: str,
    retry_run_id: str | None,
) -> dict:
    report_path = project_dir / RECOVERY_REPORT
    payload = {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "decision": decision.value,
        "decided_at_utc": decided_at_utc,
        "decided_by": "supervisor_agent",
        "reason": reason,
        "source_recovery_report": RECOVERY_REPORT,
        "source_recovery_report_sha256": sha256_file(report_path),
        "issues": [],
    }
    if retry_run_id is not None:
        payload["retry_run_id"] = retry_run_id
    return payload


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 5: Run retry tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py -q
```

Expected: all recovery tests pass.

- [ ] **Step 6: Run package compatibility tests**

Run:

```bash
python3 -m pytest tests/test_real_run_recovery.py tests/test_real_run.py tests/test_metric_results.py tests/test_result_handoff.py tests/test_real_result_record.py -q
python3 -m ruff check src/hermes_workflow/real_run.py src/hermes_workflow/real_run_recovery.py tests/test_real_run_recovery.py
```

Expected: all tests pass and ruff is clean.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/hermes_workflow/real_run.py src/hermes_workflow/real_run_recovery.py tests/test_real_run_recovery.py docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "feat: prepare real run retry packages"
```

- [ ] **Step 8: Task 3 review gate**

Run spec and code-quality reviews focused on:

```text
Review C-10 Task 3 recovery decisions and retry package writer.

Check:
- retry writes a new run_id while preserving original candidate_id and parameters
- failed artifacts are not overwritten
- recovery_decision.json is explicit and auditable
- retry target directories and symlinks fail closed
- retry budget prevents third attempts
- metric request uses retry run_id and original candidate_id
- C-10 still does not run real tools, call C-7, parse PSF, rewrite formulas, or write ledger/state
```

---

## Task 4: C-9 Unresolved Real-Run Guard

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Modify: `src/hermes_workflow/real_run_recovery.py`
- Modify: `tests/test_next_real_run.py`
- Modify: `tests/test_real_run_recovery.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [ ] **Step 1: Add failing C-9 guard tests**

Append to `tests/test_next_real_run.py`:

```python
def test_prepare_next_real_run_refuses_unresolved_pending_package(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_unresolved_failed_package(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002")
    result_path = project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    result = _load_json(result_path)
    result["status"] = "failed"
    _write_json(result_path, result)

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)
```

Append an abandoned-case test:

```python
def test_prepare_next_real_run_continues_after_abandoned_candidate(
    tmp_path: Path,
) -> None:
    from hermes_workflow.real_run_recovery import resolve_real_run_failure

    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-02T00:50:00Z",
    )
    _write_result_manifest(project_dir, run_id="real_002")
    result_path = project_dir / "runs" / "real" / "real_002" / "result_manifest.json"
    result = _load_json(result_path)
    result["status"] = "failed"
    _write_json(result_path, result)
    resolve_real_run_failure(
        project_dir,
        run_id="real_002",
        decision="abandon_candidate",
        reason="skip this candidate",
        decided_at_utc="2026-06-02T01:00:00Z",
    )

    package = prepare_next_real_run(
        project_dir,
        run_id="real_003",
        created_at_utc="2026-06-02T01:10:00Z",
    )

    assert package.run_id == "real_003"
```

- [ ] **Step 2: Run guard tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_pending_package tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_failed_package -q
```

Expected: tests fail because C-9 currently allows preparing another package while an unresolved package exists.

- [ ] **Step 3: Add unresolved guard helper**

Append to `src/hermes_workflow/real_run_recovery.py`:

```python
RESOLVED_CLASSIFICATIONS = {
    RealRunRecoveryClassification.ALREADY_RECORDED,
    RealRunRecoveryClassification.RESOLVED_ABANDONED,
}


def assert_no_unresolved_real_runs(project_dir: Path) -> None:
    project_dir = Path(project_dir)
    root = project_dir / REAL_RUN_ROOT
    if not root.exists():
        return
    unresolved: list[str] = []
    for run_dir in sorted(root.iterdir()):
        if not RUN_ID_RE.match(run_dir.name):
            continue
        if run_dir.is_symlink():
            raise FileExistsError(
                f"real run directory must not be a symlink: {run_dir}"
            )
        if not run_dir.is_dir():
            continue
        report = assess_real_run_recovery(
            project_dir,
            run_id=run_dir.name,
            persist_report=False,
        )
        if report.classification not in RESOLVED_CLASSIFICATIONS:
            unresolved.append(f"{run_dir.name}:{report.classification.value}")
    if unresolved:
        raise ValueError("unresolved real run exists: " + ", ".join(unresolved))
```

- [ ] **Step 4: Call guard from C-9**

Modify `prepare_next_real_run()` in `src/hermes_workflow/real_run.py` after config hash validation and before reading the ledger:

```python
    from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

    assert_no_unresolved_real_runs(project_dir)
```

Place the import inside the function to avoid a module import cycle.

- [ ] **Step 5: Run guard tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_pending_package tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_failed_package tests/test_next_real_run.py::test_prepare_next_real_run_continues_after_abandoned_candidate -q
```

Expected: 3 tests pass.

- [ ] **Step 6: Run focused integration tests**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py -q
python3 -m ruff check src/hermes_workflow/real_run.py src/hermes_workflow/real_run_recovery.py tests/test_next_real_run.py tests/test_real_run_recovery.py
```

Expected: all tests pass and ruff is clean.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/hermes_workflow/real_run.py src/hermes_workflow/real_run_recovery.py tests/test_next_real_run.py tests/test_real_run_recovery.py docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "feat: block next runs on unresolved real runs"
```

- [ ] **Step 8: Task 4 review gate**

Run spec and code-quality reviews focused on:

```text
Review C-10 Task 4 unresolved real-run guard.

Check:
- C-9 cannot silently skip pending, failed, partial, or retry-prepared runs
- abandoned and already-recorded runs are treated as resolved
- symlinked run directories fail closed
- no real tools, C-7 calls, PSF parsing, formula rewriting, or ledger/state writes occur
- no circular import risk at module import time
```

---

## Task 5: CLI Integration

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_cli_assess_real_run_recovery_reports_pending(tmp_path: Path) -> None:
    from tests.test_real_run_recovery import _create_ready_project

    project_dir = _create_ready_project(tmp_path)

    result = runner.invoke(
        app,
        ["assess-real-run-recovery", str(project_dir), "--run-id", "real_001"],
    )

    assert result.exit_code == 0
    assert "real run recovery assessed" in result.output
    assert "classification: pending_execution" in result.output
    assert "report: reports/real_run_recovery_report.json" in result.output


def test_cli_resolve_real_run_failure_writes_abandon_decision(
    tmp_path: Path,
) -> None:
    from tests.test_real_run_recovery import _create_ready_project, _write_result_manifest

    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    result = runner.invoke(
        app,
        [
            "resolve-real-run-failure",
            str(project_dir),
            "--run-id",
            "real_001",
            "--decision",
            "abandon_candidate",
            "--reason",
            "skip failed candidate",
        ],
    )

    assert result.exit_code == 0
    assert "real run failure resolved" in result.output
    assert "decision: abandon_candidate" in result.output


def test_cli_prepare_real_run_retry_outputs_paths(tmp_path: Path) -> None:
    from tests.test_real_run_recovery import _create_ready_project, _write_result_manifest

    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir, status="failed")

    result = runner.invoke(
        app,
        [
            "prepare-real-run-retry",
            str(project_dir),
            "--failed-run-id",
            "real_001",
            "--retry-run-id",
            "real_002",
            "--reason",
            "retry failed simulation",
        ],
    )

    assert result.exit_code == 0
    assert "real run retry package prepared" in result.output
    assert "failed run: runs/real/real_001" in result.output
    assert "retry run: runs/real/real_002" in result.output
    assert "decision: runs/real/real_001/recovery_decision.json" in result.output
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_cli.py::test_cli_assess_real_run_recovery_reports_pending tests/test_cli.py::test_cli_prepare_real_run_retry_outputs_paths -q
```

Expected: Typer reports missing commands.

- [ ] **Step 3: Add CLI imports**

Modify `src/hermes_workflow/cli.py` imports:

```python
from hermes_workflow.real_run_recovery import (
    assess_real_run_recovery,
    prepare_real_run_retry,
    resolve_real_run_failure,
)
```

- [ ] **Step 4: Add CLI commands**

Append commands after `prepare_next_real_run_command()` and before `check_real_run_command()`:

```python
@app.command("assess-real-run-recovery")
def assess_real_run_recovery_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a real-run package."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Real-run package id such as real_002."),
    ],
) -> None:
    try:
        report = assess_real_run_recovery(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run recovery assessed")
    typer.echo(f"run: runs/real/{report.run_id}")
    typer.echo(f"classification: {report.classification.value}")
    if report.recommended_action is not None:
        typer.echo(f"recommended: {report.recommended_action.value}")
    typer.echo("report: reports/real_run_recovery_report.json")
    if report.status.value != "pass":
        raise typer.Exit(code=1)


@app.command("prepare-real-run-retry")
def prepare_real_run_retry_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a failed real-run package."),
    ],
    failed_run_id: Annotated[
        str,
        typer.Option("--failed-run-id", help="Failed real-run id such as real_002."),
    ],
    retry_run_id: Annotated[
        str | None,
        typer.Option("--retry-run-id", help="Optional retry real-run id."),
    ] = None,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Supervisor reason for retry."),
    ] = "supervisor requested retry",
) -> None:
    try:
        retry = prepare_real_run_retry(
            project_dir,
            failed_run_id=failed_run_id,
            retry_run_id=retry_run_id,
            reason=reason,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run retry package prepared")
    typer.echo(f"failed run: runs/real/{retry.failed_run_id}")
    typer.echo(f"retry run: runs/real/{retry.run_id}")
    typer.echo(f"decision: {retry.decision_path.relative_to(project_dir)}")
    typer.echo(f"manifest: {retry.package.manifest_path.relative_to(project_dir)}")


@app.command("resolve-real-run-failure")
def resolve_real_run_failure_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a failed real-run package."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Real-run package id such as real_002."),
    ],
    decision: Annotated[
        str,
        typer.Option(
            "--decision",
            help="Recovery decision: abandon_candidate, stop_workflow, or revise_contracts.",
        ),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Supervisor reason for this decision."),
    ],
) -> None:
    try:
        report = resolve_real_run_failure(
            project_dir,
            run_id=run_id,
            decision=decision,
            reason=reason,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run failure resolved")
    typer.echo(f"run: runs/real/{report.run_id}")
    typer.echo(f"decision: {decision}")
    typer.echo(f"classification: {report.classification.value}")
    typer.echo(f"decision_file: runs/real/{report.run_id}/recovery_decision.json")
```

- [ ] **Step 5: Run CLI tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_cli.py::test_cli_assess_real_run_recovery_reports_pending tests/test_cli.py::test_cli_resolve_real_run_failure_writes_abandon_decision tests/test_cli.py::test_cli_prepare_real_run_retry_outputs_paths -q
```

Expected: 3 tests pass.

- [ ] **Step 6: Run focused CLI verification**

Run:

```bash
python3 -m pytest tests/test_cli.py tests/test_real_run_recovery.py tests/test_next_real_run.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/real_run_recovery.py tests/test_cli.py
```

Expected: all tests pass and ruff is clean.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/hermes_workflow/cli.py tests/test_cli.py docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "feat: add real run recovery cli"
```

---

## Task 6: Docs, Progress, Final Verification

**Files:**

- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`

- [ ] **Step 1: Update project overview**

In `docs/PROJECT_WORKFLOW_OVERVIEW.md`, add a C-10 current node after C-9:

```markdown
- Plan C C-10 real-run failure/retry policy contract 已完成：Hermes workflow tooling 可通过 `assess-real-run-recovery` 对 pending/failed/partial/metric-failed/recordable/recorded run 做 deterministic classification，通过 `prepare-real-run-retry` 为同一 candidate 准备新的 retry package，通过 `resolve-real-run-failure` 写入 abandon/stop/revise decision。C-10 不运行真实工具，不调用 C-7 adapter，不写 ledger/state，不解析 PSF，不改写公式。
```

Add CLI commands to the usage section:

```bash
hermes-workflow assess-real-run-recovery projects/bridge_test_inv --run-id real_002
hermes-workflow prepare-real-run-retry projects/bridge_test_inv --failed-run-id real_002
hermes-workflow resolve-real-run-failure projects/bridge_test_inv --run-id real_002 --decision abandon_candidate --reason "skip failed candidate"
```

- [ ] **Step 2: Update execution progress**

Append to `docs/EXECUTION_PROGRESS_2026-05-29.md`:

```markdown
## Plan C C-10 Real-Run Failure Retry Policy Contract

Status: complete and reviewed as of 2026-06-02.

Implemented:

- `assess_real_run_recovery()` classifies pending, invalid, failed, partial, metric-failed, recordable, recorded, retry-prepared, abandoned, and stopped real-run states.
- `prepare_real_run_retry()` writes an auditable `recovery_decision.json` and prepares a new C-4/C-6/C-7-compatible package for the same candidate with a new run id.
- `resolve_real_run_failure()` writes abandon/stop/revise decisions without writing optimizer ledger/state.
- `prepare-next-real-run` now fails closed while unresolved real-run packages exist.

Locked C-10 policy:

- C-10 is contract-only.
- It does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- It does not parse PSF, rewrite OCEAN formulas, compute metrics in Python, write optimizer ledger/state, or add failure-penalty rows.
- Failed and partial run artifacts remain evidence and are not overwritten.

Verification:

- `python3 -m pytest -q`
- `python3 -m ruff check src tests tools`
- `git diff --check`

Next:

- C-11 local smoke chaining C-9 -> C-7 -> C-8 with one controlled C-10 failure/retry case.
```

- [ ] **Step 3: Update compact checkpoint and next log**

In `docs/COMPACT_RESUME_CHECKPOINT.md`, add:

```markdown
- C-10 real-run failure/retry policy contract is complete and reviewed. It adds recovery assessment, explicit supervisor decision files, retry package preparation for the same candidate with a new run id, and a C-9 unresolved-run guard. It remains contract-only and does not run real tools, call C-7, write ledger/state, parse PSF, or rewrite formulas.
```

In `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, update current status:

```markdown
- Plan C C-10 real-run failure/retry policy contract: complete and reviewed.
- Next required action: C-11 local smoke chaining C-9 -> C-7 -> C-8 with one controlled C-10 failure/retry case.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected:

- full test suite passes
- ruff clean
- no whitespace errors

- [ ] **Step 5: Commit docs/progress**

```bash
git add docs/PROJECT_WORKFLOW_OVERVIEW.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md
git commit -m "docs: record real run recovery progress"
```

- [ ] **Step 6: Final combined review**

Run final spec and code-quality reviews focused on:

```text
Final review C-10 real-run failure/retry policy contract.

Check:
- C-10 design spec is implemented
- classification states are deterministic and file-backed
- retry preserves failed evidence and uses a new run id for the same candidate
- failed runs do not write optimizer ledger/state
- C-9 cannot advance past unresolved real-run packages
- CLI uses locked supervisor/Hermes tooling/execution-agent terminology
- no real tools, C-7 adapter calls, PSF parsing, formula rewriting, or failure-penalty rows are introduced
- local OCEAN evidence files remain untracked and uncommitted
```

- [ ] **Step 7: Mark C-10 complete in this plan**

Update this plan's task checkboxes to complete and leave final verification command outputs in the task notes.

## Self-Review Checklist

- Spec coverage: Tasks 1-6 cover report schema, classification, allowed actions, recovery decisions, retry packages, C-9 guard, CLI, docs, and final review from the C-10 design spec.
- Boundary check: No task invokes Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, network access, or the C-7 adapter.
- Formula safety: C-10 copies existing request/package formulas and never rewrites or computes formulas.
- State safety: C-10 does not write optimizer ledger/state; C-8 remains the only successful-result record path.
- Evidence safety: C-10 preserves failed run artifacts and writes retry attempts to new run directories.
- Placeholder scan: No unresolved placeholders, incomplete steps, or unspecified test steps.
