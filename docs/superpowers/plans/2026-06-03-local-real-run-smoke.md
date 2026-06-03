# Local Real-Run Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build C-11 local/fake controlled smoke coverage for the real-run workflow loop before any real tool or real agent integration.

**Architecture:** Keep C-11 entirely in tests and documentation. Add a small test-only helper for synthetic approved projects and fake C-7-style returned artifacts, then add library-level happy-path and failure/retry smoke tests plus one narrow CLI smoke. The smoke must exercise existing Hermes workflow tooling entry points without running Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, network access, or subprocess-backed C-7 adapter commands.

**Tech Stack:** Python 3.11+, pytest, Typer `CliRunner`, existing `hermes_workflow` modules, synthetic test files under pytest temporary directories.

---

## Required Reading

- `AGENTS.md`
- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`
- `docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`
- `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`
- `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/real_run_recovery.py`
- `src/hermes_workflow/cli.py`
- `tests/test_next_real_run.py`
- `tests/test_real_run_recovery.py`
- `tests/test_real_result_record.py`
- `tests/test_cli.py`

Before implementation, run codegraph context/search for the exact task being executed. If codegraph is unavailable or stale, state that and use `rg` plus focused file reads.

## Execution Model

Use Subagent-Driven Development.

Risk-tiered gates:

- Task 1 is medium risk test-infrastructure work. Run focused helper tests and code-quality review.
- Task 2 is medium risk integration test work. Run focused smoke tests and spec/code-quality review.
- Task 3 is high risk because it validates failure/retry state transitions and C-9 blocking. Run focused smoke/recovery/next-run tests and spec/code-quality review.
- Task 4 is medium risk CLI/docs/final verification. Run focused CLI smoke, full tests, ruff, `git diff --check`, and final combined review.

Stop after each task is implemented, verified, reviewed, committed, and recorded. Do not start the next task until the user confirms.

No task may run Virtuoso, Spectre, OCEAN, SSH, Claude CLI as an execution agent, `virtuoso-bridge-lite`, network access, or the C-7 adapter with a subprocess-backed runner.

## File Map

- Create `tests/real_run_smoke_helpers.py`: test-only helpers for approved fake projects, fake result manifests, fake metric result manifests, checked recording, and ledger reads.
- Create `tests/test_local_real_run_smoke.py`: C-11 helper, library happy-path, library failure/retry, and CLI smoke tests.
- Modify `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`: check off completed tasks.
- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: record the current C-11 task checkpoint.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record the current C-11 task checkpoint.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: record compact-resume state.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: record C-11 completion after final gate.
- Modify `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`: record C-11 completion after final gate.

Do not modify production modules unless a test exposes a real integration bug. If that happens, update the design spec and this plan before changing production behavior.

## Shared Constants

Use these in `tests/real_run_smoke_helpers.py`:

```python
TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""

DEFAULT_VALUES = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
```

Use fixed timestamps in tests:

```text
2026-06-03T00:00:00Z package build
2026-06-03T00:10:00Z approval
2026-06-03T00:20:00Z first real run package
2026-06-03T00:30:00Z fake execution start
2026-06-03T00:31:00Z fake execution complete
2026-06-03T00:40:00Z seed record
2026-06-03T00:50:00Z next run package
2026-06-03T01:00:00Z recovery decision
2026-06-03T01:10:00Z retry record
```

---

## Task 1: Test-Only Smoke Helpers

**Files:**

- Create: `tests/real_run_smoke_helpers.py`
- Create: `tests/test_local_real_run_smoke.py`
- Modify: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] **Step 1: Write the failing helper smoke test**

Create `tests/test_local_real_run_smoke.py` with this initial content:

```python
from __future__ import annotations

from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    ledger_rows,
    record_checked_run,
)


def test_c11_helper_seeds_recorded_real_result(tmp_path):
    project_dir = create_approved_real_project(tmp_path)

    report = record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    rows = ledger_rows(project_dir)
    assert report.status.value == "pass"
    assert [row["run_id"] for row in rows] == ["real_001"]
    assert [row["candidate_id"] for row in rows] == ["real_001"]
    assert_no_unresolved_real_runs(project_dir)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py::test_c11_helper_seeds_recorded_real_result -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tests.real_run_smoke_helpers'`.

- [ ] **Step 3: Add the test-only helper module**

Create `tests/real_run_smoke_helpers.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealResultRecordReport,
)
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""

DEFAULT_VALUES = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def create_approved_real_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-03T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-03T00:20:00Z")
    return project_dir


def write_fake_result_manifest(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    status: str = "succeeded",
    include_artifacts: bool = True,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    prepared = load_json(run_dir / "real_run_manifest.json")
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
    write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": selected_candidate_id,
            "status": status,
            "started_at_utc": "2026-06-03T00:30:00Z",
            "completed_at_utc": "2026-06-03T00:31:00Z",
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


def write_fake_metric_result_manifest(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    status: str = "succeeded",
    metric_status: str = "succeeded",
    values: dict[str, float] | None = None,
) -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = load_json(request_path)
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    selected_candidate_id = candidate_id or request["candidate_id"]
    metric_values = values or DEFAULT_VALUES
    write_json(
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
                "scalar_output_file": (
                    f"runs/real/{run_id}/metrics/ocean_scalars.tsv"
                ),
            },
            "metrics": [
                {
                    "name": name,
                    "status": metric_status,
                    "value": value if metric_status == "succeeded" else None,
                    "value_text": (
                        f"{value:.12g}" if metric_status == "succeeded" else None
                    ),
                    "unit": request_by_name[name]["unit"],
                    "result": request_by_name[name]["result"],
                    "expression": request_by_name[name]["expression"],
                    "expression_sha256": request_by_name[name]["expression_sha256"],
                    "expression_source": request_by_name[name]["expression_source"],
                    "issues": [] if metric_status == "succeeded" else ["scalar failed"],
                }
                for name, value in metric_values.items()
            ],
            "issues": [] if status == "succeeded" else ["ocean failed"],
        },
    )


def record_checked_run(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None = None,
    recorded_at_utc: str,
) -> RealResultRecordReport:
    write_fake_result_manifest(project_dir, run_id=run_id, candidate_id=candidate_id)
    write_fake_metric_result_manifest(
        project_dir,
        run_id=run_id,
        candidate_id=candidate_id,
    )
    assert check_real_run(project_dir, run_id=run_id).status == RealRunCheckStatus.PASS
    assert (
        check_metric_results(project_dir, run_id=run_id).status
        == MetricResultCheckStatus.PASS
    )
    return record_real_result(
        project_dir,
        run_id=run_id,
        recorded_at_utc=recorded_at_utc,
    )


def ledger_rows(project_dir: Path) -> list[dict]:
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    return [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py::test_c11_helper_seeds_recorded_real_result -q
```

Expected: 1 test passes.

- [ ] **Step 5: Run focused lint**

Run:

```bash
python3 -m ruff check tests/real_run_smoke_helpers.py tests/test_local_real_run_smoke.py
```

Expected: all checks pass.

- [ ] **Step 6: Update task status and node files**

In this plan, mark Task 1 steps as complete.

Update the current node in `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` to:

```text
- Current scope: Plan C C-11 local smoke implementation
- Current status: C-11 Task 1 test-only smoke helpers complete and reviewed
- Next required action: wait for user confirmation before C-11 Task 2 library happy-path smoke
```

Add matching C-11 Task 1 checkpoint bullets to `docs/EXECUTION_PROGRESS_2026-05-29.md` and `docs/COMPACT_RESUME_CHECKPOINT.md`.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add tests/real_run_smoke_helpers.py tests/test_local_real_run_smoke.py docs/superpowers/plans/2026-06-03-local-real-run-smoke.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "test: add local real run smoke helpers"
```

Expected: commit succeeds. Do not stage local OCEAN research or toolchain evidence files.

---

## Task 2: Library Happy-Path Smoke

**Files:**

- Modify: `tests/test_local_real_run_smoke.py`
- Modify: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] **Step 1: Add the failing happy-path smoke test**

Append to `tests/test_local_real_run_smoke.py`:

```python
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.real_run import prepare_next_real_run
from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs
from hermes_workflow.reports import (
    MetricResultCheckStatus,
    RealRunCheckStatus,
    RealResultRecordStatus,
)
from hermes_workflow.result_handoff import check_real_run
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
    ledger_rows,
    load_json,
    record_checked_run,
    write_fake_metric_result_manifest,
    write_fake_result_manifest,
)


def test_c11_library_happy_path_records_next_real_run(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-03T00:50:00Z",
    )
    assert package.run_id == "real_002"

    write_fake_result_manifest(project_dir, run_id="real_002")
    write_fake_metric_result_manifest(project_dir, run_id="real_002")

    real_report = check_real_run(project_dir, run_id="real_002")
    metric_report = check_metric_results(project_dir, run_id="real_002")
    record_report = record_real_result(
        project_dir,
        run_id="real_002",
        recorded_at_utc="2026-06-03T01:00:00Z",
    )

    rows = ledger_rows(project_dir)
    state = load_json(project_dir / "state" / "optimizer_state.json")
    best = load_json(project_dir / "state" / "best_candidate.json")

    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
    assert record_report.status == RealResultRecordStatus.PASS
    assert [row["run_id"] for row in rows] == ["real_001", "real_002"]
    assert rows[1]["candidate_id"] == "real_002"
    assert rows[1]["parameters"] == package.candidate_payload["parameters"]
    assert state["current_evaluations"] == 2
    assert best["candidate_id"] in {row["candidate_id"] for row in rows}
    assert (project_dir / "reports" / "real_run_check_report.json").exists()
    assert (project_dir / "reports" / "metric_result_check_report.json").exists()
    assert (project_dir / "reports" / "real_result_record_report.json").exists()
    assert_no_unresolved_real_runs(project_dir)
```

If Task 1 already imported `assert_no_unresolved_real_runs`, replace the import block instead of duplicating imports. Keep imports sorted by ruff.

- [ ] **Step 2: Run the new test and verify it fails or passes for the right reason**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py::test_c11_library_happy_path_records_next_real_run -q
```

Expected: the test should pass if Task 1 helpers were complete. If it fails, the failure must identify a real mismatch in the integration chain; fix only the test/helper or documented contract issue needed for this task.

- [ ] **Step 3: Run focused regression tests**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py tests/test_next_real_run.py tests/test_real_result_record.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run focused lint**

Run:

```bash
python3 -m ruff check tests/real_run_smoke_helpers.py tests/test_local_real_run_smoke.py
```

Expected: all checks pass.

- [ ] **Step 5: Update task status and node files**

In this plan, mark Task 2 steps as complete.

Update the current node in `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` to:

```text
- Current scope: Plan C C-11 local smoke implementation
- Current status: C-11 Task 2 library happy-path smoke complete and reviewed
- Next required action: wait for user confirmation before C-11 Task 3 controlled failure/retry smoke
```

Add matching C-11 Task 2 checkpoint bullets to `docs/EXECUTION_PROGRESS_2026-05-29.md` and `docs/COMPACT_RESUME_CHECKPOINT.md`.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add tests/test_local_real_run_smoke.py docs/superpowers/plans/2026-06-03-local-real-run-smoke.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "test: cover local real run happy path"
```

Expected: commit succeeds. Do not stage local OCEAN research or toolchain evidence files.

---

## Task 3: Controlled Failure/Retry Smoke

**Files:**

- Modify: `tests/test_local_real_run_smoke.py`
- Modify: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] **Step 1: Add the failing failure/retry smoke test**

Append to `tests/test_local_real_run_smoke.py`:

```python
import pytest

from hermes_workflow.real_run_recovery import (
    assess_real_run_recovery,
    prepare_real_run_retry,
)
from hermes_workflow.reports import RealRunRecoveryAction, RealRunRecoveryClassification


def test_c11_controlled_failure_retry_records_retry_success(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )

    failed_package = prepare_next_real_run(
        project_dir,
        run_id="real_002",
        created_at_utc="2026-06-03T00:50:00Z",
    )
    write_fake_result_manifest(
        project_dir,
        run_id="real_002",
        status="failed",
    )

    failed_report = assess_real_run_recovery(project_dir, run_id="real_002")
    assert failed_report.classification == RealRunRecoveryClassification.TOOL_RESULT_FAILED
    assert (
        RealRunRecoveryAction.RETRY_SAME_CANDIDATE
        in failed_report.allowed_actions
    )

    with pytest.raises(ValueError, match="unresolved real run exists"):
        prepare_next_real_run(project_dir)

    retry = prepare_real_run_retry(
        project_dir,
        failed_run_id="real_002",
        retry_run_id="real_003",
        reason="retry fake failed execution",
        decided_at_utc="2026-06-03T01:00:00Z",
    )
    retry_candidate = load_json(retry.package.candidate_path)
    retry_manifest = load_json(retry.package.manifest_path)

    assert retry.run_id == "real_003"
    assert retry_candidate["candidate_id"] == "real_002"
    assert retry_candidate["parameters"] == failed_package.candidate_payload["parameters"]
    assert retry_manifest["retry_of_run_id"] == "real_002"
    assert retry_manifest["retry_attempt_number"] == 2
    assert retry.decision_path.exists()

    write_fake_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )
    write_fake_metric_result_manifest(
        project_dir,
        run_id="real_003",
        candidate_id="real_002",
    )

    assert (
        check_real_run(project_dir, run_id="real_003").status
        == RealRunCheckStatus.PASS
    )
    assert (
        check_metric_results(project_dir, run_id="real_003").status
        == MetricResultCheckStatus.PASS
    )
    retry_record = record_real_result(
        project_dir,
        run_id="real_003",
        recorded_at_utc="2026-06-03T01:10:00Z",
    )
    source_after_retry = assess_real_run_recovery(project_dir, run_id="real_002")
    rows = ledger_rows(project_dir)

    assert retry_record.status == RealResultRecordStatus.PASS
    assert source_after_retry.classification == RealRunRecoveryClassification.ALREADY_RECORDED
    assert [row["run_id"] for row in rows] == ["real_001", "real_003"]
    assert [row["candidate_id"] for row in rows] == ["real_001", "real_002"]
    assert_no_unresolved_real_runs(project_dir)

    next_package = prepare_next_real_run(
        project_dir,
        run_id="real_004",
        created_at_utc="2026-06-03T01:20:00Z",
    )
    assert next_package.run_id == "real_004"
```

If imports become duplicated, consolidate them at the top of `tests/test_local_real_run_smoke.py` before running ruff.

- [ ] **Step 2: Run the new test and verify it fails or passes for the right reason**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py::test_c11_controlled_failure_retry_records_retry_success -q
```

Expected: the test should pass if C-10 and the Task 1 helper are aligned. If it fails, the failure must identify a real mismatch in C-10/C-9/C-8 integration; fix only the minimal mismatch and update the C-11 spec/plan if the route changes.

- [ ] **Step 3: Run focused recovery and next-run regressions**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py tests/test_real_run_recovery.py tests/test_next_real_run.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run focused lint**

Run:

```bash
python3 -m ruff check tests/real_run_smoke_helpers.py tests/test_local_real_run_smoke.py
```

Expected: all checks pass.

- [ ] **Step 5: Update task status and node files**

In this plan, mark Task 3 steps as complete.

Update the current node in `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` to:

```text
- Current scope: Plan C C-11 local smoke implementation
- Current status: C-11 Task 3 controlled failure/retry smoke complete and reviewed
- Next required action: wait for user confirmation before C-11 Task 4 CLI smoke, docs, and final gate
```

Add matching C-11 Task 3 checkpoint bullets to `docs/EXECUTION_PROGRESS_2026-05-29.md` and `docs/COMPACT_RESUME_CHECKPOINT.md`.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add tests/test_local_real_run_smoke.py docs/superpowers/plans/2026-06-03-local-real-run-smoke.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "test: cover local real run retry smoke"
```

Expected: commit succeeds. Do not stage local OCEAN research or toolchain evidence files.

---

## Task 4: CLI Smoke, Docs, And Final Gate

**Files:**

- Modify: `tests/test_local_real_run_smoke.py`
- Modify: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`

- [ ] **Step 1: Add the failing narrow CLI smoke test**

Append to `tests/test_local_real_run_smoke.py`:

```python
from typer.testing import CliRunner

from hermes_workflow.cli import app


def test_c11_cli_smoke_records_next_real_run(tmp_path):
    project_dir = create_approved_real_project(tmp_path)
    record_checked_run(
        project_dir,
        run_id="real_001",
        recorded_at_utc="2026-06-03T00:40:00Z",
    )
    runner = CliRunner()

    prepare_result = runner.invoke(
        app,
        ["prepare-next-real-run", str(project_dir), "--run-id", "real_002"],
    )
    assert prepare_result.exit_code == 0
    assert "next real run package prepared" in prepare_result.stdout
    assert "run: runs/real/real_002" in prepare_result.stdout

    write_fake_result_manifest(project_dir, run_id="real_002")
    write_fake_metric_result_manifest(project_dir, run_id="real_002")

    real_result = runner.invoke(
        app,
        ["check-real-run", str(project_dir), "--run-id", "real_002"],
    )
    metric_result = runner.invoke(
        app,
        ["check-metric-results", str(project_dir), "--run-id", "real_002"],
    )
    record_result = runner.invoke(
        app,
        ["record-real-result", str(project_dir), "--run-id", "real_002"],
    )

    rows = ledger_rows(project_dir)
    assert real_result.exit_code == 0
    assert "real run handoff check passed" in real_result.stdout
    assert metric_result.exit_code == 0
    assert "metric result check passed" in metric_result.stdout
    assert record_result.exit_code == 0
    assert "real result recorded" in record_result.stdout
    assert [row["run_id"] for row in rows] == ["real_001", "real_002"]
```

If imports become duplicated, consolidate them at the top of `tests/test_local_real_run_smoke.py` before running ruff.

- [ ] **Step 2: Run the CLI smoke test**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py::test_c11_cli_smoke_records_next_real_run -q
```

Expected: 1 test passes.

- [ ] **Step 3: Run focused smoke suite**

Run:

```bash
python3 -m pytest tests/test_local_real_run_smoke.py -q
```

Expected: all C-11 smoke tests pass.

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected: full pytest passes, ruff reports all checks passed, and `git diff --check` has no output.

- [ ] **Step 5: Update docs and route audit**

In this plan, mark Task 4 steps as complete.

Update `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`:

```text
- Current scope: Plan C C-11 local smoke complete
- Current status: C-11 local/fake controlled smoke complete and reviewed
- Next required action: choose the next real-tool/agent practice scope; do not run real tools until the next design spec is approved
```

Update `docs/EXECUTION_PROGRESS_2026-05-29.md`, `docs/COMPACT_RESUME_CHECKPOINT.md`, `docs/PROJECT_WORKFLOW_OVERVIEW.md`, and `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md` to record:

```text
C-11 local/fake controlled smoke is complete. It verifies the C-9 -> fake C-7-style returned artifacts -> C-5/C-6 checks -> C-8 happy path and one C-10 failure/retry path without real Virtuoso/Spectre/OCEAN/SSH/agent/bridge execution. The next scope must be a separate real-tool/agent practice plan.
```

Do not update `AGENTS.md` unless the cadence, role model, or handoff expectations change.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add tests/test_local_real_run_smoke.py docs/superpowers/plans/2026-06-03-local-real-run-smoke.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md
git commit -m "test: add local real run cli smoke"
```

Expected: commit succeeds. Do not stage local OCEAN research or toolchain evidence files.

- [ ] **Step 7: Final review gate**

Run the project review gate after the commit:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected: full verification passes.

Request final spec-compliance and code-quality review. The final review prompt must state:

```text
Review C-11 local/fake controlled smoke. It must remain a test-only local smoke that exercises existing Hermes workflow contracts. It must not run real Virtuoso, Spectre, OCEAN, SSH, Claude CLI, virtuoso-bridge-lite, network access, or subprocess-backed C-7 adapter commands. It must not parse PSF or rewrite Calculator/OCEAN formulas. Verify that the happy path and controlled C-10 retry path actually exercise existing validators and recorders instead of bypassing them.
```

If review finds issues, fix them in a follow-up commit and rerun the focused and final verification commands.

## Plan Self-Review

Spec coverage:

- Happy path smoke is covered by Task 2 and Task 4.
- Controlled failure/retry smoke is covered by Task 3.
- Local/fake boundary is enforced by using synthetic files in pytest temp directories only.
- Existing validators are exercised directly: `check_real_run`, `check_metric_results`, `record_real_result`, `assess_real_run_recovery`, `prepare_real_run_retry`, and `assert_no_unresolved_real_runs`.
- Real tools, network, bridge calls, PSF parsing, and formula rewriting are excluded in every task.
- Progress and top-level route sync are covered in each task, with final route sync in Task 4.

Placeholder scan:

- This plan contains no deferred implementation placeholders.

Type consistency:

- Run ids use `real_001`, `real_002`, `real_003`, and `real_004`.
- Retry success keeps `run_id="real_003"` and `candidate_id="real_002"`.
- Report status comparisons use existing enum values from `hermes_workflow.reports`.
