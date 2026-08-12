from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

import pytest

from hermes_workflow.remote_attempt_lock import (
    RemoteAttemptLockedError,
    acquire_remote_attempt_lock,
)
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult


class LocalShellRunner:
    profile = "local-shell"

    def run(
        self,
        command: str,
        *,
        input_text: str | None = None,
        **_: object,
    ) -> RemoteCommandResult:
        completed = subprocess.run(
            ["/bin/sh", "-c", command],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        return RemoteCommandResult(
            completed.returncode,
            completed.stdout,
            completed.stderr,
            ["/bin/sh", "-c", command],
        )

    def read_text(self, path: PurePosixPath | str) -> str:
        return Path(path).read_text(encoding="utf-8")


def test_remote_attempt_lock_excludes_second_controller_and_releases(
    tmp_path,
) -> None:
    runner = LocalShellRunner()
    ref = RemoteProjectRef("local-shell", PurePosixPath(tmp_path.as_posix()))

    first = acquire_remote_attempt_lock(ref, runner=runner)
    with pytest.raises(RemoteAttemptLockedError, match="already has an active"):
        acquire_remote_attempt_lock(ref, runner=runner)

    first.release()
    replacement = acquire_remote_attempt_lock(ref, runner=runner)
    replacement.release()

    assert not (tmp_path / "state" / "remote_attempt.lock").exists()


def test_remote_attempt_lock_context_releases_after_failure(tmp_path) -> None:
    runner = LocalShellRunner()
    ref = RemoteProjectRef("local-shell", PurePosixPath(tmp_path.as_posix()))

    with pytest.raises(ValueError, match="synthetic"):
        with acquire_remote_attempt_lock(ref, runner=runner):
            raise ValueError("synthetic")

    with acquire_remote_attempt_lock(ref, runner=runner):
        assert (tmp_path / "state" / "remote_attempt.lock").is_dir()


def test_remote_attempt_lock_refuses_to_release_another_owner(tmp_path) -> None:
    runner = LocalShellRunner()
    ref = RemoteProjectRef("local-shell", PurePosixPath(tmp_path.as_posix()))
    lease = acquire_remote_attempt_lock(ref, runner=runner)
    token_path = tmp_path / "state" / "remote_attempt.lock" / "token"
    token_path.write_text("different-owner\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="return_code=76"):
        lease.release()

    assert token_path.is_file()
