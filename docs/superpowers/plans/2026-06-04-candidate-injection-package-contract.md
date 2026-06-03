# Candidate-Injection Package Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a narrow Hermes workflow command that turns one explicit optimizer candidate request into one deterministic `runs/real/<run_id>/` package.

**Architecture:** Reuse the existing `src/hermes_workflow/real_run.py` package writer instead of creating a parallel writer. Add validation for one candidate request file, pass the validated candidate into the existing package path, and extend that writer only enough to persist `candidate_request.json` as package evidence.

**Tech Stack:** Python 3, Pydantic models, Typer CLI, pytest, existing Hermes workflow contracts.

---

## Scope Guard

This plan implements only `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md`.

Allowed:

- Add `prepare_candidate_real_run()` as a library function.
- Add `hermes-workflow prepare-candidate-real-run`.
- Add focused tests with fake C-7 result artifacts.
- Reuse existing C-4/C-6/C-9 package/check/record code paths.

Forbidden:

- Do not add optimizer algorithms, TuRBO product code, acquisition logic, or optimizer ledger/state update logic beyond existing checks.
- Do not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 subprocess adapter.
- Do not parse PSF or waveform databases.
- Do not rewrite Calculator/OCEAN formulas.
- Do not replace C-4 first-run preparation or C-9 deterministic next-run preparation.
- Do not commit `docs/OCEAN_DOC_*`, `docs/toolchain_evidence/`, raw `input.scs`, protected include files, PSF/raw data, or full Cadence logs.

## File Map

- Modify `src/hermes_workflow/real_run.py`
  - Add candidate request schema and validation helpers.
  - Add `prepare_candidate_real_run(project_dir, *, candidate_file, run_id=None, created_at_utc=None)`.
  - Extend `_write_real_run_package()` with optional copied request evidence without changing existing callers.

- Modify `src/hermes_workflow/cli.py`
  - Import `prepare_candidate_real_run`.
  - Add `prepare-candidate-real-run PROJECT_DIR --candidate-file PATH [--run-id real_###]`.

- Create `tests/test_candidate_injection_real_run.py`
  - Cover candidate request validation, package shape, dedupe, unresolved-run guard, CLI behavior, and fake C-7 handoff compatibility.
  - Reuse helper functions from `tests/test_next_real_run.py` for the approved project and fake real-result setup.

- Update progress files after each completed task according to `AGENTS.md`
  - Always update `docs/CURRENT_TASK_STATE.json`.
  - Append `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` when task state changes.
  - Update this plan's checkboxes.

---

### Task 1: Candidate Request Validation

**Risk:** High. This validates optimizer-selected parameters against the approved design space.

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Create: `tests/test_candidate_injection_real_run.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`

- [x] **Step 1: Add focused failing tests for request schema and parameter validation**

Add `tests/test_candidate_injection_real_run.py` with imports and helpers:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.real_run import prepare_candidate_real_run
from tests.test_next_real_run import _create_ready_project, _load_json, _record_real_001


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _candidate_request(
    project_dir: Path,
    *,
    candidate_id: str = "candidate_000009",
    parameters: dict[str, str] | None = None,
    source: str = "optimizer_turbo_suggestion",
) -> Path:
    path = project_dir / "candidate_requests" / f"{candidate_id}.json"
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "source": source,
            "parameters": parameters
            or {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "metadata": {"optimizer": "turbo", "evaluation_index": 9},
        },
    )
    return path
```

Add tests:

```python
def test_prepare_candidate_real_run_rejects_missing_parameter(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters={"FN": "12", "WN": "1.3u", "FP": "2"},
    )

    with pytest.raises(ValueError, match="candidate parameters must match variables.yaml"):
        prepare_candidate_real_run(project_dir, candidate_file=request)

    assert not (project_dir / "runs" / "real" / "real_002").exists()


def test_prepare_candidate_real_run_rejects_extra_parameter(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters={
            "FN": "12",
            "WN": "1.3u",
            "FP": "2",
            "WP": "2.5u",
            "EXTRA": "1",
        },
    )

    with pytest.raises(ValueError, match="candidate parameters must match variables.yaml"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_bad_candidate_id(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, candidate_id="../bad")

    with pytest.raises(ValueError, match="candidate_id must be a safe identifier"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (
            {"FN": "1.5", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "FN must be an integer",
        ),
        (
            {"FN": "99", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
            "FN is outside approved bounds",
        ),
        (
            {"FN": "12", "WN": "1.3 um", "FP": "2", "WP": "2.5u"},
            "WN must use a Spectre-safe attached unit suffix",
        ),
        (
            {"FN": "12", "WN": "1.4u", "FP": "2", "WP": "2.5u"},
            "WN is not aligned to approved step",
        ),
    ],
)
def test_prepare_candidate_real_run_rejects_invalid_values(
    tmp_path: Path,
    parameters: dict[str, str],
    message: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, parameters=parameters)

    with pytest.raises(ValueError, match=message):
        prepare_candidate_real_run(project_dir, candidate_file=request)
```

- [x] **Step 2: Run validation tests and confirm they fail because the function is missing**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
```

Expected: fail with `ImportError` or `AttributeError` for `prepare_candidate_real_run`.

- [x] **Step 3: Add minimal validation implementation in `real_run.py`**

Modify imports:

```python
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from hermes_workflow.schemas import LedgerRow, OptimizerState, VariableKind
```

Add constants near the existing real-run constants:

```python
SAFE_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CONTINUOUS_VALUE_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?P<unit>[A-Za-z]+)?\s*$"
)
```

Add a strict request model:

```python
class CandidateInjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    candidate_id: str
    source: str = Field(min_length=1)
    parameters: dict[str, str]
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError('schema_version must be "1.0"')
        return value

    @field_validator("candidate_id")
    @classmethod
    def _candidate_id_is_safe(cls, value: str) -> str:
        if not value or not SAFE_CANDIDATE_ID_RE.match(value):
            raise ValueError("candidate_id must be a safe identifier")
        return value
```

Add request loading and parameter validation helpers:

```python
def _load_candidate_request(path: Path) -> CandidateInjectionRequest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"candidate request is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate request is invalid JSON: {exc.msg}") from exc
    try:
        return CandidateInjectionRequest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"candidate request is invalid: {exc}") from exc


def _assert_candidate_parameters_match_bundle(
    bundle: ContractBundle,
    parameters: dict[str, str],
) -> None:
    expected_names = [variable.name for variable in bundle.variables.variables]
    if set(parameters) != set(expected_names):
        raise ValueError("candidate parameters must match variables.yaml")
    for variable in bundle.variables.variables:
        raw_value = parameters[variable.name]
        if not isinstance(raw_value, str):
            raise ValueError(f"{variable.name} value must be a string")
        if variable.kind == VariableKind.INTEGER:
            _assert_integer_candidate(variable.name, raw_value, variable.lower, variable.upper, variable.step)
        elif variable.kind == VariableKind.CONTINUOUS_STEP:
            _assert_continuous_candidate(variable.name, raw_value, variable.lower, variable.upper, variable.step)
        else:
            raise ValueError(f"{variable.name} kind is unsupported: {variable.kind}")
```

Add numeric helpers:

```python
def _assert_integer_candidate(
    name: str,
    raw_value: str,
    lower_raw: str,
    upper_raw: str,
    step_raw: str,
) -> None:
    try:
        value = int(raw_value)
        lower = int(lower_raw)
        upper = int(upper_raw)
        step = int(step_raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if str(value) != raw_value:
        raise ValueError(f"{name} must be an integer")
    if value < lower or value > upper:
        raise ValueError(f"{name} is outside approved bounds")
    if step <= 0 or (value - lower) % step != 0:
        raise ValueError(f"{name} is not aligned to approved step")


def _parse_continuous_candidate(raw: str) -> tuple[Decimal, str]:
    match = CONTINUOUS_VALUE_RE.match(raw)
    if match is None:
        raise ValueError("value must be numeric with an optional unit suffix")
    if match.group("unit") and match.start("unit") > match.end("value"):
        raise ValueError("value must use a Spectre-safe attached unit suffix")
    try:
        return Decimal(match.group("value")), match.group("unit") or ""
    except InvalidOperation as exc:
        raise ValueError("value must be numeric with an optional unit suffix") from exc


def _assert_continuous_candidate(
    name: str,
    raw_value: str,
    lower_raw: str,
    upper_raw: str,
    step_raw: str,
) -> None:
    try:
        value, value_unit = _parse_continuous_candidate(raw_value)
    except ValueError as exc:
        if "attached unit suffix" in str(exc):
            raise ValueError(f"{name} must use a Spectre-safe attached unit suffix") from exc
        raise ValueError(f"{name} must be numeric with an optional unit suffix") from exc
    lower, lower_unit = _parse_continuous_candidate(lower_raw)
    upper, upper_unit = _parse_continuous_candidate(upper_raw)
    step, step_unit = _parse_continuous_candidate(step_raw)
    if len({value_unit, lower_unit, upper_unit, step_unit}) != 1:
        raise ValueError(f"{name} unit suffix must match variables.yaml")
    if value < lower or value > upper:
        raise ValueError(f"{name} is outside approved bounds")
    if step <= 0 or (value - lower) % step != 0:
        raise ValueError(f"{name} is not aligned to approved step")
```

Add a temporary public function body that validates only and raises a clear implementation error after validation:

```python
def prepare_candidate_real_run(
    project_dir: Path,
    *,
    candidate_file: Path,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    request = _load_candidate_request(Path(candidate_file))
    bundle = assert_valid_project(project_dir)
    _assert_candidate_parameters_match_bundle(bundle, request.parameters)
    raise NotImplementedError("candidate real-run package writing is implemented in Task 2")
```

- [x] **Step 4: Run validation tests and confirm invalid cases pass**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
```

Expected: validation rejection tests pass. Tests that expect a successful package are not added until Task 2.

- [x] **Step 5: Update task state and commit Task 1**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- This plan checkbox for Task 1

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Commit:

```bash
git add src/hermes_workflow/real_run.py tests/test_candidate_injection_real_run.py docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md
git commit -m "feat: validate candidate injection requests"
```

Stop for user confirmation.

---

### Task 2: Candidate Package Writer

**Risk:** High. This writes package files under `runs/real/<run_id>/`.

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Modify: `tests/test_candidate_injection_real_run.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`

- [x] **Step 1: Add failing happy-path and dedupe tests**

Append tests:

```python
def test_prepare_candidate_real_run_writes_real_002_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    variables_before = (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")

    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        created_at_utc="2026-06-04T00:00:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_002"
    candidate = _load_json(run_dir / "candidate.json")
    copied_request = _load_json(run_dir / "candidate_request.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")
    metric_request = _load_json(run_dir / "metric_extraction_request.json")

    assert package.run_id == "real_002"
    assert copied_request["candidate_id"] == "candidate_000009"
    assert candidate["candidate_id"] == "candidate_000009"
    assert candidate["source"] == "explicit_candidate_request"
    assert candidate["requested_source"] == "optimizer_turbo_suggestion"
    assert candidate["parameters"] == {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"}
    assert candidate["candidate_request_file"] == "runs/real/real_002/candidate_request.json"
    assert candidate["candidate_request_sha256"]
    assert manifest["run_id"] == "real_002"
    assert manifest["candidate_id"] == "candidate_000009"
    assert manifest["candidate_source"] == "explicit_candidate_request"
    assert manifest["selection_policy"] == "explicit_candidate_injection"
    assert manifest["candidate_request_file"] == "runs/real/real_002/candidate_request.json"
    assert manifest["candidate_request_sha256"] == candidate["candidate_request_sha256"]
    assert manifest["previous_evaluations"] == 1
    assert manifest["ledger_snapshot_sha256"]
    assert manifest["optimizer_state_sha256"]
    assert metric_request["run_id"] == "real_002"
    assert metric_request["candidate_id"] == "candidate_000009"
    assert (run_dir / "netlist" / "input.scs").exists()
    assert (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8") == variables_before


def test_prepare_candidate_real_run_rejects_real_001_override(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)

    with pytest.raises(ValueError, match="prepare-candidate-real-run cannot target real_001"):
        prepare_candidate_real_run(project_dir, candidate_file=request, run_id="real_001")


def test_prepare_candidate_real_run_rejects_duplicate_candidate_id_from_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir, candidate_id="real_001")

    with pytest.raises(ValueError, match="ledger already contains candidate_id real_001"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_duplicate_parameter_tuple_from_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(
        project_dir,
        parameters={"FN": "2", "WN": "0.3u", "FP": "2", "WP": "0.3u"},
    )

    with pytest.raises(ValueError, match="ledger already contains candidate parameters"):
        prepare_candidate_real_run(project_dir, candidate_file=request)


def test_prepare_candidate_real_run_rejects_duplicate_prepared_candidate_id(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    second = _candidate_request(
        project_dir,
        candidate_id="candidate_000009",
        parameters={"FN": "13", "WN": "1.3u", "FP": "2", "WP": "2.5u"},
    )

    with pytest.raises(ValueError, match="prepared run already contains candidate_id candidate_000009"):
        prepare_candidate_real_run(project_dir, candidate_file=second, run_id="real_003")


def test_prepare_candidate_real_run_rejects_duplicate_prepared_parameters(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = _candidate_request(project_dir, candidate_id="candidate_000009")
    prepare_candidate_real_run(project_dir, candidate_file=first)
    second = _candidate_request(project_dir, candidate_id="candidate_000010")

    with pytest.raises(ValueError, match="prepared run already contains candidate parameters"):
        prepare_candidate_real_run(project_dir, candidate_file=second, run_id="real_003")
```

- [x] **Step 2: Run tests and confirm package-writing failures**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
```

Expected: happy-path and dedupe tests fail because package writing is not implemented.

- [x] **Step 3: Implement package writing by reusing `_write_real_run_package()`**

Add helper functions:

```python
def _json_text(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_request_payload(request: CandidateInjectionRequest) -> dict:
    return request.model_dump(mode="json")
```

Extend `_write_real_run_package()` signature:

```python
def _write_real_run_package(
    bundle: ContractBundle,
    selected_run_id: str,
    candidate: dict,
    created_at_utc: str,
    instruction: dict,
    approved_hashes: dict[str, str],
    *,
    manifest_extra: dict,
    rendered_text_override: str | None = None,
    candidate_request_text: str | None = None,
) -> RealRunPackage:
```

Inside `_write_real_run_package()`, define and write the optional request before `candidate.json`:

```python
candidate_request_relative = (
    f"{REAL_RUN_ROOT}/{selected_run_id}/candidate_request.json"
    if candidate_request_text is not None
    else None
)
candidate_request_path = (
    _project_path(bundle, candidate_request_relative)
    if candidate_request_relative is not None
    else None
)
```

Inside the `try` block, before writing `candidate.json`:

```python
candidate_for_write = dict(candidate)
if candidate_request_path is not None and candidate_request_text is not None:
    candidate_request_path.write_text(candidate_request_text, encoding="utf-8")
    candidate_for_write["candidate_request_file"] = candidate_request_relative
    candidate_for_write["candidate_request_sha256"] = sha256_file(candidate_request_path)
candidate_path.write_text(
    json.dumps(candidate_for_write, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
candidate_id = str(candidate_for_write["candidate_id"])
```

Return `candidate_payload=candidate_for_write`.

Add dedupe helpers:

```python
def _prepared_candidate_ids(project_dir: Path) -> set[str]:
    root = project_dir / REAL_RUN_ROOT
    ids: set[str] = set()
    if not root.exists():
        return ids
    for run_dir in sorted(root.iterdir()):
        if not RUN_ID_RE.match(run_dir.name):
            continue
        _assert_run_dir_is_not_symlink(run_dir)
        candidate_path = run_dir / "candidate.json"
        if not candidate_path.exists():
            continue
        payload = _load_json_object(candidate_path, "prepared candidate")
        candidate_id = payload.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise ValueError(f"prepared candidate is invalid: {candidate_path}")
        ids.add(candidate_id)
    return ids


def _assert_candidate_is_unique(
    project_dir: Path,
    request: CandidateInjectionRequest,
    ledger_rows: list[LedgerRow],
) -> None:
    request_key = _parameter_key(request.parameters)
    for row in ledger_rows:
        if row.candidate_id == request.candidate_id:
            raise ValueError(f"ledger already contains candidate_id {request.candidate_id}")
        if _parameter_key(row.parameters) == request_key:
            raise ValueError("ledger already contains candidate parameters")
    if request.candidate_id in _prepared_candidate_ids(project_dir):
        raise ValueError(f"prepared run already contains candidate_id {request.candidate_id}")
    if request_key in _prepared_candidate_keys(project_dir):
        raise ValueError("prepared run already contains candidate parameters")
```

Replace the temporary `prepare_candidate_real_run()` body:

```python
def prepare_candidate_real_run(
    project_dir: Path,
    *,
    candidate_file: Path,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    if run_id is not None:
        _validate_run_id(run_id)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)

    from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

    assert_no_unresolved_real_runs(project_dir)
    bundle = assert_valid_project(project_dir)
    request = _load_candidate_request(Path(candidate_file))
    _assert_candidate_parameters_match_bundle(bundle, request.parameters)
    ledger_rows = _read_ledger_rows_or_raise(project_dir)
    state = _load_optimizer_state_or_raise(project_dir)
    _assert_optimizer_state_matches_bundle(bundle, state, ledger_rows)
    _assert_candidate_is_unique(project_dir, request, ledger_rows)

    selected_run_id = _select_next_run_id(project_dir, run_id)
    request_payload = _candidate_request_payload(request)
    request_text = _json_text(request_payload)
    request_sha256 = _sha256_text(request_text)
    candidate = {
        "schema_version": "1.0",
        "candidate_id": request.candidate_id,
        "source": "explicit_candidate_request",
        "requested_source": request.source,
        "parameters": request.parameters,
        "metadata": request.metadata,
    }
    return _write_real_run_package(
        bundle,
        selected_run_id,
        candidate,
        created_at_utc or _utc_now(),
        instruction,
        approved_hashes,
        manifest_extra={
            "candidate_source": "explicit_candidate_request",
            "selection_policy": "explicit_candidate_injection",
            "candidate_request_file": f"{REAL_RUN_ROOT}/{selected_run_id}/candidate_request.json",
            "candidate_request_sha256": request_sha256,
            "ledger_snapshot_sha256": _sha256_existing_or_empty(project_dir / LEDGER_PATH),
            "optimizer_state_sha256": sha256_file(project_dir / OPTIMIZER_STATE_PATH),
            "previous_evaluations": len(ledger_rows),
        },
        candidate_request_text=request_text,
    )
```

- [x] **Step 4: Run targeted package tests**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py -q
```

Expected: pass.

- [x] **Step 5: Update task state and commit Task 2**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- This plan checkbox for Task 2

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Commit:

```bash
git add src/hermes_workflow/real_run.py tests/test_candidate_injection_real_run.py docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md
git commit -m "feat: prepare candidate real run packages"
```

Stop for user confirmation.

---

### Task 3: CLI Wiring And Fake Handoff Smoke

**Risk:** Medium. This exposes the library path through CLI and proves compatibility with fake C-7 artifacts.

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_candidate_injection_real_run.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`

- [x] **Step 1: Add failing CLI and fake handoff smoke tests**

Append tests:

```python
def test_prepare_candidate_real_run_cli_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "prepare-candidate-real-run",
            str(project_dir),
            "--candidate-file",
            str(request),
        ],
    )

    assert result.exit_code == 0
    assert "candidate real run package prepared" in result.output
    assert "run: runs/real/real_002" in result.output
    assert "manifest: runs/real/real_002/real_run_manifest.json" in result.output
    assert "candidate: runs/real/real_002/candidate.json" in result.output
    assert "candidate request: runs/real/real_002/candidate_request.json" in result.output


def test_prepare_candidate_real_run_cli_failure_without_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    request = _candidate_request(project_dir)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "prepare-candidate-real-run",
            str(project_dir),
            "--candidate-file",
            str(request),
        ],
    )

    assert result.exit_code == 1
    assert "unresolved real run exists" in result.output
```

Add a fake C-7 compatibility smoke. Use local fake result writers in this test file
instead of importing `tests.test_next_real_run` helper writers, because the existing
helpers intentionally set `candidate_id` to the run id and would not preserve the
explicit optimizer candidate id required by this contract:

```python
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import MetricResultCheckStatus, RealResultRecordStatus, RealRunCheckStatus
```

Then append:

```python
def test_candidate_package_accepts_fake_c7_result_and_records(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    request = _candidate_request(project_dir)
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        created_at_utc="2026-06-04T00:00:00Z",
    )

    _write_candidate_result_manifest(project_dir, run_id=package.run_id)
    _write_candidate_metric_result_manifest(project_dir, run_id=package.run_id)

    real_report = check_real_run(project_dir, run_id=package.run_id)
    metric_report = check_metric_results(project_dir, run_id=package.run_id)
    record_report = record_real_result(
        project_dir,
        run_id=package.run_id,
        recorded_at_utc="2026-06-04T00:10:00Z",
    )

    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
    assert record_report.status == RealResultRecordStatus.PASS
    assert record_report.candidate_id == "candidate_000009"

    ledger_rows = [
        json.loads(line)
        for line in (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert [row["run_id"] for row in ledger_rows] == ["real_001", "real_002"]
    assert ledger_rows[1]["candidate_id"] == "candidate_000009"
    assert ledger_rows[1]["parameters"] == {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"}
```

- [x] **Step 2: Run tests and confirm CLI command is missing**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
```

Expected: CLI test fails because command does not exist.

- [x] **Step 3: Add CLI command**

Modify `src/hermes_workflow/cli.py` import:

```python
from hermes_workflow.real_run import (
    prepare_candidate_real_run,
    prepare_next_real_run,
    prepare_real_run,
)
```

Add command after `prepare-next-real-run`:

```python
@app.command("prepare-candidate-real-run")
def prepare_candidate_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with at least one recorded checked real result."
        ),
    ],
    candidate_file: Annotated[
        Path,
        typer.Option(
            "--candidate-file",
            help="JSON file containing one explicit optimizer candidate request.",
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Optional candidate real-run package id such as real_002.",
        ),
    ] = None,
) -> None:
    try:
        package = prepare_candidate_real_run(
            project_dir,
            candidate_file=candidate_file,
            run_id=run_id,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("candidate real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")
    typer.echo(f"candidate: {package.candidate_path.relative_to(project_dir)}")
    typer.echo(
        "candidate request: "
        f"{package.run_dir.relative_to(project_dir) / 'candidate_request.json'}"
    )
```

- [x] **Step 4: Run targeted CLI and fake handoff tests**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py tests/test_cli.py -q
python3 -m pytest tests/test_next_real_run.py tests/test_real_result_record.py tests/test_metric_results.py -q
```

Expected: pass.

- [x] **Step 5: Update task state and commit Task 3**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- This plan checkbox for Task 3

Run:

```bash
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Commit:

```bash
git add src/hermes_workflow/cli.py tests/test_candidate_injection_real_run.py docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md
git commit -m "feat: add candidate real run CLI"
```

Stop for user confirmation.

---

### Task 4: Final Verification And Review Gate

**Risk:** High. Final gate for package-writing contract.

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`

- [ ] **Step 1: Run full targeted verification**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py -q
python3 -m pytest tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_result_record.py tests/test_cli.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: pass. `git status --short` may still show local-only `docs/OCEAN_DOC_*` and `docs/toolchain_evidence/`; do not stage them.

- [ ] **Step 2: Run high-risk review gate**

Use the project review path available in the session. If Claude review MCP is available, request:

```text
Review the candidate-injection package contract implementation against docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md.
Focus on: file writes, cleanup, candidate request hash provenance, run-id policy, duplicate candidate/parameter rejection, config immutability, and accidental real-tool execution.
```

Record status as:

- `reviewed` only when spec-compliance and code-quality review evidence exists.
- `verified-only` if no callable review path is available.
- `blocked-no-subagent` if review is required by the user and no review path exists.

- [ ] **Step 3: Update milestone state**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- This plan checkbox for Task 4

Route audit text:

```text
Alignment: The implementation follows the candidate-injection design spec and top-level practice-first route. It adds only explicit candidate package preparation after recorded real evidence and before optimizer algorithm productization.
Drift: None if no optimizer algorithm, real-tool execution, PSF parsing, formula rewriting, or Maestro/ADE layout replacement was added.
```

- [ ] **Step 4: Commit final docs if needed**

Run:

```bash
git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/COMPACT_RESUME_CHECKPOINT.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md
git commit -m "docs: record candidate injection package completion"
```

If Task 3 already updated all docs and no final docs changed, skip this commit and report that no final docs commit was needed.

Stop for user confirmation before starting Hermes optimizer algorithm productization.

---

## Final Acceptance Criteria

- `prepare_candidate_real_run()` prepares `real_002+` from one explicit candidate request after at least one recorded real result exists.
- `candidate_request.json` is copied into the run package and hashed.
- `candidate.json`, `real_run_manifest.json`, and `metric_extraction_request.json` agree on run id, candidate id, paths, and hashes.
- `config/variables.yaml` is not modified.
- Existing C-4 `prepare_real_run()` and C-9 `prepare_next_real_run()` behavior remains compatible.
- Existing C-10 unresolved-run guard blocks new candidate packages when a prior run is unresolved.
- Fake C-7 result artifacts can pass `check-real-run`, `check-metric-results`, and `record-real-result`.
- No real Cadence tools are invoked during implementation or tests.

## Self-Review Checklist

- Spec coverage: Tasks 1-3 cover request schema, validation, package outputs, run-id policy, dedupe, CLI, cleanup through existing writer, and fake handoff compatibility.
- Red-flag scan: This plan contains no incomplete implementation markers.
- Type consistency: Public function is `prepare_candidate_real_run(project_dir, *, candidate_file, run_id=None, created_at_utc=None)`. CLI command is `prepare-candidate-real-run`.
- Route alignment: This remains a package contract and does not start optimizer algorithm productization.
