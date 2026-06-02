# Spectre + OCEAN Real Metric Result Contract Design

## Goal

Add a Hermes-side contract for real metric extraction results from standalone Spectre plus batch OCEAN, without letting Python or an agent parse PSF data or reimplement ADE/Maestro Calculator formulas.

C-6 turns the validated backend route into deterministic files:

```text
approved real-run package
-> standalone Spectre produces PSF
-> batch OCEAN opens PSF
-> OCEAN evaluates exact approved formulas
-> execution agent writes scalar metric artifacts
-> Hermes validates metric result contract
```

## Problem

C-4 prepares the first real-run package after supervisor approval, and C-5 validates the execution agent's returned simulator handoff. That proves the file boundary around a real run, but it intentionally stops before real metric extraction.

The project now has practical evidence that the intended backend is viable:

- Transient/DC inverter evidence shows batch OCEAN can open point-level Maestro PSF and standalone Spectre replay PSF, then compute matching `rise`, `fall`, and `DC` scalar values.
- PSS/PAC/PNoise mixer evidence shows batch OCEAN can open point-level Maestro PSF and standalone Spectre replay PSF, then compute matching `BW` and `MAX_GAIN` scalar values.
- `drplPacVolGnExpDen` is callable in batch OCEAN in the tested environment, but a hand-written `drpl` candidate was not numerically equivalent to the current `vh` formula. Formula rewriting is therefore forbidden.

The remaining gap is productizing this rule:

```text
Python may invoke OCEAN and record OCEAN-produced scalars.
Python must not parse PSF waveforms.
Python must not reimplement Calculator/OCEAN formulas.
Agents must not rewrite formulas across dialects.
```

C-6 closes that gap with a file contract. It still does not wire the physical adapter; it defines the request and result artifacts that C-7 will later produce with real tools.

## Scope

Included:

- Extend `metrics.yaml` so executable OCEAN formulas are explicit, exact, and user/project-approved.
- Preserve `maestro_formula` as provenance/reference, not as an automatically executable source unless explicitly approved into the OCEAN formula field.
- Add a metric extraction request artifact to the real-run package.
- Add expected PSF/result location fields needed by a future execution agent.
- Define an OCEAN scalar result artifact written by the execution agent after Spectre/OCEAN execution.
- Define a Hermes validator for metric result artifacts.
- Add a CLI command for metric result validation.
- Update C-5 result handoff to reference PSF/result data and metric artifacts safely.
- Replace or extend the historical Plan A `output_format: psfascii` constraint for the confirmed OCEAN backend. Current evidence used `psfxl`.
- Add deterministic unit and CLI tests using sanitized fake artifacts.
- Update project docs and resume state.

Excluded:

- Running Spectre from Hermes.
- Running OCEAN from Hermes.
- Launching shell subprocesses from Hermes.
- Implementing the physical Spectre/OCEAN adapter.
- Auto-discovering formulas from Maestro/ADE and approving them without user review.
- Parsing PSF, PSFXL, PSF ASCII, raw, SST2, or other simulator databases in Python.
- Recomputing calculator functions in Python.
- Rewriting formulas between `vh`, `v`, `VT`, `drpl*`, or any other dialect.
- Evaluating optimizer objective or constraints from real metrics.
- Appending production ledger rows.
- Updating optimizer state or best-candidate state.
- Multi-candidate, sweep, family, or corner aggregation. C-6 is single point only.

## Current Route

C-6 sits after C-5 and before the physical adapter:

```text
Hermes prepare-real-run
-> runs/real/real_001/input.scs
-> runs/real/real_001/metric_extraction_request.json
-> execution agent runs standalone Spectre outside Hermes
-> execution agent runs batch OCEAN outside Hermes
-> execution agent writes metric_result_manifest.json and scalar artifacts
-> Hermes check-metric-results
-> reports/metric_result_check_report.json
-> future optimizer/ledger consumes validated scalar metrics
```

The validator checks identity, hashes, paths, formula text, formula hashes, scalar presence, units, and failure states. It does not inspect PSF contents and does not evaluate formulas.

## Responsibility Split

Hermes owns:

- Schema validation for `metrics.yaml` and `spectre.yaml`.
- Generation of `metric_extraction_request.json`.
- Stable hashes for formulas, request files, rendered input deck, and immutable configs.
- Validation of returned metric result artifacts.
- `reports/metric_result_check_report.json`.

The execution agent owns:

- Running standalone Spectre only after C-4 approval/package creation.
- Running batch OCEAN with the exact formulas from the request.
- Writing OCEAN logs, scalar output files, and `metric_result_manifest.json`.
- Preserving prepared package inputs.
- Reporting failures as structured files rather than chat prose.

Hermes does not trust:

- The execution agent's prose.
- A formula that differs from `metrics.yaml`.
- A metric value without matching formula hash and request hash.
- A path outside `runs/real/<run_id>/`.

## Metrics YAML Contract

The first Plan A schema used:

```yaml
metrics:
  - name: rise
    unit: ps
    maestro_formula: riseTime(...)
    required_signals:
      - /VOUT
```

C-6 should extend each metric with an explicit executable formula block:

```yaml
metrics:
  - name: rise
    unit: s
    required_signals:
      - /VOUT
    maestro_formula: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
    ocean:
      expression: riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")
      result: tran
      expression_source: user_approved
      source_reference: maestro_output:rise
      expected_value_type: real_scalar
      nil_policy: fail
      non_finite_policy: fail
```

Rules:

- `ocean.expression` is the executable formula. It must be exact and approved.
- `maestro_formula` remains a trace/reference field.
- `ocean.expression_source` is one of:
  - `user_approved`
  - `maestro_output_approved`
  - `direct_plot_approved`
- Agent-discovered formulas may be written only after approval. Discovery alone is not approval.
- `ocean.result` is the OCEAN result/analysis selector, for example `tran`, `dc`, `ac`, `pac`, `pnoise`, `pss_td`, `pss_fd`, or `stb`.
- `expected_value_type` is `real_scalar` for C-6.
- `nil_policy` must be `fail` for C-6.
- `non_finite_policy` must be `fail` for C-6.
- `unit` is a project-contract label. C-6 does not convert units. The approved formula must return values in the declared unit.
- Formula text must not contain unresolved template placeholders such as `{{FN}}`.

This shape deliberately avoids a generic Calculator parser. Hermes validates the presence and identity of the formula string. OCEAN evaluates it later.

## Spectre Output Format Contract

The historical Plan A schema constrained:

```yaml
spectre:
  output_format: psfascii
```

That was tied to an early Python parser-oriented route. It is not the final policy for real metric extraction.

C-6 should support the confirmed OCEAN backend with:

```yaml
spectre:
  output_format: psfxl
```

Implementation guidance:

- Extend `SpectreSettings.output_format` to allow at least `psfxl`.
- Keep `psfascii` only if needed for historical fixtures or non-OCEAN dry-run compatibility.
- Require `psfxl` when generating a Spectre + OCEAN metric extraction request unless a later evidence pass proves another format is equally supported.
- Record the output format in both `real_run_manifest.json` and `metric_extraction_request.json`.

Current evidence used:

```text
spectre -64 input.scs ... -format psfxl -raw <psf_dir>
ocean -nograph -replay <probe.ocn> -log <probe.log>
```

## Metric Extraction Request Contract

Hermes writes:

```text
runs/real/<run_id>/metric_extraction_request.json
```

This file is created by `prepare-real-run` or a focused C-6 helper invoked from it. The request is the only formula source the execution agent may use.

Shape:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "backend": "spectre_ocean_batch",
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "prepared_input_sha256": "<sha256>",
  "expected_psf_dir": "runs/real/real_001/psf",
  "spectre": {
    "engine": "spectre_x",
    "preset": "ax",
    "output_format": "psfxl",
    "timeout_s": 3600
  },
  "ocean": {
    "mode": "nograph_replay",
    "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
    "log_file": "runs/real/real_001/metrics/ocean.log",
    "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv"
  },
  "metrics": [
    {
      "name": "rise",
      "unit": "s",
      "required_signals": ["/VOUT"],
      "result": "tran",
      "expression": "riseTime(VT(\"/VOUT\") 0 nil 0.9 nil 10 90 nil \"time\")",
      "expression_sha256": "<sha256 of exact expression text>",
      "expression_source": "user_approved",
      "source_reference": "maestro_output:rise",
      "expected_value_type": "real_scalar",
      "nil_policy": "fail",
      "non_finite_policy": "fail"
    }
  ],
  "forbidden_actions": [
    "rewrite_metric_formula",
    "parse_psf_in_python",
    "modify_prepared_input_scs",
    "modify_immutable_config_files",
    "write_results_outside_run_dir"
  ]
}
```

Rules:

- All paths are project-relative POSIX paths.
- All paths must stay under `runs/real/<run_id>/`, except `prepared_input_scs`, which must match the C-4 manifest path.
- `expected_psf_dir` is a contract hint for the future Spectre runner. C-6 does not require the directory to exist at request creation time.
- `expression_sha256` is computed over the exact UTF-8 expression text.
- The request file hash should be recorded in `real_run_manifest.json`.
- If `spectre.output_format` is not OCEAN-ready, request generation fails.

## Real-Run Manifest Extension

C-4 currently writes:

```text
runs/real/<run_id>/real_run_manifest.json
```

C-6 should add:

```json
{
  "metric_extraction_request": "runs/real/real_001/metric_extraction_request.json",
  "metric_extraction_request_sha256": "<sha256>"
}
```

The manifest remains status `prepared`. Adding a request file does not mean Spectre or OCEAN has run.

## Result Manifest Extension

C-5 currently validates:

```text
runs/real/<run_id>/result_manifest.json
```

C-6 should extend it to let the execution agent declare result data and metric artifacts:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "status": "succeeded",
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "prepared_input_sha256": "<sha256>",
  "result_data": {
    "kind": "spectre_psf",
    "psf_dir": "runs/real/real_001/psf",
    "spectre_out": "runs/real/real_001/psf/spectre.out"
  },
  "metric_result_manifest": "runs/real/real_001/metrics/metric_result_manifest.json",
  "log_file": "runs/real/real_001/spectre.log",
  "artifact_files": [
    "runs/real/real_001/psf/spectre.out",
    "runs/real/real_001/metrics/ocean.log",
    "runs/real/real_001/metrics/ocean_scalars.tsv"
  ]
}
```

Rules:

- `result_data` is required only when `status` is `succeeded`.
- If `status` is `failed`, metric artifacts may be absent, but the failure must still be represented by a valid C-5 handoff.
- `psf_dir`, `spectre_out`, and `metric_result_manifest` must be project-relative and under `runs/real/<run_id>/`.
- C-5 path safety rules continue to apply.

## Metric Result Manifest Contract

The execution agent writes:

```text
runs/real/<run_id>/metrics/metric_result_manifest.json
```

Shape:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "backend": "spectre_ocean_batch",
  "status": "succeeded",
  "request_file": "runs/real/real_001/metric_extraction_request.json",
  "request_sha256": "<sha256>",
  "psf_dir": "runs/real/real_001/psf",
  "ocean": {
    "mode": "nograph_replay",
    "return_code": 0,
    "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
    "script_sha256": "<sha256>",
    "log_file": "runs/real/real_001/metrics/ocean.log",
    "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv"
  },
  "metrics": [
    {
      "name": "rise",
      "status": "succeeded",
      "value": 7.520168e-11,
      "value_text": "7.520168e-11",
      "unit": "s",
      "result": "tran",
      "expression": "riseTime(VT(\"/VOUT\") 0 nil 0.9 nil 10 90 nil \"time\")",
      "expression_sha256": "<sha256>",
      "expression_source": "user_approved",
      "issues": []
    }
  ],
  "issues": []
}
```

Allowed top-level `status` values:

- `succeeded`
- `failed`

Allowed per-metric `status` values:

- `succeeded`
- `failed`

Rules:

- Top-level `status: "succeeded"` requires every configured metric to have per-metric `status: "succeeded"`.
- Top-level `status: "failed"` is valid returned data if the manifest is well formed and includes issues.
- A succeeded metric requires a finite JSON number in `value`.
- `value_text` records the original OCEAN scalar text, for traceability.
- `unit`, `result`, `expression`, `expression_sha256`, and `expression_source` must match the request for the metric name.
- Extra metrics not present in the request are validation failures.
- Missing requested metrics are validation failures.
- `nil`, `NaN`, `Inf`, `-Inf`, waveform object strings, and empty strings are failures for C-6.
- The validator does not compare metric values against constraints or objectives.

## Scalar Output File Contract

The OCEAN scalar output file is an execution artifact:

```text
runs/real/<run_id>/metrics/ocean_scalars.tsv
```

C-6 should treat `metric_result_manifest.json` as the canonical machine-readable result. The TSV is supporting evidence produced by OCEAN or by the future adapter's OCEAN wrapper.

Recommended TSV columns:

```text
metric	status	value_text	unit	expression_sha256	issue
rise	succeeded	7.520168e-11	s	<sha256>
```

Rules:

- C-6 validator only verifies that the scalar output file exists when declared.
- C-6 does not need to parse TSV if the JSON manifest is complete.
- C-7 may parse this TSV to build the JSON manifest, but it must not parse PSF or compute waveform-derived values.

## Validation Architecture

Add a focused module:

```text
src/hermes_workflow/metric_results.py
```

Public API:

```python
check_metric_results(project_dir: Path, *, run_id: str | None = None) -> MetricResultCheckReport
```

`run_id` defaults to `real_001` and follows the existing `real_[0-9]{3}` pattern.

The implementation should:

1. Validate and load the project bundle with `assert_valid_project(project_dir)`.
2. Resolve `runs/real/<run_id>/`.
3. Load `real_run_manifest.json`.
4. Load `metric_extraction_request.json`.
5. Load `result_manifest.json`.
6. Require `result_manifest.status == "succeeded"` before metric validation. If the simulator failed, write a metric report with status `fail` and issue `simulator result is not succeeded`.
7. Load `metric_result_manifest.json`.
8. Validate all paths are project-relative and under the run directory.
9. Verify request hash matches `metric_result_manifest.request_sha256`.
10. Verify `run_id`, `candidate_id`, `prepared_input_scs`, and PSF directory references are consistent.
11. Verify every requested metric appears exactly once.
12. Verify no unrequested metric appears.
13. Verify formula text and formula hashes match the request.
14. Verify units, result selectors, expression sources, and metric statuses.
15. Verify succeeded metric values are finite real numbers.
16. Write `reports/metric_result_check_report.json`.
17. Return the report model.

The validator should always write a report when the project config and run directory can be loaded. If project config cannot be loaded, the CLI may surface the existing domain error without fabricating a report, following current CLI patterns.

## Metric Result Check Report

Hermes writes:

```text
reports/metric_result_check_report.json
```

Successful report:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "backend": "spectre_ocean_batch",
  "request_file": "runs/real/real_001/metric_extraction_request.json",
  "metric_result_manifest": "runs/real/real_001/metrics/metric_result_manifest.json",
  "psf_dir": "runs/real/real_001/psf",
  "metrics": {
    "rise": {
      "status": "succeeded",
      "value": 7.520168e-11,
      "value_text": "7.520168e-11",
      "unit": "s",
      "expression_sha256": "<sha256>"
    }
  },
  "checks": {
    "request_hash_ok": true,
    "result_manifest_ok": true,
    "metric_manifest_ok": true,
    "metric_identity_ok": true,
    "formula_hashes_ok": true,
    "scalar_values_ok": true,
    "artifact_paths_ok": true
  },
  "issues": []
}
```

Failure report:

```json
{
  "schema_version": "1.0",
  "status": "fail",
  "run_id": "real_001",
  "candidate_id": null,
  "backend": null,
  "request_file": "runs/real/real_001/metric_extraction_request.json",
  "metric_result_manifest": "runs/real/real_001/metrics/metric_result_manifest.json",
  "psf_dir": null,
  "metrics": {},
  "checks": {
    "request_hash_ok": false,
    "result_manifest_ok": false,
    "metric_manifest_ok": false,
    "metric_identity_ok": false,
    "formula_hashes_ok": false,
    "scalar_values_ok": false,
    "artifact_paths_ok": false
  },
  "issues": [
    "metric result manifest is missing"
  ]
}
```

## CLI Contract

Add:

```text
hermes-workflow check-metric-results PROJECT_DIR [--run-id real_001]
```

Success output:

```text
metric result check passed
run: runs/real/real_001
metrics: reports/metric_result_check_report.json
```

Failure output:

```text
metric result check failed
<issue line 1>
<issue line 2>
report: reports/metric_result_check_report.json
```

Exit codes:

- `0` when the metric result contract passes.
- `1` when the report is written with `status: "fail"` or a domain error occurs.

## Failure Surface

C-6 must fail closed for:

- Missing `metric_extraction_request.json`.
- Missing or malformed `metric_result_manifest.json`.
- Metric result manifest outside the run directory.
- Unsafe paths, absolute paths, or paths containing `..`.
- Request hash mismatch.
- Run ID or candidate ID mismatch.
- Simulator result not succeeded.
- Missing PSF directory declaration.
- Missing declared OCEAN log or scalar output file.
- Missing requested metric.
- Extra unrequested metric.
- Formula text mismatch.
- Formula hash mismatch.
- Unit mismatch.
- Result selector mismatch.
- `nil` metric result.
- `NaN`, `Inf`, or `-Inf` metric result.
- Waveform object text where a scalar was expected.
- Per-metric failure with top-level `status: "succeeded"`.

## Formula Authority Rules

These rules are non-negotiable for C-6:

- `metrics.yaml` is the authority after user/project approval.
- Maestro/ADE/Direct Plot formula discovery is useful only to draft or audit `metrics.yaml`.
- No agent may silently replace `vh(...)` with `drpl...`, `VT(...)` with `v(...)`, or any equivalent-looking expression.
- If the approved formula is a Direct Plot helper expression, evaluate that exact expression.
- If the approved formula is a `vh(...)` expression, evaluate that exact expression.
- If an OCEAN function is unavailable or returns `nil`, the metric fails. The workflow must not fall back to Python computation.

## Test Strategy

Use sanitized fixtures only. Do not commit real `input.scs`, PSF, Spectre logs, or proprietary simulator outputs.

Unit tests should cover:

- Valid `metrics.yaml` with executable `ocean` formula blocks.
- Missing `ocean.expression` rejected.
- Unsupported `expected_value_type` rejected.
- `spectre.output_format: psfxl` accepted.
- OCEAN metric request generation writes exact formula and formula hash.
- Request generation rejects non-OCEAN-ready output format.
- `real_run_manifest.json` includes metric request path and hash.
- Valid metric result manifest passes.
- Request hash mismatch fails.
- Formula text mismatch fails.
- Formula hash mismatch fails.
- Missing metric fails.
- Extra metric fails.
- `nil`/`NaN`/`Inf`/waveform-looking values fail.
- Unsafe metric artifact path fails.
- Simulator failed result blocks metric validation.

CLI tests should cover:

- `prepare-real-run` writes `metric_extraction_request.json`.
- `check-metric-results` exits `0` and writes a pass report for valid fake OCEAN scalar results.
- `check-metric-results` exits `1` and writes a fail report for formula mismatch.
- `check-metric-results` exits `1` and writes a fail report for missing metric artifacts.

## Documentation Updates

C-6 implementation should update:

- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- The top-level broad plan if implementation changes scope or naming.

The docs must preserve the validated route:

```text
standalone Spectre
-> batch OCEAN
-> exact approved formula
-> scalar metric artifacts
-> Hermes validation
```

## Open Decisions Deferred To C-7 Or Later

- Exact shell command generation for Spectre and OCEAN.
- Whether `virtuoso-bridge-lite` exposes a first-class OCEAN adapter or Hermes writes a run script for the execution agent.
- Whether OCEAN scripts are generated by Hermes or by the external adapter from the request JSON.
- Real sweep/family/corner metric aggregation.
- Comparison against Maestro/ADE golden values for every production project.
- Ledger append and optimizer-state update from checked metrics.
- Multi-candidate batching and concurrency.

## Acceptance Criteria

C-6 is complete when:

- The design and implementation plan define a deterministic contract for OCEAN-backed scalar metric extraction.
- `metrics.yaml` can carry exact approved executable OCEAN formulas.
- A prepared real-run package carries a metric extraction request with formula hashes.
- A returned metric result manifest can be validated without running Spectre/OCEAN.
- The validator rejects formula drift, path drift, missing metrics, extra metrics, non-finite scalars, and unsafe artifacts.
- Python still does not parse PSF and does not compute Calculator/OCEAN metrics.
- Tests and docs make the `psfascii` to OCEAN-readable PSF transition explicit.
