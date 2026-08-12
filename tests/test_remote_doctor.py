from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath

import pytest

from hermes_workflow.remote_doctor import _build_remote_dirty_state, run_remote_doctor
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import RemoteCommandResult


VALID_REQUIREMENT = (
    Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1")
)
MODEL_FILE_PATH = "/remote/pdk/models/device.scs"
MODEL_FILE_REQUIREMENT = VALID_REQUIREMENT.replace(
    "## Spectre Settings\n",
    f"""## Process Corners

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: external_model
    model_file: {MODEL_FILE_PATH}
```

## Spectre Settings
""",
)
NATIVE_REQUIREMENT = VALID_REQUIREMENT.replace(
    "algorithm: openbox\n",
    "algorithm: turbo\nstrategy: turbo_trust_region\n",
)
RANDOM_BASELINE_REQUIREMENT = VALID_REQUIREMENT.replace(
    "algorithm: openbox\n",
    "algorithm: random\nstrategy: random_baseline\n",
)
FIX_RUN_REQUIREMENT = (
    Path("examples/spectre_maestro_project/opt_requirement.fix_run.md")
    .read_text(encoding="utf-8")
    .replace(
        "/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_CG_Noise/"
        "maestro/results/maestro/Interactive.N/1/Mixer_CS_CG_NF",
        "/remote/maestro/point_1",
    )
    .replace("require_license_check: true", "require_license_check: false")
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
        if command == "test -d /remote/project":
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -w /remote/project" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if (
            command == "test -x /bin/sh"
            or command.startswith("command -v tar")
            or command.startswith("readlink -e /bin/sh")
            or command.startswith("stat -Lc ")
            or command.startswith("printf x | sha256sum")
            or ".ic-opt-doctor-publish-probe" in command
        ):
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/project/cadence_env.csh" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "test -f /remote/maestro/point_1/netlist/input.scs" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
        if "which spectre" in command and "which ocean" in command:
            return RemoteCommandResult(
                0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command]
            )
        if "which ocean" in command:
            return RemoteCommandResult(
                0, "/tools/ocean\n", "", ["ssh", "lab", command]
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


class OptimizerHistoryRunner(FakeRunner):
    """Fake Remote Host exposing a selected set of optimizer artifacts."""

    def __init__(
        self,
        files: dict[str, str],
        *,
        requirement_text: str = NATIVE_REQUIREMENT,
    ) -> None:
        super().__init__()
        self.files = files
        self.requirement_text = requirement_text

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        if command.startswith("test -f "):
            parts = shlex.split(command)
            if len(parts) == 3 and parts[2].startswith(
                (
                    "/remote/project/reports/",
                    "/remote/project/state/",
                    "/remote/project/ledger/",
                )
            ):
                self.commands.append(command)
                return RemoteCommandResult(
                    0 if parts[2] in self.files else 1,
                    "",
                    "",
                    ["ssh", "lab", command],
                )
        return super().run(command, **kwargs)

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        path = str(remote_path)
        if path == "/remote/project/opt_requirement.md":
            return self.requirement_text
        if path in self.files:
            return self.files[path]
        return super().read_text(remote_path)


def _valid_native_turbo_trace(index: int) -> dict[str, object]:
    return {
        "evaluation_index": index,
        "run_id": f"real_{index:03d}",
        "selection_phase": "initialization",
        "raw_x": [2.0, 0.3, 2.0, 0.3],
        "parameters": {
            "FN": "2",
            "WN": "0.3u",
            "FP": "2",
            "WP": "0.3u",
        },
        "status": "recorded",
        "objective": float(index),
        "fom": float(index),
        "constraint_penalty": 0.0,
        "metrics": {"metric": float(index)},
        "result_manifest": f"runs/real/real_{index:03d}/result_manifest.json",
        "metric_result_manifest": (
            f"runs/real/real_{index:03d}/metrics/metric_result_manifest.json"
        ),
        "issues": [],
        "batch_id": f"batch_{index:03d}",
        "batch_slot": 1,
        "batch_size": 1,
    }


def _native_turbo_history_files(
    *,
    report: dict[str, object],
    traces: list[dict[str, object]],
) -> dict[str, str]:
    count = len(traces)
    return {
        "/remote/project/reports/native_turbo_optimizer_report.json": json.dumps(
            report
        ),
        "/remote/project/reports/native_turbo_optimizer_evaluations.jsonl": "".join(
            json.dumps(trace) + "\n" for trace in traces
        ),
        "/remote/project/state/optimizer_state.json": json.dumps(
            {
                "current_evaluations": count,
                "recorded_observation_count": count,
            }
        ),
        "/remote/project/ledger/experiment_ledger.jsonl": "{}\n" * count,
    }


class MaestroProbeRunner(FakeRunner):
    def __init__(self, return_code: int, stderr: str = "") -> None:
        super().__init__()
        self.return_code = return_code
        self.stderr = stderr

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        if command == "test -f /remote/maestro/point_1/netlist/input.scs":
            self.commands.append(command)
            return RemoteCommandResult(
                self.return_code,
                "",
                self.stderr,
                ["ssh", "lab", command],
            )
        return super().run(command, **kwargs)


class ModelFileProbeRunner(FakeRunner):
    def __init__(self, return_code: int, stderr: str = "") -> None:
        super().__init__()
        self.return_code = return_code
        self.stderr = stderr

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        if str(remote_path) == "/remote/project/opt_requirement.md":
            return MODEL_FILE_REQUIREMENT
        return super().read_text(remote_path)

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        expected = f"test -f {MODEL_FILE_PATH} && test -r {MODEL_FILE_PATH}"
        if command == expected:
            self.commands.append(command)
            return RemoteCommandResult(
                self.return_code,
                "",
                self.stderr,
                ["ssh", "lab", command],
            )
        return super().run(command, **kwargs)


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


def test_remote_doctor_checks_optimizer_runtime_on_controller_not_remote_host(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner({}, requirement_text=NATIVE_REQUIREMENT)
    runtime_calls: list[tuple[dict[str, object], str]] = []

    def check_runtime(
        sections: dict[str, object],
        *,
        workflow_mode: str,
    ) -> dict[str, object]:
        runtime_calls.append((sections, workflow_mode))
        return {
            "status": "pass",
            "resolved_backend": "native_turbo",
            "detail": "native dependencies passed on Controller",
            "issues": [],
        }

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
        controller_optimizer_runtime_probe=check_runtime,
    )

    assert report.status == "pass"
    assert len(runtime_calls) == 1
    assert runtime_calls[0][1] == "optimize"
    assert runtime_calls[0][0]["Optimizer Settings"]["algorithm"] == "turbo"
    assert report.checks["controller_optimizer_runtime"] == {
        "status": "pass",
        "message": "native dependencies passed on Controller",
    }
    assert not any("python" in command.lower() for command in runner.commands)


def test_remote_doctor_fails_when_controller_optimizer_runtime_is_missing(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner({}, requirement_text=NATIVE_REQUIREMENT)

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
        controller_optimizer_runtime_probe=lambda *_args, **_kwargs: {
            "status": "fail",
            "resolved_backend": "native_turbo",
            "detail": "Turbo1 import failed",
            "issues": ["Turbo1 import failed"],
        },
    )

    assert report.status == "fail"
    assert report.checks["controller_optimizer_runtime"]["status"] == "fail"
    diagnostic = next(
        issue
        for issue in report.structured_issues
        if issue.code == "CONTROLLER_OPTIMIZER_RUNTIME_UNAVAILABLE"
    )
    assert diagnostic.stage == "controller"
    assert diagnostic.detail == "Turbo1 import failed"
    assert not any("python" in command.lower() for command in runner.commands)


def test_remote_doctor_marks_fix_run_optimizer_runtime_skipped(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner({}, requirement_text=FIX_RUN_REQUIREMENT)

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "pass"
    assert report.workflow_mode == "fix_run"
    assert report.checks["controller_optimizer_runtime"]["status"] == "skipped"
    assert "does not use an optimizer" in report.checks[
        "controller_optimizer_runtime"
    ]["message"]
    assert not any("python" in command.lower() for command in runner.commands)


def test_remote_doctor_fails_when_controller_transfer_tool_is_missing(
    tmp_path: Path,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(
        ref,
        runner=FakeRunner(),
        cache_root=tmp_path,
        controller_which=lambda tool: None if tool == "scp" else f"/usr/bin/{tool}",
    )

    assert report.status == "fail"
    assert report.checks["controller_scp"]["status"] == "fail"
    assert any("Controller dependency is missing: scp" in issue for issue in report.issues)


def test_remote_doctor_fails_when_remote_transfer_capability_is_missing(
    tmp_path: Path,
) -> None:
    class MissingReadlinkRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            if command.startswith("readlink -e /bin/sh"):
                self.commands.append(command)
                return RemoteCommandResult(127, "", "readlink: not found", [])
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    report = run_remote_doctor(
        ref,
        runner=MissingReadlinkRunner(),
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    assert report.checks["remote_readlink_e"]["status"] == "fail"


def test_remote_doctor_checks_spectre_and_ocean_independently(
    tmp_path: Path,
) -> None:
    class MissingSpectreRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            if "which spectre" in command and "which ocean" not in command:
                self.commands.append(command)
                return RemoteCommandResult(1, "", "spectre not found", [])
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    report = run_remote_doctor(
        ref,
        runner=MissingSpectreRunner(),
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    assert report.checks["spectre"]["status"] == "fail"
    assert report.checks["ocean"]["status"] == "pass"
    assert report.checks["spectre_ocean"]["status"] == "fail"


@pytest.mark.parametrize(
    ("return_code", "expected_status"),
    [(0, "pass"), (1, "fail")],
)
def test_remote_doctor_maestro_probe_maps_test_f_exit_codes(
    tmp_path: Path,
    return_code: int,
    expected_status: str,
) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(
        ref,
        runner=MaestroProbeRunner(return_code),
        cache_root=tmp_path,
    )

    assert report.status == expected_status
    if return_code == 1:
        assert any(
            "maestro_point_root/netlist/input.scs is missing" in issue
            for issue in report.issues
        )


def test_remote_doctor_maestro_probe_raises_transport_error(tmp_path: Path) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    with pytest.raises(RuntimeError, match="ssh transport timed out"):
        run_remote_doctor(
            ref,
            runner=MaestroProbeRunner(255, "ssh transport timed out"),
            cache_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("return_code", "expected_status", "transport_error"),
    [
        (0, "pass", False),
        (1, "fail", False),
        (255, None, True),
    ],
)
def test_remote_doctor_model_file_probe_is_remote_readable_file_check(
    tmp_path: Path,
    return_code: int,
    expected_status: str | None,
    transport_error: bool,
) -> None:
    runner = ModelFileProbeRunner(
        return_code,
        "ssh transport timed out" if transport_error else "",
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    expected_command = f"test -f {MODEL_FILE_PATH} && test -r {MODEL_FILE_PATH}"
    assert not Path(MODEL_FILE_PATH).exists()

    if transport_error:
        with pytest.raises(RuntimeError, match="ssh transport timed out"):
            run_remote_doctor(ref, runner=runner, cache_root=tmp_path)
    else:
        report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)
        assert report.status == expected_status
        if return_code == 1:
            assert any(
                "Process Corners.model_file is missing or unreadable" in issue
                for issue in report.issues
            )

    assert expected_command in runner.commands


def test_remote_doctor_preserves_local_failure_report_when_remote_write_fails(
    tmp_path: Path,
) -> None:
    class FailingReportWriteRunner(FakeRunner):
        def write_text(
            self,
            remote_path: PurePosixPath | str,
            text: str,
        ) -> None:
            raise RuntimeError("connection reset")

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(
        ref,
        runner=FailingReportWriteRunner(),
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    assert report.local_report_path.is_file()
    payload = json.loads(report.local_report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["checks"]["remote_doctor_report_write"]["status"] == "fail"
    assert any(
        issue["code"] == "REMOTE_DOCTOR_REPORT_WRITE_FAILED"
        for issue in payload["structured_issues"]
    )


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
            if "which ocean" in command:
                return RemoteCommandResult(
                    0, "/tools/ocean\n", "", ["ssh", "lab", command]
                )
            if "mkdir -p" in command:
                return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
            return RemoteCommandResult(1, "", "unexpected command", ["ssh", "lab", command])

    runner = SpacePathRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    run_remote_doctor(ref, runner=runner, cadence_cshrc=cshrc, cache_root=tmp_path)

    csh_commands = [c for c in runner.commands if c.startswith("csh -fc")]
    assert len(csh_commands) == 3  # separate spectre/ocean checks + license probe
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


def test_remote_doctor_recognizes_native_turbo_history(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        _native_turbo_history_files(
            report={
                "schema_version": "1.0",
                "status": "completed",
                "backend": "native_turbo",
                "evaluation_count": 2,
                "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
            },
            traces=[_valid_native_turbo_trace(1), _valid_native_turbo_trace(2)],
        )
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "native_turbo"
    assert report.dirty_state["has_optimizer_run_report"] is True
    assert report.dirty_state["has_optimizer_evaluations"] is True
    assert report.optimizer_progress_summary["report_evaluation_count"] == 2
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 2
    assert not any(
        issue.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH"
        for issue in report.structured_issues
    )


@pytest.mark.parametrize(
    ("invalid_case", "expected_detail"),
    [
        ("wrong_schema_version", "schema_version must be 1.0"),
        ("report_not_completed", "requires a completed report"),
        ("wrong_backend", "backend must be native_turbo"),
        ("noncanonical_evaluations", "evaluations path is invalid"),
        ("noninteger_evaluation_count", "evaluation_count must be an integer"),
        ("boolean_evaluation_count", "evaluation_count must be an integer"),
        ("missing_trace_field", "evaluation line 1 is invalid"),
        ("noncontiguous_evaluation_index", "evaluation_index sequence is invalid"),
        ("invalid_selection_phase", "selection_phase is invalid"),
        ("nonscalar_selection_phase", "selection_phase is invalid"),
        ("invalid_raw_x", "raw_x is invalid"),
        ("invalid_parameters", "parameters are invalid"),
        ("nonfinite_objective", "objective is non-finite"),
        ("partial_batch_metadata", "batch metadata must be all present"),
        ("duplicate_run_id", "duplicate run_id"),
        ("reappearing_batch_id", "batch_id must be strictly increasing"),
        ("mixed_batch_phase", "mixes selection_phase"),
    ],
)
def test_remote_doctor_rejects_native_history_that_continuation_would_reject(
    tmp_path: Path,
    invalid_case: str,
    expected_detail: str,
) -> None:
    report_payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": "completed",
        "backend": "native_turbo",
        "evaluation_count": 1,
        "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
    }
    trace = _valid_native_turbo_trace(1)
    traces = [trace]
    if invalid_case == "wrong_schema_version":
        report_payload["schema_version"] = "2.0"
    elif invalid_case == "report_not_completed":
        report_payload["status"] = "running"
    elif invalid_case == "wrong_backend":
        report_payload["backend"] = "turbo"
    elif invalid_case == "noncanonical_evaluations":
        report_payload["evaluations"] = "reports/other.jsonl"
    elif invalid_case == "noninteger_evaluation_count":
        report_payload["evaluation_count"] = "1"
    elif invalid_case == "boolean_evaluation_count":
        report_payload["evaluation_count"] = True
    elif invalid_case == "missing_trace_field":
        trace.pop("run_id")
    elif invalid_case == "noncontiguous_evaluation_index":
        trace["evaluation_index"] = 2
    elif invalid_case == "invalid_selection_phase":
        trace["selection_phase"] = "unknown"
    elif invalid_case == "nonscalar_selection_phase":
        trace["selection_phase"] = ["initialization"]
    elif invalid_case == "invalid_raw_x":
        trace["raw_x"] = [True]
    elif invalid_case == "invalid_parameters":
        trace["parameters"] = ["V1"]
    elif invalid_case == "nonfinite_objective":
        trace["objective"] = float("nan")
    elif invalid_case == "partial_batch_metadata":
        trace.pop("batch_id")
    elif invalid_case == "duplicate_run_id":
        duplicate = _valid_native_turbo_trace(2)
        duplicate["run_id"] = trace["run_id"]
        traces.append(duplicate)
        report_payload["evaluation_count"] = 2
    elif invalid_case == "reappearing_batch_id":
        traces.extend(
            [_valid_native_turbo_trace(2), _valid_native_turbo_trace(3)]
        )
        traces[2]["batch_id"] = "batch_001"
        report_payload["evaluation_count"] = 3
    elif invalid_case == "mixed_batch_phase":
        second = _valid_native_turbo_trace(2)
        trace.update(batch_id="batch_001", batch_slot=1, batch_size=2)
        second.update(
            batch_id="batch_001",
            batch_slot=2,
            batch_size=2,
            selection_phase="turbo_trust_region",
        )
        traces.append(second)
        report_payload["evaluation_count"] = 2
    else:  # pragma: no cover - parameter table is closed above
        raise AssertionError(invalid_case)
    runner = OptimizerHistoryRunner(
        _native_turbo_history_files(report=report_payload, traces=traces)
    )

    doctor = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert doctor.status == "fail"
    invalid = next(
        issue
        for issue in doctor.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert expected_detail in (invalid.detail or "")


@pytest.mark.parametrize(
    ("invalid_case", "expected_detail"),
    [
        ("raw_x_dimension", "raw_x dimension mismatch"),
        ("parameter_names", "parameters mismatch"),
        ("quantized_values", "raw_x/parameters mismatch"),
    ],
)
def test_remote_doctor_rejects_native_history_with_invalid_variable_semantics(
    tmp_path: Path,
    invalid_case: str,
    expected_detail: str,
) -> None:
    trace = _valid_native_turbo_trace(1)
    if invalid_case == "raw_x_dimension":
        trace["raw_x"] = [2.0, 0.3, 2.0]
    elif invalid_case == "parameter_names":
        parameters = dict(trace["parameters"])
        parameters["UNKNOWN"] = parameters.pop("WP")
        trace["parameters"] = parameters
    elif invalid_case == "quantized_values":
        parameters = dict(trace["parameters"])
        parameters["WN"] = "0.5u"
        trace["parameters"] = parameters
    else:  # pragma: no cover - parameter table is closed above
        raise AssertionError(invalid_case)
    runner = OptimizerHistoryRunner(
        _native_turbo_history_files(
            report={
                "schema_version": "1.0",
                "status": "completed",
                "backend": "native_turbo",
                "evaluation_count": 1,
                "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
            },
            traces=[trace],
        )
    )

    doctor = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert doctor.status == "fail"
    invalid = next(
        issue
        for issue in doctor.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert expected_detail in (invalid.detail or "")


def test_remote_doctor_fails_when_native_turbo_trace_count_disagrees(
    tmp_path: Path,
) -> None:
    files = _native_turbo_history_files(
        report={
            "schema_version": "1.0",
            "status": "completed",
            "backend": "native_turbo",
            "evaluation_count": 2,
            "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
        },
        traces=[_valid_native_turbo_trace(1)],
    )
    files["/remote/project/state/optimizer_state.json"] = json.dumps(
        {"current_evaluations": 2, "recorded_observation_count": 2}
    )
    files["/remote/project/ledger/experiment_ledger.jsonl"] = "{}\n{}\n"
    runner = OptimizerHistoryRunner(files)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "fail"
    mismatch = [
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH"
    ]
    assert len(mismatch) == 1
    assert "report=2, evaluations=1" in (mismatch[0].detail or "")


def test_remote_doctor_selects_history_for_requirement_backend(
    tmp_path: Path,
) -> None:
    native_history = _native_turbo_history_files(
        report={
            "schema_version": "1.0",
            "status": "completed",
            "backend": "native_turbo",
            "evaluation_count": 2,
            "evaluations": "reports/native_turbo_optimizer_evaluations.jsonl",
        },
        traces=[_valid_native_turbo_trace(1), _valid_native_turbo_trace(2)],
    )
    native_history.update(
        {
            "/remote/project/reports/optimizer_run_report.json": json.dumps(
                {
                    "status": "completed",
                    "backend": "openbox",
                    "evaluation_count": 3,
                }
            ),
            "/remote/project/reports/optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\n'
                '{"evaluation_index": 2}\n'
                '{"evaluation_index": 3}\n'
            ),
        }
    )
    runner = OptimizerHistoryRunner(native_history)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "native_turbo"
    assert report.optimizer_progress_summary["report_evaluation_count"] == 2
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 2


def test_remote_doctor_fails_when_native_turbo_history_pair_is_incomplete(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/native_turbo_optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1, "status": "recorded"}\n'
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 1,
                    "recorded_observation_count": 1,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n",
        }
    )
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "fail"
    invalid = [
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    ]
    assert len(invalid) == 1
    assert "native_turbo_optimizer_report.json" in (invalid[0].detail or "")


def test_remote_doctor_fails_when_native_turbo_evaluations_are_missing(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/native_turbo_optimizer_report.json": json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "backend": "native_turbo",
                    "evaluation_count": 1,
                    "evaluations": (
                        "reports/native_turbo_optimizer_evaluations.jsonl"
                    ),
                }
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 1,
                    "recorded_observation_count": 1,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n",
        }
    )

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    invalid = next(
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert "native_turbo_optimizer_evaluations.jsonl" in (invalid.detail or "")


def test_remote_doctor_fails_closed_on_corrupt_native_turbo_history(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/native_turbo_optimizer_report.json": json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "backend": "native_turbo",
                    "evaluation_count": 2,
                    "evaluations": (
                        "reports/native_turbo_optimizer_evaluations.jsonl"
                    ),
                }
            ),
            "/remote/project/reports/native_turbo_optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\nnot-json\n'
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 2,
                    "recorded_observation_count": 2,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n{}\n",
        }
    )

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    invalid = next(
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert "invalid JSONL row" in (invalid.detail or "")


def test_remote_doctor_native_turbo_fresh_project_has_no_history_error(
    tmp_path: Path,
) -> None:
    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=OptimizerHistoryRunner({}),
        cache_root=tmp_path,
    )

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "native_turbo"
    assert report.optimizer_progress_summary["report_evaluation_count"] is None
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 0
    assert not any(
        issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
        for issue in report.structured_issues
    )


def test_remote_doctor_openbox_ignores_stale_native_turbo_history(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/optimizer_run_report.json": json.dumps(
                {
                    "status": "completed",
                    "backend": "openbox",
                    "evaluation_count": 2,
                }
            ),
            "/remote/project/reports/optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\n{"evaluation_index": 2}\n'
            ),
            "/remote/project/reports/native_turbo_optimizer_report.json": json.dumps(
                {
                    "status": "completed",
                    "backend": "native_turbo",
                    "evaluation_count": 3,
                }
            ),
            "/remote/project/reports/native_turbo_optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\n'
                '{"evaluation_index": 2}\n'
                '{"evaluation_index": 3}\n'
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 2,
                    "recorded_observation_count": 2,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n{}\n",
        },
        requirement_text=VALID_REQUIREMENT,
    )

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "openbox"
    assert report.optimizer_progress_summary["report_evaluation_count"] == 2
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 2


def test_remote_doctor_random_baseline_uses_openbox_artifact_contract(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/optimizer_run_report.json": json.dumps(
                {
                    "status": "completed",
                    "backend": "openbox",
                    "evaluation_count": 1,
                }
            ),
            "/remote/project/reports/optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\n'
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 1,
                    "recorded_observation_count": 1,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n",
        },
        requirement_text=RANDOM_BASELINE_REQUIREMENT,
    )

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "pass"
    assert report.optimizer_summary["resolved_backend"] == "random_baseline"
    assert report.optimizer_progress_summary["report_evaluation_count"] == 1
    assert report.optimizer_progress_summary["evaluation_trace_count"] == 1


def test_remote_doctor_fails_when_history_only_matches_wrong_backend(
    tmp_path: Path,
) -> None:
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/optimizer_run_report.json": json.dumps(
                {
                    "status": "completed",
                    "backend": "openbox",
                    "evaluation_count": 2,
                }
            ),
            "/remote/project/reports/optimizer_evaluations.jsonl": (
                '{"evaluation_index": 1}\n{"evaluation_index": 2}\n'
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 2,
                    "recorded_observation_count": 2,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n{}\n",
        }
    )

    report = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert report.status == "fail"
    invalid = next(
        issue
        for issue in report.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert "do not match expected backend native_turbo" in (invalid.detail or "")


def test_remote_doctor_rejects_native_history_in_noncanonical_neutral_paths(
    tmp_path: Path,
) -> None:
    trace = _valid_native_turbo_trace(1)
    runner = OptimizerHistoryRunner(
        {
            "/remote/project/reports/optimizer_run_report.json": json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "completed",
                    "backend": "native_turbo",
                    "evaluation_count": 1,
                    "evaluations": "reports/optimizer_evaluations.jsonl",
                }
            ),
            "/remote/project/reports/optimizer_evaluations.jsonl": (
                json.dumps(trace) + "\n"
            ),
            "/remote/project/state/optimizer_state.json": json.dumps(
                {
                    "current_evaluations": 1,
                    "recorded_observation_count": 1,
                }
            ),
            "/remote/project/ledger/experiment_ledger.jsonl": "{}\n",
        }
    )

    doctor = run_remote_doctor(
        RemoteProjectRef("lab", PurePosixPath("/remote/project")),
        runner=runner,
        cache_root=tmp_path,
    )

    assert doctor.status == "fail"
    invalid = next(
        issue
        for issue in doctor.structured_issues
        if issue.code == "OPTIMIZER_PROGRESS_ARTIFACT_INVALID"
    )
    assert "native_turbo_optimizer_report.json" in (invalid.detail or "")


def test_remote_doctor_ignores_unmaterialized_controller_cache_history(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    cache_dir = remote_cache_dir(ref, cache_root=tmp_path)
    reports = cache_dir / "reports"
    state = cache_dir / "state"
    reports.mkdir(parents=True)
    state.mkdir(parents=True)
    (reports / "optimizer_evaluations.jsonl").write_text(
        '{"evaluation_index": 1}\n',
        encoding="utf-8",
    )
    (reports / "optimizer_run_report.json").write_text(
        '{"evaluation_count": 1}\n',
        encoding="utf-8",
    )
    (state / "optimizer_state.json").write_text(
        '{"current_evaluations": 99}\n',
        encoding="utf-8",
    )

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert not any(
        issue.code == "OPTIMIZER_PROGRESS_STATE_MISMATCH"
        for issue in report.structured_issues
    )


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


class _DirtyStateExitCodeRunner(FakeRunner):
    """Inject one dirty-state path or directory-listing exit code."""

    def __init__(
        self,
        *,
        runs_path_return_code: int = 0,
        listing_return_code: int = 0,
    ) -> None:
        super().__init__()
        self.runs_path_return_code = runs_path_return_code
        self.listing_return_code = listing_return_code

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        if command == "test -d /remote/project/runs/real":
            self.commands.append(command)
            return RemoteCommandResult(
                self.runs_path_return_code,
                "",
                "dirty path probe failed",
                ["ssh", "lab", command],
            )
        if command.startswith("ls -1 /remote/project/runs/real"):
            self.commands.append(command)
            return RemoteCommandResult(
                self.listing_return_code,
                "",
                "dirty listing failed",
                ["ssh", "lab", command],
            )
        return super().run(command, **kwargs)


@pytest.mark.parametrize(
    ("return_code", "expected_has_runs"),
    [(0, True), (1, False)],
)
def test_remote_doctor_dirty_state_treats_only_boolean_one_as_absent(
    tmp_path: Path,
    return_code: int,
    expected_has_runs: bool,
) -> None:
    runner = _DirtyStateExitCodeRunner(runs_path_return_code=return_code)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "pass"
    assert report.dirty_state["has_runs"] is expected_has_runs
    assert not any(
        issue.code == "REMOTE_DIRTY_STATE_PROBE_FAILED"
        for issue in report.structured_issues
    )


@pytest.mark.parametrize("return_code", [2, 126, 127, 255])
def test_remote_doctor_dirty_state_path_probe_fails_closed_on_abnormal_exit(
    tmp_path: Path,
    return_code: int,
) -> None:
    runner = _DirtyStateExitCodeRunner(runs_path_return_code=return_code)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "fail"
    assert report.dirty_state["has_runs"] is None
    diagnostic = next(
        issue
        for issue in report.structured_issues
        if issue.code == "REMOTE_DIRTY_STATE_PROBE_FAILED"
    )
    assert "/remote/project/runs/real" in diagnostic.detail
    if return_code == 255:
        assert "SSH passwordless login failed" in diagnostic.detail
    elif return_code in {126, 127}:
        assert "remote command is unavailable" in diagnostic.detail
        assert f"return_code={return_code}" in diagnostic.detail
    else:
        assert "remote command failed" in diagnostic.detail
        assert "return_code=2" in diagnostic.detail


@pytest.mark.parametrize("return_code", [1, 2, 126, 127, 255])
def test_remote_doctor_dirty_state_listing_fails_closed_on_nonzero_exit(
    tmp_path: Path,
    return_code: int,
) -> None:
    runner = _DirtyStateExitCodeRunner(listing_return_code=return_code)
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=runner, cache_root=tmp_path)

    assert report.status == "fail"
    assert report.dirty_state["has_runs"] is None
    diagnostic = next(
        issue
        for issue in report.structured_issues
        if issue.code == "REMOTE_DIRTY_STATE_PROBE_FAILED"
    )
    listing_command = next(
        command
        for command in runner.commands
        if command.startswith("ls -1 /remote/project/runs/real")
    )
    assert "2>/dev/null" not in listing_command
    assert "remote real-run directory listing" in diagnostic.detail
    assert "dirty listing failed" in diagnostic.detail
    if return_code == 255:
        assert "SSH passwordless login failed" in diagnostic.detail
    elif return_code in {126, 127}:
        assert "remote command is unavailable" in diagnostic.detail
        assert f"return_code={return_code}" in diagnostic.detail
    else:
        assert "remote command failed" in diagnostic.detail
        assert f"return_code={return_code}" in diagnostic.detail


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
