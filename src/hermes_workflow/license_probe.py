"""License environment probe for Spectre/OCEAN workflows.

This module provides visibility into the Cadence/Spectre license environment
before real simulation jobs start.  It is **not** a license reservation or
guarantee — it only checks that the expected tools and license servers are
reachable from the configured Cadence environment.

The probe runs once during the doctor/preflight gate, not per-child
simulation.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal


LICENSE_PROBE_REPORT_NAME = "reports/license_probe_report.json"

# Accept both "Total of N" and "Total N" variants with flexible spacing.
# Real lmstat output examples:
#   Users of Spectre_X:  (Total of 10 licenses issued;  Total of 3 licenses in use)
#   Users of e_nexus_datadisplay_nexus: (Total 999 licenses issued; 0 licenses in use)
_LMSTAT_USERS_RE = re.compile(
    r"^Users of\s+(\S+):\s+\(Total\s+(?:of\s+)?(\d+)\s+licenses?\s+issued;\s*"
    r"(?:Total\s+(?:of\s+))?(\d+)\s+licenses?\s+in use\)"
)


@dataclass(frozen=True)
class LicenseFeature:
    name: str
    total_issued: int
    total_in_use: int


@dataclass(frozen=True)
class LicenseProbeReport:
    status: Literal["pass", "fail", "skipped"]
    execution_mode: Literal["local", "remote"]
    require_license_check: bool
    spectre_path: str | None = None
    spectre_version: str | None = None
    lmstat_available: bool = False
    license_features: list[LicenseFeature] = field(default_factory=list)
    raw_license_lines: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    spectre_version_rc: int | None = None
    lmstat_rc: int | None = None
    raw_stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def parse_lmstat_output(text: str) -> list[LicenseFeature]:
    """Parse ``lmstat -a`` output for ``Users of ...`` lines.

    Each matching line produces a :class:`LicenseFeature` with the feature
    name, total issued count, and total in-use count.  Non-matching lines
    are silently skipped.

    Supports both ``Total of N`` and ``Total N`` variants, and any feature
    name (not limited to Spectre_*).
    """
    features: list[LicenseFeature] = []
    for line in text.splitlines():
        m = _LMSTAT_USERS_RE.match(line.strip())
        if m:
            features.append(
                LicenseFeature(
                    name=m.group(1),
                    total_issued=int(m.group(2)),
                    total_in_use=int(m.group(3)),
                )
            )
    return features


def _parse_spectre_version_output(text: str) -> str | None:
    """Extract the first non-empty line from ``spectre -V`` output."""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _build_csh_license_probe_script(cadence_cshrc: str) -> str:
    """Build a csh-compatible license probe script.

    The script is designed to run inside ``csh -fc "<script>"`` and must
    **not** use any Bash-only syntax such as ``$()`` or ``2>&1 |``.

    Uses csh-native constructs:
    - Backtick command substitution `` `which spectre` ``
    - ``if (...) then / else / endif`` for conditionals (requires newlines)
    - ``echo $status`` for return codes
    - ``|&`` for piping both stdout and stderr (csh pipe-both)
    - Glob pattern ``=~ /*`` to distinguish real paths from tcsh error messages

    Does **not** write cshrc content to any output; only sources it.
    """
    # NOTE: csh if/then/else/endif REQUIRES newlines — semicolons do NOT
    # work as statement separators for these control-flow keywords.
    # Also: tcsh `which spectre` writes "spectre: Command not found." to
    # stdout (not stderr) when spectre is absent, so we check with a glob
    # pattern (~= /*) rather than testing for empty string.
    return (
        f"source {cadence_cshrc}\n"
        "set sp=`which spectre`\n"
        'if ("$sp" =~ /*) then\n'
        "echo SPECTRE_PATH=$sp\n"
        "else\n"
        "echo SPECTRE_PATH=NOTFOUND\n"
        "endif\n"
        "spectre -V |& head -1\n"
        "echo SPECTRE_VERSION_RC=$status\n"
        "echo LMSTAT_BEGIN\n"
        "lmstat -a |& head -200\n"
        "echo LMSTAT_RC=$status\n"
        "echo LMSTAT_END"
    )


def run_local_license_probe(
    cadence_cshrc: Path,
    *,
    timeout_s: int = 30,
) -> LicenseProbeReport:
    """Run license probe locally by sourcing the Cadence cshrc.

    Uses ``csh -fc "source <cshrc>; ..."`` to ensure the probe runs in
    the same environment as real Spectre jobs.

    Does **not** store cshrc content in the report.
    """
    if not cadence_cshrc.is_file():
        return LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            issues=[f"cadence cshrc does not exist: {cadence_cshrc}"],
        )

    cshrc_quoted = shlex.quote(str(cadence_cshrc))
    probe_script = _build_csh_license_probe_script(cshrc_quoted)
    try:
        result = subprocess.run(
            ["csh", "-fc", probe_script],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            issues=["csh is not available on this system"],
        )
    except subprocess.TimeoutExpired:
        return LicenseProbeReport(
            status="fail",
            execution_mode="local",
            require_license_check=True,
            issues=[f"license probe timed out after {timeout_s}s"],
        )

    return _parse_probe_output(
        result.stdout,
        result.stderr,
        result.returncode,
        execution_mode="local",
    )


def run_remote_license_probe(
    runner: Any,
    cadence_cshrc: PurePosixPath,
    *,
    timeout_s: int = 30,
) -> LicenseProbeReport:
    """Run license probe on a remote host via SSH.

    Uses the same ``csh -fc "source <cshrc>; ..."`` pattern as the remote
    Spectre/OCEAN adapter, ensuring the probe environment matches real
    execution.

    Does **not** store the cshrc path or SSH command details in the report.
    """
    from hermes_workflow.remote_ssh import quote_remote_path

    cshrc_quoted = quote_remote_path(cadence_cshrc)
    probe_body = _build_csh_license_probe_script(cshrc_quoted)
    command = "csh -fc " + quote_remote_path(probe_body)

    try:
        remote_result = runner.run(command, timeout_s=timeout_s)
    except Exception as exc:
        return LicenseProbeReport(
            status="fail",
            execution_mode="remote",
            require_license_check=True,
            issues=[f"remote license probe command failed: {exc}"],
        )

    return _parse_probe_output(
        remote_result.stdout,
        remote_result.stderr,
        remote_result.return_code,
        execution_mode="remote",
    )


def _parse_probe_output(
    stdout: str,
    stderr: str,
    return_code: int,
    *,
    execution_mode: Literal["local", "remote"],
) -> LicenseProbeReport:
    """Parse the structured output from a local or remote license probe."""
    spectre_path: str | None = None
    spectre_version: str | None = None
    spectre_version_rc: int | None = None
    lmstat_rc: int | None = None
    raw_license_lines: list[str] = []
    issues: list[str] = []
    in_lmstat_block = False

    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("SPECTRE_PATH="):
            path = stripped.split("=", 1)[1]
            if path != "NOTFOUND":
                spectre_path = path
        elif stripped.startswith("SPECTRE_VERSION_RC="):
            rc_str = stripped.split("=", 1)[1]
            try:
                spectre_version_rc = int(rc_str)
            except ValueError:
                pass
        elif stripped == "LMSTAT_BEGIN":
            in_lmstat_block = True
        elif stripped == "LMSTAT_END":
            in_lmstat_block = False
        elif stripped.startswith("LMSTAT_RC="):
            rc_str = stripped.split("=", 1)[1]
            try:
                lmstat_rc = int(rc_str)
            except ValueError:
                pass
        elif not spectre_version and not stripped.startswith("SPECTRE_") and stripped:
            # First non-SPECTRE_PATH/non-marker line is the version
            spectre_version = stripped
        elif in_lmstat_block and "Users of" in stripped:
            raw_license_lines.append(stripped)

    license_features = parse_lmstat_output("\n".join(raw_license_lines))
    lmstat_available = bool(raw_license_lines) or "lmstat" in stdout.lower()

    # Sanitized stderr: preserve diagnostic clues but redact cshrc content
    sanitized_stderr = _sanitize_stderr(stderr)

    if spectre_path is None:
        # Check if stderr indicates a csh syntax error rather than spectre absence
        if "Illegal variable name" in stderr:
            issues.append(
                "csh syntax error in license probe; "
                f"stderr: {sanitized_stderr}"
            )
        elif "Missing }" in stderr:
            issues.append(
                "csh syntax error in license probe; "
                f"stderr: {sanitized_stderr}"
            )
        else:
            issues.append("spectre not found in PATH after sourcing cadence cshrc")

    # If spectre -V returned non-zero, that's a failure condition
    if spectre_path and spectre_version_rc is not None and spectre_version_rc != 0:
        issues.append(
            f"spectre -V returned non-zero exit code ({spectre_version_rc})"
        )

    # lmstat failure when require_license_check is true
    if lmstat_rc is not None and lmstat_rc != 0 and lmstat_available is False:
        issues.append(
            f"lmstat -a failed with exit code {lmstat_rc}"
        )

    report = LicenseProbeReport(
        status="fail" if issues else "pass",
        execution_mode=execution_mode,
        require_license_check=True,
        spectre_path=spectre_path,
        spectre_version=spectre_version,
        lmstat_available=lmstat_available,
        license_features=license_features,
        raw_license_lines=raw_license_lines,
        issues=issues,
        spectre_version_rc=spectre_version_rc,
        lmstat_rc=lmstat_rc,
        raw_stderr=sanitized_stderr,
    )
    return report


def _sanitize_stderr(stderr: str) -> str:
    """Sanitize stderr for inclusion in the report.

    Preserves diagnostic clues (like 'Illegal variable name') but strips
    any lines that might contain cshrc content (setenv, set, source lines
    with paths).
    """
    if not stderr:
        return ""
    safe_lines: list[str] = []
    for line in stderr.splitlines():
        stripped = line.strip()
        # Skip lines that look like cshrc content leaking through
        if stripped.startswith("setenv ") or stripped.startswith("set "):
            continue
        if stripped.startswith("source ") and "/" in stripped:
            continue
        safe_lines.append(stripped)
    return "\n".join(safe_lines)


def write_license_probe_report(
    project_dir: Path,
    report: LicenseProbeReport,
) -> Path:
    """Write the license probe report to ``reports/license_probe_report.json``."""
    report_path = project_dir / LICENSE_PROBE_REPORT_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["schema_version"] = "1.0"
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def run_license_probe_skipped(
    *,
    execution_mode: Literal["local", "remote"],
) -> LicenseProbeReport:
    """Return a skipped license probe report.

    Called when ``require_license_check`` is ``False`` — no probe commands
    are executed.
    """
    return LicenseProbeReport(
        status="skipped",
        execution_mode=execution_mode,
        require_license_check=False,
    )
