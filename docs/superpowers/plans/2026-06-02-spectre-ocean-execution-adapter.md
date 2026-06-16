# Spectre + OCEAN Execution Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the C-7 execution-side adapter that consumes a prepared real-run package, invokes standalone Spectre and batch OCEAN through an injectable runner, and writes C-5/C-6-compatible result artifacts without parsing PSF or rewriting formulas.

**Architecture:** Add an `execution_adapters` package under `hermes_workflow` to make the tool boundary explicit while reusing existing C-5/C-6 Pydantic contract models. The adapter loads and verifies `real_run_manifest.json` and `metric_extraction_request.json`, generates an OCEAN replay script that preserves request formulas exactly, runs commands through an injected `CommandRunner`, parses only OCEAN scalar TSV output, and writes `result_manifest.json` plus `metrics/metric_result_manifest.json`. Unit tests use fake runners and fake artifacts only; real Cadence smoke remains local-only documentation.

**Tech Stack:** Python 3.11+, Pydantic v2 models already in `metric_results.py` and `result_handoff.py`, standard-library `subprocess`, `csv`, `json`, `dataclasses`, pytest, ruff, existing `sha256_file`, `check_real_run`, and `check_metric_results`.

---

## Required Reading

- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`
- `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`
- `docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md`
- `docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md`
- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/metric_requests.py`

## Execution Model

Use Subagent-Driven Development for implementation. Each task should get a fresh worker context containing only:

```text
docs/ROLE_MODEL_AND_TERMINOLOGY.md
docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md
docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md
the current task section
```

Risk-tiered gates:

- Task 1 is high risk because it gates command execution and path writes. Run local tests and code-quality review.
- Task 2 is high risk because it handles formula preservation. Run local tests and code-quality review.
- Task 3 is high risk because it writes result artifacts. Run local tests and code-quality review.
- Task 4 is high risk because it handles failures and overwrite policy. Run local tests and code-quality review.
- Tasks 5-6 are medium/low risk. Run local tests after Task 5, then one final combined review after Task 6.

No task may call real Spectre, real OCEAN, real Virtuoso, SSH, Claude CLI as execution agent, or network access.

## File Map

- Create `src/hermes_workflow/execution_adapters/__init__.py`: package marker and public exports.
- Create `src/hermes_workflow/execution_adapters/spectre_ocean.py`: C-7 adapter library, precondition checks, command runner, OCEAN script generation, scalar TSV parsing, manifest writing.
- Create `tests/test_spectre_ocean_adapter.py`: unit tests with fake runner and fake artifacts.
- Create `tools/run_spectre_ocean_adapter.py`: explicit execution-side tool entry point for local use.
- Modify `README.md`: document C-7 adapter boundary and command.
- Modify `docs/PROJECT_WORKFLOW_OVERVIEW.md`: add C-7 adapter layer.
- Modify `docs/EXECUTION_PROGRESS_2026-05-29.md`: record C-7 plan and implementation status.
- Modify `docs/COMPACT_RESUME_CHECKPOINT.md`: update next action.
- Modify this plan file as tasks are completed.

## Contract Constants

Use the existing constants where available:

```python
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
METRIC_BACKEND = "spectre_ocean_batch"
OCEAN_MODE = "nograph_replay"
```

Use these generated paths for C-7:

```python
SPECTRE_LOG_NAME = "spectre.out"
SPECTRE_STDOUT_NAME = "spectre.stdout"
SPECTRE_STDERR_NAME = "spectre.stderr"
RESULT_MANIFEST_NAME = "result_manifest.json"
METRICS_DIR_NAME = "metrics"
OCEAN_SCRIPT_NAME = "metric_probe.ocn"
OCEAN_LOG_NAME = "ocean.log"
OCEAN_STDOUT_NAME = "ocean.stdout"
OCEAN_STDERR_NAME = "ocean.stderr"
OCEAN_SCALARS_NAME = "ocean_scalars.tsv"
METRIC_RESULT_MANIFEST_NAME = "metric_result_manifest.json"
```

## Task 1: Adapter Context And Preconditions

**Files:**

- Create: `src/hermes_workflow/execution_adapters/__init__.py`
- Create: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Create: `tests/test_spectre_ocean_adapter.py`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Write failing context-loader tests**

Create `tests/test_spectre_ocean_adapter.py` with these imports and helpers:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterPreconditionError,
    load_adapter_context,
)
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.real_run import prepare_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_ready_real_run_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-02T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir
```

Append context success coverage:

```python
def test_load_adapter_context_accepts_prepared_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)

    context = load_adapter_context(project_dir)

    assert context.run_id == "real_001"
    assert context.run_relative == "runs/real/real_001"
    assert context.run_dir == project_dir / "runs" / "real" / "real_001"
    assert context.input_scs == context.run_dir / "input.scs"
    assert context.psf_dir == context.run_dir / "psf"
    assert context.metrics_dir == context.run_dir / "metrics"
    assert context.request.backend == "spectre_ocean_batch"
    assert context.request.spectre["output_format"] == "psfxl"
    assert context.request.metrics
```

Append precondition failure coverage:

```python
def test_load_adapter_context_rejects_formula_hash_drift(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["metrics"][0]["expression_sha256"] = expression_sha256("different_formula")
    _write_json(request_path, request)

    with pytest.raises(AdapterPreconditionError, match="expression hash mismatch"):
        load_adapter_context(project_dir)


def test_load_adapter_context_rejects_non_psfxl_request(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["spectre"]["output_format"] = "psfascii"
    _write_json(request_path, request)

    with pytest.raises(AdapterPreconditionError, match="output_format must be psfxl"):
        load_adapter_context(project_dir)


def test_load_adapter_context_rejects_unsafe_expected_psf_dir(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["expected_psf_dir"] = "../escaped/psf"
    _write_json(request_path, request)

    with pytest.raises(AdapterPreconditionError, match="expected_psf_dir is unsafe"):
        load_adapter_context(project_dir)
```

- [x] **Step 2: Run tests and verify they fail for missing module**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: import failure for `hermes_workflow.execution_adapters`.

- [x] **Step 3: Create the adapter package and context loader**

Create `src/hermes_workflow/execution_adapters/__init__.py`:

```python
from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterPreconditionError,
    SpectreOceanContext,
    load_adapter_context,
)

__all__ = [
    "AdapterPreconditionError",
    "SpectreOceanContext",
    "load_adapter_context",
]
```

Create `src/hermes_workflow/execution_adapters/spectre_ocean.py` with these definitions:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

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
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"


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


def load_adapter_context(
    project_dir: Path,
    *,
    run_id: str | None = None,
) -> SpectreOceanContext:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _safe_project_path(project_dir, run_relative, "run directory")
    prepared_path = run_dir / "real_run_manifest.json"
    request_path = run_dir / "metric_extraction_request.json"
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

    if prepared.run_id != selected_run_id:
        raise AdapterPreconditionError("real run manifest run_id mismatch")
    if request.run_id != selected_run_id:
        raise AdapterPreconditionError("metric request run_id mismatch")
    if prepared.status != "prepared":
        raise AdapterPreconditionError("real run package is not prepared")
    if request.backend != METRIC_BACKEND:
        raise AdapterPreconditionError(f"backend is unsupported: {request.backend}")
    if request.spectre.get("output_format") != "psfxl":
        raise AdapterPreconditionError("output_format must be psfxl")
    if request.ocean.mode != OCEAN_MODE:
        raise AdapterPreconditionError(f"ocean mode is unsupported: {request.ocean.mode}")

    input_scs = _safe_project_path(
        project_dir,
        request.prepared_input_scs,
        "prepared_input_scs",
        required_prefix=run_relative,
    )
    psf_dir = _safe_project_path(
        project_dir,
        request.expected_psf_dir,
        "expected_psf_dir",
        required_prefix=run_relative,
    )
    metrics_dir = _safe_project_path(
        project_dir,
        f"{run_relative}/metrics",
        "metrics directory",
        required_prefix=run_relative,
    )
    _safe_project_path(
        project_dir,
        request.ocean.script_file,
        "ocean script_file",
        required_prefix=run_relative,
    )
    _safe_project_path(
        project_dir,
        request.ocean.log_file,
        "ocean log_file",
        required_prefix=run_relative,
    )
    _safe_project_path(
        project_dir,
        request.ocean.scalar_output_file,
        "ocean scalar_output_file",
        required_prefix=run_relative,
    )

    if request.prepared_input_scs != prepared.rendered_input_scs:
        raise AdapterPreconditionError("prepared input path mismatch")
    if request.prepared_input_sha256 != prepared.rendered_input_sha256:
        raise AdapterPreconditionError("prepared input hash mismatch")
    if prepared.metric_extraction_request != f"{run_relative}/metric_extraction_request.json":
        raise AdapterPreconditionError("metric request path mismatch")
    if prepared.metric_extraction_request_sha256 != sha256_file(request_path):
        raise AdapterPreconditionError("metric request file hash mismatch")
    if not input_scs.exists():
        raise AdapterPreconditionError("prepared input_scs is missing")
    if sha256_file(input_scs) != request.prepared_input_sha256:
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
        if metric.nil_policy != "fail" or metric.non_finite_policy != "fail":
            raise AdapterPreconditionError(
                f"metric {metric.name} failure policy is unsupported"
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
    )


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise AdapterPreconditionError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_model(path: Path, model_class, label: str):
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
```

- [x] **Step 4: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: all Task 1 tests pass.

- [x] **Step 5: Run formatting/lint check**

Run:

```bash
python3 -m ruff check src/hermes_workflow/execution_adapters tests/test_spectre_ocean_adapter.py
```

Expected: `All checks passed!`

- [x] **Step 6: Mark Task 1 complete**

Update this task's checkboxes to `[x]` after local verification and review gate approval.

## Task 2: OCEAN Replay Script Generation And Scalar TSV Parsing

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `tests/test_spectre_ocean_adapter.py`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Add failing tests for exact formula preservation and scalar parsing**

Append to `tests/test_spectre_ocean_adapter.py`:

```python
from hermes_workflow.execution_adapters.spectre_ocean import (
    parse_ocean_scalars,
    render_ocean_replay_script,
)


def test_render_ocean_replay_script_preserves_formula_text(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    context = load_adapter_context(project_dir)

    script = render_ocean_replay_script(context)

    for metric in context.request.metrics:
        assert metric.expression in script
        assert metric.expression_sha256 in script
    assert "openResults" in script
    assert "selectResult" in script
    assert "ocean_scalars.tsv" in script
    assert "rewrite" not in script.lower()


def test_parse_ocean_scalars_accepts_finite_pass_rows(tmp_path: Path) -> None:
    scalars_path = tmp_path / "ocean_scalars.tsv"
    scalars_path.write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
        "rise\t1.25e-10\ts\tpass\tabc123\t\n"
        "fall\t1.50e-10\ts\tpass\tdef456\t\n",
        encoding="utf-8",
    )

    rows = parse_ocean_scalars(scalars_path)

    assert rows["rise"].value == 1.25e-10
    assert rows["rise"].value_text == "1.25e-10"
    assert rows["fall"].status == "pass"


def test_parse_ocean_scalars_rejects_non_finite_pass_row(tmp_path: Path) -> None:
    scalars_path = tmp_path / "ocean_scalars.tsv"
    scalars_path.write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
        "rise\tNaN\ts\tpass\tabc123\t\n",
        encoding="utf-8",
    )

    with pytest.raises(AdapterPreconditionError, match="not finite"):
        parse_ocean_scalars(scalars_path)
```

- [x] **Step 2: Run tests and verify they fail for missing functions**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_render_ocean_replay_script_preserves_formula_text tests/test_spectre_ocean_adapter.py::test_parse_ocean_scalars_accepts_finite_pass_rows tests/test_spectre_ocean_adapter.py::test_parse_ocean_scalars_rejects_non_finite_pass_row -q
```

Expected: import or attribute failures for `render_ocean_replay_script` and `parse_ocean_scalars`.

- [x] **Step 3: Implement OCEAN script rendering and scalar parsing**

Add to `src/hermes_workflow/execution_adapters/spectre_ocean.py`:

```python
import csv
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OceanScalarRow:
    metric: str
    value: float | None
    value_text: str | None
    unit: str
    status: str
    expression_sha256: str
    message: str


def render_ocean_replay_script(context: SpectreOceanContext) -> str:
    scalar_path = _posix_join(context.request.ocean.scalar_output_file)
    psf_path = _posix_join(context.request.expected_psf_dir)
    lines = [
        "; Generated by ic-auto-opt-workflow C-7 execution adapter",
        "; Formula text below is copied exactly from metric_extraction_request.json",
        f"openResults({_skill_string(psf_path)})",
        f"out = outfile({_skill_string(scalar_path)})",
        'fprintf(out "metric\\tvalue\\tunit\\tstatus\\texpression_sha256\\tmessage\\n")',
    ]
    for metric in context.request.metrics:
        lines.extend(
            [
                f"selectResult('{metric.result})",
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
                    f"{_skill_string(metric.expression_sha256)} "
                    ")"
                ),
                "  else",
                (
                    '    fprintf(out "%s\\t\\t%s\\tfail\\t%s\\tnon_scalar\\n" '
                    f"{_skill_string(metric.name)} "
                    f"{_skill_string(metric.unit)} "
                    f"{_skill_string(metric.expression_sha256)} "
                    ")"
                ),
                "  )",
                "else",
                (
                    '  fprintf(out "%s\\t\\t%s\\tfail\\t%s\\texpression_error\\n" '
                    f"{_skill_string(metric.name)} "
                    f"{_skill_string(metric.unit)} "
                    f"{_skill_string(metric.expression_sha256)} "
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
        expected = ["metric", "value", "unit", "status", "expression_sha256", "message"]
        if reader.fieldnames != expected:
            raise AdapterPreconditionError("ocean scalar output header is invalid")
        rows: dict[str, OceanScalarRow] = {}
        for row in reader:
            metric = row["metric"]
            status = row["status"]
            value_text = row["value"]
            value = None
            if status == "pass":
                try:
                    value = float(value_text)
                except ValueError as exc:
                    raise AdapterPreconditionError(
                        f"metric {metric} value is not numeric"
                    ) from exc
                if not math.isfinite(value):
                    raise AdapterPreconditionError(f"metric {metric} value is not finite")
            if metric in rows:
                raise AdapterPreconditionError(f"duplicate scalar metric: {metric}")
            rows[metric] = OceanScalarRow(
                metric=metric,
                value=value,
                value_text=value_text if value_text else None,
                unit=row["unit"],
                status=status,
                expression_sha256=row["expression_sha256"],
                message=row["message"],
            )
    return rows


def _skill_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _posix_join(value: str) -> str:
    return PurePosixPath(value).as_posix()
```

- [x] **Step 4: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_render_ocean_replay_script_preserves_formula_text tests/test_spectre_ocean_adapter.py::test_parse_ocean_scalars_accepts_finite_pass_rows tests/test_spectre_ocean_adapter.py::test_parse_ocean_scalars_rejects_non_finite_pass_row -q
```

Expected: all three tests pass.

- [x] **Step 5: Add stricter formula-regression test**

Append:

```python
def test_render_ocean_replay_script_keeps_drpl_formula_unchanged(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    expression = 'db(harmonic(drplPacVolGnExpDen("(v(\\"/RF_P\\" ?result \\"pac\\")-v(\\"/RF_N\\" ?result \\"pac\\"))" \\'(0) nil) \\'-1))'
    request["metrics"][0]["expression"] = expression
    request["metrics"][0]["expression_sha256"] = expression_sha256(expression)
    request["metrics"][0]["result"] = "pac"
    _write_json(request_path, request)
    prepared_path = (
        project_dir / "runs" / "real" / "real_001" / "real_run_manifest.json"
    )
    prepared = _load_json(prepared_path)
    from hermes_workflow.package import sha256_file

    prepared["metric_extraction_request_sha256"] = sha256_file(request_path)
    _write_json(prepared_path, prepared)

    context = load_adapter_context(project_dir)
    script = render_ocean_replay_script(context)

    assert expression in script
    assert "drplPacVolGnExpDen" in script
    assert 'VT("' not in script
```

- [x] **Step 6: Run all adapter tests and lint**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
python3 -m ruff check src/hermes_workflow/execution_adapters tests/test_spectre_ocean_adapter.py
```

Expected: tests pass and ruff reports `All checks passed!`

- [x] **Step 7: Mark Task 2 complete**

Update this task's checkboxes to `[x]` after local verification and review gate approval.

## Task 3: Fake Runner Success Path And Manifest Writing

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `tests/test_spectre_ocean_adapter.py`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Add fake runner success test**

Append to `tests/test_spectre_ocean_adapter.py`:

```python
from hermes_workflow.execution_adapters.spectre_ocean import (
    CommandResult,
    run_spectre_ocean_adapter,
)
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.result_handoff import check_real_run
from hermes_workflow.reports import MetricResultCheckStatus, RealRunCheckStatus


class FakeSuccessRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        self.commands.append(argv)
        stdout_path.write_text("fake stdout\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        if argv[0] == "spectre":
            psf_dir = cwd / "psf"
            psf_dir.mkdir(parents=True, exist_ok=True)
            (psf_dir / "spectre.out").write_text("fake spectre out\n", encoding="utf-8")
        elif argv[0] == "ocean":
            metrics_dir = cwd / "metrics"
            request = _load_json(cwd / "metric_extraction_request.json")
            lines = ["metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"]
            for index, metric in enumerate(request["metrics"], start=1):
                lines.append(
                    f"{metric['name']}\t{index}.25\t{metric['unit']}\tpass\t"
                    f"{metric['expression_sha256']}\t\n"
                )
            (metrics_dir / "ocean.log").write_text("fake ocean log\n", encoding="utf-8")
            (metrics_dir / "ocean_scalars.tsv").write_text(
                "".join(lines),
                encoding="utf-8",
            )
        return CommandResult(return_code=0, started_at_utc="2026-06-02T00:30:00Z", completed_at_utc="2026-06-02T00:31:00Z")


def test_run_spectre_ocean_adapter_fake_success_writes_valid_contracts(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "succeeded"
    assert [command[0] for command in runner.commands] == ["spectre", "ocean"]
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS
```

- [x] **Step 2: Run test and verify it fails for missing orchestration**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_run_spectre_ocean_adapter_fake_success_writes_valid_contracts -q
```

Expected: import or attribute failure for `CommandResult` and `run_spectre_ocean_adapter`.

- [x] **Step 3: Implement command runner protocol and success orchestration**

Add to `src/hermes_workflow/execution_adapters/spectre_ocean.py`:

```python
import subprocess
from typing import Protocol


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
```

Add orchestration functions:

```python
def run_spectre_ocean_adapter(
    project_dir: Path,
    *,
    run_id: str | None = None,
    runner: CommandRunner | None = None,
    allow_overwrite: bool = False,
) -> AdapterRunResult:
    context = load_adapter_context(project_dir, run_id=run_id)
    _assert_overwrite_policy(context, allow_overwrite=allow_overwrite)
    context.metrics_dir.mkdir(parents=True, exist_ok=True)
    context.psf_dir.mkdir(parents=True, exist_ok=True)
    runner = runner or SubprocessCommandRunner()

    script_path = context.project_dir / Path(*PurePosixPath(context.request.ocean.script_file).parts)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(render_ocean_replay_script(context), encoding="utf-8")

    spectre_result = runner.run(
        _spectre_argv(context),
        cwd=context.run_dir,
        stdout_path=context.run_dir / "spectre.stdout",
        stderr_path=context.run_dir / "spectre.stderr",
        timeout_s=int(context.request.spectre.get("timeout_s", 3600)),
    )
    if spectre_result.return_code != 0:
        result_manifest_path = _write_result_manifest(
            context,
            status="failed",
            started_at_utc=spectre_result.started_at_utc,
            completed_at_utc=spectre_result.completed_at_utc,
            spectre_return_code=spectre_result.return_code,
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

    ocean_result = runner.run(
        _ocean_argv(context),
        cwd=context.run_dir,
        stdout_path=context.metrics_dir / "ocean.stdout",
        stderr_path=context.metrics_dir / "ocean.stderr",
        timeout_s=int(context.request.spectre.get("timeout_s", 3600)),
    )
    result_manifest_path = _write_result_manifest(
        context,
        status="succeeded",
        started_at_utc=spectre_result.started_at_utc,
        completed_at_utc=ocean_result.completed_at_utc,
        spectre_return_code=spectre_result.return_code,
        include_metric_manifest=True,
        notes="spectre command completed",
    )
    metric_manifest_path = _write_metric_result_manifest(
        context,
        ocean_return_code=ocean_result.return_code,
    )
    status = "succeeded" if ocean_result.return_code == 0 else "failed"
    return AdapterRunResult(
        status=status,
        run_id=context.run_id,
        result_manifest_path=result_manifest_path,
        metric_result_manifest_path=metric_manifest_path,
        issues=[] if status == "succeeded" else ["ocean command failed"],
    )
```

Implement helpers `_spectre_argv`, `_ocean_argv`, `_write_result_manifest`, `_write_metric_result_manifest`, and `_utc_now` so they produce the exact C-5/C-6 shapes currently expected by `check_real_run()` and `check_metric_results()`.

Use these command arrays for the first version:

```python
def _spectre_argv(context: SpectreOceanContext) -> list[str]:
    return [
        "spectre",
        "-64",
        str(context.input_scs.name),
        "-format",
        "psfxl",
        "-raw",
        str(context.psf_dir.name),
    ]


def _ocean_argv(context: SpectreOceanContext) -> list[str]:
    return [
        "ocean",
        "-nograph",
        "-replay",
        str(PurePosixPath(context.request.ocean.script_file).name),
        "-log",
        "ocean.log",
    ]
```

If `_ocean_argv()` needs the replay script path relative to `runs/real/<run_id>`, use `metrics/metric_probe.ocn`, not the basename alone.

- [x] **Step 4: Run fake success test**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_run_spectre_ocean_adapter_fake_success_writes_valid_contracts -q
```

Expected: pass.

- [x] **Step 5: Run C-5/C-6 related tests**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: all tests pass.

- [x] **Step 6: Mark Task 3 complete**

Update this task's checkboxes to `[x]` after local verification and review gate approval.

## Task 4: Failure Artifacts, Overwrite Policy, And Safety Hardening

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `tests/test_spectre_ocean_adapter.py`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Add failure and overwrite tests**

Append:

```python
class FakeSpectreFailureRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        self.commands.append(argv)
        stdout_path.write_text("fake stdout\n", encoding="utf-8")
        stderr_path.write_text("fake spectre failure\n", encoding="utf-8")
        if argv[0] == "spectre":
            return CommandResult(return_code=2, started_at_utc="2026-06-02T00:30:00Z", completed_at_utc="2026-06-02T00:31:00Z")
        raise AssertionError("ocean should not run after spectre failure")


class FakeOceanFailureRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        if argv[0] == "ocean":
            self.commands.append(argv)
            stdout_path.write_text("fake ocean stdout\n", encoding="utf-8")
            stderr_path.write_text("fake ocean failure\n", encoding="utf-8")
            (cwd / "metrics" / "ocean.log").write_text(
                "fake ocean failure log\n",
                encoding="utf-8",
            )
            (cwd / "metrics" / "ocean_scalars.tsv").write_text(
                "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
                encoding="utf-8",
            )
            return CommandResult(return_code=3, started_at_utc="2026-06-02T00:31:00Z", completed_at_utc="2026-06-02T00:32:00Z")
        return super().run(
            argv,
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_s=timeout_s,
        )


def test_spectre_failure_writes_failed_result_manifest_and_skips_ocean(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSpectreFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert [command[0] for command in runner.commands] == ["spectre"]
    real_report = check_real_run(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert real_report.result_status == "failed"


def test_ocean_failure_writes_metric_failure_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeOceanFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    assert any("ocean return_code" in issue for issue in metric_report.issues)


def test_adapter_rejects_overwrite_of_existing_success(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_spectre_ocean_adapter(project_dir, runner=FakeSuccessRunner())

    with pytest.raises(AdapterPreconditionError, match="result already exists"):
        run_spectre_ocean_adapter(project_dir, runner=FakeSuccessRunner())
```

- [x] **Step 2: Run tests and verify they fail before hardening**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_spectre_failure_writes_failed_result_manifest_and_skips_ocean tests/test_spectre_ocean_adapter.py::test_ocean_failure_writes_metric_failure_manifest tests/test_spectre_ocean_adapter.py::test_adapter_rejects_overwrite_of_existing_success -q
```

Expected: failures for incomplete failure/overwrite behavior.

- [x] **Step 3: Implement failure manifest and overwrite behavior**

Update `_assert_overwrite_policy()`:

```python
def _assert_overwrite_policy(
    context: SpectreOceanContext,
    *,
    allow_overwrite: bool,
) -> None:
    result_manifest = context.run_dir / "result_manifest.json"
    metric_manifest = context.metrics_dir / "metric_result_manifest.json"
    if allow_overwrite:
        return
    if result_manifest.exists() or metric_manifest.exists():
        raise AdapterPreconditionError("result already exists; use allow_overwrite to rerun")
```

Ensure Spectre failure writes:

```json
{
  "status": "failed",
  "result_data": null,
  "metric_result_manifest": null,
  "artifact_files": [
    "runs/real/real_001/spectre.stdout",
    "runs/real/real_001/spectre.stderr"
  ]
}
```

Ensure OCEAN failure writes:

- `result_manifest.json` with `status: "succeeded"` when Spectre succeeded.
- `metric_result_manifest.json` with `status: "failed"`.
- `ocean.return_code` set to the failing code.
- `metrics` entries for every requested metric with `status: "failed"`, `value: null`, `value_text: null`, and an issue such as `"ocean command failed"`.

- [x] **Step 4: Run failure tests**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: all adapter tests pass.

- [x] **Step 5: Run related checker tests**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: all tests pass.

- [x] **Step 6: Mark Task 4 complete**

Update this task's checkboxes to `[x]` after local verification and review gate approval.

## Task 5: Execution-Side Tool Entry Point

**Files:**

- Create: `tools/run_spectre_ocean_adapter.py`
- Modify: `tests/test_spectre_ocean_adapter.py`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Add CLI smoke tests using monkeypatch**

Append:

```python
def test_tool_entrypoint_reports_success_without_real_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    import tools.run_spectre_ocean_adapter as entrypoint

    def fake_run(project: Path, **kwargs):
        assert project == project_dir
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "run_id": "real_001",
                "result_manifest_path": project_dir
                / "runs"
                / "real"
                / "real_001"
                / "result_manifest.json",
                "metric_result_manifest_path": project_dir
                / "runs"
                / "real"
                / "real_001"
                / "metrics"
                / "metric_result_manifest.json",
                "issues": [],
            },
        )()

    monkeypatch.setattr(entrypoint, "run_spectre_ocean_adapter", fake_run)

    exit_code = entrypoint.main([str(project_dir), "--run-id", "real_001"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "succeeded" in captured.out
```

- [x] **Step 2: Run test and verify it fails for missing tool**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_tool_entrypoint_reports_success_without_real_tools -q
```

Expected: import failure for `tools.run_spectre_ocean_adapter`.

- [x] **Step 3: Create tool entry point**

Create `tools/run_spectre_ocean_adapter.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterPreconditionError,
    run_spectre_ocean_adapter,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the execution-side Spectre + OCEAN adapter.",
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--run-id", default="real_001")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_spectre_ocean_adapter(
            args.project_dir,
            run_id=args.run_id,
            allow_overwrite=args.allow_overwrite,
        )
    except AdapterPreconditionError as exc:
        print(f"failed: {exc}")
        return 2

    print(f"{result.status}: run_id={result.run_id}")
    print(f"result_manifest={result.result_manifest_path}")
    if result.metric_result_manifest_path is not None:
        print(f"metric_result_manifest={result.metric_result_manifest_path}")
    for issue in result.issues:
        print(f"issue: {issue}")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run entrypoint test**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py::test_tool_entrypoint_reports_success_without_real_tools -q
```

Expected: pass.

- [x] **Step 5: Run adapter suite and ruff**

Run:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
python3 -m ruff check src/hermes_workflow/execution_adapters tests/test_spectre_ocean_adapter.py tools/run_spectre_ocean_adapter.py
```

Expected: tests pass and ruff reports `All checks passed!`

- [x] **Step 6: Mark Task 5 complete**

Update this task's checkboxes to `[x]` after local verification.

## Task 6: Docs, Progress, Full Verification, And Final Review

**Files:**

- Modify: `README.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

- [x] **Step 1: Update README with the execution adapter command**

Add this after the C-6 metric check section:

```markdown
The C-7 execution-side adapter is an explicit tool boundary, not a Hermes validator:

```bash
python tools/run_spectre_ocean_adapter.py projects/bridge_test_inv --run-id real_001
```

The supervisor agent should still run `check-real-run` and `check-metric-results` after the adapter returns. Adapter success alone is not workflow success.
```

- [x] **Step 2: Update overview and checkpoints**

Record:

```text
C-7 Spectre + OCEAN execution adapter wires the physical tool boundary while preserving the locked role model:
supervisor agent -> Hermes workflow tooling -> execution agent -> C-7 adapter -> Hermes workflow checks.
Automated tests use fake runners; real Cadence smoke remains local-only evidence.
```

- [x] **Step 3: Run full verification**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests tools
git diff --check
```

Expected:

```text
pytest: 337 passed
ruff: All checks passed!
git diff --check: no output
```

- [x] **Step 4: Run final combined review gate**

Use the project's established review path. The review request must include:

```text
Review C-7 Spectre + OCEAN execution adapter implementation.
Focus on:
- locked role model preservation
- no PSF parsing in Python
- no formula rewriting
- no real tool invocation in tests
- command execution only through explicit adapter entry point
- path and overwrite safety
- returned artifacts satisfy existing C-5/C-6 checkers
```

Final re-review result:

```text
STATUS: APPROVED
FINDINGS: None.
SUMMARY: Previous blockers are closed. C-7 is safe to close under the stated no-real-tool boundary.
```

- [x] **Step 5: Fix review findings**

If review returns Critical or Important findings, fix them, rerun focused tests, then rerun final verification.

First final combined review returned three blockers:

- OCEAN was run from the run directory while generated script paths were project-relative.
- OCEAN scalar TSV parse failures after a zero exit were not converted into structured C-5/C-6 failure artifacts.
- Spectre did not explicitly write the declared `psf/spectre.out` log artifact.

Fixes:

- OCEAN now runs from the project root and receives project-relative `-replay` and `-log` paths.
- Spectre command now includes `-log psf/spectre.out` while still running from the run directory.
- Metric manifest writing now converts scalar TSV parse failures into failed `metric_result_manifest.json` output and failed adapter status.
- Regression coverage added for project-root OCEAN paths and malformed scalar TSV after a zero OCEAN exit.

Fresh verification after fixes:

```text
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
55 passed

python3 -m pytest -q
337 passed

python3 -m ruff check src tests tools
All checks passed!

git diff --check
no output
```

- [x] **Step 6: Mark Task 6 complete**

Update this task's checkboxes to `[x]` after final verification and review pass.

## Plan Self-Review

- Spec coverage: Tasks cover adapter preconditions, safe paths, exact formula script generation, scalar TSV parsing, fake runner orchestration, result and metric manifest writing, failure manifests, overwrite policy, tool entry point, docs, full verification, and review gate.
- Role model coverage: The plan uses `supervisor agent`, `Hermes workflow tooling`, and `execution agent` as locked role names.
- Test isolation: No task invokes real Spectre, real OCEAN, real Virtuoso, SSH, Claude CLI as execution agent, network access, or local proprietary netlists.
- Deferred work: real local Cadence smoke, SSH execution profile, `virtuoso-bridge-lite` daemon integration, optimizer ledger/state update, multi-candidate execution, and sweep/corner aggregation remain outside C-7.

## Execution Handoff

Recommended execution mode: Subagent-Driven, one fresh worker per task, with the review gates listed above.
