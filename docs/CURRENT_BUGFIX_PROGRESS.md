# Current Bugfix Progress

Last updated: 2026-06-16

## Scope Rules

- Development package: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Release package: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`
- Fixes are made only in the development package unless release sync is explicitly requested.
- Do not commit, reset, revert, or stash existing user/agent changes while continuing this queue.
- After each completed fix, update this file before ending the task.
- Product CLI contract: initial real runs must take optimizer, workload,
  scheduler, Spectre, metric, and resource settings only from
  `opt_requirement.md` / generated config files. The product CLI must not add
  workload/resource/optimizer override flags.
- Product continuation contract: CLI may provide only `--continue N`, where `N`
  is an additional evaluation budget delta. Every other value still comes from
  the project requirement/config.
- Acceptance contract: source review and unit tests are only code-level
  acceptance. A bug is fully accepted only after an actual workflow run and
  artifact inspection prove requirement variables propagated through generated
  config, backend execution, process/state files, reports, and manifests.

## 2026-06-17 Dev Package Release-Line Cleanup

Status: completed in the development package.

Purpose:

- Bring the dev package back in line with the published v0.1.8 release direction.
- Use the v0.1.8 release package as the source of truth for release-facing docs,
  examples, templates, product code, and tests.
- Remove obsolete runtime-native Claude/OpenCode adapter assets, packaged
  `src/hermes_workflow/agent_skills`, and execution-agent handoff code from the
  dev mainline. The current agent contract remains the root
  `skills/ic-opt/SKILL.md`.
- Keep dev-only historical planning records under `docs/superpowers/`; those are
  not release-package contents.

Actions:

- Synced v0.1.8 release-facing README, release notes, user docs, agent docs,
  examples, templates, requirements files, and core product/test files back into
  the dev package.
- Added `RELEASE_NOTES_v0.1.8.md` to dev.
- Updated `.gitignore` for Python caches and local tooling state, then removed
  generated `__pycache__` and `.serena` directories from the working tree.
- Removed tracked obsolete runtime/agent files:
  `agent_runtime/`, `claude_skills/`, `src/hermes_workflow/agent_runtime.py`,
  `src/hermes_workflow/agent_skills/`,
  `src/hermes_workflow/execution_agent_handoff.py`,
  `tests/test_agent_runtime.py`, `tests/test_agent_skill.py`, and
  `tests/test_execution_agent_handoff.py`.
- Removed the positive `--execution-agent` product CLI path and kept only
  negative tests that assert the old flag is rejected.

Fresh verification:

- Focused:
  `rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_cli.py tests/test_optimizer_flow.py tests/test_fix_run_flow.py tests/test_remote_fix_run_flow.py tests/test_validate.py tests/test_package.py -q`
  -> `143 passed, 13 warnings`.
- Full:
  `rtk proxy ./.venv/bin/python -m pytest -q`
  -> `1191 passed, 13 warnings`.
- Ruff:
  `rtk proxy ./.venv/bin/python -m ruff check src tests`
  -> `All checks passed!`.
- Whitespace:
  `rtk git diff --check`
  -> clean.
- Dev/release tracked-file comparison:
  release files are all present in dev; only intentional content deltas are
  `.gitignore`, `src/hermes_workflow/product_cli.py`, and
  `tests/test_product_cli.py`.

## 2026-06-16 Release v0.1.7 Agent/Skill Cleanup

Current release-package direction:

- The user-facing agent skill lives only at `skills/ic-opt/SKILL.md`.
- `src/` is product code only; no `src/hermes_workflow/agent_skills` package-data skill remains.
- Old Claude/OpenCode runtime adapter assets and commands are removed from the release package.
- Old execution-agent handoff code paths are removed from release `optimizer_flow`, product CLI wiring, tests, and docs.
- Release docs should describe the correct current workflow directly, without calling out obsolete flags or historical mistakes.

Verification in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`:

- `PYTHONPATH=src ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q` exited 0.
- `PYTHONPATH=src ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests` passed.
- `git diff --check -- . ':!vendor' ':!.serena'` passed.
- Grep for `Claude|claude|OpenCode|opencode|agent_runtime|agent_skills|claude_skills|install-runtime-adapter|runtime-adapter|agent-skill-path|execution_agent_handoff` returned no release-package matches outside `vendor/.git`.
- Grep for `--execution-agent|execution_agent|execution-agent` returns only negative tests that assert the old option is rejected.

## Code-Level Accepted In Dev

### B-01 Product CLI `--strategy` removal

Status: code-level accepted in development package; workflow-level acceptance
is still pending.

Evidence:
- Product CLI no longer exposes `--strategy` as an accepted option.
- Initial local and remote product flows no longer accept a CLI strategy override.
- Tests lock fail-closed behavior for initial runs and continuation attempts that pass `--strategy`.
- Low-level OpenBox/backend strategy debug capability remains out of scope and is intentionally preserved.

Release status:
- Not synced to release package yet.

Workflow acceptance still required:
- Run the product CLI workflow path and inspect generated process/artifact
  files to prove initial optimizer settings come only from
  `opt_requirement.md` / generated config.
- Confirm no product workflow artifact records or depends on a CLI strategy
  override.

### B-07 `optimizer.initialization` pass-through

Status: code-level accepted in development package; workflow-level acceptance
is still pending.

Evidence:
- OpenBox initialization is passed through to Advisor `init_strategy`.
- Native TuRBO initialization supports `sobol`, `latin_hypercube`, and `random`.
- Native TuRBO Sobol initialization now uses `Sobol(..., scramble=True, seed=seed)`, so `random_seed` controls the design.
- Same Sobol seed reproduces the same samples; different Sobol seeds produce different samples.
- Report/audit evidence fields were added for effective initialization.

Fresh verification:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_native_turbo.py -q` passed.
- `rtk proxy ./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_remote_optimizer_flow.py -q` passed.
- `rtk proxy ./.venv/bin/python -m pytest -q` passed.
- `rtk proxy ./.venv/bin/python -m ruff check src tests` passed.
- `rtk proxy git diff --check -- . ':!vendor' ':!.serena'` passed.

Release status:
- Not synced to release package yet.

Workflow acceptance still required:
- Start from an `opt_requirement.md` with non-default
  `optimizer.initialization`.
- Run the actual project workflow far enough to generate optimizer process
  files and reports.
- Inspect generated config, optimizer report/audit, and workflow state files to
  prove the requirement value was propagated and became the effective
  initialization.
- Cover at least OpenBox with a non-default initialization and native TuRBO
  Sobol seed behavior through generated workflow artifacts rather than helper
  tests.
- Do not call B-07 fully accepted until artifact-level evidence proves the
  requirement variable was passed and took effect.

## Open / Not Yet Fixed

### B-10 Spectre/OCEAN command traceability

Status: code-level fixed in development package; workflow-level acceptance
pending real local/remote artifact gate.

Root cause:
- `build_spectre_argv` and `build_ocean_argv` constructed correct argv,
  but `_write_result_manifest` and `_write_metric_result_manifest` never
  persisted it in the manifest payload. The remote adapter similarly
  constructed `spectre_command`/`ocean_command` (csh -fc wrappers) but
  never wrote any command trace.
- Pydantic models `ResultManifest` and `MetricResultManifest` used
  `extra="forbid"` and had no `command_trace` field, so even if a trace
  were added to the payload, validation would reject it.

Code-level fix (2026-06-15):
- Added `_build_spectre_trace`, `_build_ocean_trace`, and
  `_build_command_trace` helper functions to `spectre_ocean.py`.
- Extended `_write_result_manifest`, `_write_metric_result_manifest`,
  `write_spectre_result_manifest`, and `write_metric_result_manifest`
  with optional `command_trace: dict | None = None` parameter.
- Local adapter `run_spectre_ocean_adapter` now builds and passes
  `command_trace` to all manifest writer calls (spectre failure, ocean
  failure, success).
- Remote adapter `run_remote_spectre_ocean_adapter` now builds and passes
  `command_trace` to all manifest writer calls, including `_write_remote_failure`
  (upload failure, spectre exception, spectre non-zero, PSF missing,
  ocean no-result, metric download failure, success/ocean-failure).
- `_write_remote_failure` now accepts optional `command_trace` parameter.
- Trace is sanitized: `command` field uses `shlex.quote` on canonical
  local argv (from `build_spectre_argv`/`build_ocean_argv`), NOT the
  remote `csh -fc` wrapper. No cshrc path, no SSH command, no secrets.
- `ResultManifest` in `result_handoff.py` and `MetricResultManifest` in
  `metric_results.py` now have `command_trace: dict | None = None`.
- `parallel_jobs` is never present in any trace field.

Command trace schema:
```json
{
  "command_trace": {
    "schema_version": "1.0",
    "execution_mode": "local" | "remote",
    "spectre": {
      "argv": ["spectre", "-64", "input.scs", "+escchars", ...],
      "command": "spectre -64 input.scs +escchars ...",
      "cwd": "/path/to/netlist",
      "timeout_s": 3600,
      "settings": {
        "engine": "spectre_x",
        "preset": "ax",
        "threads_per_run": 10,
        "output_format": "psfxl"
      }
    },
    "ocean": {
      "argv": ["ocean", "-nograph", "-replay", "...", "-log", "..."],
      "command": "ocean -nograph -replay ... -log ...",
      "cwd": "/path/to/project",
      "timeout_s": 3600,
      "mode": "nograph_replay",
      "return_code": 0,
      "return_codes": [0]
    }
  }
}
```

Manifest fields affected:
- Child `result_manifest.json`: `command_trace` with `spectre` sub-object.
  On spectre failure, `ocean` sub-object is omitted.
- Child `metric_result_manifest.json`: `command_trace` with `spectre` and
  `ocean` sub-objects including `return_code`/`return_codes`.
- Parent aggregate manifests: no change (continue to reference child manifests).

Tests added:
- `test_local_success_result_manifest_has_command_trace_spectre_argv`
- `test_local_success_metric_manifest_has_command_trace_ocean_argv`
- `test_local_spectre_failure_result_manifest_still_has_command_trace`
- `test_local_ocean_failure_metric_manifest_has_command_trace_with_return_codes`
- `test_local_command_trace_does_not_contain_parallel_jobs`
- `test_local_transient_ocean_failure_command_trace_has_retry_return_codes`
- `test_remote_success_result_manifest_has_command_trace`
- `test_remote_success_metric_manifest_has_command_trace`
- `test_remote_command_trace_timeout_s_comes_from_request`
- `test_remote_command_trace_does_not_leak_cshrc_or_ssh`
- `test_remote_spectre_failure_still_writes_command_trace`
- `test_remote_spectre_runtime_error_still_writes_command_trace`
- `test_remote_upload_failure_still_writes_command_trace`
- `test_remote_psf_missing_still_writes_command_trace`
- `test_remote_ocean_failure_writes_command_trace`

Verification:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py tests/test_metric_results.py -q`: 168 passed
- `rtk proxy ./.venv/bin/python -m pytest tests/test_real_run.py tests/test_optimizer_acceptance.py tests/test_product_cli.py tests/test_product_cli_remote.py -q`: 66 passed
- `rtk proxy ./.venv/bin/python -m pytest -q`: 990 passed
- `rtk proxy ./.venv/bin/python -m ruff check src tests`: All checks passed
- `rtk proxy git diff --check -- . ':!vendor' ':!.serena'`: Clean
- Release package (`ic-auto-opt-workflow-v0.1`): Not touched

Modified files:
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_remote_spectre_ocean.py`

Workflow acceptance still required:
- Run real local and remote Spectre/OCEAN workflows and inspect child
  `result_manifest.json` and `metric_result_manifest.json` for the
  `command_trace` field.
- Verify `execution_mode`, `spectre.argv`, `ocean.argv`, `timeout_s`,
  and sanitized `command` values in both local and remote artifacts.
- Verify failure-path manifests (spectre failure, ocean failure) still
  carry `command_trace`.
- Verify no cshrc content, SSH command, or secrets leak into traces.
- Do not call B-10 fully accepted until real artifact inspection proves
  the command trace is present and correct in production workflow output.

### B-08 / output format contract tightening

Status: code-level fixed in development package; workflow-level acceptance pending.

Current evidence:
- `src/hermes_workflow/schemas.py` now allows only `Literal["psfxl"]`.
- `psfascii` is rejected during project config/schema validation before real-run preparation and before metric request generation.
- `src/hermes_workflow/metric_requests.py` still treats `psfxl` as the only OCEAN-ready format.

Required outcome:
- Do not add `psfascii` support.
- Fail closed earlier for unsupported `psfascii` in the production requirement path. Code-level fixed.
- Keep templates and user-facing docs aligned on `psfxl`.

Fresh code-level verification:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py::test_spectre_rejects_psfascii_output_format -q` -> exit 0
- `rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py tests/test_real_run.py tests/test_spectre_ocean_adapter.py -q` -> exit 0

### B-03/B-04 acceptance gate

Status: dev source appears fixed, but final acceptance is still open.

Current evidence:
- B-03 remote timeout propagation appears fixed in dev source.
- B-04 parent aggregate manifest metadata inheritance appears fixed in dev source.

Required outcome:
- Reconfirm after release sync with real local and remote 3-corner parent aggregate manifests.
- Specifically inspect parent `result_manifest.json` simulator metadata, rather than run success alone.

### Release sync

Status: open.

Current evidence:
- Release package tracked source files were not touched during B-07 blocker verification.
- Dev package and release package are still not declared synchronized.

Required outcome:
- Sync only after remaining dev fixes and required real/local remote validation gates are complete.
- Re-run release-gate checks after sync.

### B-05 `require_license_check` parsed but not enforced

Status: code-level fixed in development package; workflow-level acceptance
pending real local/remote artifact gate.

Root cause:
- `SpectreSettings.require_license_check` existed in schema and was
  required by requirement intake, but neither local doctor, remote doctor,
  nor real optimizer flow executed any license environment probe.
- The field was a cosmetic contract entry with no enforcement.

Code-level fix (2026-06-15):
- Added `src/hermes_workflow/license_probe.py` with:
  - `LicenseProbeReport` dataclass (status, execution_mode,
    require_license_check, spectre_path, spectre_version,
    lmstat_available, license_features, raw_license_lines, issues).
  - `parse_lmstat_output()` parses ``lmstat -a`` "Users of ..." lines.
  - `run_local_license_probe()` sources cshrc via ``csh -fc`` and runs
    ``which spectre``, ``spectre -V``, ``lmstat -a``.
  - `run_remote_license_probe()` uses SSH runner with same ``csh -fc``
    pattern via `quote_remote_path()`.
  - `write_license_probe_report()` writes
    ``reports/license_probe_report.json`` with ``schema_version: "1.0"``.
  - `run_license_probe_skipped()` returns status="skipped" when
    ``require_license_check=false``.
- `product_doctor.py`:
  - Added `license_probe` field to `ProductDoctorReport`.
  - Added `check_license` slot to `ProductDoctorServices`.
  - `_check_license_probe()` reads ``require_license_check`` from
    requirement sections. When true, runs probe; when false, skipped.
  - Probe failure adds to doctor issues, causing overall status="fail".
  - Standalone ``reports/license_probe_report.json`` written locally.
- `remote_doctor.py`:
  - Added `license_probe` field to `RemoteDoctorReport`.
  - `_check_remote_license_probe()` runs after ``spectre_ocean`` check.
  - When ``require_license_check=true``, runs remote probe via SSH.
  - Probe failure adds to issues + structured diagnostics.
  - Standalone ``reports/license_probe_report.json`` written to local cache.
- `optimizer_flow.py`:
  - Added `run_product_doctor` slot to `OptimizerFlowServices`.
  - Local ``optimize_project()`` now calls doctor as preflight gate when
    ``real=True``, matching remote flow parity.
  - Doctor failure raises ``ValueError`` before any optimizer steps.

Sanitization:
- Report does NOT contain cshrc content, secrets, or SSH command strings.
- ``license_guaranteed`` is NOT used anywhere.
- Remote report does NOT leak cshrc path or SSH profile.

Behavior matrix:
| require_license_check | Doctor action | Real flow |
|---|---|---|
| true + probe pass | status=pass | allowed |
| true + probe fail | status=fail | blocked |
| false | skipped | allowed |

Tests added:
- `tests/test_license_probe.py` (24 tests):
  parse_lmstat_output, local success/failure (cshrc missing, csh not
  available, timeout, spectre missing), remote success/failure,
  skipped, write report, sanitization checks.
- `tests/test_product_doctor.py` (3 tests):
  require=true+pass, require=true+fail, require=false+skipped.
- `tests/test_remote_doctor.py` (3 tests):
  require=true+pass, require=true+fail, require=false+skipped.
- `tests/test_optimizer_flow.py`: Updated call sequences to include
  ``doctor`` step; added `run_product_doctor` mock to `_services`.

Verification:
- `pytest tests/test_license_probe.py tests/test_product_doctor.py tests/test_remote_doctor.py -q`: 53 passed
- `pytest tests/test_optimizer_flow.py -q`: 8 passed
- `pytest -q`: 1022 passed
- `ruff check src tests`: All checks passed
- `git diff --check`: Clean
- Release package (`ic-auto-opt-workflow-v0.1`): Not touched

Workflow acceptance still required:
- Run real local doctor with `require_license_check: true` and verify
  `reports/license_probe_report.json` is produced with expected fields.
- Run real remote doctor and verify license probe runs on remote host.
- Verify probe fail blocks real optimizer flow in both local and remote.
- Verify `require_license_check: false` skips probe and allows flow.
- Do not call B-05 fully accepted until real artifact inspection proves
  enforcement.

### `require_license_check` (old deferred note: superseded)

Status: now implemented as B-05 code-level fix (see above).

## 2026-06-16 Fix-Run Simulation Workflow Implementation

Status: code-level verified in development package; workflow-level acceptance pending real Spectre/OCEAN run.

Scope: Implement `fix_run` workflow mode that runs user-specified design points through existing real Spectre/OCEAN infrastructure and archives PSF data, scalar metrics, waveform CSV exports, command traces, and manifests — without entering optimizer logic.

Key principle: `ic-opt PROJECT --real` remains the only CLI entry. Workflow mode is selected by `opt_requirement.md` `Workflow.mode: fix_run`.

### Tasks Completed (TDD with subagent-driven development)

**Task 1: Fix-Run Models** (`feat: add fix-run config models`)
- Created `src/hermes_workflow/fix_run_models.py` with 10 Pydantic models:
  `WorkflowMode`, `WorkflowSettings`, `FixedPoint`, `FixedPointsConfig`,
  `WaveformExport`, `WaveformExportsConfig`, `WaveformExportResult`,
  `WaveformExportManifest`, `FixRunPointReport` (with `ChildRunIssue`),
  `FixRunReport`
- Tests: `tests/test_fix_run_models.py` — 20 tests pass
- Spec gap fixed: added `ChildRunIssue` for testbench/corner issue grouping

**Task 2: Requirement Intake Workflow-Aware** (`feat: support fix-run requirement intake`)
- Modified `src/hermes_workflow/requirement_intake.py`:
  - Added `Workflow`, `Fixed Points`, `Waveform Exports` to optional sections
  - Mode detection: `Workflow.mode` → `fix_run` or `optimize` (default)
  - Mode-specific required sections and field validation
  - Mode-specific config rendering (no `optimizer.yaml` for fix-run)
  - Added `workflow_mode` field to `RequirementIntakeReport`
- Tests: `tests/test_requirement_intake_fix_run.py` — 12 tests pass
- All 32 existing intake tests still pass

**Task 3: Waveform Exports in Metric Requests** (`feat: include waveform exports in metric requests`)
- Modified `src/hermes_workflow/metric_requests.py`: added `waveform_exports` to request payload
- Modified `src/hermes_workflow/metric_results.py`: added `WaveformExportRequestEntry` model and `waveform_exports` field to `MetricExtractionRequest`
- Tests: `tests/test_metric_requests.py` — 6 tests, `tests/test_metric_results.py` — 5 new tests

**Task 4: OCEAN Waveform CSV Rendering** (`feat: render waveform csv exports in ocean replay`)
- Modified `src/hermes_workflow/execution_adapters/spectre_ocean.py`:
  - Added `_render_waveform_export_lines()` for `ocnPrint` CSV export
  - Expression safety validation (rejects `outfile(`, `system(`, `{{`)
  - Creates `metrics/waveforms/` directory
- Tests: `tests/test_spectre_ocean_adapter.py` — 7 new tests (78 total)

**Task 5: Waveform Export Manifests** (`feat: persist waveform export manifests`)
- Modified `spectre_ocean.py`: added `_write_waveform_export_manifest()` for local persistence
- Modified `metric_results.py`: added optional manifest validation
- Tests: 6 new adapter tests + 3 new metric_results tests

**Task 6: Local Fix-Run Orchestration** (`feat: add local fix-run workflow`)
- Created `src/hermes_workflow/fix_run_flow.py`: `run_fix_run_project()` entry point
- Modified `src/hermes_workflow/product_cli.py`: dispatches to fix-run when `Workflow.mode: fix_run`
- Tests: `tests/test_fix_run_flow.py` — 7 tests, `tests/test_product_cli.py` — 2 tests

**Task 7: Remote Fix-Run Orchestration** (`feat: add remote fix-run workflow`)
- Created `src/hermes_workflow/remote_fix_run_flow.py`: `run_remote_fix_run_project()` entry point
- Modified `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`: downloads waveform CSVs and manifests
- Modified `product_cli.py`: remote dispatch to fix-run
- Tests: `tests/test_remote_fix_run_flow.py` — 6 tests, `tests/test_remote_spectre_ocean_waveform.py` — 3 tests

**Task 8: Documentation and Examples** (`docs: add fix-run requirement example`)
- Created `examples/spectre_maestro_project/opt_requirement.fix_run.md`
- Created `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md` (identical)
- Updated: `OPT_REQUIREMENT_README.md`, `USER_GUIDE_CN.md`, `TOOLCHAIN_EXECUTION_REFERENCE.md`, `PRODUCT_RELEASE_CHECKLIST.md`, `skills/ic-opt/SKILL.md`
- Tests: `tests/test_fix_run_docs.py` — 11 tests

**Task 9: Code-Level Verification**
- Focused tests: 257 passed
- Full pytest: 1164 passed, 1 pre-existing unrelated failure in `test_agent_skill.py`
- Ruff: All checks passed
- `git diff --check`: clean
- Release package: NOT modified

### Files Created
- `src/hermes_workflow/fix_run_models.py`
- `src/hermes_workflow/fix_run_flow.py`
- `src/hermes_workflow/remote_fix_run_flow.py`
- `tests/test_fix_run_models.py`
- `tests/test_requirement_intake_fix_run.py`
- `tests/test_metric_requests.py` (new)
- `tests/test_remote_fix_run_flow.py`
- `tests/test_remote_spectre_ocean_waveform.py`
- `tests/test_fix_run_flow.py`
- `tests/test_product_cli.py` (new)
- `tests/test_fix_run_docs.py`
- `examples/spectre_maestro_project/opt_requirement.fix_run.md`
- `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md`

### Files Modified
- `src/hermes_workflow/requirement_intake.py`
- `src/hermes_workflow/metric_requests.py`
- `src/hermes_workflow/metric_results.py`
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- `src/hermes_workflow/product_cli.py`
- `tests/test_metric_results.py`
- `tests/test_spectre_ocean_adapter.py`
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- `docs/USER_GUIDE_CN.md`
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`
- `docs/PRODUCT_RELEASE_CHECKLIST.md`
- `skills/ic-opt/SKILL.md`

### Workflow Acceptance Still Required
- At least one real local fix-run with Spectre/OCEAN
- At least one real remote fix-run
- Verify 1 fixed point across 30 corners (3 process sections x 10 temperatures)
- Verify each corner has: PSF, OCEAN log, waveform CSV, waveform_export_manifest.json, command_trace
- Randomly inspect tt, ss, ff corners for correct model_section, temperature, parameters, expression, CSV path
- Verify no optimizer_state or optimizer decision/final reports are generated
- If real environment is temporarily unavailable, must explicitly mark workflow acceptance as NOT complete

## Recommended Next Task

Before any more implementation or release sync, run a context-recovery pass over
the development package source, tests, docs, and recovered conversation records.
The immediate debug direction is requirement-variable propagation, not UI polish
or superficial code review.

Workflow validation direction:
- For an initial local or remote 10-point validation run, the 10-point budget
  must be present in `opt_requirement.md` / generated `config/optimizer.yaml`.
  Do not pass a workload budget through product CLI.
- For a continuation validation run, the only product CLI budget input may be
  `--continue 10`; all other settings must still come from existing
  requirement-backed config.
- For each validation run, inspect at least:
  `opt_requirement.md`, generated `config/optimizer.yaml`,
  generated `config/spectre.yaml`, backend optimizer report/audit,
  `state/optimizer_state.json`, child `result_manifest.json`, child
  `metrics/metric_result_manifest.json`, and parent aggregate manifests when
  multi-testbench/multi-corner is involved.
- Do not call a bug fully accepted unless these artifacts prove the requirement
  values propagated and took effect in execution.

Next implementation target after context recovery: ~~B-10 Spectre/OCEAN command
traceability~~ (code-level fixed 2026-06-15; workflow acceptance pending).

Then:
1. Tighten `output_format` to production `psfxl` behavior.
2. Run B-03/B-04 local and remote 3-corner acceptance gates.
3. Run B-10 real artifact gate (inspect child command_trace in local/remote manifests).
4. Perform release sync only after dev fixes and acceptance gates are complete.

## 2026-06-14 Local/Remote 10-Point Artifact Gate

Base requirement:
- Source project: `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_4`
- Local validation copy:
  `/tmp/ic_auto_opt_b07_b01_local10_Mixer_CS_muti_tb_fix_4_20260614`
- Remote validation copy:
  `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_4_remote10_b07_20260614`
- Remote local cache:
  `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/9318a5457958500f`

Requirement changes made only in validation copies:
- `optimizer.initialization: latin_hypercube`
- `optimizer.max_evaluations: 10`
- Kept multi-testbench and multi-corner coverage:
  `cg_nf`, `iip3`, `p1db` x `tt`, `ss`, `ff`
- Kept `spectre.output_format: psfxl`, `threads_per_run: 10`,
  `parallel_jobs: 10`, and `timeout_s: 7200`.

Commands run:
- Local: `./.venv/bin/ic-opt /tmp/ic_auto_opt_b07_b01_local10_Mixer_CS_muti_tb_fix_4_20260614 --doctor`
- Local: `./.venv/bin/ic-opt /tmp/ic_auto_opt_b07_b01_local10_Mixer_CS_muti_tb_fix_4_20260614 --real`
- Remote: `./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 /home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_4_remote10_b07_20260614 --doctor`
- Remote: `./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 /home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_4_remote10_b07_20260614 --real`

Artifact evidence:
- Both local and remote `reports/optimizer_flow_run_report.json` had
  `max_evals: null`, `batch_size: null`, and `parallel_jobs: null`, proving the
  product CLI did not provide workload/resource overrides.
- Both local and remote generated `config/optimizer.yaml` had
  `strategy: openbox_prf_eic`, `initialization: latin_hypercube`,
  `max_evaluations: 10`, `batch_size: 10`, and `random_seed: 20260528`.
- Both local and remote generated `config/process_corners.yaml` had
  `objective_policy: worst_case`, `constraint_policy: all_corners`, and corners
  `tt`, `ss`, `ff`.
- Both local and remote generated `config/spectre.yaml` had
  `output_format: psfxl`, `threads_per_run: 10`, `parallel_jobs: 10`, and
  `timeout_s: 7200`.
- Both local and remote `reports/optimizer_effectiveness_audit.json` had
  `initialization: latin_hypercube` and
  `effective_init_strategy: latin_hypercube`.
- Both local and remote `state/optimizer_state.json` had
  `initialization: latin_hypercube`, `current_evaluations: 10`,
  `max_evaluations: 10`, `batch_size: 10`, and `random_seed: 20260528`.
- Both local and remote produced 10 parent real-run directories.
- Both local and remote produced 90 child result manifests:
  10 per `cg_nf/iip3/p1db` x `tt/ss/ff`.
- Both local and remote parent and child manifests carried simulator metadata:
  `spectre_x`, `preset: ax`, `output_format: psfxl`, `threads_per_run: 10`,
  `timeout_s: 7200`, and no `parallel_jobs` as a Spectre child setting.
- Remote original project and remote local cache both retained synchronized
  reports/state/runs artifacts.

Status after this gate:
- B-01 product CLI source-of-truth contract: workflow accepted for initial
  local and remote real runs.
- B-07 OpenBox initialization pass-through: workflow accepted for OpenBox with
  non-default `latin_hypercube` initialization. Native TuRBO workflow is not
  covered by this OpenBox validation and remains code-level verified only unless
  a separate native TuRBO real workflow is run.
- B-04 parent aggregate manifest metadata inheritance: workflow accepted for
  local and remote multi-testbench/multi-corner parent manifests.
- B-03 remote timeout propagation: artifact-level accepted through remote
  generated config, metric requests, parent manifests, and child manifests with
  `timeout_s: 7200`; direct shell-command/argv trace for the timeout wrapper is
  still blocked by B-10 command traceability.
- B-10 remains open because child artifacts still do not persist a complete
  sanitized Spectre/OCEAN command trace.
## 2026-06-15 Codex Review: B-10 Claude Fix

Status: code-level review passed; workflow-level acceptance is still pending.

Scope reviewed in development package only:
- `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- `src/hermes_workflow/result_handoff.py`
- `src/hermes_workflow/metric_results.py`
- `tests/test_spectre_ocean_adapter.py`
- `tests/test_remote_spectre_ocean.py`

Fresh verification run by Codex:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py tests/test_metric_results.py -q` -> exit 0
- `rtk proxy ./.venv/bin/python -m pytest tests/test_real_run.py tests/test_optimizer_acceptance.py tests/test_product_cli.py tests/test_product_cli_remote.py -q` -> exit 0
- `rtk proxy ./.venv/bin/python -m pytest -q` -> exit 0
- `rtk proxy ./.venv/bin/python -m ruff check src tests` -> exit 0, all checks passed
- `rtk proxy git diff --check -- . ':!vendor' ':!.serena'` -> exit 0
- `rtk git -C ../ic-auto-opt-workflow-v0.1 status --short` -> only `?? .serena/`, no tracked release file touched

Code-level conclusion:
- B-10 source fix is acceptable at code level: local and remote adapter manifest writers now support `command_trace`.
- The trace is built from canonical `build_spectre_argv()` / `build_ocean_argv()` instead of reimplementing command construction.
- Result and metric Pydantic handoff models allow the new field.
- Tests cover local and remote success/failure paths and sanitization expectations.

Important remaining gate:
- B-10 is NOT workflow-accepted yet. It still requires a real local and remote workflow run, then inspection of real child `result_manifest.json` and `metrics/metric_result_manifest.json` artifacts to prove `command_trace` exists and records the effective `spectre_x`, `+preset=ax`, `+mt=<threads_per_run>`, `-format psfxl`, timeout, and OCEAN replay argv.
- During workflow gate, also re-check that no trace contains `parallel_jobs`, cshrc content, SSH command text, or secret environment data.

## 2026-06-15 Codex Update: B-08 and Native TuRBO B-07 Gate

### B-08 output_format contract

Status: code-level fixed in development package; real workflow gate pending.

Changes:
- `src/hermes_workflow/schemas.py` now allows only `Literal["psfxl"]` for `spectre.output_format`.
- `psfascii` now fails during schema/project config validation, before real-run preparation and before OCEAN metric request generation.
- `docs/PROJECT_WORKFLOW_OVERVIEW.md` now states `psfascii` is historical design record only, not current schema/backend allowed format.

Fresh verification:
- RED: `tests/test_schemas.py::test_spectre_rejects_psfascii_output_format` failed before schema change because `psfascii` did not raise `ValidationError`.
- GREEN: `rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py::test_spectre_rejects_psfascii_output_format -q` -> exit 0
- GREEN: `rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py tests/test_real_run.py tests/test_spectre_ocean_adapter.py -q` -> exit 0

### Native TuRBO B-07 report/workflow gate

Status: offline workflow gate passed; real EDA workflow gate still pending.

Root cause found during gate:
- A temporary native TuRBO workflow from `opt_requirement.md` produced `config/optimizer.yaml` with `algorithm: turbo` and `initialization: sobol`, but `reports/native_turbo_optimizer_report.json` and `reports/optimizer_effectiveness_audit.json` initially wrote `initialization: null` and `effective_initial_design: null`.
- Cause: not all `NativeTurboRunResult` return paths propagated `initialization` / `effective_initial_design`.

Changes:
- `src/hermes_workflow/native_turbo.py` now propagates `initialization` and `effective_initial_design` from runner results through public return wrappers and reports.
- `tests/test_native_turbo.py` now asserts `native_turbo_optimizer_report.json` records `initialization: sobol` and `effective_initial_design: sobol`.

Offline workflow evidence:
- Temporary project: `/tmp/ic_auto_opt_native_turbo_b07_workflow_gate`
- Source: `tests/fixtures/requirement_intake/valid_project/opt_requirement.md`
- Requirement edits only for the gate: `algorithm: turbo`, `max_evaluations: 10`, `batch_size: 2`, `initialization: sobol`.
- Generated `config/optimizer.yaml`: `algorithm: turbo`, `initialization: sobol`, `max_evaluations: 10`, `batch_size: 2`, `random_seed: 20260528`.
- `reports/native_turbo_optimizer_report.json`: `status: completed`, `evaluation_count: 10`, `initialization: sobol`, `effective_initial_design: sobol`.
- `reports/optimizer_effectiveness_audit.json`: `backend: native_turbo`, `initialization: sobol`, `effective_initial_design: sobol`.
- `reports/native_turbo_optimizer_evaluations.jsonl`: initialization phase rows followed by trust-region rows.

Fresh verification:
- RED: `rtk proxy ./.venv/bin/python -m pytest tests/test_native_turbo.py -q` failed after adding report assertions because report initialization was `None`.
- GREEN: `rtk proxy ./.venv/bin/python -m pytest tests/test_native_turbo.py -q` -> exit 0
- GREEN: `rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py tests/test_real_run.py tests/test_spectre_ocean_adapter.py tests/test_native_turbo.py tests/test_optimizer_flow.py tests/test_remote_optimizer_flow.py -q` -> exit 0
- GREEN: `rtk proxy ./.venv/bin/python -m pytest -q` -> exit 0
- GREEN: `rtk proxy ./.venv/bin/python -m ruff check src tests` -> exit 0
- GREEN: `rtk proxy git diff --check -- . ':!vendor' ':!.serena'` -> exit 0
- Release check: `rtk git -C ../ic-auto-opt-workflow-v0.1 status --short` -> only `?? .serena/`, no tracked release file touched

Remaining acceptance boundary:
- Native TuRBO is now accepted for code-level plus offline workflow artifact propagation.
- It still has not been accepted in a real Spectre/OCEAN workflow. If the next real workflow uses OpenBox, native TuRBO real-EDA behavior remains pending.
## 2026-06-15 Real Local/Remote OpenBox/TuRBO 40-Point Gate

Status: completed artifact inspection for four real workflows. This gate verifies variable propagation from `opt_requirement.md` / generated config into local and remote OpenBox/TuRBO execution artifacts. It does not perform release-package sync.

Valid workflow roots:
- Local OpenBox: `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed`
- Local native TuRBO: `/tmp/ic_auto_opt_real_gate_20260615_011933/local_turbo40_unsandboxed`
- Remote OpenBox cache: `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/79226ef09cc8b781`
- Remote native TuRBO cache: `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/e11d4b360776746e`

Discarded workflow root:
- `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40` was a sandboxed failed attempt. Cadence wrapper failed with `cannot create pipe [Operation not permitted]`; do not use it as an acceptance sample.

Run configuration confirmed from generated configs:
- `optimizer.algorithm`: OpenBox cases `openbox`; TuRBO cases `turbo`
- `optimizer.initialization`: `sobol`
- `optimizer.max_evaluations`: `40`
- `optimizer.batch_size`: `10`
- `optimizer.optimizer_cpu_threads`: `32`
- `spectre.engine`: `spectre_x`
- `spectre.preset`: `ax`
- `spectre.output_format`: `psfxl`
- `spectre.threads_per_run`: `10`
- `spectre.parallel_jobs`: `10`
- `spectre.timeout_s`: `7200`
- process corners: `ff`, `ss`, `tt`

Product CLI contract check:
- `./.venv/bin/ic-opt --help`: `--strategy`, `--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads-per-run`, and `--optimizer-cpu-threads` are absent.
- `--continue` is present.
- Four workflow `reports/optimizer_flow_run_report.json` files have `cli_overrides: null`.

B-07 initialization evidence:
- Local OpenBox: `state/optimizer_state.json` has `algorithm=openbox`, `initialization=sobol`, `current_evaluations=40`, `max_evaluations=40`, `batch_size=10`; `reports/optimizer_run_report.json` has `openbox.initialization=sobol`, `openbox.effective_init_strategy=sobol`, `openbox.max_evals=40`, `openbox.batch_size=10`.
- Remote OpenBox: same as local OpenBox.
- Local native TuRBO: `state/optimizer_state.json` has `algorithm=turbo`, `initialization=sobol`, `current_evaluations=40`, `max_evaluations=40`, `batch_size=10`; `reports/native_turbo_optimizer_report.json` has `initialization=sobol`, `effective_initial_design=sobol`, `evaluation_count=40`; `reports/optimizer_effectiveness_audit.json` has `backend=native_turbo`, `initialization=sobol`, `effective_initial_design=sobol`.
- Remote native TuRBO: same as local native TuRBO.

Evaluation log evidence:
- Local OpenBox `reports/optimizer_evaluations.jsonl`: 40 rows, batch counts `batch_001..batch_004 = 10 each`, `batch_worker_count=10` on 40/40 rows, `max_parallel_jobs=10` on 40/40 rows, `threads_per_run=10` on 40/40 rows.
- Remote OpenBox: same as local OpenBox.
- Local native TuRBO `reports/native_turbo_optimizer_evaluations.jsonl`: 40 rows, batch counts `10, 6, 10, 10, 4` across `batch_001..batch_005`; `batch_worker_count=10`, `max_parallel_jobs=10`, `threads_per_run=10` on 40/40 rows.
- Remote native TuRBO: same as local native TuRBO.

B-03/B-04 parent aggregate manifest evidence:
- Each valid workflow has 40 parent `runs/real/real_*/result_manifest.json` files, all `status=succeeded`.
- All 160 parent manifests have nested `simulator` metadata:
  `command_label=multi_testbench_aggregate`, `engine=spectre_x`, `preset=ax`, `output_format=psfxl`, `threads_per_run=10`, `timeout_s=7200`.
- This confirms remote timeout did not regress to 3600 and parent aggregate metadata inherits prepared/request Spectre metadata.

B-10 child command trace evidence:
- Each valid workflow has 360 child `result_manifest.json` files and 360 child `metrics/metric_result_manifest.json` files.
- All 1440 child result manifests and all 1440 child metric manifests have `command_trace`.
- Local traces use `execution_mode=local`; remote traces use `execution_mode=remote`.
- All child traces record `schema_version=1.0`, Spectre `timeout_s=7200`, `engine=spectre_x`, `preset=ax`, `threads_per_run=10`, `output_format=psfxl`.
- All child traces have canonical Spectre argv containing `+preset=ax`, `+mt=10`, `-format`, and `psfxl`.
- All child metric traces include OCEAN trace.
- Sanitization check across child traces found 0 manifests containing `cshrc`, `source `, `ssh `, `csh -fc`, or `parallel_jobs`.

Spectre/OCEAN execution outcome:
- All four workflows: 360/360 child Spectre result manifests are `status=succeeded`.
- Metric checks are partially failing, but OCEAN command traces are present. Counts:
  - Local OpenBox child metrics: 323 succeeded, 37 failed; parent metrics: 25 succeeded, 15 failed.
  - Remote OpenBox child metrics: 323 succeeded, 37 failed; parent metrics: 25 succeeded, 15 failed.
  - Local TuRBO child metrics: 246 succeeded, 114 failed; parent metrics: 9 succeeded, 31 failed.
  - Remote TuRBO child metrics: 255 succeeded, 105 failed; parent metrics: 9 succeeded, 31 failed.
- Optimizer evaluation rows use failure/constraint statuses as expected for bad candidates; this does not block variable propagation acceptance, but it should not be described as all metrics passing.

B-08 output_format evidence:
- `src/hermes_workflow/schemas.py` has `output_format: Literal["psfxl"]`.
- `src/hermes_workflow/metric_requests.py` still rejects non-OCEAN-ready output formats.
- Four real workflows generated `spectre.output_format=psfxl` and command traces show `-format psfxl`.

Optimizer CPU limit evidence:
- Requirement/generated config in all four workflows has `optimizer_cpu_threads=32`.
- OpenBox `reports/optimizer_run_report.json` records `openbox.optimizer_cpu_threads=32` for local and remote OpenBox.
- Source path: OpenBox backend calls `optimizer_cpu_thread_limits(optimizer_cpu_threads, set_environment=True, set_torch=False)` around batch/update/report phases.
- Source path: native TuRBO stores `self.optimizer_cpu_threads = optimizer.optimizer.optimizer_cpu_threads` and calls `optimizer_cpu_thread_limits(self.optimizer_cpu_threads, set_environment=False, ...)` in the native runner path.
- Artifact gap: neither native TuRBO report nor runtime artifacts record a threadpool/env snapshot; `optimizer_state.json` and `optimizer_effectiveness_audit.json` currently show `optimizer_cpu_threads: null` or omit it. Therefore CPU limit can be accepted as config/source-level applied, but not as fully runtime-observed from process artifacts. Add runtime threadpool/env evidence in a future hardening task if exact process-level CPU cap audit is required.

Verification commands run after the remote TuRBO adapter fix:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_remote_optimizer_flow.py tests/test_schemas.py tests/test_real_run.py tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py -q` -> exit 0.
- `rtk proxy ./.venv/bin/python -m pytest -q` -> exit 0.
- `rtk proxy ./.venv/bin/python -m ruff check src tests` -> `All checks passed!`.
- `rtk proxy git diff --check -- . ':!vendor' ':!.serena'` -> exit 0.
- `rtk git -C ../ic-auto-opt-workflow-v0.1 status --short` -> only `?? .serena/`; no tracked release package source file touched.

Additional fix found during this real gate:
- Remote native TuRBO initially failed because `run_batch_native_turbo_optimization()` did not accept the remote flow `adapter=` argument.
- Fixed in dev package: added `adapter: Callable[..., object] | None = None` to `run_batch_native_turbo_optimization(...)` and passed it into `make_real_candidate_batch_evaluator(...)`.
- Added regression test `tests/test_native_turbo.py::test_run_batch_native_turbo_optimization_accepts_adapter_argument`.

## 2026-06-15 Multi-Corner Flow Documentation and Remaining Bugs

Documentation added:
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`

Purpose:
- Explain the multi-process-corner optimizer flow to users.
- Clarify that the optimizer does not use a fixed `tt`/`ff`/`ss` corner.
- Clarify that each candidate runs all configured `testbench x corner` children, then `aggregate_multi_testbench_run()` collapses those child results into a single optimizer observation.
- Clarify that `objective_policy: worst_case` selects the largest internal minimize-objective among corners, and `constraint_policy: all_corners` marks a candidate failed if any corner violates constraints.

Current accepted items after real workflow artifact gate:
- B-01 product CLI override removal: workflow accepted. Product CLI has no `--strategy`, `--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads-per-run`, or `--optimizer-cpu-threads`; only `--continue` remains for continuation.
- B-03 remote timeout propagation: workflow accepted in the 40-point remote OpenBox/TuRBO runs. Remote artifacts use `timeout_s=7200`, not the old 3600 default.
- B-04 parent aggregate simulator metadata inheritance: workflow accepted. Parent aggregate manifests carry `simulator.command_label=multi_testbench_aggregate`, `engine=spectre_x`, `preset=ax`, `output_format=psfxl`, `threads_per_run=10`, `timeout_s=7200`.
- B-07 optimizer initialization pass-through: workflow accepted for OpenBox and native TuRBO with `initialization=sobol`; reports/state/evaluations show the effective initialization.
- B-08 output_format contract: code and workflow accepted. Schema only allows `psfxl`; real command traces show `-format psfxl`.
- B-10 Spectre/OCEAN command traceability: workflow accepted. All checked child result/metric manifests contain sanitized `command_trace` with correct local/remote execution mode and canonical Spectre/OCEAN argv.

Remaining bug / hardening items:
- ~~CPU thread limit runtime audit gap~~: Fixed as B-11 (see below). `optimizer_cpu_threads=32` is now proven at artifact level via `runtime_thread_limits` objects in both OpenBox and native TuRBO report + effectiveness audit artifacts.
- Multi-corner decision/insight report clarity gap: the core multi-corner optimizer flow appears correct, but `optimizer_decision_report.md` can be misleading when no feasible candidate exists. In the remote TuRBO run, the report says `Recommended run: none` and shows `Worst corner: n/a`, while per-run aggregation files do contain real corner data such as `real_002` selecting `ss` as the worst corner. The report should display corner failure distribution and representative `corner_objectives` even in `no_feasible_candidate` cases.
- Release package sync remains pending. Development package fixes have not been synced to `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`.
- `require_license_check` remains a later dedicated topic. It is a schema/template contract entry but still lacks real license-probe semantics.

Not considered bugs from the 40-point gate:
- Metric checks failed for many candidate points, but all child Spectre result manifests succeeded. The metric failures are candidate/circuit/constraint outcomes, not evidence that variable propagation failed.
- native TuRBO batch distribution was `10, 6, 10, 10, 4` while every evaluation row still recorded `batch_worker_count=10`, `max_parallel_jobs=10`, and `threads_per_run=10`. This is native TuRBO batch/duplicate/replacement behavior, not a failure to run 40 points.

## 2026-06-15 B-05 `require_license_check` Code-Level Review

Status: code-level accepted; real local/remote license-probe artifact gate still pending.

Root cause:
- `SpectreSettings.require_license_check` was present in schema and required by requirement intake, but local/remote doctor and real optimizer flows did not enforce it.
- The field was effectively a cosmetic contract entry.

Implemented in dev package:
- Added `src/hermes_workflow/license_probe.py`.
- Added local probe integration to `src/hermes_workflow/product_doctor.py`.
- Added remote probe integration to `src/hermes_workflow/remote_doctor.py`.
- Added local optimizer doctor gate in `src/hermes_workflow/optimizer_flow.py` for `real=True`.
- Added/updated tests:
  - `tests/test_license_probe.py`
  - `tests/test_product_doctor.py`
  - `tests/test_remote_doctor.py`
  - `tests/test_optimizer_flow.py`

Behavior:
- `require_license_check: true`: doctor runs license probe, writes `reports/license_probe_report.json`, embeds summary in `reports/ic_opt_doctor_report.json`, and fails closed if the probe fails.
- `require_license_check: false`: doctor writes a skipped license probe summary and does not execute the license probe.
- Remote doctor runs the probe on the remote host using the remote cshrc path and mirrors the report in the local remote-run cache.

Verification run by Codex after Claude's fix:
- `rtk proxy ./.venv/bin/python -m pytest tests/test_license_probe.py tests/test_product_doctor.py tests/test_remote_doctor.py tests/test_optimizer_flow.py -q` -> exit 0.
- `rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py tests/test_remote_optimizer_flow.py -q` -> exit 0.
- `rtk proxy ./.venv/bin/python -m pytest -q` -> exit 0.
- `rtk proxy ./.venv/bin/python -m ruff check src tests` -> `All checks passed!`.
- `rtk proxy git diff --check -- . ':!vendor' ':!.serena'` -> exit 0.
- `rtk git -C ../ic-auto-opt-workflow-v0.1 status --short` -> only `?? .serena/`; no tracked release source touched.

Remaining acceptance gate:
- Run real local and remote doctor/real workflow with `require_license_check: true`.
- Inspect:
  - `reports/license_probe_report.json`
  - `reports/ic_opt_doctor_report.json`
  - remote mirrored doctor/license reports
- Confirm actual `csh`, `spectre -V`, and `lmstat -a` behavior in the real Cadence environment.
- Do not call B-05 workflow-accepted until those real artifacts are inspected.

### 2026-06-15 B-05 Real Doctor Gate Attempt

Status: failed; B-05 workflow acceptance is blocked by a license probe script bug.

Commands:
- Local: `rtk proxy ./.venv/bin/ic-opt /tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed --doctor`
- Remote: `rtk proxy ./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 /home/zzchen/remote_opt/ic_auto_opt_real_gate_20260615_011933/remote_openbox40 --doctor`

Observed doctor results:
- Local doctor failed with `license_probe: spectre not found in PATH after sourcing cadence cshrc`.
- Remote doctor failed with `LICENSE_PROBE_FAILED`, detail `spectre not found in PATH after sourcing cadence cshrc`.
- Remote doctor simultaneously had `spectre_ocean: pass`, which proved the same remote cshrc can expose `spectre` and `ocean`.

Artifact paths inspected:
- Local: `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed/reports/license_probe_report.json`
- Local: `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed/reports/ic_opt_doctor_report.json`
- Remote cache: `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/79226ef09cc8b781/reports/license_probe_report.json`
- Remote cache: `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/79226ef09cc8b781/reports/ic_opt_doctor_report.json`

Manual environment proof:
- Local `csh -fc 'source .../cadence_env.csh; which spectre; which ocean; spectre -V | head -1; lmstat -a | grep -E "Users of" | head -5'` found Spectre/OCEAN and printed Spectre version plus lmstat license lines.
- Remote equivalent over SSH found Spectre/OCEAN and printed Spectre version plus lmstat license lines.

Root cause of false failure:
- `src/hermes_workflow/license_probe.py` uses Bash command substitution inside `csh -fc`:
  - line 107: `echo SPECTRE_PATH=$(which spectre 2>/dev/null || echo NOTFOUND);`
  - line 160: same remote probe pattern
- `csh` does not support `$()` command substitution. A direct smoke command returned `Illegal variable name.`
- Therefore the probe script fails before it can emit `SPECTRE_PATH=...`, causing parser/report to misdiagnose `spectre not found`.

Required fix:
- Rewrite local and remote license probe commands to be valid `csh` syntax, or invoke a POSIX shell after sourcing cshrc in a way that preserves the Cadence environment.
- Add RED tests that validate the generated probe command does not contain `$(` and that real/fake csh-compatible output parses correctly.
- Re-run local and remote doctor artifact gate after the fix.

### 2026-06-15 B-05 csh probe blocker fixed and workflow accepted

Status: accepted for development package. The previous real doctor blocker was
fixed and re-validated with real local and remote doctor gates. Release package
is still not synced.

Source verification:

- `src/hermes_workflow/license_probe.py` now builds the actual csh probe through
  `_build_csh_license_probe_script()`.
- The executable probe script uses csh-compatible syntax:
  `set sp=\`which spectre\`` and `spectre -V |& head -1`.
- The old Bash-only `$()` and `2>&1 |` patterns are not present in the
  executable probe script; they only remain in documentation/test text as
  forbidden examples.
- Local and remote probes share the same script builder.
- Failure diagnostics now preserve sanitized `raw_stderr` and return codes
  `spectre_version_rc` and `lmstat_rc`.

Fresh verification commands:

- `./.venv/bin/python -m pytest tests/test_license_probe.py tests/test_product_doctor.py tests/test_remote_doctor.py tests/test_optimizer_flow.py -q --disable-warnings`
  -> 91 passed, 13 warnings.
- `./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py tests/test_remote_optimizer_flow.py -q --disable-warnings`
  -> 43 passed, 13 warnings.
- `./.venv/bin/python -m pytest -q --disable-warnings`
  -> 1052 passed, 13 warnings.
- `./.venv/bin/python -m ruff check src tests`
  -> All checks passed.
- `git diff --check -- . ':!vendor' ':!.serena'`
  -> clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short`
  -> only `?? .serena/`; no tracked release source touched.

Real local doctor gate:

- Command:
  `rtk proxy ./.venv/bin/ic-opt /tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed --doctor`
- Result: exit 0, `doctor completed`.
- Requirement source had `require_license_check: true`.
- Artifact:
  `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed/reports/license_probe_report.json`
- Observed fields:
  `status=pass`, `execution_mode=local`, `require_license_check=true`,
  `spectre_path=/opt/eda/cadence/spectre_2310_242/bin/spectre`,
  `spectre_version_rc=0`, `lmstat_available=true`, `lmstat_rc=0`,
  `license_feature_count=88`, `issues=[]`, `raw_stderr=""`.
- Doctor report embeds `license_probe` with status `pass`.

Real remote doctor gate:

- Command:
  `rtk proxy ./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 /home/zzchen/remote_opt/ic_auto_opt_real_gate_20260615_011933/remote_openbox40 --doctor`
- Result: exit 0, `doctor completed`.
- Only non-fatal structured warning:
  `REMOTE_PARALLELISM_HIGH`.
- Requirement source had `require_license_check: true`.
- Local cache artifact:
  `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/79226ef09cc8b781/reports/license_probe_report.json`
- Observed fields:
  `status=pass`, `execution_mode=remote`, `require_license_check=true`,
  `spectre_path=/opt/eda/cadence/spectre_2310_242/bin/spectre`,
  `spectre_version_rc=0`, `lmstat_available=true`, `lmstat_rc=0`,
  `license_feature_count=88`, `issues=[]`, `raw_stderr=""`.
- Remote doctor report embeds `license_probe` with status `pass`.

Conclusion: B-05 is workflow-accepted in dev for the doctor gate. It proves
`require_license_check: true` is parsed from requirement, triggers a real
Cadence csh environment probe, observes `spectre -V` and `lmstat -a`, writes
artifacts, embeds the result in local/remote doctor reports, and blocks only on
actual probe failures. It does not reserve licenses and does not prove future
per-child Spectre jobs cannot hit transient license exhaustion.

## 2026-06-15 B-11 CPU Thread Limit Runtime Audit

Status: code-level accepted in development package; workflow-level acceptance
is still pending.

Root cause:
- `optimizer.optimizer_cpu_threads` was present in schema/templates/config and
  source paths. OpenBox and native TuRBO called `optimizer_cpu_thread_limits(...)`,
  but real workflow artifacts did not prove runtime effectiveness.
- OpenBox `reports/optimizer_run_report.json` recorded `openbox.optimizer_cpu_threads=32`
  as a config echo, not a runtime observation.
- native TuRBO `reports/native_turbo_optimizer_report.json` had no `optimizer_cpu_threads`
  field at all.
- No artifact contained `runtime_thread_limits`, threadpool info, env var snapshot,
  or optimizer env audit.

Code-level fix (2026-06-15):

1. Added `OptimizerThreadAudit` frozen dataclass to `src/hermes_workflow/optimizer_resources.py`:
   - Fields: `source`, `requested_threads`, `effective_threads`, `backend`,
     `execution_mode`, `process_scope`, `env_vars`, `threadpoolctl`, `torch`, `issues`.
   - `to_dict()` method for JSON serialization.
   - `threadpoolctl` dict: `available`, `libraries` (with `user_api`, `internal_api`,
     `num_threads`, `prefix` per library).
   - `torch` dict: `available`, `num_threads`, `num_interop_threads`.
   - `issues` list: records unavailability of threadpoolctl/torch explicitly.

2. Modified `optimizer_cpu_thread_limits(...)`:
   - Now yields `OptimizerThreadAudit` instead of `None`.
   - Old usage `with optimizer_cpu_thread_limits(...):` still works.
   - New usage `with optimizer_cpu_thread_limits(...) as audit:` captures audit.
   - New kwargs: `backend` (default `"unknown"`), `execution_mode` (default `"local"`).
   - Audit snapshot is captured **inside** the active limit context, after env vars
     and threadpoolctl limits are applied.
   - `effective_threads` = min of requested threads and observed threadpool/torch threads.
   - If threadpoolctl or torch is unavailable, records `available=False` with an issue
     instead of silently fabricating proof.

3. OpenBox backend (`src/hermes_workflow/openbox_backend.py`):
   - First `optimizer_cpu_thread_limits(...)` call in `_run_openbox_batches()` captures
     audit with `backend="openbox"`, `execution_mode=execution_mode`.
   - Audit written into `reports/optimizer_run_report.json` as `runtime_thread_limits`.
   - Audit written into `reports/optimizer_effectiveness_audit.json` as `runtime_thread_limits`.
   - `_write_openbox_effectiveness_audit()` accepts optional `runtime_thread_limits`.
   - `write_openbox_reports()` accepts optional `runtime_thread_limits`.

4. native TuRBO backend (`src/hermes_workflow/native_turbo.py`):
   - `NativeTurboRunner.run()` captures audit with `backend="native_turbo"`,
     `execution_mode="local"`.
   - `NativeTurboBatchRunner.run()` captures audit similarly.
   - `write_native_turbo_reports()` accepts `optimizer_cpu_threads` and
     `runtime_thread_audit` kwargs.
   - Report payload includes `optimizer_cpu_threads` and `runtime_thread_limits`.
   - Effectiveness audit includes `runtime_thread_limits`.
   - Native TuRBO uses `set_environment=False` (only threadpoolctl controls threads),
     so env_vars in audit reflect actual runtime state (may be `None`).

5. Remote parity:
   - Remote flow does NOT override CPU threads. The audit still applies to the
     local optimizer/orchestrator Python process.
   - Remote audit must say `execution_mode=remote`, `process_scope=local_optimizer_process`.
   - Spectre child process threads remain controlled by `spectre.threads_per_run` and `+mt`.

Tests added:
- `tests/test_optimizer_resources.py` (14 tests):
  - `OptimizerThreadAudit` dataclass with `to_dict()`.
  - `optimizer_cpu_thread_limits(32)` yields audit object.
  - Inside context, env vars are set; after exit, restored.
  - Backend and execution_mode recording.
  - Fake threadpoolctl path with library summaries.
  - Fake torch path with num_threads/num_interop_threads.
  - threadpoolctl unavailable records `available=False` with issue.
  - Old usage without `as` clause still works.
  - `set_environment=False` still works.
  - `effective_threads` reduced by threadpoolctl.
- `tests/test_openbox_backend.py` (3 tests):
  - `test_openbox_fake_run_writes_runtime_thread_audit`
  - `test_openbox_report_contains_runtime_thread_limits`
  - `test_openbox_separate_effectiveness_audit_file_has_runtime_thread_limits`
- `tests/test_native_turbo.py` (3 tests):
  - `test_native_turbo_report_contains_optimizer_cpu_threads`
  - `test_native_turbo_report_contains_runtime_thread_limits`
  - `test_native_turbo_effectiveness_audit_contains_runtime_thread_limits`
- `tests/test_remote_optimizer_flow.py` (1 test):
  - `test_remote_openbox_audit_records_remote_execution_mode`
- Updated existing test:
  - `test_run_batch_native_turbo_optimization_applies_optimizer_cpu_thread_limit`
    now expects `backend="native_turbo"` and `execution_mode="local"` kwargs.

Verification commands:
- `./.venv/bin/python -m pytest tests/test_optimizer_resources.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_remote_optimizer_flow.py -q` -> 129 passed, 13 warnings
- `./.venv/bin/python -m pytest -q` -> 1073 passed, 13 warnings
- `./.venv/bin/python -m ruff check src tests` -> All checks passed
- `git diff --check -- . ':!vendor' ':!.serena'` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> only `?? .serena/`; no tracked release source touched

Modified files:
- `src/hermes_workflow/optimizer_resources.py`: added `OptimizerThreadAudit`, modified `optimizer_cpu_thread_limits` to yield audit
- `src/hermes_workflow/openbox_backend.py`: capture and propagate runtime thread audit
- `src/hermes_workflow/native_turbo.py`: capture and propagate runtime thread audit
- `tests/test_optimizer_resources.py`: new test file (14 tests)
- `tests/test_openbox_backend.py`: 3 new audit tests
- `tests/test_native_turbo.py`: 3 new audit tests + 1 existing test updated
- `tests/test_remote_optimizer_flow.py`: 1 new remote parity test
- `docs/CURRENT_BUGFIX_PROGRESS.md`: this update

Exact report fields added:
- OpenBox `reports/optimizer_run_report.json`:
  - `runtime_thread_limits`: object with `source`, `requested_threads`, `effective_threads`,
    `backend`, `execution_mode`, `process_scope`, `env_vars`, `threadpoolctl`, `torch`, `issues`
- OpenBox `reports/optimizer_effectiveness_audit.json`:
  - `runtime_thread_limits`: same object as above
- native TuRBO `reports/native_turbo_optimizer_report.json`:
  - `optimizer_cpu_threads`: int (e.g., 32)
  - `runtime_thread_limits`: object with same fields as above, `backend="native_turbo"`
- native TuRBO `reports/optimizer_effectiveness_audit.json`:
  - `runtime_thread_limits`: same object as above

Workflow acceptance still required:
- Run real local and remote OpenBox and native TuRBO workflows and inspect
  `reports/optimizer_run_report.json`, `reports/native_turbo_optimizer_report.json`,
  and `reports/optimizer_effectiveness_audit.json` for the `runtime_thread_limits`
  field.
- Verify `env_vars`, `threadpoolctl`, and `torch` fields reflect actual runtime state.
- Verify `effective_threads` matches observed threadpool/torch threads.
- Verify `execution_mode` is `"fake"`/`"real"`/`"remote"` as appropriate.
- Verify `backend` is `"openbox"` or `"native_turbo"` as appropriate.
- Do not call B-11 fully accepted until real artifact inspection proves
  runtime thread limits are observed in production workflow output.

### 2026-06-15 B-11 Codex independent code-level verification

Status: code-level accepted in the development package. Workflow-level
acceptance is still pending because the existing 40-point local/remote
OpenBox/TuRBO artifacts were generated before B-11 and still do not contain
`runtime_thread_limits`.

Independent source/runtime checks:

- `optimizer_cpu_thread_limits(7, backend="smoke", execution_mode="local")`
  was executed directly.
- Inside the active context all optimizer thread environment variables were
  `"7"`.
- After context exit the previous environment was restored.
- Audit payload contained:
  `source`, `requested_threads`, `effective_threads`, `backend`,
  `execution_mode`, `process_scope`, `env_vars`, `threadpoolctl`, `torch`,
  `issues`.
- Observed payload values:
  `source=optimizer.optimizer_cpu_threads`, `backend=smoke`,
  `execution_mode=local`, `process_scope=local_optimizer_process`,
  `requested_threads=7`, `effective_threads=7`, `env_vars.OMP_NUM_THREADS=7`.

Fresh verification commands:

- `./.venv/bin/python -m pytest tests/test_optimizer_resources.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_remote_optimizer_flow.py -q --disable-warnings`
  -> 129 passed, 13 warnings.
- `./.venv/bin/python -m pytest -q --disable-warnings`
  -> 1073 passed, 13 warnings.
- `./.venv/bin/python -m ruff check src tests`
  -> All checks passed.
- `git diff --check -- . ':!vendor' ':!.serena'`
  -> clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short`
  -> only `?? .serena/`; no tracked release source touched.

Old real artifact check:

- `/tmp/ic_auto_opt_real_gate_20260615_011933/local_openbox40_unsandboxed/reports/optimizer_run_report.json`
  has no `runtime_thread_limits`; it only has `openbox.optimizer_cpu_threads=32`.
- `/tmp/ic_auto_opt_real_gate_20260615_011933/local_turbo40_unsandboxed/reports/native_turbo_optimizer_report.json`
  has no `runtime_thread_limits`.
- `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/79226ef09cc8b781/reports/optimizer_run_report.json`
  was generated before B-11 and cannot prove the new audit.
- `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/e11d4b360776746e/reports/native_turbo_optimizer_report.json`
  was generated before B-11 and cannot prove the new audit.

Next acceptance gate:

- Re-run real local OpenBox, local native TuRBO, remote OpenBox, and remote
  native TuRBO after B-11.
- Inspect optimizer reports and effectiveness audits for
  `runtime_thread_limits`.
- Required fields:
  `requested_threads=32`, `effective_threads` not greater than 32,
  `process_scope=local_optimizer_process`, env vars set to `"32"`,
  backend correct for OpenBox/native TuRBO, execution mode correct for
  local/remote.

### 2026-06-16 B-11 Real 30-Point Workflow Gate

Status: CPU thread limit runtime audit is workflow-accepted for the actual
thread-limit effect in dev. Four real 30-evaluation workflows completed:

- Local OpenBox:
  `/tmp/ic_auto_opt_b11_real_gate_20260615_214457_local_openbox30`
- Local native TuRBO final valid run:
  `/tmp/ic_auto_opt_b11_real_gate_20260616_012434_local_turbo30_batchenvfix`
- Remote OpenBox local cache:
  `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/0a6bb1742a1bd096`
- Remote native TuRBO final valid local cache:
  `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/1fc85e90d34cd484`

Input contract:

- No CLI optimizer/workload/resource overrides were used.
- `max_evaluations=30`, `batch_size=10`, `optimizer_cpu_threads=32`,
  `parallel_jobs=10`, `threads_per_run=10`, `output_format=psfxl`,
  `require_license_check=true`, and corners `tt, ss, ff` came from
  `opt_requirement.md`.
- Remote runs required `--cadence-cshrc <absolute remote cshrc>` to identify
  the Cadence environment file. This is an environment-file locator, not an
  optimizer/workload override.

Blockers found and fixed during the gate:

- Remote `--real` failed after remote doctor because `remote_optimizer_flow`
  invoked local `optimize_project()` with the default local product doctor and
  relative `cadence_cshrc=Path("remote-cadence-env.csh")`. RED test:
  `tests/test_remote_optimizer_flow.py::test_optimize_remote_project_runs_doctor_prepare_openbox_and_sync`
  failed with local doctor status `fail`. Fix: inject a remote-safe
  `run_product_doctor` service because `run_remote_doctor()` already gates
  remote cshrc/license/toolchain before local optimizer orchestration.
- Native TuRBO real batch path still called
  `optimizer_cpu_thread_limits(..., set_environment=False)`, so real
  `runtime_thread_limits.env_vars` were all `null`. RED tests were updated for
  batch/native reports; fix: both native TuRBO runner paths now use
  `set_environment=True`.

Final B-11 runtime audit observations:

- Local OpenBox `reports/optimizer_run_report.json`:
  `evaluation_count=30`, `openbox.optimizer_cpu_threads=32`,
  `runtime_thread_limits=(backend=openbox, execution_mode=real,
  process_scope=local_optimizer_process, requested_threads=32,
  effective_threads=32)`, all optimizer env vars are `"32"`, `issues=[]`,
  `threadpoolctl.available=true`, `torch.num_threads=32`.
- Local native TuRBO `reports/native_turbo_optimizer_report.json`:
  `evaluation_count=30`, `optimizer_cpu_threads=32`,
  `runtime_thread_limits=(backend=native_turbo, execution_mode=local,
  process_scope=local_optimizer_process, requested_threads=32,
  effective_threads=32)`, all optimizer env vars are `"32"`, `issues=[]`,
  `threadpoolctl.available=true`, `torch.num_threads=32`.
- Remote OpenBox cache `reports/optimizer_run_report.json`:
  `evaluation_count=30`, `openbox.optimizer_cpu_threads=32`,
  `runtime_thread_limits=(backend=openbox, execution_mode=real,
  process_scope=local_optimizer_process, requested_threads=32,
  effective_threads=32)`, all optimizer env vars are `"32"`, `issues=[]`,
  `threadpoolctl.available=true`, `torch.num_threads=32`.
- Remote native TuRBO cache `reports/native_turbo_optimizer_report.json`:
  `evaluation_count=30`, `optimizer_cpu_threads=32`,
  `runtime_thread_limits=(backend=native_turbo, execution_mode=local,
  process_scope=local_optimizer_process, requested_threads=32,
  effective_threads=32)`, all optimizer env vars are `"32"`, `issues=[]`,
  `threadpoolctl.available=true`, `torch.num_threads=32`.
- All four `reports/optimizer_effectiveness_audit.json` files also contain
  matching `runtime_thread_limits` with `requested_threads=32` and
  `effective_threads=32`.

Other gate observations:

- All four flows completed 30 optimizer evaluations.
- All four produced 300 `result_manifest.json` files:
  30 parent aggregate manifests and 270 child Spectre manifests.
- All 300 `result_manifest.json` files per flow had `status=succeeded`.
- All child Spectre result manifests had `command_trace`.
- Child command traces had `+mt=10`, `output_format=psfxl`, and no sanitized
  trace leak of `cshrc`, `source`, `ssh`, or `csh -fc`.
- Aggregate parent result/metric manifests still do not all carry
  `command_trace`; B-10 was accepted for child Spectre/OCEAN artifacts, but
  parent aggregate command traceability remains a possible future enhancement.
- License probe passed in all four runs:
  local reports `execution_mode=local`, remote reports `execution_mode=remote`,
  `spectre_version_rc=0`, `lmstat_rc=0`, `license_feature_count=88`,
  `issues=[]`.
- Remote doctor still reports non-fatal `REMOTE_PARALLELISM_HIGH` because
  `parallel_jobs=10`.

Remaining audit-label caveat:

- `runtime_thread_limits.execution_mode` currently records backend execution
  semantics (`real` for OpenBox, `local` for native TuRBO), not transport mode
  (`remote`). `process_scope=local_optimizer_process` is correct and the CPU
  limit effect is proven, but if we want the field itself to distinguish remote
  transport, add a small report-label follow-up.

Fresh verification after code fixes:

- `./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py tests/test_optimizer_resources.py tests/test_openbox_backend.py tests/test_native_turbo.py -q --disable-warnings`
  -> 135 passed, 13 warnings.
- `./.venv/bin/python -m pytest -q --disable-warnings`
  -> 1073 passed, 13 warnings.
- `./.venv/bin/python -m ruff check src tests`
  -> All checks passed.
- `git diff --check -- . ':!vendor' ':!.serena'`
  -> clean.
- `git -C ../ic-auto-opt-workflow-v0.1 status --short`
  -> only `?? .serena/`; no tracked release source touched.
## 2026-06-16 B-11 Follow-Up: Runtime Audit Transport Mode

Status: code-level fix completed; targeted tests green. No new real Spectre run
was launched for this report-label follow-up.

Root cause:
- `runtime_thread_limits.execution_mode` was being used ambiguously in user-facing
  audit reports.
- For OpenBox it describes backend execution semantics (`fake`/`real`).
- For native TuRBO it describes local optimizer process execution.
- Remote transport was not represented separately, so remote native TuRBO reports
  could look like `execution_mode=local` even though the workflow was remote.

Spec:
- Preserve existing `execution_mode` as backend execution mode.
- Add `runtime_thread_limits.transport_mode` with values `local` or `remote`.
- Keep `process_scope=local_optimizer_process`; the audit proves limits in the
  optimizer orchestration process, not Spectre child process limits.
- Do not add any CLI flag or change requirement variable sourcing.
- Do not change CPU limiting behavior, optimizer behavior, Spectre command args,
  or release package files.

Implementation:
- `OptimizerThreadAudit` now serializes `transport_mode`, defaulting to `local`.
- `optimizer_cpu_thread_limits(..., transport_mode="remote")` records remote
  workflow transport while keeping backend `execution_mode` unchanged.
- `remote_optimizer_flow` passes `transport_mode="remote"` into remote OpenBox,
  remote native TuRBO, and remote continuation OpenBox wrappers.
- OpenBox and native TuRBO reports inherit the field through
  `runtime_thread_limits.to_dict()`.

Validation:
- RED: `tests/test_optimizer_resources.py` failed with missing
  `transport_mode` and unexpected keyword argument before implementation.
- GREEN targeted command:
  `rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_resources.py tests/test_openbox_backend.py::test_openbox_fake_run_writes_runtime_thread_audit tests/test_openbox_backend.py::test_openbox_report_contains_runtime_thread_limits tests/test_native_turbo.py::test_native_turbo_report_contains_runtime_thread_limits tests/test_remote_optimizer_flow.py -q`
  exited 0.

Current expected audit semantics:
- Local OpenBox: `backend=openbox`, `execution_mode=fake|real`,
  `transport_mode=local`.
- Remote OpenBox: `backend=openbox`, `execution_mode=real`,
  `transport_mode=remote`.
- Local native TuRBO: `backend=native_turbo`, `execution_mode=local`,
  `transport_mode=local`.
- Remote native TuRBO: `backend=native_turbo`, `execution_mode=local`,
  `transport_mode=remote`.

## 2026-06-16 Parent Aggregate Command Trace + Release Sync

Status: completed. Multi-corner decision/report clarity was intentionally not
changed in this task.

Parent aggregate command trace enhancement:
- B-10 originally accepted child Spectre/OCEAN `command_trace` in child
  `result_manifest.json` and `metric_result_manifest.json`.
- Parent aggregate manifests previously kept `child_results` and
  `child_metric_results`, but did not persist a parent-level trace index.
- `multi_testbench_aggregation.py` now loads child result/metric
  `command_trace` fields and writes a parent aggregate `command_trace` into
  both parent `runs/real/<run_id>/result_manifest.json` and parent
  `runs/real/<run_id>/metrics/metric_result_manifest.json`.
- Parent trace shape:
  - `schema_version: "1.0"`
  - `execution_mode: local|remote|mixed`
  - `aggregate.kind: "multi_testbench_parent"`
  - `aggregate.children[]` with child `testbench`, child result/metric
    manifest paths, and copied sanitized child result/metric command traces.
- No command is re-constructed at the parent level; the parent only indexes
  child traces already written by local/remote Spectre/OCEAN adapters.

RED/GREEN evidence:
- RED:
  `tests/test_multi_testbench_aggregation.py::test_aggregate_parent_manifests_include_child_command_trace`
  failed with `KeyError: 'command_trace'`.
- GREEN targeted dev:
  `rtk proxy ./.venv/bin/python -m pytest tests/test_multi_testbench_aggregation.py tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py -q --disable-warnings`
  -> `121 passed, 13 warnings`.
- GREEN full dev:
  `rtk proxy ./.venv/bin/python -m pytest -q --disable-warnings`
  -> `1075 passed, 13 warnings`.
- Dev lint/check:
  `rtk proxy ./.venv/bin/python -m ruff check src tests` -> `All checks passed!`
  `git diff --check -- . ':!vendor' ':!.serena'` -> clean.

Release sync:
- Synced from dev into `../ic-auto-opt-workflow-v0.1`:
  `src/hermes_workflow/`, `tests/`, `docs/`, `agent_runtime/`, `tools/`,
  `skills/`, `claude_skills/`, `.mcp.json`, and root release/package files.
- Excluded cache/local state: `__pycache__`, `.pytest_cache`, `.ruff_cache`,
  `.serena`.
- Verified `src/hermes_workflow` and `tests` are byte-equivalent by
  `diff -qr` after excluding cache/local state.
- Release validation:
  `rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest -q --disable-warnings`
  -> `1075 passed, 13 warnings`.
- Release lint/check:
  `rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests`
  -> `All checks passed!`
  `git diff --check -- . ':!vendor' ':!.serena'` -> clean.

## 2026-06-16 Release Documentation Contract Sync

Status: documentation/release sync in progress at the time this checkpoint was
written; no real Spectre/OCEAN workflow was launched for this docs-only step.

Purpose:

- Ensure release package docs describe the current product contract after B-01,
  B-03/B-04, B-05, B-07, B-08, B-10, parent aggregate traceability, and B-11.
- Prevent stale historical command examples from being mistaken for current
  product usage.

Current release documentation contract:

- Initial product real optimization is `ic-opt PROJECT_DIR --real`.
- `opt_requirement.md` / generated config is the only first-run entry for
  `max_evaluations`, `batch_size`, `parallel_jobs`, `threads_per_run`,
  `optimizer_cpu_threads`, optimizer algorithm/strategy, initialization,
  process corners, output format, retention policy, metrics, and constraints.
- Product CLI continuation keeps exactly one budget delta:
  `ic-opt PROJECT_DIR --real --continue N`.
- Multi-corner is configured in `opt_requirement.md` under `Process Corners`,
  where corners, objective policy, and constraint policy are declared.
- Release examples include:
  - `examples/spectre_maestro_project/opt_requirement.multi_corner.md`
  - `examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`
- Supported optimizer modes are documented:
  - `algorithm: openbox`, `strategy: openbox_auto`
  - `algorithm: openbox`, `strategy: openbox_gp_eic`
  - `algorithm: openbox`, `strategy: openbox_prf_eic`
  - `algorithm: turbo`, `strategy: turbo_trust_region`
  - `algorithm: random`, `strategy: random_baseline` for diagnostic baseline use
- TuRBO dependency documentation now includes `vendor/TuRBO`, `scipy`,
  `threadpoolctl`, `torch`, and `gpytorch`.

Documentation files updated:

- `README.md`
- `RELEASE_NOTES_v0.1.7.md`
- `RELEASE_NOTES_v0.1.md`
- `RELEASE_NOTES_v0.1.1.md`
- `RELEASE_NOTES_v0.1.2.md`
- `requirements-product.txt`
- `pyproject.toml`
- `docs/PRODUCT_RELEASE_CHECKLIST.md`
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`
- `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md`
- `docs/AGENT_INTEGRATION_STATUS.md`
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- `docs/AGENT_USER_QUICKSTART_CN.md`
- `docs/USER_GUIDE_CN.md`
- `docs/OPTIMIZER_ALGORITHM_MODES.md`
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`
- `skills/ic-opt/SKILL.md`
- `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

Historical-doc handling:

- Older evidence logs, debug notes, and implementation plans that still preserve
  obsolete `--max-evals` / `--batch-size` / `--parallel-jobs` command examples
  now carry a top-level historical command notice.
- `docs/CURRENT_TASK_STATE.json` remains a JSON state snapshot; it is not a
  release usage manual.

Validation completed for this checkpoint:

- Dev full pytest:
  `rtk proxy ./.venv/bin/python -m pytest -q --disable-warnings`
  -> `1075 passed, 13 warnings`.
- Dev ruff:
  `rtk proxy ./.venv/bin/python -m ruff check src tests`
  -> `All checks passed!`
- Dev diff check:
  `git diff --check -- . ':!vendor' ':!.serena'`
  -> clean.
- Release full pytest:
  `rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest -q --disable-warnings`
  -> `1075 passed, 13 warnings`.
- Release ruff:
  `rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests`
  -> `All checks passed!`
- Release diff check:
  `git diff --check -- . ':!vendor' ':!.serena'`
  -> clean.
- Dev/release docs/examples/skills sync:
  `diff -qr` clean for `examples/` and `skills/`; `docs/` clean when excluding
  historical `docs/toolchain_evidence`.
- Agent skill sync:
  `cmp -s src/hermes_workflow/agent_skills/ic-opt/SKILL.md ../ic-auto-opt-workflow-v0.1/src/hermes_workflow/agent_skills/ic-opt/SKILL.md`
  -> `cmp_exit:0`.
- Release contract grep confirmed the current product contract, multi-corner
  examples, fixed-bug release notes, TuRBO dependencies, and supported optimizer
  modes are present in release docs.

Known documentation boundary:

- `docs/toolchain_evidence` contains historical Cadence evidence files. It is
  excluded from documentation contract sync checks because it is raw tool
  evidence, not current release usage documentation.
## 2026-06-16 Runtime Adapter Maintenance Check

Scope: verify whether `hermes-workflow install-runtime-adapter` is still
compatible with the current `ic-opt` product contract.

Finding: the installer/status mechanism was still functional, but the installed
Claude/OpenCode agent content was stale. The old assets still described the
runtime-native subagent route as the main path and included broken markdown or
shell snippets. Some user-facing docs also promoted runtime adapter installation
as the first path instead of the current product CLI plus `skills/ic-opt/SKILL.md`
route.

Fix:

- Rewrote `skills/ic-opt/SKILL.md` as the current agent contract.
- Rewrote `claude_skills/ic-opt/SKILL.md` to match the current product CLI,
  requirement-only initial-run settings, remote profile behavior, psfxl,
  license probe, command trace, CPU thread cap, and artifact inspection.
- Rewrote OpenCode command/agent assets under `agent_runtime/opencode/`.
- Updated `README.md`, `agent_runtime/README.md`, `claude_skills/README.md`,
  `docs/AGENT_INTEGRATION_STATUS.md`,
  `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`,
  `docs/AGENT_USER_QUICKSTART_CN.md`, and
  `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`.
- Extended `tests/test_agent_runtime.py` so installed assets and the main skill
  must contain the current contract and must not reintroduce old CLI/runtime
  entry strings.

Verification:

- Dev: `./.venv/bin/python -m pytest tests/test_agent_runtime.py -q` passed.
- Dev smoke: installed Claude/OpenCode adapters into
  `/tmp/ic_opt_runtime_adapter_check_20260616`, then
  `runtime-adapter-status` reported all expected assets present.
- Dev smoke content grep: installed assets contained `opt_requirement.md`,
  `--continue N`, `--ssh-profile PROFILE`, `output_format: psfxl`,
  `command_trace`, `license_probe_report.json`, `optimizer CPU cap`,
  `Process Corners`, `openbox_gp_eic`, `openbox_prf_eic`,
  `turbo_trust_region`, and `0.1u`; stale runtime/CLI strings were absent.
- Release: copied the same source/docs/tests into
  `ic-auto-opt-workflow-v0.1`.
- Release: `../ic-auto-opt-workflow/.venv/bin/python -m pytest
  tests/test_agent_runtime.py -q` passed from the release worktree.
- Release smoke: with `PYTHONPATH=src`, installed Claude/OpenCode adapters into
  `/tmp/ic_opt_runtime_adapter_release_check_20260616`, then
  `runtime-adapter-status` reported all expected assets present and content grep
  matched the same current-contract checks.

Decision: the adapter entrypoint can remain in the codebase as an optional
asset installer. It should not be promoted as the primary user path. The primary
agent path is: give the agent `skills/ic-opt/SKILL.md` and `PROJECT_DIR`; the
agent operates `ic-opt PROJECT_DIR --real` / `--continue N` and verifies
workflow artifacts.

## 2026-06-16 Release Documentation Cleanup

Scope: clean the release package documentation so GitHub users see only current
v0.1.7 docs, not historical engineering logs.

Actions in `ic-auto-opt-workflow-v0.1`:

- Removed release-package historical/debug documentation: old Claude handoff
  notes, execution progress logs, compact resume checkpoint, debug directories,
  superpowers plans/specs, simulations, toolchain evidence, build artifacts,
  pytest cache files, old release notes, and stale architecture/status notes.
- Reduced release markdown/txt files to the current publishable set, excluding
  vendored third-party docs.
- Rewrote current docs that were stale or visibly generated:
  `RELEASE_NOTES_v0.1.7.md`, `README.md`,
  `docs/AGENT_INTEGRATION_STATUS.md`,
  `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`,
  `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md`,
  `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`,
  `docs/USER_GUIDE_CN.md`, `docs/TROUBLESHOOTING_CN.md`,
  `docs/ROLE_MODEL_AND_TERMINOLOGY.md`,
  `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`, and
  `docs/PRODUCT_RELEASE_CHECKLIST.md`.
- Synchronized `src/hermes_workflow/agent_skills/ic-opt/SKILL.md` with the
  current release `skills/ic-opt/SKILL.md`, so the package no longer carries
  two conflicting skill contracts.

Verification:

- Release docs grep, excluding `vendor/`, has no matches for stale product CLI
  strings, old runtime/subagent entry claims, deleted historical document names,
  or the humanizer hard-pattern scan terms used in this pass.
- Markdown fence balance check passed for all release markdown/txt files outside
  `vendor/`.
- `../ic-auto-opt-workflow/.venv/bin/python -m pytest
  tests/test_agent_runtime.py -q` passed from the release worktree.
- `../ic-auto-opt-workflow/.venv/bin/python -m ruff check
  tests/test_agent_runtime.py` passed.
- `git diff --check -- . ':!vendor' ':!.serena'` passed in the release
  worktree.

## 2026-06-16 Release requirement templates and docs resync

Reason: release examples and docs had drifted from the verified real workflow requirement. The most serious drift was an invalid OCEAN example `getData("NF" "pnoise")`; the verified requirement and OCEAN probe use `getData("NF" ?result "pnoise")`.

Verified mother requirement used for regeneration:
`/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/1fc85e90d34cd484/opt_requirement.md`.

Evidence for using this as the mother requirement:
- project contains generated `config/*.yaml` and real run artifacts;
- `runs/real` contains 30 `metric_result_manifest.json` files;
- `cg_nf/tt/psf` from `real_028` was opened by real OCEAN;
- OCEAN confirmed `getData("NF" ?result "pnoise")` returns a waveform with 561 points and can be exported to CSV;
- `getData("NF" "pnoise")` fails in OCEAN with `getData: extra arguments or keyword missing - ("pnoise")`.

Actions completed:
- Regenerated four release/dev requirement templates from the verified Mixer requirement:
  - single testbench, single corner: `opt_requirement.md`;
  - single testbench, multi-corner: `opt_requirement.multi_corner.md`;
  - multi-testbench, single corner: `opt_requirement.multi_testbench.md`;
  - multi-testbench, multi-corner: `opt_requirement.multi_tb_corner.md`.
- Synchronized release examples and packaged templates for the four requirement files.
- Rewrote `OPT_REQUIREMENT_README.md`, root `README.md`, release notes, user guide, agent docs, optimizer mode guide, process-corner guide, troubleshooting guide, toolchain reference, handoff guide, release checklist, role terminology, GitHub publishing guide, contributing guide, requirements files, example metric notes, constraints guidance, and `skills/ic-opt/SKILL.md`.
- Removed user-facing doc references to stale runtime adapter/Claude skill entry points, stale CLI override flags, `psfascii`, `openbox_auto` as recommended/default mode, and the wrong NF formula.
- Updated requirement-intake tests so the release tests validate the current explicit-strategy templates instead of old `openbox_auto` expectations.

Verification:
- Four release requirement templates parse under current `check-requirement`; expected failures are only placeholder `maestro_point_root/netlist/input.scs is missing` messages.
- Release examples and packaged templates have identical hashes for `METRICS.md`, `OPT_REQUIREMENT_README.md`, `constraints.md`, and the four requirement templates.
- Release product docs grep has no matches for wrong NF formula, stale runtime/agent paths, stale CLI override strings, `psfascii`, or `openbox_auto` in user-facing docs.
- Markdown code-fence balance check passed.
- `requirements-product.txt` parses with pip dry-run using `--no-deps --no-build-isolation`.
- Release targeted test: `PYTHONPATH=src ../ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_requirement_intake.py -q` passed.
- Release full test: `PYTHONPATH=src ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q` exited 0.
- Release lint: `PYTHONPATH=src ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests` passed.
- Release/dev whitespace check: `git diff --check -- . ':!vendor' ':!.serena'` passed.

## 2026-06-16 Fix-Run Post-Report Audit

- Reviewed the fix-run final report against dev source before treating it as accepted.
- Found a code-level gap: local and remote `fix_run_report.json` initialized `waveform_export_manifest_paths` and `csv_artifact_paths` but did not populate them.
- Added local and remote RED/GREEN tests proving parent reports include child `metrics/waveform_export_manifest.json` and `metrics/waveforms/*.csv` paths.
- Implemented artifact scanning under each `runs/real/<run_id>` tree in local and remote fix-run flows.
- Verification after fix: focused fix-run suite passed, changed-file ruff passed, changed-file `git diff --check` passed.
- Real local/remote Spectre/OCEAN workflow acceptance is still pending and must not be reported as final acceptance.
