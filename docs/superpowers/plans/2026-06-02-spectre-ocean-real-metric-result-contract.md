# Spectre + OCEAN Real Metric Result Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the C-6 Hermes file contract for Spectre + OCEAN scalar metric extraction results, with exact approved formulas and no Python PSF parsing or formula reimplementation.

**Architecture:** Extend the existing Hermes contract models so `metrics.yaml` can carry approved executable OCEAN formulas and `spectre.yaml` can request an OCEAN-readable PSF format. Add request generation to the C-4 `prepare-real-run` package, extend the C-5 handoff manifest with PSF/metric artifact references, then add a focused `metric_results.py` validator and `check-metric-results` CLI command for returned OCEAN scalar artifacts.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, pytest, ruff, existing Hermes `schemas`, `real_run`, `result_handoff`, `reports`, `package.sha256_file`, and deterministic JSON file contracts.

---

## Execution Model

Use `superpowers:subagent-driven-development` when implementing this plan. Start each coding task with a fresh worker context and provide only:

```text
docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md
docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
the current task section
```

Use a model-efficient review process:

1. Tasks 1-2 are schema/request generation and should get local deterministic verification after each task.
2. Task 3 is result handoff extension and should get local deterministic verification after completion.
3. Task 4 is the main validator and should get a focused code-quality review gate after local tests pass.
4. Tasks 5-6 are CLI/docs/final verification and should get one combined final review gate.

Do not call real Spectre, real OCEAN, real Virtuoso, or Claude CLI as a runtime adapter while implementing C-6. C-6 validates contracts only.

Do not copy, commit, or sanitize-and-commit real `input.scs`, Spectre logs, PSF data, or proprietary simulator outputs from local toolchain evidence directories. Tests must use tiny fake files under pytest `tmp_path`.

## File Map

- Modify `src/hermes_workflow/schemas.py`: add OCEAN formula schema under `MetricSpec`, extend `SpectreSettings.output_format` to include `psfxl`, and validate exact formula policy.
- Modify `src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml`: add approved `ocean` blocks to template metrics.
- Modify `src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml`: switch template real backend output format to `psfxl`.
- Modify `tests/fixtures/bridge_test_inv/config/metrics.yaml`: add approved `ocean` blocks for fixture metrics.
- Modify `tests/fixtures/bridge_test_inv/config/spectre.yaml`: switch fixture output format to `psfxl`.
- Modify `tests/test_validate.py`: cover schema acceptance/rejection for OCEAN formulas and `psfxl`.
- Create `src/hermes_workflow/metric_requests.py`: build `metric_extraction_request.json` payloads and formula hashes.
- Modify `src/hermes_workflow/real_run.py`: write metric extraction request during `prepare_real_run`, add paths/hashes to `real_run_manifest.json`, and expose the path through `RealRunPackage`.
- Modify `tests/test_real_run.py`: assert request generation and manifest extension.
- Modify `src/hermes_workflow/result_handoff.py`: extend C-5 `result_manifest.json` model to accept optional `result_data` and `metric_result_manifest` fields with path safety.
- Modify `tests/test_result_handoff.py`: cover extended handoff fields.
- Modify `src/hermes_workflow/reports.py`: add metric result check models.
- Create `src/hermes_workflow/metric_results.py`: validate returned `metric_result_manifest.json` against the request and handoff files.
- Create `tests/test_metric_results.py`: cover valid and invalid metric result manifests.
- Modify `src/hermes_workflow/cli.py`: add `check-metric-results`.
- Modify `tests/test_cli.py`: cover `check-metric-results` success and failure.
- Modify `README.md`, `docs/PROJECT_WORKFLOW_OVERVIEW.md`, `docs/EXECUTION_PROGRESS_2026-05-29.md`, `docs/COMPACT_RESUME_CHECKPOINT.md`, and `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`: record C-6 route and next action.
- Modify this plan file as task checkboxes are completed.

## Contract Constants

Use these exact strings across code and tests:

```python
METRIC_BACKEND = "spectre_ocean_batch"
OCEAN_MODE = "nograph_replay"
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
METRIC_REQUEST_NAME = "metric_extraction_request.json"
METRIC_RESULT_REPORT = "reports/metric_result_check_report.json"
```

Formula hash rule:

```python
hashlib.sha256(expression.encode("utf-8")).hexdigest()
```

C-6 allowed scalar policies:

```text
expected_value_type: real_scalar
nil_policy: fail
non_finite_policy: fail
```

## Task 1: Schema and Fixture Upgrade

**Files:**
- Modify: `src/hermes_workflow/schemas.py`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml`
- Modify: `tests/fixtures/bridge_test_inv/config/metrics.yaml`
- Modify: `tests/fixtures/bridge_test_inv/config/spectre.yaml`
- Modify: `tests/test_validate.py`

- [x] **Step 1: Add failing schema tests**

Append tests to `tests/test_validate.py`:

```python
def test_metrics_config_accepts_approved_ocean_formula() -> None:
    payload = {
        "schema_version": "1.0",
        "metrics": [
            {
                "name": "rise",
                "unit": "s",
                "maestro_formula": 'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")',
                "required_signals": ["/VOUT"],
                "ocean": {
                    "expression": 'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")',
                    "result": "tran",
                    "expression_source": "user_approved",
                    "source_reference": "maestro_output:rise",
                    "expected_value_type": "real_scalar",
                    "nil_policy": "fail",
                    "non_finite_policy": "fail",
                },
            }
        ],
        "constraints": [],
        "objective": {
            "direction": "minimize",
            "expression": "rise",
        },
    }

    config = MetricsConfig.model_validate(payload)

    assert config.metrics[0].ocean is not None
    assert config.metrics[0].ocean.result == "tran"
    assert config.metrics[0].ocean.expression_source == "user_approved"
```

Append rejection coverage:

```python
@pytest.mark.parametrize(
    ("ocean_overrides", "expected_message"),
    [
        ({"expression": ""}, "String should have at least 1 character"),
        ({"expected_value_type": "waveform"}, "Input should be 'real_scalar'"),
        ({"nil_policy": "allow"}, "Input should be 'fail'"),
        ({"non_finite_policy": "allow"}, "Input should be 'fail'"),
        ({"expression_source": "agent_discovered"}, "Input should be"),
        ({"expression": 'value(VT("{{VOUT}}") 1n)'}, "ocean.expression must not contain template placeholders"),
    ],
)
def test_metrics_config_rejects_invalid_ocean_formula_policy(
    ocean_overrides: dict,
    expected_message: str,
) -> None:
    ocean = {
        "expression": 'value(VT("/VOUT") 1n)',
        "result": "tran",
        "expression_source": "user_approved",
        "source_reference": "maestro_output:rise",
        "expected_value_type": "real_scalar",
        "nil_policy": "fail",
        "non_finite_policy": "fail",
    }
    ocean.update(ocean_overrides)
    payload = {
        "schema_version": "1.0",
        "metrics": [
            {
                "name": "rise",
                "unit": "s",
                "maestro_formula": 'value(VT("/VOUT") 1n)',
                "required_signals": ["/VOUT"],
                "ocean": ocean,
            }
        ],
        "constraints": [],
        "objective": {"direction": "minimize", "expression": "rise"},
    }

    with pytest.raises(ValidationError, match=expected_message):
        MetricsConfig.model_validate(payload)
```

Append Spectre format coverage:

```python
def test_spectre_config_accepts_psfxl_for_ocean_backend() -> None:
    config = SpectreConfig.model_validate(
        {
            "schema_version": "1.0",
            "spectre": {
                "engine": "spectre_x",
                "preset": "ax",
                "output_format": "psfxl",
                "parallel_jobs": 10,
                "timeout_s": 3600,
                "require_license_check": True,
                "keep_failed_runs": True,
                "keep_successful_runs": True,
            },
        }
    )

    assert config.spectre.output_format == "psfxl"
```

- [x] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_validate.py -q
```

Expected: tests fail because `MetricSpec` has no `ocean` field and `SpectreSettings.output_format` only allows `psfascii`.

- [x] **Step 3: Implement schema models**

In `src/hermes_workflow/schemas.py`, add enum classes near the existing metric enums:

```python
class OceanExpressionSource(StrEnum):
    USER_APPROVED = "user_approved"
    MAESTRO_OUTPUT_APPROVED = "maestro_output_approved"
    DIRECT_PLOT_APPROVED = "direct_plot_approved"


class OceanExpectedValueType(StrEnum):
    REAL_SCALAR = "real_scalar"


class FailPolicy(StrEnum):
    FAIL = "fail"
```

Add the OCEAN formula model:

```python
class OceanMetricSpec(StrictModel):
    expression: NonEmptyStr
    result: NonEmptyStr
    expression_source: OceanExpressionSource
    source_reference: NonEmptyStr
    expected_value_type: OceanExpectedValueType
    nil_policy: FailPolicy
    non_finite_policy: FailPolicy

    @field_validator("expression")
    @classmethod
    def _expression_has_no_template_placeholders(cls, value: str) -> str:
        if "{{" in value or "}}" in value:
            raise ValueError("ocean.expression must not contain template placeholders")
        return value
```

Modify `MetricSpec`:

```python
class MetricSpec(StrictModel):
    name: str
    unit: NonEmptyStr
    maestro_formula: NonEmptyStr
    required_signals: list[NonEmptyStr]
    ocean: OceanMetricSpec | None = None
```

Modify `SpectreSettings`:

```python
class SpectreSettings(StrictModel):
    engine: Literal["spectre_x"]
    preset: SpectrePreset
    output_format: Literal["psfascii", "psfxl"]
    parallel_jobs: StrictInt = Field(ge=1)
    timeout_s: StrictInt = Field(gt=0)
    require_license_check: StrictBool
    keep_failed_runs: StrictBool
    keep_successful_runs: StrictBool
```

- [x] **Step 4: Update template and fixture YAML**

In `src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml` and `tests/fixtures/bridge_test_inv/config/spectre.yaml`, set:

```yaml
spectre:
  output_format: psfxl
```

In both template and fixture `config/metrics.yaml`, add `ocean` blocks for all metrics. Use this exact shape for the inverter fixture metrics:

```yaml
  - name: rise
    unit: s
    maestro_formula: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
    required_signals:
      - /VOUT
    ocean:
      expression: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
      result: tran
      expression_source: user_approved
      source_reference: fixture:bridge_test_inv:rise
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail
```

Use the exact evidence-backed expressions for `fall` and `DC`:

```yaml
  - name: fall
    unit: s
    maestro_formula: fallTime(VT("/VOUT") 0.9 nil 0 nil 10 90 nil "time")
    required_signals:
      - /VOUT
    ocean:
      expression: fallTime(VT("/VOUT") 0.9 nil 0 nil 10 90 nil "time")
      result: tran
      expression_source: user_approved
      source_reference: fixture:bridge_test_inv:fall
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail

  - name: DC
    unit: W
    maestro_formula: VDC("/VDD") * IDC("/M0/S")
    required_signals:
      - /VDD
      - /M0/S
    ocean:
      expression: VDC("/VDD") * IDC("/M0/S")
      result: tran
      expression_source: user_approved
      source_reference: fixture:bridge_test_inv:DC
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail
```

Because C-6 does not perform unit conversion, update the fixture/template constraints to match the formula return units:

```yaml
constraints:
  - metric: rise
    op: lt
    value: "80e-12 s"
  - metric: fall
    op: lt
    value: "80e-12 s"
  - metric: DC
    op: lt
    value: "4e-4 W"
```

- [x] **Step 5: Run schema tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_validate.py -q
```

Expected: pass.

- [x] **Step 6: Run focused fixture validation**

Run:

```bash
.venv/bin/python -m pytest tests/test_package.py tests/test_validate.py -q
```

Expected: pass.

- [ ] **Step 7: Commit task**

Not committed in this execution pass because the worktree already contains prior uncommitted docs/toolchain-evidence changes. Stage and commit Task 1 separately when the branch history is ready.

```bash
git add src/hermes_workflow/schemas.py \
  src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml \
  src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml \
  tests/fixtures/bridge_test_inv/config/metrics.yaml \
  tests/fixtures/bridge_test_inv/config/spectre.yaml \
  tests/test_validate.py \
  docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "feat: add ocean metric contract schema"
```

## Task 2: Metric Extraction Request Generation

**Files:**
- Create: `src/hermes_workflow/metric_requests.py`
- Modify: `src/hermes_workflow/real_run.py`
- Modify: `tests/test_real_run.py`

- [x] **Step 1: Add failing request-generation test**

Append to `tests/test_real_run.py`:

```python
def test_prepare_real_run_writes_metric_extraction_request(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:20:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    manifest = _load_json(run_dir / "real_run_manifest.json")

    assert package.metric_request_path == request_path
    assert request["schema_version"] == "1.0"
    assert request["backend"] == "spectre_ocean_batch"
    assert request["run_id"] == "real_001"
    assert request["candidate_id"] == "real_001"
    assert request["prepared_input_scs"] == "runs/real/real_001/input.scs"
    assert request["prepared_input_sha256"] == manifest["rendered_input_sha256"]
    assert request["expected_psf_dir"] == "runs/real/real_001/psf"
    assert request["spectre"]["output_format"] == "psfxl"
    assert request["ocean"] == {
        "mode": "nograph_replay",
        "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
        "log_file": "runs/real/real_001/metrics/ocean.log",
        "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv",
    }
    assert request["metrics"][0]["name"] == "rise"
    assert request["metrics"][0]["expression"]
    assert request["metrics"][0]["expression_sha256"]
    assert "rewrite_metric_formula" in request["forbidden_actions"]
    assert manifest["metric_extraction_request"] == "runs/real/real_001/metric_extraction_request.json"
    assert manifest["metric_extraction_request_sha256"]
```

Add a failure test:

```python
def test_prepare_real_run_rejects_metric_without_ocean_formula(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics_text = metrics_path.read_text(encoding="utf-8")
    metrics_path.write_text(
        metrics_text.replace(
            "    ocean:\n"
            "      expression: riseTime(VT(\"/VOUT\") 0 nil 0.9 nil 10 90 nil \"time\")\n"
            "      result: tran\n"
            "      expression_source: user_approved\n"
            "      source_reference: fixture:bridge_test_inv:rise\n"
            "      expected_value_type: real_scalar\n"
            "      nil_policy: fail\n"
            "      non_finite_policy: fail\n",
            "",
            1,
        ),
        encoding="utf-8",
    )
    _approve_project(project_dir)
    _write_template(project_dir)

    with pytest.raises(ValueError, match="metric rise is missing ocean formula"):
        prepare_real_run(project_dir)
```

- [x] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run.py::test_prepare_real_run_writes_metric_extraction_request tests/test_real_run.py::test_prepare_real_run_rejects_metric_without_ocean_formula -q
```

Expected: fail because `metric_requests.py` and `metric_request_path` do not exist.

- [x] **Step 3: Create request builder**

Create `src/hermes_workflow/metric_requests.py`:

```python
from __future__ import annotations

import hashlib

from hermes_workflow.validate import ContractBundle


METRIC_BACKEND = "spectre_ocean_batch"
OCEAN_MODE = "nograph_replay"
OCEAN_READY_FORMATS = {"psfxl"}


def expression_sha256(expression: str) -> str:
    return hashlib.sha256(expression.encode("utf-8")).hexdigest()


def build_metric_extraction_request(
    bundle: ContractBundle,
    *,
    run_id: str,
    candidate_id: str,
    prepared_input_scs: str,
    prepared_input_sha256: str,
) -> dict:
    spectre = bundle.spectre.spectre
    if spectre.output_format not in OCEAN_READY_FORMATS:
        raise ValueError(
            f"spectre.output_format must be OCEAN-ready for metric extraction: {spectre.output_format}"
        )

    metrics = []
    for metric in bundle.metrics.metrics:
        if metric.ocean is None:
            raise ValueError(f"metric {metric.name} is missing ocean formula")
        ocean = metric.ocean
        metrics.append(
            {
                "name": metric.name,
                "unit": metric.unit,
                "required_signals": metric.required_signals,
                "result": ocean.result,
                "expression": ocean.expression,
                "expression_sha256": expression_sha256(ocean.expression),
                "expression_source": ocean.expression_source.value,
                "source_reference": ocean.source_reference,
                "expected_value_type": ocean.expected_value_type.value,
                "nil_policy": ocean.nil_policy.value,
                "non_finite_policy": ocean.non_finite_policy.value,
            }
        )

    run_prefix = f"runs/real/{run_id}"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "backend": METRIC_BACKEND,
        "prepared_input_scs": prepared_input_scs,
        "prepared_input_sha256": prepared_input_sha256,
        "expected_psf_dir": f"{run_prefix}/psf",
        "spectre": {
            "engine": spectre.engine,
            "preset": spectre.preset.value,
            "output_format": spectre.output_format,
            "timeout_s": spectre.timeout_s,
        },
        "ocean": {
            "mode": OCEAN_MODE,
            "script_file": f"{run_prefix}/metrics/metric_probe.ocn",
            "log_file": f"{run_prefix}/metrics/ocean.log",
            "scalar_output_file": f"{run_prefix}/metrics/ocean_scalars.tsv",
        },
        "metrics": metrics,
        "forbidden_actions": [
            "rewrite_metric_formula",
            "parse_psf_in_python",
            "modify_prepared_input_scs",
            "modify_immutable_config_files",
            "write_results_outside_run_dir",
        ],
    }
```

- [x] **Step 4: Wire request into real-run package**

Modify `RealRunPackage` in `src/hermes_workflow/real_run.py`:

```python
@dataclass(frozen=True)
class RealRunPackage:
    run_id: str
    run_dir: Path
    rendered_input_scs: Path
    candidate_path: Path
    manifest_path: Path
    metric_request_path: Path
    candidate_payload: dict
    manifest_payload: dict
    metric_request_payload: dict
```

Import the helper:

```python
from hermes_workflow.metric_requests import build_metric_extraction_request
```

In `prepare_real_run()`, after writing `input.scs` and `candidate.json` but before writing the manifest, add:

```python
metric_request_relative = f"{REAL_RUN_ROOT}/{selected_run_id}/metric_extraction_request.json"
metric_request_path = _project_path(bundle, metric_request_relative)
metric_request_payload = build_metric_extraction_request(
    bundle,
    run_id=selected_run_id,
    candidate_id=selected_run_id,
    prepared_input_scs=rendered_relative,
    prepared_input_sha256=sha256_file(rendered_path),
)
metric_request_path.write_text(
    json.dumps(metric_request_payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
```

Add `metric_request_relative` and `metric_request_path` to `_build_manifest()` parameters, then include:

```python
"metric_extraction_request": metric_request_relative,
"metric_extraction_request_sha256": sha256_file(metric_request_path),
```

Return the new fields in `RealRunPackage`.

- [x] **Step 5: Run focused real-run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run.py -q
```

Expected: pass.

- [ ] **Step 6: Commit task**

Not committed in this execution pass because the implementer was explicitly instructed not to commit and the worktree contains prior unrelated changes.

```bash
git add src/hermes_workflow/metric_requests.py src/hermes_workflow/real_run.py tests/test_real_run.py docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "feat: write metric extraction request for real runs"
```

## Task 3: Extend Real-Run Result Handoff Metadata

**Files:**
- Modify: `src/hermes_workflow/result_handoff.py`
- Modify: `tests/test_result_handoff.py`

- [x] **Step 1: Add failing extended-handoff tests**

Append helper code to `tests/test_result_handoff.py`:

```python
def _write_extended_metric_handoff(project_dir: Path, *, overrides: dict | None = None) -> dict:
    payload = _write_result_handoff(project_dir)
    run_dir = project_dir / "runs" / "real" / "real_001"
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (psf_dir / "spectre.out").write_text("sanitized spectre output\n", encoding="utf-8")
    (metrics_dir / "metric_result_manifest.json").write_text("{}\n", encoding="utf-8")
    payload.update(
        {
            "result_data": {
                "kind": "spectre_psf",
                "psf_dir": "runs/real/real_001/psf",
                "spectre_out": "runs/real/real_001/psf/spectre.out",
            },
            "metric_result_manifest": "runs/real/real_001/metrics/metric_result_manifest.json",
        }
    )
    payload["artifact_files"] = [
        *payload["artifact_files"],
        "runs/real/real_001/psf/spectre.out",
        "runs/real/real_001/metrics/metric_result_manifest.json",
    ]
    if overrides:
        payload.update(overrides)
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
```

Append tests:

```python
def test_check_real_run_accepts_metric_artifact_references(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_extended_metric_handoff(project_dir)

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.PASS
    assert report.issues == []
```

```python
def test_check_real_run_rejects_unsafe_metric_result_manifest_path(tmp_path: Path) -> None:
    project_dir, _package = _prepare_real_run_project(tmp_path)
    _write_extended_metric_handoff(
        project_dir,
        overrides={"metric_result_manifest": "../metric_result_manifest.json"},
    )

    report = check_real_run(project_dir)

    assert report.status == RealRunCheckStatus.FAIL
    assert "result artifact path is unsafe: ../metric_result_manifest.json" in report.issues
```

- [x] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_result_handoff.py::test_check_real_run_accepts_metric_artifact_references tests/test_result_handoff.py::test_check_real_run_rejects_unsafe_metric_result_manifest_path -q
```

Expected: fail because `ResultManifest` forbids the new fields.

- [x] **Step 3: Extend result manifest model**

In `src/hermes_workflow/result_handoff.py`, add:

```python
class ResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    psf_dir: str
    spectre_out: str
```

Extend `ResultManifest`:

```python
    result_data: ResultData | None = None
    metric_result_manifest: str | None = None
```

In `_validate_cross_references()`, after validating `artifact_paths`, add:

```python
    if result.result_data is not None:
        if result.result_data.kind != "spectre_psf":
            issues.append(f"result_data kind is invalid: {result.result_data.kind}")
        for path_value in [result.result_data.psf_dir, result.result_data.spectre_out]:
            resolved = _safe_run_path(bundle, run_id, path_value, issues)
            if resolved is not None and not resolved.exists():
                issues.append(f"result artifact is missing: {path_value}")
    if result.metric_result_manifest is not None:
        resolved = _safe_run_path(bundle, run_id, result.metric_result_manifest, issues)
        if resolved is not None and not resolved.exists():
            issues.append(f"result artifact is missing: {result.metric_result_manifest}")
```

- [x] **Step 4: Run handoff tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_result_handoff.py -q
```

Expected: pass.

- [ ] **Step 5: Commit task**

```bash
git add src/hermes_workflow/result_handoff.py tests/test_result_handoff.py docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "feat: allow metric artifacts in real-run handoff"
```

## Task 4: Metric Result Validator

**Files:**
- Modify: `src/hermes_workflow/reports.py`
- Create: `src/hermes_workflow/metric_results.py`
- Create: `tests/test_metric_results.py`

- [x] **Step 1: Add failing report model and validator tests**

Create `tests/test_metric_results.py`:

```python
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import build_execution_package, create_project_from_template, sha256_file
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import MetricResultCheckStatus
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-02T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(project_dir, created_at_utc="2026-06-02T00:10:00Z")
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_result_manifest(project_dir: Path, *, status: str = "succeeded") -> None:
    run_dir = project_dir / "runs" / "real" / "real_001"
    prepared = _load_json(run_dir / "real_run_manifest.json")
    psf_dir = run_dir / "psf"
    metrics_dir = run_dir / "metrics"
    psf_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (psf_dir / "spectre.out").write_text("sanitized spectre output\n", encoding="utf-8")
    (metrics_dir / "ocean.log").write_text("sanitized ocean log\n", encoding="utf-8")
    (metrics_dir / "ocean_scalars.tsv").write_text(
        "metric\tstatus\tvalue_text\tunit\texpression_sha256\tissue\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
        "status": status,
        "started_at_utc": "2026-06-02T00:30:00Z",
        "completed_at_utc": "2026-06-02T00:31:00Z",
        "simulator": {
            "engine": "spectre_x",
            "preset": "ax",
            "command_label": "external_spectre_run",
        },
        "prepared_input_scs": prepared["rendered_input_scs"],
        "prepared_input_sha256": prepared["rendered_input_sha256"],
        "result_data": {
            "kind": "spectre_psf",
            "psf_dir": "runs/real/real_001/psf",
            "spectre_out": "runs/real/real_001/psf/spectre.out",
        },
        "metric_result_manifest": "runs/real/real_001/metrics/metric_result_manifest.json",
        "log_file": "runs/real/real_001/spectre.log",
        "artifact_files": [
            "runs/real/real_001/psf/spectre.out",
            "runs/real/real_001/metrics/ocean.log",
            "runs/real/real_001/metrics/ocean_scalars.tsv",
        ],
        "notes": "sanitized fake execution result",
    }
    (run_dir / "spectre.log").write_text("sanitized run log\n", encoding="utf-8")
    (run_dir / "result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_metric_result_manifest(project_dir: Path, *, overrides: dict | None = None, metrics: list[dict] | None = None) -> dict:
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request_metrics = request["metrics"]
    metric_entries = []
    for request_metric in request_metrics:
        metric_entries.append(
            {
                "name": request_metric["name"],
                "status": "succeeded",
                "value": 1.25,
                "value_text": "1.25",
                "unit": request_metric["unit"],
                "result": request_metric["result"],
                "expression": request_metric["expression"],
                "expression_sha256": request_metric["expression_sha256"],
                "expression_source": request_metric["expression_source"],
                "issues": [],
            }
        )
    payload = {
        "schema_version": "1.0",
        "run_id": "real_001",
        "candidate_id": "real_001",
        "backend": "spectre_ocean_batch",
        "status": "succeeded",
        "request_file": "runs/real/real_001/metric_extraction_request.json",
        "request_sha256": sha256_file(request_path),
        "psf_dir": "runs/real/real_001/psf",
        "ocean": {
            "mode": "nograph_replay",
            "return_code": 0,
            "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
            "script_sha256": expression_sha256("sanitized ocean script"),
            "log_file": "runs/real/real_001/metrics/ocean.log",
            "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv",
        },
        "metrics": metrics if metrics is not None else metric_entries,
        "issues": [],
    }
    if overrides:
        payload.update(overrides)
    (run_dir / "metrics" / "metric_probe.ocn").write_text("sanitized ocean script\n", encoding="utf-8")
    (run_dir / "metrics" / "metric_result_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def test_check_metric_results_accepts_valid_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    report = check_metric_results(project_dir)

    persisted = _load_json(project_dir / "reports" / "metric_result_check_report.json")
    assert report.status == MetricResultCheckStatus.PASS
    assert report.run_id == "real_001"
    assert report.backend == "spectre_ocean_batch"
    assert report.checks.request_hash_ok is True
    assert report.checks.formula_hashes_ok is True
    assert report.checks.scalar_values_ok is True
    assert report.issues == []
    assert persisted["status"] == "pass"
```

Append failure tests:

```python
@pytest.mark.parametrize(
    ("mutator", "expected_issue"),
    [
        (
            lambda payload: payload.update({"request_sha256": "wrong"}),
            "metric request hash mismatch",
        ),
        (
            lambda payload: payload["metrics"][0].update({"expression": "value(VT(\"/OTHER\") 1n)"}),
            "metric rise expression does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"expression_sha256": "wrong"}),
            "metric rise expression hash does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"unit": "ps"}),
            "metric rise unit does not match request",
        ),
        (
            lambda payload: payload["metrics"][0].update({"value": math.nan, "value_text": "NaN"}),
            "metric rise value is not finite",
        ),
        (
            lambda payload: payload.update({"psf_dir": "../psf"}),
            "metric artifact path is unsafe: ../psf",
        ),
    ],
)
def test_check_metric_results_rejects_invalid_metric_contract(
    tmp_path: Path,
    mutator,
    expected_issue: str,
) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    mutator(payload)
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert expected_issue in report.issues
```

Append missing/extra metric tests:

```python
def test_check_metric_results_rejects_missing_metric(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"] = payload["metrics"][1:]
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "requested metric is missing from metric results: rise" in report.issues


def test_check_metric_results_rejects_extra_metric(tmp_path: Path) -> None:
    project_dir = _create_ready_project(tmp_path)
    _write_result_manifest(project_dir)
    payload = _write_metric_result_manifest(project_dir)
    payload["metrics"].append(
        {
            "name": "not_requested",
            "status": "succeeded",
            "value": 1.0,
            "value_text": "1.0",
            "unit": "V",
            "result": "tran",
            "expression": "1.0",
            "expression_sha256": expression_sha256("1.0"),
            "expression_source": "user_approved",
            "issues": [],
        }
    )
    result_path = project_dir / "runs" / "real" / "real_001" / "metrics" / "metric_result_manifest.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = check_metric_results(project_dir)

    assert report.status == MetricResultCheckStatus.FAIL
    assert "unrequested metric in metric results: not_requested" in report.issues
```

- [x] **Step 2: Run failing metric-result tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_metric_results.py -q
```

Expected: fail because `metric_results.py` and report models do not exist.

- [x] **Step 3: Add report models**

In `src/hermes_workflow/reports.py`, add:

```python
class MetricResultCheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class MetricResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MetricResultCheckFlags(StrictReport):
    request_hash_ok: bool = False
    result_manifest_ok: bool = False
    metric_manifest_ok: bool = False
    metric_identity_ok: bool = False
    formula_hashes_ok: bool = False
    scalar_values_ok: bool = False
    artifact_paths_ok: bool = False


class CheckedMetricResult(StrictReport):
    status: MetricResultStatus
    value: float | None
    value_text: str | None
    unit: str
    expression_sha256: str


class MetricResultCheckReport(StrictReport):
    schema_version: str
    status: MetricResultCheckStatus
    run_id: str
    candidate_id: str | None
    backend: str | None
    request_file: str
    metric_result_manifest: str
    psf_dir: str | None
    metrics: dict[str, CheckedMetricResult] = Field(default_factory=dict)
    checks: MetricResultCheckFlags
    issues: list[str] = Field(default_factory=list)
```

- [x] **Step 4: Implement validator**

Create `src/hermes_workflow/metric_results.py` with:

```python
from __future__ import annotations

import json
import math
import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError

from hermes_workflow.package import sha256_file
from hermes_workflow.reports import (
    CheckedMetricResult,
    MetricResultCheckFlags,
    MetricResultCheckReport,
    MetricResultCheckStatus,
    MetricResultStatus,
)
from hermes_workflow.validate import ContractBundle, assert_valid_project


RUN_ID_RE = re.compile(r"^real_[0-9]{3}$")
DEFAULT_RUN_ID = "real_001"
REAL_RUN_ROOT = "runs/real"
REPORT_RELATIVE = "reports/metric_result_check_report.json"


class OceanExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    return_code: int
    script_file: str
    script_sha256: str
    log_file: str
    scalar_output_file: str


class MetricResultEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: MetricResultStatus
    value: float | None = None
    value_text: str | None = None
    unit: str
    result: str
    expression: str
    expression_sha256: str
    expression_source: str
    issues: list[str] = []


class MetricResultManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    candidate_id: str
    backend: str
    status: MetricResultStatus
    request_file: str
    request_sha256: str
    psf_dir: str
    ocean: OceanExecution
    metrics: list[MetricResultEntry]
    issues: list[str] = []


def check_metric_results(project_dir: Path, *, run_id: str | None = None) -> MetricResultCheckReport:
    project_dir = Path(project_dir)
    selected_run_id = _validate_run_id(run_id or DEFAULT_RUN_ID)
    bundle = assert_valid_project(project_dir)
    run_relative = f"{REAL_RUN_ROOT}/{selected_run_id}"
    run_dir = _project_path(bundle, run_relative)
    request_relative = f"{run_relative}/metric_extraction_request.json"
    result_relative = f"{run_relative}/metrics/metric_result_manifest.json"
    report_path = _project_path(bundle, REPORT_RELATIVE)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    issues: list[str] = []
    checks = MetricResultCheckFlags()
    request = _load_json(run_dir / "metric_extraction_request.json", "metric extraction request", issues)
    handoff = _load_json(run_dir / "result_manifest.json", "result manifest", issues)
    manifest_payload = _load_json(run_dir / "metrics" / "metric_result_manifest.json", "metric result manifest", issues)

    manifest: MetricResultManifest | None = None
    if handoff and handoff.get("status") == "succeeded":
        checks.result_manifest_ok = True
    elif handoff:
        issues.append("simulator result is not succeeded")

    if manifest_payload:
        try:
            manifest = MetricResultManifest.model_validate(manifest_payload)
            checks.metric_manifest_ok = True
        except ValidationError:
            issues.append("metric result manifest is invalid")

    metrics: dict[str, CheckedMetricResult] = {}
    candidate_id: str | None = None
    backend: str | None = None
    psf_dir: str | None = None

    if request and handoff and manifest:
        candidate_id = manifest.candidate_id
        backend = manifest.backend
        psf_dir = manifest.psf_dir
        _validate_manifest(bundle, selected_run_id, request, handoff, manifest, checks, issues, metrics)

    report = MetricResultCheckReport(
        schema_version="1.0",
        status=MetricResultCheckStatus.FAIL if issues else MetricResultCheckStatus.PASS,
        run_id=selected_run_id,
        candidate_id=candidate_id,
        backend=backend,
        request_file=request_relative,
        metric_result_manifest=result_relative,
        psf_dir=psf_dir,
        metrics=metrics,
        checks=checks,
        issues=issues,
    )
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report
```

Continue the same file with helper functions:

```python
def _validate_manifest(
    bundle: ContractBundle,
    run_id: str,
    request: dict,
    handoff: dict,
    manifest: MetricResultManifest,
    checks: MetricResultCheckFlags,
    issues: list[str],
    metrics: dict[str, CheckedMetricResult],
) -> None:
    if manifest.request_sha256 == sha256_file(bundle.project_dir / Path(*PurePosixPath(manifest.request_file).parts)):
        checks.request_hash_ok = True
    else:
        issues.append("metric request hash mismatch")

    if manifest.run_id != run_id:
        issues.append("metric result run_id does not match requested run_id")
    if manifest.candidate_id != request.get("candidate_id"):
        issues.append("metric result candidate_id does not match request")
    if manifest.backend != request.get("backend"):
        issues.append("metric backend does not match request")
    if manifest.request_file != f"{REAL_RUN_ROOT}/{run_id}/metric_extraction_request.json":
        issues.append("metric request_file does not match expected path")
    if manifest.psf_dir != request.get("expected_psf_dir"):
        issues.append("metric psf_dir does not match request")

    path_values = [
        manifest.request_file,
        manifest.psf_dir,
        manifest.ocean.script_file,
        manifest.ocean.log_file,
        manifest.ocean.scalar_output_file,
    ]
    resolved = [_safe_run_path(bundle, run_id, path_value, issues) for path_value in path_values]
    if all(path is not None and path.exists() for path in resolved):
        checks.artifact_paths_ok = True
    for path_value, path in zip(path_values, resolved, strict=True):
        if path is not None and not path.exists():
            issues.append(f"metric artifact is missing: {path_value}")

    if not issues:
        checks.metric_identity_ok = True

    request_metrics = {metric["name"]: metric for metric in request.get("metrics", [])}
    result_metrics = {metric.name: metric for metric in manifest.metrics}
    for name in sorted(set(request_metrics) - set(result_metrics)):
        issues.append(f"requested metric is missing from metric results: {name}")
    for name in sorted(set(result_metrics) - set(request_metrics)):
        issues.append(f"unrequested metric in metric results: {name}")

    formula_ok = True
    scalar_ok = True
    for name in sorted(set(request_metrics) & set(result_metrics)):
        request_metric = request_metrics[name]
        result_metric = result_metrics[name]
        if result_metric.expression != request_metric["expression"]:
            formula_ok = False
            issues.append(f"metric {name} expression does not match request")
        if result_metric.expression_sha256 != request_metric["expression_sha256"]:
            formula_ok = False
            issues.append(f"metric {name} expression hash does not match request")
        if result_metric.unit != request_metric["unit"]:
            issues.append(f"metric {name} unit does not match request")
        if result_metric.result != request_metric["result"]:
            issues.append(f"metric {name} result selector does not match request")
        if result_metric.expression_source != request_metric["expression_source"]:
            issues.append(f"metric {name} expression source does not match request")
        if result_metric.status != MetricResultStatus.SUCCEEDED:
            scalar_ok = False
            issues.append(f"metric {name} did not succeed")
        if result_metric.value is None or not math.isfinite(result_metric.value):
            scalar_ok = False
            issues.append(f"metric {name} value is not finite")
        if result_metric.value_text in {None, "", "nil", "NaN", "Inf", "-Inf"}:
            scalar_ok = False
            issues.append(f"metric {name} value_text is not a finite scalar")
        metrics[name] = CheckedMetricResult(
            status=result_metric.status,
            value=result_metric.value,
            value_text=result_metric.value_text,
            unit=result_metric.unit,
            expression_sha256=result_metric.expression_sha256,
        )

    checks.formula_hashes_ok = formula_ok and not any("expression" in issue for issue in issues)
    checks.scalar_values_ok = scalar_ok and not any("value" in issue for issue in issues)
```

Add shared path helpers:

```python
def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run_id must match real_[0-9]{{3}}: {run_id}")
    return run_id


def _load_json(path: Path, label: str, issues: list[str]) -> dict | None:
    if not path.exists():
        issues.append(f"{label} is missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append(f"{label} is invalid")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label} is invalid")
        return None
    return payload


def _safe_run_path(bundle: ContractBundle, run_id: str, relative_path: str, issues: list[str]) -> Path | None:
    path = PurePosixPath(relative_path)
    run_prefix = PurePosixPath(REAL_RUN_ROOT) / run_id
    if path.is_absolute() or ".." in path.parts or not path.is_relative_to(run_prefix):
        issues.append(f"metric artifact path is unsafe: {relative_path}")
        return None
    return bundle.project_dir / Path(*path.parts)


def _project_path(bundle: ContractBundle, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"metric result check path must be project-relative and safe: {relative_path}")
    return bundle.project_dir / Path(*path.parts)
```

- [x] **Step 5: Run metric result tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_metric_results.py -q
```

Expected: pass.

- [x] **Step 6: Run neighboring tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run.py tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: pass.

- [x] **Step 7: Code-quality review gate**

Run local checks:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest tests/test_real_run.py tests/test_result_handoff.py tests/test_metric_results.py -q
```

Expected: ruff clean and tests pass. Then request one focused code-quality review for:

```text
C-6 metric result validator only. Review schema drift, path safety, formula hash validation, scalar finite checks, and whether Hermes accidentally computes or parses metrics.
```

- [ ] **Step 8: Commit task**

```bash
git add src/hermes_workflow/reports.py src/hermes_workflow/metric_results.py tests/test_metric_results.py docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "feat: validate ocean metric result manifests"
```

## Task 5: CLI Integration

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_cli_check_metric_results_passes_for_valid_fake_ocean_results(tmp_path: Path) -> None:
    from tests.test_metric_results import (
        TEMPLATE_TEXT,
        _load_json,
        _write_metric_result_manifest,
        _write_result_manifest,
    )

    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    write_pass_reports(project_dir)
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0
    _write_result_manifest(project_dir)
    _write_metric_result_manifest(project_dir)

    result = runner.invoke(app, ["check-metric-results", str(project_dir)])

    assert result.exit_code == 0
    assert "metric result check passed" in result.stdout
    assert "run: runs/real/real_001" in result.stdout
    assert "report: reports/metric_result_check_report.json" in result.stdout
    report = _load_json(project_dir / "reports" / "metric_result_check_report.json")
    assert report["status"] == "pass"
```

Append failure test:

```python
def test_cli_check_metric_results_reports_failure_without_traceback(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    assert runner.invoke(app, ["init", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["package", str(project_dir)]).exit_code == 0
    write_pass_reports(project_dir)
    assert runner.invoke(app, ["approve", str(project_dir)]).exit_code == 0
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["prepare-real-run", str(project_dir)]).exit_code == 0

    result = runner.invoke(app, ["check-metric-results", str(project_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "metric result check failed" in result.stdout
    assert "result manifest is missing" in result.stdout
    assert "report: reports/metric_result_check_report.json" in result.stdout
    assert "Traceback" not in result.output
```

- [x] **Step 2: Run failing CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py::test_cli_check_metric_results_passes_for_valid_fake_ocean_results tests/test_cli.py::test_cli_check_metric_results_reports_failure_without_traceback -q
```

Expected: fail because `check-metric-results` command does not exist.

- [x] **Step 3: Add CLI command**

In `src/hermes_workflow/cli.py`, import:

```python
from hermes_workflow.metric_results import check_metric_results
```

Add command after `check_real_run_command`:

```python
@app.command("check-metric-results")
def check_metric_results_command(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Project directory with returned OCEAN metric result artifacts."),
    ],
    run_id: Annotated[
        str | None,
        typer.Option(
            "--run-id",
            help="Real-run package id such as real_001.",
        ),
    ] = None,
) -> None:
    try:
        report = check_metric_results(project_dir, run_id=run_id)
    except (OSError, ValueError) as exc:
        _exit_with_error(exc)
    if report.status.value == "pass":
        typer.echo("metric result check passed")
        typer.echo(f"run: runs/real/{report.run_id}")
        typer.echo("report: reports/metric_result_check_report.json")
        return

    typer.echo("metric result check failed")
    for issue in report.issues:
        typer.echo(issue)
    typer.echo("report: reports/metric_result_check_report.json")
    raise typer.Exit(code=1)
```

- [x] **Step 4: Run CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 5: Commit task**

```bash
git add src/hermes_workflow/cli.py tests/test_cli.py docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "feat: add metric result check cli"
```

## Task 6: Docs, Progress State, and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md`

- [x] **Step 1: Update README usage flow**

Add the C-6 command after `check-real-run` in `README.md`:

```text
hermes-workflow check-real-run /path/to/project
hermes-workflow check-metric-results /path/to/project
```

Add this short rule near the real-run section:

```text
Metric extraction is contract-only in Hermes. The execution agent runs standalone Spectre and batch OCEAN outside Hermes, then writes metric_result_manifest.json. Hermes validates formula identity, scalar values, and artifact paths; Hermes does not parse PSF or reimplement Calculator/OCEAN formulas.
```

- [x] **Step 2: Update project route docs**

In `docs/PROJECT_WORKFLOW_OVERVIEW.md`, extend the workflow route:

```text
prepare-real-run
-> execution agent runs standalone Spectre
-> execution agent runs batch OCEAN with exact approved formulas
-> check-real-run
-> check-metric-results
-> future ledger/optimizer state
```

Add a module bullet:

```text
`metric_results.py`: validates OCEAN scalar metric artifacts against `metric_extraction_request.json` without reading PSF or recomputing formulas.
```

- [x] **Step 3: Update progress and checkpoint docs**

In `docs/EXECUTION_PROGRESS_2026-05-29.md`, add a C-6 section:

```markdown
## Plan C C-6 Spectre + OCEAN Metric Result Contract

Status: complete and reviewed

Implemented:

- `metrics.yaml` can carry exact approved OCEAN formulas.
- `prepare-real-run` writes `metric_extraction_request.json`.
- returned handoff can reference PSF and metric artifacts.
- `check-metric-results` validates formula identity, scalar values, request hashes, and artifact paths.

Still excluded:

- running Spectre from Hermes
- running OCEAN from Hermes
- parsing PSF in Python
- computing Calculator/OCEAN formulas in Python
- optimizer ledger/state updates
```

In `docs/COMPACT_RESUME_CHECKPOINT.md` and `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, set the next action to:

```text
Next: C-7 physical Spectre + OCEAN adapter wiring through the execution-agent/tool boundary, or a focused C-6.5 evidence gate if review feedback asks for it.
```

- [x] **Step 4: Run full verification**

Run:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest -q
git diff --check
```

Expected:

```text
ruff: all checks passed
pytest: all tests pass
git diff --check: no output
```

- [x] **Step 5: Final review gate**

Request one combined C-6 final review gate. The review prompt should include:

```text
Review C-6 Spectre + OCEAN metric result contract implementation. Confirm:
1. Hermes does not run Spectre/OCEAN.
2. Hermes does not parse PSF or reimplement formulas.
3. metrics.yaml approved OCEAN formulas are the only executable formula source.
4. metric_extraction_request.json and metric_result_manifest.json hash/formula/path checks are sufficient.
5. psfxl migration is explicit and does not break completed Plan A/B/C flows.
6. tests cover success, formula drift, request drift, missing/extra metrics, unsafe paths, and non-finite scalars.
```

- [x] **Step 6: Apply review fixes if any**

If review finds issues, apply focused fixes and rerun:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest -q
git diff --check
```

Expected: all pass before marking C-6 complete.

- [ ] **Step 7: Commit docs and final fixes**

```bash
git add README.md \
  docs/PROJECT_WORKFLOW_OVERVIEW.md \
  docs/EXECUTION_PROGRESS_2026-05-29.md \
  docs/COMPACT_RESUME_CHECKPOINT.md \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md
git commit -m "docs: record c6 metric result contract"
```

## Final Acceptance Checklist

- [x] `metrics.yaml` supports exact approved OCEAN formulas and rejects invalid formula policy.
- [x] `spectre.yaml` accepts `psfxl`, and real metric request generation requires an OCEAN-ready format.
- [x] `prepare-real-run` writes `metric_extraction_request.json` and records its SHA-256.
- [x] C-5 handoff accepts safe PSF and metric artifact references.
- [x] `check-metric-results` writes `reports/metric_result_check_report.json`.
- [x] Validator rejects request hash drift, formula text drift, formula hash drift, missing metrics, extra metrics, unsafe paths, non-finite scalars, and simulator-failed handoffs.
- [x] Hermes still does not run Spectre, run OCEAN, parse PSF, evaluate formulas, append ledger rows, or update optimizer state.
- [x] Full test suite and ruff pass.
- [x] C-6 docs/progress/checkpoint files point next development to C-7 physical Spectre + OCEAN adapter or C-6.5 evidence gate.
