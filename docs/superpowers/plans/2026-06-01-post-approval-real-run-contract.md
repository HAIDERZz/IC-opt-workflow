# Post-Approval Real-Run Execution Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Hermes command that prepares the first post-approval real-run package without invoking Spectre, Virtuoso, subprocesses, or the optimizer loop.

**Architecture:** Add a focused `src/hermes_workflow/real_run.py` module that verifies `supervisor_instruction.json`, verifies immutable config hashes against `execution_manifest.json`, renders a lower-bound candidate into `runs/real/<run_id>/input.scs`, and writes `candidate.json` plus `real_run_manifest.json`. Expose it through `hermes-workflow prepare-real-run`, keeping CLI code limited to formatting success and expected errors.

**Tech Stack:** Python 3.11+, Typer, pytest, ruff, existing Hermes validation/package/dry-run helpers, Claude CLI review gates.

---

## Execution Model

Use `superpowers:subagent-driven-development` for implementation. For each task:

1. Dispatch a fresh Claude CLI coding worker with only the current task section and this spec path:

```text
docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md
```

2. Review the worker diff before continuing.
3. Run the task-specific pytest command.
4. Run `ruff check .`.
5. Run the review gate:

```bash
claude -p "Review the current git diff for C-4 Task N against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

6. Fix all Critical and Important findings before moving to the next task.
7. Commit after the task is green.

Do not commit or copy real `input.scs` examples from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example`.

## Execution Status

Status: complete and reviewed as of 2026-06-01.

Completed commits:

- `e195bd9 feat: guard post approval real runs`
- `d6804a8 feat: prepare first real run package`
- `fc34c6d fix: harden real run package creation`
- `1ce650e feat: add prepare real run cli`
- `f40966e docs: record real run package progress`

Final verification:

- `pytest -q` passed, 190 tests.
- `ruff check .` passed.
- After Task 3: `pytest tests/test_real_run.py -v` passed, 14 tests.
- After Task 3: `ruff check .` passed.
- After Task 3: `git diff --check` passed.
- After Task 4: `pytest tests/test_cli.py::test_cli_prepare_real_run_writes_package_after_approval tests/test_cli.py::test_cli_prepare_real_run_reports_missing_approval_without_traceback tests/test_cli.py::test_cli_prepare_real_run_reports_config_drift_without_traceback -v` passed, 3 tests.
- After Task 4: `pytest tests/test_real_run.py tests/test_cli.py -v` passed, 33 tests.
- After Task 4: `ruff check .` passed.

Final reviews:

- Combined final spec/code-quality review: passed with no Critical or Important findings.

Batch-gate note:

- Tasks 4-6 used Risk-Tiered Batch Gates to reduce model calls. Task 4 used a Claude CLI coding worker plus local deterministic verification. Task 5 docs were local. Task 6 ran one combined final review gate before closeout.

## File Map

- Create `src/hermes_workflow/real_run.py`: post-approval guard, config drift guard, lower-bound candidate rendering, package cleanup, manifest writing.
- Create `tests/test_real_run.py`: focused unit tests for guard failures, successful package creation, manifest content, run-id validation, overwrite refusal, and cleanup.
- Modify `src/hermes_workflow/cli.py`: add `prepare-real-run` command and translate expected domain errors to exit code 1 without traceback.
- Modify `tests/test_cli.py`: add CLI success and rejection coverage.
- Modify `README.md`: extend command sequence with `prepare-real-run`.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: add C-4 to the flow, module list, and CLI usage.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-4 task status and commits.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: update resume state after C-4.
- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: point next workers to the active C-4 plan and current task.
- Modify this plan file as tasks are completed.

## Shared Test Helpers

The first task creates `tests/test_real_run.py` with helper functions used by later tasks. These helpers should stay local to the test file:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
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
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
```

If a task needs another helper, add it near these functions and keep it deterministic.

## Task 1: Post-Approval Guard and Config Drift Guard

**Files:**
- Create: `src/hermes_workflow/real_run.py`
- Create: `tests/test_real_run.py`

- [x] **Step 1: Write failing guard tests**

Create `tests/test_real_run.py` with the shared helpers above and these tests:

```python
def test_prepare_real_run_rejects_missing_supervisor_instruction(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    _write_template(project_dir)

    with pytest.raises(FileNotFoundError, match="supervisor instruction is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_reject_instruction(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "reject_first_real_run",
                "reason": "not ready",
                "allowed_actions": [],
                "forbidden_actions": ["run_standalone_spectre_optimizer"],
                "approved_config_hashes": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(ValueError, match="first real run is not approved"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_missing_execution_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _write_template(project_dir)
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps({"decision": "approve_first_real_run"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="execution manifest is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_config_drift_after_approval(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    variables_path = project_dir / "config" / "variables.yaml"
    variables_path.write_text(
        variables_path.read_text(encoding="utf-8").replace('upper: "12"', 'upper: "14"', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable config drift detected: config/variables.yaml"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_missing_approved_hashes(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved without hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor instruction is missing approved_config_hashes",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_hash_mismatch(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    manifest = build_execution_package(
        project_dir,
        created_at_utc="2026-05-31T00:00:00Z",
    )
    approved_hashes = dict(manifest.payload["immutable_config_files"])
    approved_hashes["config/variables.yaml"] = "not-the-approved-hash"
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved with wrong hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
                "approved_config_hashes": approved_hashes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor approved config hashes do not match execution manifest",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_real_run.py::test_prepare_real_run_rejects_missing_supervisor_instruction tests/test_real_run.py::test_prepare_real_run_rejects_reject_instruction tests/test_real_run.py::test_prepare_real_run_rejects_missing_execution_manifest tests/test_real_run.py::test_prepare_real_run_rejects_config_drift_after_approval tests/test_real_run.py::test_prepare_real_run_rejects_instruction_missing_approved_hashes tests/test_real_run.py::test_prepare_real_run_rejects_instruction_hash_mismatch -v
```

Expected: import fails because `hermes_workflow.real_run` does not exist.

- [x] **Step 3: Create the guard implementation**

Create `src/hermes_workflow/real_run.py` with this initial implementation:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hermes_workflow.package import sha256_file
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
SUPERVISOR_INSTRUCTION = "supervisor_instruction.json"
EXECUTION_MANIFEST = "execution_package/execution_manifest.json"


@dataclass(frozen=True)
class RealRunPackage:
    run_id: str
    run_dir: Path
    rendered_input_scs: Path
    candidate_path: Path
    manifest_path: Path
    candidate_payload: dict
    manifest_payload: dict


def prepare_real_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)

    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    manifest_path = run_dir / "real_run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")

    raise NotImplementedError("real run package rendering is implemented in Task 2")


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_execution_manifest(project_dir: Path) -> dict:
    path = project_dir / EXECUTION_MANIFEST
    if not path.exists():
        raise FileNotFoundError("execution manifest is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"execution manifest is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("execution manifest is invalid: expected JSON object")
    return payload


def _load_supervisor_instruction(project_dir: Path) -> dict:
    path = project_dir / SUPERVISOR_INSTRUCTION
    if not path.exists():
        raise FileNotFoundError("supervisor instruction is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"supervisor instruction is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("supervisor instruction is invalid: expected JSON object")
    return payload


def _assert_approved(instruction: dict) -> None:
    if instruction.get("decision") != "approve_first_real_run":
        raise ValueError("first real run is not approved")


def _approved_hashes(manifest: dict, instruction: dict) -> dict[str, str]:
    manifest_hashes = manifest.get("immutable_config_files")
    if not isinstance(manifest_hashes, dict) or not manifest_hashes:
        raise ValueError("execution manifest is missing immutable_config_files")
    instruction_hashes = instruction.get("approved_config_hashes")
    if not isinstance(instruction_hashes, dict) or not instruction_hashes:
        raise ValueError("supervisor instruction is missing approved_config_hashes")
    if instruction_hashes != manifest_hashes:
        raise ValueError("supervisor approved config hashes do not match execution manifest")
    return {str(path): str(digest) for path, digest in manifest_hashes.items()}


def _assert_config_hashes(project_dir: Path, approved_hashes: dict[str, str]) -> None:
    for relative_path, approved_hash in sorted(approved_hashes.items()):
        current_path = project_dir / Path(*PurePosixPath(relative_path).parts)
        if not current_path.exists():
            raise ValueError(f"immutable config drift detected: {relative_path}")
        if sha256_file(current_path) != approved_hash:
            raise ValueError(f"immutable config drift detected: {relative_path}")


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"real-run path must be project-relative and safe: {relative_path}")
    return bundle.project_dir / Path(*path.parts)
```

- [x] **Step 4: Run tests and verify current result**

Run:

```bash
pytest tests/test_real_run.py::test_prepare_real_run_rejects_missing_supervisor_instruction tests/test_real_run.py::test_prepare_real_run_rejects_reject_instruction tests/test_real_run.py::test_prepare_real_run_rejects_missing_execution_manifest tests/test_real_run.py::test_prepare_real_run_rejects_config_drift_after_approval tests/test_real_run.py::test_prepare_real_run_rejects_instruction_missing_approved_hashes tests/test_real_run.py::test_prepare_real_run_rejects_instruction_hash_mismatch -v
```

Expected: all six tests pass. The implementation still raises `NotImplementedError` only after guard checks pass, which none of these tests reach.

- [x] **Step 5: Run ruff**

Run:

```bash
ruff check .
```

Expected: all checks pass.

- [x] **Step 6: Run review gate**

Run:

```bash
claude -p "Review the current git diff for C-4 Task 1 against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

Expected: no Critical or Important findings. Fix any Critical or Important findings before committing.

- [x] **Step 7: Commit Task 1**

Run:

```bash
git add src/hermes_workflow/real_run.py tests/test_real_run.py
git commit -m "feat: guard post approval real runs"
```

## Task 2: Successful Real-Run Package Creation

**Files:**
- Modify: `src/hermes_workflow/real_run.py`
- Modify: `tests/test_real_run.py`

- [x] **Step 1: Add success-path tests**

Append these tests to `tests/test_real_run.py`:

```python
def test_prepare_real_run_writes_first_real_run_package(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:20:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    rendered = (run_dir / "input.scs").read_text(encoding="utf-8")
    candidate = _load_json(run_dir / "candidate.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")

    assert package.run_id == "real_001"
    assert package.run_dir == run_dir
    assert package.rendered_input_scs == run_dir / "input.scs"
    assert package.candidate_path == run_dir / "candidate.json"
    assert package.manifest_path == run_dir / "real_run_manifest.json"
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "FN=2" in rendered
    assert "WN=0.3 um" in rendered
    assert "FP=2" in rendered
    assert "WP=0.3 um" in rendered
    assert candidate == {
        "schema_version": "1.0",
        "candidate_id": "real_001",
        "source": "lower_bound_first_real_run",
        "parameters": {
            "FN": "2",
            "WN": "0.3 um",
            "FP": "2",
            "WP": "0.3 um",
        },
    }
    assert manifest["schema_version"] == "1.0"
    assert manifest["run_id"] == "real_001"
    assert manifest["project_name"] == "bridge_test_inv"
    assert manifest["created_at_utc"] == "2026-05-31T00:20:00Z"
    assert manifest["status"] == "prepared"
    assert manifest["supervisor_decision"] == "approve_first_real_run"
    assert manifest["template_scs"] == "netlists/templates/template.scs"
    assert manifest["rendered_input_scs"] == "runs/real/real_001/input.scs"
    assert manifest["candidate_file"] == "runs/real/real_001/candidate.json"
    assert manifest["candidate_id"] == "real_001"
    assert manifest["candidate_source"] == "lower_bound_first_real_run"
    assert manifest["template_sha256"]
    assert manifest["rendered_input_sha256"]
    assert manifest["approved_config_hashes"]["config/project_config.yaml"]
    assert manifest["spectre"] == {
        "engine": "spectre_x",
        "preset": "ax",
        "output_format": "psfascii",
        "parallel_jobs": 10,
        "timeout_s": 3600,
    }
    assert "modify_maestro_setup" in manifest["forbidden_actions"]
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_prepare_real_run_accepts_valid_custom_run_id(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        run_id="real_007",
        created_at_utc="2026-05-31T00:20:00Z",
    )

    manifest = _load_json(project_dir / "runs" / "real" / "real_007" / "real_run_manifest.json")
    assert package.run_id == "real_007"
    assert manifest["run_id"] == "real_007"
    assert manifest["candidate_id"] == "real_007"
    assert manifest["rendered_input_scs"] == "runs/real/real_007/input.scs"
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_real_run.py::test_prepare_real_run_writes_first_real_run_package tests/test_real_run.py::test_prepare_real_run_accepts_valid_custom_run_id -v
```

Expected: both tests fail with `NotImplementedError`.

- [x] **Step 3: Implement package rendering**

In `src/hermes_workflow/real_run.py`, add these imports near the top:

```python
import shutil
from datetime import UTC, datetime

from hermes_workflow.dry_run import PLACEHOLDER_RE, UNRESOLVED_PLACEHOLDER_RE
```

Update the `prepare_real_run()` signature to accept deterministic timestamps for tests:

```python
def prepare_real_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
```

Then replace the `raise NotImplementedError("real run package rendering is implemented in Task 2")` line in `prepare_real_run()` with:

```python
    template_relative = bundle.project_config.netlist.template_scs
    template_path = _project_path(bundle, template_relative)
    if not template_path.exists():
        raise FileNotFoundError(f"template.scs is missing: {template_relative}")

    candidate = _lower_bound_candidate(bundle, selected_run_id)
    rendered_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/input.scs"
    candidate_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate.json"
    manifest_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/real_run_manifest.json"
    rendered_path = _project_path(bundle, rendered_relative)
    candidate_path = _project_path(bundle, candidate_relative)

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        rendered_text = _render_template(template_path.read_text(encoding="utf-8"), candidate["parameters"])
        rendered_path.write_text(rendered_text, encoding="utf-8")
        candidate_path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_payload = _build_manifest(
            bundle,
            selected_run_id,
            created_at_utc or _utc_now(),
            instruction,
            approved_hashes,
            template_relative,
            rendered_relative,
            candidate_relative,
            template_path,
            rendered_path,
        )
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        raise

    return RealRunPackage(
        run_id=selected_run_id,
        run_dir=run_dir,
        rendered_input_scs=rendered_path,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        candidate_payload=candidate,
        manifest_payload=manifest_payload,
    )
```

Add these helper functions below `_assert_config_hashes()`:

```python
def _lower_bound_candidate(bundle: ContractBundle, run_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "candidate_id": run_id,
        "source": "lower_bound_first_real_run",
        "parameters": {
            variable.name: variable.lower for variable in bundle.variables.variables
        },
    }


def _render_template(template_text: str, candidate: dict[str, str]) -> str:
    approved_names = set(candidate)
    seen_names = {match.group("name") for match in PLACEHOLDER_RE.finditer(template_text)}
    unexpected = sorted(seen_names - approved_names)
    missing = sorted(approved_names - seen_names)
    if missing:
        raise ValueError(
            "approved variable placeholders are missing: " + ", ".join(missing)
        )
    if unexpected:
        raise ValueError("unexpected template variables: " + ", ".join(unexpected))

    rendered = template_text
    for name, value in candidate.items():
        rendered = rendered.replace(f"{{{{{name}}}}}", value)

    unresolved = sorted(
        {match.group(0) for match in UNRESOLVED_PLACEHOLDER_RE.finditer(rendered)}
    )
    if unresolved:
        raise ValueError("rendered real-run deck still contains unresolved placeholders")
    return rendered


def _build_manifest(
    bundle: ContractBundle,
    run_id: str,
    created_at_utc: str,
    instruction: dict,
    approved_hashes: dict[str, str],
    template_relative: str,
    rendered_relative: str,
    candidate_relative: str,
    template_path: Path,
    rendered_path: Path,
) -> dict:
    spectre = bundle.spectre.spectre
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "project_name": bundle.project_config.project.name,
        "created_at_utc": created_at_utc,
        "status": "prepared",
        "supervisor_decision": instruction["decision"],
        "template_scs": template_relative,
        "rendered_input_scs": rendered_relative,
        "candidate_file": candidate_relative,
        "candidate_id": run_id,
        "candidate_source": "lower_bound_first_real_run",
        "approved_config_hashes": approved_hashes,
        "template_sha256": sha256_file(template_path),
        "rendered_input_sha256": sha256_file(rendered_path),
        "spectre": {
            "engine": spectre.engine,
            "preset": spectre.preset.value,
            "output_format": spectre.output_format,
            "parallel_jobs": spectre.parallel_jobs,
            "timeout_s": spectre.timeout_s,
        },
        "forbidden_actions": [
            "modify_maestro_setup",
            "modify_immutable_config_files",
            "change_variable_bounds",
            "change_objective_or_constraints",
        ],
    }
```

Add `_utc_now()` near the bottom of the module:

```python
def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
```

- [x] **Step 4: Run success tests**

Run:

```bash
pytest tests/test_real_run.py::test_prepare_real_run_writes_first_real_run_package tests/test_real_run.py::test_prepare_real_run_accepts_valid_custom_run_id -v
```

Expected: both tests pass.

- [x] **Step 5: Run all current real-run tests**

Run:

```bash
pytest tests/test_real_run.py -v
```

Expected: all current real-run tests pass.

- [x] **Step 6: Run ruff**

Run:

```bash
ruff check .
```

Expected: all checks pass.

- [x] **Step 7: Run review gate**

Run:

```bash
claude -p "Review the current git diff for C-4 Task 2 against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

Expected: no Critical or Important findings. Fix any Critical or Important findings before committing.

- [x] **Step 8: Commit Task 2**

Run:

```bash
git add src/hermes_workflow/real_run.py tests/test_real_run.py
git commit -m "feat: prepare first real run package"
```

## Task 3: Failure Cleanup, Overwrite Refusal, and Run-ID Hardening

**Files:**
- Modify: `src/hermes_workflow/real_run.py`
- Modify: `tests/test_real_run.py`

- [x] **Step 1: Add hardening tests**

Append these tests to `tests/test_real_run.py`:

```python
def test_prepare_real_run_rejects_invalid_run_id(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    with pytest.raises(ValueError, match=r"run_id must match real_\[0-9\]\{3\}: run_1"):
        prepare_real_run(project_dir, run_id="run_1")

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_missing_template(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)

    with pytest.raises(FileNotFoundError, match="template.scs is missing: netlists/templates/template.scs"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_unexpected_template_variable(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(
        project_dir,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}} EXTRA={{EXTRA}}
tran tran stop=10n
""",
    )

    with pytest.raises(ValueError, match="unexpected template variables: EXTRA"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_refuses_existing_package(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    with pytest.raises(FileExistsError, match="real run package already exists"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:21:00Z")


def test_prepare_real_run_cleans_partial_run_directory_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    original_write_text = Path.write_text

    def failing_write_text(self: Path, data: str, *args, **kwargs):
        if self.name == "candidate.json":
            raise OSError("simulated candidate write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError, match="simulated candidate write failure"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()

    monkeypatch.undo()
    package = prepare_real_run(project_dir, created_at_utc="2026-05-31T00:21:00Z")
    assert package.manifest_path.exists()
```

- [x] **Step 2: Run hardening tests and verify result**

Run:

```bash
pytest tests/test_real_run.py::test_prepare_real_run_rejects_invalid_run_id tests/test_real_run.py::test_prepare_real_run_rejects_missing_template tests/test_real_run.py::test_prepare_real_run_rejects_unexpected_template_variable tests/test_real_run.py::test_prepare_real_run_refuses_existing_package tests/test_real_run.py::test_prepare_real_run_cleans_partial_run_directory_on_write_failure -v
```

Expected: all five tests pass.

- [x] **Step 3: Confirm hardening implementation**

Confirm `src/hermes_workflow/real_run.py` contains this run-id validator:

```python
def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id
```

Confirm the manifest overwrite check appears before `run_dir.mkdir(parents=True, exist_ok=True)`:

```python
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")
```

Confirm the cleanup wrapper around all writes is:

```python
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        rendered_text = _render_template(
            template_path.read_text(encoding="utf-8"),
            candidate["parameters"],
        )
        rendered_path.write_text(rendered_text, encoding="utf-8")
        candidate_path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_payload = _build_manifest(
            bundle,
            selected_run_id,
            created_at_utc or _utc_now(),
            instruction,
            approved_hashes,
            template_relative,
            rendered_relative,
            candidate_relative,
            template_path,
            rendered_path,
        )
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
```

- [x] **Step 4: Run all real-run tests**

Run:

```bash
pytest tests/test_real_run.py -v
```

Expected: all real-run tests pass.

- [x] **Step 5: Run ruff**

Run:

```bash
ruff check .
```

Expected: all checks pass.

- [x] **Step 6: Run review gate**

Run:

```bash
claude -p "Review the current git diff for C-4 Task 3 against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

Expected: no Critical or Important findings. Fix any Critical or Important findings before committing.

- [x] **Step 7: Commit Task 3**

Run:

```bash
git add src/hermes_workflow/real_run.py tests/test_real_run.py
git commit -m "fix: harden real run package creation"
```

## Task 4: CLI Command

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add CLI tests**

Append these tests to `tests/test_cli.py`:

```python
def test_cli_prepare_real_run_writes_package_after_approval(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
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

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    manifest_path = project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json"
    assert result.exit_code == 0
    assert "real run package prepared" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "manifest: runs/real/real_001/real_run_manifest.json" in result.stdout
    assert manifest_path.exists()
    assert (project_dir / "runs" / "real" / "real_001" / "input.scs").exists()


def test_cli_prepare_real_run_reports_missing_approval_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "supervisor instruction is missing" in result.stdout
    assert "Traceback" not in result.output


def test_cli_prepare_real_run_reports_config_drift_without_traceback(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "bridge_test_inv"
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
    variables_path = project_dir / "config" / "variables.yaml"
    variables_path.write_text(
        variables_path.read_text(encoding="utf-8").replace('upper: "12"', 'upper: "14"', 1),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "immutable config drift detected: config/variables.yaml" in result.stdout
    assert "Traceback" not in result.output
```

- [x] **Step 2: Run CLI tests and verify failure**

Run:

```bash
pytest tests/test_cli.py::test_cli_prepare_real_run_writes_package_after_approval tests/test_cli.py::test_cli_prepare_real_run_reports_missing_approval_without_traceback tests/test_cli.py::test_cli_prepare_real_run_reports_config_drift_without_traceback -v
```

Expected: tests fail because the CLI command does not exist.

- [x] **Step 3: Add CLI command**

In `src/hermes_workflow/cli.py`, add this import with the other command imports:

```python
from hermes_workflow.real_run import prepare_real_run
```

Add this command after `approve_command()` and before `mock_run_command()`:

```python
@app.command("prepare-real-run")
def prepare_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with approve_first_real_run instruction."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Real-run package id such as real_001."),
    ] = None,
) -> None:
    try:
        package = prepare_real_run(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")
```

- [x] **Step 4: Run CLI tests**

Run:

```bash
pytest tests/test_cli.py::test_cli_prepare_real_run_writes_package_after_approval tests/test_cli.py::test_cli_prepare_real_run_reports_missing_approval_without_traceback tests/test_cli.py::test_cli_prepare_real_run_reports_config_drift_without_traceback -v
```

Expected: all three tests pass.

- [x] **Step 5: Run broader CLI and real-run tests**

Run:

```bash
pytest tests/test_real_run.py tests/test_cli.py -v
```

Expected: all selected tests pass.

- [x] **Step 6: Run ruff**

Run:

```bash
ruff check .
```

Expected: all checks pass.

- [x] **Step 7: Defer review gate to Task 6 combined batch gate**

Run:

```bash
claude -p "Review the current git diff for C-4 Task 4 against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on spec compliance and code quality. Return Critical, Important, Minor findings."
```

Risk-Tiered Batch Gates update: the per-task review gate was intentionally deferred to the Task 6 combined final review gate after local deterministic verification passed.

- [x] **Step 8: Commit Task 4**

Run:

```bash
git add src/hermes_workflow/cli.py tests/test_cli.py src/hermes_workflow/real_run.py tests/test_real_run.py
git commit -m "feat: add prepare real run cli"
```

## Task 5: Documentation and Progress State

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`

- [x] **Step 1: Update README command sequence**

In `README.md`, add `prepare-real-run` after approval in the usage command block:

```bash
hermes-workflow package projects/bridge_test_inv
# execution agent exports or places netlists/exported/input.scs
hermes-workflow prepare-netlist projects/bridge_test_inv
hermes-workflow dry-run projects/bridge_test_inv
hermes-workflow preflight-health projects/bridge_test_inv
hermes-workflow approve projects/bridge_test_inv
hermes-workflow prepare-real-run projects/bridge_test_inv
```

Add this sentence near the command sequence:

```markdown
`prepare-real-run` prepares `runs/real/real_001/` after approval, but it does not run Spectre, Virtuoso, subprocesses, or an optimizer loop.
```

- [x] **Step 2: Update project overview**

In `docs/PROJECT_WORKFLOW_OVERVIEW.md`, add `hermes-workflow prepare-real-run` after `approve` in the Mermaid flow:

```mermaid
    Q -- approve --> W[hermes-workflow prepare-real-run]
    W --> X[runs/real/real_001 package]
    X --> S[未来真实 Spectre/Virtuoso run]
```

Add a module note:

```markdown
### Post-approval real-run package 层

- `src/hermes_workflow/real_run.py`
  对应 Plan C C-4。它在 `approve_first_real_run` 之后验证 supervisor instruction 和 immutable config hashes，渲染第一个真实 candidate deck，并写入 `runs/real/real_001/candidate.json` 与 `real_run_manifest.json`。它不运行 Spectre。

- `hermes-workflow prepare-real-run`
  调用上述逻辑，准备后续真实 simulator runner 可消费的文件合同。
```

- [x] **Step 3: Update progress docs**

Append a `Plan C-4` section to `docs/EXECUTION_PROGRESS_2026-05-29.md`:

```markdown
## Plan C-4: Post-Approval Real-Run Execution Contract

Status: complete and reviewed as of 2026-06-01.

Spec:

- `docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`

Implemented:

- `src/hermes_workflow/real_run.py` prepares a contract-only real-run package after `approve_first_real_run`.
- `hermes-workflow prepare-real-run PROJECT_DIR` writes `runs/real/real_001/input.scs`, `candidate.json`, and `real_run_manifest.json`.
- The command refuses missing approval, rejected approval, immutable config drift, missing templates, invalid run IDs, and existing real-run packages.
- C-4 does not run Spectre, Virtuoso, subprocesses, metric extraction, ledger append, or optimizer execution.

Next recommended action:

- Confirm the next Plan C scope before adding Spectre subprocess execution, real metric extraction, or optimizer-loop integration.
```

Update `docs/COMPACT_RESUME_CHECKPOINT.md` latest checkpoint bullets:

```markdown
- C-4 post-approval real-run execution contract design spec exists: `0f64570 docs: design post approval real run contract`.
- C-4 implementation plan exists: `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`.
- C-4 is complete and reviewed.
```

Update `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`:

```markdown
- Current scope: Plan C-4, post-approval real-run execution contract
- Current status: complete and reviewed
- Next required action: confirm next Plan C scope
```

- [x] **Step 4: Mark this plan progress**

In this plan file, update the existing `## Execution Status` block after `## Execution Model`.

Run:

```bash
git log --oneline -8
```

Then replace the existing `## Execution Status` block with this shape. Copy the real short hashes and messages for these commits from `git log`; do not write temporary hash placeholders:

```markdown
## Execution Status

Status: complete and reviewed as of 2026-06-01.

Completed commits:

- Task 1: real short hash and message for `feat: guard post approval real runs`
- Task 2: real short hash and message for `feat: prepare first real run package`
- Task 3: real short hash and message for `fix: harden real run package creation`
- Task 4: real short hash and message for `feat: add prepare real run cli`

Verification:

- Task 4 selected tests passed.
- `ruff check .`: passed.

Final reviews:

- Combined final spec/code-quality review passed with no Critical or Important findings.
```

- [x] **Step 5: Run docs checks**

Run:

```bash
rg -n "prepare-real-run|real_run.py|real_001|C-4|Spectre" README.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md
```

Expected: `prepare-real-run`, `real_run.py`, `real_001`, and `C-4` appear in updated docs; docs explicitly say C-4 does not run Spectre.

- [x] **Step 6: Run tests and ruff**

Run:

```bash
pytest tests/test_real_run.py tests/test_cli.py -v
ruff check .
```

Expected: selected tests pass and ruff reports no issues.

- [x] **Step 7: Defer review gate to Task 6 combined batch gate**

Run:

```bash
claude -p "Review the current git diff for C-4 Task 5 against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus on docs/spec consistency and code quality. Return Critical, Important, Minor findings."
```

Risk-Tiered Batch Gates update: the per-task docs review gate was intentionally deferred to the Task 6 combined final review gate after docs checks and local deterministic verification passed.

- [x] **Step 8: Commit Task 5**

Run:

```bash
git add README.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md
git commit -m "docs: record real run package progress"
```

## Task 6: Final Verification and Review Gate

**Files:**
- No planned source changes unless final review finds Critical or Important issues.
- Modify status docs only after final verification and reviews pass.

- [x] **Step 1: Run full verification**

Run:

```bash
pytest -q
ruff check .
```

Expected: full pytest suite passes and ruff reports no issues.

- [x] **Step 2: Run combined final spec/code-quality review**

Run:

```bash
claude -p "Review the completed C-4 implementation against docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md. Focus only on spec compliance. Return Critical, Important, Minor findings and say whether it is ready to proceed."
```

Risk-Tiered Batch Gates update: replaced separate final spec and code-quality reviews with one combined final review gate. Result: no Critical or Important findings; ready to close C-4.

- [x] **Step 3: Combined review covered final code-quality review**

Run:

```bash
claude -p "Review the completed C-4 implementation diff for code quality, maintainability, error handling, test coverage, and behavior regressions. Return Critical, Important, Minor findings and say whether it is ready to proceed."
```

Risk-Tiered Batch Gates update: covered by the combined final review gate in Step 2.

- [x] **Step 4: Fix review findings if needed**

If a review returns Critical or Important findings, apply the smallest focused fix, then run:

```bash
pytest -q
ruff check .
```

Commit review fixes with:

```bash
git add src tests README.md docs
git commit -m "fix: address real run package review"
```

- [x] **Step 5: Update C-4 status docs**

After full verification and final reviews pass, update:

- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`

Use this status wording:

```markdown
Plan C-4 post-approval real-run execution contract is complete and reviewed. Final verification: `pytest -q` passed; `ruff check .` passed; final spec and code-quality reviews passed with no Critical or Important findings.
```

Set the next recommended action to:

```markdown
Confirm the next Plan C scope before adding Spectre subprocess execution, real metric extraction, or optimizer-loop integration.
```

- [x] **Step 6: Commit final status update**

Run:

```bash
git add docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/PROJECT_WORKFLOW_OVERVIEW.md docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md
git commit -m "docs: close real run package contract"
```

- [ ] **Step 7: Confirm clean closeout**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: worktree is clean and the latest commits correspond to C-4 tasks and any review fix.

## Self-Review Notes

- Spec coverage: Tasks 1-4 cover approval guard, config drift guard, deterministic first candidate, run package files, manifest contents, cleanup, overwrite refusal, run-id validation, and CLI behavior. Task 5 covers docs. Task 6 covers final verification and review.
- Scope: This plan does not run Virtuoso, run Spectre, launch subprocesses, parse Spectre results, compute real metrics, append production ledger rows, write optimizer state, or implement an optimizer loop.
- Local data safety: Real decks under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` remain local-only and are not copied into tests or docs as fixtures.
