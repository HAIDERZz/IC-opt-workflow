from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from hermes_workflow.dry_run import PLACEHOLDER_RE, UNRESOLVED_PLACEHOLDER_RE
from hermes_workflow.metric_requests import build_metric_extraction_request
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
    metric_request_path: Path
    candidate_payload: dict
    manifest_payload: dict
    metric_request_payload: dict


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

    run_dir = _project_path(bundle, f"{REAL_RUN_ROOT}/{selected_run_id}")
    manifest_path = run_dir / "real_run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"real run package already exists: {manifest_path}")

    template_relative = bundle.project_config.netlist.template_scs
    template_path = _project_path(bundle, template_relative)
    if not template_path.exists():
        raise FileNotFoundError(f"template.scs is missing: {template_relative}")

    candidate = _lower_bound_candidate(bundle, selected_run_id)
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
            created_at_utc or _utc_now(),
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
