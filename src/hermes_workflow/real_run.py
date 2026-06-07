from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from hermes_workflow.dry_run import PLACEHOLDER_RE, UNRESOLVED_PLACEHOLDER_RE
from hermes_workflow.metric_requests import build_metric_extraction_request
from hermes_workflow.mock_optimizer import generate_candidates
from hermes_workflow.package import sha256_file
from hermes_workflow.schemas import LedgerRow, OptimizerState, VariableKind
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
SPECTRE_NETLIST_DIR = "netlist"
SUPERVISOR_INSTRUCTION = "supervisor_instruction.json"
EXECUTION_MANIFEST = "execution_package/execution_manifest.json"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
NEXT_CANDIDATE_SOURCE = "deterministic_initialization_sequence"
NEXT_SELECTION_POLICY = "next_unique_from_optimizer_initialization_sequence"
EMPTY_LEDGER_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SAFE_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CONTINUOUS_VALUE_RE = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s*(?P<unit>\S+))?\s*$"
)


@dataclass(frozen=True)
class RealRunPackage:
    run_id: str
    run_dir: Path
    rendered_input_scs: Path
    candidate_path: Path
    manifest_path: Path
    metric_request_path: Path
    candidate_payload: dict
    manifest_payload: dict
    metric_request_payload: dict


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


@dataclass(frozen=True)
class _CandidateSelection:
    candidate_index: int
    parameters: dict[str, str]


def prepare_real_run(
    project_dir: Path,
    *,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)

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


def prepare_next_real_run(
    project_dir: Path,
    *,
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
    ledger_rows = _read_ledger_rows_or_raise(project_dir)
    state = _load_optimizer_state_or_raise(project_dir)
    _assert_optimizer_state_matches_bundle(bundle, state, ledger_rows)
    selected_run_id = _select_next_run_id(project_dir, run_id)
    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    manifest_path = run_dir / "real_run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")
    prepared_keys = _prepared_candidate_keys(project_dir)
    selection = _select_next_candidate(bundle, ledger_rows, prepared_keys)
    candidate = _next_candidate_payload(selected_run_id, selection)
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
            "ledger_snapshot_sha256": _sha256_existing_or_empty(
                project_dir / LEDGER_PATH
            ),
            "optimizer_state_sha256": sha256_file(project_dir / OPTIMIZER_STATE_PATH),
            "previous_evaluations": len(ledger_rows),
        },
    )


def prepare_candidate_real_run(
    project_dir: Path,
    *,
    candidate_file: Path,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    candidate_file = Path(candidate_file)
    if run_id is not None:
        _validate_run_id(run_id)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)
    selected_run_id = _select_candidate_run_id(project_dir, run_id)

    from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

    assert_no_unresolved_real_runs(project_dir)
    request = _load_candidate_request(candidate_file)
    request_text = candidate_file.read_text(encoding="utf-8")
    bundle = assert_valid_project(project_dir)
    _assert_candidate_parameters_match_bundle(bundle, request.parameters)
    ledger_rows = _read_ledger_rows_or_raise(project_dir)
    state = _load_optimizer_state_or_raise(project_dir)
    _assert_optimizer_state_matches_bundle(bundle, state, ledger_rows)
    _assert_candidate_is_unique(project_dir, request, ledger_rows)
    request_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate_request.json"
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
            "candidate_request_file": request_relative,
            "candidate_request_sha256": request_sha256,
            "ledger_snapshot_sha256": _sha256_existing_or_empty(
                project_dir / LEDGER_PATH
            ),
            "optimizer_state_sha256": sha256_file(project_dir / OPTIMIZER_STATE_PATH),
            "previous_evaluations": len(ledger_rows),
        },
        candidate_request_text=request_text,
    )


def prepare_explicit_candidate_real_run(
    project_dir: Path,
    *,
    candidate_id: str,
    source: str,
    parameters: dict[str, str],
    run_id: str | None = None,
    metadata: dict[str, object] | None = None,
    created_at_utc: str | None = None,
    allow_unresolved_batch_runs: bool = False,
    allow_optimizer_continuation: bool = False,
) -> RealRunPackage:
    project_dir = Path(project_dir)
    if run_id is not None:
        _validate_run_id(run_id)
    manifest = _load_execution_manifest(project_dir)
    instruction = _load_supervisor_instruction(project_dir)
    _assert_approved(instruction)
    approved_hashes = _approved_hashes(manifest, instruction)
    _assert_config_hashes(project_dir, approved_hashes)
    selected_run_id = _select_explicit_run_id(project_dir, run_id)

    from hermes_workflow.real_run_recovery import assert_no_unresolved_real_runs

    if not allow_unresolved_batch_runs:
        assert_no_unresolved_real_runs(project_dir)
    request = CandidateInjectionRequest(
        schema_version="1.0",
        candidate_id=candidate_id,
        source=source,
        parameters=parameters,
        metadata=metadata or {},
    )
    request_text = _json_text(request.model_dump())
    bundle = assert_valid_project(project_dir)
    _assert_candidate_parameters_match_bundle(bundle, request.parameters)
    ledger_rows = _read_ledger_rows_if_present(project_dir)
    state_path = project_dir / OPTIMIZER_STATE_PATH
    if ledger_rows or state_path.exists():
        state = _load_optimizer_state_or_raise(project_dir)
        _assert_optimizer_state_matches_bundle(
            bundle,
            state,
            ledger_rows,
            allow_optimizer_continuation=allow_optimizer_continuation,
        )
    _assert_candidate_is_unique(project_dir, request, ledger_rows)
    request_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate_request.json"
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
            "selection_policy": "native_turbo_explicit_candidate",
            "candidate_request_file": request_relative,
            "candidate_request_sha256": request_sha256,
            "ledger_snapshot_sha256": _sha256_existing_or_empty(
                project_dir / LEDGER_PATH
            ),
            "optimizer_state_sha256": _sha256_existing_or_empty(
                project_dir / OPTIMIZER_STATE_PATH
            ),
            "previous_evaluations": len(ledger_rows),
        },
        candidate_request_text=request_text,
    )


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_execution_manifest(project_dir: Path) -> dict:
    return _load_json_object(project_dir / EXECUTION_MANIFEST, "execution manifest")


def _load_supervisor_instruction(project_dir: Path) -> dict:
    return _load_json_object(
        project_dir / SUPERVISOR_INSTRUCTION,
        "supervisor instruction",
    )


def _load_json_object(path: Path, label: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{label} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is invalid: expected JSON object")
    return payload


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


def _json_text(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _read_ledger_rows_if_present(project_dir: Path) -> list[LedgerRow]:
    ledger_path = project_dir / LEDGER_PATH
    if not ledger_path.exists():
        return []
    return _read_ledger_rows_or_raise(project_dir)


def _load_optimizer_state_or_raise(project_dir: Path) -> OptimizerState:
    state_path = project_dir / OPTIMIZER_STATE_PATH
    if not state_path.exists():
        raise ValueError("optimizer state is missing")
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"optimizer state is invalid JSON: {exc.msg}") from exc
    try:
        return OptimizerState.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"optimizer state is invalid: {exc}") from exc


def _assert_optimizer_state_matches_bundle(
    bundle: ContractBundle,
    state: OptimizerState,
    ledger_rows: list[LedgerRow],
    *,
    allow_optimizer_continuation: bool = False,
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
    if state.status == "stopped":
        raise ValueError(f"optimizer state is {state.status}")
    if state.status == "completed" and not allow_optimizer_continuation:
        raise ValueError(f"optimizer state is {state.status}")
    if state.current_evaluations != len(ledger_rows):
        raise ValueError(
            "optimizer state current_evaluations disagrees with ledger row count"
        )
    if (
        state.current_evaluations >= optimizer.max_evaluations
        and not allow_optimizer_continuation
    ):
        raise ValueError("optimizer maximum evaluations have already been reached")


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
            _assert_integer_candidate(
                variable.name,
                raw_value,
                variable.lower,
                variable.upper,
                variable.step,
            )
        elif variable.kind == VariableKind.CONTINUOUS_STEP:
            _assert_continuous_candidate(
                variable.name,
                raw_value,
                variable.lower,
                variable.upper,
                variable.step,
            )
        else:
            raise ValueError(f"{variable.name} kind is unsupported: {variable.kind}")


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
    if raw != raw.strip():
        raise ValueError("value must use compact Spectre-safe formatting")
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
        if "compact Spectre-safe formatting" in str(exc):
            raise ValueError(
                f"{name} must use compact Spectre-safe formatting"
            ) from exc
        if "attached unit suffix" in str(exc):
            raise ValueError(
                f"{name} must use a Spectre-safe attached unit suffix"
            ) from exc
        raise ValueError(
            f"{name} must be numeric with an optional unit suffix"
        ) from exc
    lower, lower_unit = _parse_continuous_candidate(lower_raw)
    upper, upper_unit = _parse_continuous_candidate(upper_raw)
    step, step_unit = _parse_continuous_candidate(step_raw)
    if len({value_unit, lower_unit, upper_unit, step_unit}) != 1:
        raise ValueError(f"{name} unit suffix must match variables.yaml")
    if value < lower or value > upper:
        raise ValueError(f"{name} is outside approved bounds")
    if step <= 0 or (value - lower) % step != 0:
        raise ValueError(f"{name} is not aligned to approved step")


def _next_unused_run_id(project_dir: Path) -> str:
    root = project_dir / REAL_RUN_ROOT
    used: set[int] = {1}
    if root.exists():
        for child in root.iterdir():
            if not RUN_ID_RE.match(child.name):
                continue
            _assert_run_dir_is_not_symlink(child)
            if not child.is_dir():
                continue
            used.add(int(child.name.removeprefix("real_")))

    next_id = 2
    while next_id in used:
        next_id += 1
    return f"real_{next_id:03d}"


def _select_candidate_run_id(project_dir: Path, run_id: str | None) -> str:
    if run_id is None:
        return _next_unused_run_id(project_dir)
    selected = _validate_run_id(run_id)
    if selected == DEFAULT_RUN_ID:
        raise ValueError("prepare-candidate-real-run cannot target real_001")
    run_dir = project_dir / REAL_RUN_ROOT / selected
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError(f"candidate real run directory already exists: {run_dir}")
    return selected


def _select_explicit_run_id(project_dir: Path, run_id: str | None) -> str:
    if run_id is None:
        root = project_dir / REAL_RUN_ROOT
        next_id = 1
        while (root / f"real_{next_id:03d}").exists():
            next_id += 1
        return f"real_{next_id:03d}"
    selected = _validate_run_id(run_id)
    run_dir = project_dir / REAL_RUN_ROOT / selected
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError(f"explicit real run directory already exists: {run_dir}")
    return selected


def _select_next_run_id(project_dir: Path, run_id: str | None) -> str:
    if run_id is None:
        return _next_unused_run_id(project_dir)
    selected = _validate_run_id(run_id)
    if selected == DEFAULT_RUN_ID:
        raise ValueError("prepare-next-real-run cannot target real_001")
    return selected


def _parameter_key(parameters: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(parameters.items()))


def _prepared_candidate_ids(project_dir: Path) -> set[str]:
    root = project_dir / REAL_RUN_ROOT
    ids: set[str] = set()
    if not root.exists():
        return ids
    for run_dir in sorted(root.iterdir()):
        if not RUN_ID_RE.match(run_dir.name):
            continue
        _assert_run_dir_is_not_symlink(run_dir)
        if not run_dir.is_dir():
            continue
        candidate_path = run_dir / "candidate.json"
        if not candidate_path.exists():
            continue
        payload = _load_json_object(candidate_path, "prepared candidate")
        candidate_id = payload.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise ValueError(f"prepared candidate is invalid: {candidate_path}")
        ids.add(candidate_id)
    return ids


def _prepared_candidate_keys(project_dir: Path) -> set[tuple[tuple[str, str], ...]]:
    root = project_dir / REAL_RUN_ROOT
    keys: set[tuple[tuple[str, str], ...]] = set()
    if not root.exists():
        return keys
    for run_dir in sorted(root.iterdir()):
        if not RUN_ID_RE.match(run_dir.name):
            continue
        _assert_run_dir_is_not_symlink(run_dir)
        if not run_dir.is_dir():
            continue
        candidate_path = run_dir / "candidate.json"
        if not candidate_path.exists():
            continue
        payload = _load_json_object(candidate_path, "prepared candidate")
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise ValueError(f"prepared candidate is invalid: {candidate_path}")
        keys.add(_parameter_key(parameters))
    return keys


def _assert_candidate_is_unique(
    project_dir: Path,
    request: CandidateInjectionRequest,
    ledger_rows: list[LedgerRow],
) -> None:
    request_key = _parameter_key(request.parameters)
    for row in ledger_rows:
        if row.candidate_id == request.candidate_id:
            raise ValueError(
                f"ledger already contains candidate_id {request.candidate_id}"
            )
        if _parameter_key(row.parameters) == request_key:
            raise ValueError("ledger already contains candidate parameters")
    if request.candidate_id in _prepared_candidate_ids(project_dir):
        raise ValueError(
            f"prepared run already contains candidate_id {request.candidate_id}"
        )
    if request_key in _prepared_candidate_keys(project_dir):
        raise ValueError("prepared run already contains candidate parameters")


def _select_next_candidate(
    bundle: ContractBundle,
    ledger_rows: list[LedgerRow],
    prepared_keys: set[tuple[tuple[str, str], ...]],
) -> _CandidateSelection:
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


def _sha256_existing_or_empty(path: Path) -> str:
    if not path.exists():
        return EMPTY_LEDGER_SHA256
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_run_dir_is_not_symlink(run_dir: Path) -> None:
    if run_dir.is_symlink():
        raise FileExistsError(f"real run directory must not be a symlink: {run_dir}")


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
        raise ValueError(
            f"real-run path must be project-relative and safe: {relative_path}"
        )
    return bundle.project_dir / Path(*path.parts)


def _lower_bound_candidate(bundle: ContractBundle, run_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "candidate_id": run_id,
        "source": "lower_bound_first_real_run",
        "parameters": {
            variable.name: variable.lower for variable in bundle.variables.variables
        },
    }


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
    _assert_real_run_parent_dirs_are_not_symlinks(bundle.project_dir)
    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    _assert_run_dir_is_not_symlink(run_dir)
    manifest_path = run_dir / "real_run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"real run directory is not empty: {run_dir}")

    template_relative = bundle.project_config.netlist.template_scs
    template_path = _project_path(bundle, template_relative)
    if not template_path.exists():
        raise FileNotFoundError(f"template.scs is missing: {template_relative}")

    rendered_relative = (
        f"{REAL_RUN_ROOT}/{selected_run_id}/{SPECTRE_NETLIST_DIR}/input.scs"
    )
    candidate_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate.json"
    candidate_request_relative = (
        f"{REAL_RUN_ROOT}/{selected_run_id}/candidate_request.json"
        if candidate_request_text is not None
        else None
    )
    metric_request_relative = (
        f"{REAL_RUN_ROOT}/{selected_run_id}/metric_extraction_request.json"
    )
    rendered_path = _project_path(bundle, rendered_relative)
    candidate_path = _project_path(bundle, candidate_relative)
    candidate_request_path = (
        _project_path(bundle, candidate_request_relative)
        if candidate_request_relative is not None
        else None
    )
    metric_request_path = _project_path(bundle, metric_request_relative)

    created_run_dir = not run_dir.exists()
    candidate_for_write = dict(candidate)
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        netlist_dir = run_dir / SPECTRE_NETLIST_DIR
        netlist_dir.mkdir(parents=True, exist_ok=True)
        _copy_exported_netlist_bundle(bundle, netlist_dir)
        rendered_text = (
            rendered_text_override
            if rendered_text_override is not None
            else _render_template(
                template_path.read_text(encoding="utf-8"),
                candidate["parameters"],
            )
        )
        rendered_path.write_text(rendered_text, encoding="utf-8")
        if candidate_request_path is not None and candidate_request_text is not None:
            candidate_request_path.write_text(
                candidate_request_text,
                encoding="utf-8",
            )
            candidate_for_write["candidate_request_file"] = candidate_request_relative
            candidate_for_write["candidate_request_sha256"] = sha256_file(
                candidate_request_path
            )
        candidate_path.write_text(_json_text(candidate_for_write), encoding="utf-8")
        candidate_id = str(candidate_for_write["candidate_id"])
        metric_request_payload = build_metric_extraction_request(
            bundle,
            run_id=selected_run_id,
            candidate_id=candidate_id,
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
        manifest_payload.update(manifest_extra)
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_multi_testbench_real_run_packages(
            bundle,
            selected_run_id,
            candidate,
            candidate_id,
            created_at_utc,
            instruction,
            approved_hashes,
            candidate_relative,
            manifest_extra,
        )
    except Exception:
        if created_run_dir and run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        raise

    return RealRunPackage(
        run_id=selected_run_id,
        run_dir=run_dir,
        rendered_input_scs=rendered_path,
        candidate_path=candidate_path,
        manifest_path=manifest_path,
        metric_request_path=metric_request_path,
        candidate_payload=candidate_for_write,
        manifest_payload=manifest_payload,
        metric_request_payload=metric_request_payload,
    )


def _copy_exported_netlist_bundle(bundle: ContractBundle, run_dir: Path) -> None:
    _copy_exported_netlist_bundle_from_relative(
        bundle,
        bundle.project_config.netlist.exported_input_scs,
        run_dir,
    )


def _copy_exported_netlist_bundle_from_relative(
    bundle: ContractBundle,
    exported_input_relative: str,
    run_dir: Path,
) -> None:
    exported_input = _project_path(
        bundle,
        exported_input_relative,
    )
    exported_root = exported_input.parent
    if exported_root.is_symlink():
        raise FileExistsError(
            f"exported netlist bundle must not contain symlinks: {exported_root}"
        )
    if not exported_root.exists():
        return

    for source in sorted(exported_root.rglob("*")):
        if source.is_symlink():
            raise FileExistsError(
                f"exported netlist bundle must not contain symlinks: {source}"
            )
        relative = source.relative_to(exported_root)
        destination = run_dir / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not source.is_file():
            raise ValueError(f"exported netlist bundle file is not regular: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _write_multi_testbench_real_run_packages(
    bundle: ContractBundle,
    selected_run_id: str,
    candidate: dict,
    candidate_id: str,
    created_at_utc: str,
    instruction: dict,
    approved_hashes: dict[str, str],
    candidate_relative: str,
    manifest_extra: dict,
) -> None:
    if bundle.testbenches is None:
        return

    for testbench in bundle.testbenches.testbenches:
        testbench_id = testbench.id
        child_prefix = f"{REAL_RUN_ROOT}/{selected_run_id}/testbenches/{testbench_id}"
        template_relative = f"netlists/testbenches/{testbench_id}/templates/template.scs"
        exported_input_relative = f"netlists/testbenches/{testbench_id}/exported/input.scs"
        rendered_relative = f"{child_prefix}/{SPECTRE_NETLIST_DIR}/input.scs"
        metric_request_relative = f"{child_prefix}/metric_extraction_request.json"

        template_path = _project_path(bundle, template_relative)
        if not template_path.exists():
            raise FileNotFoundError(f"template.scs is missing: {template_relative}")

        child_dir = _project_path(bundle, child_prefix)
        child_netlist_dir = child_dir / SPECTRE_NETLIST_DIR
        child_netlist_dir.mkdir(parents=True, exist_ok=True)
        _copy_exported_netlist_bundle_from_relative(
            bundle,
            exported_input_relative,
            child_netlist_dir,
        )

        rendered_path = _project_path(bundle, rendered_relative)
        rendered_path.write_text(
            _render_template(
                template_path.read_text(encoding="utf-8"),
                candidate["parameters"],
            ),
            encoding="utf-8",
        )
        metrics_subset = [
            metric for metric in bundle.metrics.metrics if metric.testbench == testbench_id
        ]
        metric_request_path = _project_path(bundle, metric_request_relative)
        metric_request_payload = build_metric_extraction_request(
            bundle,
            run_id=selected_run_id,
            candidate_id=candidate_id,
            prepared_input_scs=rendered_relative,
            prepared_input_sha256=sha256_file(rendered_path),
            run_prefix=child_prefix,
            metrics_subset=metrics_subset,
        )
        metric_request_path.write_text(
            json.dumps(metric_request_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        child_manifest = _build_manifest(
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
        child_manifest.update(manifest_extra)
        child_manifest["testbench_id"] = testbench_id
        (child_dir / "real_run_manifest.json").write_text(
            json.dumps(child_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _render_template(template_text: str, candidate: dict[str, str]) -> str:
    approved_names = set(candidate)
    placeholder_values = sorted(
        name for name, value in candidate.items() if UNRESOLVED_PLACEHOLDER_RE.search(value)
    )
    if placeholder_values:
        raise ValueError(
            "candidate parameter values must not contain placeholders: "
            + ", ".join(placeholder_values)
        )

    seen_names = {match.group("name") for match in PLACEHOLDER_RE.finditer(template_text)}
    unexpected = sorted(seen_names - approved_names)
    missing = sorted(approved_names - seen_names)
    if missing:
        raise ValueError(
            "template is missing placeholders for approved variables: "
            + ", ".join(missing)
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
        raise ValueError(
            "rendered real-run deck still contains unresolved placeholders: "
            + ", ".join(unresolved)
        )
    return rendered


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
        "metric_extraction_request": metric_request_relative,
        "metric_extraction_request_sha256": sha256_file(metric_request_path),
        "candidate_id": candidate_id,
        "candidate_source": "lower_bound_first_real_run",
        "approved_config_hashes": approved_hashes,
        "template_sha256": sha256_file(template_path),
        "rendered_input_sha256": sha256_file(rendered_path),
        "spectre": {
            "engine": spectre.engine,
            "preset": spectre.preset.value,
            "output_format": spectre.output_format,
            "threads_per_run": spectre.threads_per_run,
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


def _assert_real_run_parent_dirs_are_not_symlinks(project_dir: Path) -> None:
    for relative_path in ("runs", REAL_RUN_ROOT):
        path = project_dir / Path(*PurePosixPath(relative_path).parts)
        if path.is_symlink():
            raise FileExistsError(
                f"real run parent directory must not be a symlink: {path}"
            )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
