from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import quote_remote_path
from hermes_workflow.requirement_intake import (
    render_config_payloads,
    write_config_payloads,
    parse_requirement_text,
)


@dataclass(frozen=True)
class RemotePrepareResult:
    status: str
    cache_dir: Path
    issues: list[str]


def prepare_remote_project_cache(
    ref: RemoteProjectRef,
    *,
    runner: Any,
    cache_root: Path | None = None,
) -> RemotePrepareResult:
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    requirement_text = runner.read_text(ref.remote_project_dir / "opt_requirement.md")
    try:
        constraints_text = runner.read_text(ref.remote_project_dir / "constraints.md")
    except Exception:
        constraints_text = None
    (cache_dir / "opt_requirement.md").write_text(requirement_text, encoding="utf-8")
    if constraints_text is not None:
        (cache_dir / "constraints.md").write_text(constraints_text, encoding="utf-8")

    report = parse_requirement_text(
        requirement_text,
        constraints_text=constraints_text,
        maestro_input_exists=lambda path: runner.run(f"test -f {quote_remote_path(path)}").return_code == 0,
    )
    if report.status != "pass":
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=report.issues)

    write_config_payloads(cache_dir, render_config_payloads(report.sections))
    try:
        _download_remote_netlists(cache_dir, report.sections, runner)
    except FileExistsError as exc:
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=[str(exc)])
    netlist_report = prepare_netlist(cache_dir)
    if netlist_report.status.value != "pass":
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=netlist_report.issues)
    return RemotePrepareResult(status="pass", cache_dir=cache_dir, issues=[])


def _download_remote_netlists(cache_dir: Path, sections: dict[str, object], runner: Any) -> None:
    from hermes_workflow.requirement_intake import _dict_section, _testbench_sources

    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    for index, testbench in enumerate(testbenches):
        remote_netlist = PurePosixPath(str(testbench["maestro_point_root"])) / "netlist"
        if "testbenches" in maestro:
            destination = cache_dir / "netlists" / "testbenches" / str(testbench["id"]) / "exported"
        else:
            destination = cache_dir / "netlists" / "exported"
        runner.download_tree(remote_netlist, destination)
        _materialize_downloaded_symlinks(destination)
        if index == 0 and "testbenches" in maestro:
            primary = cache_dir / "netlists" / "exported"
            runner.download_tree(remote_netlist, primary)
            _materialize_downloaded_symlinks(primary)


def _materialize_downloaded_symlinks(directory: Path) -> None:
    """Replace symlinks in a downloaded netlist directory with regular file copies.

    Raises ``FileExistsError`` if any symlink target escapes *directory* or is
    not a regular file.  This mirrors the safety contract of
    ``requirement_intake._collect_import_entries`` for local Maestro imports.
    """
    resolved_dir = directory.resolve()
    for path in sorted(directory.rglob("*")):
        if not path.is_symlink():
            continue
        target = path.resolve(strict=False)
        try:
            target.relative_to(resolved_dir)
        except ValueError:
            raise FileExistsError(
                f"downloaded netlist symlink target escapes directory: "
                f"{path.relative_to(directory)} -> {target}"
            )
        if not target.is_file():
            raise FileExistsError(
                f"downloaded netlist symlink target is not a regular file: "
                f"{path.relative_to(directory)} -> {target}"
            )
        path.unlink()
        shutil.copy2(target, path)
