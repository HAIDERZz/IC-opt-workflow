from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from hermes_workflow.remote_ssh import RemoteCommandResult, RemoteSshRunner


def test_remote_runner_uses_batchmode_and_profile() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="ok\n", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    result = runner.run("test -d /remote/project", timeout_s=12)

    assert result.return_code == 0
    assert calls == [
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "lab",
            "test -d /remote/project",
        ]
    ]


def test_remote_runner_wraps_cwd_with_posix_cd() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    runner.run("pwd", cwd=PurePosixPath("/tmp/a path"))

    assert calls[0][-1] == "cd '/tmp/a path' && pwd"


def test_remote_runner_check_raises_actionable_connection_error() -> None:
    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        return RemoteCommandResult(return_code=255, stdout="", stderr="Permission denied", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    try:
        runner.run("true", check=True)
    except RuntimeError as exc:
        assert 'SSH passwordless login failed for profile "lab"' in str(exc)
        assert "ssh lab true" in str(exc)
    else:
        raise AssertionError("expected connection error")


def test_remote_runner_read_text_uses_cat() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="hello", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    assert runner.read_text(PurePosixPath("/remote/opt_requirement.md")) == "hello"
    assert calls[0][-1] == "cat /remote/opt_requirement.md"


def test_remote_runner_write_text_uses_cat_with_input() -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append((argv, input_text))
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    runner.write_text(PurePosixPath("/remote/file.txt"), "hello world")

    assert calls[0][0][-1] == "cat > /remote/file.txt"
    assert calls[0][1] == "hello world"


def test_remote_runner_exists_returns_true_on_zero_exit() -> None:
    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    assert runner.exists(PurePosixPath("/remote/something")) is True


def test_remote_runner_exists_returns_false_on_nonzero_exit() -> None:
    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        return RemoteCommandResult(return_code=1, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    assert runner.exists(PurePosixPath("/remote/nope")) is False


def test_remote_runner_mkdir_uses_mkdir_p() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    runner.mkdir(PurePosixPath("/remote/new/dir"))

    assert calls[0][-1] == "mkdir -p /remote/new/dir"


def test_remote_runner_empty_profile_raises() -> None:
    with pytest.raises(ValueError, match="ssh profile must not be empty"):
        RemoteSshRunner("")


def test_remote_runner_check_raises_generic_error_for_non_255() -> None:
    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        return RemoteCommandResult(return_code=1, stdout="", stderr="bad", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    try:
        runner.run("false", check=True)
    except RuntimeError as exc:
        assert "remote command failed" in str(exc)
        assert "SSH passwordless login failed" not in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_remote_runner_download_uses_scp(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    local_path = tmp_path / "subdir" / "file.txt"
    runner.download(PurePosixPath("/remote/data.csv"), local_path)

    assert calls[0] == [
        "scp",
        "-o",
        "BatchMode=yes",
        "lab:/remote/data.csv",
        str(local_path),
    ]


def test_remote_runner_upload_uses_scp(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    local_path = tmp_path / "local.txt"
    local_path.write_text("data")
    runner.upload(local_path, PurePosixPath("/remote/upload.txt"))

    assert calls[0] == [
        "scp",
        "-o",
        "BatchMode=yes",
        str(local_path),
        "lab:/remote/upload.txt",
    ]
