from __future__ import annotations

import shlex
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
    except RuntimeError as exc:
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=[str(exc)])
    netlist_report = prepare_netlist(cache_dir)
    if netlist_report.status.value != "pass":
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=netlist_report.issues)
    return RemotePrepareResult(status="pass", cache_dir=cache_dir, issues=[])


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
        f"root=$(readlink -f {escaped_root})\n"
        f"net=$(readlink -f {escaped_netlist})\n"
        f"bad=$(find \"$net\" -type l -exec sh -c '\n"
        f"  root=\"$1\"; shift\n"
        f"  for f; do\n"
        f"    r=$(readlink -f \"$f\") || {{ printf \"%s\\n\" \"$f\"; continue; }}\n"
        f"    if [ ! -f \"$r\" ]; then printf \"%s\\n\" \"$f\"; continue; fi\n"
        f"    case \"$r\" in\n"
        f"      \"$root\") ;;\n"
        f"      \"$root\"/*) ;;\n"
        f"      *) printf \"%s\\n\" \"$f\";;\n"
        f"    esac\n"
        f"  done\n"
        f"' _ \"$root\" {{}} +)\n"
        f"if [ -n \"$bad\" ]; then printf '%s\\n' \"$bad\"; exit 1; fi\n"
    )
    result = runner.run(script, check=True)
    if result.return_code != 0:
        details = result.stderr.strip().split("symlink validation failed:\n")
        issues = [f"  {line}" for line in (details[1] if len(details) > 1 else details[0]).strip().splitlines()]
        raise RuntimeError("remote netlist symlink validation failed:\n" + "\n".join(issues))


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
