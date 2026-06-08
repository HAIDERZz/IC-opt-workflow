from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath

from hermes_workflow.execution_adapters.remote_spectre_ocean import run_remote_spectre_ocean_adapter
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult
from tests.real_run_smoke_helpers import create_approved_real_project


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.uploads: list[tuple[Path, str]] = []
        self.downloads: list[tuple[str, Path]] = []

    def upload_tree(self, local_path, remote_path, include=None, exclude=None) -> None:
        self.uploads.append((Path(local_path), str(remote_path)))

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        (Path(local_path) / "ocean_scalars.tsv").write_text(
            "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
            "rise\t1e-12\ts\tpass\t352e7b3256d5417f58d087382bd2054efbcf696d06b58fc6d39002bb09489748\t\n"
            "fall\t1e-12\ts\tpass\t8ba00c0d961decb9275b9636f61dbbd5659b5ed066a74b0083cd0e1d6d3d5493\t\n"
            "DC\t1e-06\tW\tpass\tcb82f3f25ee13ea3cb45f605a763ed0806ebb7f47fd27ce4a9c4a4cd902bb7c4\t\n",
            encoding="utf-8",
        )

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

    def upload(self, local_path, remote_path) -> None:
        self.uploads.append((Path(local_path), str(remote_path)))


class FailingFakeRunner(FakeRunner):
    def __init__(self, fail_on_substring: str) -> None:
        super().__init__()
        self._fail_on = fail_on_substring

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if self._fail_on in command:
            return RemoteCommandResult(1, "", "error", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])


def test_remote_adapter_runs_spectre_and_ocean_remotely(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    assert any("spectre" in command for command in runner.commands)
    assert any("ocean" in command for command in runner.commands)
    assert (run_dir / "result_manifest.json").is_file()
    assert (run_dir / "metrics" / "metric_result_manifest.json").is_file()
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["backend"] == "remote_spectre_ocean"


def test_remote_adapter_csh_payload_quotes_paths(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    remote_project = PurePosixPath("/remote/my project")
    cshrc = PurePosixPath("/remote/my project/my cadence env.csh")
    run_id = "real_001"
    remote_run_dir = remote_project / "runs" / "real" / run_id
    ref = RemoteProjectRef("lab", remote_project)
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id=run_id,
        remote_ref=ref,
        remote_cadence_cshrc=cshrc,
        runner=runner,
    )

    csh_commands = [c for c in runner.commands if c.startswith("csh -fc")]
    assert len(csh_commands) == 2

    spectre_cmd, ocean_cmd = csh_commands

    inner_spectre = shlex.split(spectre_cmd)[2]
    inner_ocean = shlex.split(ocean_cmd)[2]

    quoted_cshrc = shlex.quote(str(cshrc))
    quoted_input_dir = shlex.quote(str(remote_run_dir / "netlist"))
    quoted_project = shlex.quote(str(remote_project))
    quoted_restore = shlex.quote(str(remote_run_dir / "metrics" / "metric_probe.ocn"))

    assert f"source {quoted_cshrc}" in inner_spectre
    assert f"cd {quoted_input_dir}" in inner_spectre

    assert f"source {quoted_cshrc}" in inner_ocean
    assert f"cd {quoted_project}" in inner_ocean
    assert f"-restore {quoted_restore}" in inner_ocean


def test_remote_adapter_spectre_failure_uploads_manifest_to_remote(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FailingFakeRunner(fail_on_substring="spectre")

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    manifest_uploads = [
        (local, remote) for local, remote in runner.uploads
        if remote.endswith("result_manifest.json") and local == run_dir / "result_manifest.json"
    ]
    assert len(manifest_uploads) == 1


def test_remote_adapter_ocean_failure_uploads_manifest_to_remote(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FailingFakeRunner(fail_on_substring="ocean")

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    manifest_uploads = [
        (local, remote) for local, remote in runner.uploads
        if remote.endswith("result_manifest.json") and local == run_dir / "result_manifest.json"
    ]
    assert len(manifest_uploads) == 1
