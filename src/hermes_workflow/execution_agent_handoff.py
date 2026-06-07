from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

TASK_RELATIVE = Path("execution_package/OPTIMIZER_EXECUTION_TASK.md")
MANIFEST_RELATIVE = Path("execution_package/optimizer_execution_manifest.json")
REPORT_RELATIVE = Path("reports/execution_agent_handoff_report.json")
TRANSCRIPT_RELATIVE = Path("reports/execution_agent_handoff_transcript.txt")

Runner = Callable[..., Any]


@dataclass(frozen=True)
class ExecutionAgentHandoffReport:
    status: str
    project_dir: str
    execution_agent: str
    task_path: Path
    manifest_path: Path
    command: list[str]
    transcript_path: Path
    report_path: Path
    returncode: int | None
    started_at_utc: str
    finished_at_utc: str
    issues: list[str] = field(default_factory=list)


def dispatch_execution_agent(
    project_dir: str | Path,
    *,
    execution_agent: str,
    runner: Runner | None = None,
    repo_dir: Path | None = None,
) -> ExecutionAgentHandoffReport:
    project_root = Path(project_dir).resolve()
    agent = execution_agent.strip().lower()
    if agent not in {"direct", "claude"}:
        raise ValueError("execution_agent must be direct or claude")
    if agent == "direct":
        raise ValueError("direct execution does not use execution-agent handoff")

    task_path = project_root / TASK_RELATIVE
    manifest_path = project_root / MANIFEST_RELATIVE
    _require_file(task_path, "optimizer execution task")
    _require_file(manifest_path, "optimizer execution manifest")

    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = project_root / TRANSCRIPT_RELATIVE
    report_path = project_root / REPORT_RELATIVE
    root = repo_dir or _repo_root()

    prompt = _claude_execution_prompt(project_root, task_path, manifest_path, root)
    command = ["claude", "-p", "--dangerously-skip-permissions", prompt]
    env = _execution_env(root)
    started_at = _utc_now()
    run = runner or subprocess.run
    completed = run(
        command,
        cwd=root,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    finished_at = _utc_now()
    returncode = int(getattr(completed, "returncode", 1))
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    issues = [] if returncode == 0 else [f"execution agent exited with code {returncode}"]
    transcript_path.write_text(
        _transcript(command, stdout=stdout, stderr=stderr),
        encoding="utf-8",
    )
    report = ExecutionAgentHandoffReport(
        status="pass" if returncode == 0 else "fail",
        project_dir=str(project_root),
        execution_agent=agent,
        task_path=task_path,
        manifest_path=manifest_path,
        command=command[:3] + ["<prompt>"],
        transcript_path=transcript_path,
        report_path=report_path,
        returncode=returncode,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        issues=issues,
    )
    _write_report(project_root, report)
    return report


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _execution_env(repo_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    venv_bin = repo_dir / ".venv" / "bin"
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    env.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "ic_auto_opt_mplconfig"),
    )
    return env


def _claude_execution_prompt(project_root: Path, task_path: Path, manifest_path: Path, repo: Path) -> str:
    return f"""You are the independent execution agent for ic-auto-opt-workflow.

Project directory:
{project_root}

Workflow repository:
{repo}

Read these files before executing:
- {task_path}
- {manifest_path}

Execute the optimizer task package exactly:
1. cd {repo}
2. Put {repo / ".venv" / "bin"} first in PATH.
3. Run the Command section from {task_path}.
4. Run the Audit Commands section from {task_path}.

Hard boundaries:
- Do not run /ic-opt recursively.
- Do not ask the user for formulas, variables, or settings.
- Do not hand-pick candidate points.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not change Spectre precision, threads_per_run, or parallel_jobs.
- Do not create a per-project virtualenv.

When finished, report only command status, audit status, and report paths.
"""


def _transcript(command: list[str], *, stdout: str, stderr: str) -> str:
    return "\n".join(
        [
            "# Execution Agent Transcript",
            "",
            "## Command",
            "",
            "```text",
            " ".join(command[:3] + ["<prompt>"]),
            "```",
            "",
            "## STDOUT",
            "",
            "```text",
            stdout.rstrip(),
            "```",
            "",
            "## STDERR",
            "",
            "```text",
            stderr.rstrip(),
            "```",
            "",
        ]
    )


def _write_report(project_root: Path, report: ExecutionAgentHandoffReport) -> None:
    payload = asdict(report)
    payload["schema_version"] = "1.0"
    payload["task_path"] = _relative(project_root, report.task_path)
    payload["manifest_path"] = _relative(project_root, report.manifest_path)
    payload["transcript_path"] = _relative(project_root, report.transcript_path)
    payload["report_path"] = _relative(project_root, report.report_path)
    report.report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
