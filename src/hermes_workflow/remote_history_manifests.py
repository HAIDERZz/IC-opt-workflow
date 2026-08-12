from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.package import sha256_file
from hermes_workflow.optimizer_trace_identity import (
    optimizer_trace_identity_issues,
)
from hermes_workflow.optimizer_trace_science import (
    DUPLICATE_SKIPPED,
    duplicate_skipped_trace_issues,
)
from hermes_workflow.real_run import RUN_ID_RE
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import quote_remote_path
from hermes_workflow.retention_evidence import (
    materialize_decision_bound_retention_evidence,
)
from hermes_workflow.validate import load_contract_bundle, require_optimize_bundle


HISTORY_MANIFEST_ROOT_RELATIVE = Path(".remote_history_manifests")
RUN_INVENTORY_RELATIVE = PurePosixPath(
    "reports/remote_run_artifacts.sha256"
)
ACCEPTANCE_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")


@dataclass(frozen=True)
class _PriorAcceptance:
    evaluation_count: int
    result_manifest_count: int
    metric_manifest_count: int


def materialize_remote_history_manifests(
    ref: RemoteProjectRef,
    cache_dir: Path,
    history_path: Path,
    runner: Any,
) -> Path:
    """Materialize checksum-verified prior parent manifests outside ``runs/``."""
    inventory_path = cache_dir.joinpath(*RUN_INVENTORY_RELATIVE.parts)
    checksums = _load_run_inventory(inventory_path) if inventory_path.is_file() else {}
    retention_root = materialize_decision_bound_retention_evidence(
        cache_dir,
        run_ids=_history_run_ids(history_path),
        action_field="remote_action",
        canonical_missing_only=False,
    )
    retention_checksums: dict[PurePosixPath, str] = {}
    if retention_root is not None:
        for path in retention_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = PurePosixPath(path.relative_to(retention_root).as_posix())
            if not _is_scoped_run_artifact(relative):
                raise RuntimeError(
                    f"retention evidence materialized an unscoped path: {relative}"
                )
            retention_checksums[relative] = sha256_file(path)
    acceptance = _load_prior_acceptance(cache_dir)
    available_checksums = dict(checksums)
    available_checksums.update(retention_checksums)
    selected = _history_parent_manifest_paths(
        history_path,
        available_checksums,
        acceptance=acceptance,
        project_dir=cache_dir,
    )
    remote_selected = tuple(
        relative for relative in selected if relative not in retention_checksums
    )

    if remote_selected:
        remote_inventory = ref.remote_project_dir / RUN_INVENTORY_RELATIVE
        command = (
            f"test -f {quote_remote_path(remote_inventory)} && "
            f"cd {quote_remote_path(ref.remote_project_dir)} && "
            "sha256sum --quiet -c -- "
            f"{quote_remote_path(RUN_INVENTORY_RELATIVE)}"
        )
        result = runner.run(
            command,
            timeout_s=getattr(runner, "transfer_timeout_s", None),
            check=True,
        )
        if getattr(result, "return_code", 0) != 0:
            raise RuntimeError(
                "remote run artifact checksum validation failed: "
                f"return_code={result.return_code}"
            )

    target = cache_dir / HISTORY_MANIFEST_ROOT_RELATIVE
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RuntimeError(
            f"historical manifest bundle target is not a directory: {target}"
        )
    staging = target.parent / f".{target.name}.verified-{uuid.uuid4().hex}"
    try:
        if remote_selected:
            runner.download_files(
                ref.remote_project_dir,
                remote_selected,
                staging,
            )
        for relative in selected:
            if relative not in retention_checksums:
                continue
            if retention_root is None:  # pragma: no cover - narrowed above.
                raise RuntimeError("retention evidence root disappeared")
            source = retention_root.joinpath(*relative.parts)
            destination = staging.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for relative in selected:
            local_path = staging.joinpath(*relative.parts)
            if local_path.is_symlink() or not local_path.is_file():
                raise RuntimeError(
                    "historical manifest bundle entry is not a regular file: "
                    f"{relative}"
                )
            actual = sha256_file(local_path)
            expected = available_checksums[relative]
            if actual != expected:
                raise RuntimeError(
                    "historical manifest checksum mismatch: "
                    f"{relative}: expected={expected}, actual={actual}"
                )
        _publish_verified_bundle(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def _history_run_ids(history_path: Path) -> tuple[str, ...]:
    """Read only syntactically valid run IDs needed for evidence selection.

    Full trace identity and count validation remains centralized in
    ``_history_parent_manifest_paths`` below.
    """
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"optimizer continuation history is unavailable: {history_path}: {exc}"
        ) from exc
    run_ids: list[str] = []
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "optimizer continuation history is invalid at "
                f"line {line_number}: {exc}"
            ) from exc
        run_id = row.get("run_id") if isinstance(row, dict) else None
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            raise RuntimeError(
                "optimizer continuation history run_id is invalid at "
                f"line {line_number}: {run_id!r}"
            )
        run_ids.append(run_id)
    if not run_ids:
        raise RuntimeError("optimizer continuation history is empty")
    return tuple(run_ids)


def _load_run_inventory(path: Path) -> dict[PurePosixPath, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"remote run checksum inventory is unavailable: {path}: {exc}"
        ) from exc
    checksums: dict[PurePosixPath, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line:
            continue
        digest, separator, raw_relative = raw_line.partition("  ")
        relative = PurePosixPath(raw_relative)
        if (
            separator != "  "
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or not _is_scoped_run_artifact(relative)
        ):
            raise RuntimeError(
                "remote run checksum inventory is invalid at "
                f"line {line_number}: {raw_line!r}"
            )
        existing = checksums.get(relative)
        if existing is not None and existing != digest:
            raise RuntimeError(
                f"conflicting remote run checksum entry: {relative}"
            )
        checksums[relative] = digest
    return checksums


def _load_prior_acceptance(cache_dir: Path) -> _PriorAcceptance:
    path = cache_dir / ACCEPTANCE_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"prior optimizer acceptance report is unavailable or invalid: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("status") != "accepted":
        raise RuntimeError("prior optimizer acceptance is not accepted")
    counts: dict[str, int] = {}
    for field in (
        "evaluation_count",
        "result_manifest_count",
        "metric_manifest_count",
    ):
        value = payload.get(field)
        minimum = 1 if field == "evaluation_count" else 0
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < minimum
        ):
            raise RuntimeError(
                f"prior optimizer acceptance {field} must be an integer >= {minimum}"
            )
        counts[field] = value
    if counts["result_manifest_count"] > counts["evaluation_count"]:
        raise RuntimeError(
            "prior optimizer acceptance result_manifest_count exceeds "
            "evaluation_count"
        )
    if counts["metric_manifest_count"] > counts["result_manifest_count"]:
        raise RuntimeError(
            "prior optimizer acceptance metric_manifest_count exceeds "
            "result_manifest_count"
        )
    return _PriorAcceptance(**counts)


def _history_parent_manifest_paths(
    history_path: Path,
    checksums: dict[PurePosixPath, str],
    *,
    acceptance: _PriorAcceptance,
    project_dir: Path,
) -> tuple[PurePosixPath, ...]:
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"optimizer continuation history is unavailable: {history_path}: {exc}"
        ) from exc
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "optimizer continuation history is invalid at "
                f"line {line_number}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise RuntimeError(
                "optimizer continuation history row must be an object at "
                f"line {line_number}"
            )
        rows.append(row)

    if not rows:
        raise RuntimeError("optimizer continuation history is empty")
    identity_issues = optimizer_trace_identity_issues(rows, is_fake=False)
    if identity_issues:
        raise RuntimeError(
            "optimizer continuation history identity is invalid: "
            + "; ".join(identity_issues)
        )
    if len(rows) != acceptance.evaluation_count:
        raise RuntimeError(
            "prior optimizer acceptance/history count mismatch: "
            f"accepted={acceptance.evaluation_count}, history={len(rows)}"
        )

    selected: set[PurePosixPath] = set()
    result_reference_count = 0
    metric_reference_count = 0
    duplicate_count = 0
    failure_penalty: float | None = None
    for line_number, row in enumerate(rows, start=1):
        run_id = row.get("run_id")
        if not isinstance(run_id, str):
            raise RuntimeError(
                "optimizer continuation history run_id validation was inconsistent"
            )
        if row.get("status") == DUPLICATE_SKIPPED:
            if failure_penalty is None:
                failure_penalty = _optimizer_failure_penalty(project_dir)
            duplicate_issues = duplicate_skipped_trace_issues(
                row,
                failure_penalty=failure_penalty,
                label=f"history line {line_number} {run_id}",
            )
            if duplicate_issues:
                raise RuntimeError(
                    "optimizer continuation duplicate trace is invalid: "
                    + "; ".join(duplicate_issues)
                )
            duplicate_count += 1
            continue
        result = _required_parent_manifest_path(
            row.get("result_manifest"),
            run_id=run_id,
            field="result_manifest",
            line_number=line_number,
        )
        selected.add(result)
        result_reference_count += 1
        raw_metric = row.get("metric_result_manifest")
        if raw_metric is not None and raw_metric != "":
            metric = _required_parent_manifest_path(
                raw_metric,
                run_id=run_id,
                field="metric_result_manifest",
                line_number=line_number,
            )
            selected.add(metric)
            metric_reference_count += 1

    if (
        result_reference_count != acceptance.result_manifest_count
        or metric_reference_count != acceptance.metric_manifest_count
        or result_reference_count + duplicate_count != acceptance.evaluation_count
    ):
        raise RuntimeError(
            "prior optimizer acceptance/manifest reference count mismatch: "
            f"accepted_evaluations={acceptance.evaluation_count}, "
            f"accepted_results={acceptance.result_manifest_count}, "
            f"history_results={result_reference_count}, "
            f"accepted_metrics={acceptance.metric_manifest_count}, "
            f"history_metrics={metric_reference_count}"
        )
    missing = sorted(selected - checksums.keys(), key=PurePosixPath.as_posix)
    if missing:
        raise RuntimeError(
            "optimizer continuation history references manifests absent from the "
            "remote checksum inventory or retention evidence: "
            + ", ".join(path.as_posix() for path in missing)
        )
    return tuple(sorted(selected, key=PurePosixPath.as_posix))


def _optimizer_failure_penalty(project_dir: Path) -> float:
    try:
        bundle = require_optimize_bundle(
            load_contract_bundle(project_dir),
            operation="optimizer continuation history",
        )
    except ValueError as exc:
        raise RuntimeError(
            f"optimizer continuation scientific contract is invalid: {exc}"
        ) from exc
    if bundle.optimizer is None:  # pragma: no cover - narrowed by contract helper.
        raise RuntimeError("optimizer continuation history lacks optimizer config")
    return bundle.optimizer.optimizer.failure_penalty


def _required_parent_manifest_path(
    value: object,
    *,
    run_id: str,
    field: str,
    line_number: int,
) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise RuntimeError(
            f"optimizer continuation history {field} is missing at "
            f"line {line_number}"
        )
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise RuntimeError(
            f"optimizer continuation history {field} is not project-relative at "
            f"line {line_number}: {value!r}"
        )
    expected_result = PurePosixPath(
        "runs", "real", run_id, "result_manifest.json"
    )
    expected_metric = PurePosixPath(
        "runs",
        "real",
        run_id,
        "metrics",
        "metric_result_manifest.json",
    )
    expected = expected_result if field == "result_manifest" else expected_metric
    if relative != expected:
        raise RuntimeError(
            f"optimizer continuation history {field} is not the parent manifest "
            f"for {run_id} at line {line_number}: {value!r}"
        )
    return relative


def _is_scoped_run_artifact(relative: PurePosixPath) -> bool:
    parts = relative.parts
    return (
        not relative.is_absolute()
        and ".." not in parts
        and len(parts) >= 4
        and parts[:2] == ("runs", "real")
        and RUN_ID_RE.fullmatch(parts[2]) is not None
    )


def _publish_verified_bundle(staging: Path, target: Path) -> None:
    backup: Path | None = None
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
