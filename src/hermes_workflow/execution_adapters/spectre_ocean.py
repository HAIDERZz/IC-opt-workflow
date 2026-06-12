from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.metric_results import (
    METRIC_BACKEND,
    OCEAN_MODE,
    MetricExtractionRequest,
    PreparedRealRunManifest,
)
from hermes_workflow.package import sha256_file
from hermes_workflow.validate import assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
RESULT_SELECTOR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
METRIC_REQUEST_NAME = "metric_extraction_request.json"
REAL_RUN_MANIFEST_NAME = "real_run_manifest.json"
SPECTRE_ENGINE = "spectre_x"
SPECTRE_OUTPUT_FORMAT = "psfxl"
SPECTRE_NETLIST_DIR_NAME = "netlist"
SPECTRE_INPUT_NAME = "input.scs"
PSF_DIR_NAME = "psf"
METRICS_DIR_NAME = "metrics"
OCEAN_SCRIPT_NAME = "metric_probe.ocn"
OCEAN_LOG_NAME = "ocean.log"
SPECTRE_STDOUT_NAME = "spectre.stdout"
SPECTRE_STDERR_NAME = "spectre.stderr"
RESULT_MANIFEST_NAME = "result_manifest.json"
OCEAN_STDOUT_NAME = "ocean.stdout"
OCEAN_STDERR_NAME = "ocean.stderr"
OCEAN_SCALARS_NAME = "ocean_scalars.tsv"
METRIC_RESULT_MANIFEST_NAME = "metric_result_manifest.json"
OCEAN_MAX_ATTEMPTS = 3

ModelT = TypeVar("ModelT", bound=BaseModel)


class AdapterPreconditionError(RuntimeError):
    """Raised when a real-run package is not safe to execute."""


@dataclass(frozen=True)
class SpectreOceanContext:
    project_dir: Path
    run_id: str
    run_relative: str
    run_dir: Path
    input_scs: Path
    psf_dir: Path
    metrics_dir: Path
    real_run_manifest_path: Path
    metric_request_path: Path
    prepared: PreparedRealRunManifest
    request: MetricExtractionRequest
    testbench_id: str | None = None
    corner_id: str | None = None


@dataclass(frozen=True)
class OceanScalarRow:
    metric: str
    value: float | None
    value_text: str | None
    unit: str
    status: str
    expression_sha256: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    return_code: int
    started_at_utc: str
    completed_at_utc: str


@dataclass(frozen=True)
class AdapterRunResult:
    status: str
    run_id: str
    result_manifest_path: Path
    metric_result_manifest_path: Path | None
    issues: list[str]


@dataclass(frozen=True)
class MetricManifestWriteResult:
    path: Path
    status: str
    issues: list[str]


class CommandRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        ...


class SubprocessCommandRunner:
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        started = _utc_now()
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w",
            encoding="utf-8",
        ) as stderr:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_s,
                check=False,
            )
        return CommandResult(
            return_code=completed.returncode,
            started_at_utc=started,
            completed_at_utc=_utc_now(),
        )


def run_spectre_ocean_adapter(
    project_dir: Path,
    *,
    run_id: str | None = None,
    testbench_id: str | None = None,
    corner_id: str | None = None,
    runner: CommandRunner | None = None,
    allow_overwrite: bool = False,
) -> AdapterRunResult:
    context = load_adapter_context(
        project_dir,
        run_id=run_id,
        testbench_id=testbench_id,
        corner_id=corner_id,
    )
    _reject_symlinks(context.project_dir, context.metrics_dir, "metrics directory")
    _reject_symlinks(context.project_dir, context.psf_dir, "psf directory")
    context.metrics_dir.mkdir(parents=True, exist_ok=True)
    context.psf_dir.mkdir(parents=True, exist_ok=True)
    _reject_output_file_symlinks(context)
    _assert_overwrite_policy(context, allow_overwrite=allow_overwrite)
    runner = runner or SubprocessCommandRunner()

    script_path = _project_relative_path(
        context.project_dir,
        context.request.ocean.script_file,
    )
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    spectre_result = runner.run(
        _spectre_argv(context),
        cwd=context.input_scs.parent,
        stdout_path=context.run_dir / SPECTRE_STDOUT_NAME,
        stderr_path=context.run_dir / SPECTRE_STDERR_NAME,
        timeout_s=int(context.request.spectre.get("timeout_s", 3600)),
    )
    if spectre_result.return_code != 0:
        result_manifest_path = _write_result_manifest(
            context,
            status="failed",
            started_at_utc=spectre_result.started_at_utc,
            completed_at_utc=spectre_result.completed_at_utc,
            include_metric_manifest=False,
            notes="spectre command failed",
        )
        return AdapterRunResult(
            status="failed",
            run_id=context.run_id,
            result_manifest_path=result_manifest_path,
            metric_result_manifest_path=None,
            issues=["spectre command failed"],
        )

    ocean_results = _run_ocean_with_retries(context, runner)
    ocean_result = ocean_results[-1]
    metric_result = _write_metric_result_manifest(
        context,
        ocean_return_code=ocean_result.return_code,
        ocean_return_codes=[result.return_code for result in ocean_results],
    )
    result_manifest_path = _write_result_manifest(
        context,
        status="succeeded",
        started_at_utc=spectre_result.started_at_utc,
        completed_at_utc=ocean_result.completed_at_utc,
        include_metric_manifest=True,
        notes="spectre command completed",
    )
    status = "succeeded" if metric_result.status == "succeeded" else "failed"
    return AdapterRunResult(
        status=status,
        run_id=context.run_id,
        result_manifest_path=result_manifest_path,
        metric_result_manifest_path=metric_result.path,
        issues=metric_result.issues,
    )


def _run_ocean_with_retries(
    context: SpectreOceanContext,
    runner: CommandRunner,
) -> list[CommandResult]:
    results: list[CommandResult] = []
    for _attempt in range(OCEAN_MAX_ATTEMPTS):
        result = runner.run(
            _ocean_argv(context),
            cwd=context.project_dir,
            stdout_path=context.metrics_dir / OCEAN_STDOUT_NAME,
            stderr_path=context.metrics_dir / OCEAN_STDERR_NAME,
            timeout_s=int(context.request.spectre.get("timeout_s", 3600)),
        )
        results.append(result)
        if result.return_code == 0:
            break
    return results


def load_adapter_context(
    project_dir: Path,
    *,
    run_id: str | None = None,
    testbench_id: str | None = None,
    corner_id: str | None = None,
) -> SpectreOceanContext:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    selected_testbench_id = _validate_testbench_id(testbench_id)
    selected_corner_id = _validate_corner_id(corner_id)
    try:
        bundle = assert_valid_project(project_dir)
    except ValueError as exc:
        raise AdapterPreconditionError("project contract validation failed") from exc

    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    if selected_testbench_id is not None:
        run_relative = f"{run_relative}/testbenches/{selected_testbench_id}"
    if selected_corner_id is not None:
        run_relative = f"{run_relative}/corners/{selected_corner_id}"
    run_dir = _safe_project_path(project_dir, run_relative, "run directory")
    _reject_symlinks(project_dir, run_dir, "run directory")
    if not run_dir.is_dir():
        raise AdapterPreconditionError("run directory is missing")

    prepared_path = run_dir / REAL_RUN_MANIFEST_NAME
    request_path = run_dir / METRIC_REQUEST_NAME
    _reject_symlinks(project_dir, prepared_path, "real run manifest")
    _reject_symlinks(project_dir, request_path, "metric extraction request")
    prepared = _load_model(
        prepared_path,
        PreparedRealRunManifest,
        "real run manifest",
    )
    request = _load_model(
        request_path,
        MetricExtractionRequest,
        "metric extraction request",
    )

    _validate_ids_and_modes(selected_run_id, prepared, request)

    expected_input = f"{run_relative}/{SPECTRE_NETLIST_DIR_NAME}/{SPECTRE_INPUT_NAME}"
    expected_psf = f"{run_relative}/{PSF_DIR_NAME}"
    expected_metrics = f"{run_relative}/{METRICS_DIR_NAME}"
    expected_ocean_script = f"{expected_metrics}/{OCEAN_SCRIPT_NAME}"
    expected_ocean_log = f"{expected_metrics}/{OCEAN_LOG_NAME}"
    expected_ocean_scalars = f"{expected_metrics}/{OCEAN_SCALARS_NAME}"
    expected_metric_request = f"{run_relative}/{METRIC_REQUEST_NAME}"

    prepared_metric_request = _exact_project_path(
        project_dir,
        prepared.metric_extraction_request,
        "metric_extraction_request",
        expected_metric_request,
    )
    if prepared_metric_request != request_path:
        raise AdapterPreconditionError("metric request path mismatch")
    if prepared.metric_extraction_request_sha256 != sha256_file(request_path):
        raise AdapterPreconditionError("metric request file hash mismatch")
    _validate_spectre_request(request.spectre)
    _validate_spectre_settings_match(prepared, request)

    input_scs = _exact_project_path(
        project_dir,
        request.prepared_input_scs,
        "prepared_input_scs",
        expected_input,
    )
    prepared_input_scs = _exact_project_path(
        project_dir,
        prepared.rendered_input_scs,
        "rendered_input_scs",
        expected_input,
    )
    psf_dir = _exact_project_path(
        project_dir,
        request.expected_psf_dir,
        "expected_psf_dir",
        expected_psf,
    )
    metrics_dir = _exact_project_path(
        project_dir,
        expected_metrics,
        "metrics directory",
        expected_metrics,
    )
    _exact_project_path(
        project_dir,
        request.ocean.script_file,
        "ocean script_file",
        expected_ocean_script,
    )
    _exact_project_path(
        project_dir,
        request.ocean.log_file,
        "ocean log_file",
        expected_ocean_log,
    )
    _exact_project_path(
        project_dir,
        request.ocean.scalar_output_file,
        "ocean scalar_output_file",
        expected_ocean_scalars,
    )

    if input_scs != prepared_input_scs:
        raise AdapterPreconditionError("prepared input path mismatch")
    if request.prepared_input_scs != prepared.rendered_input_scs:
        raise AdapterPreconditionError("prepared input path mismatch")
    if request.prepared_input_sha256 != prepared.rendered_input_sha256:
        raise AdapterPreconditionError("prepared input hash mismatch")
    _reject_symlinks(project_dir, input_scs, "prepared_input_scs")
    _reject_symlinks(project_dir, input_scs.parent, "spectre netlist directory")
    if not input_scs.exists():
        raise AdapterPreconditionError("prepared input_scs is missing")
    current_input_sha256 = sha256_file(input_scs)
    if current_input_sha256 != request.prepared_input_sha256:
        raise AdapterPreconditionError("prepared input_scs hash mismatch")
    if current_input_sha256 != prepared.rendered_input_sha256:
        raise AdapterPreconditionError("prepared input_scs hash mismatch")

    for metric in request.metrics:
        if expression_sha256(metric.expression) != metric.expression_sha256:
            raise AdapterPreconditionError(
                f"metric {metric.name} expression hash mismatch"
            )
        if metric.expected_value_type != "real_scalar":
            raise AdapterPreconditionError(
                f"metric {metric.name} expected_value_type is unsupported"
            )
        if metric.nil_policy != "fail":
            raise AdapterPreconditionError(
                f"metric {metric.name} nil_policy is unsupported"
            )
        if metric.non_finite_policy != "fail":
            raise AdapterPreconditionError(
                f"metric {metric.name} non_finite_policy is unsupported"
            )

    return SpectreOceanContext(
        project_dir=bundle.project_dir,
        run_id=selected_run_id,
        run_relative=run_relative,
        run_dir=run_dir,
        input_scs=input_scs,
        psf_dir=psf_dir,
        metrics_dir=metrics_dir,
        real_run_manifest_path=prepared_path,
        metric_request_path=request_path,
        prepared=prepared,
        request=request,
        testbench_id=selected_testbench_id,
        corner_id=selected_corner_id,
    )


def render_ocean_replay_script(context: SpectreOceanContext) -> str:
    scalar_path = _posix_path(context.request.ocean.scalar_output_file)
    psf_path = _posix_path(context.request.expected_psf_dir)
    _validate_emitted_field(psf_path, "expected_psf_dir")
    _validate_emitted_field(scalar_path, "ocean scalar_output_file")
    lines = [
        "; Generated by ic-auto-opt-workflow C-7 execution adapter",
        "; Formula text below is copied exactly from metric_extraction_request.json",
        f"openResults({_skill_string(psf_path)})",
        f"out = outfile({_skill_string(scalar_path)})",
        'fprintf(out "metric\\tvalue\\tunit\\tstatus\\texpression_sha256\\tmessage\\n")',
    ]

    for metric in context.request.metrics:
        _validate_emitted_field(metric.name, "metric name")
        _validate_emitted_field(metric.unit, f"metric {metric.name} unit")
        _validate_emitted_field(
            metric.expression_sha256,
            f"metric {metric.name} expression_sha256",
        )
        if metric.result is not None:
            _validate_emitted_field(metric.result, f"metric {metric.name} result")
            _validate_result_selector(metric.result, f"metric {metric.name} result")
            lines.append(f"selectResult('{metric.result})")
        lines.extend(
            [
                f"; metric: {metric.name}",
                f"; expression_sha256: {metric.expression_sha256}",
                f"hermesResult = errset({metric.expression} t)",
                "if(hermesResult then",
                "  hermesValue = car(hermesResult)",
                "  if(numberp(hermesValue) then",
                (
                    '    fprintf(out "%s\\t%.16g\\t%s\\tpass\\t%s\\t\\n" '
                    f"{_skill_string(metric.name)} "
                    "hermesValue "
                    f"{_skill_string(metric.unit)} "
                    f"{_skill_string(metric.expression_sha256)}"
                    ")"
                ),
                "  else",
                (
                    '    fprintf(out "%s\\t\\t%s\\tfail\\t%s\\tnon_scalar\\n" '
                    f"{_skill_string(metric.name)} "
                    f"{_skill_string(metric.unit)} "
                    f"{_skill_string(metric.expression_sha256)}"
                    ")"
                ),
                "  )",
                "else",
                (
                    '  fprintf(out "%s\\t\\t%s\\tfail\\t%s\\texpression_error\\n" '
                    f"{_skill_string(metric.name)} "
                    f"{_skill_string(metric.unit)} "
                    f"{_skill_string(metric.expression_sha256)}"
                    ")"
                ),
                ")",
            ]
        )

    lines.extend(["close(out)", "exit()"])
    return "\n".join(lines) + "\n"


def parse_ocean_scalars(path: Path) -> dict[str, OceanScalarRow]:
    if not path.exists():
        raise AdapterPreconditionError("ocean scalar output is missing")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected_header = [
            "metric",
            "value",
            "unit",
            "status",
            "expression_sha256",
            "message",
        ]
        if reader.fieldnames != expected_header:
            raise AdapterPreconditionError("ocean scalar output header is invalid")

        rows: dict[str, OceanScalarRow] = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise AdapterPreconditionError("ocean scalar output row is malformed")

            metric = row["metric"]
            if not metric:
                raise AdapterPreconditionError("ocean scalar metric is required")
            if metric in rows:
                raise AdapterPreconditionError(f"duplicate scalar metric: {metric}")

            unit = row["unit"]
            if not unit:
                raise AdapterPreconditionError(f"metric {metric} unit is required")
            expression_hash = row["expression_sha256"]
            if not expression_hash:
                raise AdapterPreconditionError(
                    f"metric {metric} expression_sha256 is required"
                )
            status = row["status"]
            if status not in {"pass", "fail"}:
                raise AdapterPreconditionError(
                    f"metric {metric} status is invalid: {status}"
                )

            value_text = row["value"]
            value = None
            if status == "pass":
                if not value_text:
                    raise AdapterPreconditionError(
                        f"metric {metric} value is required for pass"
                    )
                try:
                    value = float(value_text)
                except ValueError as exc:
                    raise AdapterPreconditionError(
                        f"metric {metric} value is not numeric"
                    ) from exc
                if not math.isfinite(value):
                    raise AdapterPreconditionError(f"metric {metric} value is not finite")
            elif value_text:
                raise AdapterPreconditionError(
                    f"metric {metric} fail value must be empty"
                )

            rows[metric] = OceanScalarRow(
                metric=metric,
                value=value,
                value_text=value_text if value_text else None,
                unit=unit,
                status=status,
                expression_sha256=expression_hash,
                message=row["message"],
            )

    return rows


def build_spectre_argv(context: SpectreOceanContext) -> list[str]:
    """Build the canonical spectre command argv.

    The first element is ``"spectre"``; remaining elements are the flags
    read from *context.request.spectre*.  Callers that need a remote shell
    string should ``shlex.quote`` each element and join them.
    """
    preset = str(context.request.spectre["preset"])
    output_format = str(context.request.spectre["output_format"])
    threads_per_run = int(context.request.spectre["threads_per_run"])
    return [
        "spectre",
        "-64",
        context.input_scs.name,
        "+escchars",
        f"+preset={preset}",
        f"+mt={threads_per_run}",
        "+lqtimeout",
        "900",
        "-maxw",
        "5",
        "-maxn",
        "5",
        "-env",
        "ade",
        "+logstatus",
        "-format",
        output_format,
        "-raw",
        f"../{PSF_DIR_NAME}",
        "+log",
        f"../{PSF_DIR_NAME}/spectre.out",
    ]


def build_ocean_argv(context: SpectreOceanContext) -> list[str]:
    """Build the canonical ocean command argv.

    The first element is ``"ocean"``; remaining elements are the flags
    read from *context.request.ocean*.  Callers that need a remote shell
    string should ``shlex.quote`` each element and join them.
    """
    return [
        "ocean",
        "-nograph",
        "-replay",
        context.request.ocean.script_file,
        "-log",
        context.request.ocean.log_file,
    ]


def _spectre_argv(context: SpectreOceanContext) -> list[str]:
    return build_spectre_argv(context)


def _ocean_argv(context: SpectreOceanContext) -> list[str]:
    return build_ocean_argv(context)


def _write_result_manifest(
    context: SpectreOceanContext,
    *,
    status: str,
    started_at_utc: str,
    completed_at_utc: str,
    include_metric_manifest: bool,
    notes: str,
) -> Path:
    spectre_out = f"{context.run_relative}/{PSF_DIR_NAME}/spectre.out"
    spectre_stdout = f"{context.run_relative}/{SPECTRE_STDOUT_NAME}"
    spectre_stderr = f"{context.run_relative}/{SPECTRE_STDERR_NAME}"
    spectre_succeeded = status == "succeeded"
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.prepared.candidate_id,
        "testbench_id": context.testbench_id,
        "corner_id": context.corner_id,
        "status": status,
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "simulator": {
            "engine": SPECTRE_ENGINE,
            "preset": str(context.request.spectre["preset"]),
            "output_format": str(context.request.spectre["output_format"]),
            "threads_per_run": int(context.request.spectre["threads_per_run"]),
            "timeout_s": int(context.request.spectre["timeout_s"]),
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": context.prepared.rendered_input_scs,
        "prepared_input_sha256": context.prepared.rendered_input_sha256,
        "log_file": spectre_out if spectre_succeeded else spectre_stderr,
        "artifact_files": [spectre_stdout, spectre_stderr],
        "result_data": None,
        "metric_result_manifest": None,
        "notes": notes,
    }
    if spectre_succeeded:
        payload["result_data"] = {
            "kind": "spectre_psf",
            "psf_dir": context.request.expected_psf_dir,
            "spectre_out": spectre_out,
        }
    if include_metric_manifest:
        payload["metric_result_manifest"] = (
            f"{context.run_relative}/{METRICS_DIR_NAME}/{METRIC_RESULT_MANIFEST_NAME}"
        )
    artifact_candidates = [*payload["artifact_files"]]
    if spectre_succeeded:
        artifact_candidates.append(spectre_out)
    if include_metric_manifest:
        artifact_candidates.extend(
            [
                f"{context.run_relative}/{METRICS_DIR_NAME}/{OCEAN_SCRIPT_NAME}",
                f"{context.run_relative}/{METRICS_DIR_NAME}/{OCEAN_LOG_NAME}",
                f"{context.run_relative}/{METRICS_DIR_NAME}/{OCEAN_STDOUT_NAME}",
                f"{context.run_relative}/{METRICS_DIR_NAME}/{OCEAN_STDERR_NAME}",
                f"{context.run_relative}/{METRICS_DIR_NAME}/{OCEAN_SCALARS_NAME}",
                str(payload["metric_result_manifest"]),
            ]
        )
    payload["artifact_files"] = _existing_artifact_files(context, artifact_candidates)

    result_path = context.run_dir / RESULT_MANIFEST_NAME
    _write_json(result_path, payload)
    return result_path


def _write_metric_result_manifest(
    context: SpectreOceanContext,
    *,
    ocean_return_code: int,
    ocean_return_codes: Sequence[int] | None = None,
) -> MetricManifestWriteResult:
    scalar_path = _project_relative_path(
        context.project_dir,
        context.request.ocean.scalar_output_file,
    )
    issues: list[str] = []
    try:
        scalar_rows = parse_ocean_scalars(scalar_path)
    except AdapterPreconditionError as exc:
        scalar_rows = {}
        issues.append(str(exc))
    ocean_failed = ocean_return_code != 0
    return_codes = list(ocean_return_codes or [ocean_return_code])
    if ocean_failed:
        issues.append("ocean command failed")

    metrics = []
    for request_metric in context.request.metrics:
        if ocean_failed:
            metrics.append(
                {
                    "name": request_metric.name,
                    "status": "failed",
                    "value": None,
                    "value_text": None,
                    "unit": request_metric.unit,
                    "result": request_metric.result,
                    "expression": request_metric.expression,
                    "expression_sha256": request_metric.expression_sha256,
                    "expression_source": request_metric.expression_source,
                    "issues": ["ocean command failed"],
                }
            )
            continue
        row = scalar_rows.get(request_metric.name)
        if row is None:
            metrics.append(
                {
                    "name": request_metric.name,
                    "status": "failed",
                    "value": None,
                    "value_text": None,
                    "unit": request_metric.unit,
                    "result": request_metric.result,
                    "expression": request_metric.expression,
                    "expression_sha256": request_metric.expression_sha256,
                    "expression_source": request_metric.expression_source,
                    "issues": ["metric missing from ocean scalar output"],
                }
            )
            issues.append(f"metric {request_metric.name} missing from ocean scalar output")
            continue
        metric_issues = []
        if row.unit != request_metric.unit:
            metric_issues.append("unit does not match request")
        if row.expression_sha256 != request_metric.expression_sha256:
            metric_issues.append("expression_sha256 does not match request")
        if row.status != "pass":
            metric_issues.append(row.message or "ocean metric evaluation failed")
        metric_status = "succeeded" if not metric_issues else "failed"
        metrics.append(
            {
                "name": request_metric.name,
                "status": metric_status,
                "value": row.value if metric_status == "succeeded" else None,
                "value_text": (
                    row.value_text if metric_status == "succeeded" else None
                ),
                "unit": request_metric.unit,
                "result": request_metric.result,
                "expression": request_metric.expression,
                "expression_sha256": request_metric.expression_sha256,
                "expression_source": request_metric.expression_source,
                "issues": metric_issues,
            }
        )
        issues.extend(f"metric {request_metric.name} {issue}" for issue in metric_issues)

    extra_metrics = sorted(set(scalar_rows) - {metric.name for metric in context.request.metrics})
    issues.extend(f"unrequested metric in ocean scalar output: {name}" for name in extra_metrics)

    manifest_status = "succeeded" if not issues else "failed"
    script_path = _project_relative_path(
        context.project_dir,
        context.request.ocean.script_file,
    )
    payload = {
        "schema_version": "1.0",
        "run_id": context.run_id,
        "candidate_id": context.request.candidate_id,
        "backend": context.request.backend,
        "status": manifest_status,
        "request_file": f"{context.run_relative}/{METRIC_REQUEST_NAME}",
        "request_sha256": sha256_file(context.metric_request_path),
        "psf_dir": context.request.expected_psf_dir,
        "ocean": {
            "mode": context.request.ocean.mode,
            "return_code": ocean_return_code,
            "attempts": len(return_codes),
            "return_codes": return_codes,
            "script_file": context.request.ocean.script_file,
            "script_sha256": sha256_file(script_path),
            "log_file": context.request.ocean.log_file,
            "scalar_output_file": context.request.ocean.scalar_output_file,
        },
        "metrics": metrics,
        "issues": issues,
    }
    result_path = context.metrics_dir / METRIC_RESULT_MANIFEST_NAME
    _write_json(result_path, payload)
    return MetricManifestWriteResult(
        path=result_path,
        status=manifest_status,
        issues=issues,
    )


def write_spectre_result_manifest(
    context: SpectreOceanContext,
    *,
    status: str,
    started_at_utc: str,
    completed_at_utc: str,
    include_metric_manifest: bool,
    notes: str,
) -> Path:
    """Public wrapper around ``_write_result_manifest``.

    The remote adapter calls this instead of hand-writing the result
    manifest payload, ensuring the schema stays in sync with the local
    adapter.
    """
    return _write_result_manifest(
        context,
        status=status,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        include_metric_manifest=include_metric_manifest,
        notes=notes,
    )


def write_metric_result_manifest(
    context: SpectreOceanContext,
    *,
    ocean_return_code: int,
    ocean_return_codes: Sequence[int] | None = None,
) -> MetricManifestWriteResult:
    """Public wrapper around ``_write_metric_result_manifest``.

    The remote adapter calls this instead of hand-writing the metric
    result manifest payload, ensuring the schema stays in sync with the
    local adapter.
    """
    return _write_metric_result_manifest(
        context,
        ocean_return_code=ocean_return_code,
        ocean_return_codes=ocean_return_codes,
    )


def _assert_overwrite_policy(
    context: SpectreOceanContext,
    *,
    allow_overwrite: bool,
) -> None:
    if allow_overwrite:
        return
    result_manifest = context.run_dir / RESULT_MANIFEST_NAME
    metric_manifest = context.metrics_dir / METRIC_RESULT_MANIFEST_NAME
    if result_manifest.exists() or metric_manifest.exists():
        raise AdapterPreconditionError(
            "result already exists; use allow_overwrite to rerun"
        )


def _reject_output_file_symlinks(context: SpectreOceanContext) -> None:
    for path in _adapter_output_paths(context):
        if path.is_symlink():
            raise AdapterPreconditionError(
                f"output file is a symlink: {_relative_to_project(context, path)}"
            )


def _adapter_output_paths(context: SpectreOceanContext) -> list[Path]:
    return [
        _project_relative_path(context.project_dir, context.request.ocean.script_file),
        context.run_dir / SPECTRE_STDOUT_NAME,
        context.run_dir / SPECTRE_STDERR_NAME,
        context.run_dir / RESULT_MANIFEST_NAME,
        context.psf_dir / "spectre.out",
        context.metrics_dir / OCEAN_STDOUT_NAME,
        context.metrics_dir / OCEAN_STDERR_NAME,
        context.metrics_dir / METRIC_RESULT_MANIFEST_NAME,
        _project_relative_path(context.project_dir, context.request.ocean.log_file),
        _project_relative_path(
            context.project_dir,
            context.request.ocean.scalar_output_file,
        ),
    ]


def _existing_artifact_files(
    context: SpectreOceanContext,
    relative_paths: list[str],
) -> list[str]:
    artifacts = []
    for relative_path in relative_paths:
        path = _project_relative_path(context.project_dir, relative_path)
        if path.exists():
            artifacts.append(relative_path)
    return artifacts


def _relative_to_project(context: SpectreOceanContext, path: Path) -> str:
    return path.relative_to(context.project_dir).as_posix()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_relative_path(project_dir: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    return project_dir / Path(*path.parts)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_ids_and_modes(
    selected_run_id: str,
    prepared: PreparedRealRunManifest,
    request: MetricExtractionRequest,
) -> None:
    if prepared.run_id != selected_run_id:
        raise AdapterPreconditionError("real run manifest run_id mismatch")
    if request.run_id != selected_run_id:
        raise AdapterPreconditionError("metric request run_id mismatch")
    if prepared.status != "prepared":
        raise AdapterPreconditionError("real run package is not prepared")
    if request.backend != METRIC_BACKEND:
        raise AdapterPreconditionError(f"backend is unsupported: {request.backend}")
    if request.ocean.mode != OCEAN_MODE:
        raise AdapterPreconditionError(f"ocean mode is unsupported: {request.ocean.mode}")


def _validate_spectre_request(spectre: dict) -> None:
    engine = spectre.get("engine")
    if engine is None:
        raise AdapterPreconditionError("spectre.engine is required")
    if engine != SPECTRE_ENGINE:
        raise AdapterPreconditionError(f"spectre.engine is unsupported: {engine}")
    preset = spectre.get("preset")
    if not isinstance(preset, str) or not preset:
        raise AdapterPreconditionError("spectre.preset must be a non-empty string")
    output_format = spectre.get("output_format")
    if output_format is None:
        raise AdapterPreconditionError("spectre.output_format is required")
    if output_format != SPECTRE_OUTPUT_FORMAT:
        raise AdapterPreconditionError("output_format must be psfxl")
    threads_per_run = spectre.get("threads_per_run")
    if (
        not isinstance(threads_per_run, int)
        or isinstance(threads_per_run, bool)
        or threads_per_run <= 0
    ):
        raise AdapterPreconditionError(
            "spectre.threads_per_run must be a positive integer"
        )
    parallel_jobs = spectre.get("parallel_jobs")
    if (
        not isinstance(parallel_jobs, int)
        or isinstance(parallel_jobs, bool)
        or parallel_jobs <= 0
    ):
        raise AdapterPreconditionError(
            "spectre.parallel_jobs must be a positive integer"
        )
    timeout_s = spectre.get("timeout_s")
    if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise AdapterPreconditionError("spectre.timeout_s must be a positive integer")


def _validate_spectre_settings_match(
    prepared: PreparedRealRunManifest,
    request: MetricExtractionRequest,
) -> None:
    for key in (
        "engine",
        "preset",
        "output_format",
        "threads_per_run",
        "parallel_jobs",
        "timeout_s",
    ):
        if prepared.spectre.get(key) != request.spectre.get(key):
            raise AdapterPreconditionError(
                f"spectre.{key} does not match prepared manifest"
            )


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise AdapterPreconditionError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _validate_testbench_id(testbench_id: str | None) -> str | None:
    if testbench_id is None:
        return None
    if not RESULT_SELECTOR_RE.match(testbench_id):
        raise AdapterPreconditionError(f"testbench_id is unsafe: {testbench_id}")
    return testbench_id


def _validate_corner_id(corner_id: str | None) -> str | None:
    if corner_id is None:
        return None
    if not RESULT_SELECTOR_RE.match(corner_id):
        raise AdapterPreconditionError(f"corner_id is unsafe: {corner_id}")
    return corner_id


def _load_model(path: Path, model_class: type[ModelT], label: str) -> ModelT:
    if not path.exists():
        raise AdapterPreconditionError(f"{label} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterPreconditionError(f"{label} is invalid: {exc.msg}") from exc
    try:
        return model_class.model_validate(payload)
    except ValidationError as exc:
        raise AdapterPreconditionError(f"{label} is invalid") from exc


def _exact_project_path(
    project_dir: Path,
    relative_path: str,
    label: str,
    expected_relative: str,
) -> Path:
    resolved_path = _safe_project_path(
        project_dir,
        relative_path,
        label,
        required_prefix=str(PurePosixPath(expected_relative).parent),
    )
    if PurePosixPath(relative_path) != PurePosixPath(expected_relative):
        raise AdapterPreconditionError(f"{label} must be {expected_relative}")
    return resolved_path


def _safe_project_path(
    project_dir: Path,
    relative_path: str,
    label: str,
    *,
    required_prefix: str | None = None,
) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise AdapterPreconditionError(f"{label} is unsafe: {relative_path}")
    if required_prefix is not None and not path.is_relative_to(
        PurePosixPath(required_prefix)
    ):
        raise AdapterPreconditionError(f"{label} is unsafe: {relative_path}")
    return project_dir / Path(*path.parts)


def _reject_symlinks(project_dir: Path, path: Path, label: str) -> None:
    try:
        relative_parts = path.relative_to(project_dir).parts
    except ValueError:
        raise AdapterPreconditionError(f"{label} is unsafe: {path}") from None
    current = project_dir
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            if current == path:
                raise AdapterPreconditionError(f"{label} is a symlink")
            raise AdapterPreconditionError(f"{label} has symlink ancestor")


def _skill_string(value: str) -> str:
    _validate_emitted_field(value, "SKILL string")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _posix_path(value: str) -> str:
    return PurePosixPath(value).as_posix()


def _validate_emitted_field(value: str, label: str) -> None:
    for char in value:
        if ord(char) < 32 or ord(char) == 127:
            raise AdapterPreconditionError(f"{label} contains control characters")


def _validate_result_selector(value: str, label: str) -> None:
    if not RESULT_SELECTOR_RE.match(value):
        raise AdapterPreconditionError(f"{label} is not a safe OCEAN result selector")
