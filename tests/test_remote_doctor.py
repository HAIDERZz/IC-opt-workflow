from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath

from hermes_workflow.remote_doctor import _build_remote_dirty_state, run_remote_doctor
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult


VALID_REQUIREMENT = (
    Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1")
)


class FakeRunner:
    profile = "lab"

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.writes: dict[str, str] = {}

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if command == "true":
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -d /remote/project" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -w /remote/project" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/project/cadence_env.csh" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/maestro/point_1/netlist/input.scs" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "which spectre" in command and "which ocean" in command:
            return RemoteCommandResult(
                0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command]
            )
        if "mkdir -p /remote/project/reports" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        # License probe: csh -fc "source ...; which spectre ...; spectre -V ...; lmstat -a ..."
        # This has "which spectre" but NOT "which ocean"
        if "which spectre" in command and "which ocean" not in command:
            return RemoteCommandResult(
                0,
                "SPECTRE_PATH=/tools/spectre\n"
                "spectre version 23.1.0\n"
                "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n",
                "",
                ["ssh", "lab", command],
            )
        return RemoteCommandResult(1, "", "unexpected command", ["ssh", "lab", command])

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return VALID_REQUIREMENT
        if path == "/remote/project/constraints.md":
            return ""
        raise FileNotFoundError(path)

    def write_text(self, remote_path: PurePosixPath | str, text: str) -> None:
        self.writes[str(remote_path)] = text

    def mkdir(self, remote_path: PurePosixPath | str) -> None:
        self.run(f"mkdir -p {remote_path}")


def test_remote_doctor_writes_remote_and_local_reports(tmp_path: Path) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert report.remote_report_path == "/remote/project/reports/ic_opt_doctor_report.json"
    assert "/remote/project/reports/ic_opt_doctor_report.json" in runner.writes
    assert (report.local_report_path).is_file()
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["checks"]["ssh"]["status"] == "pass"
    assert payload["checks"]["spectre_ocean"]["status"] == "pass"


def test_remote_doctor_fails_before_optimizer_when_ssh_is_not_ready(
    tmp_path: Path,
) -> None:
    class FailingSshRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            if command == "true":
                return RemoteCommandResult(
                    255, "", "Permission denied", ["ssh", "lab", command]
                )
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=FailingSshRunner(), cache_root=tmp_path)

    assert report.status == "fail"
    assert report.checks["ssh"]["status"] == "fail"
    assert "ssh lab true" in report.checks["ssh"]["message"]


def test_remote_doctor_csh_payload_quotes_cshrc_path(tmp_path: Path) -> None:
    cshrc = PurePosixPath("/remote/project/my cadence env.csh")

    class SpacePathRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            self.commands.append(command)
            if command == "true":
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "test -d" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "test -w" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if f"test -f {shlex.quote(str(cshrc))}" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            if "which spectre" in command and "which ocean" in command:
                return RemoteCommandResult(
                    0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command]
                )
            if "which spectre" in command and "which ocean" not in command:
                return RemoteCommandResult(
                    0, "SPECTRE_PATH=/tools/spectre\nspectre version 23.1.0\n", "", ["ssh", "lab", command]
                )
            if "mkdir -p" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            return RemoteCommandResult(1, "", "unexpected command", ["ssh", "lab", command])

    runner = SpacePathRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    run_remote_doctor(ref, runner=runner, cadence_cshrc=cshrc, cache_root=tmp_path)

    csh_commands = [c for c in runner.commands if c.startswith("csh -fc")]
    assert len(csh_commands) == 2  # spectre_ocean check + license probe
    assert shlex.quote(str(cshrc)) in csh_commands[0]


def test_remote_doctor_attaches_unified_summaries(tmp_path: Path) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["transport"]["mode"] == "remote"
    assert payload["transport"]["ssh_profile"] == "lab"
    assert payload["transport"]["remote_project_dir"] == "/remote/project"
    assert payload["requirement_summary"]["testbench_count"] == 1
    assert payload["requirement_summary"]["corner_count"] == 1
    assert payload["evaluation_matrix"]["inside_candidate_execution"] == "serial"
    assert payload["evaluation_matrix"]["candidate_parallelism"] == 10
    assert payload["optimizer_summary"]["algorithm"] == "openbox"
    assert payload["optimizer_summary"]["requested_strategy"] == "openbox_auto"
    assert payload["optimizer_summary"]["max_evaluations"] == 100
    assert payload["optimizer_summary"]["max_evaluations_source"] == "config"
    assert "dirty_state" in payload


def test_remote_doctor_warns_when_remote_parallel_jobs_above_threshold(
    tmp_path: Path,
) -> None:
    high_runner = FakeRunner()
    high_runner._read_text_override = VALID_REQUIREMENT.replace(
        "parallel_jobs: 10", "parallel_jobs: 24"
    )

    def fake_read_text(self: FakeRunner, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return self._read_text_override
        if path == "/remote/project/constraints.md":
            return ""
        raise FileNotFoundError(path)

    high_runner.read_text = fake_read_text.__get__(high_runner, FakeRunner)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=high_runner, cache_root=tmp_path)

    assert report.status == "pass"
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert any(
        item["code"] == "REMOTE_PARALLELISM_HIGH"
        for item in payload["structured_issues"]
    )


def test_remote_doctor_supports_cli_max_evals_override(tmp_path: Path) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(
        ref, runner=runner, cache_root=tmp_path, cli_max_evals=7
    )

    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["optimizer_summary"]["max_evaluations"] == 7
    assert payload["optimizer_summary"]["max_evaluations_source"] == "cli"


def test_remote_doctor_fails_on_invalid_optimizer_strategy(tmp_path: Path) -> None:
    bad_runner = FakeRunner()
    bad_runner._read_text_override = VALID_REQUIREMENT.replace(
        "algorithm: openbox\ninitialization: sobol",
        "algorithm: openbox\nstrategy: openbox_eic\ninitialization: sobol",
    )

    def fake_read_text(self: FakeRunner, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return self._read_text_override
        if path == "/remote/project/constraints.md":
            return ""
        raise FileNotFoundError(path)

    bad_runner.read_text = fake_read_text.__get__(bad_runner, FakeRunner)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=bad_runner, cache_root=tmp_path)

    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert report.status == "fail"
    assert payload["status"] == "fail"
    assert any(
        item["code"] == "OPTIMIZER_STRATEGY_INVALID"
        for item in payload["structured_issues"]
    )


def test_remote_doctor_payload_exposes_run_retention_policy(tmp_path: Path) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    retention = payload["resource_summary"]["run_retention"]
    assert retention["keep_failed_runs"] is True
    assert retention["keep_successful_runs"] is True
    assert retention["cleanup_scope"] == "runs/real/<run_id>"
    assert retention["decision_reports"] == "state/run_retention/<run_id>.json"


def test_remote_doctor_reports_optimizer_progress_summary_in_payload(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    progress = payload["optimizer_progress_summary"]
    assert "report_evaluation_count" in progress
    assert "evaluation_trace_count" in progress
    assert "state_current_evaluations" in progress
    assert "state_recorded_observation_count" in progress
    assert "ledger_row_count" in progress


class _DirtyFakeRunner:
    """Fake SSH runner driving remote dirty-state probes for one project."""

    profile = "lab"

    def __init__(
        self,
        *,
        listing: list[str],
        present_files: set[str],
        present_dirs: set[str],
    ) -> None:
        self.commands: list[str] = []
        self._listing = listing
        self._present_files = present_files
        self._present_dirs = present_dirs

    @staticmethod
    def _extract_path(command: str, prefix: str) -> str:
        rest = command[len(prefix):]
        # Strip trailing redirection like " 2>/dev/null" if present.
        if " 2>" in rest:
            rest = rest.split(" 2>", 1)[0]
        rest = rest.strip()
        # Paths in our tests are ASCII without spaces; shlex.quote returns them
        # unchanged. Strip surrounding single quotes defensively.
        if rest.startswith("'") and rest.endswith("'"):
            rest = rest[1:-1]
        return rest

    def run(self, command: str, **_: object) -> RemoteCommandResult:
        self.commands.append(command)
        if command.startswith("ls -1 "):
            path = self._extract_path(command, "ls -1 ")
            if path in self._present_dirs:
                return RemoteCommandResult(
                    0, "\n".join(self._listing) + "\n", "", ["ssh", "lab", command]
                )
            return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
        if command.startswith("test -f "):
            path = self._extract_path(command, "test -f ")
            return RemoteCommandResult(
                0 if path in self._present_files else 1,
                "",
                "",
                ["ssh", "lab", command],
            )
        if command.startswith("test -d "):
            path = self._extract_path(command, "test -d ")
            return RemoteCommandResult(
                0 if path in self._present_dirs else 1,
                "",
                "",
                ["ssh", "lab", command],
            )
        return RemoteCommandResult(1, "", "unexpected", ["ssh", "lab", command])


def test_remote_dirty_state_does_not_warn_when_candidate_result_manifest_exists() -> None:
    runner = _DirtyFakeRunner(
        listing=["real_001"],
        present_files={
            "/remote/project/runs/real/real_001/result_manifest.json",
        },
        present_dirs={
            "/remote/project/runs/real",
        },
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    summary, diagnostics = _build_remote_dirty_state(ref, runner)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is False
    assert not any(d.code == "INCOMPLETE_REAL_RUN" for d in diagnostics)


def test_remote_dirty_state_warns_when_candidate_dir_has_no_completion_marker() -> None:
    runner = _DirtyFakeRunner(
        listing=["real_001"],
        present_files=set(),
        present_dirs={
            "/remote/project/runs/real",
        },
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    summary, diagnostics = _build_remote_dirty_state(ref, runner)

    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is True
    incomplete = [d for d in diagnostics if d.code == "INCOMPLETE_REAL_RUN"]
    assert len(incomplete) == 1


class _CompletedRunFakeRunner(FakeRunner):
    """FakeRunner that reports a completed candidate run on the remote side."""

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        # Dirty-state directory probe.
        if command == "test -d /remote/project/runs/real":
            self.commands.append(command)
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if command.startswith("ls -1 /remote/project/runs/real"):
            self.commands.append(command)
            return RemoteCommandResult(
                0, "real_001\n", "", ["ssh", "lab", command]
            )
        if command == "test -f /remote/project/runs/real/real_001/result_manifest.json":
            self.commands.append(command)
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if command.startswith("test -f /remote/project/runs/real/real_001/"):
            # Any other candidate-level probe (metric manifest, optimizer
            # reports, candidate markers) reports missing.
            self.commands.append(command)
            return RemoteCommandResult(1, "", "", ["ssh", "lab", command])
        # Delegate to parent FakeRunner which handles license probe
        return super().run(command, **kwargs)


def test_remote_doctor_payload_does_not_warn_for_completed_candidate_run(
    tmp_path: Path,
) -> None:
    runner = _CompletedRunFakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["dirty_state"]["has_runs"] is True
    assert payload["dirty_state"]["has_incomplete_real_run"] is False
    assert not any(
        item["code"] == "INCOMPLETE_REAL_RUN"
        for item in payload["structured_issues"]
    )
    assert report.status == "pass"


# ── B-05: remote license probe tests ──────────────────────────────────────


class LicenseProbeFakeRunner(FakeRunner):
    """FakeRunner that responds to license probe commands."""

    def __init__(
        self,
        *,
        spectre_found: bool = True,
        lmstat_output: str = "",
    ) -> None:
        super().__init__()
        self._spectre_found = spectre_found
        self._lmstat_output = lmstat_output

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
        if "which spectre" in command and "which ocean" not in command:
            # License probe command (has "which spectre" but NOT "which ocean")
            spectre_path = "/tools/spectre" if self._spectre_found else "NOTFOUND"
            output = (
                f"SPECTRE_PATH={spectre_path}\n"
                "spectre version 23.1.0\n"
                f"{self._lmstat_output}"
            )
            return RemoteCommandResult(
                0, output, "", ["ssh", "lab", command]
            )
        return super().run(command, **kwargs)


def test_remote_doctor_license_probe_pass_when_required_and_ok(
    tmp_path: Path,
) -> None:
    """B-05: remote require_license_check=true + probe pass → doctor pass."""
    runner = LicenseProbeFakeRunner(
        spectre_found=True,
        lmstat_output="Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n",
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert "license_probe" in report.checks
    assert report.checks["license_probe"]["status"] == "pass"
    # Local mirrored report should also have license_probe
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert "license_probe" in payload
    assert payload["license_probe"]["status"] == "pass"
    assert payload["license_probe"]["execution_mode"] == "remote"


def test_remote_doctor_license_probe_fail_when_required_and_spectre_missing(
    tmp_path: Path,
) -> None:
    """B-05: remote require_license_check=true + spectre missing → doctor fail."""
    runner = LicenseProbeFakeRunner(spectre_found=False)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "fail"
    assert "license_probe" in report.checks
    assert report.checks["license_probe"]["status"] == "fail"


def test_remote_doctor_license_probe_skipped_when_not_required(
    tmp_path: Path,
) -> None:
    """B-05: remote require_license_check=false → skipped, no probe command."""
    # Override requirement to set require_license_check: false
    runner = FakeRunner()
    override_req = VALID_REQUIREMENT.replace(
        "require_license_check: true", "require_license_check: false"
    )
    runner._read_text_override = override_req

    def fake_read_text(self, remote_path):
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return self._read_text_override
        if path == "/remote/project/constraints.md":
            return ""
        raise FileNotFoundError(path)

    runner.read_text = fake_read_text.__get__(runner, FakeRunner)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert "license_probe" in report.checks
    assert report.checks["license_probe"]["status"] == "skipped"
    # No lmstat or license probe command should have been sent
    assert not any("lmstat" in cmd for cmd in runner.commands)
