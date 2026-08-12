from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import (
    quote_remote_path,
    raise_for_remote_result,
)


REMOTE_ATTEMPT_LOCK_RELATIVE = PurePosixPath("state/remote_attempt.lock")
_LOCK_OCCUPIED_EXIT = 73


class RemoteAttemptLockedError(RuntimeError):
    """Another Controller owns the Remote project attempt lock."""


@dataclass
class RemoteAttemptLease:
    runner: Any
    lock_dir: PurePosixPath
    token: str
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        token_path = self.lock_dir / "token"
        command = (
            f"if [ ! -d {quote_remote_path(self.lock_dir)} ]; then exit 0; fi; "
            f"if [ ! -f {quote_remote_path(token_path)} ]; then exit 75; fi; "
            f"owner=$(cat {quote_remote_path(token_path)}) || exit 75; "
            f"if [ \"$owner\" != {quote_remote_path(self.token)} ]; then exit 76; fi; "
            f"rm -rf -- {quote_remote_path(self.lock_dir)}"
        )
        result = self.runner.run(command)
        raise_for_remote_result(
            result,
            profile=getattr(self.runner, "profile", "remote"),
            description=f"remote attempt lock release for {self.lock_dir}",
        )
        self.released = True

    def __enter__(self) -> RemoteAttemptLease:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


def acquire_remote_attempt_lock(
    ref: RemoteProjectRef,
    *,
    runner: Any,
) -> RemoteAttemptLease:
    """Atomically claim one Remote project for one Controller attempt.

    Locks are deliberately never stolen automatically. If a Controller dies,
    the owner metadata tells the operator what to inspect before manually
    removing the lock directory.
    """
    lock_dir = ref.remote_project_dir / REMOTE_ATTEMPT_LOCK_RELATIVE
    token = uuid.uuid4().hex
    metadata = {
        "schema_version": "1.0",
        "token": token,
        "controller_host": socket.gethostname(),
        "controller_pid": os.getpid(),
        "ssh_profile": ref.ssh_profile,
        "remote_project_dir": ref.remote_project_dir.as_posix(),
        "acquired_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    token_path = lock_dir / "token"
    owner_path = lock_dir / "owner.json"
    command = (
        f"mkdir -p -- {quote_remote_path(lock_dir.parent)} || exit 74; "
        f"if mkdir -- {quote_remote_path(lock_dir)} 2>/dev/null; then "
        f"if printf '%s\\n' {quote_remote_path(token)} > "
        f"{quote_remote_path(token_path)} && cat > "
        f"{quote_remote_path(owner_path)}; then exit 0; fi; "
        f"rm -rf -- {quote_remote_path(lock_dir)}; exit 75; fi; "
        f"if [ -d {quote_remote_path(lock_dir)} ]; then exit "
        f"{_LOCK_OCCUPIED_EXIT}; fi; exit 74"
    )
    result = runner.run(
        command,
        input_text=json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )
    if result.return_code == _LOCK_OCCUPIED_EXIT:
        owner = "owner metadata unavailable"
        try:
            owner = runner.read_text(owner_path).strip()
        except Exception:
            pass
        raise RemoteAttemptLockedError(
            "remote project already has an active optimization attempt: "
            f"{lock_dir}. Inspect {owner_path} before manually removing a "
            f"stale lock. Owner: {owner}"
        )
    raise_for_remote_result(
        result,
        profile=getattr(runner, "profile", ref.ssh_profile),
        description=f"remote attempt lock acquisition for {lock_dir}",
    )
    return RemoteAttemptLease(runner=runner, lock_dir=lock_dir, token=token)
