# Real-Run Result Handoff Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the C-5 Hermes-side validator and CLI command for checking the first real-run result handoff returned by an execution agent.

**Architecture:** Add a focused `src/hermes_workflow/result_handoff.py` module that validates `runs/real/<run_id>/result_manifest.json` against the prepared C-4 real-run package without running Spectre or parsing simulator outputs. Add strict report models in `src/hermes_workflow/reports.py`, expose the validator through `hermes-workflow check-real-run`, and keep C-5.5 dual-agent simulation as the next verification scope rather than product code in this plan.

**Tech Stack:** Python 3.11+, Typer, Pydantic, pytest, ruff, existing Hermes `real_run`, `package`, and validation helpers, Risk-Tiered Batch Gates.

---

## Execution Model

Use `superpowers:subagent-driven-development` when implementing this plan. Start each coding task with a fresh worker context and give it only:

```text
docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md
docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md
the current task section
```

Use the **Risk-Tiered Batch Gates** process for C-5:

1. Tasks 1-4: coding worker plus local deterministic verification after each task.
2. Task 5: docs/progress update with local diff review.
3. Task 6: one combined final spec/code-quality review gate for the complete C-5 diff.
4. If path-safety, hash-attestation, or report-failure tests fail twice during implementation, run a targeted Claude review before moving on.

Do not copy or commit real `input.scs`, Spectre logs, PSF data, or proprietary simulator artifacts from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example
```

C-5 is contract validation only. It does not run Spectre, run Virtuoso, parse real metrics, append `ledger/experiment_ledger.jsonl`, or write optimizer state.

## File Map

- Create `src/hermes_workflow/result_handoff.py`: public `check_real_run(project_dir: Path, *, run_id: str | None = None) -> RealRunCheckReport`, result manifest loading, prepared manifest checks, hash checks, artifact path safety checks, report writing.
- Modify `src/hermes_workflow/reports.py`: add `RealRunCheckStatus`, `RealRunResultStatus`, `RealRunCheckFlags`, and `RealRunCheckReport`.
- Create `tests/test_result_handoff.py`: focused C-5 unit tests using sanitized inline fake logs and artifact files.
- Modify `src/hermes_workflow/cli.py`: add `check-real-run` Typer command with no-traceback expected failure output.
- Modify `tests/test_cli.py`: add CLI success and failure coverage.
- Modify `README.md`: show `check-real-run` after external simulator execution.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: add the result handoff gate to the workflow route and module list.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-5 implementation progress.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: update resume state after C-5 tasks and closeout.
- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: keep the next worker pointed at C-5 until it is complete.
- Modify this plan file as task checkboxes are completed.

## Result Manifest Shape

The execution agent writes this file after consuming the C-4 package:

```text
runs/real/<run_id>/result_manifest.json
```

Use this sanitized test shape throughout C-5:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "status": "succeeded",
  "started_at_utc": "2026-06-01T00:20:00Z",
  "completed_at_utc": "2026-06-01T00:21:00Z",
  "simulator": {
    "engine": "spectre_x",
    "preset": "ax",
    "command_label": "external_spectre_run"
  },
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "prepared_input_sha256": "<sha256 from real_run_manifest.json>",
  "log_file": "runs/real/real_001/spectre.log",
  "artifact_files": [
    "runs/real/real_001/artifacts/psf_summary.txt"
  ],
  "notes": "sanitized fake execution result"
}
```

The `status` field accepts only:

```text
succeeded
failed
```

A `failed` simulator outcome is a valid handoff when the file contract itself is valid.

## Report Shape

C-5 writes:

```text
reports/real_run_check_report.json
```

Successful report shape:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "result_status": "succeeded",
  "real_run_manifest": "runs/real/real_001/real_run_manifest.json",
  "result_manifest": "runs/real/real_001/result_manifest.json",
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "log_file": "runs/real/real_001/spectre.log",
  "artifact_files": [
    "runs/real/real_001/artifacts/psf_summary.txt"
  ],
  "checks": {
    "prepared_manifest_ok": true,
    "candidate_ok": true,
    "result_manifest_ok": true,
    "prepared_input_hash_ok": true,
    "artifact_paths_ok": true
  },
  "issues": []
}
```

Failure report shape:

```json
{
  "schema_version": "1.0",
  "status": "fail",
  "run_id": "real_001",
  "candidate_id": null,
  "result_status": null,
  "real_run_manifest": "runs/real/real_001/real_run_manifest.json",
  "result_manifest": "runs/real/real_001/result_manifest.json",
  "prepared_input_scs": null,
  "log_file": null,
  "artifact_files": [],
  "checks": {
    "prepared_manifest_ok": false,
    "candidate_ok": false,
    "result_manifest_ok": false,
    "prepared_input_hash_ok": false,
    "artifact_paths_ok": false
  },
  "issues": [
    "result manifest is missing"
  ]
}
```

## Task 1: Report Models and Test Scaffolding

**Files:**
- Modify: `src/hermes_workflow/reports.py`
- Create: `tests/test_result_handoff.py`

- [ ] **Step 1: Write failing report model tests**

Create `tests/test_result_handoff.py` with this content:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import (
    RealRunCheckFlags,
    RealRunCheckReport,
    RealRunCheckStatus,
    RealRunResultStatus,
)
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    return project_dir


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")


def _approve_project(project_dir: Path) -> None:
    build_execution_package(project_dir, created_at_utc="2026-06-01T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"


def _prepare_real_run_project(tmp_path: Path):
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:20:00Z",
    )
    return project_dir, package


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_run_check_report_schema_accepts_pass_report() -> None:
    report = RealRunCheckReport(
        schema_version="1.0",
        status=RealRunCheckStatus.PASS,
        run_id="real_001",
        candidate_id="real_001",
        result_status=RealRunResultStatus.SUCCEEDED,
        real_run_manifest="runs/real/real_001/real_run_manifest.json",
        result_manifest="runs/real/real_001/result_manifest.json",
        prepared_input_scs="runs/real/real_001/input.scs",
        log_file="runs/real/real_001/spectre.log",
        artifact_files=["runs/real/real_001/artifacts/psf_summary.txt"],
        checks=RealRunCheckFlags(
            prepared_manifest_ok=True,
            candidate_ok=True,
            result_manifest_ok=True,
            prepared_input_hash_ok=True,
            artifact_paths_ok=True,
        ),
        issues=[],
    )

    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.SUCCEEDED
    assert report.checks.artifact_paths_ok is True


def test_real_run_check_report_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RealRunCheckReport(
            schema_version="1.0",
            status="pass",
            run_id="real_001",
            candidate_id="real_001",
            result_status="succeeded",
            real_run_manifest="runs/real/real_001/real_run_manifest.json",
            result_manifest="runs/real/real_001/result_manifest.json",
            prepared_input_scs="runs/real/real_001/input.scs",
            log_file="runs/real/real_001/spectre.log",
            artifact_files=[],
            checks={
                "prepared_manifest_ok": True,
                "candidate_ok": True,
                "result_manifest_ok": True,
                "prepared_input_hash_ok": True,
                "artifact_paths_ok": True,
            },
            issues=[],
            unexpected=True,
        )
```

- [ ] **Step 2: Run the model tests and verify the expected import failure**

Run:

```bash
pytest tests/test_result_handoff.py::test_real_run_check_report_schema_accepts_pass_report -v
```

Expected:

```text
ImportError: cannot import name 'RealRunCheckFlags'
```

- [ ] **Step 3: Add strict report models**

Append these models to `src/hermes_workflow/reports.py` after `HealthStatus` and before the existing report model classes:

```python
class RealRunCheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class RealRunResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

Add these models after `HealthCheck`:

```python
class RealRunCheckFlags(StrictReport):
    prepared_manifest_ok: bool = False
    candidate_ok: bool = False
    result_manifest_ok: bool = False
    prepared_input_hash_ok: bool = False
    artifact_paths_ok: bool = False


class RealRunCheckReport(StrictReport):
    schema_version: str
    status: RealRunCheckStatus
    run_id: str
    candidate_id: str | None
    result_status: RealRunResultStatus | None
    real_run_manifest: str
    result_manifest: str
    prepared_input_scs: str | None
    log_file: str | None
    artifact_files: list[str] = Field(default_factory=list)
    checks: RealRunCheckFlags
    issues: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run the task tests**

Run:

```bash
pytest tests/test_result_handoff.py::test_real_run_check_report_schema_accepts_pass_report tests/test_result_handoff.py::test_real_run_check_report_schema_rejects_unknown_fields -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Run lint**

Run:

```bash
ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add src/hermes_workflow/reports.py tests/test_result_handoff.py
git commit -m "feat: add real run check report models"
```

## Task 2: Result Handoff Success Path

**Files:**
- Create: `src/hermes_workflow/result_handoff.py`
- Modify: `tests/test_result_handoff.py`

- [ ] **Step 1: Add sanitized result manifest helpers and success tests**

Append this code to `tests/test_result_handoff.py`:

```python
from hermes_workflow.result_handoff import check_real_run


def _write_result_handoff(
    project_dir: Path,
    *,
    status: str = "succeeded",
    overrides: dict | None = None,
) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spectre.log").write_text(
        "sanitized spectre log\nanalysis completed\n",
        encoding="utf-8",
    )
    (artifacts_dir / "psf_summary.txt").write_text(
        "sanitized artifact summary\n",
        encoding="utf-8",
    )
    prepared_manifest = _load_json(run_dir / "real_run_manifest.json")
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": prepared_manifest["candidate_id"],
        "status": status,
        "started_at_utc": "2026-06-01T00:30:00Z",
        "completed_at_utc": "2026-06-01T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared_manifest["rendered_input_scs"],
        "prepared_input_sha256": prepared_manifest["rendered_input_sha256"],
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": ["runs/real/real_001/artifacts/psf_summary.txt"],
        "notes": "sanitized fake execution result",
    }
    if overrides:
        payload.update(overrides)
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def test_check_real_run_accepts_valid_succeeded_handoff(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir)

    report = check_real_run(project_dir)

    report_path = project_dir / "reports" / "real_run_check_report.json"
    persisted = _load_json(report_path)
    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.SUCCEEDED
    assert report.run_id == "real_001"
    assert report.candidate_id == "real_001"
    assert report.real_run_manifest == "runs/real/real_001/real_run_manifest.json"
    assert report.result_manifest == "runs/real/real_001/result_manifest.json"
    assert report.prepared_input_scs == "runs/real/real_001/input.scs"
    assert report.log_file == "runs/real/real_001/spectre.log"
    assert report.artifact_files == ["runs/real/real_001/artifacts/psf_summary.txt"]
    assert report.checks.prepared_manifest_ok is True
    assert report.checks.candidate_ok is True
    assert report.checks.result_manifest_ok is True
    assert report.checks.prepared_input_hash_ok is True
    assert report.checks.artifact_paths_ok is True
    assert report.issues == []
    assert persisted["status"] == "pass"
    assert persisted["result_status"] == "succeeded"


def test_check_real_run_accepts_valid_failed_handoff(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, status="failed")

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.PASS
    assert report.result_status == RealRunResultStatus.FAILED
    assert report.issues == []
```

- [ ] **Step 2: Run success tests and verify the expected module failure**

Run:

```bash
pytest tests/test_result_handoff.py::test_check_real_run_accepts_valid_succeeded_handoff -v
```

Expected:

```text
ModuleNotFoundError: No module named 'hermes_workflow.result_handoff'
```

- [ ] **Step 3: Implement the minimal success-path validator**

Create `src/hermes_workflow/result_handoff.py` with this code:

```python
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError

from hermes_workflow.package import sha256_file
from hermes_workflow.reports import (
    RealRunCheckFlags,
    RealRunCheckReport,
    RealRunCheckStatus,
    RealRunResultStatus,
)
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
REPORT_RELATIVE = "reports/real_run_check_report.json"


class ResultManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    candidate_id: str
    status: RealRunResultStatus
    started_at_utc: str
    completed_at_utc: str
    simulator: dict
    prepared_input_scs: str
    prepared_input_sha256: str
    log_file: str
    artifact_files: list[str]
    notes: str | None = None


def check_real_run(project_dir: Path, *, run_id: str | None = None) -> RealRunCheckReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _project_path(bundle, run_relative)
    prepared_relative = f"{run_relative}/real_run_manifest.json"
    result_relative = f"{run_relative}/result_manifest.json"
    report_path = _project_path(bundle, REPORT_RELATIVE)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    checks = RealRunCheckFlags()
    prepared = _load_json(run_dir / "real_run_manifest.json", "real run manifest", issues)
    candidate = _load_json(run_dir / "candidate.json", "candidate file", issues)
    result_payload = _load_json(run_dir / "result_manifest.json", "result manifest", issues)

    result: ResultManifest | None = None
    if prepared and prepared.get("status") == "prepared":
        checks.prepared_manifest_ok = True
    elif prepared:
        issues.append("real run package is not prepared")
    if candidate:
        checks.candidate_ok = True
    if result_payload:
        try:
            result = ResultManifest.model_validate(result_payload)
            checks.result_manifest_ok = True
        except ValidationError:
            issues.append("result manifest is invalid")

    candidate_id: str | None = None
    result_status: RealRunResultStatus | None = None
    prepared_input_scs: str | None = None
    log_file: str | None = None
    artifact_files: list[str] = []

    if prepared and candidate and result:
        candidate_id = result.candidate_id
        result_status = result.status
        prepared_input_scs = result.prepared_input_scs
        log_file = result.log_file
        artifact_files = result.artifact_files
        _validate_cross_references(
            bundle,
            selected_run_id,
            prepared,
            candidate,
            result,
            issues,
            checks,
        )

    report = _build_report(
        run_id=selected_run_id,
        candidate_id=candidate_id,
        result_status=result_status,
        prepared_relative=prepared_relative,
        result_relative=result_relative,
        prepared_input_scs=prepared_input_scs,
        log_file=log_file,
        artifact_files=artifact_files,
        checks=checks,
        issues=issues,
    )
    _write_report(report_path, report)
    return report


def _validate_cross_references(
    bundle: ContractBundle,
    run_id: str,
    prepared: dict,
    candidate: dict,
    result: ResultManifest,
    issues: list[str],
    checks: RealRunCheckFlags,
) -> None:
    if result.run_id != run_id:
        issues.append("result run_id does not match requested run_id")
    if result.candidate_id != prepared.get("candidate_id"):
        issues.append("result candidate_id does not match prepared candidate")
    if result.candidate_id != candidate.get("candidate_id"):
        issues.append("result candidate_id does not match candidate file")
    if result.prepared_input_scs != prepared.get("rendered_input_scs"):
        issues.append("result prepared_input_scs does not match prepared manifest")
    if result.prepared_input_sha256 != prepared.get("rendered_input_sha256"):
        issues.append("prepared input hash mismatch")

    prepared_path = _safe_run_path(bundle, run_id, result.prepared_input_scs, issues)
    if prepared_path is not None:
        expected_hash = str(prepared.get("rendered_input_sha256"))
        if sha256_file(prepared_path) == expected_hash:
            checks.prepared_input_hash_ok = True
        else:
            issues.append("prepared input hash mismatch")

    artifact_paths = [result.log_file, *result.artifact_files]
    resolved_artifacts = [
        _safe_run_path(bundle, run_id, artifact_path, issues)
        for artifact_path in artifact_paths
    ]
    missing = [
        artifact_path
        for artifact_path, resolved in zip(artifact_paths, resolved_artifacts, strict=True)
        if resolved is not None and not resolved.exists()
    ]
    for artifact_path in missing:
        issues.append(f"result artifact is missing: {artifact_path}")
    if all(path is not None and path.exists() for path in resolved_artifacts):
        checks.artifact_paths_ok = True


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_json(path: Path, label: str, issues: list[str]) -> dict | None:
    if not path.exists():
        issues.append(f"{label} is missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append(f"{label} is invalid")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label} is invalid")
        return None
    return payload


def _safe_run_path(
    bundle: ContractBundle,
    run_id: str,
    relative_path: str,
    issues: list[str],
) -> Path | None:
    path = PurePosixPath(relative_path)
    run_prefix = PurePosixPath(REAL_RUN_ROOT) / run_id
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(run_prefix):
        issues.append(f"result artifact path is unsafe: {relative_path}")
        return None
    return bundle.project_dir / Path(*path.parts)


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"real-run check path must be project-relative and safe: {relative_path}"
        )
    return bundle.project_dir / Path(*path.parts)


def _build_report(
    *,
    run_id: str,
    candidate_id: str | None,
    result_status: RealRunResultStatus | None,
    prepared_relative: str,
    result_relative: str,
    prepared_input_scs: str | None,
    log_file: str | None,
    artifact_files: list[str],
    checks: RealRunCheckFlags,
    issues: list[str],
) -> RealRunCheckReport:
    return RealRunCheckReport(
        schema_version="1.0",
        status=RealRunCheckStatus.FAIL if issues else RealRunCheckStatus.PASS,
        run_id=run_id,
        candidate_id=candidate_id,
        result_status=result_status,
        real_run_manifest=prepared_relative,
        result_manifest=result_relative,
        prepared_input_scs=prepared_input_scs,
        log_file=log_file,
        artifact_files=artifact_files,
        checks=checks,
        issues=issues,
    )


def _write_report(path: Path, report: RealRunCheckReport) -> None:
    path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run success-path tests**

Run:

```bash
pytest tests/test_result_handoff.py::test_check_real_run_accepts_valid_succeeded_handoff tests/test_result_handoff.py::test_check_real_run_accepts_valid_failed_handoff -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Run lint**

Run:

```bash
ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add src/hermes_workflow/result_handoff.py tests/test_result_handoff.py
git commit -m "feat: validate real run result handoff"
```

## Task 3: Failure Reports and Path Safety

**Files:**
- Modify: `src/hermes_workflow/result_handoff.py`
- Modify: `tests/test_result_handoff.py`

- [ ] **Step 1: Add failure and safety tests**

Append this code to `tests/test_result_handoff.py`:

```python
@pytest.mark.parametrize(
    ("overrides", "expected_issue"),
    [
        (
            {"run_id": "real_002"},
            "result run_id does not match requested run_id",
        ),
        (
            {"candidate_id": "other_candidate"},
            "result candidate_id does not match prepared candidate",
        ),
        (
            {"prepared_input_scs": "runs/real/real_001/other.scs"},
            "result prepared_input_scs does not match prepared manifest",
        ),
        (
            {"prepared_input_sha256": "not-the-prepared-hash"},
            "prepared input hash mismatch",
        ),
        (
            {"status": "unknown"},
            "result status is invalid: unknown",
        ),
    ],
)
def test_check_real_run_reports_manifest_mismatches(
    tmp_path: Path,
    overrides: dict,
    expected_issue: str,
) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, overrides=overrides)

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert expected_issue in report.issues
    assert (project_dir / "reports" / "real_run_check_report.json").exists()


def test_check_real_run_reports_missing_result_manifest(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert report.candidate_id is None
    assert report.result_status is None
    assert "result manifest is missing" in report.issues


def test_check_real_run_reports_malformed_result_manifest(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    result_path.write_text("{", encoding="utf-8")

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "result manifest is invalid" in report.issues


def test_check_real_run_reports_prepared_input_hash_drift(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir)
    input_path = project_dir / "runs" / "real" / "real_001" / "input.scs"
    input_path.write_text(
        input_path.read_text(encoding="utf-8") + "\n// changed after prepare-real-run\n",
        encoding="utf-8",
    )

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "prepared input hash mismatch" in report.issues
    assert report.checks.prepared_input_hash_ok is False


@pytest.mark.parametrize(
    ("artifact_value", "expected_issue"),
    [
        ("/tmp/spectre.log", "result artifact path is unsafe: /tmp/spectre.log"),
        (
            "runs/real/real_001/../spectre.log",
            "result artifact path is unsafe: runs/real/real_001/../spectre.log",
        ),
        (
            "runs/real/real_002/spectre.log",
            "result artifact path is unsafe: runs/real/real_002/spectre.log",
        ),
    ],
)
def test_check_real_run_rejects_unsafe_log_paths(
    tmp_path: Path,
    artifact_value: str,
    expected_issue: str,
) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(project_dir, overrides={"log_file": artifact_value})

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert expected_issue in report.issues
    assert report.checks.artifact_paths_ok is False


def test_check_real_run_rejects_missing_declared_artifact(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_result_handoff(
        project_dir,
        overrides={
            "artifact_files": ["runs/real/real_001/artifacts/missing.raw"],
        },
    )

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "result artifact is missing: runs/real/real_001/artifacts/missing.raw" in report.issues
    assert report.checks.artifact_paths_ok is False
```

- [ ] **Step 2: Run failure tests and observe at least one failure**

Run:

```bash
pytest tests/test_result_handoff.py -v
```

Expected before hardening:

```text
FAILED tests/test_result_handoff.py::test_check_real_run_reports_manifest_mismatches
```

The initial implementation may report Pydantic validation generically for invalid result status instead of the exact required issue.

- [ ] **Step 3: Harden result manifest validation and issue collection**

Modify `src/hermes_workflow/result_handoff.py` so `_load_json` and result validation produce exact issue messages. Replace the `except ValidationError` block in `check_real_run()` with:

```python
        except ValidationError:
            invalid_status = result_payload.get("status")
            if invalid_status not in {status.value for status in RealRunResultStatus}:
                issues.append(f"result status is invalid: {invalid_status}")
            else:
                issues.append("result manifest is invalid")
```

Update `_validate_cross_references()` to avoid duplicate hash mismatch messages:

```python
    hash_matches_manifest = result.prepared_input_sha256 == prepared.get(
        "rendered_input_sha256"
    )
    if not hash_matches_manifest:
        issues.append("prepared input hash mismatch")

    prepared_path = _safe_run_path(bundle, run_id, result.prepared_input_scs, issues)
    if prepared_path is not None and hash_matches_manifest:
        expected_hash = str(prepared.get("rendered_input_sha256"))
        if sha256_file(prepared_path) == expected_hash:
            checks.prepared_input_hash_ok = True
        else:
            issues.append("prepared input hash mismatch")
```

Keep the `prepared_input_scs` safe-path check even when the path mismatches the prepared manifest so unsafe input paths are still surfaced.

- [ ] **Step 4: Run all result handoff tests**

Run:

```bash
pytest tests/test_result_handoff.py -v
```

Expected:

```text
14 passed
```

The exact count may be higher if implementation workers add small focused tests; all tests in this file must pass.

- [ ] **Step 5: Run focused related tests and lint**

Run:

```bash
pytest tests/test_real_run.py tests/test_result_handoff.py -v
ruff check .
```

Expected:

```text
tests/test_real_run.py ... passed
tests/test_result_handoff.py ... passed
All checks passed!
```

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add src/hermes_workflow/result_handoff.py tests/test_result_handoff.py
git commit -m "fix: harden real run handoff validation"
```

## Task 4: CLI Command

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add CLI tests**

Append this code to `tests/test_cli.py`:

```python
def _prepare_cli_real_run(project_dir: Path) -> None:
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "exported" / "input.scs").write_text(
        """simulator lang=spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
tran tran stop=10n
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-netlist", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["dry-run", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["preflight-health", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0


def _write_cli_result_manifest(project_dir: Path) -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spectre.log").write_text("sanitized spectre log\n", encoding="utf-8")
    (artifacts_dir / "psf_summary.txt").write_text(
        "sanitized artifact summary\n",
        encoding="utf-8",
    )
    prepared_manifest = json.loads(
        (run_dir / "real_run_manifest.json").read_text(encoding="utf-8")
    )
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": prepared_manifest["candidate_id"],
        "status": "succeeded",
        "started_at_utc": "2026-06-01T00:30:00Z",
        "completed_at_utc": "2026-06-01T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared_manifest["rendered_input_scs"],
        "prepared_input_sha256": prepared_manifest["rendered_input_sha256"],
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": ["runs/real/real_001/artifacts/psf_summary.txt"],
    }
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_cli_check_real_run_reports_success(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    _prepare_cli_real_run(project_dir)
    _write_cli_result_manifest(project_dir)

    result = runner.invoke(app, ["check-real-run", str(project_dir)])

    assert result.exit_code == 0
    assert "real run handoff check passed" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "result: runs/real/real_001/result_manifest.json" in result.stdout
    assert "report: reports/real_run_check_report.json" in result.stdout
    assert (project_dir / "reports" / "real_run_check_report.json").exists()


def test_cli_check_real_run_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    _prepare_cli_real_run(project_dir)

    result = runner.invoke(app, ["check-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "real run handoff check failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/real_run_check_report.json" in result.stdout
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run CLI tests and verify command is missing**

Run:

```bash
pytest tests/test_cli.py::test_cli_check_real_run_reports_success -v
```

Expected:

```text
Error: No such command 'check-real-run'
```

- [ ] **Step 3: Add CLI command**

Modify `src/hermes_workflow/cli.py`.

Add this import near the other workflow imports:

```python
from hermes_workflow.result_handoff import check_real_run
```

Add this command after `prepare_real_run_command()`:

```python
@app.command("check-real-run")
def check_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with a returned real-run result manifest."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Real-run package id such as real_001.",
        ),
    ] = None,
) -> None:
    try:
        report = check_real_run(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("real run handoff check passed")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo(f"result: {report.result_manifest}")
        typer.echo("report: reports/real_run_check_report.json")
        return

    typer.echo("real run handoff check failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/real_run_check_report.json")
    raise typer.Exit(code=1)
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
pytest tests/test_cli.py::test_cli_check_real_run_reports_success tests/test_cli.py::test_cli_check_real_run_reports_failure_without_traceback -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Run focused C-5 suite and lint**

Run:

```bash
pytest tests/test_result_handoff.py tests/test_cli.py -v
ruff check .
```

Expected:

```text
tests/test_result_handoff.py ... passed
tests/test_cli.py ... passed
All checks passed!
```

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add src/hermes_workflow/cli.py tests/test_cli.py
git commit -m "feat: add real run handoff cli"
```

## Task 5: Documentation and Resume State

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`

- [ ] **Step 1: Update README command sequence**

Add `check-real-run` after `prepare-real-run` and after the external execution note. The sequence should read:

```bash
hermes-workflow init ./bridge_test_inv
hermes-workflow validate ./bridge_test_inv
hermes-workflow package ./bridge_test_inv
hermes-workflow prepare-netlist ./bridge_test_inv
hermes-workflow dry-run ./bridge_test_inv
hermes-workflow preflight-health ./bridge_test_inv
hermes-workflow approve ./bridge_test_inv
hermes-workflow prepare-real-run ./bridge_test_inv
# execution agent runs the prepared deck outside Hermes and writes result_manifest.json
hermes-workflow check-real-run ./bridge_test_inv
```

Add this scope note near the real-run usage section:

```text
`check-real-run` validates the returned file contract only. It does not launch
Spectre, parse simulator databases, compute real metrics, append ledger rows, or
advance optimizer state.
```

- [ ] **Step 2: Update workflow overview**

In `docs/PROJECT_WORKFLOW_OVERVIEW.md`, add this route:

```text
prepare-real-run
-> execution agent runs Spectre externally
-> execution agent writes runs/real/<run_id>/result_manifest.json
-> check-real-run
-> future metric extraction contract
```

Add this module summary:

```text
`src/hermes_workflow/result_handoff.py` validates the post-execution result
handoff from an execution agent. It checks the prepared manifest, result
manifest, candidate identity, rendered deck hash, and declared artifact paths,
then writes `reports/real_run_check_report.json`.
```

Add this dual-agent simulation note under the future tool-integration route:

```text
C-5.5 should validate the workflow with two simulated Codex roles before using
real Hermes or Claude CLI integrations: one execution-agent role writes the
returned result package, and one supervisor/Hermes-observer role checks whether
the file contract prevents unsafe or ambiguous behavior.
```

- [ ] **Step 3: Update progress and checkpoint docs**

In `docs/EXECUTION_PROGRESS_2026-05-29.md`, add a C-5 section with:

```text
Plan C C-5 Real-Run Result Handoff Contract

Status: implementation in progress.

Scope: validate `runs/real/<run_id>/result_manifest.json` and declared
artifacts after an execution agent consumes the C-4 first real-run package.
C-5 does not run Spectre, parse metrics, write ledger rows, or update optimizer
state.

Implementation plan:
`docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`
```

In `docs/COMPACT_RESUME_CHECKPOINT.md`, add:

```text
- C-5 real-run result handoff design spec exists: `docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md`.
- C-5 implementation plan exists: `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`.
- C-5 next action: start Task 1, report models and test scaffolding.
```

In `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, update the current node:

```text
- Current scope: Plan C-5, real-run result handoff contract
- Current status: C-5 implementation plan ready; implementation not started
- Next required action: execute C-5 Task 1 with Subagent-Driven development
```

- [ ] **Step 4: Mark Task 5 progress in this plan**

Change the C-5 plan task status bullets completed by this docs task from unchecked to checked. Keep future task checkboxes unchanged.

- [ ] **Step 5: Verify docs diff**

Run:

```bash
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add README.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md
git commit -m "docs: record real run result handoff progress"
```

## Task 6: Final Verification and C-5.5 Simulation Prep

**Files:**
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`

- [ ] **Step 1: Run focused verification**

Run:

```bash
pytest tests/test_result_handoff.py tests/test_cli.py -v
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 2: Run full verification**

Run:

```bash
pytest -q
ruff check .
```

Expected:

```text
all tests passed
All checks passed!
```

- [ ] **Step 3: Run one combined final review gate**

Run:

```bash
claude -p "Review the current git diff for Plan C C-5 Real-Run Result Handoff Contract against docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md and docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md. Focus on spec compliance, hash/path safety, report failure surfaces, CLI no-traceback behavior, and code quality. Return Critical, Important, and Minor findings."
```

Expected:

```text
No Critical findings.
No Important findings.
```

Fix all Critical and Important findings before closing C-5. Minor findings may be recorded if they are intentionally deferred outside C-5 scope.

- [ ] **Step 4: Record C-5.5 simulation scenarios**

Append this section to `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`:

```text
## Planned C-5.5 Dual-Agent Result Handoff Simulation Gate

C-5.5 should run before any real Hermes or Claude CLI tool integration. Use two
simulated Codex roles:

- Execution-agent role: receives only the C-4 package contract and writes
  `runs/real/real_001/result_manifest.json` plus sanitized fake artifacts.
- Hermes-observer role: runs `check-real-run`, inspects
  `reports/real_run_check_report.json`, and records whether unsafe or ambiguous
  behavior was blocked by deterministic file checks.

Required simulation cases:

- Happy path: valid `succeeded` handoff.
- Valid simulator failure: `status: failed` with existing sanitized log.
- Unsafe path attempt: absolute or traversal artifact path.
- Mutated prepared deck: changed `input.scs` after C-4.
- Identity mismatch: wrong `candidate_id` or `run_id`.

C-5.5 should not call real Spectre, real Virtuoso, real Hermes, or real Claude
CLI. It is a workflow behavior validation gate before physical tool adapters.
```

- [ ] **Step 5: Update checkpoint state**

In `docs/COMPACT_RESUME_CHECKPOINT.md`, mark:

```text
- C-5 real-run result handoff contract is complete and reviewed.
- C-5 final verification: `pytest -q` passed; `ruff check .` passed; combined final review gate passed with no Critical or Important findings.
- Next recommended scope: C-5.5 dual-agent result handoff simulation gate before real tool adapters.
```

- [ ] **Step 6: Commit closeout docs**

Run:

```bash
git add docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/COMPACT_RESUME_CHECKPOINT.md docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md
git commit -m "docs: close real run result handoff contract"
```

## Self-Review Checklist

- Spec coverage:
  - `result_manifest.json` contract is implemented by Tasks 2-3.
  - `check-real-run` CLI contract is implemented by Task 4.
  - `reports/real_run_check_report.json` is implemented by Tasks 1-3.
  - Hash attestation and prepared deck drift checks are implemented by Tasks 2-3.
  - Artifact path safety checks are implemented by Task 3.
  - Documentation and resume state are implemented by Task 5.
  - C-5.5 dual-agent simulation prep is recorded by Task 6.
- Scope control:
  - No task runs Spectre, Virtuoso, shell subprocess simulations, metric parsing, ledger updates, or optimizer state updates.
  - Tests use sanitized inline fake logs and artifacts only.
- Type consistency:
  - `check_real_run(project_dir: Path, *, run_id: str | None = None) -> RealRunCheckReport`.
  - Report fields match `RealRunCheckReport`.
  - CLI command name is `check-real-run`.
  - Report path is `reports/real_run_check_report.json`.
