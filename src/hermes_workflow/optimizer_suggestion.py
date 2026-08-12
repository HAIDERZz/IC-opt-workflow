from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Sequence

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
from hermes_workflow.schemas import VariableKind
from hermes_workflow.validate import assert_valid_project, require_optimize_bundle


@dataclass(frozen=True)
class CandidateSuggestionResult:
    candidate_id: str
    output_path: Path
    selection_mode: str
    parameters: dict[str, str]


@dataclass(frozen=True)
class _CandidateSuggestion:
    parameters: dict[str, str]
    selection_mode: str
    candidate_index: int | None
    finite_observations: int


def suggest_candidate_request(
    project_dir: Path,
    *,
    candidate_id: str | None = None,
    output_path: Path | None = None,
    created_at_utc: str | None = None,
) -> CandidateSuggestionResult:
    project_dir = Path(project_dir)
    bundle = require_optimize_bundle(
        assert_valid_project(project_dir),
        operation="candidate suggestion",
    )
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

    suggestion = _select_candidate(
        bundle,
        ledger_rows,
        _prepared_candidate_keys(project_dir),
    )
    source = (
        "optimizer_turbo_suggestion"
        if suggestion.selection_mode == "turbo"
        else "optimizer_initialization_suggestion"
    )
    metadata: dict[str, object] = {
        "optimizer": bundle.optimizer.optimizer.algorithm.value,
        "selection_mode": suggestion.selection_mode,
        "evaluation_index": evaluation_index,
        "ledger_rows_seen": len(ledger_rows),
        "finite_observations": suggestion.finite_observations,
        "optimizer_state_sha256": sha256_file(project_dir / OPTIMIZER_STATE_PATH),
        "ledger_sha256": sha256_file(project_dir / LEDGER_PATH),
    }
    if suggestion.candidate_index is not None:
        metadata["candidate_index"] = suggestion.candidate_index
    if created_at_utc is not None:
        metadata["created_at_utc"] = created_at_utc

    payload = {
        "schema_version": "1.0",
        "candidate_id": selected_candidate_id,
        "source": source,
        "parameters": suggestion.parameters,
        "metadata": metadata,
    }
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
        selection_mode=suggestion.selection_mode,
        parameters=suggestion.parameters,
    )


def _load_optimizer_state(project_dir: Path):
    from hermes_workflow.real_run import _load_optimizer_state_or_raise

    return _load_optimizer_state_or_raise(project_dir)


def _select_candidate(bundle, ledger_rows, prepared_keys) -> _CandidateSuggestion:
    finite_rows = [
        row
        for row in ledger_rows
        if row.objective is not None and math.isfinite(float(row.objective))
    ]
    min_turbo_observations = 2 * len(bundle.variables.variables)
    if (
        bundle.optimizer.optimizer.algorithm.value == "turbo"
        and len(finite_rows) >= min_turbo_observations
    ):
        used_keys = {_parameter_key(row.parameters) for row in ledger_rows} | prepared_keys
        try:
            raw_candidate = _suggest_turbo_raw_candidate(
                bundle,
                finite_rows,
                bundle.optimizer.optimizer.random_seed,
            )
        except ImportError:
            raw_candidate = None
        if raw_candidate is not None:
            parameters = _quantize_raw_candidate(bundle, raw_candidate)
            if _parameter_key(parameters) not in used_keys:
                return _CandidateSuggestion(
                    parameters=parameters,
                    selection_mode="turbo",
                    candidate_index=None,
                    finite_observations=len(finite_rows),
                )

    parameters, selection_mode, candidate_index = _select_initialization_candidate(
        bundle,
        ledger_rows,
        prepared_keys,
    )
    return _CandidateSuggestion(
        parameters=parameters,
        selection_mode=selection_mode,
        candidate_index=candidate_index,
        finite_observations=len(finite_rows),
    )


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
    parameters: dict[str, str] = {}
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
