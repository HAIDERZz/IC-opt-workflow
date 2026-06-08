from __future__ import annotations

from pathlib import Path, PurePosixPath

import shlex

from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef


VALID_REQUIREMENT = (Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1"))


class FakeRunner:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, Path]] = []

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return VALID_REQUIREMENT
        if path == "/remote/project/constraints.md":
            return "# guidance\n"
        raise FileNotFoundError(path)

    def run(self, command: str, **kwargs: object):
        from hermes_workflow.remote_ssh import RemoteCommandResult

        if "test -f /remote/maestro/point_1/netlist/input.scs" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
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


def test_prepare_remote_project_cache_quotes_paths_with_spaces(tmp_path: Path) -> None:
    spaced_requirement = (
        Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
        .read_text(encoding="utf-8")
        .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/my point 1")
    )
    spaced_path = "/remote/maestro/my point 1/netlist/input.scs"
    expected_quoted = shlex.quote(spaced_path)
    commands_run: list[str] = []

    class SpacedFakeRunner(FakeRunner):
        def read_text(self, remote_path):
            path = str(remote_path)
            if path == "/remote/project/opt_requirement.md":
                return spaced_requirement
            if path == "/remote/project/constraints.md":
                return "# guidance\n"
            raise FileNotFoundError(path)

        def run(self, command: str, **kwargs):
            commands_run.append(command)
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = SpacedFakeRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert any(expected_quoted in cmd for cmd in commands_run)


def test_prepare_remote_project_cache_materializes_symlinks(tmp_path: Path) -> None:
    """Symlinks in downloaded remote netlists must be materialized as regular files."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class SymlinkFakeRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n"
                "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
                "tran tran stop=10n\n",
                encoding="utf-8",
            )
            # Create a regular file and a symlink pointing to it
            (local_path / "real_output.log").write_text("data\n", encoding="utf-8")
            (local_path / "exprOutputs.log").symlink_to(local_path / "real_output.log")

    runner = SymlinkFakeRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    exported = result.cache_dir / "netlists" / "exported"
    assert (exported / "exprOutputs.log").is_file()
    assert not (exported / "exprOutputs.log").is_symlink()


def test_prepare_remote_project_cache_rejects_symlink_escaping_directory(tmp_path: Path) -> None:
    """Symlinks whose target escapes the downloaded directory must be rejected."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("secret\n", encoding="utf-8")

    class EscapingSymlinkRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n", encoding="utf-8",
            )
            (local_path / "escape.log").symlink_to(outside_file)

    runner = EscapingSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
    assert any("symlink" in issue.lower() or "escapes" in issue.lower() for issue in result.issues)


def test_prepare_remote_project_cache_rejects_broken_symlink(tmp_path: Path) -> None:
    """Symlinks whose target does not exist must be rejected."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class BrokenSymlinkRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n", encoding="utf-8",
            )
            (local_path / "broken.log").symlink_to(Path("/nonexistent/target"))

    runner = BrokenSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
    assert any("symlink" in issue.lower() or "not a regular file" in issue.lower() for issue in result.issues)
