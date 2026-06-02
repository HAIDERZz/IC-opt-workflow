from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from hermes_workflow.dry_run import PLACEHOLDER_RE, UNRESOLVED_PLACEHOLDER_RE
from hermes_workflow.metric_requests import build_metric_extraction_request
from hermes_workflow.mock_optimizer import generate_candidates
from hermes_workflow.package import sha256_file
from hermes_workflow.schemas import LedgerRow, OptimizerState
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
SUPERVISOR_INSTRUCTION = "supervisor_instruction.json"
EXECUTION_MANIFEST = "execution_package/execution_manifest.json"
LEDGER_PATH = "ledger/experiment_ledger.jsonl"
OPTIMIZER_STATE_PATH = "state/optimizer_state.json"
NEXT_CANDIDATE_SOURCE = "deterministic_initialization_sequence"
NEXT_SELECTION_POLICY = "next_unique_from_optimizer_initialization_sequence"
EMPTY_LEDGER_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


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
) -> RealRunPackage:
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

    rendered_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/input.scs"
    candidate_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/candidate.json"
    metric_request_relative = (
        f"{REAL_RUN_ROOT}/{selected_run_id}/metric_extraction_request.json"
    )
    rendered_path = _project_path(bundle, rendered_relative)
    candidate_path = _project_path(bundle, candidate_relative)
    metric_request_path = _project_path(bundle, metric_request_relative)

    created_run_dir = not run_dir.exists()
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
        candidate_payload=candidate,
        manifest_payload=manifest_payload,
        metric_request_payload=metric_request_payload,
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


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
