from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


@dataclass(frozen=True)
class RemoteCommandResult:
    return_code: int
    stdout: str
    stderr: str
    argv: list[str]


ExecuteRemoteCommand = Callable[..., RemoteCommandResult]


def _default_execute(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout_s: int | None = None,
) -> RemoteCommandResult:
    completed = subprocess.run(
        argv,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    return RemoteCommandResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        argv=argv,
    )


def quote_remote_path(path: str | PurePosixPath) -> str:
    return shlex.quote(str(path))


class RemoteSshRunner:
    def __init__(
        self,
        profile: str,
        *,
        execute: ExecuteRemoteCommand = _default_execute,
    ) -> None:
        if not profile.strip():
            raise ValueError("ssh profile must not be empty")
        self.profile = profile
        self._execute = execute

    def run(
        self,
        command: str,
        *,
        cwd: PurePosixPath | str | None = None,
        timeout_s: int | None = None,
        input_text: str | None = None,
        check: bool = False,
    ) -> RemoteCommandResult:
        remote_command = command
        if cwd is not None:
            remote_command = f"cd {quote_remote_path(cwd)} && {command}"
        argv = ["ssh", "-o", "BatchMode=yes", self.profile, remote_command]
        result = self._execute(argv, input_text=input_text, timeout_s=timeout_s)
        if check and result.return_code != 0:
            self._raise_checked_error(result)
        return result

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        result = self.run(f"cat {quote_remote_path(remote_path)}", check=True)
        return result.stdout

    def write_text(self, remote_path: PurePosixPath | str, text: str) -> None:
        command = f"cat > {quote_remote_path(remote_path)}"
        self.run(command, input_text=text, check=True)

    def exists(self, remote_path: PurePosixPath | str) -> bool:
        result = self.run(f"test -e {quote_remote_path(remote_path)}")
        return result.return_code == 0

    def mkdir(self, remote_path: PurePosixPath | str) -> None:
        self.run(f"mkdir -p {quote_remote_path(remote_path)}", check=True)

    def download(self, remote_path: PurePosixPath | str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            f"{self.profile}:{quote_remote_path(remote_path)}",
            str(local_path),
        ]
        result = self._execute(argv, input_text=None, timeout_s=None)
        if result.return_code != 0:
            self._raise_checked_error(result)

    def upload(self, local_path: Path, remote_path: PurePosixPath | str) -> None:
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            str(local_path),
            f"{self.profile}:{quote_remote_path(remote_path)}",
        ]
        result = self._execute(argv, input_text=None, timeout_s=None)
        if result.return_code != 0:
            self._raise_checked_error(result)

    def _raise_checked_error(self, result: RemoteCommandResult) -> None:
        if result.return_code == 255:
            raise RuntimeError(
                f'SSH passwordless login failed for profile "{self.profile}". '
                f"Configure ~/.ssh/config and key-based login, then verify: "
                f"ssh {self.profile} true. stderr: {result.stderr.strip()}"
            )
        raise RuntimeError(
            "remote command failed: "
            f"return_code={result.return_code}, command={result.argv[-1]!r}, "
            f"stderr={result.stderr.strip()}"
        )
