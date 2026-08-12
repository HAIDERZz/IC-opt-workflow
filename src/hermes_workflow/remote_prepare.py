from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import shlex
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import quote_remote_path, require_boolean_probe
from hermes_workflow.requirement_intake import (
    RequirementIntakeReport,
    RequirementPreparationReport,
    check_requirement,
    render_config_payloads,
    write_config_payloads,
)


_HISTORY_SOURCE_CONFIG_FILES = (
    "project_config.yaml",
    "variables.yaml",
    "metrics.yaml",
    "spectre.yaml",
    "optimizer.yaml",
)
_REMOTE_PREPARATION_SNAPSHOT_RELATIVE = PurePosixPath(
    "state/remote_preparation_snapshot"
)
_REMOTE_PREPARATION_SNAPSHOT_STORE_RELATIVE = PurePosixPath(
    "state/remote_preparation_snapshots"
)
_SNAPSHOT_MANIFEST_RELATIVE = Path(
    "reports/remote_preparation_snapshot.json"
)
_SNAPSHOT_COMPLETION_MARKER = Path(".complete")
REMOTE_PREPARATION_SNAPSHOT_RETENTION = 3


@dataclass(frozen=True)
class RemotePrepareResult:
    status: str
    cache_dir: Path
    issues: list[str]
    requirement_report: RequirementIntakeReport
    preparation_report: RequirementPreparationReport


def _remote_requirement_file_exists(
    runner: Any,
    remote_path: PurePosixPath | str,
) -> bool:
    probe = runner.run(f"test -f {quote_remote_path(remote_path)}")
    return require_boolean_probe(
        probe,
        profile=getattr(runner, "profile", "remote"),
        description=f"remote requirement file probe for {remote_path}",
    )


def _remote_model_file_is_readable(
    runner: Any,
    remote_path: PurePosixPath | str,
) -> bool:
    quoted_path = quote_remote_path(remote_path)
    probe = runner.run(f"test -f {quoted_path} && test -r {quoted_path}")
    return require_boolean_probe(
        probe,
        profile=getattr(runner, "profile", "remote"),
        description=f"remote model file readability probe for {remote_path}",
    )


def _memoized_remote_model_file_checker(
    runner: Any,
) -> Callable[[str], bool]:
    results: dict[str, bool] = {}

    def is_readable(path: str) -> bool:
        if path not in results:
            results[path] = _remote_model_file_is_readable(runner, path)
        return results[path]

    return is_readable


def prepare_remote_project_cache(
    ref: RemoteProjectRef,
    *,
    runner: Any,
    cache_root: Path | None = None,
    persist_snapshot: bool = False,
    frozen_snapshot: bool = False,
) -> RemotePrepareResult:
    if persist_snapshot and frozen_snapshot:
        raise ValueError(
            "persist_snapshot and frozen_snapshot are mutually exclusive"
        )
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if frozen_snapshot:
        return _restore_remote_preparation_snapshot(
            cache_dir,
            ref,
            runner,
        )

    model_file_is_readable = _memoized_remote_model_file_checker(runner)

    requirement_text = runner.read_text(ref.remote_project_dir / "opt_requirement.md")
    constraints_path = ref.remote_project_dir / "constraints.md"
    constraints_probe = runner.run(
        f"test -f {quote_remote_path(constraints_path)}"
    )
    constraints_exists = require_boolean_probe(
        constraints_probe,
        profile=getattr(runner, "profile", "remote"),
        description=f"remote constraints probe for {constraints_path}",
    )
    if constraints_exists:
        constraints_text = runner.read_text(ref.remote_project_dir / "constraints.md")
    else:
        constraints_text = None
    (cache_dir / "opt_requirement.md").write_text(requirement_text, encoding="utf-8")
    if constraints_text is not None:
        (cache_dir / "constraints.md").write_text(constraints_text, encoding="utf-8")

    report = check_requirement(
        cache_dir,
        maestro_input_exists=lambda path: _remote_requirement_file_exists(
            runner,
            path,
        ),
        model_file_is_readable=model_file_is_readable,
    )
    if report.status != "pass":
        preparation_report = RequirementPreparationReport(
            status="fail",
            issues=report.issues,
        )
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=report.issues,
            requirement_report=report,
            preparation_report=preparation_report,
        )

    config_payloads = render_config_payloads(
        report.sections,
        workflow_mode=report.workflow_mode,
    )
    try:
        history_sources = _materialize_remote_history_sources(
            cache_dir,
            ref,
            config_payloads,
            runner,
        )
    except RuntimeError as exc:
        issues = [str(exc)]
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=issues,
            requirement_report=report,
            preparation_report=RequirementPreparationReport(
                status="fail",
                issues=issues,
            ),
        )
    write_config_payloads(cache_dir, config_payloads)
    try:
        _download_remote_netlists(cache_dir, report.sections, runner)
    except RuntimeError as exc:
        issues = [str(exc)]
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=issues,
            requirement_report=report,
            preparation_report=RequirementPreparationReport(
                status="fail",
                issues=issues,
            ),
        )
    netlist_report = prepare_netlist(
        cache_dir,
        model_file_is_readable=model_file_is_readable,
    )
    if netlist_report.status.value != "pass":
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=netlist_report.issues,
            requirement_report=report,
            preparation_report=RequirementPreparationReport(
                status="fail",
                issues=netlist_report.issues,
            ),
        )
    _write_remote_preparation_snapshot(
        cache_dir,
        ref,
        history_sources=history_sources,
    )
    if persist_snapshot:
        try:
            _persist_remote_preparation_snapshot(cache_dir, ref, runner)
        except Exception as exc:
            issues = [f"failed to persist remote preparation snapshot: {exc}"]
            return RemotePrepareResult(
                status="fail",
                cache_dir=cache_dir,
                issues=issues,
                requirement_report=report,
                preparation_report=RequirementPreparationReport(
                    status="fail",
                    issues=issues,
                ),
            )
    return RemotePrepareResult(
        status="pass",
        cache_dir=cache_dir,
        issues=[],
        requirement_report=report,
        preparation_report=RequirementPreparationReport(status="pass", issues=[]),
    )


def _remote_preparation_snapshot_dir(ref: RemoteProjectRef) -> PurePosixPath:
    return ref.remote_project_dir / _REMOTE_PREPARATION_SNAPSHOT_RELATIVE


def _persist_remote_preparation_snapshot(
    cache_dir: Path,
    ref: RemoteProjectRef,
    runner: Any,
) -> None:
    manifest_path = cache_dir / _SNAPSHOT_MANIFEST_RELATIVE
    manifest_sha256 = _sha256_file(manifest_path)
    created_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_id = (
        f"{created_at}-{manifest_sha256[:16]}-{uuid.uuid4().hex}"
    )
    remote_store = (
        ref.remote_project_dir
        / _REMOTE_PREPARATION_SNAPSHOT_STORE_RELATIVE
    )
    staged_snapshot = remote_store / snapshot_id
    runner.run(
        f"mkdir -p -- {quote_remote_path(staged_snapshot)}",
        check=True,
    )
    runner.upload_tree(cache_dir, staged_snapshot)
    runner.write_text(
        staged_snapshot / _SNAPSHOT_COMPLETION_MARKER.as_posix(),
        manifest_sha256 + "\n",
    )

    canonical = _remote_preparation_snapshot_dir(ref)
    temporary_link = canonical.parent / f".{canonical.name}.{uuid.uuid4().hex}"
    relative_target = PurePosixPath(remote_store.name) / snapshot_id
    quoted_canonical = quote_remote_path(canonical)
    runner.run(
        f"ln -s {quote_remote_path(relative_target)} "
        f"{quote_remote_path(temporary_link)} && "
        f"if [ -e {quoted_canonical} ] && "
        f"[ ! -L {quoted_canonical} ]; then "
        f"rm -rf -- {quoted_canonical}; fi && "
        f"mv -Tf -- {quote_remote_path(temporary_link)} "
        f"{quoted_canonical}",
        check=True,
    )
    _prune_remote_preparation_snapshots(
        ref,
        runner,
        keep=REMOTE_PREPARATION_SNAPSHOT_RETENTION,
    )


def _prune_remote_preparation_snapshots(
    ref: RemoteProjectRef,
    runner: Any,
    *,
    keep: int,
) -> None:
    if keep < 1:
        raise ValueError("remote preparation snapshot retention must be >= 1")
    remote_store = (
        ref.remote_project_dir
        / _REMOTE_PREPARATION_SNAPSHOT_STORE_RELATIVE
    )
    canonical = _remote_preparation_snapshot_dir(ref)
    q_store = quote_remote_path(remote_store)
    q_canonical = quote_remote_path(canonical)
    script = (
        f"store={q_store}\n"
        f"current=$(readlink -e -- {q_canonical}) || exit 78\n"
        "count=0\n"
        "for candidate in \"$store\"/*; do\n"
        "  if [ -d \"$candidate\" ] && [ ! -L \"$candidate\" ]; then "
        "count=$((count + 1)); fi\n"
        "done\n"
        f"excess=$((count - {keep}))\n"
        "if [ \"$excess\" -le 0 ]; then exit 0; fi\n"
        "for candidate in \"$store\"/*; do\n"
        "  if [ \"$excess\" -le 0 ]; then break; fi\n"
        "  if [ ! -d \"$candidate\" ] || [ -L \"$candidate\" ]; then continue; fi\n"
        "  resolved=$(readlink -e -- \"$candidate\") || continue\n"
        "  if [ \"$resolved\" = \"$current\" ]; then continue; fi\n"
        "  rm -rf -- \"$candidate\" || exit 79\n"
        "  excess=$((excess - 1))\n"
        "done\n"
        "if [ \"$excess\" -ne 0 ]; then exit 79; fi\n"
    )
    runner.run(script, check=True)


def _restore_remote_preparation_snapshot(
    cache_dir: Path,
    ref: RemoteProjectRef,
    runner: Any,
) -> RemotePrepareResult:
    remote_snapshot = _remote_preparation_snapshot_dir(ref)
    probe = runner.run(f"test -d {quote_remote_path(remote_snapshot)}")
    snapshot_exists = require_boolean_probe(
        probe,
        profile=getattr(runner, "profile", "remote"),
        description=f"remote preparation snapshot probe for {remote_snapshot}",
    )
    if not snapshot_exists:
        raise RuntimeError(
            "remote preparation snapshot is missing; continuation cannot "
            f"re-read live requirement inputs: {remote_snapshot}"
        )
    try:
        runner.download_tree(remote_snapshot, cache_dir)
    except Exception as exc:
        raise RuntimeError(
            f"failed to restore remote preparation snapshot {remote_snapshot}: {exc}"
        ) from exc

    manifest_path = cache_dir / _SNAPSHOT_MANIFEST_RELATIVE
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"remote preparation snapshot manifest is missing or invalid: {exc}"
        ) from exc
    if (
        manifest.get("status") != "pass"
        or manifest.get("remote_project_dir")
        != ref.remote_project_dir.as_posix()
    ):
        raise RuntimeError(
            "remote preparation snapshot manifest does not match the remote project"
        )
    _verify_remote_preparation_snapshot(cache_dir, manifest)

    model_file_is_readable = _memoized_remote_model_file_checker(runner)

    requirement_report = check_requirement(
        cache_dir,
        maestro_input_exists=lambda _path: True,
        model_file_is_readable=model_file_is_readable,
    )
    if requirement_report.status != "pass":
        preparation_report = RequirementPreparationReport(
            status="fail",
            issues=requirement_report.issues,
        )
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=requirement_report.issues,
            requirement_report=requirement_report,
            preparation_report=preparation_report,
        )

    netlist_report = prepare_netlist(
        cache_dir,
        model_file_is_readable=model_file_is_readable,
    )
    if netlist_report.status.value != "pass":
        preparation_report = RequirementPreparationReport(
            status="fail",
            issues=netlist_report.issues,
        )
        return RemotePrepareResult(
            status="fail",
            cache_dir=cache_dir,
            issues=netlist_report.issues,
            requirement_report=requirement_report,
            preparation_report=preparation_report,
        )

    return RemotePrepareResult(
        status="pass",
        cache_dir=cache_dir,
        issues=[],
        requirement_report=requirement_report,
        preparation_report=RequirementPreparationReport(status="pass", issues=[]),
    )


def _materialize_remote_history_sources(
    cache_dir: Path,
    ref: RemoteProjectRef,
    config_payloads: dict[str, dict[str, Any]],
    runner: Any,
) -> list[dict[str, str]]:
    raw_config = config_payloads.get("history_warm_start.yaml")
    if not isinstance(raw_config, dict):
        return []
    history_config = copy.deepcopy(raw_config)
    settings = history_config.get("history_warm_start")
    if not isinstance(settings, dict) or not settings.get("enabled", False):
        config_payloads["history_warm_start.yaml"] = history_config
        return []
    sources = settings.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("history_warm_start.sources must be a list")

    materialized: list[dict[str, str]] = []
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise RuntimeError("history_warm_start source must be a mapping")
        raw_path = source.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RuntimeError("history_warm_start source path is missing")
        source_path = PurePosixPath(raw_path)
        if not source_path.is_absolute():
            source_path = ref.remote_project_dir / source_path
        remote_source = PurePosixPath(posixpath.normpath(source_path.as_posix()))
        local_relative = Path("history_sources") / f"source_{index:03d}"
        local_source = cache_dir / local_relative

        for filename in _HISTORY_SOURCE_CONFIG_FILES:
            _download_required_remote_file(
                runner,
                remote_source / "config" / filename,
                local_source / "config" / filename,
                purpose="history warm-start config",
            )
        _download_required_remote_file(
            runner,
            remote_source / "reports" / "optimizer_evaluations.jsonl",
            local_source / "reports" / "optimizer_evaluations.jsonl",
            purpose="history warm-start evaluations",
        )
        source["path"] = local_relative.as_posix()
        materialized.append(
            {
                "remote_path": remote_source.as_posix(),
                "controller_path": local_relative.as_posix(),
            }
        )

    config_payloads["history_warm_start.yaml"] = history_config
    return materialized


def _download_required_remote_file(
    runner: Any,
    remote_path: PurePosixPath,
    local_path: Path,
    *,
    purpose: str,
) -> None:
    probe = runner.run(f"test -f {quote_remote_path(remote_path)}")
    exists = require_boolean_probe(
        probe,
        profile=getattr(runner, "profile", "remote"),
        description=f"{purpose} probe for {remote_path}",
    )
    if not exists:
        raise RuntimeError(
            f"{purpose} is missing or unreadable: {remote_path} "
            "(path does not exist)"
        )
    try:
        runner.download(remote_path, local_path)
    except Exception as exc:
        raise RuntimeError(
            f"failed to materialize {purpose} {remote_path}: {exc}"
        ) from exc


def _write_remote_preparation_snapshot(
    cache_dir: Path,
    ref: RemoteProjectRef,
    *,
    history_sources: list[dict[str, str]],
) -> None:
    path = cache_dir / _SNAPSHOT_MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.1",
        "status": "pass",
        "remote_project_dir": ref.remote_project_dir.as_posix(),
        "history_sources": history_sources,
        "files": _snapshot_file_hashes(cache_dir),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _snapshot_file_hashes(cache_dir: Path) -> dict[str, str]:
    excluded = {
        _SNAPSHOT_MANIFEST_RELATIVE.as_posix(),
        _SNAPSHOT_COMPLETION_MARKER.as_posix(),
    }
    hashes: dict[str, str] = {}
    for path in sorted(cache_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(cache_dir).as_posix()
        if relative in excluded:
            continue
        hashes[relative] = _sha256_file(path)
    return hashes


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_remote_preparation_snapshot(
    cache_dir: Path,
    manifest: dict[str, Any],
) -> None:
    declared = manifest.get("files")
    if not isinstance(declared, dict) or not all(
        isinstance(path, str) and isinstance(digest, str)
        for path, digest in declared.items()
    ):
        raise RuntimeError(
            "snapshot integrity check failed: file hash manifest is missing"
        )

    manifest_path = cache_dir / _SNAPSHOT_MANIFEST_RELATIVE
    marker_path = cache_dir / _SNAPSHOT_COMPLETION_MARKER
    try:
        completion_digest = marker_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"snapshot integrity check failed: completion marker is missing: {exc}"
        ) from exc
    if completion_digest != _sha256_file(manifest_path):
        raise RuntimeError(
            "snapshot integrity check failed: completion marker does not match manifest"
        )

    actual = _snapshot_file_hashes(cache_dir)
    if actual != declared:
        declared_paths = set(declared)
        actual_paths = set(actual)
        missing = sorted(declared_paths - actual_paths)
        unexpected = sorted(actual_paths - declared_paths)
        changed = sorted(
            path
            for path in declared_paths & actual_paths
            if declared[path] != actual[path]
        )
        detail = (
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )
        raise RuntimeError(
            f"snapshot integrity check failed: {detail}"
        )


def _compute_remote_history_root(maestro_point_root: PurePosixPath) -> PurePosixPath:
    parent = maestro_point_root.parent
    if parent.name in {"1", "psf"}:
        return parent.parent
    return maestro_point_root


def _validate_remote_netlist_symlinks(
    remote_netlist: PurePosixPath,
    allowed_root: PurePosixPath,
    runner: Any,
) -> None:
    escaped_netlist = shlex.quote(str(remote_netlist))
    escaped_root = shlex.quote(str(allowed_root))
    script = (
        f"root=$(readlink -e -- {escaped_root})\n"
        "if [ -z \"$root\" ] || [ ! -d \"$root\" ]; then\n"
        "  printf 'allowed Maestro root cannot be resolved\\n'\n"
        "  exit 1\n"
        "fi\n"
        f"net=$(readlink -e -- {escaped_netlist})\n"
        "if [ -z \"$net\" ] || [ ! -d \"$net\" ]; then\n"
        "  printf 'remote netlist root cannot be resolved\\n'\n"
        "  exit 1\n"
        "fi\n"
        "case \"$net\" in\n"
        "  \"$root\"|\"$root\"/*) ;;\n"
        "  *) printf 'netlist root escapes Maestro point root: %s\\n' \"$net\"; exit 1 ;;\n"
        "esac\n"
        "validate_path() {\n"
        "  (\n"
        "    path=$1\n"
        "    ancestors=$2\n"
        "    if [ -L \"$path\" ]; then\n"
        "      resolved=$(readlink -e -- \"$path\")\n"
        "      if [ -z \"$resolved\" ]; then\n"
        "        printf 'symlink target is missing or cyclic: %s\\n' \"$path\"\n"
        "        exit 1\n"
        "      fi\n"
        "      case \"$resolved\" in\n"
        "        \"$root\"|\"$root\"/*) ;;\n"
        "        *) printf 'symlink target escapes Maestro point root: %s\\n' \"$path\"; exit 1 ;;\n"
        "      esac\n"
        "      if [ -f \"$resolved\" ]; then exit 0; fi\n"
        "      if [ -d \"$resolved\" ]; then\n"
        "        validate_dir \"$resolved\" \"$ancestors\" \"$path\"\n"
        "        exit $?\n"
        "      fi\n"
        "      printf 'symlink target is not a regular file or directory: %s\\n' \"$path\"\n"
        "      exit 1\n"
        "    fi\n"
        "    if [ -f \"$path\" ]; then exit 0; fi\n"
        "    if [ -d \"$path\" ]; then\n"
        "      validate_dir \"$path\" \"$ancestors\" \"$path\"\n"
        "      exit $?\n"
        "    fi\n"
        "    printf 'netlist entry is not a regular file or directory: %s\\n' \"$path\"\n"
        "    exit 1\n"
        "  )\n"
        "}\n"
        "validate_dir() {\n"
        "  (\n"
        "    directory=$(readlink -e -- \"$1\")\n"
        "    ancestors=$2\n"
        "    display_path=$3\n"
        "    if [ -z \"$directory\" ] || [ ! -r \"$directory\" ] || [ ! -x \"$directory\" ]; then\n"
        "      printf 'netlist directory cannot be traversed: %s\\n' \"$display_path\"\n"
        "      exit 1\n"
        "    fi\n"
        "    if ! inode=$(stat -Lc '%d:%i' -- \"$directory\"); then\n"
        "      printf 'netlist directory identity cannot be read: %s\\n' \"$display_path\"\n"
        "      exit 1\n"
        "    fi\n"
        "    case \" $ancestors \" in\n"
        "      *\" $inode \"*) printf 'symlink directory cycle detected: %s\\n' \"$display_path\"; exit 1 ;;\n"
        "    esac\n"
        "    next_ancestors=\"$ancestors $inode\"\n"
        "    status=0\n"
        "    for child in \"$directory\"/* \"$directory\"/.[!.]* \"$directory\"/..?*; do\n"
        "      if [ ! -e \"$child\" ] && [ ! -L \"$child\" ]; then continue; fi\n"
        "      validate_path \"$child\" \"$next_ancestors\" || status=1\n"
        "    done\n"
        "    exit \"$status\"\n"
        "  )\n"
        "}\n"
        "validate_dir \"$net\" '' \"$net\"\n"
    )
    result = runner.run(script)
    details = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )
    if result.return_code == 255:
        if not details:
            details = "ssh exited 255"
        raise RuntimeError(
            "remote netlist symlink validation transport failed: " + details
        )
    if result.return_code != 0:
        if not details:
            details = f"remote validation command exited {result.return_code}"
        issues = [f"  {line}" for line in details.splitlines()]
        raise RuntimeError(
            "remote netlist symlink validation failed:\n" + "\n".join(issues)
        )


def _download_remote_netlists(cache_dir: Path, sections: dict[str, object], runner: Any) -> None:
    from hermes_workflow.requirement_intake import _dict_section, _testbench_sources

    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    for index, testbench in enumerate(testbenches):
        maestro_point_root = PurePosixPath(str(testbench["maestro_point_root"]))
        remote_netlist = maestro_point_root / "netlist"
        allowed_root = _compute_remote_history_root(maestro_point_root)
        if "testbenches" in maestro:
            destination = cache_dir / "netlists" / "testbenches" / str(testbench["id"]) / "exported"
        else:
            destination = cache_dir / "netlists" / "exported"
        _validate_remote_netlist_symlinks(remote_netlist, allowed_root, runner)
        runner.download_tree(remote_netlist, destination, dereference=True)
        if index == 0 and "testbenches" in maestro:
            primary = cache_dir / "netlists" / "exported"
            _validate_remote_netlist_symlinks(remote_netlist, allowed_root, runner)
            runner.download_tree(remote_netlist, primary, dereference=True)
