from __future__ import annotations

import json
import os
import shlex
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import yaml

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_multi_testbench_adapter,
    run_remote_spectre_ocean_adapter,
)
from hermes_workflow.execution_adapters.spectre_ocean import load_adapter_context
from hermes_workflow.package import build_execution_package, sha256_file
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult
from hermes_workflow.requirement_intake import prepare_from_requirement
from tests.project_factory import create_generic_project
from tests.report_helpers import write_pass_reports
from tests.real_run_smoke_helpers import (
    create_approved_real_project,
)
from tests.test_requirement_intake import _copy_multi_testbench_requirement_project


def _metric_names(project_dir: Path) -> list[str]:
    request = json.loads(
        (project_dir / "runs" / "real" / "real_001" / "metric_extraction_request.json")
        .read_text(encoding="utf-8")
    )
    return [metric["name"] for metric in request["metrics"]]


def _variable_names(project_dir: Path) -> list[str]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return [variable["name"] for variable in payload["variables"]]


def _request_for_metrics_dir(metrics_dir: Path) -> dict | None:
    """Resolve the metric_extraction_request.json for a downloaded metrics dir.

    The metrics dir lives at <project_dir>/runs/real/<run_id>/metrics (single
    testbench) or under a testbenches/<id>[/corners/<id>] subtree (multi
    testbench).  Walk parents to find the runs/real/<run_id> directory that
    contains the metric_extraction_request.json.
    """
    run_dir = metrics_dir.parent
    direct = run_dir / "metric_extraction_request.json"
    if direct.is_file():
        return json.loads(direct.read_text(encoding="utf-8"))
    for ancestor in metrics_dir.parents:
        if ancestor.name == "runs":
            continue
        candidate = ancestor / "metric_extraction_request.json"
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def _ocean_scalars_tsv(request: dict | None) -> str:
    """Build an ocean_scalars.tsv body from a metric request.

    A metric request is always required; the legacy hardcoded fallback rows
    have been removed.
    """
    if not request:
        raise AssertionError(
            "ocean_scalars.tsv requires a resolvable metric_extraction_request, got None"
        )
    header = "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
    rows = "".join(
        f"{metric['name']}\t1e-12\t{metric['unit']}\tpass\t{metric['expression_sha256']}\t\n"
        for metric in request["metrics"]
    )
    return header + rows


def _inject_three_corner_section(project_dir: Path) -> None:
    requirement_path = project_dir / "opt_requirement.md"
    text = requirement_path.read_text(encoding="utf-8")
    corners_section = """
## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: "0"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
```
"""
    requirement_path.write_text(
        text.replace("## Approval Checklist", corners_section + "\n## Approval Checklist"),
        encoding="utf-8",
    )


def _create_ready_multi_corner_multi_testbench_project(tmp_path: Path) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    _inject_three_corner_section(project_dir)
    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"
    build_execution_package(project_dir, created_at_utc="2026-06-12T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-12T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-12T00:20:00Z")
    return project_dir


def _write_process_corners_config(
    project_dir: Path,
    corner_ids: list[str],
    *,
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> None:
    lines = [
        'schema_version: "1.0"',
        f"objective_policy: {objective_policy}",
        f"constraint_policy: {constraint_policy}",
        "corners:",
    ]
    for corner_id in corner_ids:
        lines.extend(
            [
                f"  - id: {corner_id}",
                f"    description: {corner_id} corner",
            ]
        )
    (project_dir / "config" / "process_corners.yaml").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _create_ready_multi_corner_single_testbench_project(
    tmp_path: Path,
    *,
    corner_ids: list[str],
    objective_policy: str = "worst_case",
    constraint_policy: str = "all_corners",
) -> Path:
    project_dir = create_generic_project(
        tmp_path,
        name="multi_corner_project",
    )
    _write_process_corners_config(
        project_dir,
        corner_ids,
        objective_policy=objective_policy,
        constraint_policy=constraint_policy,
    )
    template_text = (
        project_dir / "netlists" / "templates" / "template.scs"
    ).read_text(encoding="utf-8")
    for corner_id in corner_ids:
        corner_template = (
            project_dir / "netlists" / "corners" / corner_id / "template.scs"
        )
        corner_template.parent.mkdir(parents=True, exist_ok=True)
        corner_template.write_text(template_text, encoding="utf-8")
    build_execution_package(project_dir, created_at_utc="2026-06-13T00:00:00Z")
    write_pass_reports(project_dir, variable_names=tuple(_variable_names(project_dir)))
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-13T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-13T00:20:00Z")
    return project_dir


def _prepared_testbench_child_dir(
    project_dir: Path,
    testbench_id: str,
    *,
    run_id: str = "real_001",
    corner_id: str | None = None,
) -> Path:
    child_dir = project_dir / "runs" / "real" / run_id / "testbenches" / testbench_id
    if corner_id is not None:
        return child_dir / "corners" / corner_id
    if (child_dir / "metric_extraction_request.json").is_file():
        return child_dir
    corner_requests = sorted(child_dir.glob("corners/*/metric_extraction_request.json"))
    if len(corner_requests) == 1:
        return corner_requests[0].parent
    return child_dir


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.command_kwargs: list[dict[str, object]] = []
        self.uploads: list[tuple[Path, str]] = []
        self.downloads: list[tuple[str, Path]] = []

    def upload_tree(self, local_path, remote_path, include=None, exclude=None) -> None:
        self.uploads.append((Path(local_path), str(remote_path)))

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics"):
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout output", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log output", encoding="utf-8")

    def download(self, remote_path: str, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))
        # Only create the file if the remote path is a plausible artifact
        # location.  This prevents unconditional file creation from masking
        # redirect-placement bugs.
        name = Path(remote_path).name
        parent = str(Path(remote_path).parent)
        if name in ("ocean.log",) and parent.rstrip("/").endswith("metrics"):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(f"content of {name}", encoding="utf-8")

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        self.command_kwargs.append(dict(kwargs))
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
            return RemoteCommandResult(
                1,
                f"stdout from failing {self._fail_on} command",
                f"stderr from failing {self._fail_on} command",
                ["ssh", "lab", command],
            )
        return RemoteCommandResult(0, "stdout from successful command", "", ["ssh", "lab", command])


class UploadFailingFakeRunner(FakeRunner):
    """Runner that simulates remote upload failures after upload was attempted."""

    def __init__(self, fail_on_substring: str) -> None:
        super().__init__()
        self._fail_on = fail_on_substring

    def upload(self, local_path, remote_path) -> None:
        self.uploads.append((Path(local_path), str(remote_path)))
        if self._fail_on in str(remote_path):
            raise RuntimeError(f"upload failure for {remote_path}")
        return None


class DownloadFailingFakeRunner(FakeRunner):
    """Runner that raises on download to exercise local manifest fallback."""

    def __init__(self, fail_on_substring: str) -> None:
        super().__init__()
        self._fail_on = fail_on_substring

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        remote = str(remote_path)
        if self._fail_on in remote:
            raise RuntimeError(f"download failure for {remote}")
        return super().download_tree(remote_path, local_path, include=include, exclude=exclude)


class RunExceptionFakeRunner(FakeRunner):
    """Runner that raises an exception for commands matching a substring."""

    def __init__(self, fail_on_substring: str) -> None:
        super().__init__()
        self._fail_on = fail_on_substring

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if self._fail_on in command:
            raise RuntimeError(f"SSH RuntimeError: {self._fail_on}")
        return RemoteCommandResult(0, f"stdout from {command[:40]}", "", ["ssh", "lab", command])


class RunExceptionUploadFailingFakeRunner(RunExceptionFakeRunner):
    """Runner that fails upload for a specific remote path after the command exception path."""

    def __init__(self, fail_on_substring: str, fail_upload_on_substring: str) -> None:
        super().__init__(fail_on_substring)
        self._fail_upload_on = fail_upload_on_substring

    def upload(self, local_path, remote_path) -> None:
        self.uploads.append((Path(local_path), str(remote_path)))
        if self._fail_upload_on in str(remote_path):
            raise RuntimeError(f"upload failure for {remote_path}")
        return None


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
    assert "spectre command completed" in manifest.get("notes", "")


def test_remote_adapter_applies_request_timeout_to_remote_commands(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["spectre"]["timeout_s"] = 7200
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    manifest_path = run_dir / "real_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["spectre"]["timeout_s"] = 7200
    manifest["metric_extraction_request_sha256"] = sha256_file(request_path)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
    command_timeouts = [
        kwargs.get("timeout_s")
        for command, kwargs in zip(runner.commands, runner.command_kwargs, strict=True)
        if "spectre" in command or "ocean" in command
    ]
    assert command_timeouts == [7200, 7200]


def test_remote_adapter_runs_corner_aware_child_run(tmp_path: Path) -> None:
    from tests.test_spectre_ocean_adapter import _create_ready_corner_project

    project_dir = _create_ready_corner_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
    }
    request = json.loads(
        (
            project_dir
            / "runs"
            / "real"
            / "real_001"
            / "testbenches"
            / "cg_nf"
            / "corners"
            / "ss"
            / "metric_extraction_request.json"
        ).read_text(encoding="utf-8")
    )
    runner.child_metric_units = {
        "cg_nf": {
            metric["name"]: metric["unit"]
            for metric in request["metrics"]
        }
    }
    runner.child_expression_sha256 = {
        "cg_nf": {
            metric["name"]: metric["expression_sha256"]
            for metric in request["metrics"]
        }
    }

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
        testbench_id="cg_nf",
        corner_id="ss",
    )

    assert result.status == "succeeded"
    corner_remote = "/remote/project/runs/real/real_001/testbenches/cg_nf/corners/ss"
    assert any(str(upload[1]).startswith(corner_remote) for upload in runner.uploads)
    manifest = json.loads(result.result_manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("testbench_id") == "cg_nf"
    assert manifest.get("corner_id") == "ss"


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

    assert f"source {quoted_cshrc}" in inner_spectre
    assert f"cd {quoted_input_dir}" in inner_spectre

    assert f"source {quoted_cshrc}" in inner_ocean
    assert f"cd {quoted_project}" in inner_ocean
    assert "-replay" in inner_ocean
    assert "-log" in inner_ocean
    assert "-restore" not in inner_ocean

    # No shell redirects in the csh payload -- diagnostics are captured
    # from RemoteCommandResult.stdout/stderr and written locally instead.
    assert ">" not in inner_spectre
    assert "2>" not in inner_spectre
    assert ">" not in inner_ocean
    assert "2>" not in inner_ocean


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

    # Diagnostics must be written locally even on spectre failure
    assert (run_dir / "spectre.stdout").is_file()
    assert (run_dir / "spectre.stderr").is_file()
    assert "failing spectre" in (run_dir / "spectre.stdout").read_text(encoding="utf-8")
    assert "failing spectre" in (run_dir / "spectre.stderr").read_text(encoding="utf-8")

    # Diagnostics must be uploaded to remote
    spectre_stdout_uploads = [
        (local, remote) for local, remote in runner.uploads
        if str(remote).endswith("spectre.stdout")
    ]
    spectre_stderr_uploads = [
        (local, remote) for local, remote in runner.uploads
        if str(remote).endswith("spectre.stderr")
    ]
    assert len(spectre_stdout_uploads) >= 1
    assert len(spectre_stderr_uploads) >= 1


def test_remote_adapter_spectre_runtime_error_still_writes_local_failure_manifest(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = RunExceptionFakeRunner("spectre")

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    assert (run_dir / "result_manifest.json").is_file()
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "spectre command exception" in "\n".join(result.issues)
    assert "spectre command failed with exception" in (run_dir / "spectre.stdout").read_text(encoding="utf-8")


def test_remote_adapter_upload_failure_does_not_prevent_local_manifest(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = RunExceptionUploadFailingFakeRunner(
        fail_on_substring="spectre",
        fail_upload_on_substring="result_manifest.json",
    )

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    assert (run_dir / "result_manifest.json").is_file()
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert any("failed to upload result manifest" in issue for issue in result.issues)


def test_remote_adapter_download_exception_still_writes_local_manifest(tmp_path: Path) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = DownloadFailingFakeRunner("/psf")

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    assert (run_dir / "result_manifest.json").is_file()
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert any("download" in issue.lower() for issue in result.issues)


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

    # Diagnostics must be written locally even on ocean failure
    assert (run_dir / "metrics" / "ocean.stdout").is_file()
    assert (run_dir / "metrics" / "ocean.stderr").is_file()
    assert "failing ocean" in (run_dir / "metrics" / "ocean.stdout").read_text(encoding="utf-8")
    assert "failing ocean" in (run_dir / "metrics" / "ocean.stderr").read_text(encoding="utf-8")

    # Diagnostics must be uploaded to remote
    ocean_stdout_uploads = [
        (local, remote) for local, remote in runner.uploads
        if str(remote).endswith("ocean.stdout")
    ]
    ocean_stderr_uploads = [
        (local, remote) for local, remote in runner.uploads
        if str(remote).endswith("ocean.stderr")
    ]
    assert len(ocean_stdout_uploads) >= 1
    assert len(ocean_stderr_uploads) >= 1


def test_result_manifest_log_file_points_to_existing_file(tmp_path: Path) -> None:
    """result_manifest.json log_file must reference a file that actually exists."""
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
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    log_file = manifest["log_file"]
    log_path = project_dir / log_file
    assert log_path.is_file(), f"log_file {log_file} does not exist at {log_path}"


def test_spectre_diagnostics_written_on_success_path(tmp_path: Path) -> None:
    """On successful spectre run, spectre.stdout and spectre.stderr must exist locally."""
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
    assert (run_dir / "spectre.stdout").is_file()
    assert (run_dir / "spectre.stderr").is_file()
    assert (run_dir / "metrics" / "ocean.stdout").is_file()
    assert (run_dir / "metrics" / "ocean.stderr").is_file()


class MultiTestbenchFakeRunner(FakeRunner):
    """FakeRunner that writes correct ocean_scalars.tsv per child testbench."""

    def __init__(self) -> None:
        super().__init__()
        self.child_metric_names: dict[str, list[str]] = {}
        # Maps testbench_id -> {metric_name: expression_sha256}
        self.child_expression_sha256: dict[str, dict[str, str]] = {}
        # Maps testbench_id -> {metric_name: unit}
        self.child_metric_units: dict[str, dict[str, str]] = {}
        self._project_dir: Path | None = None

    def set_project_dir(self, project_dir: Path) -> None:
        """Store project_dir so metric metadata can be resolved from metric requests."""
        self._project_dir = project_dir

    def _populate_from_request(self, testbench_id: str) -> None:
        """Auto-populate expression_sha256 and unit from the metric request file."""
        if self._project_dir is None:
            return
        if testbench_id in self.child_expression_sha256 and testbench_id in self.child_metric_units:
            return
        request_path = (
            _prepared_testbench_child_dir(self._project_dir, testbench_id)
            / "metric_extraction_request.json"
        )
        if request_path.is_file():
            import json as _json
            request = _json.loads(request_path.read_text(encoding="utf-8"))
            self.child_expression_sha256[testbench_id] = {
                m["name"]: m["expression_sha256"] for m in request.get("metrics", [])
            }
            self.child_metric_units[testbench_id] = {
                m["name"]: m["unit"] for m in request.get("metrics", [])
            }

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        local = Path(local_path)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (local / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics"):
            metric_names = self._resolve_metric_names(local)
            sha256_map = self._resolve_expression_sha256(local)
            unit_map = self._resolve_metric_units(local)
            header = "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
            rows = "".join(
                f"{name}\t1e-12\t{unit_map.get(name, 's')}\tpass\t{sha256_map.get(name, 'a' * 64)}\t\n"
                for name in metric_names
            )
            (local / "ocean_scalars.tsv").write_text(header + rows, encoding="utf-8")
            (local / "ocean.stdout").write_text("ocean stdout output", encoding="utf-8")
            (local / "ocean.stderr").write_text("", encoding="utf-8")
            (local / "ocean.log").write_text("ocean log output", encoding="utf-8")

    def download(self, remote_path: str, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))
        # Only create the file if the remote path is a plausible artifact
        # location.  This prevents unconditional file creation from masking
        # redirect-placement bugs (e.g. files landing in the SSH session cwd
        # instead of remote_run_dir).
        name = Path(remote_path).name
        parent = str(Path(remote_path).parent)
        parent_stripped = parent.rstrip("/")
        is_run_dir = parent_stripped.endswith("real_001") or "/testbenches/" in parent_stripped
        if name in ("spectre.stdout", "spectre.stderr") and is_run_dir:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(f"content of {name}", encoding="utf-8")
        elif name in ("ocean.stdout", "ocean.stderr", "ocean.log") and parent_stripped.endswith("metrics"):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(f"content of {name}", encoding="utf-8")

    def _resolve_metric_names(self, local_path: Path) -> list[str]:
        parts = local_path.parts
        for i, part in enumerate(parts):
            if part == "testbenches" and i + 1 < len(parts):
                testbench_id = parts[i + 1]
                if testbench_id in self.child_metric_names:
                    return self.child_metric_names[testbench_id]
        request = _request_for_metrics_dir(local_path)
        if request is not None:
            return [str(metric["name"]) for metric in request["metrics"]]
        raise AssertionError(
            f"could not resolve metric names for metrics dir: {local_path}"
        )

    def _resolve_expression_sha256(self, local_path: Path) -> dict[str, str]:
        parts = local_path.parts
        for i, part in enumerate(parts):
            if part == "testbenches" and i + 1 < len(parts):
                testbench_id = parts[i + 1]
                self._populate_from_request(testbench_id)
                if testbench_id in self.child_expression_sha256:
                    return self.child_expression_sha256[testbench_id]
        return {}

    def _resolve_metric_units(self, local_path: Path) -> dict[str, str]:
        parts = local_path.parts
        for i, part in enumerate(parts):
            if part == "testbenches" and i + 1 < len(parts):
                testbench_id = parts[i + 1]
                self._populate_from_request(testbench_id)
                if testbench_id in self.child_metric_units:
                    return self.child_metric_units[testbench_id]
        return {}


def test_remote_multi_testbench_adapter_runs_each_child(tmp_path: Path) -> None:
    from tests.test_multi_testbench_aggregation import (
        _create_ready_multi_testbench_project,
    )

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }
    runner.child_metric_units = {}
    runner.child_expression_sha256 = {}
    for testbench_id in ("cg_nf", "iip3"):
        request_path = (
            _prepared_testbench_child_dir(project_dir, testbench_id)
            / "metric_extraction_request.json"
        )
        request = json.loads(request_path.read_text(encoding="utf-8"))
        runner.child_metric_units[testbench_id] = {
            metric["name"]: metric["unit"]
            for metric in request["metrics"]
        }
        runner.child_expression_sha256[testbench_id] = {
            metric["name"]: metric["expression_sha256"]
            for metric in request["metrics"]
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
    runner.set_project_dir(project_dir)
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
        assert "testbenches/" in inner
        assert "metric_probe.ocn" in inner
        # Verify child testbench path, not top-level metrics path
        assert "/real/real_001/metrics/metric_probe.ocn" not in inner.replace("testbenches/", "")


def test_remote_multi_testbench_adapter_runs_multi_corner_children_serially(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = _create_ready_multi_corner_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }
    runner.child_metric_units = {}
    runner.child_expression_sha256 = {}
    for testbench_id in ("cg_nf", "iip3"):
        request_path = (
            project_dir
            / "runs"
            / "real"
            / "real_001"
            / "testbenches"
            / testbench_id
            / "corners"
            / "tt"
            / "metric_extraction_request.json"
        )
        request = json.loads(request_path.read_text(encoding="utf-8"))
        runner.child_metric_units[testbench_id] = {
            metric["name"]: metric["unit"]
            for metric in request["metrics"]
        }
        runner.child_expression_sha256[testbench_id] = {
            metric["name"]: metric["expression_sha256"]
            for metric in request["metrics"]
        }

    def fake_aggregate(project: Path, *, run_id: str):
        result_path = project / "runs" / "real" / run_id / "result_manifest.json"
        metric_path = (
            project / "runs" / "real" / run_id / "metrics" / "metric_result_manifest.json"
        )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        metric_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text("{\"status\": \"succeeded\"}\n", encoding="utf-8")
        metric_path.write_text("{\"status\": \"succeeded\"}\n", encoding="utf-8")
        return SimpleNamespace(status="succeeded", issues=[])

    monkeypatch.setattr(
        "hermes_workflow.multi_testbench_aggregation.aggregate_multi_testbench_run",
        fake_aggregate,
        raising=False,
    )

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    spectre_cmds = [cmd for cmd in runner.commands if "spectre " in cmd]
    ocean_cmds = [cmd for cmd in runner.commands if "ocean " in cmd]
    assert len(spectre_cmds) == 6
    assert len(ocean_cmds) == 6
    expected_order = [
        "testbenches/cg_nf/corners/tt",
        "testbenches/cg_nf/corners/ff",
        "testbenches/cg_nf/corners/ss",
        "testbenches/iip3/corners/tt",
        "testbenches/iip3/corners/ff",
        "testbenches/iip3/corners/ss",
    ]
    assert [path for path in expected_order if any(path in cmd for cmd in spectre_cmds)] == expected_order
    assert [path for path in expected_order if any(path in cmd for cmd in ocean_cmds)] == expected_order


def test_remote_multi_testbench_adapter_runs_single_testbench_multi_corner_children_serially(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_single_testbench_project(
        tmp_path,
        corner_ids=["tt", "ff", "ss"],
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    for corner_id in ("tt", "ff", "ss"):
        child_dir = project_dir / "runs" / "real" / "real_001" / "corners" / corner_id
        assert (child_dir / "result_manifest.json").is_file()
        assert (child_dir / "metrics" / "metric_result_manifest.json").is_file()
    assert any("/remote/project/runs/real/real_001/corners/tt" in cmd for cmd in runner.commands)
    assert any("/remote/project/runs/real/real_001/corners/ff" in cmd for cmd in runner.commands)
    assert any("/remote/project/runs/real/real_001/corners/ss" in cmd for cmd in runner.commands)


def test_remote_multi_testbench_adapter_preserves_explicit_single_corner_id(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_corner_single_testbench_project(
        tmp_path,
        corner_ids=["ss"],
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    report = json.loads(
        (
            project_dir
            / "runs"
            / "real"
            / "real_001"
            / "multi_testbench_aggregation_report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["objective_policy"] == "worst_case"
    assert report["constraint_policy"] == "all_corners"
    assert report["selected_corner"] == "ss"
    assert report["worst_corner"] == "ss"
    assert any("/remote/project/runs/real/real_001/corners/ss" in cmd for cmd in runner.commands)
    assert not any("/corners/nominal" in cmd for cmd in runner.commands)


def test_remote_multi_testbench_adapter_child_failure_reports_issues(tmp_path: Path) -> None:
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
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
    runner.set_project_dir(project_dir)
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


def test_remote_spectre_command_uses_canonical_local_argv(tmp_path: Path) -> None:
    """Regression C-70: remote spectre must use the same flags as the local adapter.

    The local adapter _spectre_argv includes +escchars, +lqtimeout 900,
    -maxw 5, -maxn 5, -env ade, +logstatus, and +log ../psf/spectre.out.
    It reads preset from context.request.spectre, not hardcoded.
    The C-69 remote adapter hardcodes +preset=aps and omits all those flags.
    """
    project_dir = create_approved_real_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    spectre_cmd = next(c for c in runner.commands if "spectre" in c)
    inner = shlex.split(spectre_cmd)[2]

    # Preset must come from the configured request, not be hardcoded
    context = load_adapter_context(project_dir, run_id="real_001")
    expected_preset = context.request.spectre["preset"]
    assert f"+preset={expected_preset}" in inner, (
        f"spectre command must use configured preset +preset={expected_preset}, "
        f"not hardcoded +preset=aps"
    )

    # All local adapter flags must be present
    for flag in ("+escchars", "+lqtimeout", "-maxw", "-maxn", "-env ade", "+logstatus"):
        assert flag in inner, f"local adapter flag missing from remote spectre command: {flag}"

    # Local adapter includes +log ../psf/spectre.out
    assert "+log" in inner, "remote spectre command must include +log for spectre.out"


def test_remote_ocean_command_uses_replay_not_restore(tmp_path: Path) -> None:
    """Regression C-70: remote ocean must use -replay/-log, not -restore.

    The local adapter _ocean_argv uses: ocean -nograph -replay <script> -log <log>
    The C-69 remote adapter uses: ocean -nograph -restore <metric_probe.ocn>
    """
    project_dir = create_approved_real_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    ocean_cmd = next(c for c in runner.commands if "ocean" in c)
    inner = shlex.split(ocean_cmd)[2]

    assert "-replay" in inner, "remote ocean must use -replay, not -restore"
    assert "-log" in inner, "remote ocean must include -log for ocean.log"
    assert "-restore" not in inner, "remote ocean must not use -restore"


class NoPsfFakeRunner(FakeRunner):
    """FakeRunner that succeeds but does not create PSF artifacts locally.

    This simulates the case where remote spectre succeeds but the psf/
    directory is not present locally (e.g. download failed silently).
    Metrics and log files are still created so the failure is specifically
    about the missing PSF directory.
    """

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            # Do NOT create spectre.out -- simulate missing PSF artifacts
            pass
        elif remote.endswith("/metrics"):
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout output", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log output", encoding="utf-8")


def test_remote_adapter_fails_when_psf_artifacts_missing(tmp_path: Path) -> None:
    """Regression C-70: adapter must fail if PSF artifacts are not present locally.

    When remote spectre returns success but psf/ and psf/spectre.out are not
    downloaded, the adapter must not write a success result manifest.
    The C-69 adapter skips PSF download and writes a success manifest anyway.
    """
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = NoPsfFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed", (
        "adapter must fail when psf/spectre.out artifacts are missing"
    )
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed", (
        "result_manifest must report failed when PSF artifacts are missing"
    )


class MetricFailFakeRunner(FakeRunner):
    """FakeRunner that writes ocean_scalars.tsv with a metric row marked fail.

    The last metric from the project's metric_extraction_request.json is the
    one marked fail.  A resolvable metric request is required; the legacy
    hardcoded fallback rows have been removed.
    """

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics"):
            request = _request_for_metrics_dir(Path(local_path))
            if request is None:
                raise AssertionError(
                    "MetricFailFakeRunner requires a resolvable metric_extraction_request"
                )
            metrics = request["metrics"]
            failing = metrics[-1]["name"]
            rows = "".join(
                f"{metric['name']}\t\t{metric['unit']}\t"
                f"{'fail' if metric['name'] == failing else 'pass'}\t"
                f"{metric['expression_sha256']}\t\n"
                for metric in metrics
            )
            tsv = "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n" + rows
            (Path(local_path) / "ocean_scalars.tsv").write_text(tsv, encoding="utf-8")
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout output", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log output", encoding="utf-8")


def test_remote_adapter_propagates_metric_failure(tmp_path: Path) -> None:
    """Regression C-70: metric failures in ocean_scalars.tsv must propagate.

    When ocean_scalars.tsv contains a requested metric row with status=fail,
    the metric result manifest must have status=failed, and the adapter
    result must have status=failed.
    The C-69 adapter does not propagate metric row failures.
    """
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MetricFailFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    # result_manifest reports spectre status (succeeded), not metric status.
    # Metric failures are recorded in metric_result_manifest instead.
    assert manifest["status"] == "succeeded", (
        "result_manifest must report succeeded when spectre succeeded (metric failure is in metric_result_manifest)"
    )

    metric_manifest = json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    assert metric_manifest["status"] == "failed", (
        "metric_result_manifest must report failed when a metric row has status=fail"
    )
    failing_name = _metric_names(project_dir)[-1]
    failed_metric = next(m for m in metric_manifest["metrics"] if m["name"] == failing_name)
    assert failed_metric["status"] == "failed", (
        "individual metric with status=fail in TSV must be marked failed in manifest"
    )

    assert result.status == "failed", (
        "adapter result must be failed when a metric row has status=fail"
    )
    assert any(failing_name in issue for issue in result.issues), (
        "adapter issues must mention the failing metric name"
    )


class OceanFailNoScalarsFakeRunner(FakeRunner):
    """FakeRunner where OCEAN fails all attempts and ocean_scalars.tsv is missing.

    Simulates the case where remote OCEAN crashes without producing output,
    but diagnostic files (ocean.stdout, ocean.stderr, ocean.log) are still
    captured by the shell redirect.
    """

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if "ocean" in command:
            return RemoteCommandResult(
                1,
                "ocean crash stdout output",
                "ocean crash stderr output",
                ["ssh", "lab", command],
            )
        return RemoteCommandResult(0, "spectre stdout output", "", ["ssh", "lab", command])

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics"):
            # Do NOT create ocean_scalars.tsv -- OCEAN failed to produce it
            (Path(local_path) / "ocean.stdout").write_text("ocean crash output", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("ocean error", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log", encoding="utf-8")


def test_remote_adapter_writes_metric_manifest_when_ocean_fails_without_scalars(tmp_path: Path) -> None:
    """C-70 parity: OCEAN failure without scalars must still write metric manifest.

    When OCEAN fails all OCEAN_MAX_ATTEMPTS and ocean_scalars.tsv is missing,
    the local adapter still writes metric_result_manifest (recording ocean
    command failed), then result_manifest with status=succeeded and
    include_metric_manifest=True.  The remote adapter must match.
    """
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = OceanFailNoScalarsFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    # Adapter result must be failed
    assert result.status == "failed"
    assert any("ocean" in issue.lower() for issue in result.issues)

    # metric_result_manifest must exist and record ocean failure
    metric_manifest_path = run_dir / "metrics" / "metric_result_manifest.json"
    assert metric_manifest_path.is_file(), "metric_result_manifest.json must be written even when ocean fails"
    metric_manifest = json.loads(metric_manifest_path.read_text(encoding="utf-8"))
    assert metric_manifest["status"] == "failed"
    assert any("ocean command failed" in issue for issue in metric_manifest.get("issues", []))
    assert metric_manifest["ocean"]["return_code"] != 0
    assert len(metric_manifest["ocean"]["return_codes"]) > 1  # retried

    # result_manifest must say succeeded (spectre succeeded) with metric manifest ref
    result_manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert result_manifest["status"] == "succeeded", (
        "result_manifest must report succeeded when spectre succeeded "
        "(ocean failure is recorded in metric_result_manifest)"
    )
    assert result_manifest["metric_result_manifest"] is not None

    # Both manifests must be uploaded
    metric_uploads = [r for _, r in runner.uploads if "metric_result_manifest" in r]
    result_uploads = [r for _, r in runner.uploads if r.endswith("result_manifest.json")]
    assert len(metric_uploads) >= 1
    assert len(result_uploads) >= 1


def test_remote_multi_testbench_writes_ocean_scripts_under_project_dir(tmp_path: Path) -> None:
    """Regression: child metric_probe.ocn files must be under project_dir, not cwd."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path / "project")
    separate_cwd = tmp_path / "other_cwd"
    separate_cwd.mkdir()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
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
            _prepared_testbench_child_dir(project_dir, tb_id)
            / "metrics"
            / "metric_probe.ocn"
        )
        assert expected.is_file(), f"metric_probe.ocn missing for {tb_id}: {expected}"
        wrong = separate_cwd / expected.relative_to(project_dir)
        assert not wrong.exists(), f"metric_probe.ocn leaked to cwd for {tb_id}: {wrong}"


def test_remote_multi_testbench_adapter_metric_failure_propagates(tmp_path: Path) -> None:
    """When a child ocean produces a metric row with status=fail, the multi-testbench
    adapter must propagate the failure through aggregation."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
    runner.child_metric_names = {
        "cg_nf": ["MAX_GAIN"],
        "iip3": ["IIP3"],
    }

    # Make iip3 ocean produce a failing metric row
    def metric_fail_download_tree(remote_path, local_path, include=None, exclude=None):
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics") and "iip3" in remote:
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
                "IIP3\t\tdBm\tfail\t" + "a" * 64 + "\tmetric extraction failed\n",
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log", encoding="utf-8")
        elif remote.endswith("/metrics"):
            # cg_nf succeeds
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
                "MAX_GAIN\tdB\tdB\tpass\t" + "b" * 64 + "\t\n",
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log", encoding="utf-8")

    runner.download_tree = metric_fail_download_tree

    result = run_remote_multi_testbench_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    # The child adapter for iip3 should return failed due to metric failure,
    # and the multi-testbench adapter must propagate that.
    assert result.status == "failed"
    assert any("iip3" in issue for issue in result.issues)


def test_remote_multi_testbench_adapter_aggregate_manifest_content(tmp_path: Path) -> None:
    """Verify the aggregate manifest contains metrics from ALL children."""
    import json as _json

    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
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

    run_dir = project_dir / "runs" / "real" / "real_001"

    # Aggregate metric manifest must contain metrics from both children
    metric_manifest = _json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    metric_names = [m["name"] for m in metric_manifest["metrics"]]
    assert "MAX_GAIN" in metric_names, "aggregate must include cg_nf metric"
    assert "IIP3" in metric_names, "aggregate must include iip3 metric"

    # Aggregate result manifest must reference both child results
    result_manifest = _json.loads(
        (run_dir / "result_manifest.json").read_text(encoding="utf-8")
    )
    child_testbenches = [c["testbench"] for c in result_manifest.get("child_results", [])]
    assert "cg_nf" in child_testbenches, "aggregate result must reference cg_nf child"
    assert "iip3" in child_testbenches, "aggregate result must reference iip3 child"

    # Aggregate metric manifest must reference both child metric results
    child_metric_testbenches = [
        c["testbench"] for c in metric_manifest.get("child_metric_results", [])
    ]
    assert "cg_nf" in child_metric_testbenches
    assert "iip3" in child_metric_testbenches


def test_remote_multi_testbench_adapter_does_not_multiply_parallel_jobs(tmp_path: Path) -> None:
    """Verify the multi-testbench adapter does not multiply spectre.parallel_jobs
    by the number of testbenches. Each child runs with its own configured resources."""
    from tests.test_multi_testbench_aggregation import _create_ready_multi_testbench_project

    project_dir = _create_ready_multi_testbench_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = MultiTestbenchFakeRunner()
    runner.set_project_dir(project_dir)
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

    # The spectre commands should each have the same thread count from the
    # configured request, not a multiplied value.
    spectre_cmds = [c for c in runner.commands if "spectre" in c and "csh" in c]
    assert len(spectre_cmds) == 2

    # Read the expected thread count from the project config.
    spectre_cfg = yaml.safe_load(
        (project_dir / "config" / "spectre.yaml").read_text(encoding="utf-8")
    )
    expected_threads = spectre_cfg["spectre"]["threads_per_run"]

    # Extract the inner csh payload for each spectre command and verify
    # +mt= matches the configured value (not multiplied by testbench count).
    for cmd in spectre_cmds:
        inner = shlex.split(cmd)[2]
        assert f"+mt={expected_threads}" in inner, (
            f"expected +mt={expected_threads} in spectre command, got: {inner}"
        )


def test_remote_adapter_accepts_missing_parallel_jobs_in_spectre_contract(
    tmp_path: Path,
) -> None:
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    # Sanity: prepared real_run already drops parallel_jobs from spectre blocks.
    manifest = json.loads((run_dir / "real_run_manifest.json").read_text(encoding="utf-8"))
    request = json.loads(
        (run_dir / "metric_extraction_request.json").read_text(encoding="utf-8")
    )
    assert "parallel_jobs" not in manifest["spectre"]
    assert "parallel_jobs" not in request["spectre"]

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


# ── B-10: remote command_trace tests (RED first) ──────────────────────


def test_remote_success_result_manifest_has_command_trace(tmp_path: Path) -> None:
    """B-10: remote success result_manifest must contain command_trace."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert "command_trace" in manifest, "result_manifest must contain command_trace"
    ct = manifest["command_trace"]
    assert ct["schema_version"] == "1.0"
    assert ct["execution_mode"] == "remote"
    assert "spectre" in ct
    spectre_trace = ct["spectre"]
    assert isinstance(spectre_trace["argv"], list)
    assert spectre_trace["argv"][0] == "spectre"
    assert spectre_trace["timeout_s"] > 0
    # command is the sanitized shell-joined body (no csh wrapper, no cshrc)
    assert isinstance(spectre_trace["command"], str)
    assert "spectre" in spectre_trace["command"]
    # Must not leak cshrc content or raw SSH command
    assert "source" not in spectre_trace["command"]
    assert "ssh" not in spectre_trace["command"]


def test_remote_success_metric_manifest_has_command_trace(tmp_path: Path) -> None:
    """B-10: remote success metric_result_manifest must contain command_trace."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    metric_manifest = json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    assert "command_trace" in metric_manifest, (
        "metric_result_manifest must contain command_trace"
    )
    ct = metric_manifest["command_trace"]
    assert ct["schema_version"] == "1.0"
    assert ct["execution_mode"] == "remote"
    assert "ocean" in ct
    ocean_trace = ct["ocean"]
    assert isinstance(ocean_trace["argv"], list)
    assert ocean_trace["argv"][0] == "ocean"
    assert ocean_trace["mode"] == "nograph_replay"
    assert ocean_trace["timeout_s"] > 0
    assert isinstance(ocean_trace["command"], str)
    assert "ocean" in ocean_trace["command"]
    # Must not leak cshrc content or raw SSH command
    assert "source" not in ocean_trace["command"]
    assert "ssh" not in ocean_trace["command"]


def test_remote_command_trace_timeout_s_comes_from_request(tmp_path: Path) -> None:
    """B-10: remote command_trace.timeout_s must match request timeout."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["spectre"]["timeout_s"] = 7200
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    manifest_path = run_dir / "real_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["spectre"]["timeout_s"] = 7200
    manifest["metric_extraction_request_sha256"] = sha256_file(request_path)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    result_manifest = json.loads(
        (run_dir / "result_manifest.json").read_text(encoding="utf-8")
    )
    assert result_manifest["command_trace"]["spectre"]["timeout_s"] == 7200

    metric_manifest = json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    assert metric_manifest["command_trace"]["ocean"]["timeout_s"] == 7200


def test_remote_command_trace_does_not_leak_cshrc_or_ssh(tmp_path: Path) -> None:
    """B-10: command_trace must not contain cshrc content or SSH raw command."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    cshrc = PurePosixPath("/remote/project/cadence_env.csh")
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=cshrc,
        runner=runner,
    )

    result_manifest = json.loads(
        (run_dir / "result_manifest.json").read_text(encoding="utf-8")
    )
    metric_manifest = json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    for manifest, label in [
        (result_manifest, "result_manifest"),
        (metric_manifest, "metric_result_manifest"),
    ]:
        ct_str = json.dumps(manifest.get("command_trace", {}))
        # Must not contain the cshrc path or content
        assert str(cshrc) not in ct_str, (
            f"command_trace in {label} must not contain cshrc path"
        )
        assert "source " not in ct_str, (
            f"command_trace in {label} must not contain cshrc source directive"
        )
        # Must not contain raw SSH command
        assert "ssh " not in ct_str, (
            f"command_trace in {label} must not contain SSH command"
        )
        # Must not contain csh wrapper
        assert "csh -fc" not in ct_str, (
            f"command_trace in {label} must not contain csh -fc wrapper"
        )
        # Must not contain parallel_jobs
        assert "parallel_jobs" not in ct_str, (
            f"command_trace in {label} must not contain parallel_jobs"
        )


def test_remote_spectre_failure_still_writes_command_trace(tmp_path: Path) -> None:
    """B-10: remote Spectre failure must still write command_trace in result manifest."""
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
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert "command_trace" in manifest, (
        "remote failure result_manifest must still contain command_trace"
    )
    ct = manifest["command_trace"]
    assert ct["execution_mode"] == "remote"
    assert "spectre" in ct
    spectre_trace = ct["spectre"]
    assert isinstance(spectre_trace["argv"], list)
    assert spectre_trace["argv"][0] == "spectre"


def test_remote_spectre_runtime_error_still_writes_command_trace(tmp_path: Path) -> None:
    """B-10: remote Spectre runtime exception must still write command_trace."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = RunExceptionFakeRunner("spectre")

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert "command_trace" in manifest, (
        "remote spectre exception result_manifest must contain command_trace"
    )
    ct = manifest["command_trace"]
    assert ct["execution_mode"] == "remote"
    assert "spectre" in ct


def test_remote_upload_failure_still_writes_command_trace(tmp_path: Path) -> None:
    """B-10: remote upload failure must still write command_trace."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class UploadFailRunner(FakeRunner):
        def upload_tree(self, local_path, remote_path, include=None, exclude=None):
            raise RuntimeError("upload failed")

    runner = UploadFailRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert "command_trace" in manifest, (
        "remote upload failure result_manifest must contain command_trace"
    )
    ct = manifest["command_trace"]
    assert ct["execution_mode"] == "remote"


def test_remote_psf_missing_still_writes_command_trace(tmp_path: Path) -> None:
    """B-10: remote PSF artifacts missing must still write command_trace."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = NoPsfFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    manifest = json.loads((run_dir / "result_manifest.json").read_text(encoding="utf-8"))
    assert "command_trace" in manifest, (
        "remote PSF missing result_manifest must contain command_trace"
    )
    ct = manifest["command_trace"]
    assert ct["execution_mode"] == "remote"
    assert "spectre" in ct


def test_remote_ocean_failure_writes_command_trace(tmp_path: Path) -> None:
    """B-10: remote OCEAN failure must write command_trace in metric manifest."""
    project_dir = create_approved_real_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = OceanFailNoScalarsFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "failed"
    # metric_result_manifest must have command_trace with ocean sub-object
    metric_manifest = json.loads(
        (run_dir / "metrics" / "metric_result_manifest.json").read_text(encoding="utf-8")
    )
    assert "command_trace" in metric_manifest, (
        "remote OCEAN failure metric_result_manifest must contain command_trace"
    )
    ct = metric_manifest["command_trace"]
    assert ct["execution_mode"] == "remote"
    assert "ocean" in ct
    ocean_trace = ct["ocean"]
    assert isinstance(ocean_trace["return_code"], int)
    assert ocean_trace["return_code"] != 0
    assert isinstance(ocean_trace["return_codes"], list)
    assert len(ocean_trace["return_codes"]) > 0
