"""Tests for B-05: require_license_check enforcement — license_probe module."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import patch

from hermes_workflow.license_probe import (
    LicenseFeature,
    LicenseProbeReport,
    parse_lmstat_output,
    run_license_probe_skipped,
    run_local_license_probe,
    run_remote_license_probe,
    write_license_probe_report,
    LICENSE_PROBE_REPORT_NAME,
)


# ── parse_lmstat_output ────────────────────────────────────────────────────


class TestParseLmstatOutput:
    def test_parses_users_of_line_with_licenses_in_use(self) -> None:
        text = (
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 1
        assert features[0].name == "Spectre_X"
        assert features[0].total_issued == 10
        assert features[0].total_in_use == 3

    def test_parses_zero_licenses_in_use(self) -> None:
        text = (
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 0 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 1
        assert features[0].total_in_use == 0

    def test_parses_multiple_features(self) -> None:
        text = (
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
            "Some other line\n"
            "Users of Virtuoso:  (Total of 5 licenses issued;  Total of 1 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 2
        assert features[0].name == "Spectre_X"
        assert features[1].name == "Virtuoso"

    def test_empty_output_returns_empty_list(self) -> None:
        features = parse_lmstat_output("")
        assert features == []

    def test_no_users_of_lines_returns_empty_list(self) -> None:
        text = "lmstat - Copyright (c) Flexera\nSome random output\n"
        features = parse_lmstat_output(text)
        assert features == []

    def test_malformed_users_line_skipped(self) -> None:
        text = "Users of Spectre_X: something wrong here\n"
        features = parse_lmstat_output(text)
        assert features == []

    # ── B-05: enhanced lmstat parsing for real-world variants ───────────

    def test_parses_total_without_of_issued(self) -> None:
        """Real lmstat output may omit 'of': 'Total 999 licenses issued'."""
        text = (
            "Users of e_nexus_datadisplay_nexus: (Total 999 licenses issued; 0 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 1
        assert features[0].name == "e_nexus_datadisplay_nexus"
        assert features[0].total_issued == 999
        assert features[0].total_in_use == 0

    def test_parses_single_space_before_licenses(self) -> None:
        """Handle variable spacing: 'Total of 10 licenses' vs 'Total 999 licenses'."""
        text = (
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 1
        assert features[0].total_issued == 10
        assert features[0].total_in_use == 3

    def test_parses_no_of_and_no_total_of_in_use(self) -> None:
        """Both 'Total' and 'Total of' variants in the same line."""
        text = (
            "Users of e_nexus_datadisplay_nexus: (Total 999 licenses issued; 0 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 1
        assert features[0].total_issued == 999
        assert features[0].total_in_use == 0

    def test_any_feature_name_not_just_spectre(self) -> None:
        """Parser must accept arbitrary feature names, not just Spectre_*."""
        text = (
            "Users of e_nexus_datadisplay_nexus: (Total 999 licenses issued; 0 licenses in use)\n"
            "Users of Virtuoso_XL:  (Total of 5 licenses issued;  Total of 1 licenses in use)\n"
        )
        features = parse_lmstat_output(text)
        assert len(features) == 2
        assert features[0].name == "e_nexus_datadisplay_nexus"
        assert features[1].name == "Virtuoso_XL"


# ── run_local_license_probe with fake subprocess ───────────────────────────


class FakeCompletedProcess:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _make_fake_subprocess_run(stdout: str, stderr: str = "", returncode: int = 0):
    """Return a fake subprocess.run that returns the given output."""

    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(stdout, stderr, returncode)

    return fake_run


class TestRunLocalLicenseProbe:
    def test_success_probe_has_spectre_path_and_version(self, tmp_path: Path) -> None:
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_output = (
            "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
            "spectre version 23.1.0\n"
            "SPECTRE_VERSION_RC=0\n"
            "LMSTAT_BEGIN\n"
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
            "LMSTAT_RC=0\n"
            "LMSTAT_END\n"
        )
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "pass"
        assert report.execution_mode == "local"
        assert report.require_license_check is True
        assert report.spectre_path == "/tools/spectre/bin/spectre"
        assert report.spectre_version == "spectre version 23.1.0"
        assert report.lmstat_available is True
        assert len(report.license_features) == 1
        assert report.license_features[0].name == "Spectre_X"
        assert report.issues == []

    def test_spectre_missing_fails(self, tmp_path: Path) -> None:
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_output = "SPECTRE_PATH=NOTFOUND\n"
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "fail"
        assert report.spectre_path is None
        assert any("spectre not found" in issue for issue in report.issues)

    def test_cshrc_missing_fails(self, tmp_path: Path) -> None:
        cshrc = tmp_path / "nonexistent.csh"
        report = run_local_license_probe(cshrc)
        assert report.status == "fail"
        assert any("cshrc does not exist" in issue for issue in report.issues)

    def test_spectre_v_fails_but_path_found_passes(self, tmp_path: Path) -> None:
        """If spectre is found but -V fails, the probe should still pass
        (spectre_path is the critical check; version is informational)."""
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_output = "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "pass"
        assert report.spectre_path is not None

    def test_lmstat_not_available_passes_if_spectre_found(
        self, tmp_path: Path
    ) -> None:
        """lmstat absence should not cause failure if spectre is found.
        lmstat is informational — not all sites have it installed."""
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_output = "SPECTRE_PATH=/tools/spectre/bin/spectre\nversion line\n"
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "pass"
        assert report.lmstat_available is False

    def test_probe_does_not_write_cshrc_content_to_report(
        self, tmp_path: Path
    ) -> None:
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("setenv SECRET_KEY abc123\n", encoding="utf-8")
        fake_output = "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        report_str = json.dumps(report.to_dict())
        assert "SECRET_KEY" not in report_str
        assert "abc123" not in report_str

    def test_csh_not_available_fails(self, tmp_path: Path) -> None:
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            side_effect=FileNotFoundError("csh not found"),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "fail"
        assert any("csh is not available" in issue for issue in report.issues)

    def test_timeout_fails(self, tmp_path: Path) -> None:
        import subprocess

        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="csh", timeout=30),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "fail"
        assert any("timed out" in issue for issue in report.issues)


# ── B-05 RED: csh compatibility tests ──────────────────────────────────────


class TestCshCompatibility:
    """RED tests: verify probe scripts are csh-compatible.

    These tests MUST fail with the current code that uses $() inside csh -fc.
    """

    def test_local_probe_script_does_not_contain_dollar_paren(
        self, tmp_path: Path
    ) -> None:
        """The generated csh probe script must NOT contain $() (bash syntax).

        csh does not support $() command substitution; only backticks work.
        """
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        scripts_seen: list[str] = []

        def capture_script(cmd, **kwargs):
            # cmd is ["csh", "-fc", <script>]
            if len(cmd) >= 3:
                scripts_seen.append(cmd[2])
            return FakeCompletedProcess(
                stdout="SPECTRE_PATH=/tools/spectre/bin/spectre\n",
                stderr="",
                returncode=0,
            )

        with patch("hermes_workflow.license_probe.subprocess.run", capture_script):
            run_local_license_probe(cshrc)

        assert len(scripts_seen) == 1
        script = scripts_seen[0]
        assert "$(" not in script, (
            f"Probe script contains $() which is invalid csh syntax: {script!r}"
        )

    def test_local_probe_script_uses_csh_set_and_backtick(
        self, tmp_path: Path
    ) -> None:
        """The generated csh probe script must use csh-compatible syntax.

        Must use backtick `` which ... `` instead of $(which ...).
        Must use `set var=...` / `if (...) then` / `endif` for conditionals.
        Must use glob pattern =~ /* instead of == "" for path check.
        """
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        scripts_seen: list[str] = []

        def capture_script(cmd, **kwargs):
            if len(cmd) >= 3:
                scripts_seen.append(cmd[2])
            return FakeCompletedProcess(
                stdout="SPECTRE_PATH=/tools/spectre/bin/spectre\n",
                stderr="",
                returncode=0,
            )

        with patch("hermes_workflow.license_probe.subprocess.run", capture_script):
            run_local_license_probe(cshrc)

        assert len(scripts_seen) == 1
        script = scripts_seen[0]
        # Must NOT use $() — already checked above
        # Must use backtick command substitution for `which spectre`
        assert "`which spectre`" in script or "`which spectre " in script, (
            f"Probe script must use backtick `which spectre` syntax: {script!r}"
        )
        # Must use glob pattern for path detection (not empty string check)
        assert "=~ /*" in script, (
            f"Probe script must use glob =~ /* for path check: {script!r}"
        )

    def test_parse_probe_output_surfaces_stderr_on_csh_syntax_error(
        self, tmp_path: Path
    ) -> None:
        """When csh hits $(), stderr contains 'Illegal variable name'.

        _parse_probe_output must surface this in issues rather than
        just saying 'spectre not found'.
        """
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        # Simulate what really happens: csh errors on $(), emits nothing to stdout
        fake_stderr = "Illegal variable name.\n"
        fake_stdout = ""

        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_stdout, fake_stderr, returncode=1),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "fail"
        # The issues must mention the stderr content, not just "spectre not found"
        issues_text = " ".join(report.issues)
        assert "Illegal variable name" in issues_text or "stderr" in issues_text, (
            f"Expected stderr/csh error in issues, got: {report.issues}"
        )

    def test_spectre_version_rc_in_report_when_available(self, tmp_path: Path) -> None:
        """Report should include spectre_version_rc and lmstat_rc if present."""
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_output = (
            "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
            "spectre version 23.1.0\n"
            "SPECTRE_VERSION_RC=0\n"
            "LMSTAT_BEGIN\n"
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
            "LMSTAT_RC=0\n"
            "LMSTAT_END\n"
        )
        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run(fake_output),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "pass"
        assert report.spectre_path == "/tools/spectre/bin/spectre"
        assert report.spectre_version == "spectre version 23.1.0"
        # Check new fields
        assert getattr(report, "spectre_version_rc", None) == 0
        assert getattr(report, "lmstat_rc", None) == 0

    def test_raw_stderr_in_report_when_probe_fails(self, tmp_path: Path) -> None:
        """Report should include raw_stderr when probe command fails."""
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        fake_stderr = "Some error on stderr\n"

        with patch(
            "hermes_workflow.license_probe.subprocess.run",
            _make_fake_subprocess_run("", fake_stderr, returncode=1),
        ):
            report = run_local_license_probe(cshrc)

        assert report.status == "fail"
        raw_stderr = getattr(report, "raw_stderr", None)
        assert raw_stderr is not None, "Report must include raw_stderr field"

    def test_local_probe_script_no_bash_2_redirect(self, tmp_path: Path) -> None:
        """The probe script must not use bash-only 2>&1 | syntax.

        csh uses |& instead of 2>&1 | for piping both stdout and stderr.
        """
        cshrc = tmp_path / "cadence_env.csh"
        cshrc.write_text("# cshrc\n", encoding="utf-8")
        scripts_seen: list[str] = []

        def capture_script(cmd, **kwargs):
            if len(cmd) >= 3:
                scripts_seen.append(cmd[2])
            return FakeCompletedProcess(
                stdout="SPECTRE_PATH=/tools/spectre/bin/spectre\n",
                stderr="",
                returncode=0,
            )

        with patch("hermes_workflow.license_probe.subprocess.run", capture_script):
            run_local_license_probe(cshrc)

        assert len(scripts_seen) == 1
        script = scripts_seen[0]
        assert "2>&1" not in script, (
            f"Probe script contains bash-only 2>&1 syntax: {script!r}"
        )


# ── run_remote_license_probe with fake runner ──────────────────────────────


class FakeRemoteRunner:
    def __init__(self, stdout: str = "", return_code: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.return_code = return_code
        self.stderr = stderr
        self.commands: list[str] = []

    def run(self, command: str, **kwargs) -> Any:
        self.commands.append(command)
        from hermes_workflow.remote_ssh import RemoteCommandResult

        return RemoteCommandResult(
            return_code=self.return_code,
            stdout=self.stdout,
            stderr=self.stderr,
            argv=["ssh", "lab", command],
        )


class TestRunRemoteLicenseProbe:
    def test_success_probe_has_spectre_path_and_version(self) -> None:
        fake_output = (
            "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
            "spectre version 23.1.0\n"
            "SPECTRE_VERSION_RC=0\n"
            "LMSTAT_BEGIN\n"
            "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)\n"
            "LMSTAT_RC=0\n"
            "LMSTAT_END\n"
        )
        runner = FakeRemoteRunner(stdout=fake_output)
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        report = run_remote_license_probe(runner, cshrc)

        assert report.status == "pass"
        assert report.execution_mode == "remote"
        assert report.spectre_path == "/tools/spectre/bin/spectre"
        assert report.spectre_version == "spectre version 23.1.0"
        assert len(report.license_features) == 1
        # Verify command used csh -fc with source
        assert any("csh -fc" in cmd for cmd in runner.commands)

    def test_spectre_missing_fails(self) -> None:
        fake_output = "SPECTRE_PATH=NOTFOUND\n"
        runner = FakeRemoteRunner(stdout=fake_output)
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        report = run_remote_license_probe(runner, cshrc)

        assert report.status == "fail"
        assert report.spectre_path is None

    def test_runner_exception_fails(self) -> None:
        class ExceptionRunner:
            def run(self, command, **kwargs):
                raise RuntimeError("SSH connection failed")

        runner = ExceptionRunner()
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        report = run_remote_license_probe(runner, cshrc)

        assert report.status == "fail"
        assert any("remote license probe command failed" in issue for issue in report.issues)

    def test_report_does_not_leak_cshrc_path_or_ssh(self) -> None:
        fake_output = "SPECTRE_PATH=/tools/spectre/bin/spectre\n"
        runner = FakeRemoteRunner(stdout=fake_output)
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        report = run_remote_license_probe(runner, cshrc)

        report_str = json.dumps(report.to_dict())
        assert str(cshrc) not in report_str
        assert "ssh" not in report_str.lower()

    def test_sources_remote_cshrc_before_probe(self) -> None:
        runner = FakeRemoteRunner(stdout="SPECTRE_PATH=/tools/spectre\n")
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        run_remote_license_probe(runner, cshrc)

        assert len(runner.commands) == 1
        cmd = runner.commands[0]
        assert "csh -fc" in cmd
        # The cshrc path should appear in the command (it's sent to the
        # remote host), but must NOT appear in the report output

    # ── B-05 RED: remote csh compatibility tests ────────────────────────

    def test_remote_probe_script_does_not_contain_dollar_paren(self) -> None:
        """Remote probe script must NOT contain $() (bash syntax)."""
        runner = FakeRemoteRunner(stdout="SPECTRE_PATH=/tools/spectre\n")
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        run_remote_license_probe(runner, cshrc)

        assert len(runner.commands) == 1
        cmd = runner.commands[0]
        assert "$(" not in cmd, (
            f"Remote probe script contains $() which is invalid csh: {cmd!r}"
        )

    def test_remote_probe_script_uses_backtick_which(self) -> None:
        """Remote probe script must use backtick `which spectre` syntax."""
        runner = FakeRemoteRunner(stdout="SPECTRE_PATH=/tools/spectre\n")
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        run_remote_license_probe(runner, cshrc)

        assert len(runner.commands) == 1
        cmd = runner.commands[0]
        assert "`which spectre`" in cmd or "`which spectre " in cmd, (
            f"Remote probe script must use backtick `which spectre`: {cmd!r}"
        )

    def test_remote_probe_script_no_bash_2_redirect(self) -> None:
        """Remote probe script must not use bash-only 2>&1 | syntax."""
        runner = FakeRemoteRunner(stdout="SPECTRE_PATH=/tools/spectre\n")
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        run_remote_license_probe(runner, cshrc)

        assert len(runner.commands) == 1
        cmd = runner.commands[0]
        assert "2>&1" not in cmd, (
            f"Remote probe script contains bash-only 2>&1: {cmd!r}"
        )

    def test_remote_csh_syntax_error_surfaces_in_issues(self) -> None:
        """When remote probe has csh syntax error, issues must show stderr."""
        runner = FakeRemoteRunner(
            stdout="",
            stderr="Illegal variable name.\n",
            return_code=1,
        )
        cshrc = PurePosixPath("/remote/project/cadence_env.csh")

        report = run_remote_license_probe(runner, cshrc)

        assert report.status == "fail"
        issues_text = " ".join(report.issues)
        assert "Illegal variable name" in issues_text or "stderr" in issues_text, (
            f"Expected stderr/csh error in remote issues, got: {report.issues}"
        )


# ── run_license_probe_skipped ──────────────────────────────────────────────


class TestRunLicenseProbeSkipped:
    def test_skipped_report_has_correct_fields(self) -> None:
        report = run_license_probe_skipped(execution_mode="local")
        assert report.status == "skipped"
        assert report.require_license_check is False
        assert report.execution_mode == "local"
        assert report.spectre_path is None
        assert report.issues == []

    def test_skipped_remote(self) -> None:
        report = run_license_probe_skipped(execution_mode="remote")
        assert report.status == "skipped"
        assert report.execution_mode == "remote"

    def test_skipped_does_not_execute_probe_commands(self, tmp_path: Path) -> None:
        """require_license_check: false must skip all shell probe execution."""
        report = run_license_probe_skipped(execution_mode="local")
        assert report.status == "skipped"
        assert report.require_license_check is False
        # No subprocess.run should have been invoked
        assert report.spectre_path is None
        assert report.spectre_version is None
        assert report.lmstat_available is False
        assert report.license_features == []


# ── write_license_probe_report ─────────────────────────────────────────────


class TestWriteLicenseProbeReport:
    def test_writes_json_report(self, tmp_path: Path) -> None:
        report = LicenseProbeReport(
            status="pass",
            execution_mode="local",
            require_license_check=True,
            spectre_path="/tools/spectre",
            spectre_version="23.1",
            lmstat_available=True,
            license_features=[
                LicenseFeature(name="Spectre_X", total_issued=10, total_in_use=3)
            ],
            raw_license_lines=[
                "Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)"
            ],
            issues=[],
        )

        path = write_license_probe_report(tmp_path, report)

        assert path == tmp_path / LICENSE_PROBE_REPORT_NAME
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "pass"
        assert data["schema_version"] == "1.0"
        assert data["spectre_path"] == "/tools/spectre"
        assert len(data["license_features"]) == 1
        assert data["license_features"][0]["name"] == "Spectre_X"

    def test_skipped_report_writes_skipped_status(self, tmp_path: Path) -> None:
        report = run_license_probe_skipped(execution_mode="local")
        path = write_license_probe_report(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "skipped"
        assert data["require_license_check"] is False

    def test_report_does_not_contain_license_guaranteed(self, tmp_path: Path) -> None:
        report = LicenseProbeReport(
            status="pass",
            execution_mode="local",
            require_license_check=True,
        )
        path = write_license_probe_report(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        report_str = json.dumps(data)
        assert "license_guaranteed" not in report_str
        assert "guaranteed" not in report_str

    def test_report_includes_new_diagnostic_fields(self, tmp_path: Path) -> None:
        """Report with spectre_version_rc, lmstat_rc, raw_stderr fields."""
        report = LicenseProbeReport(
            status="pass",
            execution_mode="local",
            require_license_check=True,
            spectre_path="/tools/spectre",
            spectre_version="23.1",
            lmstat_available=True,
            spectre_version_rc=0,
            lmstat_rc=0,
            raw_stderr="",
            issues=[],
        )
        path = write_license_probe_report(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "spectre_version_rc" in data
        assert data["spectre_version_rc"] == 0
        assert "lmstat_rc" in data
        assert data["lmstat_rc"] == 0
        assert "raw_stderr" in data

    def test_fail_report_preserves_raw_stderr(self, tmp_path: Path) -> None:
        """When probe fails, raw_stderr must be preserved in the report."""
        report = LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            raw_stderr="Illegal variable name.\n",
            issues=["csh syntax error in license probe: Illegal variable name."],
        )
        path = write_license_probe_report(tmp_path, report)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "Illegal variable name" in data.get("raw_stderr", "")
        assert data["status"] == "fail"


# ── _build_csh_license_probe_script helper tests ───────────────────────────


class TestBuildCshProbeScript:
    """Test the _build_csh_license_probe_script helper directly."""

    def test_script_no_dollar_paren(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "$(" not in script

    def test_script_uses_backtick_which_spectre(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "`which spectre`" in script

    def test_script_sources_cshrc(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "source" in script
        assert "/path/to/cadence_env.csh" in script

    def test_script_runs_spectre_v(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "spectre -V" in script

    def test_script_runs_lmstat(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "lmstat" in script

    def test_script_emits_spectre_path_marker(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "SPECTRE_PATH=" in script

    def test_script_emits_version_rc_marker(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "SPECTRE_VERSION_RC" in script

    def test_script_emits_lmstat_rc_marker(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "LMSTAT_RC" in script

    def test_script_emits_lmstat_begin_end(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "LMSTAT_BEGIN" in script
        assert "LMSTAT_END" in script

    def test_script_no_bash_2_redirect(self) -> None:
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "2>&1" not in script

    def test_script_uses_csh_pipe_both(self) -> None:
        """Script should use |& (csh pipe-both) instead of 2>&1 |."""
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        # spectre -V |& head -1 is the csh-native way
        if "spectre -V" in script:
            # Should use |& or just spectre -V without pipe
            # Either |& or no pipe at all is fine, but NOT 2>&1 |
            assert "2>&1" not in script

    def test_script_uses_newlines_not_semicolons_for_if(self) -> None:
        """csh if/then/else/endif requires newlines, not semicolons."""
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        # Must NOT have 'then;' or 'else;' or 'endif;' (semicolon after keyword)
        assert "then;" not in script
        assert "else;" not in script
        assert "endif;" not in script
        # Must have actual newlines
        assert "\n" in script

    def test_script_uses_glob_pattern_for_path_check(self) -> None:
        """Script must use =~ /* glob to detect real paths.

        tcsh 'which spectre' outputs 'spectre: Command not found.' to stdout
        when spectre is not found, so empty-string check doesn't work.
        A glob pattern =~ /* checks that the result starts with / (a real path).
        """
        from hermes_workflow.license_probe import _build_csh_license_probe_script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        assert "=~ /*" in script

        script = _build_csh_license_probe_script("/path/to/cadence_env.csh")
        # spectre -V |& head -1 is the csh-native way
        if "spectre -V" in script:
            # Should use |& or just spectre -V without pipe
            # Either |& or no pipe at all is fine, but NOT 2>&1 |
            assert "2>&1" not in script
