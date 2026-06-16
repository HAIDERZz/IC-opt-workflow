# Fix-Run Simulation Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `fix_run` workflow that runs user-specified design points through the existing real Spectre/OCEAN flow and archives scalar metrics, waveform CSV exports, command traces, and manifests without entering optimizer logic.

**Architecture:** Add a requirement-driven workflow mode and a thin `fix_run_flow` orchestration layer. Reuse existing `CandidateInjectionRequest`, `runs/real/real_NNN` artifact layout, local/remote Spectre/OCEAN adapters, process corner expansion, doctor/license gates, and aggregation code. Extend the metric request/OCEAN replay path with waveform export artifacts while leaving scalar metrics and optimizer paths unchanged.

**Tech Stack:** Python, Pydantic, Typer, pytest, ruff, Spectre/OCEAN, existing Hermes workflow modules.

## File Structure

- Create `src/hermes_workflow/fix_run_models.py` for Pydantic models that are specific to `Workflow`, `Fixed Points`, `Waveform Exports`, and fix-run reports.
- Create `src/hermes_workflow/fix_run_flow.py` for local orchestration of fixed points through existing real-run and Spectre/OCEAN paths.
- Create `src/hermes_workflow/remote_fix_run_flow.py` for remote orchestration, using existing remote doctor and remote Spectre/OCEAN execution.
- Modify `src/hermes_workflow/requirement_intake.py` to parse sections by workflow mode.
- Modify `src/hermes_workflow/metric_requests.py` to carry waveform export requests into metric extraction requests.
- Modify `src/hermes_workflow/metric_results.py` to validate waveform export manifests.
- Modify `src/hermes_workflow/execution_adapters/spectre_ocean.py` to render and persist waveform CSV exports.
- Modify `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py` to upload/download waveform export artifacts.
- Modify `src/hermes_workflow/product_cli.py` so `--real` dispatches to fix-run when `Workflow.mode: fix_run`.
- Modify `src/hermes_workflow/schemas.py` only if shared schema types are needed by existing config rendering.
- Add tests under `tests/` for intake, flow dispatch, OCEAN script rendering, local adapter manifests, remote adapter downloads, and product CLI behavior.
- Add docs and examples under `docs/` and `examples/spectre_maestro_project/`.

## Task 1: Add Fix-Run Models

**Files:**

- Create: `src/hermes_workflow/fix_run_models.py`
- Test: `tests/test_fix_run_models.py`

**Step 1: Write failing model tests**

Add tests for:

- `WorkflowSettings(schema_version="1.0", mode="fix_run", starting_run_id="real_001")` passes.
- Missing `starting_run_id` defaults to `real_001`.
- `starting_run_id="fix_001"` fails because the first version reuses `real_NNN`.
- `FixedPoint(candidate_id="user_point_001", parameters={"w_m1": "8u"})` passes.
- `FixedPoint(candidate_id="../bad", parameters={"w_m1": "8u"})` fails.
- `WaveformExport(name="nf_pnoise", testbench="cg_nf", expression='getData("NF" ?result "pnoise")', output_format="csv", nil_policy="fail")` passes.
- `WaveformExport(..., output_format="psfascii")` fails.
- A waveform expression containing `outfile(` fails.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_models.py -q
```

Expected: FAIL because the module does not exist.

**Step 2: Implement the models**

In `fix_run_models.py`, define:

- `WorkflowMode = Literal["optimize", "fix_run"]`
- `WorkflowSettings`
- `FixedPoint`
- `FixedPointsConfig`
- `WaveformExport`
- `WaveformExportsConfig`
- `FixRunPointReport`
- `FixRunReport`

Reuse existing validation helpers where available:

- safe candidate id rule from `real_run.py`
- safe name validation from `schemas.py`
- run id validation compatible with `real_run.RUN_ID_RE`

**Step 3: Run model tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_models.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/fix_run_models.py tests/test_fix_run_models.py
git commit -m "feat: add fix-run config models"
```

## Task 2: Make Requirement Intake Workflow-Aware

**Files:**

- Modify: `src/hermes_workflow/requirement_intake.py`
- Test: `tests/test_requirement_intake.py`
- Test: `tests/test_requirement_intake_fix_run.py`

**Step 1: Write failing intake tests**

Add tests for:

- A valid `fix_run` requirement without `Optimizer Settings`, `Objective`, or `Constraints` passes.
- A valid optimizer requirement with no `Workflow` section still passes.
- A valid optimizer requirement with `Workflow.mode: optimize` still requires `Optimizer Settings`.
- `fix_run` without `Fixed Points` fails.
- `fix_run` without both `Metrics` and `Waveform Exports` fails.
- `fix_run` with an unknown fixed-point parameter fails.
- `fix_run` with a missing required design variable fails.
- Wrong pnoise expression text is not rewritten by intake; intake preserves `getData("NF" ?result "pnoise")`.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_requirement_intake.py tests/test_requirement_intake_fix_run.py -q
```

Expected: FAIL because intake still uses a single required-section list.

**Step 2: Implement mode detection**

In `requirement_intake.py`:

- Add `Workflow`, `Fixed Points`, and `Waveform Exports` to optional parseable sections.
- Parse `Workflow` before enforcing mode-specific required sections.
- Default missing `Workflow` to `mode: optimize`.
- Use optimizer required sections only for optimizer mode.
- Use fix-run required sections only for fix-run mode.
- Render fix-run config payloads without creating `optimizer.yaml`.

**Step 3: Validate rendered payloads**

For fix-run mode, render:

- `project_config.yaml`
- `testbenches.yaml` when multiple testbenches are configured
- `variables.yaml`
- `spectre.yaml`
- `process_corners.yaml` when corners are configured
- `fixed_points.yaml`
- `waveform_exports.yaml` when waveform exports are configured

Do not render `optimizer.yaml` for fix-run.

**Step 4: Run intake tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_requirement_intake.py tests/test_requirement_intake_fix_run.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hermes_workflow/requirement_intake.py tests/test_requirement_intake.py tests/test_requirement_intake_fix_run.py
git commit -m "feat: support fix-run requirement intake"
```

## Task 3: Carry Waveform Exports in Metric Requests

**Files:**

- Modify: `src/hermes_workflow/metric_requests.py`
- Modify: `src/hermes_workflow/metric_results.py`
- Test: `tests/test_metric_requests.py`
- Test: `tests/test_metric_results.py`

**Step 1: Write failing request tests**

Add tests for:

- A fix-run request with one waveform export includes `waveform_exports` in `metric_extraction_request.json`.
- The waveform export entry includes `name`, `testbench`, `expression`, `expression_sha256`, `output_format`, `nil_policy`, and `csv_output_file`.
- Scalar metric request output is unchanged for optimizer mode.
- Empty scalar metrics are allowed when waveform exports are present.
- A request with no scalar metrics and no waveform exports fails.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_metric_requests.py tests/test_metric_results.py -q
```

Expected: FAIL because waveform exports are not part of the request model.

**Step 2: Implement request fields**

In `metric_requests.py`:

- Add `waveform_exports` to request payloads.
- Compute `expression_sha256` with the existing helper.
- Place CSV paths under `metrics/waveforms/<export_name>.csv`.
- Keep scalar `metrics` unchanged.

In `metric_results.py`:

- Add Pydantic request models for waveform export entries.
- Validate `output_format == "csv"`.
- Validate expression hashes.
- Validate relative CSV output paths.

**Step 3: Run request tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_metric_requests.py tests/test_metric_results.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/metric_requests.py src/hermes_workflow/metric_results.py tests/test_metric_requests.py tests/test_metric_results.py
git commit -m "feat: include waveform exports in metric requests"
```

## Task 4: Render OCEAN Waveform CSV Exports

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Test: `tests/test_spectre_ocean_adapter.py`

**Step 1: Write failing OCEAN rendering tests**

Add tests for:

- `render_ocean_replay_script()` emits `ocnPrint` for each waveform export.
- The emitted script uses the exact expression `getData("NF" ?result "pnoise")`.
- The emitted script writes to `metrics/waveforms/nf_pnoise.csv`.
- Expressions containing `outfile(`, `system(`, or template placeholders are rejected before script rendering.
- Existing scalar metric OCEAN output is unchanged.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: FAIL because `waveform_exports` are ignored.

**Step 2: Implement script rendering**

In `spectre_ocean.py`:

- Add `_render_waveform_export_lines(context)` next to scalar metric rendering.
- Validate export name, output path, expression, and expression hash.
- Create `metrics/waveforms/` before OCEAN runs.
- Emit `outfile`, `ocnPrint`, and `close` lines for each export.
- Ensure generated OCEAN variable names are safe and derived from export names.

**Step 3: Run OCEAN rendering tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/execution_adapters/spectre_ocean.py tests/test_spectre_ocean_adapter.py
git commit -m "feat: render waveform csv exports in ocean replay"
```

## Task 5: Persist Waveform Export Manifests Locally

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `src/hermes_workflow/metric_results.py`
- Test: `tests/test_spectre_ocean_adapter.py`

**Step 1: Write failing manifest tests**

Add tests for:

- Successful local OCEAN run writes `metrics/waveform_export_manifest.json`.
- Manifest contains `workflow_mode`, `run_id`, `candidate_id`, `testbench_id`, `corner_id`, `model_section`, `corner_variables`, `parameters`, `exports`, `psf_dir`, `ocean_log`, and `command_trace`.
- Missing CSV after OCEAN return code zero marks the export failed.
- OCEAN failure still writes a waveform export manifest with issues.
- Existing `metric_result_manifest.json` remains valid.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py -q
```

Expected: FAIL because no waveform export manifest is written.

**Step 2: Implement manifest writing**

In `spectre_ocean.py`:

- Add `WAVEFORM_EXPORT_MANIFEST_NAME = "waveform_export_manifest.json"`.
- Add `_write_waveform_export_manifest(...)`.
- Call it after OCEAN completes, before returning adapter result.
- Include command trace using the existing `_build_command_trace(...)`.
- Store CSV paths relative to the child run directory.

In `metric_results.py`:

- Add validation model for `WaveformExportManifest`.

**Step 3: Run manifest tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_metric_results.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/execution_adapters/spectre_ocean.py src/hermes_workflow/metric_results.py tests/test_spectre_ocean_adapter.py tests/test_metric_results.py
git commit -m "feat: persist waveform export manifests"
```

## Task 6: Add Local Fix-Run Orchestration

**Files:**

- Create: `src/hermes_workflow/fix_run_flow.py`
- Modify: `src/hermes_workflow/product_cli.py`
- Test: `tests/test_fix_run_flow.py`
- Test: `tests/test_product_cli.py`

**Step 1: Write failing flow tests**

Add tests for:

- `run_fix_run_project(project_dir, real=True)` calls product doctor before real execution.
- One fixed point creates one candidate request with the configured `candidate_id` and parameters.
- Two fixed points allocate `real_001` and `real_002`.
- Testbench/corner expansion calls the same child run path used by optimizer real runs.
- `reports/fix_run_report.json` is written.
- No optimizer state path is created.
- Product CLI `ic-opt PROJECT --real` dispatches to fix-run when `Workflow.mode: fix_run`.
- Product CLI `ic-opt PROJECT --real` still dispatches to optimizer when `Workflow` is absent.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_product_cli.py -q
```

Expected: FAIL because fix-run flow does not exist.

**Step 2: Implement local flow**

In `fix_run_flow.py`:

- Load requirement intake result.
- Confirm `Workflow.mode == "fix_run"`.
- Run product doctor when real execution is requested.
- Convert each fixed point to `CandidateInjectionRequest`.
- Reuse existing candidate real-run preparation helpers.
- Reuse existing multi-testbench/corner execution utilities.
- Write `reports/fix_run_report.json`.
- Return a structured result with status, run ids, artifact paths, and issues.

In `product_cli.py`:

- Keep `--real` as the product entry.
- Detect workflow mode from requirement intake.
- Dispatch to `run_fix_run_project()` for fix-run mode.
- Keep optimizer dispatch unchanged for optimizer mode.

**Step 3: Run flow tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_product_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/fix_run_flow.py src/hermes_workflow/product_cli.py tests/test_fix_run_flow.py tests/test_product_cli.py
git commit -m "feat: add local fix-run workflow"
```

## Task 7: Add Remote Fix-Run Orchestration

**Files:**

- Create: `src/hermes_workflow/remote_fix_run_flow.py`
- Modify: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `src/hermes_workflow/product_cli.py`
- Test: `tests/test_remote_fix_run_flow.py`
- Test: `tests/test_remote_spectre_ocean.py`

**Step 1: Write failing remote tests**

Add tests for:

- Remote fix-run calls remote doctor and blocks on failure.
- Remote fix-run uploads fixed-point request artifacts.
- Remote Spectre/OCEAN downloads `metrics/waveforms/*.csv`.
- Remote Spectre/OCEAN downloads `metrics/waveform_export_manifest.json`.
- Remote failure manifests preserve waveform export issues and command trace.
- Product CLI remote `--real` dispatches to remote fix-run when `Workflow.mode: fix_run`.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_remote_spectre_ocean.py tests/test_product_cli.py -q
```

Expected: FAIL because remote fix-run does not exist and waveform files are not downloaded.

**Step 2: Implement remote flow**

In `remote_fix_run_flow.py`:

- Mirror local fix-run flow structure.
- Reuse remote doctor and remote cache preparation.
- Use existing SSH runner abstractions.
- Preserve remote and local artifact paths in the report.

In `remote_spectre_ocean.py`:

- Download `metrics/waveforms/`.
- Download `metrics/waveform_export_manifest.json`.
- Include waveform export manifest references in success and failure paths.

In `product_cli.py`:

- Dispatch remote `--real` to remote fix-run when workflow mode is `fix_run`.

**Step 3: Run remote tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py tests/test_remote_spectre_ocean.py tests/test_product_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hermes_workflow/remote_fix_run_flow.py src/hermes_workflow/remote_optimizer_flow.py src/hermes_workflow/execution_adapters/remote_spectre_ocean.py src/hermes_workflow/product_cli.py tests/test_remote_fix_run_flow.py tests/test_remote_spectre_ocean.py tests/test_product_cli.py
git commit -m "feat: add remote fix-run workflow"
```

## Task 8: Add Examples and User Documentation

**Files:**

- Create: `examples/spectre_maestro_project/opt_requirement.fix_run.md`
- Create: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md`
- Modify: `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify: `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`
- Modify: `docs/PRODUCT_RELEASE_CHECKLIST.md`
- Modify: `skills/ic-opt/SKILL.md`
- Test: `tests/test_release_docs.py` if present, otherwise add `tests/test_fix_run_docs.py`

**Step 1: Write failing docs/template tests**

Add tests for:

- Release example and packaged template are byte-for-byte identical.
- `opt_requirement.fix_run.md` parses as `Workflow.mode: fix_run`.
- The example uses `getData("NF" ?result "pnoise")`.
- The example does not mention `--fix-run`, `--max-evals`, `--parallel-jobs`, `--strategy`, `--multi-corner`, or `psfascii`.

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_docs.py -q
```

Expected: FAIL because the example does not exist.

**Step 2: Write docs and templates**

Create `opt_requirement.fix_run.md` from a verified requirement pattern with sensitive paths removed. Include:

- `Workflow`
- `Project`
- `Maestro Source`
- `Design Variables`
- `Spectre Settings`
- `Process Corners`
- `Fixed Points`
- `Waveform Exports`
- `Approval Checklist`

Update user-facing docs to state:

- Fix-run uses `ic-opt PROJECT --real`.
- `Workflow.mode` chooses fix-run.
- Variables, points, corners, thread count, parallelism, timeout, and waveform expressions come from `opt_requirement.md`.
- The output is a simulation archive, not an optimization report.

**Step 3: Run docs tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_fix_run_docs.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add examples/spectre_maestro_project/opt_requirement.fix_run.md src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md examples/spectre_maestro_project/OPT_REQUIREMENT_README.md docs/USER_GUIDE_CN.md docs/TOOLCHAIN_EXECUTION_REFERENCE.md docs/PRODUCT_RELEASE_CHECKLIST.md skills/ic-opt/SKILL.md tests/test_fix_run_docs.py
git commit -m "docs: add fix-run requirement example"
```

## Task 9: Run Code-Level Verification

**Files:**

- No source files created.
- Verification covers all modified files.

**Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_fix_run_models.py \
  tests/test_requirement_intake.py \
  tests/test_requirement_intake_fix_run.py \
  tests/test_metric_requests.py \
  tests/test_metric_results.py \
  tests/test_spectre_ocean_adapter.py \
  tests/test_remote_spectre_ocean.py \
  tests/test_fix_run_flow.py \
  tests/test_remote_fix_run_flow.py \
  tests/test_product_cli.py \
  tests/test_fix_run_docs.py \
  -q
```

Expected: PASS.

**Step 2: Run broader regression tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests -q
```

Expected: PASS.

**Step 3: Run lint**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected: PASS.

**Step 4: Run whitespace check**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: no output.

- [ ] **Step 5: Commit if verification required changes**

```bash
git add src tests docs examples skills
git commit -m "test: verify fix-run workflow"
```

## Task 10: Run Real Workflow Acceptance

**Files:**

- Use a real project copy under `/tmp` or another approved scratch directory.
- Do not modify the original user project in place.

**Step 1: Prepare one local fix-run requirement**

Use a real project with:

- one fixed point
- one testbench or the target testbench set
- 3 process sections
- 10 temperatures
- one waveform export using `getData("NF" ?result "pnoise")`

**Step 2: Run local doctor**

Run:

```bash
rtk proxy ./.venv/bin/ic-opt /path/to/local/fix_run_project --doctor
```

Expected: doctor passes, including license probe when required.

**Step 3: Run local fix-run**

Run:

```bash
rtk proxy ./.venv/bin/ic-opt /path/to/local/fix_run_project --real
```

Expected: fix-run completes or records child-level failures with artifacts.

**Step 4: Inspect local artifacts**

Verify:

- `reports/fix_run_report.json` exists.
- No `state/optimizer_state.json` exists.
- No `reports/optimizer_decision_report.md` exists.
- 30 child corners exist for the single fixed point.
- Each child has `psf/`, `metrics/ocean.log`, `metrics/waveform_export_manifest.json`, and the requested CSV.
- One `tt`, one `ss`, and one `ff` manifest show correct `model_section`, `temperature`, fixed-point parameters, OCEAN expression, CSV path, and command trace.

**Step 5: Prepare one remote fix-run requirement**

Copy the same sanitized project to the remote workspace used for real optimizer validation.

**Step 6: Run remote doctor**

Run:

```bash
rtk proxy ./.venv/bin/ic-opt --ssh-profile user@host /remote/path/to/fix_run_project --doctor
```

Expected: remote doctor passes, including license probe when required.

**Step 7: Run remote fix-run**

Run:

```bash
rtk proxy ./.venv/bin/ic-opt --ssh-profile user@host /remote/path/to/fix_run_project --real
```

Expected: remote fix-run completes or records child-level failures with downloaded artifacts.

**Step 8: Inspect remote-downloaded artifacts**

Verify in the local remote-run cache:

- `reports/fix_run_report.json` exists.
- 30 child corners have downloaded PSF directories or expected PSF references.
- 30 waveform export manifests exist.
- 30 CSV files exist and are non-empty.
- Command traces are sanitized and contain Spectre/OCEAN argv summaries.

**Step 9: Record acceptance**

Update:

- `docs/CURRENT_BUGFIX_PROGRESS.md`
- `docs/CURRENT_TASK_STATE.json`

Record:

- local project path
- remote project path
- run ids
- artifact paths
- number of corners
- number of CSV files
- inspected corner ids
- remaining risks

- [ ] **Step 10: Commit acceptance notes**

```bash
git add docs/CURRENT_BUGFIX_PROGRESS.md docs/CURRENT_TASK_STATE.json
git commit -m "docs: record fix-run workflow acceptance"
```

