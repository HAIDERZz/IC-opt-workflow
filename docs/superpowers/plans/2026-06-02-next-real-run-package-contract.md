# Next Real-Run Package Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build C-9 so Hermes workflow tooling can prepare the next real-run package after a checked real result has been recorded.

**Architecture:** Keep C-9 inside the deterministic Hermes file-contract layer. Extend `real_run.py` with next-candidate selection and package writing that reuses the existing C-4/C-6 package shape, uses Plan B's deterministic candidate generator, deduplicates against ledger and already prepared runs, and never invokes real Cadence tools.

**Tech Stack:** Python 3.11+, existing Pydantic schemas, `mock_optimizer.generate_candidates`, `real_run` package writer helpers, Typer CLI, pytest, ruff.

---

## Required Reading

- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`
- `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`
- `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/mock_optimizer.py`
- `src/hermes_workflow/cli.py`
- `tests/test_real_run.py`
- `tests/test_real_result_record.py`

## Execution Model

Use Subagent-Driven Development.

Risk-tiered review gates:

- Task 1 is high risk because it decides candidate progression. Run local tests and code-quality review.
- Task 2 is high risk because it writes `runs/real/<run_id>/` package files. Run local tests and code-quality review.
- Tasks 3-4 are medium risk because they wire integration tests and CLI. Batch them into one review gate after Task 4.
- Task 5 is low risk docs/progress work. Run local checks, then one final combined review.

No task may call real Virtuoso, Spectre, OCEAN, SSH, Claude CLI as an execution agent, `virtuoso-bridge-lite`, or network access.

## File Map

- Modify `src/hermes_workflow/real_run.py`: add `prepare_next_real_run()`, candidate selection helpers, strict ledger/state readers, next run-id selection, and manifest provenance additions.
- Modify `src/hermes_workflow/cli.py`: add `prepare-next-real-run`.
- Create `tests/test_next_real_run.py`: C-9 unit and integration tests with synthetic project fixtures.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: record C-9 layer after implementation.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-9 implementation status.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: record compact-resume node.
- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: update next-development handoff.
- Modify this plan file as task checkboxes complete.

## Shared Constants

Use existing constants from `real_run.py`:

```python
RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
SUPERVISOR_INSTRUCTION = "supervisor_instruction.json"
EXECUTION_MANIFEST = "execution_package/execution_manifest.json"
```

Add C-9 constants in `real_run.py`:

```python
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
NEXT_CANDIDATE_SOURCE = "deterministic_initialization_sequence"
NEXT_SELECTION_POLICY = "next_unique_from_optimizer_initialization_sequence"
EMPTY_LEDGER_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

Use `EMPTY_LEDGER_SHA256` only when the ledger file is absent. Normal C-9 usage after C-8 should have a ledger file.

---

## Task 1: Candidate Selection Preconditions

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Create: `tests/test_next_real_run.py`
- Modify: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

- [x] **Step 1: Write failing candidate-selection tests**

Create `tests/test_next_real_run.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_next_real_run, prepare_real_run
from hermes_workflow.real_result_record import record_real_result
from hermes_workflow.reports import RealResultRecordStatus, RealRunCheckStatus
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


def _write_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
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
    _write_json(
        run_dir / "result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": run_id,
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


def _write_metric_result_manifest(project_dir: Path, *, run_id: str = "real_001") -> None:
    run_dir = project_dir / "runs" / "real" / run_id
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    metrics_dir = run_dir / "metrics"
    script_path = metrics_dir / "metric_probe.ocn"
    script_path.write_text("sanitized ocean script\n", encoding="utf-8")
    request_by_name = {metric["name"]: metric for metric in request["metrics"]}
    values = {"rise": 1.0e-12, "fall": 1.0e-12, "DC": 1.0e-6}
    _write_json(
        metrics_dir / "metric_result_manifest.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "candidate_id": run_id,
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
                    "result": request_by_name[name]["result"],
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


def _record_real_001(project_dir: Path) -> None:
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)
    assert check_real_run(project_dir).status == RealRunCheckStatus.PASS
    report = record_real_result(
        project_dir,
        recorded_at_utc="2026-06-02T00:40:00Z",
    )
    assert report.status == RealResultRecordStatus.PASS
```

Append precondition tests:

```python
def test_prepare_next_real_run_refuses_before_recorded_result(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    with pytest.raises(ValueError, match="ledger is missing"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_invalid_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    ledger_path = project_dir / "ledger" / "experiment_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ledger row 1 is invalid"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_optimizer_state_drift(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["random_seed"] = 99
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state random_seed disagrees"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_completed_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["status"] = "completed"
    _write_json(state_path, state)

    with pytest.raises(ValueError, match="optimizer state is completed"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_refuses_when_max_evaluations_reached(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    optimizer_path.write_text(
        optimizer_path.read_text(encoding="utf-8").replace(
            "max_evaluations: 20",
            "max_evaluations: 1",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immutable config drift detected"):
        prepare_next_real_run(project_dir)
```

The final max-evaluations test intentionally expects config drift because immutable config changes after approval must fail before optimizer policy evaluation.

- [x] **Step 2: Run tests and verify they fail for missing function**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
```

Expected: import failure for `prepare_next_real_run`.

- [x] **Step 3: Add strict ledger/state helpers and a stub `prepare_next_real_run()`**

Modify `src/hermes_workflow/real_run.py` imports:

```python
import hashlib
from pydantic import ValidationError

from hermes_workflow.mock_optimizer import generate_candidates
from hermes_workflow.schemas import LedgerRow, OptimizerState
```

Add constants after `EXECUTION_MANIFEST`:

```python
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
NEXT_CANDIDATE_SOURCE = "deterministic_initialization_sequence"
NEXT_SELECTION_POLICY = "next_unique_from_optimizer_initialization_sequence"
EMPTY_LEDGER_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

Add helper functions near `_load_json_object()`:

```python
def _read_ledger_rows_or_raise(project_dir: Path) -> list[LedgerRow]:
    ledger_path = project_dir / LEDGER_PATH
    if not ledger_path.exists():
        raise ValueError("ledger is missing; record a checked real result first")
    rows: list[LedgerRow] = []
    for line_number, raw_line in enumerate(
        ledger_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            rows.append(LedgerRow.model_validate(payload))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"ledger row {line_number} is invalid: {exc}") from exc
    if not rows:
        raise ValueError("ledger has no recorded evaluations")
    return rows


def _load_optimizer_state_or_raise(project_dir: Path) -> OptimizerState:
    state_path = project_dir / OPTIMIZER_STATE_PATH
    if not state_path.exists():
        raise ValueError("optimizer state is missing")
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return OptimizerState.model_validate(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"optimizer state is invalid JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise ValueError(f"optimizer state is invalid: {exc}") from exc
```

Add state/config check:

```python
def _assert_optimizer_state_matches_bundle(
    bundle: ContractBundle,
    state: OptimizerState,
    ledger_rows: list[LedgerRow],
) -> None:
    optimizer = bundle.optimizer.optimizer
    checks = {
        "algorithm": optimizer.algorithm.value,
        "initialization": optimizer.initialization.value,
        "max_evaluations": optimizer.max_evaluations,
        "batch_size": optimizer.batch_size,
        "random_seed": optimizer.random_seed,
    }
    for field_name, expected in checks.items():
        actual = getattr(state, field_name)
        if actual != expected:
            raise ValueError(
                f"optimizer state {field_name} disagrees with optimizer.yaml"
            )
    if state.status in {"completed", "stopped"}:
        raise ValueError(f"optimizer state is {state.status}")
    if state.current_evaluations != len(ledger_rows):
        raise ValueError(
            "optimizer state current_evaluations disagrees with ledger row count"
        )
    if state.current_evaluations >= optimizer.max_evaluations:
        raise ValueError("optimizer maximum evaluations have already been reached")
```

Add a temporary public function:

```python
def prepare_next_real_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)
    ledger_rows = _read_ledger_rows_or_raise(project_dir)
    state = _load_optimizer_state_or_raise(project_dir)
    _assert_optimizer_state_matches_bundle(bundle, state, ledger_rows)
    raise ValueError("next candidate selection is not implemented")
```

- [x] **Step 4: Run tests and verify precondition tests pass up to the stub**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
```

Expected: some tests pass; remaining tests fail with `next candidate selection is not implemented` once later happy-path tests are added.

- [x] **Step 5: Commit Task 1**

```bash
git add src/hermes_workflow/real_run.py tests/test_next_real_run.py docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md
git commit -m "feat: validate next real run preconditions"
```

- [x] **Step 6: Review gate**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
python3 -m pytest tests/test_real_run.py tests/test_real_result_record.py tests/test_next_real_run.py -q
python3 -m ruff check src tests tools
git diff --check
```

Run code-quality review focused on:

```text
Review C-9 Task 1 next real-run preconditions.

Check:
- no real tool invocation
- no PSF parsing
- immutable config drift checked before optimizer state policy
- strict ledger/state parsing
- no writes before preconditions pass
- role model remains Hermes workflow tooling, not Hermes agent
```

---

## Task 2: Next Candidate Selection And Package Writing

**Files:**

- Modify: `src/hermes_workflow/real_run.py`
- Modify: `tests/test_next_real_run.py`
- Modify: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

- [x] **Step 1: Add failing package-writing tests**

Append to `tests/test_next_real_run.py`:

```python
def test_prepare_next_real_run_writes_real_002_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_002"
    candidate = _load_json(run_dir / "candidate.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")
    metric_request = _load_json(run_dir / "metric_extraction_request.json")
    rendered = (run_dir / "input.scs").read_text(encoding="utf-8")

    assert package.run_id == "real_002"
    assert package.run_dir == run_dir
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert candidate["candidate_id"] == "real_002"
    assert candidate["source"] == "deterministic_initialization_sequence"
    assert candidate["candidate_index"] == 1
    assert candidate["parameters"] == {
        "FN": "11",
        "FP": "11",
        "WN": "0.3 um",
        "WP": "2.9 um",
    }
    assert manifest["run_id"] == "real_002"
    assert manifest["candidate_id"] == "real_002"
    assert manifest["candidate_source"] == "deterministic_initialization_sequence"
    assert manifest["candidate_index"] == 1
    assert manifest["selection_policy"] == (
        "next_unique_from_optimizer_initialization_sequence"
    )
    assert manifest["previous_evaluations"] == 1
    assert manifest["ledger_snapshot_sha256"]
    assert manifest["optimizer_state_sha256"]
    assert manifest["metric_extraction_request"] == (
        "runs/real/real_002/metric_extraction_request.json"
    )
    assert metric_request["run_id"] == "real_002"
    assert metric_request["candidate_id"] == "real_002"
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl.lock").exists()


def test_prepare_next_real_run_refuses_real_001_override(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    with pytest.raises(ValueError, match="prepare-next-real-run cannot target real_001"):
        prepare_next_real_run(project_dir, run_id="real_001")


def test_prepare_next_real_run_refuses_existing_run_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_002"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "real_run_manifest.json", {"status": "prepared"})

    with pytest.raises(FileExistsError, match="real run package already exists"):
        prepare_next_real_run(project_dir)


def test_prepare_next_real_run_skips_already_prepared_candidate(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    first = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )
    assert first.run_id == "real_002"

    second = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T01:00:00Z",
    )

    candidate = _load_json(second.candidate_path)
    assert second.run_id == "real_003"
    assert candidate["candidate_index"] == 2
    assert candidate["parameters"] == {
        "FN": "4",
        "FP": "2",
        "WN": "2.3 um",
        "WP": "0.7 um",
    }
```

- [x] **Step 2: Run tests and verify package tests fail on stub**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
```

Expected: new package tests fail with `next candidate selection is not implemented`.

- [x] **Step 3: Implement next run id and prepared candidate scanning**

Add to `src/hermes_workflow/real_run.py`:

```python
def _next_unused_run_id(project_dir: Path) -> str:
    root = project_dir / REAL_RUN_ROOT
    used: set[int] = {1}
    if root.exists():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if RUN_ID_RE.match(child.name):
                used.add(int(child.name.removeprefix("real_")))
    next_id = 2
    while next_id in used:
        next_id += 1
    return f"real_{next_id:03d}"


def _select_next_run_id(project_dir: Path, run_id: str | None) -> str:
    if run_id is None:
        return _next_unused_run_id(project_dir)
    selected = _validate_run_id(run_id)
    if selected == DEFAULT_RUN_ID:
        raise ValueError("prepare-next-real-run cannot target real_001")
    return selected


def _parameter_key(parameters: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(parameters.items()))


def _prepared_candidate_keys(project_dir: Path) -> set[tuple[tuple[str, str], ...]]:
    root = project_dir / REAL_RUN_ROOT
    keys: set[tuple[tuple[str, str], ...]] = set()
    if not root.exists():
        return keys
    for candidate_path in sorted(root.glob("real_[0-9][0-9][0-9]/candidate.json")):
        payload = _load_json_object(candidate_path, "prepared candidate")
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise ValueError(f"prepared candidate is invalid: {candidate_path}")
        keys.add(_parameter_key(parameters))
    return keys
```

- [x] **Step 4: Implement candidate sequence selection**

Add:

```python
@dataclass(frozen=True)
class _CandidateSelection:
    candidate_index: int
    parameters: dict[str, str]


def _select_next_candidate(
    bundle: ContractBundle,
    ledger_rows: list[LedgerRow],
    prepared_keys: set[tuple[tuple[str, str], ...]],
) -> _CandidateSelection:
    evaluated_keys = {_parameter_key(row.parameters) for row in ledger_rows}
    used_keys = evaluated_keys | prepared_keys
    candidates = generate_candidates(
        bundle,
        n_candidates=bundle.optimizer.optimizer.max_evaluations,
        seed=bundle.optimizer.optimizer.random_seed,
        initialization=bundle.optimizer.optimizer.initialization.value,
    )
    for index, parameters in enumerate(candidates, 1):
        if _parameter_key(parameters) not in used_keys:
            return _CandidateSelection(candidate_index=index, parameters=parameters)
    raise ValueError("no unique candidate remains in optimizer initialization sequence")


def _next_candidate_payload(
    run_id: str,
    selection: _CandidateSelection,
) -> dict:
    return {
        "schema_version": "1.0",
        "candidate_id": run_id,
        "source": NEXT_CANDIDATE_SOURCE,
        "candidate_index": selection.candidate_index,
        "parameters": selection.parameters,
    }
```

- [x] **Step 5: Refactor package writing into a reusable helper**

Replace the body of `prepare_real_run()` after preconditions with:

```python
    candidate = _lower_bound_candidate(bundle, selected_run_id)
    return _write_real_run_package(
        bundle,
        selected_run_id,
        candidate,
        created_at_utc or _utc_now(),
        instruction,
        approved_hashes,
        manifest_extra={},
    )
```

Add `_write_real_run_package()`:

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
) -> RealRunPackage:
    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    manifest_path = run_dir / "real_run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")

    template_relative = bundle.project_config.netlist.template_scs
    template_path = _project_path(bundle, template_relative)
    if not template_path.exists():
        raise FileNotFoundError(f"template.scs is missing: {template_relative}")

    rendered_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/input.scs"
    candidate_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate.json"
    metric_request_relative = (
        f"{REAL_RUN_ROOT}/{selected_run_id}/metric_extraction_request.json"
    )
    rendered_path = _project_path(bundle, rendered_relative)
    candidate_path = _project_path(bundle, candidate_relative)
    metric_request_path = _project_path(bundle, metric_request_relative)

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
        metric_request_payload = build_metric_extraction_request(
            bundle,
            run_id=selected_run_id,
            candidate_id=selected_run_id,
            prepared_input_scs=rendered_relative,
            prepared_input_sha256=sha256_file(rendered_path),
        )
        metric_request_path.write_text(
            json.dumps(metric_request_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_payload = _build_manifest(
            bundle,
            selected_run_id,
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
        manifest_payload.update(manifest_extra)
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
        metric_request_path=metric_request_path,
        candidate_payload=candidate,
        manifest_payload=manifest_payload,
        metric_request_payload=metric_request_payload,
    )
```

- [x] **Step 6: Implement `prepare_next_real_run()` fully**

Replace the Task 1 stub tail with:

```python
    selected_run_id = _select_next_run_id(project_dir, run_id)
    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    if (run_dir / "real_run_manifest.json").exists():
        raise FileExistsError(
            f"real run package already exists: {run_dir / 'real_run_manifest.json'}"
        )
    prepared_keys = _prepared_candidate_keys(project_dir)
    selection = _select_next_candidate(bundle, ledger_rows, prepared_keys)
    candidate = _next_candidate_payload(selected_run_id, selection)
    ledger_hash = _sha256_existing_or_empty(project_dir / LEDGER_PATH)
    state_hash = sha256_file(project_dir / OPTIMIZER_STATE_PATH)
    return _write_real_run_package(
        bundle,
        selected_run_id,
        candidate,
        created_at_utc or _utc_now(),
        instruction,
        approved_hashes,
        manifest_extra={
            "candidate_source": NEXT_CANDIDATE_SOURCE,
            "candidate_index": selection.candidate_index,
            "selection_policy": NEXT_SELECTION_POLICY,
            "ledger_snapshot_sha256": ledger_hash,
            "optimizer_state_sha256": state_hash,
            "previous_evaluations": len(ledger_rows),
        },
    )
```

Add hash helper:

```python
def _sha256_existing_or_empty(path: Path) -> str:
    if not path.exists():
        return EMPTY_LEDGER_SHA256
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

- [x] **Step 7: Run package tests**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
python3 -m pytest tests/test_real_run.py tests/test_next_real_run.py -q
```

Expected: pass.

- [x] **Step 8: Commit Task 2**

```bash
git add src/hermes_workflow/real_run.py tests/test_next_real_run.py docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md
git commit -m "feat: prepare next real run package"
```

- [x] **Step 9: Review gate**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py tests/test_real_result_record.py -q
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Run code-quality review focused on:

```text
Review C-9 Task 2 next real-run package writer.

Check:
- prepare_real_run behavior is preserved
- package writes are fail-closed and clean partial directories
- next package remains C-4/C-6 compatible
- no real tool invocation
- formulas are passed through metric_extraction_request only
- no ledger/state writes happen in C-9
```

---

## Task 3: Handoff Compatibility Tests

**Files:**

- Modify: `tests/test_next_real_run.py`
- Modify: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

- [ ] **Step 1: Add fake C-7 compatibility test for `real_002`**

Append:

```python
def test_next_real_run_package_can_be_checked_and_recorded_after_fake_result(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    package = prepare_next_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:50:00Z",
    )
    assert package.run_id == "real_002"

    _write_result_manifest(project_dir, run_id="real_002")
    _write_metric_result_manifest(project_dir, run_id="real_002")

    real_report = check_real_run(project_dir, run_id="real_002")
    assert real_report.status == RealRunCheckStatus.PASS
    record_report = record_real_result(
        project_dir,
        run_id="real_002",
        recorded_at_utc="2026-06-02T01:10:00Z",
    )

    assert record_report.status == RealResultRecordStatus.PASS
    ledger_rows = [
        json.loads(line)
        for line in (project_dir / "ledger" / "experiment_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert [row["run_id"] for row in ledger_rows] == ["real_001", "real_002"]
    assert ledger_rows[1]["candidate_id"] == "real_002"
    assert ledger_rows[1]["parameters"] == package.candidate_payload["parameters"]
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    assert state["current_evaluations"] == 2
```

- [ ] **Step 2: Run compatibility test**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py::test_next_real_run_package_can_be_checked_and_recorded_after_fake_result -q
```

Expected: pass.

- [ ] **Step 3: Commit Task 3**

```bash
git add tests/test_next_real_run.py docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md
git commit -m "test: verify next real run handoff compatibility"
```

---

## Task 4: CLI Integration

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_next_real_run.py`
- Modify: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

- [ ] **Step 1: Add CLI tests**

Append imports:

```python
from typer.testing import CliRunner

from hermes_workflow.cli import app
```

Append:

```python
def test_prepare_next_real_run_cli_success(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()

    result = runner.invoke(app, ["prepare-next-real-run", str(project_dir)])

    assert result.exit_code == 0
    assert "next real run package prepared" in result.output
    assert "run: runs/real/real_002" in result.output
    assert "manifest: runs/real/real_002/real_run_manifest.json" in result.output
    assert "candidate: runs/real/real_002/candidate.json" in result.output


def test_prepare_next_real_run_cli_failure(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["prepare-next-real-run", str(project_dir)])

    assert result.exit_code == 1
    assert "ledger is missing" in result.output
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py::test_prepare_next_real_run_cli_success tests/test_next_real_run.py::test_prepare_next_real_run_cli_failure -q
```

Expected: fail because the CLI command does not exist.

- [ ] **Step 3: Wire CLI command**

Modify `src/hermes_workflow/cli.py` import:

```python
from hermes_workflow.real_run import prepare_next_real_run, prepare_real_run
```

Add command after `prepare-real-run`:

```python
@app.command("prepare-next-real-run")
def prepare_next_real_run_command(
    project_dir: Annotated[
        Path,
        typer.Argument(
            help="Project directory with at least one recorded checked real result."
        ),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Optional next real-run package id such as real_002.",
        ),
    ] = None,
) -> None:
    try:
        package = prepare_next_real_run(project_dir, run_id=run_id)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo("next real run package prepared")
    typer.echo(f"run: {package.run_dir.relative_to(project_dir)}")
    typer.echo(f"manifest: {package.manifest_path.relative_to(project_dir)}")
    typer.echo(f"candidate: {package.candidate_path.relative_to(project_dir)}")
```

- [ ] **Step 4: Run medium-risk verification**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py -q
python3 -m pytest tests/test_cli.py tests/test_real_run.py tests/test_real_result_record.py tests/test_next_real_run.py -q
python3 -m ruff check src tests tools
git diff --check
```

Expected: pass.

- [ ] **Step 5: Commit Tasks 3-4 if Task 3 was not already committed**

If Task 3 already has its own commit, commit only CLI changes:

```bash
git add src/hermes_workflow/cli.py tests/test_next_real_run.py docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md
git commit -m "feat: add prepare next real run cli"
```

- [ ] **Step 6: Batched review gate for Tasks 3-4**

Run code-quality review focused on:

```text
Review C-9 Tasks 3-4 integration and CLI.

Check:
- CLI only calls C-9 package prep, not real tools
- error output matches existing CLI style
- next package can pass C-5/C-6 checks with fake returned artifacts
- record-real-result can append real_002 after fake checked result
- no local evidence files are committed
```

---

## Task 5: Docs, Progress, Final Verification

**Files:**

- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

- [ ] **Step 1: Update project overview**

In `docs/PROJECT_WORKFLOW_OVERVIEW.md`, update the current node list:

```markdown
- Plan C C-9 next real-run package contract 已完成：`hermes-workflow prepare-next-real-run` 在 C-8 已记录 checked real result 之后，按 optimizer config 的 deterministic initialization sequence 选择下一唯一候选，生成新的 C-4/C-6-compatible real-run package。C-9 不运行真实工具，不调用 C-7 adapter，不写 ledger/state，不解析 PSF，不改写公式。
```

Add CLI command to the usage section:

```bash
hermes-workflow prepare-next-real-run projects/bridge_test_inv
```

- [ ] **Step 2: Update execution progress**

Append to `docs/EXECUTION_PROGRESS_2026-05-29.md`:

```markdown
## Plan C C-9 Next Real-Run Package Contract

Status: complete and reviewed.

Implemented:

- `prepare_next_real_run()` selects the next unique candidate from the deterministic optimizer initialization sequence after C-8 records a checked real result.
- `hermes-workflow prepare-next-real-run` writes the next C-4/C-6-compatible package under `runs/real/<run_id>/`.
- C-9 deduplicates against strict ledger rows and already prepared run packages.
- C-9 validates immutable config hashes, optimizer state consistency, ledger schema, max-evaluation bounds, run-id safety, and overwrite safety.

Locked C-9 policy:

- C-9 is contract-only.
- It does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- It does not parse PSF, rewrite OCEAN formulas, write ledger/state, or add failure-penalty rows.

Verification:

- `python3 -m pytest -q`
- `python3 -m ruff check src tests tools`
- `git diff --check`

Next:

- Choose failure/retry policy or local smoke chaining C-9 -> C-7 -> C-8 on a known test cell.
```

- [ ] **Step 3: Update compact resume checkpoint**

In `docs/COMPACT_RESUME_CHECKPOINT.md`, add:

```markdown
- C-9 next real-run package contract is complete and reviewed. It adds `prepare_next_real_run()` and `hermes-workflow prepare-next-real-run`, selecting the next unique candidate from the deterministic initialization sequence after C-8 has recorded checked real results. C-9 remains contract-only and does not run real tools, call C-7, write ledger/state, parse PSF, or rewrite formulas.
```

- [ ] **Step 4: Update next development log**

In `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, update current status:

```markdown
- Plan C C-9 next real-run package contract: complete and reviewed.
- Next required action: choose failure/retry policy or local smoke chaining C-9 -> C-7 -> C-8.
```

- [ ] **Step 5: Run final verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected:

- all tests pass
- ruff clean
- no whitespace errors

- [ ] **Step 6: Commit docs/progress**

```bash
git add docs/PROJECT_WORKFLOW_OVERVIEW.md docs/EXECUTION_PROGRESS_2026-05-29.md docs/COMPACT_RESUME_CHECKPOINT.md docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md
git commit -m "docs: record next real run package progress"
```

- [ ] **Step 7: Final combined review**

Run code-quality review focused on:

```text
Final review C-9 next real-run package contract.

Check:
- design spec is implemented
- C-9 does not run real tools or call C-7
- candidate progression is deterministic and deduplicated
- package artifacts remain compatible with C-4/C-6/C-7/C-8
- optimizer state and ledger preconditions fail closed
- CLI and docs use locked role terminology
- untracked local OCEAN research/evidence files are not included
```

- [ ] **Step 8: Mark C-9 complete in this plan**

Update this plan's task checkboxes to complete and leave the final verification command outputs in the task notes.

## Self-Review

- Spec coverage: The plan covers candidate selection, run-id policy, ledger/state preconditions, package writing, CLI, tests, docs, and review gates from the C-9 design spec.
- Boundary check: No task calls Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, network access, or the C-7 adapter.
- Formula safety: C-9 only reuses `build_metric_extraction_request()` and never rewrites formulas.
- State safety: C-9 does not write ledger or optimizer state; C-8 remains the only record path after checked real results.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, or unspecified test steps.
