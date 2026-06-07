from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from hermes_workflow.execution_agent_handoff import dispatch_execution_agent


def _write_task(project_dir: Path) -> None:
    execution_dir = project_dir / "execution_package"
    execution_dir.mkdir(parents=True)
    (execution_dir / "OPTIMIZER_EXECUTION_TASK.md").write_text(
        "# Optimizer Execution Agent Task\n\n## Command\n\n```bash\nhermes-workflow run-openbox-real PROJECT\n```\n",
        encoding="utf-8",
    )
    (execution_dir / "optimizer_execution_manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )


def test_dispatch_execution_agent_writes_success_report(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_task(project_dir)
    calls: list[dict[str, object]] = []

    def fake_runner(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0, stdout="execution ok\n", stderr="")

    report = dispatch_execution_agent(
        project_dir,
        execution_agent="claude",
        runner=fake_runner,
        repo_dir=tmp_path,
    )

    assert report.status == "pass"
    assert report.returncode == 0
    assert report.transcript_path.exists()
    assert "execution ok" in report.transcript_path.read_text(encoding="utf-8")
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["execution_agent"] == "claude"
    assert payload["task_path"] == "execution_package/OPTIMIZER_EXECUTION_TASK.md"
    assert payload["manifest_path"] == "execution_package/optimizer_execution_manifest.json"
    assert payload["transcript_path"] == "reports/execution_agent_handoff_transcript.txt"
    assert payload["issues"] == []
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["command"][:3] == ["claude", "-p", "--dangerously-skip-permissions"]
    assert "Do not run /ic-opt recursively" in calls[0]["command"][3]


def test_dispatch_execution_agent_writes_failure_report(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_task(project_dir)

    def fake_runner(_command, **_kwargs):
        return SimpleNamespace(returncode=7, stdout="", stderr="tool failed\n")

    report = dispatch_execution_agent(
        project_dir,
        execution_agent="claude",
        runner=fake_runner,
        repo_dir=tmp_path,
    )

    assert report.status == "fail"
    assert report.returncode == 7
    assert "execution agent exited with code 7" in report.issues
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["issues"] == ["execution agent exited with code 7"]
    assert "tool failed" in report.transcript_path.read_text(encoding="utf-8")


def test_dispatch_execution_agent_rejects_unknown_agent(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_task(project_dir)

    try:
        dispatch_execution_agent(project_dir, execution_agent="other", repo_dir=tmp_path)
    except ValueError as exc:
        assert "execution_agent must be direct or claude" in str(exc)
    else:
        raise AssertionError("expected ValueError")
