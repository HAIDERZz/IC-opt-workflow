from __future__ import annotations

from pathlib import Path, PurePosixPath

import shlex

from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult


VALID_REQUIREMENT = (Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1"))


class FakeRunner:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, Path]] = []
        self.commands_run: list[str] = []

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return VALID_REQUIREMENT
        if path == "/remote/project/constraints.md":
            return "# guidance\n"
        raise FileNotFoundError(path)

    def run(self, command: str, **kwargs: object):
        self.commands_run.append(command)
        if "test -f /remote/maestro/point_1/netlist/input.scs" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

    def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
        self.downloads.append((str(remote_path), local_path))
        (local_path / "input.scs").parent.mkdir(parents=True, exist_ok=True)
        (local_path / "input.scs").write_text(
            "simulator lang=spectre\n"
            "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
            "tran tran stop=10n\n",
            encoding="utf-8",
        )


def test_prepare_remote_project_cache_writes_local_controller_project(tmp_path: Path) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert (result.cache_dir / "opt_requirement.md").is_file()
    assert (result.cache_dir / "constraints.md").is_file()
    assert (result.cache_dir / "config" / "optimizer.yaml").is_file()
    assert runner.downloads == [
        ("/remote/maestro/point_1/netlist", result.cache_dir / "netlists" / "exported")
    ]
    assert any("readlink -f" in cmd and "netlist" in cmd for cmd in runner.commands_run)


def test_prepare_remote_project_cache_quotes_paths_with_spaces(tmp_path: Path) -> None:
    spaced_requirement = (
        Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
        .read_text(encoding="utf-8")
        .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/my point 1")
    )
    spaced_path = "/remote/maestro/my point 1/netlist/input.scs"
    expected_quoted = shlex.quote(spaced_path)

    class SpacedFakeRunner(FakeRunner):
        def read_text(self, remote_path):
            path = str(remote_path)
            if path == "/remote/project/opt_requirement.md":
                return spaced_requirement
            if path == "/remote/project/constraints.md":
                return "# guidance\n"
            raise FileNotFoundError(path)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = SpacedFakeRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert any(expected_quoted in cmd for cmd in runner.commands_run)
    assert any(shlex.quote("/remote/maestro/my point 1/netlist") in cmd for cmd in runner.commands_run)


def test_prepare_remote_project_cache_validates_symlinks_before_download(tmp_path: Path) -> None:
    """Symlink validation must run on the remote host before download_tree."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class RecordingRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            super().download_tree(remote_path, local_path, include=include, exclude=exclude, dereference=dereference)

    runner = RecordingRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    assert any("readlink -f" in cmd and "netlist" in cmd for cmd in runner.commands_run)


def test_prepare_remote_project_cache_real_maestro_symlink_shape(tmp_path: Path) -> None:
    """Real Maestro shape: netlist/exprOutputs.log -> ../../../exprOutputs.log.6.0.1
    accepted when allowed root is the Interactive.* history root."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class RecordingRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            super().download_tree(remote_path, local_path, include=include, exclude=exclude, dereference=dereference)

    runner = RecordingRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    # Validation must search the netlist path, not the allowed_root path
    assert any(shlex.quote("/remote/maestro/point_1/netlist") in cmd for cmd in runner.commands_run)


def test_prepare_remote_project_cache_validation_searches_netlist_not_allowed_root(tmp_path: Path) -> None:
    """Validation must find symlinks under remote_netlist, not under allowed_root."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    netlist_quoted = shlex.quote("/remote/maestro/point_1/netlist")
    # The find command must target the netlist path
    assert any(netlist_quoted in cmd and "find" in cmd for cmd in runner.commands_run)
    # The readlink -f must resolve the netlist path
    assert any(f"readlink -f {netlist_quoted}" in cmd for cmd in runner.commands_run)


def test_prepare_remote_project_cache_boundary_rejects_prefix_trick(tmp_path: Path) -> None:
    """Root /remote/history must reject target /remote/history_evil/file."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class PrefixTrickRunner(FakeRunner):
        def run(self, command: str, **kwargs):
            self.commands_run.append(command)
            if "test -f" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if command.startswith("root=$(readlink"):
                # Simulate: a symlink under netlist resolves to /remote/history_evil/file
                # The script should exit 1 because /remote/history_evil/file does not match
                # root="/remote/history" or root/*="/remote/history/*"
                return RemoteCommandResult(
                    1,
                    "",
                    "/remote/maestro/point_1/netlist/evil.log\n",
                    ["ssh", "lab", command],
                )
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

    runner = PrefixTrickRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
    assert any("symlink" in issue.lower() for issue in result.issues)
    assert len(runner.downloads) == 0


def test_prepare_remote_project_cache_rejects_escaping_symlink(tmp_path: Path) -> None:
    """Symlinks whose target escapes the allowed history root must be rejected before download_tree."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class EscapingSymlinkRunner(FakeRunner):
        def run(self, command: str, **kwargs):
            self.commands_run.append(command)
            if command.startswith("root=$(readlink"):
                return RemoteCommandResult(
                    1, "", "/remote/maestro/point_1/netlist/escape.log\n", ["ssh", "lab", command],
                )
            return super().run(command, **kwargs)

    runner = EscapingSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
    assert any("symlink" in issue.lower() for issue in result.issues)
    assert len(runner.downloads) == 0


def test_prepare_remote_project_cache_rejects_nonregular_symlink_target(tmp_path: Path) -> None:
    """Symlinks whose target is not a regular file must be rejected before download_tree."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class NonRegularSymlinkRunner(FakeRunner):
        def run(self, command: str, **kwargs):
            self.commands_run.append(command)
            if command.startswith("root=$(readlink"):
                return RemoteCommandResult(
                    1, "", "/remote/maestro/point_1/netlist/bad.log\n", ["ssh", "lab", command],
                )
            return super().run(command, **kwargs)

    runner = NonRegularSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
    assert any("symlink" in issue.lower() for issue in result.issues)
    assert len(runner.downloads) == 0
