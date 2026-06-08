from __future__ import annotations

import json
import os
import shlex
from pathlib import Path, PurePosixPath

from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_multi_testbench_adapter,
    run_remote_spectre_ocean_adapter,
)
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
    assert manifest["status"] == "succeeded"
    assert "remote spectre and ocean completed" in manifest.get("notes", "")


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


class MultiTestbenchFakeRunner(FakeRunner):
    """FakeRunner that writes correct ocean_scalars.tsv per child testbench."""

    def __init__(self) -> None:
        super().__init__()
        self.child_metric_names: dict[str, list[str]] = {}

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        local = Path(local_path)
        metric_names = self._resolve_metric_names(local)
        header = "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
        rows = "".join(
            f"{name}\t1e-12\ts\tpass\t{'a' * 64}\t\n" for name in metric_names
        )
        (local / "ocean_scalars.tsv").write_text(header + rows, encoding="utf-8")

    def _resolve_metric_names(self, local_path: Path) -> list[str]:
        parts = local_path.parts
        for i, part in enumerate(parts):
            if part == "testbenches" and i + 1 < len(parts):
                testbench_id = parts[i + 1]
                if testbench_id in self.child_metric_names:
                    return self.child_metric_names[testbench_id]
        return ["rise", "fall", "DC"]


def test_remote_multi_testbench_adapter_runs_each_child(tmp_path: Path) -> None:
    from tests.test_multi_testbench_aggregation import (
        _create_ready_multi_testbench_project,
    )

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    spectre_cmds = [c for c in runner.commands if "spectre" in c]
    ocean_cmds = [c for c in runner.commands if "ocean" in c]
    assert len(spectre_cmds) == 2
    assert len(ocean_cmds) == 2
    for cmd in ocean_cmds:
        assert "testbenches/" in cmd
        assert "metric_probe.ocn" in cmd
    aggregate_uploads = [
        (local, remote) for local, remote in runner.uploads
        if str(remote).endswith("result_manifest.json")
        and "/testbenches/" not in str(remote)
    ]
    assert len(aggregate_uploads) >= 1
    child_result_uploads = [
        (local, remote) for local, remote in runner.uploads
        if "/testbenches/" in str(remote) and str(remote).endswith("/result_manifest.json")
    ]
    assert len(child_result_uploads) == 2
    child_metric_uploads = [
        (local, remote) for local, remote in runner.uploads
        if "/testbenches/" in str(remote) and "metric_result_manifest.json" in str(remote)
    ]
    assert len(child_metric_uploads) == 2


def test_remote_multi_testbench_adapter_child_metric_probe_paths(tmp_path: Path) -> None:
    """Verify ocean commands use child metric_probe.ocn, not top-level."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    ocean_cmds = [c for c in runner.commands if "ocean" in c]
    for cmd in ocean_cmds:
        inner = shlex.split(cmd)[2]
        assert "/real/real_001/metrics/metric_probe.ocn" not in inner
        assert "testbenches/" in inner
        assert "metric_probe.ocn" in inner


def test_remote_multi_testbench_adapter_child_failure_reports_issues(tmp_path: Path) -> None:
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    def failing_run(command: str, **kwargs: object) -> RemoteCommandResult:
        runner.commands.append(command)
        if "spectre" in command and "iip3" in command:
            return RemoteCommandResult(1, "", "spectre error", ["ssh", "lab", command])
        return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

    runner.run = failing_run

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    assert any("iip3" in issue for issue in result.issues)


def test_remote_multi_testbench_adapter_aggregates_upload(tmp_path: Path) -> None:
    """Verify aggregate result_manifest and metric_result_manifest are uploaded."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    remote_run_dir = "/remote/project/runs/real/real_001"
    result_uploads = [
        r for _, r in runner.uploads
        if r == f"{remote_run_dir}/result_manifest.json"
    ]
    assert len(result_uploads) >= 1
    metric_uploads = [
        r for _, r in runner.uploads
        if r == f"{remote_run_dir}/metrics/metric_result_manifest.json"
    ]
    assert len(metric_uploads) >= 1


def test_remote_adapter_writes_ocean_script_under_project_dir_not_cwd(tmp_path: Path) -> None:
    """Regression: metric_probe.ocn must be written under project_dir, not cwd."""
    project_dir = create_approved_real_project(tmp_path / "project")
    separate_cwd = tmp_path / "other_cwd"
    separate_cwd.mkdir()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    original_cwd = Path.cwd()
    try:
        os.chdir(separate_cwd)
        run_remote_spectre_ocean_adapter(
            project_dir,
            run_id="real_001",
            remote_ref=ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            runner=runner,
        )
    finally:
        os.chdir(original_cwd)

    # Script must exist under project_dir, not under separate_cwd
    expected_script = project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_probe.ocn"
    assert expected_script.is_file(), f"metric_probe.ocn missing from project_dir: {expected_script}"
    wrong_script = separate_cwd / "runs" / "real" / "real_001" / "metrics" / "metric_probe.ocn"
    assert not wrong_script.exists(), f"metric_probe.ocn leaked to cwd: {wrong_script}"


def test_remote_multi_testbench_writes_ocean_scripts_under_project_dir(tmp_path: Path) -> None:
    """Regression: child metric_probe.ocn files must be under project_dir, not cwd."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path / "project")
    separate_cwd = tmp_path / "other_cwd"
    separate_cwd.mkdir()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    original_cwd = Path.cwd()
    try:
        os.chdir(separate_cwd)
        run_remote_multi_testbench_adapter(
            project_dir,
            run_id="real_001",
            remote_ref=ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            runner=runner,
        )
    finally:
        os.chdir(original_cwd)

    # Each child metric_probe.ocn must be under project_dir
    for tb_id in ("cg_nf", "iip3"):
        expected = (
            project_dir / "runs" / "real" / "real_001"
            / "testbenches" / tb_id / "metrics" / "metric_probe.ocn"
        )
        assert expected.is_file(), f"metric_probe.ocn missing for {tb_id}: {expected}"
        wrong = (
            separate_cwd / "runs" / "real" / "real_001"
            / "testbenches" / tb_id / "metrics" / "metric_probe.ocn"
        )
        assert not wrong.exists(), f"metric_probe.ocn leaked to cwd for {tb_id}: {wrong}"
