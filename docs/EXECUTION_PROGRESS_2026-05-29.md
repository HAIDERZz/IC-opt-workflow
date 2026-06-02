# Execution Progress 2026-05-29

This note preserves the implementation state for continuing Plan A after context compaction or quota reset.

## Repository State

- Repo: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Baseline branch: `master`
- Baseline commit: `885e97f docs: capture workflow planning baseline`
- Latest C-3 code commit before docs-only cleanup: `edb107f fix: harden preflight readiness gates`; docs cleanup continues through current HEAD
- Active plan: `docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md`
- Execution method: `superpowers:subagent-driven-development`
- Dependencies installed in active Python environment on 2026-05-29: `pytest`, `typer`, `pydantic`, `PyYAML`, `ruff`

## Completed Tasks

### Task 1: Python Package Scaffold

Status: complete.

Commits:

- `d501ae1 chore: scaffold hermes workflow package`

Implemented:

- `pyproject.toml`
- `README.md`
- `src/hermes_workflow/__init__.py`
- `src/hermes_workflow/cli.py`
- `tests/test_cli.py`

Verification:

- `pytest tests/test_cli.py -v`
- `ruff check .`

Reviews:

- Spec compliance: passed.
- Code quality: approved with minor note about duplicated version string.

### Task 2: YAML Schema Models

Status: complete.

Commits:

- `5c19728 feat: define hermes yaml schemas`
- `3367e5b fix: tighten schema scalar validation`
- `048a823 fix: reject coerced boolean literals`

Implemented:

- `src/hermes_workflow/schemas.py`
- Five confirmed YAML fixtures under `tests/fixtures/bridge_test_inv/config/`
- `tests/test_schemas.py`

Important decisions/fixes:

- Schema models use strict scalar handling for bool/int fields.
- Required strings reject empty or whitespace-only content, except `project.description`.
- Fixed safety booleans and `deduplicate_candidates` reject numeric coercion such as `1`/`0`.

Verification:

- `pytest tests/test_schemas.py -v`
- `ruff check .`

Reviews:

- Final spec compliance: passed.
- Final code quality: approved.

### Task 3: Cross-File Contract Validation

Status: complete.

Commits:

- `363b487 feat: validate hermes config contracts`
- `cbff0d2 fix: align validation success message`
- `54d04d0 fix: tighten objective and quantity validation`
- `bb0497a fix: require finite objective literals`

Implemented:

- `src/hermes_workflow/validate.py`
- `tests/test_validate.py`

Important decisions/fixes:

- `ValidationReport.format()` success text is exactly `validation passed`.
- Objective AST validation rejects function calls, unknown metric names, bool literals, and non-finite numeric literals.
- Continuous values support attached units such as `0.3um` and whitespace units such as `0.3 um`.
- Continuous stepped ranges intentionally do not require `upper` to land exactly on the step grid. Accepted semantics: candidate values are `lower + k * step <= upper`. This preserves the confirmed canonical fixture `0.3 um` to `3 um` with `0.2 um` step.
- Integer ranges still require exact divisibility by `step`.

Verification:

- `pytest tests/test_validate.py -v`
- `pytest tests/test_schemas.py tests/test_validate.py -v`
- `ruff check .`

Reviews:

- Final spec compliance: passed.
- Final code quality: approved with minor future hardening notes about `load_contract_bundle()` semantics and additional error-format tests.

### Task 4: Project Template Generation

Status: complete.

Commits:

- `d226b3b feat: add hermes project template`
- `e3138dc fix: make template regeneration explicit`
- `3d5767c fix: preserve template gitkeep files`
- `9b818e9 fix: keep packaged template source canonical`
- `9fd283c docs: align template package snippets`

Implemented:

- `src/hermes_workflow/package.py`
- `src/hermes_workflow/templates/spectre_maestro_project/**`
- `tests/test_package.py`
- `pyproject.toml` package-data entries for packaged template resources

Important decisions/fixes:

- `create_project_from_template(..., force=True)` performs clean regeneration by removing an existing destination directory before copying templates. Stale files are removed.
- File destinations raise `TemplateError("destination exists and is not a directory")`.
- Template discovery uses `importlib.resources` and the canonical packaged template tree at `src/hermes_workflow/templates/spectre_maestro_project`.
- The old top-level `templates/spectre_maestro_project` tree was removed to avoid divergent template sources.
- Generated projects preserve the seven required `.gitkeep` placeholders.
- Plan snippets were updated to preserve Task 4 package-resource behavior before Task 5 adds manifest functions.

Verification:

- `pytest tests/test_package.py -v`: passed, 6 tests.
- `pytest tests/test_schemas.py tests/test_validate.py tests/test_package.py -v`: passed, 29 tests.
- `ruff check .`: passed.
- Installed-package smoke test generated a template project from packaged resources and validated `.gitkeep` preservation.

Reviews:

- Final spec compliance: passed.
- Final code quality: approved.

## Claude Review MCP

Status: implemented as project tooling before Task 5.

Commits:

- `1935667 feat: add claude review mcp shell`
- `5c32764 feat: add claude spec review tool`
- `b32aa37 feat: add claude code quality review tool`
- `c6a76ca docs: register claude review mcp server`
- `15bfe6c docs: note claude review mcp handoff`
- `a719d1f fix: pass claude review prompt via stdin`

Implemented:

- `tools/claude_review_mcp.py`
- `.mcp.json`
- `docs/CLAUDE_REVIEW_MCP.md`
- `tests/test_claude_review_mcp.py`

Verification:

- `pytest tests/test_claude_review_mcp.py -v`: passed, 9 tests.
- `pytest -q`: passed, 39 tests.
- `ruff check .`: passed.
- `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python tools/claude_review_mcp.py`: returned `spec_review` and `code_quality_review`.
- `claude --version`: `2.1.153 (Claude Code)` after rollback from a CLI regression.

Usage:

- Use `claude-review.spec_review` and `claude-review.code_quality_review` as review gates for Task 5-9 when the MCP host has loaded the project server.
- If the MCP host has not reloaded project config, continue with existing subagent reviews or invoke the server script directly for smoke checks.

## Current Task

### Task 5: Execution Package Manifest Builder

Status: completed and committed.

Commits:

- `daea0f1 feat: build execution package manifest`
- `b0cfdca fix: harden execution package manifest`

Implemented:

- `build_execution_package()` validates the project, copies the five immutable config files into `execution_package/config`, records SHA-256 hashes, and writes `execution_manifest.json`.
- Existing manifests are refused with `FileExistsError` to avoid silent overwrite of an immutable snapshot.
- Missing config files are surfaced through the existing `assert_valid_project()` validation boundary.
- Package tests cover all five copied config files and hashes, duplicate manifest refusal, and missing config reporting.

Verification:

- `pytest tests/test_package.py -v`: passed, 9 tests after Task 5 hardening.
- `pytest tests/test_schemas.py tests/test_validate.py tests/test_package.py -v`: passed, 33 tests after Task 6.
- `ruff check .`: passed.

Reviews:

- Claude MCP spec review: passed.
- Claude MCP code-quality review: first returned two Important items; hardening commit addressed the overwrite risk and expanded test coverage.

### Task 6: `EXECUTION_TASK.md` Renderer

Status: completed and committed.

Commits:

- `009fbde feat: render claude execution task`
- `b907b64 fix: avoid duplicate execution task validation`

Implemented:

- `render_execution_task(project_dir, manifest_payload)` renders the public Task 6 Markdown API.
- `build_execution_package()` writes `execution_package/EXECUTION_TASK.md`.
- A private bundle renderer avoids re-validating the project during `build_execution_package()` while preserving the public renderer API.
- Package tests assert the required execution task content: project, backend, Spectre X preset, variables, Maestro safety rule, and supervisor approval wait.

Verification:

- `pytest tests/test_package.py -v`: passed, 10 tests.
- `pytest tests/test_schemas.py tests/test_validate.py tests/test_package.py -v`: passed, 33 tests.
- `ruff check .`: passed.

Reviews:

- Claude MCP spec review: passed after the validation-refactor fix.
- Claude MCP code-quality review: passed with no Critical or Important issues; only minor non-blocking notes.

### Task 7: Preflight Report Readers

Status: completed and committed.

Commits:

- `6d4cc76 feat: read claude preflight reports`

Implemented:

- `src/hermes_workflow/reports.py` defines strict Pydantic report models for netlist preparation, dry run, and health check files.
- `load_preflight_reports(project_dir)` loads the three required preflight report JSON files and aggregates readiness messages.
- `tests/report_helpers.py` writes reusable pass-report fixtures for Task 7 and downstream approval tests.
- `tests/test_reports.py` covers happy-path readiness and failed dry-run message aggregation.
- `tests/__init__.py` was added so the plan-specified `tests.report_helpers` import resolves consistently under pytest.

Verification:

- `pytest tests/test_reports.py -v`: passed, 2 tests.
- `pytest -q`: passed, 45 tests.
- `ruff check .`: passed.

Reviews:

- Claude MCP spec review: passed.
- Claude MCP code-quality review: passed with no Critical or Important issues; only minor non-blocking notes.

### Task 8: Hermes First-Run Approval Gate

Status: completed and committed.

Commits:

- `e530f94 feat: add hermes first-run approval gate`
- `7031fb9 fix: reject malformed approval manifests`
- `f644674 test: cover approval reject branches`

Implemented:

- `src/hermes_workflow/approvals.py` writes `supervisor_instruction.json` via `decide_first_real_run()`.
- Approval requires a present execution manifest, valid project config, and ready preflight reports.
- Rejection paths cover missing manifest, malformed manifest, missing manifest hashes, invalid config, and failed preflight reports.
- Approval output allows `run_standalone_spectre_optimizer` and pins the approved immutable config hashes.
- Rejection output allows escalation/revision actions and forbids standalone Spectre optimizer execution.

Verification:

- `pytest tests/test_approvals.py -v`: passed, 6 tests after review fixes.
- `pytest -q`: passed, 51 tests.
- `ruff check .`: passed.

Reviews:

- Claude MCP spec review: passed after review fixes.
- Claude MCP code-quality review: initially requested malformed-manifest handling and missing branch tests; final re-review passed with no Critical or Important issues.

### Task 9: CLI Contract Smoke Tests

Status: completed and committed.

Commits:

- `3ef818c feat: add hermes workflow cli commands`
- `96fe092 fix: report cli domain errors cleanly`
- `1411a71 fix: clarify cli error control flow`
- `716b0db fix: tighten cli approval error handling`
- `4b269a9 fix: harden cli approve error surface`
- `720adb9 fix: clarify cli json error handling`

Implemented:

- `hermes-workflow init <project_dir>` creates the packaged Spectre Maestro project template.
- `hermes-workflow validate <project_dir>` validates the five YAML file contracts.
- `hermes-workflow package <project_dir>` builds `execution_package/execution_manifest.json` and `EXECUTION_TASK.md`.
- `hermes-workflow approve <project_dir>` writes `supervisor_instruction.json` and exits nonzero for rejected first-run decisions.
- CLI smoke tests cover init/validate and package/approve happy paths.
- CLI error-surface tests cover package/init/approve domain failures without traceback leakage.
- README now includes the MVP CLI command sequence and approval semantics.

Important decisions/fixes:

- CLI commands catch only expected file-contract/domain errors and convert them into clean `exit code 1` output.
- `_exit_with_error()` is typed `NoReturn`; unreachable post-exit `return` statements were removed.
- `approve` explicitly handles malformed preflight JSON through `json.JSONDecodeError` and a regression test for malformed `dry_run_report.json`.
- No optimizer loop, runner, Spectre execution, or follow-up workflow scope was added.

Verification:

- `pytest tests/test_cli.py -v`: passed, 6 tests.
- `pytest -q`: passed, 56 tests.
- `ruff check .`: passed.

Reviews:

- Claude MCP spec review for final Task 9 head: spec compliant with noted defensive extras.
- Claude MCP code-quality review for final Task 9 head: passed with no Critical or Important issues.

### Focused Plan A Completion

Status: focused Plan A complete through Task 9.

Focused Hermes Plan A ends at Task 9. There is no Task 10 in this Hermes File Contract MVP plan.

Next recommended action (historical): hand off from focused Plan A into a new, user-confirmed development scope. This was superseded by later Plan C-3 status; current next action is confirming the next Plan C scope. The new worker should read `docs/OPENCODE_HANDOFF_2026-05-29.md` first and avoid redoing completed Plan A/B/C work.

## Plan C: Netlist Template Contract

Status: completed through Task 6 on 2026-05-30.

Plan files:

- Spec: `docs/superpowers/specs/2026-05-30-netlist-template-contract-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-30-netlist-template-contract.md`

Commits:

- `51253fe docs: design netlist template contract`
- `e1e428e docs: plan netlist template contract`
- `1ab42e1 feat: prepare spectre netlist templates`
- `6ce3e69 fix: support continued spectre parameters`
- `8e59ac9 fix: report unsafe netlist templating failures`
- `04fa358 feat: add prepare netlist cli`
- `5bf3e33 docs: record netlist template progress`
- `da23a7f fix: harden netlist parameter scanner`

Completed:

- Task 1: single-line top-level Spectre `parameters` assignment templating.
- Task 2: backslash-continued `parameters` blocks and no instance-parameter templating.
- Task 3: fail reports for missing exported input, missing approved variables, duplicate approved variables, and stale `template.scs` cleanup on failure.
- Task 4: `hermes-workflow prepare-netlist` CLI command and CLI smoke tests.
- Task 5: full verification, local-only real deck smoke in `/tmp`, and progress update.
- Task 6: final spec/code-quality gate and scanner hardening from review feedback.

Implemented so far:

- `src/hermes_workflow/netlists.py`
- `tests/test_netlists.py`
- `hermes-workflow prepare-netlist` in `src/hermes_workflow/cli.py`
- CLI tests in `tests/test_cli.py`

Verification:

- Baseline before Plan C execution: `pytest -q` passed, 138 tests.
- Baseline before Plan C execution: `ruff check .` passed.
- After Task 1: `pytest tests/test_netlists.py::test_prepare_netlist_templates_single_line_parameter_values -v` passed.
- After Task 1: `ruff check src/hermes_workflow/netlists.py tests/test_netlists.py` passed.
- After Task 2: `pytest tests/test_netlists.py -v` passed, 3 tests.
- After Task 2: `ruff check src/hermes_workflow/netlists.py tests/test_netlists.py` passed.
- After Task 3: `pytest tests/test_netlists.py -v` passed, 6 tests.
- After Task 3: `ruff check src/hermes_workflow/netlists.py tests/test_netlists.py` passed.
- After Task 4: `pytest tests/test_netlists.py tests/test_cli.py -v` passed, 16 tests.
- After Task 4: `ruff check src/hermes_workflow/cli.py src/hermes_workflow/netlists.py tests/test_cli.py tests/test_netlists.py` passed.
- During Task 5: `pytest -q` passed, 146 tests.
- During Task 5: `ruff check .` passed.
- During Task 5: local-only smoke under `/tmp/hermes_plan_c_smoke` passed for `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs`, `input1.scs`, `input2.scs`, and `input3.scs`.
- During Task 6 after review fixes: `pytest -q` passed, 148 tests.
- During Task 6 after review fixes: `ruff check .` passed.
- During Task 6 after review fixes: local-only smoke under `/tmp/hermes_plan_c_smoke` passed again for all four real deck examples.

Reviews:

- Task 1 spec review: passed; Task 1 code-quality review: passed with no Critical or Important issues.
- Task 2 spec review: passed; Task 2 code-quality review: passed with no Critical or Important issues.
- Task 3 spec review: passed; Task 3 code-quality review: passed with no Critical or Important issues.
- Task 4 spec review: passed; Task 4 code-quality review: passed with no Critical or Important issues.
- Task 6 final spec review: passed.
- Task 6 final code-quality review initially found Critical/Important scanner issues. Commit `da23a7f` fixed whitespace-unit RHS spans, subckt/non-top-level parameter handling, and `forbidden_setup_changes_detected` propagation. Final code-quality re-review passed with no Critical or Important issues.

Important decisions:

- The four real `input.scs` examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` are local reference material only and must not be committed.
- Repository tests use sanitized inline Spectre snippets only.
- Current netlist templater rewrites only approved variable RHS values in top-level `parameters` statements.
- Device, subckt, source, analysis, include, model, and save statements remain unchanged.

Next recommended action (historical):

- Plan C C-1 is complete.
- Do not copy real `input.scs` examples into the repository.
- Next scope should be confirmed before starting a new Plan C follow-up task.
- This was superseded by later Plan C-3 status; current next action is confirming the next Plan C scope.

## Plan C-2: Dry-Run Candidate Renderer

Status: complete as of 2026-05-30.

Route alignment:

- The historical broad plan has been updated so current project files agree on the responsibility split.
- Hermes workflow tooling owns deterministic preflight: validation, netlist preparation, dry-run rendering, packaging, and approval.
- The execution agent owns Maestro export and post-approval real Spectre/optimizer execution through `virtuoso-bridge-lite`.
- `render_netlist.py` and `dry_run.py` inside the generated execution package are no longer the preferred route for preflight.

Spec:

- `docs/superpowers/specs/2026-05-30-dry-run-candidate-renderer-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-05-30-dry-run-candidate-renderer.md`

Commit:

- `e2b1c30 docs: design dry-run candidate renderer`
- `5441972 docs: plan dry-run candidate renderer`
- `b925cb9 feat: add dry-run renderer`
- `b042a74 fix: enforce dry-run placeholder failures`
- `c2e08d2 test: lock dry-run mock check semantics`
- `9fffb90 feat: add dry-run cli command`
- `59c0aff docs: record dry-run renderer progress`
- `1835c94 fix: report dry-run render write failures`

Implemented:

- `src/hermes_workflow/dry_run.py` renders one lower-bound candidate from `netlists/templates/template.scs`.
- `hermes-workflow dry-run PROJECT_DIR` writes `runs/dry_run/input.scs` and `reports/dry_run_report.json`.
- Dry-run checks missing approved placeholders, unexpected placeholders, malformed unresolved placeholders, mock metric computation, objective evaluation, constraint evaluability, and `ledger/` and `state/` writability.
- Dry-run does not run Spectre, Virtuoso, or `run_mock_optimization()`.
- Dry-run does not write optimizer ledger rows, optimizer state, best-candidate files, or health-check files.

Verification:

- `pytest tests/test_dry_run.py -v`: passed, 9 tests.
- `pytest tests/test_cli.py tests/test_dry_run.py -v`: passed, 21 tests.
- `pytest -q`: passed, 159 tests.
- `ruff check .`: passed.
- Local-only smoke under `/tmp/hermes_c2_smoke` passed using `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example/input.scs`: `prepare-netlist` passed and `dry-run` passed.

Reviews:

- Task 1 spec review: passed; Task 1 code-quality review: passed with no Critical or Important issues.
- Task 2 spec review: passed; Task 2 code-quality review: passed with no Critical or Important issues.
- Task 3 spec review: passed; Task 3 code-quality review: passed with no Critical or Important issues.
- Task 4 spec review: passed; Task 4 code-quality review: passed with no Critical or Important issues.
- Final spec review: passed.
- Final code-quality review: passed through the project Claude Review MCP wrapper with no Critical or Important findings.

Next resume point (historical):

- Plan C-2 is complete.
- Next follow-up scope should be confirmed before starting additional Plan C work.
- This was superseded by later Plan C-3 status; current next action is confirming the next Plan C scope.

## Plan C-3: Execution Package Preflight Readiness

Status: complete and reviewed as of 2026-05-31.

Spec:

- `docs/superpowers/specs/2026-05-30-execution-package-preflight-readiness-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-05-30-execution-package-preflight-readiness.md`

Commits:

- `362f34c fix: align execution package preflight contract`
- `adb3f4a fix: clarify execution task templating ownership`
- `caf2175 feat: write preflight health reports`
- `5bae3c1 test: cover optimizer state preflight artifact`
- `ded8d11 feat: add preflight health cli`
- `79df214 test: cover preapproval readiness flow`
- `900dcf2 fix: harden preapproval flow tests`
- `edb107f fix: harden preflight readiness gates`
- `a4e2473 docs: record preflight readiness progress`
- `bbbfcd7 docs: fill preflight readiness progress hash`
- `6befb7b docs: clarify preflight readiness resume state`
- `88a8c21 docs: align preflight readiness pending verification`
- `f3bc789 docs: mark stale handoff notes historical`
- `919bb84 docs: refresh opencode handoff for c3 verification`

Implemented:

- Generated `EXECUTION_TASK.md` now tells the execution agent to export or place `netlists/exported/input.scs` and wait for Hermes deterministic preflight.
- `src/hermes_workflow/health.py` writes `state/health_check.json` for preflight readiness.
- `hermes-workflow preflight-health PROJECT_DIR` writes a healthy report or a fail-closed error report when pre-approval real-run artifacts exist.
- `approve` wording no longer refers to Claude preflight reports.
- CLI integration coverage now proves the no-real-execution flow can reach `approve_first_real_run`.
- Approval now rejects missing required preflight reports through a structured `reject_first_real_run` instruction instead of surfacing a raw filesystem error.
- Execution package build failures now clean up partial `execution_package/` artifacts so a retry can succeed.

Verification:

- `pytest tests/test_cli.py tests/test_approvals.py tests/test_health.py tests/test_package.py -v`: passed, 37 tests.
- `ruff check .`: passed.
- `pytest tests/test_approvals.py tests/test_package.py tests/test_reports.py tests/test_health.py -q`: passed, 28 tests after Task 6 hardening.
- `pytest -q`: passed, 173 tests.

Next recommended action:

- Plan C-3 is complete and reviewed.
- Plan C-4 has since been confirmed, completed, and reviewed.

## Plan C-4: Post-Approval Real-Run Execution Contract

Status: complete and reviewed as of 2026-06-01.

Scope:

- Contract-only first real-run package.
- Hermes prepares `runs/real/<run_id>/input.scs`, `candidate.json`, and `real_run_manifest.json`.
- Hermes must not run Spectre, Virtuoso, subprocesses, or the optimizer loop.

Spec:

- `docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`

Commits:

- `0f64570 docs: design post approval real run contract`
- `e6512cc docs: plan post approval real run contract`
- `e195bd9 feat: guard post approval real runs`
- `d6804a8 feat: prepare first real run package`
- `fc34c6d fix: harden real run package creation`
- `1ce650e feat: add prepare real run cli`
- `f40966e docs: record real run package progress`

Implemented:

- `src/hermes_workflow/real_run.py` validates `supervisor_instruction.json` and requires `approve_first_real_run`.
- Real-run preparation verifies instruction `approved_config_hashes` exactly match `execution_manifest.json` immutable config hashes.
- Current immutable config files are re-hashed before package creation to detect approval-time drift.
- The first real-run candidate is deterministic lower-bound data from `variables.yaml`.
- `template.scs` is rendered into `runs/real/<run_id>/input.scs` without using a general template engine.
- `candidate.json` and `real_run_manifest.json` are written next to the rendered deck.
- Existing packages are not overwritten.
- Partial `runs/real/<run_id>/` directories are removed on render/write failure so retries are clean.
- `hermes-workflow prepare-real-run PROJECT_DIR` writes `runs/real/real_001/input.scs`, `candidate.json`, and `real_run_manifest.json`.
- The command refuses missing approval, rejected approval, immutable config drift, missing templates, invalid run IDs, and existing real-run packages.
- C-4 does not run Spectre, Virtuoso, subprocesses, metric extraction, ledger append, or optimizer execution.

Verification:

- `pytest -q`: passed, 190 tests.
- `ruff check .`: passed.
- `pytest tests/test_real_run.py -v`: passed, 14 tests after Task 3.
- `ruff check .`: passed after Task 3.
- `git diff --check`: passed after Task 3.
- After Task 4: `pytest tests/test_cli.py::test_cli_prepare_real_run_writes_package_after_approval tests/test_cli.py::test_cli_prepare_real_run_reports_missing_approval_without_traceback tests/test_cli.py::test_cli_prepare_real_run_reports_config_drift_without_traceback -v` passed, 3 tests.
- After Task 4: `pytest tests/test_real_run.py tests/test_cli.py -v` passed, 33 tests.
- After Task 4: `ruff check .` passed.

Reviews:

- Task 1 spec review: passed; Task 1 code-quality review: passed with no Critical or Important issues.
- Task 2 spec review: passed; Task 2 code-quality review: passed after fixes with no Critical or Important issues.
- Task 3 spec review: passed; Task 3 code-quality review: passed with no Critical or Important issues.
- Task 4 used Risk-Tiered Batch Gates: local deterministic verification passed; final combined review completed in Task 6.
- Combined final spec/code-quality review: passed with no Critical or Important findings; ready to close C-4.

Next recommended action:

- C-5 has since been confirmed as the next Plan C scope.

## Plan C-5: Real-Run Result Handoff Contract

Status: complete and reviewed as of 2026-06-01.

Scope:

- Hermes validates `runs/real/<run_id>/result_manifest.json` after an execution agent consumes the C-4 first real-run package.
- Hermes checks the prepared manifest, result manifest, candidate identity, rendered deck hash, and declared artifact paths.
- Hermes writes `reports/real_run_check_report.json`.
- C-5 does not run Spectre, run Virtuoso, parse real metrics, append ledger rows, or update optimizer state.

Spec:

- `docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`

Commits so far:

- `ce4ce0d docs: design real run result handoff contract`
- `081cc65 docs: plan real run result handoff contract`
- `55ec944 feat: add real run check report models`
- `b928cc5 docs: mark c5 task 1 complete`
- `ced01cc feat: validate real run result handoff`
- `3d5802b docs: mark c5 task 2 complete`
- `72d1696 fix: harden real run handoff validation`
- `414d61f fix: validate real run result manifest shape`
- `c9983df docs: mark c5 task 3 complete`
- `8272b04 feat: add real run handoff cli`
- `fadc22c docs: mark c5 task 4 complete`
- `36a027a docs: record real run result handoff progress`

Implemented so far:

- `src/hermes_workflow/reports.py` defines strict real-run check report models.
- `src/hermes_workflow/result_handoff.py` validates returned `result_manifest.json`, prepared package identity, prepared input hash, simulator/timestamp shape, and artifact path safety.
- `reports/real_run_check_report.json` is written for pass/fail result handoff checks when project config can be loaded.
- `hermes-workflow check-real-run PROJECT_DIR` prints pass/fail output and expected failures without tracebacks.
- Sanitized tests cover valid succeeded/failed handoffs, missing/malformed manifests, identity mismatches, invalid status, invalid manifest shape, prepared input drift, unsafe paths, missing artifacts, and CLI output.

Task 1-4 verification:

- `pytest tests/test_result_handoff.py::test_real_run_check_report_schema_accepts_pass_report tests/test_result_handoff.py::test_real_run_check_report_schema_rejects_unknown_fields -v`: passed, 2 tests.
- `pytest tests/test_result_handoff.py::test_check_real_run_accepts_valid_succeeded_handoff tests/test_result_handoff.py::test_check_real_run_accepts_valid_failed_handoff -v`: passed, 2 tests.
- `pytest tests/test_result_handoff.py -v`: passed, 19 tests.
- `pytest tests/test_real_run.py tests/test_result_handoff.py -v`: passed, 33 tests.
- `pytest tests/test_cli.py::test_cli_check_real_run_reports_success tests/test_cli.py::test_cli_check_real_run_reports_failure_without_traceback -v`: passed, 2 tests.
- `pytest tests/test_result_handoff.py tests/test_cli.py -v`: passed, 40 tests.
- `ruff check .`: passed.

Final verification:

- `pytest tests/test_result_handoff.py tests/test_cli.py -v`: passed, 40 tests.
- `pytest -q`: passed, 211 tests.
- `ruff check .`: passed.

Review:

- Combined final spec/code-quality review: passed with no Critical or Important findings.
- Minor findings only: clearer missing prepared input message, no dedicated CLI `--run-id` test, and harmless sorted-key test fixture mismatch.

Next recommended action:

- Run C-5.5 dual-agent result handoff simulation before adding real Hermes, Claude CLI, Spectre, Virtuoso, metric extraction, or optimizer-loop tool adapters.

## Plan C-5.5: Dual-Agent Result Handoff Simulation Gate

Status: complete as of 2026-06-01; simulation gate passed.

Scope:

- Use simulated Codex roles for execution-agent and Hermes workflow observer.
- Validate the C-4/C-5 role split in a temporary sanitized project.
- Run five scenarios: happy path, valid simulator failure, unsafe path, mutated prepared deck, and identity mismatch.
- Write `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`.
- Do not call real Spectre, real Virtuoso, real Claude CLI as execution agent, a hypothetical Hermes service, metric extraction, ledger append, or optimizer state update.

Spec:

- `docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`

Simulation report:

- `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`

Scenario outcomes:

- `happy_path`: final observer exit code 0, report `pass`, result status `succeeded`, no issues. First attempt exposed prompt drift: `created_at_utc` instead of required `started_at_utc`.
- `valid_failure`: observer exit code 0, report `pass`, result status `failed`, no issues.
- `unsafe_path`: final observer exit code 1, report `fail`, issue `result artifact path is unsafe: /tmp/c5_5_outside_spectre.log`. The outside file was not created.
- `mutated_deck`: final observer exit code 1, report `fail`, issue `prepared input hash mismatch`.
- `identity_mismatch`: final observer exit code 1, report `fail`, issues `result candidate_id does not match prepared candidate` and `result candidate_id does not match candidate file`.

Behavior finding:

- Exact C-5 schema enumeration is needed in future execution-agent prompts or adapters. With loose prompts, simulated execution agents drifted toward older C-4/C-5-adjacent manifest shapes; Hermes still failed closed through the deterministic checker.

## Spectre + OCEAN Toolchain Evidence

Status: complete as of 2026-06-01.

Purpose:

- Resolve the metric-backend uncertainty before continuing Plan C.
- Reject the unsafe route where an agent reads Calculator formulas and reimplements them in Python.
- Validate that standalone Spectre plus batch OCEAN can be the authoritative metric extraction path.

Evidence directories:

- `docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/`
- `docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/`

Findings:

- Transient/DC inverter case:
  - Maestro point-level PSF opened in `ocean -nograph`.
  - Standalone Spectre replay PSF opened in `ocean -nograph`.
  - OCEAN scalar values for `rise`, `fall`, and `DC` matched between Maestro PSF and standalone replay.
- PSS/PAC/PNoise mixer case:
  - Target cell: `Virtuoso_Bridge_test/Mixer_PSS_CG_Noise`.
  - Maestro point-level PSF opened in `ocean -nograph`.
  - Standalone Spectre replay completed with `0 errors, 7 warnings, and 9 notices`.
  - OCEAN scalar values for `BW` and `MAX_GAIN` matched between Maestro PSF and standalone replay.
  - `drplPacVolGnExpDen` is callable in batch OCEAN in this environment.

Locked policy:

- `metrics.yaml` formulas are authoritative contract inputs.
- Formula discovery from Maestro/ADE is allowed only as a draft/audit helper; the user/project must approve the exact executable expression before real execution.
- Do not rewrite formulas across dialects. If the approved formula uses `vh`, evaluate `vh`; if it uses `drplPacVolGnExpDen`, evaluate `drplPacVolGnExpDen`.
- Python must not parse PSF waveform data.
- Python must not reimplement OCEAN/Calculator formulas.
- Python may invoke batch OCEAN and parse already-produced scalar/text outputs and logs.

## Plan C C-6 Spectre + OCEAN Metric Result Contract

Status: complete and reviewed as of 2026-06-02.

Spec:

- `docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md`

Implemented:

- `metrics.yaml` can carry exact approved OCEAN formula blocks.
- `spectre.yaml` accepts `psfxl`; C-6 real metric request generation requires an OCEAN-ready format.
- `prepare-real-run` writes `runs/real/<run_id>/metric_extraction_request.json` and records its SHA-256 in `real_run_manifest.json`.
- Returned `result_manifest.json` can reference `result_data` PSF artifacts and `metric_result_manifest.json`.
- `src/hermes_workflow/metric_results.py` validates returned OCEAN scalar manifests against the prepared request without reading PSF, parsing waveform data, or recomputing formulas.
- `hermes-workflow check-metric-results PROJECT_DIR` writes `reports/metric_result_check_report.json` and surfaces expected failures without tracebacks.

Task verification so far:

- Task 1 final local verification: `pytest tests/test_validate.py tests/test_package.py -q` passed, 30 tests; `pytest tests/test_mock_optimizer.py tests/test_dry_run.py -q` passed, 89 tests; `ruff check src tests` passed.
- Task 2 final local verification: `pytest tests/test_real_run.py tests/test_validate.py tests/test_package.py -q` passed, 48 tests; `ruff check src tests` passed.
- Task 3 final local verification: `pytest tests/test_result_handoff.py tests/test_real_run.py -q` passed, 46 tests; `ruff check src tests` passed.
- Task 4 high-risk gate: spec re-review and code-quality review approved. Final local verification: `pytest tests/test_metric_results.py -q` passed, 48 tests; `pytest tests/test_metric_results.py tests/test_result_handoff.py tests/test_real_run.py -q` passed, 94 tests; `ruff check src tests` passed.
- Task 5 CLI integration local verification: `pytest tests/test_cli.py -q` passed, 23 tests; `pytest tests/test_cli.py tests/test_metric_results.py tests/test_result_handoff.py tests/test_real_run.py -q` passed, 117 tests.
- Task 6 full verification before final review: `pytest -q` passed, 282 tests; `ruff check src tests tools` passed; `git diff --check` passed.
- Task 6 final combined review gate: approved with no Critical, Important, or Minor findings.

Locked C-6 policy:

- `metrics.yaml` approved OCEAN formulas are the only executable formula source.
- Formula discovery from Maestro/ADE remains draft/audit only until approved into `metrics.yaml`.
- Hermes must not run Spectre, run OCEAN, parse PSF, parse waveform data, translate formulas, append optimizer ledger rows, or update optimizer state in C-6.
- Python may validate JSON contract files, hashes, finite scalar values, and artifact paths.

Still excluded:

- running Spectre from Hermes
- running OCEAN from Hermes
- parsing PSF in Python
- computing Calculator/OCEAN formulas in Python
- optimizer ledger/state updates

Next recommended action:

- C-7 Task 6 final verification and combined review are complete.
- C-8 now records checked real metric results into optimizer ledger/state after `check-real-run` and `check-metric-results` pass.

## Plan C C-7 Spectre + OCEAN Execution Adapter

Status: complete and reviewed as of 2026-06-02.

Spec:

- `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`

Implemented:

- `src/hermes_workflow/execution_adapters/spectre_ocean.py` loads approved real-run packages, verifies preconditions, generates exact-formula OCEAN replay scripts, runs through an injectable command runner, parses only `metrics/ocean_scalars.tsv`, and writes C-5/C-6-compatible result artifacts.
- Failure handling distinguishes Spectre failure from OCEAN/metric failure. Spectre failure writes a structurally valid failed `result_manifest.json` and skips OCEAN. OCEAN failure keeps Spectre handoff status succeeded while failing `metric_result_manifest.json`.
- Overwrite and safety hardening reject existing result artifacts unless `allow_overwrite=True`, reject adapter-owned output symlinks, and declare only existing artifacts in `result_manifest.json`.
- `tools/run_spectre_ocean_adapter.py` is the explicit execution-side entry point. It is not a Hermes validator and is not registered as a `hermes-workflow` CLI command.
- Automated tests use fake runners and monkeypatching only. No test invokes real Spectre, real OCEAN, real Virtuoso, SSH, Claude CLI as execution agent, or network.

Task verification:

- Task 1 context/precondition gate: adapter tests passed; ruff passed; spec and code-quality reviews approved.
- Task 2 OCEAN replay/TSV parsing gate: adapter tests passed; ruff passed; spec and code-quality reviews approved after strict TSV/control-character hardening.
- Task 3 fake runner success/manifest writing gate: adapter/C-5/C-6 tests passed; ruff passed; spec and code-quality reviews approved after OCEAN log path and output-dir symlink fixes.
- Task 4 failure/overwrite/safety gate: adapter/C-5/C-6 tests passed; ruff passed; spec and code-quality reviews approved after artifact declaration and file-level symlink fixes.
- Task 5 execution-side tool entry point local verification: `pytest tests/test_spectre_ocean_adapter.py -q` passed; `ruff check src/hermes_workflow/execution_adapters tests/test_spectre_ocean_adapter.py tools/run_spectre_ocean_adapter.py` passed.
- Task 6 docs/progress/full verification/final review gate complete. First final review found three path/failure-log blockers; fixes made OCEAN run from the project root with project-relative replay/log paths, directed Spectre to `psf/spectre.out`, and converted malformed scalar TSV after zero OCEAN exit into structured failed metric artifacts. Re-review approved with no findings.
- Final verification: `python3 -m pytest tests/test_spectre_ocean_adapter.py -q` passed with 55 tests; `python3 -m pytest -q` passed with 337 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output.

Locked C-7 policy:

- The supervisor agent must still run `check-real-run` and `check-metric-results` after the adapter returns. Adapter success alone is not workflow success.
- The adapter may invoke physical tools only through its explicit execution-side entry point after `prepare-real-run`.
- Python still must not parse PSF or reimplement Calculator/OCEAN formulas.
- Automated tests must continue to use fake runners; real Cadence smoke remains local-only evidence.

## Plan C C-8 Real Result Ledger/State Update

Status: complete and reviewed as of 2026-06-02.

Spec:

- `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`

Implemented:

- `LedgerRow` accepts optional real-result provenance fields while preserving existing mock ledger compatibility.
- `record_real_result()` reruns `check_real_run()` and `check_metric_results()` from fresh in-memory reports before any optimizer writes.
- Precondition failures, missing manifests, duplicate `run_id`, duplicate `candidate_id`, and invalid ledger rows fail closed before append.
- Successful checked real results append one row to `ledger/experiment_ledger.jsonl`, update `state/optimizer_state.json`, and update `state/best_candidate.json` only when the real result is feasible and better than the existing best.
- `hermes-workflow record-real-result PROJECT_DIR --run-id real_001` exposes the record operation with pass/fail output and no traceback for expected contract failures.

Task verification:

- Task 1 schema/report gate: focused tests passed; ruff passed; spec and code-quality reviews approved after mock ledger backwards-compatibility fix.
- Task 2 fail-closed precondition gate: focused/checker tests passed; ruff passed; spec and code-quality reviews approved after adding no-persist checker calls for prerequisite reports.
- Task 3 success write gate: real-result/checker tests passed; ruff passed; spec and code-quality reviews approved.
- Task 4 duplicate/best hardening gate: real-result/checker tests passed; ruff passed; spec and code-quality reviews approved after removing a stale unused ledger-count helper.
- Task 5 CLI integration gate: CLI/real-result/checker tests passed; ruff passed; combined review approved.
- Task 6 full verification after final-review fixes: `python3 -m pytest -q` passed with 362 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output.
- Task 6 final combined review found two Important ledger/state/best consistency findings. They were fixed: best candidate is now derived from strict ledger rows plus the current real row, stale/invalid `best_candidate.json` no longer overrides ledger source of truth, and infeasible best candidates cannot block feasible rows. Final re-review confirmed the code findings were addressed; docs-only Minor cleanup remained.
- Task 6 final docs re-review: approved with no remaining findings.

Locked C-8 policy:

- C-8 is contract-only. It does not run Spectre, run OCEAN, call the C-7 adapter, parse PSF, or rewrite formulas.
- `check-real-run` and `check-metric-results` must pass before ledger/state writes.
- The ledger remains the source of truth. Optimizer state and best candidate are derived from checked ledger-worthy payloads.
- C-8 does not generate the next candidate and does not add failure-penalty rows for simulator/metric failures.

Next recommended action:

- Historical after C-8/C-9: choose failure/retry policy or local smoke chaining C-9 -> C-7 -> C-8. This is now superseded by C-10 planning below; execute C-10 before C-11 local smoke.

## Plan C C-9 Next Real-Run Package Contract

Status: complete and reviewed as of 2026-06-02.

Spec:

- `docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`

Implemented:

- `prepare_next_real_run()` selects the next unique candidate from the deterministic optimizer initialization sequence after C-8 records a checked real result.
- `hermes-workflow prepare-next-real-run` writes the next C-4/C-6-compatible package under `runs/real/<run_id>/`.
- C-9 deduplicates against strict ledger rows and already prepared run packages.
- C-9 validates immutable config hashes, optimizer state consistency, ledger schema, max-evaluation bounds, run-id safety, overwrite safety, and partial run directory safety.
- Ledger and best-candidate numeric fields were hardened to strict finite floats, with strict bools for feasibility, so C-9 cannot proceed from coerced ledger data.
- Fake handoff coverage confirms a `real_002` package can be checked and recorded through `check-real-run`, `check-metric-results`, and `record-real-result`.

Task verification:

- Task 1 precondition gate: C-9 tests passed; C-4/C-8 related tests passed; ruff passed. Spec review approved. Code-quality review found a strict ledger coercion issue; it was fixed by strict finite ledger/best schema fields and re-reviewed as approved.
- Task 2 package-writing gate: C-9/C-4/C-8 related tests passed; ruff passed. Spec review found partial run directory reuse; it was fixed so existing `real_###` directories are treated as used by default, explicit non-empty target directories fail closed, and existing partial contents are preserved. Spec re-review and code-quality review approved.
- Tasks 3-4 integration/CLI gate: C-9, CLI, and real-result related tests passed; ruff passed. Batched spec and code-quality reviews approved.
- Final review found one high-risk symlinked real-run directory issue. It was fixed so explicit `run_id`, default next-run scanning, and prepared-candidate scanning all reject symlinked `runs/real/real_###` directories before writes. Re-review approved.
- Final verification: `python3 -m pytest -q` passed with 380 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output.

Locked C-9 policy:

- C-9 is contract-only.
- It does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- It does not parse PSF, rewrite OCEAN formulas, check returned results, record ledger/state, or add failure-penalty rows.
- The execution agent must still run C-7 after a prepared package exists, and the supervisor agent must still run `check-real-run`, `check-metric-results`, and `record-real-result`.

Next recommended action:

- Choose failure/retry policy for failed real-run packages, or run a local smoke that chains C-9 -> C-7 -> C-8 on a known test cell.

## Plan C C-10 Real-Run Failure Retry Policy Contract

Status: design spec and implementation plan complete as of 2026-06-02; code implementation has not started.

Spec:

- `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- Commit: `68c404a docs: design real run failure retry policy`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`
- Commit: `13d39e9 docs: plan real run failure retry policy`

Planned:

- Add recovery report schemas for real-run recovery status, classification, allowed actions, and assessment reports.
- Add `real_run_recovery.py` to classify pending, invalid, failed, partial, metric-failed, recordable, already-recorded, retry-prepared, abandoned, and stopped real-run states.
- Add explicit supervisor recovery decisions through `recovery_decision.json`.
- Add retry package preparation for the same candidate using a new `run_id`, while preserving failed-run artifacts.
- Add a C-9 unresolved-run guard so `prepare-next-real-run` cannot advance past unresolved pending/failed/partial/retry-prepared packages.
- Add CLI commands: `assess-real-run-recovery`, `prepare-real-run-retry`, and `resolve-real-run-failure`.

Locked C-10 policy:

- C-10 is contract-only.
- It must not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- It must not parse PSF, rewrite OCEAN formulas, compute metrics in Python, write optimizer ledger/state, or add failure-penalty rows.
- C-11 local smoke and real tool/agent integration must wait until C-10 implementation passes review/final gate.

Next required action:

- Execute C-10 Task 1 from `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md` using Subagent-Driven Development.

## Locked Role Model

Status: locked as of 2026-06-02.

Reference:

- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`

Definitions:

- Supervisor agent: the planning and decision-making agent. It uses Hermes workflow tooling, reads machine-readable reports, approves or rejects progression, and must not run real Spectre/OCEAN directly.
- Hermes workflow tooling: this repository's deterministic file-contract and validation layer. It owns schema validation, preflight, approval files, real-run package preparation, handoff checks, metric-result checks, and reports. It is not a local LLM agent.
- Execution agent: the tool-side agent that operates Virtuoso/Spectre/OCEAN through approved packages and adapter boundaries. It may be implemented by Claude CLI, another agent runtime, a scripted worker, or future `virtuoso-bridge-lite` adapter code.

Do not use "Hermes agent" as a role name in future specs or plans. If older documents mention Hermes in that sense, treat it as superseded by this role model.

## Resume Prompt

```text
请继续执行 IC auto optimization workflow。先阅读：
1. ic-auto-opt-workflow/docs/OPENCODE_HANDOFF_2026-05-29.md
2. ic-auto-opt-workflow/docs/EXECUTION_PROGRESS_2026-05-29.md
3. ic-auto-opt-workflow/docs/COMPACT_RESUME_CHECKPOINT.md
4. ic-auto-opt-workflow/docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md

当前 repo 是 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow，branch 是 plan-a-hermes-file-contract-mvp。请先阅读 docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md、docs/EXECUTION_PROGRESS_2026-05-29.md、docs/COMPACT_RESUME_CHECKPOINT.md。Hermes File Contract MVP 的 Plan A Task 1-9 已完成；Plan B mock optimization loop 已完成；Plan C C-1/C-2/C-3/C-4/C-5/C-5.5/C-6/C-7/C-8/C-9 均已完成并通过相应 verification/review gate。C-10 real-run failure/retry policy contract 的 design spec 和 implementation plan 已完成并提交，但代码实现尚未开始。下一步请使用 Subagent-Driven Development 从 docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md 的 Task 1 开始执行。不要跳到 C-11 local smoke 或真实工具/agent 接入，直到 C-10 通过 review/final gate。Spectre + OCEAN backend 已通过真实工具链证据验证。不要提交或复制本地真实 input.scs 示例，不要让 agent 重写公式，不要用 Python 解析 PSF 或重写 Calculator/OCEAN 公式。
```
