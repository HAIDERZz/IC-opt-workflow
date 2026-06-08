# Remote SSH Execution Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a remote SSH execution mode where local `ic-opt`/OpenBox/report orchestration controls a project directory on a Linux EDA server, while Spectre/OCEAN run remotely through user-configured passwordless SSH.

**Status 2026-06-08:** Implemented, reviewed, and real-accepted for the remote SSH MVP. Tasks 1-10 are complete. Final code commit for the remote Maestro symlink materialization path is `fb0497c`. Final full regression passed with `718 passed, 1 warning`; ruff, cadence check, and `git diff --check` passed. Real remote doctor, real smoke, and continuation acceptance are recorded in `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md`.

**Real acceptance summary:** user verified passwordless SSH for `zzchen@10.113.216.131`. Clean remote project `/home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001` passed `--doctor`, completed a 10-evaluation remote `--real` smoke, and completed `--continue 4`; cumulative evaluations reached 14 on both the remote project and local mirror. The user's current metric formulas produced only `metric_check_failed` rows, so the evidence proves remote execution, artifact sync, and failure classification, not a usable optimized point for that project.

**Architecture:** Keep local mode unchanged. Add a focused OpenSSH runner, a remote project/cache layer, a remote doctor gate, and a remote Spectre/OCEAN adapter that runs Cadence commands on Linux without requiring the full Python product environment there. Route product CLI remote commands through these new pieces and sync reports back to both local cache and remote project.

**Tech Stack:** Python 3.10+, Typer CLI, existing Hermes workflow modules, system OpenSSH/`tar`, pytest, Pydantic/dataclasses, existing OpenBox ask-and-tell backend.

---

## Source Design

Use the C-69 design spec as the authority:

```text
docs/superpowers/specs/2026-06-08-remote-ssh-execution-backend-design.md
```

Implementation must preserve these design decisions:

- User configures passwordless SSH outside the product.
- `ic-opt` must not manage passwords or private keys.
- Remote project directory is the source of truth.
- Local workstation runs `ic-opt`, OpenBox, agent skill, and report interpretation.
- Remote Linux host runs Spectre/OCEAN only.
- Remote mode must not require OpenBox or the product Python package on the EDA server for the MVP.
- Doctor must not launch a real Spectre simulation.
- No PSF parsing, no OCEAN formula rewrite, no Spectre version hardcode.

## File Structure

Create focused files instead of expanding `product_cli.py` or `spectre_ocean.py` into remote catch-all modules.

```text
src/hermes_workflow/remote_ssh.py
  OpenSSH command wrapper, path quoting, text/file/tree transfer helpers, redacted command manifest primitives.

src/hermes_workflow/remote_project.py
  Remote project reference, local cache path derivation, cache manifest, local/remote report sync helpers.

src/hermes_workflow/remote_doctor.py
  Remote readiness checks and doctor report writer.

src/hermes_workflow/remote_prepare.py
  Download remote markdown and Maestro/ADE netlist bundles into the local controller cache without requiring remote Python.

src/hermes_workflow/execution_adapters/remote_spectre_ocean.py
  Remote Spectre/OCEAN adapter. Generates local scripts/manifests, uploads candidate run package, runs remote Cadence commands, downloads scalar artifacts, writes manifests locally, syncs manifests back.

src/hermes_workflow/remote_optimizer_flow.py
  Product-level remote flow for `--doctor`, `--real`, and `--continue`.

tests/test_remote_ssh.py
tests/test_remote_project.py
tests/test_remote_doctor.py
tests/test_remote_prepare.py
tests/test_remote_spectre_ocean.py
tests/test_remote_optimizer_flow.py
tests/test_product_cli_remote.py
```

Modify these existing files:

```text
src/hermes_workflow/product_cli.py
  Add --ssh-profile, --doctor, --continue, remote cadence env resolution behavior, and remote flow dispatch.

src/hermes_workflow/cli.py
  Add lower-level hermes-workflow commands for remote doctor and remote smoke if needed for debugging.

src/hermes_workflow/requirement_intake.py
  Extract public requirement parsing helpers so remote doctor can validate requirement text while checking maestro_point_root paths over SSH.

src/hermes_workflow/openbox_backend.py
  Only if the remote adapter needs a tiny signature hook. Prefer the existing injected adapter parameter first.

skills/ic-opt/SKILL.md
  Teach agents to route remote requests to `ic-opt --ssh-profile PROFILE PROJECT ...` after code lands.

docs/USER_GUIDE_CN.md or release-package equivalent
  Add remote SSH mode usage after code lands and real acceptance passes.
```

## Task 1: Remote SSH Runner

Status: completed and reviewed in commits `17a5037`, `b658ebd`, `c35c39e`,
`3680050`, and `bd510ab`.

**Files:**
- Create: `src/hermes_workflow/remote_ssh.py`
- Test: `tests/test_remote_ssh.py`

- [x] **Step 1: Write failing tests for command construction and failure mapping**

Create `tests/test_remote_ssh.py`:

```python
from __future__ import annotations

from pathlib import PurePosixPath

from hermes_workflow.remote_ssh import RemoteCommandResult, RemoteSshRunner


def test_remote_runner_uses_batchmode_and_profile() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="ok\n", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    result = runner.run("test -d /remote/project", timeout_s=12)

    assert result.return_code == 0
    assert calls == [
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "lab",
            "test -d /remote/project",
        ]
    ]


def test_remote_runner_wraps_cwd_with_posix_cd() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    runner.run("pwd", cwd=PurePosixPath("/tmp/a path"))

    assert calls[0][-1] == "cd '/tmp/a path' && pwd"


def test_remote_runner_check_raises_actionable_connection_error() -> None:
    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        return RemoteCommandResult(return_code=255, stdout="", stderr="Permission denied", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    try:
        runner.run("true", check=True)
    except RuntimeError as exc:
        assert 'SSH passwordless login failed for profile "lab"' in str(exc)
        assert "ssh lab true" in str(exc)
    else:
        raise AssertionError("expected connection error")


def test_remote_runner_read_text_uses_cat() -> None:
    calls: list[list[str]] = []

    def fake_execute(argv: list[str], *, input_text: str | None, timeout_s: int | None) -> RemoteCommandResult:
        calls.append(argv)
        return RemoteCommandResult(return_code=0, stdout="hello", stderr="", argv=argv)

    runner = RemoteSshRunner("lab", execute=fake_execute)

    assert runner.read_text(PurePosixPath("/remote/opt_requirement.md")) == "hello"
    assert calls[0][-1] == "cat /remote/opt_requirement.md"
```

- [x] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_ssh.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.remote_ssh'`.

- [x] **Step 3: Implement the minimal SSH runner**

Create `src/hermes_workflow/remote_ssh.py`:

```python
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


@dataclass(frozen=True)
class RemoteCommandResult:
    return_code: int
    stdout: str
    stderr: str
    argv: list[str]


ExecuteRemoteCommand = Callable[..., RemoteCommandResult]


def _default_execute(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout_s: int | None = None,
) -> RemoteCommandResult:
    completed = subprocess.run(
        argv,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    return RemoteCommandResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        argv=argv,
    )


def quote_remote_path(path: str | PurePosixPath) -> str:
    return shlex.quote(str(path))


class RemoteSshRunner:
    def __init__(
        self,
        profile: str,
        *,
        execute: ExecuteRemoteCommand = _default_execute,
    ) -> None:
        if not profile.strip():
            raise ValueError("ssh profile must not be empty")
        self.profile = profile
        self._execute = execute

    def run(
        self,
        command: str,
        *,
        cwd: PurePosixPath | str | None = None,
        timeout_s: int | None = None,
        input_text: str | None = None,
        check: bool = False,
    ) -> RemoteCommandResult:
        remote_command = command
        if cwd is not None:
            remote_command = f"cd {quote_remote_path(cwd)} && {command}"
        argv = ["ssh", "-o", "BatchMode=yes", self.profile, remote_command]
        result = self._execute(argv, input_text=input_text, timeout_s=timeout_s)
        if check and result.return_code != 0:
            self._raise_checked_error(result)
        return result

    def read_text(self, remote_path: PurePosixPath | str) -> str:
        result = self.run(f"cat {quote_remote_path(remote_path)}", check=True)
        return result.stdout

    def write_text(self, remote_path: PurePosixPath | str, text: str) -> None:
        command = f"cat > {quote_remote_path(remote_path)}"
        self.run(command, input_text=text, check=True)

    def exists(self, remote_path: PurePosixPath | str) -> bool:
        result = self.run(f"test -e {quote_remote_path(remote_path)}")
        return result.return_code == 0

    def mkdir(self, remote_path: PurePosixPath | str) -> None:
        self.run(f"mkdir -p {quote_remote_path(remote_path)}", check=True)

    def download(self, remote_path: PurePosixPath | str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            f"{self.profile}:{remote_path}",
            str(local_path),
        ]
        result = self._execute(argv, input_text=None, timeout_s=None)
        if result.return_code != 0:
            self._raise_checked_error(result)

    def upload(self, local_path: Path, remote_path: PurePosixPath | str) -> None:
        argv = [
            "scp",
            "-o",
            "BatchMode=yes",
            str(local_path),
            f"{self.profile}:{remote_path}",
        ]
        result = self._execute(argv, input_text=None, timeout_s=None)
        if result.return_code != 0:
            self._raise_checked_error(result)

    def _raise_checked_error(self, result: RemoteCommandResult) -> None:
        if result.return_code == 255:
            raise RuntimeError(
                f'SSH passwordless login failed for profile "{self.profile}". '
                f"Configure ~/.ssh/config and key-based login, then verify: "
                f"ssh {self.profile} true. stderr: {result.stderr.strip()}"
            )
        raise RuntimeError(
            "remote command failed: "
            f"return_code={result.return_code}, command={result.argv[-1]!r}, "
            f"stderr={result.stderr.strip()}"
        )
```

- [x] **Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_ssh.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_ssh.py tests/test_remote_ssh.py
rtk git commit -m "feat: add remote ssh runner"
```

## Task 2: Remote Project Reference And Cache

**Files:**
- Create: `src/hermes_workflow/remote_project.py`
- Test: `tests/test_remote_project.py`

- [x] **Step 1: Write failing tests for remote path validation and cache path**

Create `tests/test_remote_project.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath

from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir


def test_remote_project_ref_rejects_relative_remote_path() -> None:
    try:
        RemoteProjectRef(ssh_profile="lab", remote_project_dir=PurePosixPath("relative/project"))
    except ValueError as exc:
        assert "remote project path must be absolute" in str(exc)
    else:
        raise AssertionError("expected relative path rejection")


def test_remote_project_cache_path_is_stable_and_profile_scoped(tmp_path: Path) -> None:
    ref = RemoteProjectRef(
        ssh_profile="lab",
        remote_project_dir=PurePosixPath("/home/user/spectre_opt_prj/Mixer"),
    )

    first = remote_cache_dir(ref, cache_root=tmp_path)
    second = remote_cache_dir(ref, cache_root=tmp_path)

    assert first == second
    assert first.parent == tmp_path / "lab"
    assert len(first.name) == 16


def test_remote_project_ref_report_paths_are_posix() -> None:
    ref = RemoteProjectRef(
        ssh_profile="lab",
        remote_project_dir=PurePosixPath("/remote/project"),
    )

    assert ref.remote_reports_dir == PurePosixPath("/remote/project/reports")
    assert ref.remote_doctor_report == PurePosixPath("/remote/project/reports/ic_opt_doctor_report.json")
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_project.py -q
```

Expected: FAIL because `hermes_workflow.remote_project` is missing.

- [x] **Step 3: Implement remote project reference**

Create `src/hermes_workflow/remote_project.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DEFAULT_REMOTE_CACHE_ROOT = Path("~/.ic-opt/remote_runs")


@dataclass(frozen=True)
class RemoteProjectRef:
    ssh_profile: str
    remote_project_dir: PurePosixPath

    def __post_init__(self) -> None:
        if not self.ssh_profile.strip():
            raise ValueError("ssh profile must not be empty")
        if not self.remote_project_dir.is_absolute():
            raise ValueError("remote project path must be absolute")

    @property
    def remote_reports_dir(self) -> PurePosixPath:
        return self.remote_project_dir / "reports"

    @property
    def remote_doctor_report(self) -> PurePosixPath:
        return self.remote_reports_dir / "ic_opt_doctor_report.json"


def remote_cache_dir(
    ref: RemoteProjectRef,
    *,
    cache_root: Path | None = None,
) -> Path:
    root = (cache_root or DEFAULT_REMOTE_CACHE_ROOT).expanduser()
    digest = hashlib.sha256(
        f"{ref.ssh_profile}\n{ref.remote_project_dir.as_posix()}".encode("utf-8")
    ).hexdigest()[:16]
    return root / ref.ssh_profile / digest
```

- [x] **Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_project.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_project.py tests/test_remote_project.py
rtk git commit -m "feat: add remote project cache reference"
```

## Task 3: Requirement Parsing For Remote Doctor

**Files:**
- Modify: `src/hermes_workflow/requirement_intake.py`
- Test: `tests/test_requirement_intake.py`

- [x] **Step 1: Write failing tests for injectable Maestro path checks**

Append to `tests/test_requirement_intake.py`:

```python
def test_parse_requirement_text_uses_injected_maestro_checker(tmp_path: Path) -> None:
    requirement_text = (VALID_PROJECT / "opt_requirement.md").read_text(encoding="utf-8").replace(
        "__MAESTRO_POINT_ROOT__",
        "/remote/maestro/Interactive.1/point_1",
    )
    checked: list[str] = []

    def remote_checker(path: str) -> bool:
        checked.append(path)
        return path == "/remote/maestro/Interactive.1/point_1/netlist/input.scs"

    from hermes_workflow.requirement_intake import parse_requirement_text

    report = parse_requirement_text(
        requirement_text,
        constraints_text=None,
        maestro_input_exists=remote_checker,
    )

    assert report.status == "pass"
    assert checked == ["/remote/maestro/Interactive.1/point_1/netlist/input.scs"]


def test_parse_requirement_text_reports_remote_maestro_missing() -> None:
    requirement_text = (VALID_PROJECT / "opt_requirement.md").read_text(encoding="utf-8").replace(
        "__MAESTRO_POINT_ROOT__",
        "/remote/missing_point",
    )

    from hermes_workflow.requirement_intake import parse_requirement_text

    report = parse_requirement_text(
        requirement_text,
        constraints_text=None,
        maestro_input_exists=lambda _path: False,
    )

    assert report.status == "fail"
    assert "maestro_point_root/netlist/input.scs is missing: /remote/missing_point/netlist/input.scs" in report.issues
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_requirement_intake.py::test_parse_requirement_text_uses_injected_maestro_checker tests/test_requirement_intake.py::test_parse_requirement_text_reports_remote_maestro_missing -q
```

Expected: FAIL because `parse_requirement_text` is missing.

- [x] **Step 3: Extract public parser without changing local behavior**

Modify `src/hermes_workflow/requirement_intake.py`:

```python
from collections.abc import Callable


def parse_requirement_text(
    requirement_text: str,
    *,
    constraints_text: str | None,
    maestro_input_exists: Callable[[str], bool],
) -> RequirementIntakeReport:
    issues: list[str] = []
    sections: dict[str, Any] = {}
    constraints_sha = (
        hashlib.sha256(constraints_text.encode("utf-8")).hexdigest()
        if constraints_text is not None
        else None
    )

    raw_sections, section_issues = _extract_required_sections(requirement_text)
    issues.extend(section_issues)
    if not issues:
        for name in REQUIRED_SECTIONS:
            payload, payload_issues = _parse_section_yaml(name, raw_sections[name])
            if payload_issues:
                issues.extend(payload_issues)
            else:
                sections[name] = payload

    if not issues:
        issues.extend(_validate_approval_checklist(sections))
        issues.extend(_validate_required_fields(sections))
        if not issues:
            try:
                render_config_payloads(sections)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                issues.append(f"rendered config validation failed: {exc}")
        for maestro_root in _maestro_point_roots(sections):
            netlist_input = PurePosixPath(str(maestro_root)) / "netlist" / "input.scs"
            if not maestro_input_exists(netlist_input.as_posix()):
                issues.append(f"maestro_point_root/netlist/input.scs is missing: {netlist_input.as_posix()}")

    return RequirementIntakeReport(
        status="pass" if not issues else "fail",
        issues=issues,
        sections=sections,
        constraints_md_present=constraints_text is not None,
        constraints_md_sha256=constraints_sha,
    )
```

Then modify `_parse_and_validate_requirement()` so it delegates to the new helper:

```python
def _parse_and_validate_requirement(project_dir: Path) -> RequirementIntakeReport:
    requirement_path = project_dir / "opt_requirement.md"
    constraints_path = project_dir / "constraints.md"
    if not requirement_path.exists():
        constraints_sha = _sha256(constraints_path) if constraints_path.is_file() else None
        return RequirementIntakeReport(
            status="fail",
            issues=["opt_requirement.md is missing"],
            sections={},
            constraints_md_present=constraints_path.is_file(),
            constraints_md_sha256=constraints_sha,
        )

    constraints_text = (
        constraints_path.read_text(encoding="utf-8")
        if constraints_path.is_file()
        else None
    )
    return parse_requirement_text(
        requirement_path.read_text(encoding="utf-8"),
        constraints_text=constraints_text,
        maestro_input_exists=lambda path: Path(path).expanduser().is_file(),
    )
```

Add missing import:

```python
from pathlib import Path, PurePosixPath
```

- [x] **Step 4: Run targeted and existing intake tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_requirement_intake.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/requirement_intake.py tests/test_requirement_intake.py
rtk git commit -m "refactor: expose requirement parser for remote paths"
```

## Task 4: Remote Doctor MVP

**Files:**
- Create: `src/hermes_workflow/remote_doctor.py`
- Test: `tests/test_remote_doctor.py`

- [x] **Step 1: Write failing tests for pass/fail doctor reports**

Create `tests/test_remote_doctor.py`:

```python
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteCommandResult


VALID_REQUIREMENT = (Path("tests/fixtures/requirement_intake/valid_project/opt_requirement.md")
    .read_text(encoding="utf-8")
    .replace("__MAESTRO_POINT_ROOT__", "/remote/maestro/point_1"))


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
            return RemoteCommandResult(0, "/tools/spectre\n/tools/ocean\n", "", ["ssh", "lab", command])
        if "mkdir -p /remote/project/reports" in command:
            return RemoteCommandResult(0, "", "", ["ssh", "lab", command])
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


def test_remote_doctor_fails_before_optimizer_when_ssh_is_not_ready(tmp_path: Path) -> None:
    class FailingSshRunner(FakeRunner):
        def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
            if command == "true":
                return RemoteCommandResult(255, "", "Permission denied", ["ssh", "lab", command])
            return super().run(command, **kwargs)

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))

    report = run_remote_doctor(ref, runner=FailingSshRunner(), cache_root=tmp_path)

    assert report.status == "fail"
    assert report.checks["ssh"]["status"] == "fail"
    assert "ssh lab true" in report.checks["ssh"]["message"]
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_doctor.py -q
```

Expected: FAIL because `hermes_workflow.remote_doctor` is missing.

- [x] **Step 3: Implement remote doctor**

Create `src/hermes_workflow/remote_doctor.py` with:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.remote_ssh import RemoteSshRunner, quote_remote_path
from hermes_workflow.requirement_intake import parse_requirement_text


@dataclass(frozen=True)
class RemoteDoctorReport:
    status: str
    ssh_profile: str
    remote_project_dir: str
    remote_report_path: str
    local_report_path: Path
    checks: dict[str, dict[str, str]]
    issues: list[str]


def run_remote_doctor(
    ref: RemoteProjectRef,
    *,
    runner: RemoteSshRunner | Any | None = None,
    cadence_cshrc: PurePosixPath | str | None = None,
    cache_root: Path | None = None,
) -> RemoteDoctorReport:
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    local_report_path = cache_dir / "reports" / "ic_opt_doctor_report.json"
    local_report_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, str]] = {}
    issues: list[str] = []

    _record_command_check(checks, issues, "ssh", ssh.run("true"), 'verify: ssh lab true')
    if issues:
        return _write_doctor(ref, ssh, local_report_path, checks, issues)

    _record_command_check(
        checks,
        issues,
        "remote_project_dir",
        ssh.run(f"test -d {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory exists",
    )
    _record_command_check(
        checks,
        issues,
        "remote_project_writable",
        ssh.run(f"test -w {quote_remote_path(ref.remote_project_dir)}"),
        "remote project directory is writable",
    )

    requirement_text = _read_required_remote_text(
        ssh,
        ref.remote_project_dir / "opt_requirement.md",
        checks,
        issues,
        "opt_requirement",
    )
    constraints_text = _read_optional_remote_text(ssh, ref.remote_project_dir / "constraints.md")
    if requirement_text is not None:
        req_report = parse_requirement_text(
            requirement_text,
            constraints_text=constraints_text,
            maestro_input_exists=lambda path: ssh.run(f"test -f {quote_remote_path(path)}").return_code == 0,
        )
        checks["requirement"] = {
            "status": req_report.status,
            "message": "; ".join(req_report.issues) if req_report.issues else "requirement is valid",
        }
        issues.extend(req_report.issues)

    cshrc_path = PurePosixPath(str(cadence_cshrc)) if cadence_cshrc is not None else ref.remote_project_dir / "cadence_env.csh"
    _record_command_check(
        checks,
        issues,
        "cadence_cshrc",
        ssh.run(f"test -f {quote_remote_path(cshrc_path)}"),
        f"cadence cshrc exists: {cshrc_path}",
    )
    _record_command_check(
        checks,
        issues,
        "spectre_ocean",
        ssh.run(
            "csh -fc "
            + quote_remote_path(
                f"source {cshrc_path}; which spectre; which ocean"
            )
        ),
        "spectre and ocean are available after sourcing cshrc",
    )
    return _write_doctor(ref, ssh, local_report_path, checks, issues)
```

Also define `_record_command_check`, `_read_required_remote_text`, `_read_optional_remote_text`, and `_write_doctor` in the same file. `_write_doctor` must call `ssh.mkdir(ref.remote_reports_dir)`, write JSON to `ref.remote_doctor_report`, write the same JSON locally, and return `status="pass"` only when `issues` is empty.

- [x] **Step 4: Run targeted doctor tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_doctor.py tests/test_requirement_intake.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_doctor.py tests/test_remote_doctor.py src/hermes_workflow/requirement_intake.py tests/test_requirement_intake.py
rtk git commit -m "feat: add remote doctor gate"
```

## Task 5: Product CLI Remote Doctor Route

**Files:**
- Modify: `src/hermes_workflow/product_cli.py`
- Test: `tests/test_product_cli_remote.py`

- [x] **Step 1: Write failing CLI tests**

Create `tests/test_product_cli_remote.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from typer.testing import CliRunner

from hermes_workflow import product_cli


runner = CliRunner()


def test_ic_opt_remote_doctor_does_not_resolve_local_cadence_env(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_remote_doctor(ref, **kwargs):
        calls.append({"ref": ref, **kwargs})
        report_path = tmp_path / "reports" / "ic_opt_doctor_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            local_report_path=report_path,
            remote_report_path="/remote/project/reports/ic_opt_doctor_report.json",
            issues=[],
        )

    monkeypatch.setattr(product_cli, "run_remote_doctor", fake_run_remote_doctor)

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--doctor"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["ref"].ssh_profile == "lab"
    assert calls[0]["ref"].remote_project_dir == PurePosixPath("/remote/project")
    assert "remote doctor completed" in result.output
    assert "remote report: /remote/project/reports/ic_opt_doctor_report.json" in result.output


def test_ic_opt_remote_real_reports_not_implemented_until_remote_flow_lands(monkeypatch) -> None:
    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--real"],
    )

    assert result.exit_code == 1
    assert "remote --real is not implemented yet; run --doctor first" in result.output
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli_remote.py -q
```

Expected: FAIL because `--ssh-profile` and `--doctor` are not wired.

- [x] **Step 3: Wire product CLI remote doctor**

Modify `src/hermes_workflow/product_cli.py`:

```python
from pathlib import Path, PurePosixPath
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_project import RemoteProjectRef
```

Add options to `main()`:

```python
    ssh_profile: Annotated[
        str | None,
        typer.Option("--ssh-profile", help="OpenSSH profile for remote Linux EDA server."),
    ] = None,
    doctor: Annotated[
        bool,
        typer.Option("--doctor", help="Check project/tool readiness without running Spectre."),
    ] = False,
    continue_evals: Annotated[
        int | None,
        typer.Option("--continue", min=1, help="Continue an existing optimization by N evaluations."),
    ] = None,
```

At the start of `main()`:

```python
    if ssh_profile is not None:
        ref = RemoteProjectRef(
            ssh_profile=ssh_profile,
            remote_project_dir=PurePosixPath(project_dir.as_posix()),
        )
        if doctor:
            report = run_remote_doctor(ref, cadence_cshrc=cadence_cshrc)
            if report.status == "pass":
                typer.echo("remote doctor completed")
                typer.echo(f"remote report: {report.remote_report_path}")
                typer.echo(f"local report: {report.local_report_path}")
                return
            typer.echo("remote doctor failed")
            for issue in report.issues:
                typer.echo(issue)
            typer.echo(f"local report: {report.local_report_path}")
            raise typer.Exit(code=1)
        if real:
            raise ValueError("remote --real is not implemented yet; run --doctor first")
        if continue_evals is not None:
            raise ValueError("remote --continue is not implemented yet; run --doctor first")
        raise ValueError("remote mode requires --doctor, --real, or --continue N")
```

Keep existing local behavior unchanged.

- [x] **Step 4: Run product CLI tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/product_cli.py tests/test_product_cli_remote.py
rtk git commit -m "feat: expose remote doctor in ic-opt"
```

## Task 6: Remote Project Cache Preparation

**Files:**
- Create: `src/hermes_workflow/remote_prepare.py`
- Test: `tests/test_remote_prepare.py`

- [x] **Step 1: Write failing tests for cache preparation**

Create `tests/test_remote_prepare.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath

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
        (local_path / "input.scs").write_text("simulator lang=spectre\n", encoding="utf-8")


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
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_prepare.py -q
```

Expected: FAIL because `remote_prepare` is missing.

- [x] **Step 3: Implement remote cache preparation**

Create `src/hermes_workflow/remote_prepare.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.remote_project import RemoteProjectRef, remote_cache_dir
from hermes_workflow.requirement_intake import (
    render_config_payloads,
    write_config_payloads,
    parse_requirement_text,
)


@dataclass(frozen=True)
class RemotePrepareResult:
    status: str
    cache_dir: Path
    issues: list[str]


def prepare_remote_project_cache(
    ref: RemoteProjectRef,
    *,
    runner: Any,
    cache_root: Path | None = None,
) -> RemotePrepareResult:
    cache_dir = remote_cache_dir(ref, cache_root=cache_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    requirement_text = runner.read_text(ref.remote_project_dir / "opt_requirement.md")
    try:
        constraints_text = runner.read_text(ref.remote_project_dir / "constraints.md")
    except Exception:
        constraints_text = None
    (cache_dir / "opt_requirement.md").write_text(requirement_text, encoding="utf-8")
    if constraints_text is not None:
        (cache_dir / "constraints.md").write_text(constraints_text, encoding="utf-8")

    report = parse_requirement_text(
        requirement_text,
        constraints_text=constraints_text,
        maestro_input_exists=lambda path: runner.run(f"test -f {path}").return_code == 0,
    )
    if report.status != "pass":
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=report.issues)

    write_config_payloads(cache_dir, render_config_payloads(report.sections))
    _download_remote_netlists(cache_dir, report.sections, runner)
    netlist_report = prepare_netlist(cache_dir)
    if netlist_report.status.value != "pass":
        return RemotePrepareResult(status="fail", cache_dir=cache_dir, issues=netlist_report.issues)
    return RemotePrepareResult(status="pass", cache_dir=cache_dir, issues=[])
```

Add `_download_remote_netlists()` using the same single-testbench/multi-testbench destination rules as `requirement_intake._import_destination()`:

```python
def _download_remote_netlists(cache_dir: Path, sections: dict[str, object], runner: Any) -> None:
    from hermes_workflow.requirement_intake import _dict_section, _testbench_sources

    maestro = _dict_section(sections, "Maestro Source")
    testbenches = _testbench_sources(maestro)
    for index, testbench in enumerate(testbenches):
        remote_netlist = PurePosixPath(str(testbench["maestro_point_root"])) / "netlist"
        if "testbenches" in maestro:
            destination = cache_dir / "netlists" / "testbenches" / str(testbench["id"]) / "exported"
        else:
            destination = cache_dir / "netlists" / "exported"
        runner.download_tree(remote_netlist, destination)
        if index == 0 and "testbenches" in maestro:
            runner.download_tree(remote_netlist, cache_dir / "netlists" / "exported")
```

This MVP downloads the remote `netlist/` directory. If a later real remote acceptance proves required sidecars live above `netlist/`, extend `download_tree()` roots in a new task with evidence.

- [x] **Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_prepare.py tests/test_requirement_intake.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_prepare.py tests/test_remote_prepare.py
rtk git commit -m "feat: prepare remote project cache"
```

## Task 7: Remote Spectre/OCEAN Single-Candidate Adapter

**Files:**
- Create: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Test: `tests/test_remote_spectre_ocean.py`

- [x] **Step 1: Write failing tests for upload/run/download behavior**

Create `tests/test_remote_spectre_ocean.py`:

```python
from __future__ import annotations

import json
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
            "gain\t4.0\tdB\tpass\tabc\t\n",
            encoding="utf-8",
        )

    def run(self, command: str, **kwargs: object) -> RemoteCommandResult:
        self.commands.append(command)
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
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected: FAIL because remote adapter is missing.

- [x] **Step 3: Implement remote adapter using local Python and remote Cadence commands**

Create `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterRunResult,
    load_adapter_context,
    render_ocean_replay_script,
)
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import quote_remote_path


def run_remote_spectre_ocean_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
) -> AdapterRunResult:
    context = load_adapter_context(project_dir, run_id=run_id)
    script_path = Path(context.request.ocean.script_file)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    remote_run_dir = remote_ref.remote_project_dir / "runs" / "real" / run_id
    runner.upload_tree(context.run_dir, remote_run_dir)

    remote_input_dir = remote_run_dir / "netlist"
    spectre_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {remote_cadence_cshrc}; cd {remote_input_dir}; "
            f"spectre -64 +preset=aps +mt={context.request.spectre.get('threads_per_run', 1)} "
            f"-format psfxl -raw ../psf input.scs"
        )
    )
    spectre_result = runner.run(spectre_command)
    if spectre_result.return_code != 0:
        return _write_remote_failure(context, "spectre command failed")

    ocean_command = (
        "csh -fc "
        + quote_remote_path(
            f"source {remote_cadence_cshrc}; cd {remote_ref.remote_project_dir}; "
            f"ocean -nograph -restore {remote_run_dir / 'metrics' / 'metric_probe.ocn'}"
        )
    )
    ocean_result = runner.run(ocean_command)
    if ocean_result.return_code != 0:
        return _write_remote_failure(context, "ocean command failed")

    runner.download_tree(remote_run_dir / "metrics", context.metrics_dir)
    result = _write_remote_success_manifests(context)
    runner.upload(context.run_dir / "result_manifest.json", remote_run_dir / "result_manifest.json")
    runner.upload(
        context.metrics_dir / "metric_result_manifest.json",
        remote_run_dir / "metrics" / "metric_result_manifest.json",
    )
    return result
```

Implement `_write_remote_failure()` and `_write_remote_success_manifests()` by reusing the manifest schema shape from `spectre_ocean.py`. Keep the backend label `remote_spectre_ocean` so acceptance reports can distinguish local and remote real runs.

- [x] **Step 4: Run remote adapter and existing adapter tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_real_result_record.py tests/test_metric_results.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
rtk git add src/hermes_workflow/execution_adapters/remote_spectre_ocean.py tests/test_remote_spectre_ocean.py
rtk git commit -m "feat: add remote spectre ocean adapter"
```

## Task 8: Remote OpenBox Real Flow

**Files:**
- Create: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `src/hermes_workflow/product_cli.py`
- Test: `tests/test_remote_optimizer_flow.py`
- Test: `tests/test_product_cli_remote.py`

- [x] **Step 1: Write failing orchestration tests**

Append to `tests/test_remote_optimizer_flow.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from hermes_workflow.remote_optimizer_flow import optimize_remote_project
from hermes_workflow.remote_project import RemoteProjectRef


def test_optimize_remote_project_runs_doctor_prepare_openbox_and_sync(tmp_path: Path, monkeypatch) -> None:
    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    calls: list[str] = []
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.run_remote_doctor",
        lambda *args, **kwargs: SimpleNamespace(status="pass", issues=[]),
    )
    monkeypatch.setattr(
        "hermes_workflow.remote_optimizer_flow.prepare_remote_project_cache",
        lambda *args, **kwargs: SimpleNamespace(status="pass", cache_dir=cache_dir, issues=[]),
    )

    def fake_optimize_project(project_dir: Path, **kwargs):
        calls.append("optimize_project")
        assert project_dir == cache_dir
        assert kwargs["real"] is True
        assert kwargs["execution_agent"] == "direct"
        report_path = cache_dir / "reports" / "optimizer_flow_run_report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status": "pass"}\n', encoding="utf-8")
        return SimpleNamespace(
            status="pass",
            report_path=report_path,
            recommended_run_id="real_001",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr("hermes_workflow.remote_optimizer_flow.optimize_project", fake_optimize_project)

    result = optimize_remote_project(
        ref,
        real=True,
        max_evals=2,
        batch_size=1,
        parallel_jobs=1,
        remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
        cache_root=tmp_path,
        runner=object(),
    )

    assert result.status == "pass"
    assert result.recommended_run_id == "real_001"
    assert calls == ["optimize_project"]
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

Expected: FAIL because `remote_optimizer_flow` is missing.

- [x] **Step 3: Implement remote optimizer flow with service injection**

Create `src/hermes_workflow/remote_optimizer_flow.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hermes_workflow.execution_adapters.remote_spectre_ocean import run_remote_spectre_ocean_adapter
from hermes_workflow.optimizer_flow import OptimizerFlowReport, OptimizerFlowServices, optimize_project
from hermes_workflow.openbox_backend import run_openbox_real_optimization
from hermes_workflow.remote_doctor import run_remote_doctor
from hermes_workflow.remote_prepare import prepare_remote_project_cache
from hermes_workflow.remote_project import RemoteProjectRef
from hermes_workflow.remote_ssh import RemoteSshRunner


def optimize_remote_project(
    ref: RemoteProjectRef,
    *,
    real: bool,
    remote_cadence_cshrc: PurePosixPath,
    max_evals: int,
    batch_size: int | None,
    parallel_jobs: int | None,
    cache_root: Path | None = None,
    runner: Any | None = None,
) -> OptimizerFlowReport:
    if not real:
        raise ValueError("remote optimize requires --real")
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    doctor = run_remote_doctor(
        ref,
        runner=ssh,
        cadence_cshrc=remote_cadence_cshrc,
        cache_root=cache_root,
    )
    if doctor.status != "pass":
        raise ValueError("remote doctor failed: " + "; ".join(doctor.issues))
    prepared = prepare_remote_project_cache(ref, runner=ssh, cache_root=cache_root)
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))

    def remote_openbox(project_dir: Path, **kwargs: object):
        return run_openbox_real_optimization(
            project_dir,
            adapter=lambda local_project, run_id, cadence_cshrc: run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            ),
            **kwargs,
        )

    services = OptimizerFlowServices(run_openbox_real_optimization=remote_openbox)
    return optimize_project(
        prepared.cache_dir,
        real=True,
        dry_orchestration=False,
        max_evals=max_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        cadence_cshrc=Path("remote-cadence-env.csh"),
        execution_agent="direct",
        services=services,
    )
```

After the first test passes, add a sync helper so `reports/`, `ledger/`, `state/`, and `execution_package/` are uploaded back to the remote project after closeout. Add a test asserting the runner receives `upload_tree(cache_dir / "reports", "/remote/project/reports")`.

- [x] **Step 4: Wire product CLI remote real**

Modify `src/hermes_workflow/product_cli.py`:

```python
from hermes_workflow.remote_optimizer_flow import optimize_remote_project
```

Replace the temporary remote `--real` error with:

```python
        if real:
            remote_cshrc = PurePosixPath(str(cadence_cshrc)) if cadence_cshrc is not None else ref.remote_project_dir / "cadence_env.csh"
            report = optimize_remote_project(
                ref,
                real=True,
                remote_cadence_cshrc=remote_cshrc,
                max_evals=max_evals,
                batch_size=batch_size,
                parallel_jobs=parallel_jobs,
            )
            if report.status == "pass":
                typer.echo("remote optimizer flow completed")
                if report.recommended_run_id is not None:
                    typer.echo(f"recommended: {report.recommended_run_id}")
                typer.echo(f"local report: {report.report_path}")
                typer.echo(f"remote report: {ref.remote_project_dir / 'reports' / 'optimizer_decision_report.md'}")
                return
            raise typer.Exit(code=1)
```

- [x] **Step 5: Run remote flow tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py tests/test_optimizer_flow.py tests/test_product_cli.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_optimizer_flow.py src/hermes_workflow/product_cli.py tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py
rtk git commit -m "feat: run remote openbox optimizer flow"
```

## Task 9: Remote Continuation

**Files:**
- Modify: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `src/hermes_workflow/product_cli.py`
- Test: `tests/test_remote_optimizer_flow.py`
- Test: `tests/test_product_cli_remote.py`

- [x] **Step 1: Write failing tests for `--continue`**

Append to `tests/test_product_cli_remote.py`:

```python
def test_ic_opt_remote_continue_routes_additional_evals(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_continue_remote_project(ref, **kwargs):
        calls.append({"ref": ref, **kwargs})
        return SimpleNamespace(
            status="pass",
            report_path=tmp_path / "reports" / "optimizer_flow_run_report.json",
            recommended_run_id="real_141",
            user_decision_required=True,
            issues=[],
        )

    monkeypatch.setattr(product_cli, "continue_remote_project", fake_continue_remote_project)

    result = runner.invoke(
        product_cli.app,
        ["--ssh-profile", "lab", "/remote/project", "--continue", "40"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["kwargs"]["additional_evals"] == 40
    assert "remote continuation completed" in result.output
    assert "recommended: real_141" in result.output
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli_remote.py::test_ic_opt_remote_continue_routes_additional_evals -q
```

Expected: FAIL because `continue_remote_project` is missing.

- [x] **Step 3: Implement remote continuation**

Add to `src/hermes_workflow/remote_optimizer_flow.py`:

```python
def continue_remote_project(
    ref: RemoteProjectRef,
    *,
    additional_evals: int,
    remote_cadence_cshrc: PurePosixPath,
    batch_size: int | None,
    parallel_jobs: int | None,
    cache_root: Path | None = None,
    runner: Any | None = None,
) -> OptimizerFlowReport:
    if additional_evals < 1:
        raise ValueError("additional_evals must be >= 1")
    ssh = runner or RemoteSshRunner(ref.ssh_profile)
    prepared = prepare_remote_project_cache(ref, runner=ssh, cache_root=cache_root)
    if prepared.status != "pass":
        raise ValueError("remote prepare failed: " + "; ".join(prepared.issues))
    _sync_remote_history_to_cache(ref, prepared.cache_dir, ssh)

    def remote_openbox(project_dir: Path, **kwargs: object):
        return run_openbox_real_optimization(
            project_dir,
            max_evals=None,
            additional_evals=additional_evals,
            continue_from_existing=True,
            batch_size=batch_size,
            parallel_jobs=parallel_jobs,
            adapter=lambda local_project, run_id, cadence_cshrc: run_remote_spectre_ocean_adapter(
                local_project,
                run_id=run_id,
                remote_ref=ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
            ),
        )

    services = OptimizerFlowServices(run_openbox_real_optimization=remote_openbox)
    report = optimize_project(
        prepared.cache_dir,
        real=True,
        dry_orchestration=False,
        max_evals=additional_evals,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
        cadence_cshrc=Path("remote-cadence-env.csh"),
        execution_agent="direct",
        services=services,
    )
    _sync_cache_reports_to_remote(ref, prepared.cache_dir, ssh)
    return report
```

Implement `_sync_remote_history_to_cache()` to download `ledger/`, `state/`, `reports/`, and `execution_package/` if they exist. Continuation must not change resources unless the user passes resource overrides.

- [x] **Step 4: Wire product CLI remote continuation**

Modify `src/hermes_workflow/product_cli.py` to call `continue_remote_project()` when `ssh_profile is not None and continue_evals is not None`.

- [x] **Step 5: Run targeted continuation tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py tests/test_openbox_backend.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
rtk git add src/hermes_workflow/remote_optimizer_flow.py src/hermes_workflow/product_cli.py tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py
rtk git commit -m "feat: support remote optimizer continuation"
```

## Task 10: Documentation, Skill, And Real Acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/USER_GUIDE_CN.md` if present in this repo; otherwise update the release package after backport.
- Modify: `skills/ic-opt/SKILL.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Add evidence doc after real run: `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md`

- [x] **Step 1: Add user-facing remote SSH docs**

Add a short section:

```markdown
## Remote SSH Mode

Use this when your Cadence/Spectre/OCEAN environment is on a Linux EDA server,
but you want to run `ic-opt`, OpenBox, and report viewing from your own
workstation.

First configure passwordless SSH yourself:

```bash
ssh lab true
```

Then run:

```bash
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --doctor
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --real
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --continue 40
```

The project path is the Linux server path. Reports are written on the server
under `PROJECT/reports/` and mirrored locally under `~/.ic-opt/remote_runs/`.
```

- [x] **Step 2: Update agent skill**

Modify `skills/ic-opt/SKILL.md` so agents map:

```text
优化远程服务器 lab 上 /home/user/spectre_opt_prj/Mixer_opt
```

to:

```bash
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --doctor
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --real
```

The skill must state that the agent should not ask for SSH passwords and should tell the user to verify `ssh PROFILE true` if doctor reports SSH failure.

- [x] **Step 3: Run full local regression**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_ssh.py tests/test_remote_project.py tests/test_remote_doctor.py tests/test_remote_prepare.py tests/test_remote_spectre_ocean.py tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py tests/test_product_cli.py tests/test_optimizer_flow.py tests/test_openbox_backend.py -q
rtk proxy ./.venv/bin/python -m ruff check src tests
rtk proxy ./.venv/bin/python tools/check_development_cadence.py
rtk git diff --check
```

Expected: all commands pass.

- [x] **Step 4: Run real remote doctor acceptance**

Use a user-provided SSH profile and remote project. Do not invent a remote project path.

Run:

```bash
rtk proxy ./.venv/bin/ic-opt --ssh-profile PROFILE /remote/project --doctor
```

Expected:

```text
remote doctor completed
remote report: /remote/project/reports/ic_opt_doctor_report.json
local report: ...
```

Record the actual profile/project/report paths in `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md`, redacting private PDK/license paths.

- [x] **Step 5: Run smallest meaningful remote real acceptance**

Only after doctor passes, run a small but real optimization:

```bash
rtk proxy ./.venv/bin/ic-opt --ssh-profile PROFILE /remote/project --real --max-evals 10 --batch-size 2 --parallel-jobs 2
```

Expected:

- Remote Spectre/OCEAN launches happen on Linux through SSH.
- Local OpenBox/controller state updates.
- Remote project contains `reports/optimizer_decision_report.md`.
- Local cache mirror contains the same report.
- No remote Python product package is required.

If no feasible candidate appears in 10 points, that is acceptable for the smoke. The acceptance criterion is correct remote execution and artifact sync, not optimizer quality.

- [x] **Step 6: Run remote continuation acceptance**

After the real smoke:

```bash
rtk proxy ./.venv/bin/ic-opt --ssh-profile PROFILE /remote/project --continue 4 --batch-size 2
```

Expected:

- Cumulative evaluations increase by 4.
- Resource settings are inherited unless explicitly overridden.
- Remote and local reports refresh.

- [x] **Step 7: Commit docs and evidence**

Run:

```bash
rtk git add README.md docs skills/ic-opt/SKILL.md
rtk git commit -m "docs: document remote ssh optimizer mode"
```

## Final Verification Gate

Before claiming C-69 implemented:

```bash
rtk proxy ./.venv/bin/python -m pytest -q
rtk proxy ./.venv/bin/python -m ruff check src tests
rtk proxy ./.venv/bin/python tools/check_development_cadence.py
rtk git diff --check
rtk git status --short
```

Required real evidence:

```text
docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md
```

The evidence must include:

- SSH profile name or redacted alias.
- Remote project path or redacted equivalent.
- `--doctor` report status.
- Real remote Spectre/OCEAN smoke command.
- Remote report paths.
- Local cache report paths.
- Confirmation that remote Python product environment was not required.
- Any failures classified as SSH/environment, real tool, metric, constraint, or optimizer failure.

## Plan Self-Review

Spec coverage:

- SSH/passwordless boundary: Task 1, Task 4, Task 10.
- Remote project source of truth: Task 2, Task 6, Task 8.
- Local OpenBox/controller: Task 8.
- Remote Spectre/OCEAN without remote Python product package: Task 7.
- Remote doctor without Spectre launch: Task 4 and Task 10 Step 4.
- Remote real run: Task 8 and Task 10 Step 5.
- Remote continuation: Task 9 and Task 10 Step 6.
- Report mirror: Task 2, Task 8, Task 10.
- No PSF parsing/OCEAN rewrite/Spectre hardcode: enforced in Task 7 and final acceptance.

Placeholder scan:

- The plan uses concrete file paths, command lines, and task owners, with no placeholder tasks left for the implementer to invent.

Type consistency:

- `RemoteProjectRef`, `RemoteSshRunner`, `run_remote_doctor`, `prepare_remote_project_cache`, `run_remote_spectre_ocean_adapter`, `optimize_remote_project`, and `continue_remote_project` are introduced before later tasks reference them.
