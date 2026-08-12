"""Checksum-protected parent-manifest evidence for deleted real runs.

Run retention may remove large canonical run directories, but optimizer
acceptance and continuation still need the two small parent manifests named by
the optimizer trace.  This module owns that lifecycle behind two interfaces:
``preserve_retention_evidence`` publishes one atomic per-run bundle, and
``materialize_retention_evidence`` validates all bundles into a supplementary
artifact root with the original project-relative paths.

No PSF data, child manifests, simulator logs, or arbitrary run files cross this
seam.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Literal

from hermes_workflow.package import sha256_file
from hermes_workflow.real_run import RUN_ID_RE


STORE_RELATIVE = Path("state/run_retention_evidence")
MATERIALIZED_RELATIVE = Path(".retention_evidence_manifests")
COMBINED_RELATIVE = Path(".optimizer_supplementary_manifests")
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RetentionEvidence:
    run_id: str
    candidate_id: str | None
    bundle_path: Path
    digest: str
    canonical_paths: tuple[PurePosixPath, ...]


def preserve_retention_evidence(
    project_dir: Path,
    *,
    run_id: str,
    candidate_id: str | None,
) -> RetentionEvidence:
    """Atomically preserve a run's parent manifests before canonical deletion."""
    project_root = Path(project_dir)
    _validate_run_id(run_id)
    result_relative = PurePosixPath(
        "runs", "real", run_id, "result_manifest.json"
    )
    result_path = project_root.joinpath(*result_relative.parts)
    result_payload = _load_manifest(
        result_path,
        label="retention result manifest",
    )
    _validate_manifest_identity(
        result_payload,
        run_id=run_id,
        candidate_id=candidate_id,
        label="retention result manifest",
    )

    selected: list[tuple[PurePosixPath, Path, str]] = [
        (result_relative, result_path, "artifacts/result_manifest.json")
    ]
    raw_metric = result_payload.get("metric_result_manifest")
    if isinstance(raw_metric, str) and raw_metric:
        metric_relative = PurePosixPath(raw_metric)
        expected_metric = PurePosixPath(
            "runs",
            "real",
            run_id,
            "metrics",
            "metric_result_manifest.json",
        )
        if metric_relative != expected_metric:
            raise RuntimeError(
                "retention result manifest references a noncanonical metric "
                f"manifest: {raw_metric!r}"
            )
        metric_path = project_root.joinpath(*metric_relative.parts)
        if metric_path.is_file() and not metric_path.is_symlink():
            metric_payload = _load_manifest(
                metric_path,
                label="retention metric manifest",
            )
            _validate_manifest_identity(
                metric_payload,
                run_id=run_id,
                candidate_id=candidate_id,
                label="retention metric manifest",
            )
            selected.append(
                (
                    metric_relative,
                    metric_path,
                    "artifacts/metric_result_manifest.json",
                )
            )
        elif result_payload.get("status") == "succeeded":
            raise RuntimeError(
                "successful retention result references a missing metric "
                f"manifest: {raw_metric}"
            )

    store = project_root / STORE_RELATIVE
    store.mkdir(parents=True, exist_ok=True)
    target = store / run_id
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError(f"retention evidence target is not a directory: {target}")
    staging = store / f".{run_id}.staging-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        artifacts: list[dict[str, str]] = []
        for canonical, source, bundle_relative in selected:
            destination = staging / bundle_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            digest = sha256_file(destination)
            artifacts.append(
                {
                    "canonical_path": canonical.as_posix(),
                    "bundle_path": bundle_relative,
                    "sha256": digest,
                }
            )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "candidate_id": candidate_id,
            "artifacts": artifacts,
        }
        evidence_path = staging / "evidence.json"
        evidence_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        checksums = [
            f"{entry['sha256']}  {entry['bundle_path']}\n" for entry in artifacts
        ]
        checksums.append(f"{sha256_file(evidence_path)}  evidence.json\n")
        (staging / "checksums.sha256").write_text(
            "".join(checksums),
            encoding="utf-8",
        )
        verified = _validate_bundle(staging, expected_run_id=run_id)
        if target.exists():
            backup = store / f".{run_id}.backup-{uuid.uuid4().hex}"
            target.replace(backup)
        try:
            staging.replace(target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.replace(target)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return RetentionEvidence(
            run_id=verified.run_id,
            candidate_id=verified.candidate_id,
            bundle_path=target,
            digest=sha256_file(target / "evidence.json"),
            canonical_paths=verified.canonical_paths,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def load_retention_evidence(
    project_dir: Path,
    *,
    run_id: str,
) -> RetentionEvidence:
    """Load one evidence bundle, failing closed on any path or digest drift."""
    _validate_run_id(run_id)
    bundle = Path(project_dir) / STORE_RELATIVE / run_id
    return _validate_bundle(bundle, expected_run_id=run_id)


def materialize_retention_evidence(
    project_dir: Path,
    *,
    run_ids: Iterable[str] | None = None,
) -> Path | None:
    """Return a validated supplementary root for every preserved run bundle."""
    project_root = Path(project_dir)
    store = project_root / STORE_RELATIVE
    if not store.exists():
        return None
    if store.is_symlink() or not store.is_dir():
        raise RuntimeError(f"retention evidence store is not a directory: {store}")
    if run_ids is None:
        bundle_paths = sorted(
            path
            for path in store.iterdir()
            if not path.name.startswith(".")
        )
    else:
        selected_ids = sorted(set(run_ids))
        for run_id in selected_ids:
            _validate_run_id(run_id)
        bundle_paths = [store / run_id for run_id in selected_ids]
    if not bundle_paths:
        return None
    target = project_root / MATERIALIZED_RELATIVE
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError(
            f"retention evidence materialization target is invalid: {target}"
        )
    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        copied: dict[PurePosixPath, str] = {}
        for bundle in bundle_paths:
            evidence = _validate_bundle(bundle)
            payload = _load_evidence_payload(bundle / "evidence.json")
            for raw in payload["artifacts"]:
                canonical = PurePosixPath(raw["canonical_path"])
                digest = raw["sha256"]
                prior = copied.get(canonical)
                if prior is not None and prior != digest:
                    raise RuntimeError(
                        "conflicting retention evidence for canonical path: "
                        f"{canonical}"
                    )
                source = bundle / raw["bundle_path"]
                destination = staging.joinpath(*canonical.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                if sha256_file(destination) != digest:
                    raise RuntimeError(
                        f"retention evidence copy checksum mismatch: {canonical}"
                    )
                copied[canonical] = digest
            if evidence.run_id != bundle.name:
                raise RuntimeError(
                    f"retention evidence bundle path/run_id mismatch: {bundle}"
                )
        if target.exists():
            backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
            target.replace(backup)
        try:
            staging.replace(target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.replace(target)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def materialize_decision_bound_retention_evidence(
    project_dir: Path,
    *,
    run_ids: Iterable[str],
    action_field: Literal["local_action", "remote_action"],
    canonical_missing_only: bool,
) -> Path | None:
    """Materialize only evidence authorized by the current retention decision.

    A stale bundle from an earlier fresh attempt is inert unless the current
    decision for the same run explicitly says that the selected filesystem
    side deleted or could not find its canonical run.  Automatic local
    acceptance additionally gives a current canonical parent manifest
    priority without opening or validating an unrelated stale bundle.
    """
    project_root = Path(project_dir)
    selected: list[str] = []
    for run_id in sorted(set(run_ids)):
        _validate_run_id(run_id)
        canonical_result = (
            project_root / "runs" / "real" / run_id / "result_manifest.json"
        )
        if (
            canonical_missing_only
            and canonical_result.is_file()
            and not canonical_result.is_symlink()
        ):
            continue
        decision_path = (
            project_root / "state" / "run_retention" / f"{run_id}.json"
        )
        if not decision_path.is_file() or decision_path.is_symlink():
            continue
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"run retention decision is unavailable or invalid: {decision_path}: {exc}"
            ) from exc
        if not isinstance(decision, dict) or decision.get("run_id") != run_id:
            raise RuntimeError(
                f"run retention decision does not match {run_id}: {decision_path}"
            )
        if decision.get(action_field) not in {"deleted", "missing"}:
            continue
        evidence = load_retention_evidence(project_root, run_id=run_id)
        if decision.get("evidence_status") != "preserved":
            raise RuntimeError(
                f"retention evidence status is invalid for {run_id}"
            )
        if decision.get("evidence_digest") != evidence.digest:
            raise RuntimeError(
                f"retention evidence digest mismatch for {run_id}"
            )
        selected.append(run_id)
    return materialize_retention_evidence(project_root, run_ids=selected)


def materialize_combined_supplementary_artifacts(
    project_dir: Path,
    *,
    prior_verified_root: Path | None,
    run_ids: Iterable[str],
) -> Path | None:
    """Combine prior Remote history with current deleted-run evidence.

    Canonical runs deliberately remain outside this root and are resolved from
    the project itself.  This bundle therefore only joins two independently
    verified supplementary sources without weakening either source's checks.
    """
    project_root = Path(project_dir)
    current_evidence_root = materialize_decision_bound_retention_evidence(
        project_root,
        run_ids=run_ids,
        action_field="local_action",
        canonical_missing_only=True,
    )
    roots = tuple(
        root
        for root in (prior_verified_root, current_evidence_root)
        if root is not None
    )
    if not roots:
        return None
    if len(roots) == 1:
        return roots[0]

    target = project_root / COMBINED_RELATIVE
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError(
            f"supplementary artifact target is invalid: {target}"
        )
    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        copied: dict[PurePosixPath, str] = {}
        for root in roots:
            if root.is_symlink() or not root.is_dir():
                raise RuntimeError(
                    f"supplementary artifact root is invalid: {root}"
                )
            for source in sorted(root.rglob("*")):
                if source.is_dir() and not source.is_symlink():
                    continue
                relative = PurePosixPath(source.relative_to(root).as_posix())
                if source.is_symlink() or not source.is_file():
                    raise RuntimeError(
                        "supplementary artifact entry is not a regular file: "
                        f"{relative}"
                    )
                if not _is_parent_manifest_path(relative):
                    raise RuntimeError(
                        f"supplementary artifact path is out of scope: {relative}"
                    )
                digest = sha256_file(source)
                prior = copied.get(relative)
                if prior is not None:
                    if prior != digest:
                        raise RuntimeError(
                            "conflicting supplementary artifact: "
                            f"{relative}"
                        )
                    continue
                destination = staging.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                if sha256_file(destination) != digest:
                    raise RuntimeError(
                        "supplementary artifact copy checksum mismatch: "
                        f"{relative}"
                    )
                copied[relative] = digest
        if target.exists():
            backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
            target.replace(backup)
        try:
            staging.replace(target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.replace(target)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _validate_bundle(
    bundle: Path,
    *,
    expected_run_id: str | None = None,
) -> RetentionEvidence:
    if bundle.is_symlink() or not bundle.is_dir():
        raise RuntimeError(f"retention evidence bundle is unavailable: {bundle}")
    payload = _load_evidence_payload(bundle / "evidence.json")
    declared_files = {
        raw["bundle_path"] for raw in payload["artifacts"]
    } | {"evidence.json", "checksums.sha256"}
    actual_files: set[str] = set()
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            raise RuntimeError(
                f"retention evidence bundle contains a symbolic link: {relative}"
            )
        if path.is_dir():
            if relative != "artifacts":
                raise RuntimeError(
                    f"retention evidence bundle contains an unexpected directory: {relative}"
                )
            continue
        if not path.is_file():
            raise RuntimeError(
                f"retention evidence bundle contains a non-regular entry: {relative}"
            )
        actual_files.add(relative)
    if actual_files != declared_files:
        raise RuntimeError(
            "retention evidence bundle contents do not match its declaration: "
            f"expected={sorted(declared_files)}, actual={sorted(actual_files)}"
        )
    expected_checksums = {
        raw["bundle_path"]: raw["sha256"] for raw in payload["artifacts"]
    }
    expected_checksums["evidence.json"] = sha256_file(bundle / "evidence.json")
    actual_checksums = _load_checksum_inventory(bundle / "checksums.sha256")
    if actual_checksums != expected_checksums:
        raise RuntimeError(
            f"retention evidence checksum inventory mismatch: {bundle}"
        )
    run_id = payload["run_id"]
    try:
        _validate_run_id(run_id)
    except ValueError as exc:
        raise RuntimeError(f"retention evidence run_id is invalid: {run_id!r}") from exc
    if expected_run_id is not None and run_id != expected_run_id:
        raise RuntimeError(
            "retention evidence run_id mismatch: "
            f"expected={expected_run_id!r}, actual={run_id!r}"
        )
    if bundle.name != run_id and not bundle.name.startswith(f".{run_id}.staging-"):
        raise RuntimeError(
            f"retention evidence bundle path does not match run_id: {bundle}"
        )
    candidate_id = payload["candidate_id"]
    if candidate_id is not None and not isinstance(candidate_id, str):
        raise RuntimeError("retention evidence candidate_id must be a string or null")
    canonical_paths: list[PurePosixPath] = []
    for raw in payload["artifacts"]:
        canonical = _validated_canonical_path(raw["canonical_path"], run_id=run_id)
        bundle_relative = PurePosixPath(raw["bundle_path"])
        expected_bundle_relative = (
            PurePosixPath("artifacts/result_manifest.json")
            if canonical.name == "result_manifest.json"
            and canonical.parent.name == run_id
            else PurePosixPath("artifacts/metric_result_manifest.json")
        )
        if (
            bundle_relative.is_absolute()
            or ".." in bundle_relative.parts
            or bundle_relative != expected_bundle_relative
        ):
            raise RuntimeError(
                f"retention evidence bundle path is invalid: {bundle_relative}"
            )
        digest = raw["sha256"]
        if not _is_sha256(digest):
            raise RuntimeError("retention evidence sha256 is invalid")
        artifact = bundle.joinpath(*bundle_relative.parts)
        if artifact.is_symlink() or not artifact.is_file():
            raise RuntimeError(
                f"retention evidence artifact is not a regular file: {artifact}"
            )
        actual = sha256_file(artifact)
        if actual != digest:
            raise RuntimeError(
                "retention evidence checksum mismatch: "
                f"{canonical}: expected={digest}, actual={actual}"
            )
        manifest = _load_manifest(artifact, label="retention evidence artifact")
        _validate_manifest_identity(
            manifest,
            run_id=run_id,
            candidate_id=candidate_id,
            label="retention evidence artifact",
        )
        canonical_paths.append(canonical)
    expected_result = PurePosixPath(
        "runs", "real", run_id, "result_manifest.json"
    )
    if expected_result not in canonical_paths:
        raise RuntimeError("retention evidence is missing the parent result manifest")
    return RetentionEvidence(
        run_id=run_id,
        candidate_id=candidate_id,
        bundle_path=bundle,
        digest=sha256_file(bundle / "evidence.json"),
        canonical_paths=tuple(canonical_paths),
    )


def _load_evidence_payload(path: Path) -> dict[str, Any]:
    payload = _load_manifest(path, label="retention evidence index")
    expected_keys = {"schema_version", "run_id", "candidate_id", "artifacts"}
    if set(payload) != expected_keys or payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"retention evidence index schema is invalid: {path}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimeError("retention evidence artifacts must be a non-empty list")
    for raw in artifacts:
        if not isinstance(raw, dict) or set(raw) != {
            "canonical_path",
            "bundle_path",
            "sha256",
        }:
            raise RuntimeError("retention evidence artifact entry is invalid")
        if not all(isinstance(raw[key], str) for key in raw):
            raise RuntimeError("retention evidence artifact fields must be strings")
    return payload


def _load_checksum_inventory(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            f"retention evidence checksum inventory is unavailable: {path}"
        )
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"retention evidence checksum inventory is unreadable: {path}: {exc}"
        ) from exc
    for line_number, raw_line in enumerate(lines, start=1):
        digest, separator, relative = raw_line.partition("  ")
        if (
            separator != "  "
            or not _is_sha256(digest)
            or relative
            not in {
                "artifacts/result_manifest.json",
                "artifacts/metric_result_manifest.json",
                "evidence.json",
            }
            or relative in entries
        ):
            raise RuntimeError(
                "retention evidence checksum inventory is invalid at "
                f"line {line_number}: {raw_line!r}"
            )
        entries[relative] = digest
    return entries


def _validated_canonical_path(value: str, *, run_id: str) -> PurePosixPath:
    path = PurePosixPath(value)
    allowed = {
        PurePosixPath("runs", "real", run_id, "result_manifest.json"),
        PurePosixPath(
            "runs",
            "real",
            run_id,
            "metrics",
            "metric_result_manifest.json",
        ),
    }
    if path not in allowed:
        raise RuntimeError(f"retention evidence canonical path is invalid: {value}")
    return path


def _is_parent_manifest_path(relative: PurePosixPath) -> bool:
    parts = relative.parts
    if (
        relative.is_absolute()
        or ".." in parts
        or len(parts) not in {4, 5}
        or parts[:2] != ("runs", "real")
        or RUN_ID_RE.fullmatch(parts[2]) is None
    ):
        return False
    if len(parts) == 4:
        return parts[3] == "result_manifest.json"
    return parts[3:] == ("metrics", "metric_result_manifest.json")


def _load_manifest(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is invalid: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must contain an object: {path}")
    return payload


def _validate_manifest_identity(
    payload: dict[str, Any],
    *,
    run_id: str,
    candidate_id: str | None,
    label: str,
) -> None:
    if payload.get("run_id") != run_id:
        raise RuntimeError(f"{label} run_id does not match {run_id}")
    actual_candidate = payload.get("candidate_id")
    if candidate_id is not None and actual_candidate != candidate_id:
        raise RuntimeError(
            f"{label} candidate_id does not match {candidate_id}"
        )


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError(f"invalid retention evidence run_id: {run_id!r}")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
