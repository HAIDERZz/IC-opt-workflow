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
