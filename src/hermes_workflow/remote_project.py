from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DEFAULT_REMOTE_CACHE_ROOT = Path("~/.ic-opt/remote_runs")


@dataclass(frozen=True)
class RemoteProjectRef:
    ssh_profile: str
    remote_project_dir: PurePosixPath

    def __post_init__(self) -> None:
        if not self.ssh_profile.strip():
            raise ValueError("ssh profile must not be empty")
        if not self.remote_project_dir.is_absolute():
            raise ValueError("remote project path must be absolute")

    @property
    def remote_reports_dir(self) -> PurePosixPath:
        return self.remote_project_dir / "reports"

    @property
    def remote_doctor_report(self) -> PurePosixPath:
        return self.remote_reports_dir / "ic_opt_doctor_report.json"


def remote_cache_dir(
    ref: RemoteProjectRef,
    *,
    cache_root: Path | None = None,
) -> Path:
    root = (cache_root or DEFAULT_REMOTE_CACHE_ROOT).expanduser()
    digest = hashlib.sha256(
        f"{ref.ssh_profile}\n{ref.remote_project_dir.as_posix()}".encode("utf-8")
    ).hexdigest()[:16]
    return root / ref.ssh_profile / digest
