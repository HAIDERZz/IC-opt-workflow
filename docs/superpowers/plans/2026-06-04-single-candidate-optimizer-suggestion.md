# Single-Candidate Optimizer Suggestion MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one narrow Hermes workflow command that suggests exactly one optimizer candidate request from existing ledger/state and hands it to the existing candidate-injection package contract.

**Architecture:** Add a focused `optimizer_suggestion.py` module that reads approved project config, checked ledger rows, optimizer state, and unresolved-run status, then atomically writes one `candidate_requests/<candidate_id>.json`. Reuse existing candidate generation, validation, and candidate package preparation boundaries instead of adding a broad optimizer framework.

**Tech Stack:** Python 3, Typer CLI, pytest, existing Hermes workflow contracts, optional local TuRBO import when available on `PYTHONPATH`.

---

## Scope Guard

This plan implements only `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md`.

Allowed:

- Add `suggest_candidate_request()` as a library function.
- Add `hermes-workflow suggest-candidate`.
- Write exactly one candidate request JSON per command invocation.
- Use initialization fallback when TuRBO is not yet usable.
- Use a narrow TuRBO one-step adapter when enough finite observations and local TuRBO imports are available.
- Verify that the suggested request can be consumed by `prepare_candidate_real_run()`.

Forbidden:

- Do not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 subprocess adapter.
- Do not add a batch optimizer loop, daemon, service, or broad optimizer framework.
- Do not create new optimizer algorithms.
- Do not parse PSF or waveform databases.
- Do not rewrite Calculator/OCEAN formulas.
- Do not mutate `config/variables.yaml`.
- Do not write `runs/real/<run_id>` from the suggestion command.
- Do not commit `docs/OCEAN_DOC_*`, `docs/toolchain_evidence/`, raw `input.scs`, protected include files, PSF/raw data, or full Cadence logs.

## File Map

- Create `src/hermes_workflow/optimizer_suggestion.py`
  - Public function: `suggest_candidate_request(project_dir, *, candidate_id=None, output_path=None, created_at_utc=None)`.
  - Dataclass result with candidate id, output path, selection mode, and parameters.
  - Internal candidate selection helpers.
  - Atomic candidate request writer.

- Modify `src/hermes_workflow/cli.py`
  - Import `suggest_candidate_request`.
  - Add `suggest-candidate PROJECT_DIR [--candidate-id ID] [--output PATH]`.

- Create `tests/test_optimizer_suggestion.py`
  - Cover happy path, safety failures, duplicate handling, CLI, and candidate-injection handoff.

- Modify `docs/CURRENT_TASK_STATE.json`
  - Point `active_plan` to this implementation plan.
  - Update task status and route audit after each completed task.

- Modify `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
  - Append compact C-13 checkpoints.

- Modify this plan
  - Check off completed steps during execution.

---

### Task 1: Library Writer With Initialization Fallback

**Risk:** Medium. This writes a new project-owned candidate request file, but does not touch real-run packages or real tools.

**Files:**

- Create: `src/hermes_workflow/optimizer_suggestion.py`
- Create: `tests/test_optimizer_suggestion.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`

- [x] **Step 1: Add failing happy-path and handoff tests**

Create `tests/test_optimizer_suggestion.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.optimizer_suggestion import suggest_candidate_request
from hermes_workflow.real_run import prepare_candidate_real_run
from tests.test_next_real_run import _create_ready_project, _load_json, _record_real_001


def test_suggest_candidate_writes_initialization_request(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000002",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    payload = _load_json(result.output_path)
    assert result.candidate_id == "candidate_000002"
    assert result.selection_mode == "initialization_fallback"
    assert payload["schema_version"] == "1.0"
    assert payload["candidate_id"] == "candidate_000002"
    assert payload["source"] == "optimizer_initialization_suggestion"
    assert payload["parameters"] != {"FN": "2", "WN": "0.3u", "FP": "2", "WP": "0.3u"}
    assert payload["metadata"]["selection_mode"] == "initialization_fallback"
    assert payload["metadata"]["evaluation_index"] == 2
    assert payload["metadata"]["ledger_rows_seen"] == 1
    assert len(payload["metadata"]["ledger_sha256"]) == 64
    assert len(payload["metadata"]["optimizer_state_sha256"]) == 64


def test_suggested_request_can_prepare_candidate_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000002",
        created_at_utc="2026-06-04T00:00:00Z",
    )
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=result.output_path,
        run_id="real_002",
        created_at_utc="2026-06-04T00:01:00Z",
    )

    assert package.run_id == "real_002"
    candidate = _load_json(project_dir / "runs" / "real" / "real_002" / "candidate.json")
    assert candidate["candidate_id"] == "candidate_000002"
    assert candidate["source"] == "explicit_candidate_request"
```

- [x] **Step 2: Run tests and confirm import failure**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py -q
```

Expected: fail because `hermes_workflow.optimizer_suggestion` does not exist.

- [x] **Step 3: Add minimal library implementation**

Create `src/hermes_workflow/optimizer_suggestion.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from hermes_workflow.mock_optimizer import generate_candidates
from hermes_workflow.real_run import (
    CandidateInjectionRequest,
    LEDGER_PATH,
    OPTIMIZER_STATE_PATH,
    _assert_candidate_is_unique,
    _assert_candidate_parameters_match_bundle,
    _assert_optimizer_state_matches_bundle,
    _parameter_key,
    _prepared_candidate_keys,
    _read_ledger_rows_or_raise,
)
from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs
from hermes_workflow.package import sha256_file
from hermes_workflow.validate import assert_valid_project


@dataclass(frozen=True)
class CandidateSuggestionResult:
    candidate_id: str
    output_path: Path
    selection_mode: str
    parameters: dict[str, str]


def suggest_candidate_request(
    project_dir: Path,
    *,
    candidate_id: str | None = None,
    output_path: Path | None = None,
    created_at_utc: str | None = None,
) -> CandidateSuggestionResult:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    assert_no_unresolved_real_runs(project_dir)
    ledger_rows = _read_ledger_rows_or_raise(project_dir)
    state = _load_optimizer_state(project_dir)
    _assert_optimizer_state_matches_bundle(bundle, state, ledger_rows)

    evaluation_index = state.current_evaluations + 1
    selected_candidate_id = candidate_id or f"candidate_{evaluation_index:06d}"
    selected_output = output_path or (
        project_dir / "candidate_requests" / f"{selected_candidate_id}.json"
    )
    if selected_output.exists():
        raise FileExistsError(f"candidate request already exists: {selected_output}")

    parameters, selection_mode, candidate_index = _select_initialization_candidate(
        bundle,
        ledger_rows,
        _prepared_candidate_keys(project_dir),
    )
    payload = {
        "schema_version": "1.0",
        "candidate_id": selected_candidate_id,
        "source": "optimizer_initialization_suggestion",
        "parameters": parameters,
        "metadata": {
            "optimizer": bundle.optimizer.optimizer.algorithm.value,
            "selection_mode": selection_mode,
            "evaluation_index": evaluation_index,
            "candidate_index": candidate_index,
            "ledger_rows_seen": len(ledger_rows),
            "optimizer_state_sha256": sha256_file(project_dir / OPTIMIZER_STATE_PATH),
            "ledger_sha256": sha256_file(project_dir / LEDGER_PATH),
        },
    }
    if created_at_utc is not None:
        payload["metadata"]["created_at_utc"] = created_at_utc
    try:
        request = CandidateInjectionRequest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"candidate request is invalid: {exc}") from exc
    _assert_candidate_parameters_match_bundle(bundle, request.parameters)
    _assert_candidate_is_unique(project_dir, request, ledger_rows)
    _write_json_atomic(selected_output, payload)
    return CandidateSuggestionResult(
        candidate_id=selected_candidate_id,
        output_path=selected_output,
        selection_mode=selection_mode,
        parameters=parameters,
    )


def _load_optimizer_state(project_dir: Path):
    from hermes_workflow.real_run import _load_optimizer_state_or_raise

    return _load_optimizer_state_or_raise(project_dir)


def _select_initialization_candidate(bundle, ledger_rows, prepared_keys):
    used_keys = {_parameter_key(row.parameters) for row in ledger_rows} | prepared_keys
    optimizer = bundle.optimizer.optimizer
    candidates = generate_candidates(
        bundle,
        n_candidates=optimizer.max_evaluations,
        seed=optimizer.random_seed,
        initialization=optimizer.initialization.value,
    )
    for index, parameters in enumerate(candidates, 1):
        if _parameter_key(parameters) not in used_keys:
            return parameters, "initialization_fallback", index
    raise ValueError("no unique candidate remains in optimizer initialization sequence")


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            raise FileExistsError(f"candidate request already exists: {path}") from None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
```

- [x] **Step 4: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py -q
```

Expected: pass.

- [x] **Step 5: Run adjacent candidate package tests**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py tests/test_next_real_run.py -q
```

Expected: pass.

- [x] **Step 6: Update task state**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's checkboxes

Set current status to Task 1 complete, `review_status` to `verified-only`, and next allowed action to C-13 Task 2.

---

### Task 2: TuRBO One-Step Suggestion And Safety Failures

**Risk:** Medium. This adds optional TuRBO-backed suggestion, but still does not run real tools or write real-run packages.

**Files:**

- Modify: `src/hermes_workflow/optimizer_suggestion.py`
- Modify: `tests/test_optimizer_suggestion.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`

- [x] **Step 1: Add failing safety tests**

Append to `tests/test_optimizer_suggestion.py`:

```python
import pytest


def test_suggest_candidate_rejects_existing_output(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    output = project_dir / "candidate_requests" / "candidate_000002.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="candidate request already exists"):
        suggest_candidate_request(project_dir, candidate_id="candidate_000002")

    assert output.read_text(encoding="utf-8") == "{}\n"


def test_suggest_candidate_rejects_missing_ledger(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)

    with pytest.raises(ValueError, match="ledger is missing"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_completed_state(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    state_path = project_dir / "state" / "optimizer_state.json"
    state = _load_json(state_path)
    state["status"] = "completed"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="optimizer state is completed"):
        suggest_candidate_request(project_dir)


def test_suggest_candidate_rejects_unresolved_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    unresolved = project_dir / "runs" / "real" / "real_002"
    unresolved.mkdir(parents=True)
    (unresolved / "real_run_manifest.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unresolved real run exists"):
        suggest_candidate_request(project_dir)
```

- [x] **Step 2: Add failing TuRBO-selection test with a fake one-step hook**

Append:

```python
def test_suggest_candidate_uses_turbo_when_enough_finite_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    ledger = project_dir / "ledger" / "experiment_ledger.jsonl"
    first_row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    rows = []
    for index in range(8):
        row = dict(first_row)
        row["candidate_id"] = f"seed_{index + 1:03d}"
        row["parameters"] = {
            "FN": str(2 + index),
            "WN": f"{0.3 + 0.2 * index:g}u",
            "FP": str(2 + index),
            "WP": f"{0.3 + 0.2 * index:g}u",
        }
        row["objective"] = float(100 - index)
        rows.append(row)
    ledger.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    state = _load_json(project_dir / "state" / "optimizer_state.json")
    state["current_evaluations"] = 8
    (project_dir / "state" / "optimizer_state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "hermes_workflow.optimizer_suggestion._suggest_turbo_raw_candidate",
        lambda *args, **kwargs: [12.0, 1.3, 2.0, 2.5],
    )

    result = suggest_candidate_request(
        project_dir,
        candidate_id="candidate_000009",
        created_at_utc="2026-06-04T00:00:00Z",
    )

    payload = _load_json(result.output_path)
    assert result.selection_mode == "turbo"
    assert payload["source"] == "optimizer_turbo_suggestion"
    assert payload["parameters"] == {"FN": "12", "WN": "1.3u", "FP": "2", "WP": "2.5u"}
    assert payload["metadata"]["selection_mode"] == "turbo"
    assert payload["metadata"]["finite_observations"] == 8
```

- [x] **Step 3: Run tests and confirm TuRBO test fails**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py -q
```

Expected: fail because `_suggest_turbo_raw_candidate` or turbo selection is not implemented.

- [x] **Step 4: Add TuRBO one-step selection**

Extend `src/hermes_workflow/optimizer_suggestion.py`:

```python
from decimal import Decimal
from typing import Sequence

from hermes_workflow.schemas import VariableKind


def _select_candidate(bundle, ledger_rows, prepared_keys):
    optimizer = bundle.optimizer.optimizer
    finite_rows = [
        row for row in ledger_rows
        if row.objective is not None and row.objective == row.objective
    ]
    min_turbo_observations = 2 * len(bundle.variables.variables)
    if (
        optimizer.algorithm.value == "turbo"
        and len(finite_rows) >= min_turbo_observations
        and _turbo_available()
    ):
        used_keys = {_parameter_key(row.parameters) for row in ledger_rows} | prepared_keys
        for raw_candidate in _turbo_candidate_stream(bundle, finite_rows, optimizer.random_seed):
            parameters = _quantize_raw_candidate(bundle, raw_candidate)
            if _parameter_key(parameters) not in used_keys:
                return parameters, "turbo", None, len(finite_rows)
    parameters, mode, candidate_index = _select_initialization_candidate(
        bundle,
        ledger_rows,
        prepared_keys,
    )
    return parameters, mode, candidate_index, len(finite_rows)


def _turbo_available() -> bool:
    try:
        import numpy  # noqa: F401
        import torch  # noqa: F401
        import gpytorch  # noqa: F401
        from turbo import Turbo1  # noqa: F401
    except Exception:
        return False
    return True


def _turbo_candidate_stream(bundle, finite_rows, seed: int):
    raw = _suggest_turbo_raw_candidate(bundle, finite_rows, seed)
    yield raw


def _suggest_turbo_raw_candidate(bundle, finite_rows, seed: int) -> Sequence[float]:
    import numpy as np
    from turbo import Turbo1
    from turbo.utils import from_unit_cube, to_unit_cube

    lb, ub = _numeric_bounds(bundle)
    x = np.array([_row_to_raw_vector(bundle, row) for row in finite_rows], dtype=float)
    fx = np.array([float(row.objective) for row in finite_rows], dtype=float)
    np.random.seed(seed + len(finite_rows))
    turbo = Turbo1(
        f=lambda value: 0.0,
        lb=lb,
        ub=ub,
        n_init=max(1, 2 * len(lb)),
        max_evals=max(2 * len(lb) + 1, len(finite_rows) + 1),
        batch_size=1,
        verbose=False,
        device="cpu",
        n_training_steps=30,
    )
    x_unit = to_unit_cube(x, lb, ub)
    x_cand, y_cand, _ = turbo._create_candidates(
        x_unit,
        fx,
        length=turbo.length_init,
        n_training_steps=30,
        hypers={},
    )
    next_unit = turbo._select_candidates(x_cand, y_cand)[0]
    next_raw = from_unit_cube(next_unit[None, :], lb, ub)[0]
    return [float(value) for value in next_raw]


def _numeric_bounds(bundle):
    import numpy as np

    lower = []
    upper = []
    for variable in bundle.variables.variables:
        if variable.kind == VariableKind.INTEGER:
            lower.append(float(variable.lower))
            upper.append(float(variable.upper))
        else:
            low, _unit = _parse_decimal_unit(variable.lower)
            high, _unit = _parse_decimal_unit(variable.upper)
            lower.append(float(low))
            upper.append(float(high))
    return np.array(lower, dtype=float), np.array(upper, dtype=float)


def _row_to_raw_vector(bundle, row) -> list[float]:
    values = []
    for variable in bundle.variables.variables:
        raw = row.parameters[variable.name]
        if variable.kind == VariableKind.INTEGER:
            values.append(float(raw))
        else:
            value, _unit = _parse_decimal_unit(raw)
            values.append(float(value))
    return values


def _quantize_raw_candidate(bundle, raw_values: Sequence[float]) -> dict[str, str]:
    parameters = {}
    for variable, raw in zip(bundle.variables.variables, raw_values, strict=True):
        if variable.kind == VariableKind.INTEGER:
            lower = int(variable.lower)
            upper = int(variable.upper)
            step = int(variable.step)
            offset = round((float(raw) - lower) / step)
            value = max(lower, min(upper, lower + offset * step))
            parameters[variable.name] = str(value)
        else:
            lower, unit = _parse_decimal_unit(variable.lower)
            upper, _ = _parse_decimal_unit(variable.upper)
            step, _ = _parse_decimal_unit(variable.step)
            raw_decimal = Decimal(str(raw))
            offset = round((raw_decimal - lower) / step)
            value = lower + Decimal(offset) * step
            value = max(lower, min(upper, value))
            parameters[variable.name] = f"{value.normalize():f}{unit}"
    return parameters


def _parse_decimal_unit(raw: str) -> tuple[Decimal, str]:
    text = str(raw)
    index = len(text)
    while index > 0 and text[index - 1].isalpha():
        index -= 1
    return Decimal(text[:index]), text[index:]
```

Update `suggest_candidate_request()` to call `_select_candidate()` instead of `_select_initialization_candidate()` and set source from selection mode:

```python
parameters, selection_mode, candidate_index, finite_observations = _select_candidate(
    bundle,
    ledger_rows,
    _prepared_candidate_keys(project_dir),
)
source = (
    "optimizer_turbo_suggestion"
    if selection_mode == "turbo"
    else "optimizer_initialization_suggestion"
)
```

Metadata must include `finite_observations`; include `candidate_index` only when it is not `None`.

- [x] **Step 5: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py -q
```

Expected: pass.

- [x] **Step 6: Run candidate-injection regression**

Run:

```bash
python3 -m pytest tests/test_candidate_injection_real_run.py tests/test_next_real_run.py -q
```

Expected: pass.

- [x] **Step 7: Update task state**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's checkboxes

Set current status to Task 2 complete, `review_status` to `verified-only`, and next allowed action to C-13 Task 3.

---

### Task 3: CLI Wiring And Local Fake Handoff Smoke

**Risk:** Medium. This exposes the user-facing command and verifies it composes with the existing package contract.

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_optimizer_suggestion.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`

- [x] **Step 1: Add failing CLI tests**

Append:

```python
from typer.testing import CliRunner

from hermes_workflow.cli import app


def test_suggest_candidate_cli_writes_request(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "suggest-candidate",
            str(project_dir),
            "--candidate-id",
            "candidate_000002",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "candidate request written:" in result.output
    request = project_dir / "candidate_requests" / "candidate_000002.json"
    assert request.exists()


def test_suggest_candidate_cli_output_can_prepare_package(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _record_real_001(project_dir)
    runner = CliRunner()
    request = project_dir / "requests" / "next.json"

    result = runner.invoke(
        app,
        [
            "suggest-candidate",
            str(project_dir),
            "--candidate-id",
            "candidate_000002",
            "--output",
            str(request),
        ],
    )

    assert result.exit_code == 0, result.output
    package = prepare_candidate_real_run(
        project_dir,
        candidate_file=request,
        run_id="real_002",
        created_at_utc="2026-06-04T00:01:00Z",
    )
    assert package.run_id == "real_002"
```

- [x] **Step 2: Run CLI tests and confirm missing command failure**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py -q
```

Expected: fail because `suggest-candidate` is not registered.

- [x] **Step 3: Add CLI command**

Modify `src/hermes_workflow/cli.py` imports:

```python
from hermes_workflow.optimizer_suggestion import suggest_candidate_request
```

Add command near real-run preparation commands:

```python
@app.command("suggest-candidate")
def suggest_candidate_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with checked optimizer ledger/state."),
    ],
    candidate_id: Annotated[
        str | None,
        typer.Option("--candidate-id", help="Optional candidate id for the request."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional candidate request output path."),
    ] = None,
) -> None:
    try:
        result = suggest_candidate_request(
            project_dir,
            candidate_id=candidate_id,
            output_path=output,
        )
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    typer.echo(f"candidate request written: {result.output_path}")
    typer.echo(f"candidate id: {result.candidate_id}")
    typer.echo(f"selection mode: {result.selection_mode}")
```

- [x] **Step 4: Run CLI and handoff tests**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py -q
```

Expected: pass.

- [x] **Step 5: Run focused CLI regression**

Run:

```bash
python3 -m pytest tests/test_cli.py tests/test_optimizer_suggestion.py -q
```

Expected: pass.

- [x] **Step 6: Update task state**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- this plan's checkboxes

Set current status to Task 3 complete, `review_status` to `verified-only`, and next allowed action to C-13 Task 4 final verification/review.

---

### Task 4: Final Verification, Review Gate, And Handoff

**Risk:** Medium. Final gate for a new file-writing CLI and optimizer boundary.

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`

- [x] **Step 1: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py -q
```

Expected: pass.

- [x] **Step 2: Run adjacent real-run and result contract regression**

Run:

```bash
python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py tests/test_metric_results.py tests/test_cli.py -q
```

Expected: pass.

- [x] **Step 3: Run lint and cadence checks**

Run:

```bash
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected:

- ruff passes.
- cadence checker passes.
- diff check passes.
- status shows only intended tracked changes plus known untracked local-only OCEAN evidence files.

- [x] **Step 4: Request one final review gate**

Use the project review path once after Tasks 1-3 are complete.

Review scope:

- `src/hermes_workflow/optimizer_suggestion.py`
- `src/hermes_workflow/cli.py`
- `tests/test_optimizer_suggestion.py`
- `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md`
- `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`

Required review questions:

- Does the implementation stay within the single-candidate suggestion scope?
- Does it avoid real-tool execution, PSF parsing, and formula rewriting?
- Does it fail closed for unresolved runs, completed optimizer state, duplicate candidates, and existing output files?
- Is the output immediately consumable by `prepare-candidate-real-run`?

- [x] **Step 5: Fix review findings surgically**

Only fix findings that are in scope for C-13. If review asks for batch orchestration, broad optimizer framework work, real-tool execution, or formula changes, record it as out of scope and defer to a separate user-approved plan.

- [x] **Step 6: Update final node records**

Update:

- `docs/CURRENT_TASK_STATE.json`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- this plan's checkboxes

Set:

- current scope: `C-13 Single-Candidate Optimizer Suggestion MVP`
- status: complete
- review status: `reviewed` only if review evidence exists; otherwise `verified-only`
- next allowed action: write C-14 real-tool acceptance plan for `suggest-candidate -> prepare-candidate-real-run -> C-7 adapter -> check/record`

- [x] **Step 7: Commit with explicit pathspecs after approval**

Only commit after verification and review status are recorded.

Use explicit pathspecs:

```bash
git add \
  src/hermes_workflow/optimizer_suggestion.py \
  src/hermes_workflow/cli.py \
  tests/test_optimizer_suggestion.py \
  docs/CURRENT_TASK_STATE.json \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/EXECUTION_PROGRESS_2026-05-29.md \
  docs/COMPACT_RESUME_CHECKPOINT.md \
  docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md \
  docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md
git commit -m "feat: add single candidate suggestion"
```

Do not stage `docs/OCEAN_DOC_*` or `docs/toolchain_evidence/`.

---

## Route Audit

- Active spec: `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md`
- Top-level plan: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: This plan productizes the next narrow optimizer step after real TuRBO practice and the completed candidate-injection package contract.
- Drift: None. Real-tool acceptance is explicitly deferred to C-14, and broad optimizer framework work remains out of scope.

## C-14 Handoff Boundary

C-14 should be the first real-tool acceptance of this feature:

```text
hermes-workflow suggest-candidate
-> hermes-workflow prepare-candidate-real-run
-> C-7 Spectre/OCEAN adapter
-> hermes-workflow check-real-run
-> hermes-workflow check-metric-results
-> hermes-workflow record-real-result
```

C-14 should use the proven `bridge_test_inv` layout and should not redesign the Maestro/ADE/Spectre/OCEAN file structure.
