from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir


def test_remote_project_ref_rejects_relative_remote_path() -> None:
    try:
        RemoteProjectRef(ssh_profile="lab", remote_project_dir=PurePosixPath("relative/project"))
    except ValueError as exc:
        assert "remote project path must be absolute" in str(exc)
    else:
        raise AssertionError("expected relative path rejection")


@pytest.mark.parametrize(
    "profile",
    ["../outside", "/absolute", ".", "..", "a/b", "-ProxyCommand=bad"],
)
def test_remote_project_ref_rejects_unsafe_cache_path_profile(profile: str) -> None:
    with pytest.raises(ValueError, match="single path component"):
        RemoteProjectRef(
            ssh_profile=profile,
            remote_project_dir=PurePosixPath("/remote/project"),
        )


def test_remote_project_cache_path_is_stable_and_profile_scoped(tmp_path: Path) -> None:
    ref = RemoteProjectRef(
        ssh_profile="lab",
        remote_project_dir=PurePosixPath("/home/user/spectre_opt_prj/Mixer"),
    )

    first = remote_cache_dir(ref, cache_root=tmp_path)
    second = remote_cache_dir(ref, cache_root=tmp_path)

    assert first == second
    assert first.parent == tmp_path / "lab"
    assert len(first.name) == 16


def test_remote_project_ref_report_paths_are_posix() -> None:
    ref = RemoteProjectRef(
        ssh_profile="lab",
        remote_project_dir=PurePosixPath("/remote/project"),
    )

    assert ref.remote_reports_dir == PurePosixPath("/remote/project/reports")
    assert ref.remote_doctor_report == PurePosixPath("/remote/project/reports/ic_opt_doctor_report.json")
