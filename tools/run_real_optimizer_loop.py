#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_loop import (
    ADAPTER_SUCCEEDED,
    OptimizerLoopAdapterResult,
    OptimizerLoopCycleReport,
    RECORDED,
    run_single_optimizer_cycle,
)


REPORT_PATH = "reports/optimizer_loop_report.json"
MAX_ADAPTER_ISSUE_LINES = 6
MAX_ADAPTER_ISSUE_CHARS = 500


def main(argv: Sequence[str] | None = None, *, command_runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser(
        description="Run a narrow real-tool optimizer loop using existing Hermes contracts.",
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--max-new-evaluations", type=int, default=1)
    parser.add_argument("--cadence-cshrc", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.max_new_evaluations < 1:
        print("--max-new-evaluations must be at least 1", file=sys.stderr)
        return 2

    project_dir = args.project_dir
    cycles: list[OptimizerLoopCycleReport] = []
    for index in range(1, args.max_new_evaluations + 1):
        report = run_single_optimizer_cycle(
            project_dir,
            adapter_runner=_adapter_runner(
                args.cadence_cshrc,
                command_runner=command_runner,
            ),
        )
        cycles.append(report)
        print(
            f"cycle {index}: {report.status} "
            f"candidate={report.candidate_id} run={report.run_id}"
        )
        if report.status != RECORDED:
            break

    _write_loop_report(project_dir, args.max_new_evaluations, cycles)
    return 0 if cycles and all(cycle.status == RECORDED for cycle in cycles) else 1


def _adapter_runner(cadence_cshrc: Path, *, command_runner) -> Any:
    repo = Path(__file__).resolve().parents[1]

    def run(project_dir: Path, run_id: str) -> OptimizerLoopAdapterResult:
        command = (
            f"source {shlex.quote(str(cadence_cshrc))}; "
            f"cd {shlex.quote(str(repo))}; "
            f"{shlex.quote(sys.executable)} "
            f"tools/run_spectre_ocean_adapter.py "
            f"{shlex.quote(str(project_dir))} --run-id {shlex.quote(run_id)}"
        )
        result = command_runner(
            ["csh", "-fc", command],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return OptimizerLoopAdapterResult(status=ADAPTER_SUCCEEDED)
        issues = _bounded_issue_lines(result.stdout, result.stderr)
        return OptimizerLoopAdapterResult(
            status="failed",
            issues=issues or (f"adapter exited {result.returncode}",),
        )

    return run


def _bounded_issue_lines(*streams: str | None) -> tuple[str, ...]:
    issues: list[str] = []
    for stream in streams:
        if not isinstance(stream, str):
            continue
        for line in stream.splitlines():
            text = line.strip()
            if not text:
                continue
            issues.append(text[:MAX_ADAPTER_ISSUE_CHARS])
            if len(issues) >= MAX_ADAPTER_ISSUE_LINES:
                return tuple(issues)
    return tuple(issues)


def _write_loop_report(
    project_dir: Path,
    max_new_evaluations: int,
    cycles: list[OptimizerLoopCycleReport],
) -> Path:
    payload = {
        "schema_version": "1.0",
        "max_new_evaluations": max_new_evaluations,
        "cycles": [
            {
                "status": cycle.status,
                "candidate_id": cycle.candidate_id,
                "run_id": cycle.run_id,
                "candidate_request": _relative_or_absolute(
                    project_dir,
                    cycle.candidate_request,
                ),
                "issues": list(cycle.issues),
            }
            for cycle in cycles
        ],
    }
    report_path = project_dir / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
