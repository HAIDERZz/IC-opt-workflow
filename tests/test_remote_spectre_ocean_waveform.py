"""Tests for remote Spectre/OCEAN adapter waveform CSV and manifest downloads.

These tests verify that the remote adapter:
1. Downloads metrics/waveforms/*.csv when present on the remote
2. Downloads metrics/waveform_export_manifest.json when present on the remote
3. Handles missing waveform artifacts gracefully (no error when no waveform exports)
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from hermes_workflow.remote_project import RemoteProjectRef

# Import shared test helpers from the existing test_remote_spectre_ocean module
from tests.test_remote_spectre_ocean import (
    FakeRunner,
    _ocean_scalars_tsv,
    _request_for_metrics_dir,
    create_approved_real_project,
)
from hermes_workflow.execution_adapters.remote_spectre_ocean import (
    run_remote_spectre_ocean_adapter,
)


class WaveformFakeRunner(FakeRunner):
    """FakeRunner that also creates waveform CSV files and manifest during download."""

    def __init__(self, *, include_waveforms: bool = True, include_manifest: bool = True) -> None:
        super().__init__()
        self.include_waveforms = include_waveforms
        self.include_manifest = include_manifest

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics/waveforms"):
            if self.include_waveforms:
                # Create waveform CSV files
                (Path(local_path) / "gain_phase.csv").write_text(
                    "freq,gain,phase\n1e6,10.5,45.0\n",
                    encoding="utf-8",
                )
                (Path(local_path) / "bw.csv").write_text(
                    "freq,magnitude\n1e6,0.707\n",
                    encoding="utf-8",
                )
        elif remote.endswith("/metrics"):
            # Standard metrics
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout output", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log output", encoding="utf-8")

    def download(self, remote_path: str, local_path: Path) -> None:
        self.downloads.append((str(remote_path), local_path))
        name = Path(remote_path).name
        parent = str(Path(remote_path).parent)
        if name == "waveform_export_manifest.json" and parent.rstrip("/").endswith("metrics"):
            if self.include_manifest:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(
                    json.dumps({
                        "schema_version": "1.0",
                        "workflow_mode": "fix_run",
                        "run_id": "real_001",
                        "candidate_id": "user_point_001",
                        "testbench_id": "default",
                        "corner_id": "tt",
                        "model_section": "Post_simu_top_tt",
                        "corner_variables": {"temperature": "27"},
                        "parameters": {"FN": "2", "WN": "0.3u"},
                        "exports": [
                            {
                                "name": "gain_phase",
                                "expression": "getData(\"/out\" ?result \"tran-tran\")",
                                "expression_sha256": "abc123",
                                "output_format": "csv",
                                "csv_path": "metrics/waveforms/gain_phase.csv",
                                "status": "pass",
                                "issues": [],
                            }
                        ],
                        "psf_dir": "psf",
                        "ocean_log": "metrics/ocean.log",
                    }, indent=2) + "\n",
                    encoding="utf-8",
                )
        elif name in ("ocean.log",) and parent.rstrip("/").endswith("metrics"):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(f"content of {name}", encoding="utf-8")


class NoWaveformFakeRunner(FakeRunner):
    """FakeRunner where waveform artifacts are NOT present on remote.

    The download_tree for metrics/waveforms and download for waveform_export_manifest.json
    will raise RuntimeError to simulate the remote not having these artifacts.
    """

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        remote = str(remote_path)
        if remote.endswith("/metrics/waveforms"):
            # Simulate: waveform dir does not exist on remote
            raise RuntimeError(f"remote directory not found: {remote_path}")
        return super().download_tree(remote_path, local_path, include=include, exclude=exclude)

    def download(self, remote_path: str, local_path: Path) -> None:
        name = Path(remote_path).name
        if name == "waveform_export_manifest.json":
            # Simulate: file does not exist on remote
            raise RuntimeError(f"remote file not found: {remote_path}")
        return super().download(remote_path, local_path)


# ---------------------------------------------------------------------------
# Test 1: Remote adapter downloads waveform CSV files when present
# ---------------------------------------------------------------------------
def test_remote_adapter_downloads_waveform_csv_files_when_present(tmp_path: Path) -> None:
    """When remote metrics/waveforms/ contains CSV files, the adapter must
    download them to the local metrics/waveforms/ directory."""
    project_dir = create_approved_real_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformFakeRunner(include_waveforms=True, include_manifest=True)

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    # Check that waveforms directory was downloaded
    waveforms_downloads = [
        (remote, local) for remote, local in runner.downloads
        if "waveforms" in remote
    ]
    assert len(waveforms_downloads) >= 1, "waveforms directory must be downloaded"

    # Verify the local waveforms directory exists and has CSV files
    run_dir = project_dir / "runs" / "real" / "real_001"
    local_waveforms_dir = run_dir / "metrics" / "waveforms"
    assert local_waveforms_dir.is_dir(), "waveforms directory must exist locally"
    csv_files = list(local_waveforms_dir.glob("*.csv"))
    assert len(csv_files) >= 1, "waveform CSV files must be present locally"


# ---------------------------------------------------------------------------
# Test 2: Remote adapter downloads waveform export manifest when present
# ---------------------------------------------------------------------------
def test_remote_adapter_downloads_waveform_export_manifest_when_present(tmp_path: Path) -> None:
    """When remote metrics/waveform_export_manifest.json exists, the adapter
    must download it to the local metrics/ directory."""
    project_dir = create_approved_real_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformFakeRunner(include_waveforms=True, include_manifest=True)

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded"
    # Check that waveform_export_manifest.json was downloaded
    manifest_downloads = [
        remote for remote, local in runner.downloads
        if "waveform_export_manifest.json" in remote
    ]
    assert len(manifest_downloads) >= 1, "waveform_export_manifest.json must be downloaded"

    # Verify the local manifest file exists
    run_dir = project_dir / "runs" / "real" / "real_001"
    local_manifest = run_dir / "metrics" / "waveform_export_manifest.json"
    assert local_manifest.is_file(), "waveform_export_manifest.json must exist locally"
    manifest_data = json.loads(local_manifest.read_text(encoding="utf-8"))
    assert manifest_data["schema_version"] == "1.0"
    assert "exports" in manifest_data


# ---------------------------------------------------------------------------
# Test 3: Remote adapter handles missing waveform artifacts gracefully
# ---------------------------------------------------------------------------
def test_remote_adapter_handles_missing_waveform_artifacts_gracefully(tmp_path: Path) -> None:
    """When waveform artifacts are not present on the remote, the adapter must
    NOT treat it as an error. The adapter should still succeed."""
    project_dir = create_approved_real_project(tmp_path)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = NoWaveformFakeRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    # The adapter must still succeed - missing waveform artifacts is not an error
    assert result.status == "succeeded"
    # No waveform-related issues should be present
    assert not any("waveform" in issue.lower() for issue in result.issues)


# ---------------------------------------------------------------------------
# B-FIXRUN remote: the remote OCEAN run produces the waveform CSV, but the
# waveform_export_manifest.json is a Python-side artifact the remote never
# writes. The remote adapter must GENERATE it locally (reusing the local
# helper) and upload it, so the fix-run artifact gate can find it.
# ---------------------------------------------------------------------------
class WaveformCsvOnlyRunner(FakeRunner):
    """Simulates the real remote failure: OCEAN writes the waveform CSV to
    metrics/waveforms/ remotely, but the remote never writes
    waveform_export_manifest.json. The download of the manifest must be a
    no-op (file not found on remote)."""

    def download_tree(self, remote_path, local_path, include=None, exclude=None) -> None:
        self.downloads.append((str(remote_path), Path(local_path)))
        Path(local_path).mkdir(parents=True, exist_ok=True)
        remote = str(remote_path)
        if remote.endswith("/psf"):
            (Path(local_path) / "spectre.out").write_text("spectre output", encoding="utf-8")
        elif remote.endswith("/metrics/waveforms"):
            # Remote OCEAN wrote the CSV.
            (Path(local_path) / "nf_pnoise.csv").write_text(
                "freq,nf\n1e6,10.5\n", encoding="utf-8"
            )
        elif remote.endswith("/metrics"):
            (Path(local_path) / "ocean_scalars.tsv").write_text(
                _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
                encoding="utf-8",
            )
            (Path(local_path) / "ocean.stdout").write_text("ocean stdout", encoding="utf-8")
            (Path(local_path) / "ocean.stderr").write_text("", encoding="utf-8")
            (Path(local_path) / "ocean.log").write_text("ocean log", encoding="utf-8")

    def download(self, remote_path: str, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))
        # Manifest does NOT exist on remote -> no-op (real failure shape).
        name = Path(remote_path).name
        parent = str(Path(remote_path).parent)
        if name == "ocean.log" and parent.rstrip("/").endswith("metrics"):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text("content of ocean.log", encoding="utf-8")
        # waveform_export_manifest.json: deliberately NOT created.


def _add_waveform_exports(project_dir: Path) -> None:
    """Add a waveform_exports entry to the metric extraction request and
    refresh the manifest hash, mirroring the local adapter test helper."""
    from hermes_workflow.metric_requests import expression_sha256
    from tests.test_spectre_ocean_adapter import (
        _load_json,
        _write_json,
        _refresh_metric_request_hash,
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    expression = 'getData("NF" ?result "pnoise")'
    request["waveform_exports"] = [
        {
            "name": "nf_pnoise",
            "testbench": "cg_nf",
            "expression": expression,
            "expression_sha256": expression_sha256(expression),
            "output_format": "csv",
            "nil_policy": "fail",
            "csv_output_file": "runs/real/real_001/metrics/waveforms/nf_pnoise.csv",
        }
    ]
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)


def test_remote_adapter_generates_waveform_manifest_when_absent_on_remote(
    tmp_path: Path,
) -> None:
    """Reproduces the real remote failure: remote OCEAN wrote the CSV, but the
    remote never wrote waveform_export_manifest.json. The remote adapter must
    GENERATE the manifest locally (reusing the local helper) so the fix-run
    artifact gate finds it."""
    project_dir = create_approved_real_project(tmp_path)
    _add_waveform_exports(project_dir)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformCsvOnlyRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded", result.issues
    run_dir = project_dir / "runs" / "real" / "real_001"
    local_manifest = run_dir / "metrics" / "waveform_export_manifest.json"
    assert local_manifest.is_file(), (
        "remote adapter must generate waveform_export_manifest.json locally "
        "when the remote did not produce it"
    )
    manifest_data = json.loads(local_manifest.read_text(encoding="utf-8"))
    assert manifest_data["schema_version"] == "1.0"
    assert manifest_data["workflow_mode"] == "fix_run"
    assert manifest_data["run_id"] == "real_001"
    assert manifest_data["exports"], "manifest must list waveform exports"
    export = manifest_data["exports"][0]
    assert export["name"] == "nf_pnoise"
    assert export["expression"] == 'getData("NF" ?result "pnoise")'
    assert export["csv_path"].endswith("waveforms/nf_pnoise.csv")
    assert export["status"] == "pass"


def test_remote_waveform_manifest_schema_matches_local_helper(
    tmp_path: Path,
) -> None:
    """The remote-generated manifest must carry the same fields the local
    adapter writes (CSV path, expression, name, run/corner context,
    command_trace). Locks in local/remote schema parity."""
    project_dir = create_approved_real_project(tmp_path)
    _add_waveform_exports(project_dir)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformCsvOnlyRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded", result.issues
    run_dir = project_dir / "runs" / "real" / "real_001"
    manifest_data = json.loads(
        (run_dir / "metrics" / "waveform_export_manifest.json").read_text("utf-8")
    )
    required_top = {
        "schema_version",
        "workflow_mode",
        "run_id",
        "candidate_id",
        "testbench_id",
        "corner_id",
        "model_section",
        "corner_variables",
        "parameters",
        "exports",
        "psf_dir",
        "ocean_log",
        "command_trace",
    }
    assert required_top.issubset(manifest_data.keys()), (
        f"manifest missing keys: {required_top - set(manifest_data.keys())}"
    )
    export = manifest_data["exports"][0]
    required_export = {
        "name",
        "expression",
        "expression_sha256",
        "output_format",
        "csv_path",
        "status",
        "issues",
    }
    assert required_export.issubset(export.keys())


def test_remote_waveform_manifest_command_trace_does_not_leak_cshrc(
    tmp_path: Path,
) -> None:
    """The manifest command_trace must be sanitized: no cshrc path, no
    'source', no 'csh -fc' wrapper."""
    project_dir = create_approved_real_project(tmp_path)
    _add_waveform_exports(project_dir)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformCsvOnlyRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded", result.issues
    run_dir = project_dir / "runs" / "real" / "real_001"
    manifest_data = json.loads(
        (run_dir / "metrics" / "waveform_export_manifest.json").read_text("utf-8")
    )
    trace_json = json.dumps(manifest_data.get("command_trace", {}))
    assert "cadence_env.csh" not in trace_json
    assert "source " not in trace_json
    assert "csh -fc" not in trace_json


def test_remote_adapter_uploads_generated_waveform_manifest(tmp_path: Path) -> None:
    """The locally-generated manifest must be uploaded back to the remote so
    the remote project tree is self-consistent."""
    project_dir = create_approved_real_project(tmp_path)
    _add_waveform_exports(project_dir)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = WaveformCsvOnlyRunner()

    result = run_remote_spectre_ocean_adapter(
        project_dir,
        run_id="real_001",
        remote_ref=ref,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        runner=runner,
    )

    assert result.status == "succeeded", result.issues
    manifest_uploads = [
        str(remote) for _local, remote in runner.uploads
        if "waveform_export_manifest.json" in str(remote)
    ]
    assert manifest_uploads, (
        "generated waveform_export_manifest.json must be uploaded to remote"
    )
