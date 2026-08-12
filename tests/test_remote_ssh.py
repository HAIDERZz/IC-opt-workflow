from __future__ import annotations

import subprocess
import shutil
from pathlib import Path, PurePosixPath

import pytest

from hermes_workflow.remote_ssh import (
    BinaryCommandResult,
    RemoteCommandResult,
    RemoteCommandTimeoutError,
    RemoteCommandUnavailableError,
    RemoteSshRunner,
    RemoteTransportError,
)


class RecordingTextExecutor:
    def __init__(self, return_code: int = 0, stderr: str = "") -> None:
        self.return_code = return_code
        self.stderr = stderr
        self.calls: list[tuple[list[str], str | None, int | None]] = []

    def __call__(
        self,
        argv: list[str],
        *,
        input_text: str | None,
        timeout_s: int | None,
    ) -> RemoteCommandResult:
        self.calls.append((argv, input_text, timeout_s))
        if argv[0] == "scp" and self.return_code == 0:
            destination = Path(argv[-1])
            if ":" not in argv[-1]:
                destination.write_text("downloaded", encoding="utf-8")
        return RemoteCommandResult(
            self.return_code,
            "ok\n" if self.return_code == 0 else "",
            self.stderr,
            argv,
        )


class RecordingBinaryExecutor:
    def __init__(
        self,
        results: list[tuple[int, bytes]] | None = None,
        *,
        timeout_on_call: int | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], int | None]] = []
        self.results = list(results or [])
        self.timeout_on_call = timeout_on_call

    def __call__(
        self,
        argv: list[str],
        *,
        input_file: object | None,
        output_file: object | None,
        timeout_s: int | None,
    ) -> BinaryCommandResult:
        self.calls.append((argv, timeout_s))
        if self.timeout_on_call == len(self.calls):
            raise subprocess.TimeoutExpired(argv, timeout_s)
        return_code, stderr = self.results.pop(0) if self.results else (0, b"")
        return BinaryCommandResult(return_code, b"", stderr, argv)


def _local_text_execute(
    argv: list[str],
    *,
    input_text: str | None,
    timeout_s: int | None,
) -> RemoteCommandResult:
    command = ["/bin/sh", "-c", argv[4]] if argv[0] == "ssh" else argv
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    return RemoteCommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
        argv,
    )


def _local_binary_execute(
    argv: list[str],
    *,
    input_file: object | None,
    output_file: object | None,
    timeout_s: int | None,
) -> BinaryCommandResult:
    command = ["/bin/sh", "-c", argv[4]] if argv[0] == "ssh" else argv
    completed = subprocess.run(
        command,
        stdin=input_file,
        stdout=output_file if output_file is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    return BinaryCommandResult(
        completed.returncode,
        completed.stdout or b"" if output_file is None else b"",
        completed.stderr or b"",
        argv,
    )


def _success_text(
    argv: list[str],
    *,
    input_text: str | None,
    timeout_s: int | None,
) -> RemoteCommandResult:
    return RemoteCommandResult(0, "", "", argv)


def test_remote_runner_uses_batchmode_profile_and_explicit_posix_shell() -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner("lab", execute=execute)

    result = runner.run("test -d /remote/project", timeout_s=12)

    assert result.return_code == 0
    assert execute.calls == [
        (
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "lab",
                "exec /bin/sh -c 'test -d /remote/project'",
            ],
            None,
            12,
        )
    ]


def test_remote_runner_bootstrap_probe_uses_login_shell_without_bin_sh() -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner("lab", execute=execute)

    runner.run_login_shell("test -x /bin/sh", timeout_s=8)

    assert execute.calls == [
        (
            ["ssh", "-o", "BatchMode=yes", "lab", "test -x /bin/sh"],
            None,
            8,
        )
    ]


def test_remote_runner_quotes_cwd_inside_explicit_posix_shell() -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner("lab", execute=execute)

    runner.run("pwd", cwd=PurePosixPath("/tmp/a path"))

    command = execute.calls[0][0][-1]
    assert command.startswith("exec /bin/sh -c ")
    assert "tmp/a path" in command
    assert command.endswith(" && pwd'")


def test_explicit_posix_shell_payload_runs_under_csh_login_shell() -> None:
    if shutil.which("csh") is None:
        pytest.skip("csh is not installed")
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner("lab", execute=execute)
    runner.run("if test -n ok; then printf 'posix-shell\\n'; fi")

    wrapped = execute.calls[0][0][-1]
    completed = subprocess.run(
        ["csh", "-fc", wrapped],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "posix-shell\n"


def test_remote_runner_check_classifies_connection_error() -> None:
    runner = RemoteSshRunner(
        "lab",
        execute=RecordingTextExecutor(255, "Permission denied"),
    )

    with pytest.raises(RemoteTransportError) as exc_info:
        runner.run("true", check=True)

    assert 'SSH passwordless login failed for profile "lab"' in str(exc_info.value)
    assert "ssh lab true" in str(exc_info.value)


@pytest.mark.parametrize("return_code", [126, 127])
def test_remote_runner_check_classifies_unavailable_command(
    return_code: int,
) -> None:
    runner = RemoteSshRunner(
        "lab",
        execute=RecordingTextExecutor(return_code, "not found"),
    )

    with pytest.raises(RemoteCommandUnavailableError, match="unavailable"):
        runner.run("missing-tool", check=True)


def test_remote_runner_read_write_and_mkdir_use_explicit_shell() -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner("lab", execute=execute)

    assert runner.read_text(PurePosixPath("/remote/file.txt")) == "ok\n"
    runner.write_text(PurePosixPath("/remote/file.txt"), "hello")
    runner.mkdir(PurePosixPath("/remote/new/dir"))

    assert execute.calls[0][0][-1] == "exec /bin/sh -c 'cat /remote/file.txt'"
    assert execute.calls[1][1] == "hello"
    assert "cat > /remote/.file.txt.upload-" in execute.calls[1][0][-1]
    assert "mv -f --" in execute.calls[1][0][-1]
    assert execute.calls[2][0][-1] == (
        "exec /bin/sh -c 'mkdir -p /remote/new/dir'"
    )


@pytest.mark.parametrize(
    ("return_code", "expected"),
    [
        (0, True),
        (1, False),
        (255, RemoteTransportError),
        (126, RemoteCommandUnavailableError),
        (127, RemoteCommandUnavailableError),
    ],
)
def test_remote_runner_path_probe_classifies_exit_codes(
    return_code: int,
    expected: bool | type[RuntimeError],
) -> None:
    runner = RemoteSshRunner(
        "lab",
        execute=RecordingTextExecutor(return_code, "probe failed"),
    )

    if isinstance(expected, bool):
        assert runner.exists(PurePosixPath("/remote/item")) is expected
    else:
        with pytest.raises(expected, match="remote path probe"):
            runner.exists(PurePosixPath("/remote/item"))


def test_remote_runner_validates_profile_and_timeout() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RemoteSshRunner("")
    with pytest.raises(ValueError, match="must not start"):
        RemoteSshRunner("-ProxyCommand=bad")
    with pytest.raises(ValueError, match="must be >= 1"):
        RemoteSshRunner("lab", transfer_timeout_s=0)


def test_download_uses_timeout_and_atomic_local_publish(tmp_path: Path) -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner(
        "lab",
        execute=execute,
        transfer_timeout_s=17,
    )
    target = tmp_path / "subdir" / "file.txt"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")

    runner.download(PurePosixPath("/remote/data.csv"), target)

    argv, _, timeout = execute.calls[0]
    assert argv[:4] == ["scp", "-o", "BatchMode=yes", "lab:/remote/data.csv"]
    assert Path(argv[4]).name.startswith(".file.txt.download-")
    assert timeout == 17
    assert target.read_text(encoding="utf-8") == "downloaded"


def test_upload_uses_timeout_and_atomic_remote_publish(tmp_path: Path) -> None:
    execute = RecordingTextExecutor()
    runner = RemoteSshRunner(
        "lab",
        execute=execute,
        transfer_timeout_s=29,
    )
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")

    runner.upload(source, PurePosixPath("/remote/upload.txt"))

    assert execute.calls[0][0][0] == "scp"
    assert execute.calls[0][0][4].startswith("lab:/remote/.upload.txt.upload-")
    assert execute.calls[0][2] == 29
    assert "mv -f -- /remote/.upload.txt.upload-" in execute.calls[1][0][4]
    assert execute.calls[1][2] == 29


def test_download_tree_uses_bounded_explicit_shell_and_atomic_publish(
    tmp_path: Path,
) -> None:
    binary = RecordingBinaryExecutor()
    target = tmp_path / "downloaded"
    target.mkdir()
    (target / "old.txt").write_text("preserved", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
        transfer_timeout_s=19,
    )

    runner.download_tree(
        PurePosixPath("/remote/project data"),
        target,
        exclude="*.log",
        dereference=True,
    )

    assert (target / "old.txt").read_text(encoding="utf-8") == "preserved"
    assert len(binary.calls) == 2
    remote_argv, remote_timeout = binary.calls[0]
    assert remote_argv[:4] == ["ssh", "-o", "BatchMode=yes", "lab"]
    assert remote_argv[4].startswith("exec /bin/sh -c ")
    assert "remote/project data" in remote_argv[4]
    assert "--exclude" in remote_argv[4]
    assert "-h" in remote_argv[4]
    assert remote_timeout == 19
    assert binary.calls[1][0][0] == "tar"
    assert binary.calls[1][1] == 19


def test_download_tree_failure_preserves_previous_complete_tree(
    tmp_path: Path,
) -> None:
    binary = RecordingBinaryExecutor([(255, b"connection reset")])
    target = tmp_path / "downloaded"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
    )

    with pytest.raises(RemoteTransportError, match="remote tar download failed"):
        runner.download_tree(PurePosixPath("/remote/data"), target)

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".downloaded.download-*"))


def test_download_tree_timeout_is_classified_and_preserves_target(
    tmp_path: Path,
) -> None:
    binary = RecordingBinaryExecutor(timeout_on_call=1)
    target = tmp_path / "downloaded"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
        transfer_timeout_s=7,
    )

    with pytest.raises(RemoteCommandTimeoutError, match="timed out after 7s"):
        runner.download_tree(PurePosixPath("/remote/data"), target)

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"


def test_download_files_uses_one_tar_stream_and_atomic_exact_publish(
    tmp_path: Path,
) -> None:
    remote_root = tmp_path / "remote"
    selected = (
        PurePosixPath("runs/real/real_001/result_manifest.json"),
        PurePosixPath(
            "runs/real/real_001/metrics/metric_result_manifest.json"
        ),
    )
    for relative in selected:
        path = remote_root.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"path": "{relative}"}}\n', encoding="utf-8")
    unselected = remote_root / "runs/real/real_001/psf/huge.bin"
    unselected.parent.mkdir(parents=True)
    unselected.write_bytes(b"not part of the manifest bundle")

    calls: list[list[str]] = []

    def execute_binary(
        argv: list[str],
        *,
        input_file: object | None,
        output_file: object | None,
        timeout_s: int | None,
    ) -> BinaryCommandResult:
        calls.append(argv)
        return _local_binary_execute(
            argv,
            input_file=input_file,
            output_file=output_file,
            timeout_s=timeout_s,
        )

    target = tmp_path / "controller" / ".remote_history_manifests"
    target.mkdir(parents=True)
    (target / "stale.json").write_text("stale\n", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=execute_binary,
    )

    runner.download_files(
        PurePosixPath(remote_root.as_posix()),
        selected,
        target,
    )

    assert len(calls) == 2
    assert calls[0][0] == "ssh"
    assert calls[1][0] == "tar"
    assert not (target / "stale.json").exists()
    assert not (target / "runs/real/real_001/psf").exists()
    assert {
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file()
    } == {relative.as_posix() for relative in selected}


def test_download_files_tar_failure_preserves_previous_verified_bundle(
    tmp_path: Path,
) -> None:
    binary = RecordingBinaryExecutor([(255, b"connection reset")])
    target = tmp_path / ".remote_history_manifests"
    target.mkdir()
    previous = target / "verified-before.json"
    previous.write_text("preserve me\n", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
    )

    with pytest.raises(
        RemoteTransportError,
        match="remote selected-file tar download failed",
    ):
        runner.download_files(
            PurePosixPath("/remote/project"),
            (PurePosixPath("runs/real/real_001/result_manifest.json"),),
            target,
        )

    assert previous.read_text(encoding="utf-8") == "preserve me\n"
    assert not list(tmp_path.glob("..remote_history_manifests.download-*"))


@pytest.mark.parametrize("replace", [False, True])
def test_upload_tree_stages_then_publishes_complete_tree(
    tmp_path: Path,
    replace: bool,
) -> None:
    binary = RecordingBinaryExecutor()
    text = RecordingTextExecutor()
    source = tmp_path / "source"
    source.mkdir()
    (source / "new.txt").write_text("new", encoding="utf-8")
    runner = RemoteSshRunner(
        "lab",
        execute=text,
        execute_binary=binary,
        transfer_timeout_s=23,
    )

    runner.upload_tree(
        source,
        PurePosixPath("/remote/project/runs/real/real_001"),
        exclude="*.tmp",
        replace=replace,
    )

    assert binary.calls[0][0] == [
        "tar",
        "-C",
        str(source),
        "--exclude",
        "*.tmp",
        "-cf",
        "-",
        ".",
    ]
    remote_command = binary.calls[1][0][4]
    assert remote_command.startswith("exec /bin/sh -c ")
    assert ".real_001.upload-" in remote_command
    assert "tar -C" in remote_command
    assert "mv -T --" in remote_command
    assert "rm -rf -- /remote/project/runs/real/real_001" not in remote_command
    assert ("cp -a --" in remote_command) is (not replace)
    assert binary.calls[0][1] == 23
    assert binary.calls[1][1] == 23
    assert text.calls[-1][0][4].startswith("exec /bin/sh -c 'rm -rf -- ")


def test_upload_tree_remote_failure_is_classified(tmp_path: Path) -> None:
    binary = RecordingBinaryExecutor([(0, b""), (255, b"connection reset")])
    source = tmp_path / "source"
    source.mkdir()
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
    )

    with pytest.raises(RemoteTransportError, match="remote tar upload failed"):
        runner.upload_tree(source, PurePosixPath("/remote/dest"))


def test_upload_tree_local_tar_failure_stops_before_ssh(tmp_path: Path) -> None:
    binary = RecordingBinaryExecutor([(2, b"tar error")])
    source = tmp_path / "source"
    source.mkdir()
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
    )

    with pytest.raises(RuntimeError, match="local tar creation failed.*tar error"):
        runner.upload_tree(source, PurePosixPath("/remote/dest"))

    assert len(binary.calls) == 1


def test_upload_tree_timeout_is_classified(tmp_path: Path) -> None:
    binary = RecordingBinaryExecutor(timeout_on_call=2)
    source = tmp_path / "source"
    source.mkdir()
    runner = RemoteSshRunner(
        "lab",
        execute=_success_text,
        execute_binary=binary,
        transfer_timeout_s=11,
    )

    with pytest.raises(RemoteCommandTimeoutError, match="timed out after 11s"):
        runner.upload_tree(source, PurePosixPath("/remote/dest"))


def test_tree_transfer_real_shell_round_trip_and_replace_semantics(
    tmp_path: Path,
) -> None:
    runner = RemoteSshRunner(
        "local",
        execute=_local_text_execute,
        execute_binary=_local_binary_execute,
        transfer_timeout_s=10,
    )
    source = tmp_path / "controller source"
    source.mkdir()
    (source / "fresh.txt").write_text("fresh", encoding="utf-8")
    remote = tmp_path / "remote tree"
    remote.mkdir()
    (remote / "stale.txt").write_text("stale", encoding="utf-8")

    runner.upload_tree(
        source,
        PurePosixPath(remote.as_posix()),
        replace=True,
    )

    assert (remote / "fresh.txt").read_text(encoding="utf-8") == "fresh"
    assert not (remote / "stale.txt").exists()

    (remote / "remote-only.txt").write_text("remote", encoding="utf-8")
    downloaded = tmp_path / "controller download"
    runner.download_tree(PurePosixPath(remote.as_posix()), downloaded)

    assert (downloaded / "fresh.txt").read_text(encoding="utf-8") == "fresh"
    assert (downloaded / "remote-only.txt").read_text(encoding="utf-8") == "remote"


def test_tree_transfer_rejects_unsupported_or_unsafe_targets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = RemoteSshRunner("lab", execute=_success_text)

    with pytest.raises(ValueError, match="include is not supported"):
        runner.download_tree(
            PurePosixPath("/remote/project"),
            tmp_path / "out",
            include="*.py",
        )
    with pytest.raises(ValueError, match="include is not supported"):
        runner.upload_tree(
            source,
            PurePosixPath("/remote/dest"),
            include="*.py",
        )
    for target in (PurePosixPath("/"), PurePosixPath("relative")):
        with pytest.raises(ValueError, match="scoped absolute path"):
            runner.upload_tree(source, target)
