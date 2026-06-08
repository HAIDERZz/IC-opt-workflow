from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath

from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult


VALID_REQUIREMENT = (
    Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1")
)


class FakeRunner:
    profile = "lab"

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.writes: dict[str, str] = {}

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if command == "true":
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -d /remote/project" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -w /remote/project" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/project/cadence_env.csh" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/maestro/point_1/netlist/input.scs" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "which spectre" in command and "which ocean" in command:
            return RemoteCommandResult(
                0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command]
            )
        if "mkdir -p /remote/project/reports" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(1, "", "unexpected command", ["ssh", "lab", command])

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return VALID_REQUIREMENT
        if path == "/remote/project/constraints.md":
            return ""
        raise FileNotFoundError(path)

    def write_text(self, remote_path: PurePosixPath | str, text: str) -> None:
        self.writes[str(remote_path)] = text

    def mkdir(self, remote_path: PurePosixPath | str) -> None:
        self.run(f"mkdir -p {remote_path}")


def test_remote_doctor_writes_remote_and_local_reports(tmp_path: Path) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert report.remote_report_path == "/remote/project/reports/ic_opt_doctor_report.json"
    assert "/remote/project/reports/ic_opt_doctor_report.json" in runner.writes
    assert (report.local_report_path).is_file()
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["checks"]["ssh"]["status"] == "pass"
    assert payload["checks"]["spectre_ocean"]["status"] == "pass"


def test_remote_doctor_fails_before_optimizer_when_ssh_is_not_ready(
    tmp_path: Path,
) -> None:
    class FailingSshRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            if command == "true":
                return RemoteCommandResult(
                    255, "", "Permission denied", ["ssh", "lab", command]
                )
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=FailingSshRunner(), cache_root=tmp_path)

    assert report.status == "fail"
    assert report.checks["ssh"]["status"] == "fail"
    assert "ssh lab true" in report.checks["ssh"]["message"]


def test_remote_doctor_csh_payload_quotes_cshrc_path(tmp_path: Path) -> None:
    cshrc = PurePosixPath("/remote/project/my cadence env.csh")

    class SpacePathRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            self.commands.append(command)
            if command == "true":
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "test -d" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "test -w" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if f"test -f {shlex.quote(str(cshrc))}" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "which spectre" in command and "which ocean" in command:
                return RemoteCommandResult(
                    0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command]
                )
            if "mkdir -p" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            return RemoteCommandResult(1, "", "unexpected command", ["ssh", "lab", command])

    runner = SpacePathRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    run_remote_doctor(ref, runner=runner, cadence_cshrc=cshrc, cache_root=tmp_path)

    csh_commands = [c for c in runner.commands if c.startswith("csh -fc")]
    assert len(csh_commands) == 1
    assert shlex.quote(str(cshrc)) in csh_commands[0]
