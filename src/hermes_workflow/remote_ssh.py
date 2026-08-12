from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Sequence


@dataclass(frozen=True)
class RemoteCommandResult:
    return_code: int
    stdout: str
    stderr: str
    argv: list[str]


ExecuteRemoteCommand = Callable[..., RemoteCommandResult]


@dataclass(frozen=True)
class BinaryCommandResult:
    return_code: int
    stdout: bytes
    stderr: bytes
    argv: list[str]


ExecuteBinaryCommand = Callable[..., BinaryCommandResult]


class RemoteCommandError(RuntimeError):
    """A remote command completed unsuccessfully."""


class RemoteTransportError(RemoteCommandError):
    """SSH could not transport or execute the remote command."""


class RemoteCommandUnavailableError(RemoteCommandError):
    """The requested remote executable is missing or cannot be invoked."""


class RemoteCommandTimeoutError(RemoteCommandError):
    """A remote command or transfer exceeded its configured deadline."""


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


def _default_execute_binary(
    argv: list[str],
    *,
    input_file: BinaryIO | None = None,
    output_file: BinaryIO | None = None,
    timeout_s: int | None = None,
) -> BinaryCommandResult:
    completed = subprocess.run(
        argv,
        stdin=input_file,
        stdout=output_file if output_file is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    return BinaryCommandResult(
        return_code=completed.returncode,
        stdout=(completed.stdout or b"") if output_file is None else b"",
        stderr=completed.stderr or b"",
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
        execute_binary: ExecuteBinaryCommand = _default_execute_binary,
        transfer_timeout_s: int = 1800,
    ) -> None:
        if not profile.strip():
            raise ValueError("ssh profile must not be empty")
        if profile.strip().startswith("-"):
            raise ValueError("ssh profile must not start with '-'")
        if transfer_timeout_s < 1:
            raise ValueError("transfer_timeout_s must be >= 1")
        self.profile = profile
        self._execute = execute
        self._execute_binary = execute_binary
        self.transfer_timeout_s = transfer_timeout_s

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
        argv = self._ssh_argv(remote_command)
        try:
            result = self._execute(
                argv,
                input_text=input_text,
                timeout_s=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteCommandTimeoutError(
                f"remote command timed out after {timeout_s}s: {command}"
            ) from exc
        if check and result.return_code != 0:
            self._raise_checked_error(result)
        return result

    def run_login_shell(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        check: bool = False,
    ) -> RemoteCommandResult:
        """Run a bootstrap probe before ``/bin/sh`` availability is known.

        Product workflow commands must use :meth:`run`. This narrow seam is
        only for doctor probes that establish SSH and ``/bin/sh`` readiness.
        """
        argv = ["ssh", "-o", "BatchMode=yes", self.profile, command]
        try:
            result = self._execute(
                argv,
                input_text=None,
                timeout_s=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteCommandTimeoutError(
                f"remote bootstrap command timed out after {timeout_s}s: {command}"
            ) from exc
        if check and result.return_code != 0:
            self._raise_checked_error(result)
        return result

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        result = self.run(
            f"cat {quote_remote_path(remote_path)}",
            timeout_s=self.transfer_timeout_s,
            check=True,
        )
        return result.stdout

    def write_text(self, remote_path: PurePosixPath | str, text: str) -> None:
        target = PurePosixPath(remote_path)
        temporary = _remote_upload_temp_path(target)
        command = (
            f"cat > {quote_remote_path(temporary)} && "
            f"mv -f -- {quote_remote_path(temporary)} "
            f"{quote_remote_path(target)}"
        )
        self.run(
            command,
            timeout_s=self.transfer_timeout_s,
            input_text=text,
            check=True,
        )

    def exists(self, remote_path: PurePosixPath | str) -> bool:
        result = self.run(f"test -e {quote_remote_path(remote_path)}")
        return require_boolean_probe(
            result,
            profile=self.profile,
            description=f"remote path probe for {remote_path}",
        )

    def is_file(self, remote_path: PurePosixPath | str) -> bool:
        result = self.run(f"test -f {quote_remote_path(remote_path)}")
        return require_boolean_probe(
            result,
            profile=self.profile,
            description=f"remote file probe for {remote_path}",
        )

    def is_dir(self, remote_path: PurePosixPath | str) -> bool:
        result = self.run(f"test -d {quote_remote_path(remote_path)}")
        return require_boolean_probe(
            result,
            profile=self.profile,
            description=f"remote directory probe for {remote_path}",
        )

    def mkdir(self, remote_path: PurePosixPath | str) -> None:
        self.run(f"mkdir -p {quote_remote_path(remote_path)}", check=True)

    def download(self, remote_path: PurePosixPath | str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = local_path.parent / f".{local_path.name}.download-{uuid.uuid4().hex}"
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            f"{self.profile}:{quote_remote_path(remote_path)}",
            str(temporary),
        ]
        try:
            result = self._execute(
                argv,
                input_text=None,
                timeout_s=self.transfer_timeout_s,
            )
            if result.return_code != 0:
                self._raise_checked_error(result)
            temporary.replace(local_path)
        except subprocess.TimeoutExpired as exc:
            raise RemoteCommandTimeoutError(
                f"remote file download timed out after {self.transfer_timeout_s}s: "
                f"{remote_path}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def upload(self, local_path: Path, remote_path: PurePosixPath | str) -> None:
        target = PurePosixPath(remote_path)
        temporary = _remote_upload_temp_path(target)
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            str(local_path),
            f"{self.profile}:{quote_remote_path(temporary)}",
        ]
        try:
            result = self._execute(
                argv,
                input_text=None,
                timeout_s=self.transfer_timeout_s,
            )
            if result.return_code != 0:
                self._raise_checked_error(result)
            self.run(
                f"mv -f -- {quote_remote_path(temporary)} "
                f"{quote_remote_path(target)}",
                timeout_s=self.transfer_timeout_s,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            self._remove_remote_upload_temp(temporary)
            raise RemoteCommandTimeoutError(
                f"remote file upload timed out after {self.transfer_timeout_s}s: "
                f"{target}"
            ) from exc
        except Exception:
            self._remove_remote_upload_temp(temporary)
            raise

    def download_tree(
        self,
        remote_path: PurePosixPath | str,
        local_path: Path,
        *,
        include: str | None = None,
        exclude: str | None = None,
        dereference: bool = False,
    ) -> None:
        if include is not None:
            raise ValueError("include is not supported for tree transfer yet")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote = PurePosixPath(remote_path)

        parts: list[str] = ["tar", "-C", str(remote)]
        if dereference:
            parts.append("-h")
        if exclude:
            parts.extend(["--exclude", exclude])
        parts.extend(["-cf", "-", "."])
        remote_cmd = " ".join(shlex.quote(p) for p in parts)
        ssh_argv = self._ssh_argv(remote_cmd)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{local_path.name}.download-",
                dir=local_path.parent,
            )
        )
        backup: Path | None = None
        try:
            if local_path.exists():
                if not local_path.is_dir():
                    raise ValueError(
                        f"tree download target is not a directory: {local_path}"
                    )
                shutil.copytree(
                    local_path,
                    staging,
                    dirs_exist_ok=True,
                    symlinks=True,
                )
            with tempfile.TemporaryFile(dir=local_path.parent) as archive:
                remote_result = self._run_binary(
                    ssh_argv,
                    output_file=archive,
                    operation=f"remote tree download {remote}",
                )
                if remote_result.return_code != 0:
                    self._raise_binary_error(
                        remote_result,
                        prefix="remote tar download failed",
                    )
                archive.seek(0)
                local_result = self._run_binary(
                    ["tar", "-C", str(staging), "-xf", "-"],
                    input_file=archive,
                    operation=f"local tree extraction {local_path}",
                )
                if local_result.return_code != 0:
                    raise RuntimeError(
                        "local tar extraction failed: "
                        f"return_code={local_result.return_code}, "
                        f"stderr={_decode(local_result.stderr).strip()}"
                    )
            backup = _publish_local_tree(staging, local_path)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
            if backup is not None and backup.exists():
                shutil.rmtree(backup)

    def download_files(
        self,
        remote_root: PurePosixPath | str,
        relative_paths: Sequence[PurePosixPath | str],
        local_root: Path,
    ) -> None:
        """Atomically materialize an exact set of remote-root-relative files."""
        remote = PurePosixPath(remote_root)
        if (
            not remote.is_absolute()
            or remote == PurePosixPath("/")
            or ".." in remote.parts
        ):
            raise ValueError(
                f"remote file bundle root must be a scoped absolute path: {remote}"
            )
        selected = tuple(
            sorted(
                {PurePosixPath(path) for path in relative_paths},
                key=PurePosixPath.as_posix,
            )
        )
        if not selected:
            raise ValueError("remote file bundle must contain at least one path")
        for relative in selected:
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError(
                    "remote file bundle paths must stay within the remote root: "
                    f"{relative}"
                )

        local_root.parent.mkdir(parents=True, exist_ok=True)
        if local_root.is_symlink() or (
            local_root.exists() and not local_root.is_dir()
        ):
            raise ValueError(
                f"remote file bundle target is not a directory: {local_root}"
            )
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{local_root.name}.download-",
                dir=local_root.parent,
            )
        )
        backup: Path | None = None
        remote_cmd = " ".join(
            shlex.quote(part)
            for part in (
                "tar",
                "-C",
                remote.as_posix(),
                "--null",
                "--verbatim-files-from",
                "--no-recursion",
                "-cf",
                "-",
                "-T",
                "-",
            )
        )
        try:
            with tempfile.TemporaryFile(dir=local_root.parent) as path_list:
                path_list.write(
                    b"".join(
                        relative.as_posix().encode("utf-8") + b"\0"
                        for relative in selected
                    )
                )
                path_list.seek(0)
                with tempfile.TemporaryFile(dir=local_root.parent) as archive:
                    remote_result = self._run_binary(
                        self._ssh_argv(remote_cmd),
                        input_file=path_list,
                        output_file=archive,
                        operation=f"remote selected-file download {remote}",
                    )
                    if remote_result.return_code != 0:
                        self._raise_binary_error(
                            remote_result,
                            prefix="remote selected-file tar download failed",
                        )
                    archive.seek(0)
                    local_result = self._run_binary(
                        [
                            "tar",
                            "-C",
                            str(staging),
                            "--no-same-owner",
                            "--no-same-permissions",
                            "-xf",
                            "-",
                        ],
                        input_file=archive,
                        operation=f"local selected-file extraction {local_root}",
                    )
                    if local_result.return_code != 0:
                        raise RuntimeError(
                            "local selected-file tar extraction failed: "
                            f"return_code={local_result.return_code}, "
                            f"stderr={_decode(local_result.stderr).strip()}"
                        )

            materialized: set[PurePosixPath] = set()
            for path in staging.rglob("*"):
                if path.is_symlink():
                    raise RuntimeError(
                        "remote file bundle contains a symbolic link: "
                        f"{path.relative_to(staging).as_posix()}"
                    )
                if path.is_file():
                    materialized.add(
                        PurePosixPath(path.relative_to(staging).as_posix())
                    )
            expected = set(selected)
            if materialized != expected:
                missing = sorted(expected - materialized, key=PurePosixPath.as_posix)
                unexpected = sorted(
                    materialized - expected,
                    key=PurePosixPath.as_posix,
                )
                raise RuntimeError(
                    "remote file bundle contents do not match the requested paths: "
                    f"missing={[path.as_posix() for path in missing]}, "
                    f"unexpected={[path.as_posix() for path in unexpected]}"
                )
            backup = _publish_local_tree(staging, local_root)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
            if backup is not None and backup.exists():
                shutil.rmtree(backup)

    def upload_tree(
        self,
        local_path: Path,
        remote_path: PurePosixPath | str,
        *,
        include: str | None = None,
        exclude: str | None = None,
        replace: bool = False,
    ) -> None:
        if include is not None:
            raise ValueError("include is not supported for tree transfer yet")
        remote = PurePosixPath(remote_path)
        if not remote.is_absolute() or remote == PurePosixPath("/") or ".." in remote.parts:
            raise ValueError(
                f"remote tree target must be a scoped absolute path: {remote}"
            )
        staging = remote.parent / f".{remote.name}.upload-{uuid.uuid4().hex}"
        backup = remote.parent / f".{remote.name}.backup-{uuid.uuid4().hex}"

        local_parts: list[str] = ["tar", "-C", str(local_path)]
        if exclude:
            local_parts.extend(["--exclude", exclude])
        local_parts.extend(["-cf", "-", "."])

        q_remote = quote_remote_path(remote)
        q_staging = quote_remote_path(staging)
        q_backup = quote_remote_path(backup)
        seed = "" if replace else (
            f"if [ -d {q_remote} ]; then cp -a -- {q_remote}/. {q_staging}/; "
            f"elif [ -e {q_remote} ] || [ -L {q_remote} ]; then exit 72; fi; "
        )
        remote_cmd = (
            "set -eu; "
            f"mkdir -p -- {quote_remote_path(remote.parent)}; "
            f"rm -rf -- {q_staging} {q_backup}; mkdir -- {q_staging}; "
            f"{seed}"
            f"tar -C {q_staging} -xf -; "
            f"if [ -e {q_remote} ] || [ -L {q_remote} ]; then "
            f"mv -T -- {q_remote} {q_backup}; fi; "
            f"if mv -T -- {q_staging} {q_remote}; then rm -rf -- {q_backup}; "
            f"else status=$?; if [ -e {q_backup} ] || [ -L {q_backup} ]; then "
            f"mv -T -- {q_backup} {q_remote}; fi; exit $status; fi"
        )
        transfer_failed = False
        try:
            with tempfile.TemporaryFile(dir=local_path.parent) as archive:
                local_result = self._run_binary(
                    local_parts,
                    output_file=archive,
                    operation=f"local tree archive {local_path}",
                )
                if local_result.return_code != 0:
                    raise RuntimeError(
                        "local tar creation failed: "
                        f"return_code={local_result.return_code}, "
                        f"stderr={_decode(local_result.stderr).strip()}"
                    )
                archive.seek(0)
                remote_result = self._run_binary(
                    self._ssh_argv(remote_cmd),
                    input_file=archive,
                    operation=f"remote tree upload {remote}",
                )
                if remote_result.return_code != 0:
                    self._raise_binary_error(
                        remote_result,
                        prefix="remote tar upload failed",
                    )
        except BaseException:
            transfer_failed = True
            raise
        finally:
            try:
                self.run(
                    f"rm -rf -- {q_staging} {q_backup}",
                    timeout_s=self.transfer_timeout_s,
                    check=True,
                )
            except RemoteCommandError:
                # Preserve the primary transfer/publish failure. A later
                # attempt can safely remove uniquely named staging paths.
                if not transfer_failed:
                    raise

    def _remove_remote_upload_temp(self, temporary: PurePosixPath) -> None:
        try:
            self.run(
                f"rm -f -- {quote_remote_path(temporary)}",
                timeout_s=self.transfer_timeout_s,
                check=True,
            )
        except RemoteCommandError:
            pass

    def _ssh_argv(self, command: str) -> list[str]:
        explicit_shell = f"exec /bin/sh -c {shlex.quote(command)}"
        return [
            "ssh",
            "-o",
            "BatchMode=yes",
            self.profile,
            explicit_shell,
        ]

    def _run_binary(
        self,
        argv: list[str],
        *,
        operation: str,
        input_file: BinaryIO | None = None,
        output_file: BinaryIO | None = None,
    ) -> BinaryCommandResult:
        try:
            return self._execute_binary(
                argv,
                input_file=input_file,
                output_file=output_file,
                timeout_s=self.transfer_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteCommandTimeoutError(
                f"{operation} timed out after {self.transfer_timeout_s}s"
            ) from exc

    def _raise_binary_error(
        self,
        result: BinaryCommandResult,
        *,
        prefix: str,
    ) -> None:
        text_result = RemoteCommandResult(
            result.return_code,
            _decode(result.stdout),
            _decode(result.stderr),
            result.argv,
        )
        try:
            self._raise_checked_error(text_result)
        except RemoteCommandError as exc:
            raise type(exc)(f"{prefix}: {exc}") from exc

    def _raise_checked_error(self, result: RemoteCommandResult) -> None:
        if result.return_code == 255:
            raise RemoteTransportError(
                f'SSH passwordless login failed for profile "{self.profile}". '
                f"Configure ~/.ssh/config and key-based login, then verify: "
                f"ssh {self.profile} true. stderr: {result.stderr.strip()}"
            )
        if result.return_code in {126, 127}:
            raise RemoteCommandUnavailableError(
                "remote command is unavailable: "
                f"return_code={result.return_code}, command={result.argv[-1]!r}, "
                f"stderr={result.stderr.strip()}"
            )
        raise RemoteCommandError(
            "remote command failed: "
            f"return_code={result.return_code}, command={result.argv[-1]!r}, "
            f"stderr={result.stderr.strip()}"
        )


def _remote_upload_temp_path(target: PurePosixPath) -> PurePosixPath:
    return target.parent / f".{target.name}.upload-{uuid.uuid4().hex}"


def require_boolean_probe(
    result: RemoteCommandResult,
    *,
    profile: str,
    description: str,
) -> bool:
    """Interpret POSIX ``test`` without collapsing transport/tool failures."""
    if result.return_code == 0:
        return True
    if result.return_code == 1:
        return False
    raise_for_remote_result(
        result,
        profile=profile,
        description=description,
    )
    raise AssertionError("unreachable")


def raise_for_remote_result(
    result: RemoteCommandResult,
    *,
    profile: str,
    description: str,
) -> None:
    if result.return_code == 0:
        return
    runner = RemoteSshRunner(profile)
    try:
        runner._raise_checked_error(result)
    except RemoteCommandError as exc:
        raise type(exc)(f"{description} failed: {exc}") from exc


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _publish_local_tree(staging: Path, target: Path) -> Path | None:
    """Publish a complete local tree and restore the old tree on failure."""
    backup: Path | None = None
    if target.exists():
        backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
        target.replace(backup)
    try:
        staging.replace(target)
    except Exception:
        if backup is not None and backup.exists() and not target.exists():
            backup.replace(target)
        raise
    return backup
