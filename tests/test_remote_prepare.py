from __future__ import annotations

from pathlib import Path, PurePosixPath

import shlex
import shutil

import pytest
import yaml

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


class MaestroProbeRunner(FakeRunner):
    def __init__(self, return_code: int, stderr: str = "") -> None:
        super().__init__()
        self.return_code = return_code
        self.stderr = stderr

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        if command == "test -f /remote/maestro/point_1/netlist/input.scs":
            self.commands_run.append(command)
            return RemoteCommandResult(
                self.return_code,
                "",
                self.stderr,
                ["ssh", "lab", command],
            )
        return super().run(command, **kwargs)


def test_prepare_remote_project_cache_writes_local_controller_project(tmp_path: Path) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FakeRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    assert result.requirement_report.status == "pass"
    assert result.preparation_report.status == "pass"
    assert (result.cache_dir / "opt_requirement.md").is_file()
    assert (result.cache_dir / "constraints.md").is_file()
    assert (result.cache_dir / "config" / "optimizer.yaml").is_file()
    assert (result.cache_dir / "reports" / "requirement_intake_report.json").is_file()
    assert runner.downloads == [
        ("/remote/maestro/point_1/netlist", result.cache_dir / "netlists" / "exported")
    ]
    assert any("readlink -f" in cmd and "netlist" in cmd for cmd in runner.commands_run)


@pytest.mark.parametrize(
    ("return_code", "expected_status"),
    [(0, "pass"), (1, "fail")],
)
def test_prepare_remote_project_cache_maestro_probe_maps_test_f_exit_codes(
    tmp_path: Path,
    return_code: int,
    expected_status: str,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    result = prepare_remote_project_cache(
        ref,
        runner=MaestroProbeRunner(return_code),
        cache_root=tmp_path,
    )

    assert result.status == expected_status
    if return_code == 1:
        assert any(
            "maestro_point_root/netlist/input.scs is missing" in issue
            for issue in result.issues
        )


def test_prepare_remote_project_cache_maestro_probe_raises_transport_error(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    with pytest.raises(RuntimeError, match="ssh transport timed out"):
        prepare_remote_project_cache(
            ref,
            runner=MaestroProbeRunner(255, "ssh transport timed out"),
            cache_root=tmp_path,
        )


def test_prepare_remote_project_cache_replaces_stale_snapshot_files(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    first_runner = FakeRunner()
    first = prepare_remote_project_cache(
        ref,
        runner=first_runner,
        cache_root=tmp_path,
    )
    stale_netlist = first.cache_dir / "netlists" / "exported" / "stale.inc"
    stale_netlist.write_text("stale\n", encoding="utf-8")

    class NoConstraintsRunner(FakeRunner):
        def run(self, command: str, **kwargs: object):
            if command == "test -f /remote/project/constraints.md":
                return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
            return super().run(command, **kwargs)

        def read_text(self, remote_path: PurePosixPath | str) -> str:
            if str(remote_path) == "/remote/project/constraints.md":
                raise FileNotFoundError(str(remote_path))
            return super().read_text(remote_path)

    second = prepare_remote_project_cache(
        ref,
        runner=NoConstraintsRunner(),
        cache_root=tmp_path,
    )

    assert second.status == "pass"
    assert not (second.cache_dir / "constraints.md").exists()
    assert not stale_netlist.exists()


def test_prepare_remote_project_cache_fails_closed_on_constraints_read_error(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class BrokenConstraintsRunner(FakeRunner):
        def read_text(self, remote_path: PurePosixPath | str) -> str:
            if str(remote_path) == "/remote/project/constraints.md":
                raise RuntimeError("ssh transport failed")
            return super().read_text(remote_path)

    with pytest.raises(RuntimeError, match="ssh transport failed"):
        prepare_remote_project_cache(
            ref,
            runner=BrokenConstraintsRunner(),
            cache_root=tmp_path,
        )


def test_prepare_remote_project_cache_materializes_history_warm_start_sources(
    tmp_path: Path,
) -> None:
    history_requirement = VALID_REQUIREMENT.replace(
        "## Approval Checklist",
        """## History Warm Start

```yaml
enabled: true
sources:
  - path: /remote/history/round1
    label: round1
max_observations: 20
warm_start_strategy: topk
```

## Approval Checklist""",
    )

    class HistoryRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.file_downloads: list[tuple[str, Path]] = []

        def read_text(self, remote_path: PurePosixPath | str) -> str:
            if str(remote_path) == "/remote/project/opt_requirement.md":
                return history_requirement
            return super().read_text(remote_path)

        def download(
            self,
            remote_path: PurePosixPath | str,
            local_path: Path,
        ) -> None:
            self.file_downloads.append((str(remote_path), local_path))
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if local_path.name == "optimizer_evaluations.jsonl":
                local_path.write_text('{"evaluation_index": 1}\n', encoding="utf-8")
                return
            source = Path("tests/fixtures/bridge_test_inv/config") / local_path.name
            local_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = HistoryRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass"
    history_config = yaml.safe_load(
        (result.cache_dir / "config" / "history_warm_start.yaml").read_text(
            encoding="utf-8"
        )
    )
    materialized_path = history_config["history_warm_start"]["sources"][0]["path"]
    assert materialized_path == "history_sources/source_001"
    source_root = result.cache_dir / materialized_path
    assert (source_root / "config" / "optimizer.yaml").is_file()
    assert (source_root / "reports" / "optimizer_evaluations.jsonl").is_file()
    assert all(remote.startswith("/remote/history/round1/") for remote, _ in runner.file_downloads)


def test_prepare_remote_project_cache_persists_and_restores_frozen_snapshot(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    snapshot_store = tmp_path / "remote_snapshot_store"

    class SnapshotRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.live_reads_enabled = True
            self.snapshot_downloaded = False

        def read_text(self, remote_path: PurePosixPath | str) -> str:
            if not self.live_reads_enabled:
                raise AssertionError("frozen restore must not read live requirement files")
            return super().read_text(remote_path)

        def run(self, command: str, **kwargs: object):
            self.commands_run.append(command)
            if command.startswith("test -d "):
                return RemoteCommandResult(
                    0 if snapshot_store.is_dir() else 1,
                    "",
                    "",
                    ["ssh", "lab", command],
                )
            if command.startswith("rm -rf -- "):
                if snapshot_store.exists():
                    shutil.rmtree(snapshot_store)
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])

        def write_text(
            self,
            remote_path: PurePosixPath | str,
            text: str,
        ) -> None:
            assert str(remote_path).endswith("/.complete")
            snapshot_store.mkdir(parents=True, exist_ok=True)
            (snapshot_store / ".complete").write_text(text, encoding="utf-8")

        def upload_tree(
            self,
            local_path: Path,
            remote_path: PurePosixPath | str,
            **kwargs: object,
        ) -> None:
            assert "/state/remote_preparation_snapshots/" in str(remote_path)
            shutil.copytree(local_path, snapshot_store)

        def download_tree(
            self,
            remote_path,
            local_path,
            include=None,
            exclude=None,
            dereference=False,
        ) -> None:
            if str(remote_path).endswith("state/remote_preparation_snapshot"):
                shutil.copytree(snapshot_store, local_path, dirs_exist_ok=True)
                self.snapshot_downloaded = True
                return
            super().download_tree(
                remote_path,
                local_path,
                include=include,
                exclude=exclude,
                dereference=dereference,
            )

    runner = SnapshotRunner()
    initial = prepare_remote_project_cache(
        ref,
        runner=runner,
        cache_root=tmp_path / "cache",
        persist_snapshot=True,
    )
    assert initial.status == "pass"
    assert (snapshot_store / "reports" / "remote_preparation_snapshot.json").is_file()
    assert (snapshot_store / ".complete").is_file()
    assert any("mv -Tf" in command for command in runner.commands_run)

    runner.live_reads_enabled = False
    restored = prepare_remote_project_cache(
        ref,
        runner=runner,
        cache_root=tmp_path / "cache",
        frozen_snapshot=True,
    )

    assert restored.status == "pass"
    assert runner.snapshot_downloaded is True
    assert (restored.cache_dir / "config" / "optimizer.yaml").is_file()
    assert (restored.cache_dir / "netlists" / "templates" / "template.scs").is_file()

    with (snapshot_store / "config" / "optimizer.yaml").open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write("# tampered\n")
    with pytest.raises(RuntimeError, match="snapshot integrity check failed"):
        prepare_remote_project_cache(
            ref,
            runner=runner,
            cache_root=tmp_path / "cache",
            frozen_snapshot=True,
        )


def test_prepare_remote_project_cache_fails_closed_without_frozen_snapshot(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    class MissingSnapshotRunner(FakeRunner):
        def run(self, command: str, **kwargs: object):
            if command.startswith("test -d "):
                return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
            return super().run(command, **kwargs)

        def read_text(self, remote_path: PurePosixPath | str) -> str:
            raise AssertionError("missing frozen snapshot must not fall back to live files")

    with pytest.raises(RuntimeError, match="remote preparation snapshot is missing"):
        prepare_remote_project_cache(
            ref,
            runner=MissingSnapshotRunner(),
            cache_root=tmp_path,
            frozen_snapshot=True,
        )


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


# ---------------------------------------------------------------------------
# Fix-run remote prepare: workflow_mode must propagate to render_config_payloads
# so fix-run requirements (no Metrics/Objective/Optimizer Settings) render
# correctly instead of being treated as optimizer mode.
# ---------------------------------------------------------------------------
FIX_RUN_REQUIREMENT = """\
## Workflow
```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

## Project
```yaml
project_name: fix_run_remote
backend: maestro_exported_spectre_deck
```

## Maestro Source
```yaml
maestro_point_root: /remote/maestro/point_1
virtuoso_library: Virtuoso_Bridge_test
cell: bridge_test_inv
design_view: schematic
maestro_view: maestro
test_name: tran_dc_test
corner: Nominal
```

## Design Variables
```yaml
- name: FN
  kind: integer
  lower: "2"
  upper: "12"
  step: "1"
- name: WN
  kind: continuous_step
  lower: "0.3u"
  upper: "3u"
  step: "0.2u"
- name: FP
  kind: integer
  lower: "2"
  upper: "12"
  step: "1"
- name: WP
  kind: continuous_step
  lower: "0.3u"
  upper: "3u"
  step: "0.2u"
```

## Spectre Settings
```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 4
parallel_jobs: 1
timeout_s: 3600
require_license_check: false
keep_failed_runs: false
keep_successful_runs: true
```

## Fixed Points
```yaml
schema_version: "1.0"
points:
  - candidate_id: user_point_001
    parameters:
      FN: "2"
      WN: "0.3u"
      FP: "2"
      WP: "0.3u"
```

## Waveform Exports
```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    testbench: cg_nf
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail
```

## Approval Checklist
```yaml
metric_formulas_user_approved: true
maestro_source_user_approved: true
variable_bounds_user_approved: true
spectre_resource_settings_user_approved: true
```
"""


class FixRunRunner(FakeRunner):
    def read_text(self, remote_path):
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return FIX_RUN_REQUIREMENT
        if path == "/remote/project/constraints.md":
            return "# guidance\n"
        raise FileNotFoundError(path)


def test_prepare_remote_project_cache_fix_run_passes_without_metrics(tmp_path: Path) -> None:
    """A fix-run requirement that omits Metrics/Objective/Optimizer Settings
    must pass remote prepare and render fix-run config files (no optimizer.yaml).
    Reproduces the KeyError: 'Metrics' bug."""
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FixRunRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass", result.issues
    assert (result.cache_dir / "config" / "fixed_points.yaml").is_file()
    assert (result.cache_dir / "config" / "waveform_exports.yaml").is_file()
    assert (result.cache_dir / "config" / "workflow.yaml").is_file()
    # fix-run must NOT produce optimizer.yaml.
    assert not (result.cache_dir / "config" / "optimizer.yaml").exists()


def test_prepare_remote_project_cache_fix_run_passes_workflow_mode_to_render(
    tmp_path: Path, monkeypatch
) -> None:
    """render_config_payloads must be called with workflow_mode='fix_run' for
    a fix-run requirement. Locks in the B-FIXRUN remote-prepare fix."""
    import hermes_workflow.remote_prepare as remote_prepare_module

    captured: dict[str, object] = {}
    original = remote_prepare_module.render_config_payloads

    def spy(sections, *, workflow_mode="optimize"):
        captured["workflow_mode"] = workflow_mode
        return original(sections, workflow_mode=workflow_mode)

    monkeypatch.setattr(remote_prepare_module, "render_config_payloads", spy)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = FixRunRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "pass", result.issues
    assert captured.get("workflow_mode") == "fix_run"


def test_prepare_remote_project_cache_optimizer_missing_metrics_still_fails(
    tmp_path: Path,
) -> None:
    """Optimizer mode regression boundary: an optimizer requirement missing
    Metrics must still fail remote prepare (workflow_mode must NOT relax the
    optimizer path)."""
    broken_optimizer = VALID_REQUIREMENT.replace("## Metrics", "## Not Metrics")

    class BrokenOptimizerRunner(FakeRunner):
        def read_text(self, remote_path):
            path = str(remote_path)
            if path == "/remote/project/opt_requirement.md":
                return broken_optimizer
            if path == "/remote/project/constraints.md":
                return "# guidance\n"
            raise FileNotFoundError(path)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    runner = BrokenOptimizerRunner()

    result = prepare_remote_project_cache(ref, runner=runner, cache_root=tmp_path)

    assert result.status == "fail"
