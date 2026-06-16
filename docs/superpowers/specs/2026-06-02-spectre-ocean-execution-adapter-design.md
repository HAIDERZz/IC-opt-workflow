# Spectre + OCEAN Execution Adapter Design

Date: 2026-06-02

## Goal

Add the C-7 execution-side adapter that consumes the already-approved C-4/C-6 real-run package, runs standalone Spectre, runs batch OCEAN with the exact approved formulas from `metric_extraction_request.json`, and writes the C-5/C-6 result artifacts that Hermes workflow tooling already validates.

C-7 is the first production-oriented bridge from file contracts to real Cadence tools:

```text
Hermes workflow tooling approve
-> Hermes workflow tooling prepare-real-run
-> execution agent invokes C-7 adapter
-> standalone Spectre produces PSF
-> batch OCEAN evaluates exact approved formulas
-> adapter writes result_manifest.json and metric_result_manifest.json
-> Hermes workflow tooling check-real-run
-> Hermes workflow tooling check-metric-results
```

The important boundary remains unchanged: the supervisor agent owns planning and decisions, Hermes workflow tooling owns deterministic contracts and validation, and the execution agent/tool adapter owns physical tool execution.

## Background

Plan C has deliberately built the real-run path in layers:

- C-4 creates the post-approval real-run package and renders `runs/real/<run_id>/input.scs`.
- C-5 validates a returned `result_manifest.json`.
- C-5.5 simulated the execution-agent/Hermes handoff and showed that Hermes must trust files and reports, not chat prose.
- Spectre + OCEAN toolchain evidence confirmed that standalone Spectre replay PSF can be opened by batch OCEAN and can produce scalar values matching Maestro point-level PSF for transient/DC and PSS/PAC/PNoise examples.
- C-6 added the authoritative metric request/result contract: `metrics.yaml` contains exact approved OCEAN formulas, `prepare-real-run` writes `metric_extraction_request.json`, and `check-metric-results` validates returned scalar artifacts without reading PSF or recomputing formulas.

C-7 should now wire a real adapter while preserving all of those boundaries. It must not turn Hermes into an unchecked simulator runner.

## Locked Role Model

C-7 follows the role model locked in `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

Use these meanings throughout C-7:

- `supervisor agent`: the planning and decision-making agent. It uses Hermes workflow tooling, reads reports, approves or rejects workflow progression, and must not run Spectre/OCEAN directly.
- `Hermes workflow tooling`: the deterministic file-contract and validation layer in this repository. It is not a local LLM agent and is not the physical simulator runner.
- `execution agent`: the tool-side agent that operates Virtuoso/Spectre/OCEAN through approved package and adapter boundaries.
- `execution-side adapter`: the C-7 tool entry point called by the execution agent after `prepare-real-run`.

Older project discussions sometimes used "Hermes" to mean a local supervisor agent and "Claude CLI" to mean the execution agent. That terminology is no longer authoritative. Claude CLI may still be one possible worker implementation, but the locked role name is `execution agent`.

## Non-Negotiable Rules

- Do not parse PSF, PSFXL, raw, SST2, or waveform databases in Python.
- Do not translate, simplify, normalize, or rewrite OCEAN/Calculator formulas.
- Do not infer formulas from Maestro/ADE output during execution. Formula discovery is allowed only as a separate draft/audit step before project approval.
- Do not trust an execution agent's prose as evidence of success.
- Do not accept scalar values without matching request hash, formula text, formula hash, prepared input hash, run id, artifact paths, and finite numeric policy.
- Do not copy proprietary `input.scs`, PSF data, simulator logs, or local toolchain evidence into repository fixtures.
- Do not run real Spectre or OCEAN in unit tests or normal CI.

## Scope

Included:

- Define an execution-side adapter interface for running one approved real-run package.
- Read `runs/real/<run_id>/real_run_manifest.json` and `runs/real/<run_id>/metric_extraction_request.json`.
- Verify local preconditions before invoking tools.
- Build the standalone Spectre command from the prepared deck and C-6 request contract.
- Generate an OCEAN replay script from exact approved request formulas.
- Run `ocean -nograph` or the configured batch OCEAN invocation.
- Capture command status, logs, stdout/stderr summaries, artifact hashes, and timestamps.
- Write C-5 `result_manifest.json`.
- Write C-6 `metrics/metric_result_manifest.json`.
- Write `metrics/ocean_scalars.tsv` as the machine-readable scalar output consumed by the metric result manifest.
- Provide an injectable command runner so unit tests use fake commands and fake files.
- Provide a local-only smoke path for manually validating the adapter against real Cadence tools.

Excluded:

- Changing C-4 approval semantics.
- Changing C-6 formula approval semantics.
- Adding optimizer ledger append or optimizer state updates.
- Supporting multiple candidates in one adapter invocation.
- Supporting multi-corner, sweep, or family aggregation.
- Supporting Maestro-managed optimization loops.
- Implementing formula discovery from Maestro/ADE.
- Running real tools inside Hermes validators.
- Making real Cadence tool availability a test-suite requirement.

## Position In The Workflow

C-7 sits after `prepare-real-run` and before existing Hermes checks:

```text
config/*.yaml
-> hermes-workflow validate
-> hermes-workflow prepare-netlist
-> hermes-workflow dry-run
-> hermes-workflow preflight-health
-> hermes-workflow approve --decision approve
-> hermes-workflow prepare-real-run
-> C-7 execution adapter
-> hermes-workflow check-real-run
-> hermes-workflow check-metric-results
-> future ledger/state update
```

The adapter is not part of deterministic preflight. It is allowed to run physical tools only because the approval package already exists.

## Adapter Ownership

The adapter is an execution-side tool packaged with this repository for reproducibility, but conceptually it belongs to the execution agent boundary.

Recommended implementation shape:

```text
src/hermes_workflow/execution_adapters/spectre_ocean.py
tools/run_spectre_ocean_adapter.py
tests/test_spectre_ocean_adapter.py
```

The module should be library-style and testable. The script under `tools/` should be the entry point an execution agent calls. Keeping the entry point under `tools/` makes the boundary visible: this is not a Hermes validation command and should not be invoked by `validate`, `dry-run`, `preflight-health`, `approve`, `prepare-real-run`, `check-real-run`, or `check-metric-results`.

A future implementation may add a dedicated console script, but the first C-7 version should keep the entry point explicit and boring:

```bash
python tools/run_spectre_ocean_adapter.py PROJECT_DIR --run-id real_001
```

## Inputs

The adapter consumes only prepared project artifacts.

Required files:

```text
runs/real/<run_id>/input.scs
runs/real/<run_id>/candidate.json
runs/real/<run_id>/real_run_manifest.json
runs/real/<run_id>/metric_extraction_request.json
```

Optional configuration sources:

```text
.env
config/spectre.yaml
config/project_config.yaml
```

The `.env` file may supply local tool setup values such as:

```text
VB_CADENCE_CSHRC=/home/zzchen/cadence_ic231_env.csh
```

The adapter should treat `.env` as an execution environment helper, not as a source of project truth. Project truth remains in the YAML files and generated real-run package.

## Preconditions

Before invoking Spectre or OCEAN, the adapter must fail closed if:

- The real-run directory is missing.
- `real_run_manifest.json` is missing or malformed.
- `metric_extraction_request.json` is missing or malformed.
- The manifest run id and request run id do not match the requested run id.
- The prepared `input.scs` path escapes `runs/real/<run_id>/`.
- The `input.scs` SHA-256 differs from the manifest/request hash.
- `metric_extraction_request.json` has a backend other than `spectre_ocean_batch`.
- The requested output format is not `psfxl`.
- Any metric lacks an expression, result selector, expected scalar policy, or expression hash.
- A declared formula hash does not match the expression text.
- The destination PSF, metrics, or log paths escape `runs/real/<run_id>/`.
- A previous successful result already exists and overwrite was not explicitly requested.

These checks are adapter preflight checks. Hermes will still validate returned files afterward.

## Spectre Invocation

The adapter should build the Spectre invocation from the request and configuration, with no formula knowledge involved.

Baseline command shape from toolchain evidence:

```text
spectre -64 <input.scs> -format psfxl -raw <psf_dir>
```

The implementation may include additional safe arguments from `config/spectre.yaml`, such as timeout policy, engine/preset mapping, or log path, only if they are already represented in project contracts.

C-7 should record:

- command argv after environment resolution
- working directory
- start time
- end time
- duration
- exit code
- stdout path or captured summary
- stderr path or captured summary
- primary `spectre.out` or log path
- PSF/result directory path
- hashes for stable text artifacts

The adapter should not parse Spectre waveforms. It may inspect file existence and hash text logs.

## OCEAN Replay Generation

The adapter should generate an OCEAN replay script under:

```text
runs/real/<run_id>/metrics/metric_probe.ocn
```

The generated script must:

- Open the Spectre result directory from the request or Spectre run output.
- Select each metric's requested OCEAN result/analysis.
- Evaluate the exact formula string from `metric_extraction_request.json`.
- Write one scalar row per metric to `metrics/ocean_scalars.tsv`.
- Fail closed on `nil`, non-finite values, missing signals, missing analyses, unsupported functions, or expression errors.
- Emit enough structured markers for the Python adapter to distinguish tool failure from scalar failure.

The generated script must not:

- Rewrite formulas.
- Replace `vh` with `v`, `VT`, or `drpl*`.
- Replace `drpl*` with another expression.
- Insert derived Python-calculated values.
- Depend on GUI-only state.

Approved formulas are executed exactly as OCEAN/SKILL expressions. If a formula fails in OCEAN, the adapter records a failed metric result. It does not attempt repair.

## Scalar Output Format

The scalar output file should be TSV for easy inspection and deterministic parsing:

```text
metric	value	unit	status	expression_sha256	message
rise	1.234e-10	s	pass	<sha256>	<empty>
fall	1.456e-10	s	pass	<sha256>	<empty>
DC	3.210e-04	A	pass	<sha256>	<empty>
```

Rules:

- Header is required.
- Exactly one row per requested metric is required.
- `metric` must match the request metric name.
- `value` must be a real finite scalar for pass rows.
- `unit` must match the request unit.
- `status` is `pass` or `fail`.
- `expression_sha256` must match the request formula hash.
- `message` contains a short failure explanation for failed rows.

The adapter may parse only this scalar text output and OCEAN process status. It may not parse PSF data.

## Metric Result Manifest

The adapter writes:

```text
runs/real/<run_id>/metrics/metric_result_manifest.json
```

The manifest must satisfy the C-6 checker. It should include:

- schema version
- run id
- backend `spectre_ocean_batch`
- metric extraction request path
- metric extraction request SHA-256
- prepared input path
- prepared input SHA-256
- PSF/result data path
- OCEAN script path
- OCEAN log path
- scalar output path
- Spectre status block
- OCEAN status block
- metric result entries with formula text/hash, scalar value, unit, status, and provenance

The adapter should generate the manifest even on failure when enough context exists to do so. Failure manifests let Hermes produce deterministic reports instead of relying on terminal output.

## Result Handoff Manifest

The adapter also writes or updates:

```text
runs/real/<run_id>/result_manifest.json
```

This manifest should satisfy the C-5 checker and reference:

- prepared input deck
- candidate
- Spectre log/status artifacts
- result data directory
- metric result manifest

If Spectre fails before PSF creation, the adapter should still write a failed result manifest with the available logs and a clear status. If OCEAN fails after Spectre succeeds, the result manifest should show simulator success but metric extraction failure through the metric manifest.

## Failure Model

The adapter should fail closed and preserve evidence.

Expected failure categories:

- `precondition_failed`
- `spectre_command_failed`
- `spectre_timeout`
- `spectre_missing_result`
- `ocean_script_generation_failed`
- `ocean_command_failed`
- `ocean_timeout`
- `ocean_metric_failed`
- `scalar_output_malformed`
- `artifact_write_failed`

For each failure, write:

- a stable machine-readable status
- a concise human-readable message
- relevant log paths
- command exit code when available
- no stack traces in user-facing artifacts

Python exceptions are acceptable internally, but the tool entry point should convert expected failures into structured output and a non-zero exit code.

## Path And Write Safety

The adapter may write only under:

```text
runs/real/<run_id>/
```

Allowed generated paths:

```text
runs/real/<run_id>/psf/
runs/real/<run_id>/spectre.out
runs/real/<run_id>/spectre.stdout
runs/real/<run_id>/spectre.stderr
runs/real/<run_id>/result_manifest.json
runs/real/<run_id>/metrics/
runs/real/<run_id>/metrics/metric_probe.ocn
runs/real/<run_id>/metrics/ocean.log
runs/real/<run_id>/metrics/ocean.stdout
runs/real/<run_id>/metrics/ocean.stderr
runs/real/<run_id>/metrics/ocean_scalars.tsv
runs/real/<run_id>/metrics/metric_result_manifest.json
```

The adapter must reject:

- absolute project artifact paths inside request files
- `..` path segments
- symlink escapes where detectable
- writes outside the project directory
- writes outside the selected run directory
- unexpected overwrite of existing successful results

## Environment And Tool Invocation

C-7 should support local execution first. SSH or `virtuoso-bridge-lite` mediated execution can be added after the local adapter has a stable contract.

Environment resolution should be explicit:

```text
load project .env
-> read VB_CADENCE_CSHRC if present
-> run commands through a csh/bash wrapper that sources the Cadence environment
-> invoke spectre/ocean with resolved argv
```

The exact wrapper can be chosen in the implementation plan. The design requirement is that the adapter records how the tool environment was selected, without storing secrets.

The first version should not require a running Virtuoso GUI or bridge daemon. The confirmed backend is standalone Spectre plus batch OCEAN.

## Testing Strategy

Unit tests:

- Use a fake command runner.
- Use tiny fake input files under `tmp_path`.
- Simulate Spectre success/failure by creating or omitting fake PSF directories and logs.
- Simulate OCEAN success/failure by writing fake `ocean_scalars.tsv`.
- Assert generated OCEAN script preserves formula strings exactly.
- Assert request hash and formula hash checks happen before command execution.
- Assert unsafe paths fail before command execution.
- Assert success produces both `result_manifest.json` and `metric_result_manifest.json`.
- Assert failed Spectre/OCEAN runs produce structured failure artifacts when possible.

No unit test should invoke real `spectre`, real `ocean`, real Virtuoso, `ssh`, or `virtuoso-bridge-lite`.

Local-only smoke tests:

- May be documented under `docs/toolchain_evidence/`.
- May be run manually against the already validated inverter and mixer examples.
- Must not commit proprietary simulator output, PSF data, or unsanitized netlists.
- Should record only concise summaries, commands, hashes, and sanitized observations.

## Review And Gate Strategy

C-7 is high risk because it introduces physical tool execution and file writes. Use the stricter gate style:

- Task 1 adapter precondition/schema loader: code-quality review after local tests.
- Task 2 OCEAN replay script generation: code-quality review after local tests, with formula-preservation focus.
- Task 3 fake-runner execution orchestration and artifact writing: code-quality review after local tests.
- Task 4 CLI/tool entry point and docs: local tests plus combined final review.

If implementation is split more finely, any task that changes command invocation, path writes, overwrite policy, or formula handling gets its own review gate.

## Acceptance Criteria

C-7 is complete when:

- An execution-side adapter can consume a C-6 real-run package.
- The adapter can run with a fake command runner in tests and produce C-5/C-6-compatible artifacts.
- The generated OCEAN script preserves exact formula text from `metric_extraction_request.json`.
- The adapter rejects request drift, formula hash drift, unsafe paths, non-`psfxl` real metric requests, and unexpected overwrite cases.
- Successful fake execution passes both existing Hermes checks:

```bash
hermes-workflow check-real-run PROJECT_DIR
hermes-workflow check-metric-results PROJECT_DIR
```

- Full local verification passes:

```bash
pytest -q
ruff check src tests tools
git diff --check
```

- No real Cadence tools are required for automated tests.
- Documentation records how to run a local-only real Cadence smoke test separately.

## Deferred Work

- Real optimizer ledger append and state update.
- Multi-candidate batch execution.
- Multi-corner and sweep/family metric aggregation.
- SSH/remote execution profile hardening.
- `virtuoso-bridge-lite` daemon integration for managed execution.
- Formula discovery and approval workflow.
- Production log redaction policy for proprietary simulator output.
- Parallel execution scheduling and license-aware queueing.

## Next Step

Write the C-7 implementation plan around a fake-runner-first adapter. The first implementation should prove the boundary in deterministic tests before any manual local Spectre/OCEAN smoke is attempted.
