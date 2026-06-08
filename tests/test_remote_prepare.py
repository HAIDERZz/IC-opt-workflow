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


def test_prepare_remote_project_cache_dereferences_symlinks(tmp_path: Path) -> None:
    """With tar --dereference, symlinks are resolved at source; no symlinks arrive locally."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class SymlinkFakeRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n"
                "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
                "tran tran stop=10n\n",
                encoding="utf-8",
            )
            # Simulate tar --dereference: create regular file with target content
            (local_path / "exprOutputs.log").write_text("data\n", encoding="utf-8")

    runner = SymlinkFakeRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    exported = result.cache_dir / "netlists" / "exported"
    assert (exported / "exprOutputs.log").is_file()
    assert not (exported / "exprOutputs.log").is_symlink()


def test_prepare_remote_project_cache_no_symlinks_after_dereference(tmp_path: Path) -> None:
    """With tar --dereference, escaping symlinks are resolved at source; no symlinks arrive locally."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class EscapingSymlinkRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n"
                "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
                "tran tran stop=10n\n",
                encoding="utf-8",
            )
            # Simulate tar --dereference: regular file with target content, no symlink
            (local_path / "escape.log").write_text("resolved content\n", encoding="utf-8")

    runner = EscapingSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    exported = result.cache_dir / "netlists" / "exported"
    assert not any(p.is_symlink() for p in exported.rglob("*"))


def test_prepare_remote_project_cache_no_broken_symlinks_after_dereference(tmp_path: Path) -> None:
    """With tar --dereference, broken symlinks are resolved at source; no symlinks arrive locally."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class BrokenSymlinkRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n"
                "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
                "tran tran stop=10n\n",
                encoding="utf-8",
            )
            # Simulate tar --dereference: regular file, no broken symlink
            (local_path / "broken.log").write_text("resolved content\n", encoding="utf-8")

    runner = BrokenSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    exported = result.cache_dir / "netlists" / "exported"
    assert not any(p.is_symlink() for p in exported.rglob("*"))


def test_prepare_remote_project_cache_real_maestro_symlink_shape(tmp_path: Path) -> None:
    """Real Maestro symlink: netlist/exprOutputs.log -> ../../../exprOutputs.log.6.0.1
    with allowed root being the Maestro history root."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    dereference_values: list[bool] = []

    class RealMaestroSymlinkRunner(FakeRunner):
        def download_tree(self, remote_path, local_path, include=None, exclude=None, dereference=False) -> None:
            dereference_values.append(dereference)
            local_path.mkdir(parents=True, exist_ok=True)
            (local_path / "input.scs").write_text(
                "simulator lang=spectre\n"
                "parameters FN=2 WN=0.3u FP=2 WP=0.3u\n"
                "tran tran stop=10n\n",
                encoding="utf-8",
            )
            # Simulate tar --dereference: create regular file with target content
            (local_path / "exprOutputs.log").write_text("real maestro data\n", encoding="utf-8")

    runner = RealMaestroSymlinkRunner()
    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert all(v is True for v in dereference_values)
    exported = result.cache_dir / "netlists" / "exported"
    assert (exported / "exprOutputs.log").is_file()
    assert not (exported / "exprOutputs.log").is_symlink()
    assert (exported / "exprOutputs.log").read_text(encoding="utf-8") == "real maestro data\n"
