from __future__ import annotations

import subprocess
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


# --- download_tree / upload_tree tests ---


class FakeCompletedProcess:
    """Minimal subprocess.CompletedProcess stand-in for monkeypatching."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakePipe:
    """Fake pipe object with close() for Popen stdout/stderr."""

    def __init__(self, content: bytes = b"") -> None:
        self._content = content
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def read(self) -> bytes:
        return self._content


class FakePopen:
    """Records argv and returns a controllable process for monkeypatching."""

    def __init__(
        self,
        argv: list[str],
        *,
        stdout: int | None = None,
        stderr: int | None = None,
        stdin: int | None = None,
        returncode: int = 0,
        stderr_content: bytes = b"",
    ) -> None:
        self.argv = argv
        self.stdout: FakePipe | None = FakePipe() if stdout is not None else None
        self.stderr: FakePipe | None = FakePipe(stderr_content) if stderr is not None else None
        self.stdin = stdin
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode

    def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")

    def close(self) -> None:
        pass


def test_download_tree_uses_ssh_tar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list[tuple[list[str], dict]] = []
    run_calls: list[tuple[list[str], dict]] = []

    def capturing_popen(argv, **kw):
        popen_calls.append((argv, kw))
        instance = FakePopen.__new__(FakePopen)
        instance.argv = argv
        instance.stdout = FakePipe() if kw.get("stdout") is not None else None
        instance.stderr = FakePipe() if kw.get("stderr") is not None else None
        instance.stdin = kw.get("stdin")
        instance.returncode = 0
        return instance

    monkeypatch.setattr(subprocess, "Popen", capturing_popen)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: (run_calls.append((argv, kw)) or FakeCompletedProcess()),
    )

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "downloaded"
    runner.download_tree(PurePosixPath("/remote/project/data"), local_path)

    # Verify local directory was created
    assert local_path.exists()

    # Verify remote command: tar -C <remote_path> -cf - .
    assert len(popen_calls) == 1
    ssh_argv = popen_calls[0][0]
    assert ssh_argv[:4] == ["ssh", "-o", "BatchMode=yes", "lab"]
    remote_cmd = ssh_argv[4]
    assert remote_cmd == "tar -C /remote/project/data -cf - ."

    # Verify local tar extraction command: tar -C <local_path> -xf -
    assert len(run_calls) == 1
    local_tar_argv = run_calls[0][0]
    assert local_tar_argv == ["tar", "-C", str(local_path), "-xf", "-"]


def _make_fake_popen(popen_calls: list, returncode: int = 0, stderr_content: bytes = b""):
    """Return a factory that creates FakePopen instances and records calls."""

    def factory(argv, **kw):
        popen_calls.append((argv, kw))
        instance = FakePopen.__new__(FakePopen)
        instance.argv = argv
        instance.stdout = FakePipe() if kw.get("stdout") is not None else None
        instance.stderr = FakePipe(stderr_content) if kw.get("stderr") is not None else None
        instance.stdin = kw.get("stdin")
        instance.returncode = returncode
        return instance

    return factory


def test_download_tree_creates_local_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "deep" / "nested" / "dir"
    runner.download_tree(PurePosixPath("/remote/data"), local_path)

    assert local_path.exists()


def test_download_tree_with_exclude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "downloaded"
    runner.download_tree(PurePosixPath("/remote/project"), local_path, exclude="*.log")

    ssh_argv = popen_calls[0][0]
    remote_cmd = ssh_argv[4]
    assert "--exclude" in remote_cmd
    assert "*.log" in remote_cmd


def test_download_tree_include_raises_not_supported(tmp_path: Path) -> None:
    runner = RemoteSshRunner("lab", execute=lambda *a, **kw: RemoteCommandResult(0, "", "", []))

    with pytest.raises(ValueError, match="include is not supported for tree transfer yet"):
        runner.download_tree(PurePosixPath("/remote/project"), tmp_path / "out", include="*.py")


def test_download_tree_raises_on_ssh_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls, returncode=1, stderr_content=b"Permission denied"))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    with pytest.raises(RuntimeError, match="remote tar download failed.*Permission denied"):
        runner.download_tree(PurePosixPath("/remote/data"), tmp_path / "out")


def test_download_tree_raises_on_local_tar_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: FakeCompletedProcess(returncode=1, stderr=b"tar error"),
    )

    runner = RemoteSshRunner("lab")

    with pytest.raises(RuntimeError, match="local tar extraction failed"):
        runner.download_tree(PurePosixPath("/remote/data"), tmp_path / "out")


def test_download_tree_quotes_paths_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "out"
    runner.download_tree(PurePosixPath("/remote/my project/data"), local_path)

    ssh_argv = popen_calls[0][0]
    remote_cmd = ssh_argv[4]
    assert remote_cmd == "tar -C '/remote/my project/data' -cf - ."


def test_upload_tree_uses_ssh_tar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    run_calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (run_calls.append(argv) or FakeCompletedProcess()))

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "upload_data"
    local_path.mkdir()
    (local_path / "file.txt").write_text("content")
    runner.upload_tree(local_path, PurePosixPath("/remote/dest"))

    # Should call run() first for remote mkdir -p
    assert len(run_calls) == 1
    mkdir_argv = run_calls[0]
    assert mkdir_argv[:4] == ["ssh", "-o", "BatchMode=yes", "lab"]
    assert "mkdir -p /remote/dest" in mkdir_argv[4]

    # Should have two Popen calls: local tar + SSH
    assert len(popen_calls) == 2

    # First call: local tar -C <local_path> -cf - .
    local_tar_argv = popen_calls[0][0]
    assert local_tar_argv == ["tar", "-C", str(local_path), "-cf", "-", "."]

    # Second call: SSH with remote tar -C <remote_path> -xf -
    ssh_argv = popen_calls[1][0]
    assert ssh_argv[:4] == ["ssh", "-o", "BatchMode=yes", "lab"]
    remote_cmd = ssh_argv[4]
    assert remote_cmd == "tar -C /remote/dest -xf -"


def test_upload_tree_with_exclude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "upload_data"
    local_path.mkdir()
    runner.upload_tree(local_path, PurePosixPath("/remote/dest"), exclude="*.tmp")

    # Local tar command should include --exclude
    local_tar_argv = popen_calls[0][0]
    assert "--exclude" in local_tar_argv
    assert "*.tmp" in local_tar_argv


def test_upload_tree_include_raises_not_supported(tmp_path: Path) -> None:
    runner = RemoteSshRunner("lab", execute=lambda *a, **kw: RemoteCommandResult(0, "", "", []))

    local_path = tmp_path / "upload_data"
    local_path.mkdir()

    with pytest.raises(ValueError, match="include is not supported for tree transfer yet"):
        runner.upload_tree(local_path, PurePosixPath("/remote/dest"), include="*.py")


def test_upload_tree_raises_on_mkdir_failure(tmp_path: Path) -> None:
    def fake_execute(argv, **kw):
        return RemoteCommandResult(return_code=1, stdout="", stderr="permission denied", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    local_path = tmp_path / "upload_data"
    local_path.mkdir()

    with pytest.raises(RuntimeError, match="remote command failed"):
        runner.upload_tree(local_path, PurePosixPath("/remote/dest"))


def test_upload_tree_raises_on_ssh_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = [0]

    def factory(argv, **kw):
        instance = FakePopen.__new__(FakePopen)
        instance.argv = argv
        instance.stdout = FakePipe() if kw.get("stdout") is not None else None
        instance.stderr = FakePipe(b"Connection refused") if kw.get("stderr") is not None else None
        instance.stdin = kw.get("stdin")
        call_count[0] += 1
        instance.returncode = 1 if call_count[0] == 2 else 0
        return instance

    monkeypatch.setattr(subprocess, "Popen", factory)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "upload_data"
    local_path.mkdir()

    with pytest.raises(RuntimeError, match="remote tar upload failed.*Connection refused"):
        runner.upload_tree(local_path, PurePosixPath("/remote/dest"))


def test_upload_tree_raises_on_local_tar_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = [0]

    def factory(argv, **kw):
        instance = FakePopen.__new__(FakePopen)
        instance.argv = argv
        instance.stdout = FakePipe() if kw.get("stdout") is not None else None
        instance.stderr = FakePipe() if kw.get("stderr") is not None else None
        instance.stdin = kw.get("stdin")
        call_count[0] += 1
        instance.returncode = 1 if call_count[0] == 1 else 0
        return instance

    monkeypatch.setattr(subprocess, "Popen", factory)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: FakeCompletedProcess())

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "upload_data"
    local_path.mkdir()

    with pytest.raises(RuntimeError, match="local tar creation failed"):
        runner.upload_tree(local_path, PurePosixPath("/remote/dest"))


def test_upload_tree_quotes_remote_paths_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list = []
    run_calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", _make_fake_popen(popen_calls))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (run_calls.append(argv) or FakeCompletedProcess()))

    runner = RemoteSshRunner("lab")

    local_path = tmp_path / "upload_data"
    local_path.mkdir()
    runner.upload_tree(local_path, PurePosixPath("/remote/my dest/data"))

    # mkdir -p should quote the remote path
    mkdir_cmd = run_calls[0][4]
    assert "mkdir -p '/remote/my dest/data'" in mkdir_cmd

    # remote tar should quote the remote path
    ssh_argv = popen_calls[1][0]
    remote_cmd = ssh_argv[4]
    assert remote_cmd == "tar -C '/remote/my dest/data' -xf -"
