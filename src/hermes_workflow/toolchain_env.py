from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_OPENBOX_EXECUTION_VENV: Path | None = None
DEFAULT_CADENCE_CSHRC = Path("~/.ic-opt/cadence_env.csh")


@dataclass(frozen=True)
class PythonProbeResult:
    return_code: int
    stdout: str
    stderr: str


ProbeRunner = Callable[[Path, str, int], PythonProbeResult]


IMPORT_PROBE = """
import json
import sys

import openbox
import hermes_workflow.openbox_backend as openbox_backend

print(json.dumps({
    "python_executable": sys.executable,
    "openbox_module": getattr(openbox, "__file__", None),
    "hermes_openbox_backend_module": getattr(openbox_backend, "__file__", None),
}))
"""


def check_toolchain_environment(
    *,
    openbox_venv: Path | None = DEFAULT_OPENBOX_EXECUTION_VENV,
    cadence_cshrc: Path = DEFAULT_CADENCE_CSHRC,
    report_path: Path | None = None,
    probe_runner: ProbeRunner | None = None,
    timeout_s: int = 30,
) -> dict:
    openbox_venv = resolve_openbox_execution_venv(openbox_venv)
    cadence_cshrc = Path(cadence_cshrc).expanduser()
    python_path = openbox_venv / "bin" / "python"
    hermes_script = openbox_venv / "bin" / "hermes-workflow"
    checks: list[dict] = []
    issues: list[str] = []

    _add_path_check(
        checks,
        issues,
        name="openbox_venv_exists",
        path=openbox_venv,
        expected="directory",
        ok=openbox_venv.is_dir(),
    )
    _add_path_check(
        checks,
        issues,
        name="openbox_python_exists",
        path=python_path,
        expected="file",
        ok=python_path.is_file(),
    )
    _add_path_check(
        checks,
        issues,
        name="hermes_workflow_script_exists",
        path=hermes_script,
        expected="file",
        ok=hermes_script.is_file(),
    )
    _add_path_check(
        checks,
        issues,
        name="cadence_cshrc_exists",
        path=cadence_cshrc,
        expected="file",
        ok=cadence_cshrc.is_file(),
    )

    if python_path.is_file():
        probe = (probe_runner or _run_python_probe)(python_path, IMPORT_PROBE, timeout_s)
        _add_import_probe_check(checks, issues, probe)
    else:
        checks.append(
            {
                "name": "openbox_and_hermes_import",
                "status": "fail",
                "details": {"reason": "python executable is missing"},
            }
        )
        issues.append("OpenBox/Hermes import probe skipped because Python is missing")

    status = "pass" if not issues else "fail"
    report = {
        "schema_version": "1.0",
        "status": status,
        "openbox_venv": str(openbox_venv),
        "openbox_python": str(python_path),
        "hermes_workflow_script": str(hermes_script),
        "cadence_cshrc": str(cadence_cshrc),
        "checks": checks,
        "issues": issues,
    }
    if report_path is not None:
        report_path = Path(report_path).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def resolve_openbox_execution_venv(openbox_venv: Path | None) -> Path:
    """Resolve an explicit venv or the environment running Hermes itself."""
    if openbox_venv is None:
        return Path(sys.prefix)
    return Path(openbox_venv).expanduser()


def _add_path_check(
    checks: list[dict],
    issues: list[str],
    *,
    name: str,
    path: Path,
    expected: str,
    ok: bool,
) -> None:
    status = "pass" if ok else "fail"
    checks.append(
        {
            "name": name,
            "status": status,
            "details": {
                "path": str(path),
                "expected": expected,
            },
        }
    )
    if not ok:
        issues.append(f"{name} missing: {path}")


def _add_import_probe_check(
    checks: list[dict],
    issues: list[str],
    probe: PythonProbeResult,
) -> None:
    details: dict = {
        "return_code": probe.return_code,
        "stdout": _truncate(probe.stdout),
        "stderr": _truncate(probe.stderr),
    }
    if probe.return_code == 0:
        try:
            details["imports"] = json.loads(probe.stdout)
        except json.JSONDecodeError:
            checks.append(
                {
                    "name": "openbox_and_hermes_import",
                    "status": "fail",
                    "details": details,
                }
            )
            issues.append("OpenBox/Hermes import probe returned invalid JSON")
            return
        checks.append(
            {
                "name": "openbox_and_hermes_import",
                "status": "pass",
                "details": details,
            }
        )
        return

    checks.append(
        {
            "name": "openbox_and_hermes_import",
            "status": "fail",
            "details": details,
        }
    )
    issues.append("OpenBox/Hermes import probe failed")


def _run_python_probe(python_path: Path, script: str, timeout_s: int) -> PythonProbeResult:
    try:
        completed = subprocess.run(
            [str(python_path), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return PythonProbeResult(
            return_code=124,
            stdout=exc.stdout or "",
            stderr=f"probe timed out after {timeout_s}s",
        )
    except OSError as exc:
        return PythonProbeResult(
            return_code=127,
            stdout="",
            stderr=str(exc),
        )
    return PythonProbeResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _truncate(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"
