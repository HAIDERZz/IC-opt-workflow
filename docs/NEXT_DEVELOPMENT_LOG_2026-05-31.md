# Next Development Log 2026-05-31

## Current Node

- Repository: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Current scope: C-17 Native TuRBO Optimizer Runner MVP
- Current status: verified-only; C-16 follow-up practice corrected the optimizer route by running local `Turbo1.optimize()` as the actual optimizer driver with Hermes + Spectre/OCEAN as the evaluator
- Next required action: execute C-17 Task 1 Core Objective And Candidate Quantization
- next_allowed_action: execute C-17 Task 1: Core Objective And Candidate Quantization; do not run real tools until the C-17 fake/unit tasks pass and the user confirms real-tool acceptance

C-3 Task 6 final verification is complete. C-4 is confirmed as a contract-only first real-run package; it must not run Spectre, Virtuoso, subprocesses, or the optimizer loop. C-4 is now complete and reviewed. C-5 validates the execution agent's returned `result_manifest.json` and declared artifacts without running Spectre or parsing metrics. C-5.5 rehearsed the C-4/C-5 handoff with simulated execution-agent and Hermes-observer roles. After C-5.5, the project paused implementation to validate the real metric backend. Spectre + OCEAN is now confirmed as the backend route: standalone Spectre generates PSF, batch OCEAN opens the PSF and evaluates exact user/project-approved formulas, and Python only records OCEAN-produced scalar outputs and provenance. C-6 turned that route into deterministic file contracts and a Hermes validator without physical adapter wiring. C-7 added an explicit execution-side adapter and tool entry point while preserving the rule that Hermes workflow tooling still validates returned files after execution. C-8 records checked real metric results into optimizer ledger/state after `check-real-run` and `check-metric-results` pass, while preserving the contract-only boundary. C-9 prepares the next real-run package from strict ledger/state and deterministic optimizer initialization sequence, while still not running real tools or writing ledger/state. C-10 classifies failed/partial/pending real-run packages, writes explicit recovery decisions, prepares retry packages, exposes supervisor-facing recovery CLI commands, and blocks C-9 from advancing while unresolved real-run packages exist. C-10 final review fixes aligned unsafe artifact classification with the spec and hardened symlinked recovery decision reads.

## Optimizer Skill Real Flow Practice 2026-06-04

The earlier C-15/C-16 one-candidate suggestion loop is no longer treated as valid optimizer acceptance. A corrected real practice used local `Turbo1.optimize()` from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO` as the optimizer driver and the proven Hermes + Spectre/OCEAN path as the objective evaluator.

Sanitized archive:

```text
docs/debug/2026-06-04-optimizer-skill-real-flow-practice.md
```

Local-only evidence:

```text
/tmp/ic_auto_opt_optimizer_skill_flow_001/summary.json
/tmp/ic_auto_opt_optimizer_skill_flow_001/evaluations.tsv
/tmp/ic_auto_opt_optimizer_skill_flow_001/evaluations.jsonl
```

Result: `100` evaluations completed with `8` initialization points and `92` TuRBO trust-region points. `73` candidates recorded real Spectre/OCEAN scalar results, `24` quantized duplicate candidates were skipped, and `3` metric non-scalar candidates were converted to finite penalties. Best candidate was `real_011`: `FN=11`, `WN=1.9u`, `FP=9`, `WP=0.5u`, `rise=72.489655ps`, `fall=64.569947ps`, `DC=301.334349uW`, objective `4.1300765965648685e-14`.

Productization decision: proceed with C-17 Native TuRBO Optimizer Runner MVP. C-17 must implement native `Turbo1.optimize()` driving, feasibility-first objective semantics, quantized-candidate de-duplication/replacement, explicit first optimizer candidate packaging, and compact optimizer traces. It must not create a broad optimizer framework or replace the proven Spectre/OCEAN evaluator path.

## Route Consistency Audit 2026-06-03

Current audit result: no technical-route drift was found after drafting the C-11 local smoke implementation plan. C-11 remains aligned with the top-level plan and active design spec: it is a local/fake controlled smoke for C-9 -> C-7-style returned artifacts -> C-5/C-6 checks -> C-8 record plus one controlled C-10 failure/retry path. It does not authorize real Virtuoso/Spectre/OCEAN/SSH/agent integration, PSF parsing, formula rewriting, or new optimizer policy. The implementation plan keeps C-11 in tests/docs only and defers real-tool/agent practice to a later plan.

Process hardening route audit: no Hermes technical-route change is introduced by the lightweight cadence guard. The active node is now Plan C process hardening lightweight cadence guard, tracked by `docs/CURRENT_TASK_STATE.json`, `tools/check_development_cadence.py`, and `docs/superpowers/specs/2026-06-03-process-hardening-lightweight-cadence-design.md`. This node is `verified-only` because no true callable subagent dispatch path is available in the current session. It does not run real tools, call the C-7 adapter, parse PSF, rewrite formulas, or change optimizer policy.

C-11 clean restart route audit: no technical-route drift is introduced by resetting and redoing C-11. The active C-11 scope remains local/fake controlled smoke only, using synthetic C-7-style returned artifacts and existing Hermes validators. The restart removes stale C-11 test residue and returns the active node to Task 1 ready state. It still does not authorize real Virtuoso/Spectre/OCEAN/SSH/agent/bridge execution, C-7 subprocess adapter use, PSF parsing, formula rewriting, or new optimizer policy.

C-11 Task 1 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains local/fake controlled smoke only: Task 1 added test-only helpers and a single seed-recording smoke through existing check and record contracts. Drift: none; no real tools, subprocess-backed C-7 adapter, network, PSF parsing, or formula rewriting were added.

C-11 Task 1 review evidence: spec-compliance review approved by Bohr (`019e8c9f-2249-7db3-bcaf-c7744f427cbc`) with no Critical, Important, or Minor findings. Code-quality review approved by Volta (`019e8ca0-424e-7683-bebe-bb44e2340c5c`) with no Critical, Important, or Minor findings.

C-11 Task 2 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains local/fake controlled smoke only: Task 2 added the library happy-path smoke for `prepare_next_real_run -> fake C-7-style artifacts -> check_real_run -> check_metric_results -> record_real_result`, including ledger, optimizer state, best-candidate, reports, and unresolved-run guard assertions. Drift: none; no real tools, subprocess-backed C-7 adapter, network, PSF parsing, formula rewriting, Task 3 retry flow, Task 4 CLI smoke, or final gate work was added.

C-11 Task 2 review evidence: spec-compliance review approved by Socrates (`019e8caf-9520-75e3-9cf4-e9d913d872d0`) with no Critical, Important, or Minor findings. Code-quality review approved by Dirac (`019e8cb1-9279-7273-a76e-7e760fed813e`) with no Critical, Important, or Minor findings.

C-11 Task 3 checkpoint: Active scope is Plan C C-11 Task 3 controlled failure/retry smoke. Added the controlled failure/retry library smoke for `real_001 -> real_002 failed -> real_003 retry success -> real_004 next package`, including `TOOL_RESULT_FAILED`, `RETRY_SAME_CANDIDATE`, unresolved-run blocking, retry metadata, checked retry recording, source-run `ALREADY_RECORDED`, ledger rows, and post-retry no-unresolved assertions.

C-11 Task 3 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains local/fake controlled smoke only: Task 3 uses synthetic C-7-style failed/success artifacts and existing Hermes validators/recovery/recording APIs. Drift: none; no real tools, subprocess-backed C-7 adapter, network, PSF parsing, formula rewriting, Task 4 CLI smoke, or final gate work was added.

C-11 Task 3 review evidence: spec-compliance review approved by Ptolemy (`019e8cc5-30bf-7022-bca2-657b57fec88a`) after stale handoff prompts were fixed, with no remaining Critical, Important, or Minor findings. Code-quality review approved by Heisenberg (`019e8cc8-c26b-7ef2-8fd4-d5679088521d`) with no Critical, Important, or Minor findings.

C-11 Task 4 implementation checkpoint: Added the narrow CLI smoke for `prepare-next-real-run -> fake C-7-style returned artifacts -> check-real-run -> check-metric-results -> record-real-result`. The CLI smoke uses `CliRunner` against `hermes_workflow.cli.app`, seeds checked `real_001`, prepares explicit `real_002`, validates supervisor-facing output strings, writes synthetic project-relative result/metric manifests, checks and records the run, and verifies ledger rows `real_001` and `real_002`.

C-11 Task 4 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains local/fake controlled smoke only: C-11 verifies the C-9 -> fake C-7-style returned artifacts -> C-5/C-6 checks -> C-8 happy path and one C-10 failure/retry path without real Virtuoso/Spectre/OCEAN/SSH/agent/bridge execution. Drift: none; no real tools, subprocess-backed C-7 adapter, network, PSF parsing, or formula rewriting were added. Status is complete and reviewed.

C-11 Task 4 review evidence: spec-compliance review approved by Aquinas (`019e8cd9-0de1-78e0-9201-560c807edc39`) with no findings. Code-quality review approved by Feynman (`019e8cd9-33ae-7880-aab0-767a5ed1facb`); the only low bookkeeping finding was the already-completed Step 6 checkbox, fixed in the final status update.

C-12 route audit: Active spec is `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains contract-led: C-12 is a one-cell, one-run, evidence-gated real-tool/agent practice that uses Hermes workflow tooling to prepare/check/record and uses the execution-agent/C-7 adapter boundary for real Spectre + OCEAN execution. Drift: none; the design spec does not authorize ad-hoc real-tool execution before an implementation plan is written and approved, does not allow Python PSF parsing, and does not allow formula rewriting.

C-12 implementation plan checkpoint: Active plan is `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`. The plan breaks C-12 into five gated tasks: local workspace/input gate, Hermes preflight and approved package, user-confirmed execution-agent/C-7 adapter invocation, Hermes check/record or recovery assessment, and sanitized evidence/final gate. No real tools were run while writing the plan.

C-12 Task 1 blocker checkpoint: local practice workspace was created under `/tmp/ic_auto_opt_c12`, `hermes-workflow` was found at `/home/zzchen/.venvs/openclaw/bin/hermes-workflow` with version `0.1.0`, `hermes-workflow init /tmp/ic_auto_opt_c12/bridge_test_inv` succeeded, fixed cell contract values were confirmed, and approved OCEAN formula text was confirmed. Task 1 stopped at Step 7 because `/tmp/ic_auto_opt_c12/bridge_test_inv/netlists/exported/input.scs` is missing. Route audit: active spec is `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains contract-led and evidence-gated. Drift: none. No real tools, C-7 adapter, SSH, bridge, PSF parsing, formula rewriting, or sample deck copying were used.

C-12 Task 1 blocker review evidence: spec-compliance review approved by Plato (`019e8d35-a238-7980-ba60-607d6457152d`) with no Critical, Important, or Minor findings. Code-quality review approved by Aristotle (`019e8d36-b189-7a02-aa9f-fb52a510daef`) for the modified tracked-file changes. The only Important residual risk is that untracked `docs/OCEAN_DOC_*` and `docs/toolchain_evidence/` remain an accidental-commit risk; use explicit pathspecs only.

C-12 Task 1 input gate completion checkpoint: `/tmp/ic_auto_opt_c12/bridge_test_inv/netlists/exported/input.scs` now exists, and its local-only SHA256 evidence file was written to `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/exported_input_scs.sha256`. Route audit remains aligned with the C-12 spec and top-level plan. Drift: none. No real tools, C-7 adapter, SSH, bridge, PSF parsing, formula rewriting, or deck commit occurred.

C-12 Task 1 completion review evidence: spec-compliance review approved by Epicurus (`019e8d56-4dd7-7712-b7ae-abdc6fc88c02`) after fixing the Step 10 pathspec Minor. Code-quality review approved by Ohm (`019e8d58-ba6e-7b42-91fe-ef05eb5b611e`) with no Critical, Important, or Minor findings. Task 1 is complete and reviewed; do not start Task 2 until the user confirms.

C-12 Task 2 checkpoint: user confirmed the provided `input.scs` corresponds to the template `metrics.yaml`, then Hermes `validate`, `package`, `prepare-netlist`, `dry-run`, `preflight-health`, `approve`, and `prepare-real-run --run-id real_001` all completed. `real_001` exists under `/tmp/ic_auto_opt_c12/bridge_test_inv/runs/real/real_001`, and local-only pre-execution hashes were written to `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/real_001_pre_execution_hashes.sha256`. Plan correction: the approval file exists at `$C12_PROJECT/supervisor_instruction.json`, matching `src/hermes_workflow/approvals.py` and `src/hermes_workflow/real_run.py`; the implementation plan Step 6 expected path was corrected from `reports/supervisor_instruction.json`. Route audit remains aligned with the C-12 spec and top-level plan. Drift: none. No real Spectre/OCEAN execution, C-7 adapter invocation, SSH, bridge, PSF parsing, formula rewriting, or deck commit occurred.

C-12 Task 2 review evidence: spec-compliance review approved by Noether (`019e8d66-cfe1-73a2-9b12-a70c59305735`) with no findings. Code-quality review approved by Mill (`019e8d68-4d37-7ba0-98fa-4892078d7aed`) after stale C-12 overview wording was fixed. Task 2 is complete and reviewed; Task 3 remains blocked until the user explicitly confirms real Spectre/OCEAN adapter execution.

C-12 Task 3 checkpoint: execution-agent/C-7 adapter invocation failed or was blocked for real_001. Returned artifacts/logs were preserved locally; Hermes failure checks and recovery assessment are pending.

No manual manifest repair, PSF parsing, or formula rewriting occurred.

C-12 Task 3 route audit: Active spec is `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`; active plan is `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains contract-led and evidence-gated: user explicitly confirmed Task 3, Spectre/OCEAN visibility was checked, and real execution occurred only through the execution-agent/C-7 adapter entry point. Drift found and synchronized: the local `csh` command must use `-fc` rather than unsupported `-lc`, and future transcript pipelines should preserve adapter exit status with pipefail. Real outcome: the adapter wrote `result_manifest.json` with `status: failed`, `metric_result_manifest: null`, and `notes: spectre command failed`; `spectre.stdout` reports `SPECTRE-132` because the current adapter `-log psf/spectre.out` argument is interpreted as a second input file by this Spectre invocation. This exposes a C-7 adapter command-compatibility issue for later scope; Task 3 did not hand-edit returned artifacts or rerun with overwrite.

C-12 Task 3 review evidence: spec-compliance review approved by Heisenberg (`019e8d87-de02-7a11-aa3f-cf7ab47895cb`) after stale resume prompts were fixed. Code-quality/evidence review approved by Pascal (`019e8d8d-707e-7052-b58e-1488b3fdd145`) after the current-state Task 4 confirmation gate and canonical Task 3 spec-review evidence were fixed. Both reviews reported no remaining Critical, Important, or Minor findings. Task 3 is complete and reviewed; do not enter Task 4 or rerun the adapter without user confirmation.

C-12 Task 4 checkpoint: Hermes validation or recording failed for real_001. Recovery assessment was written locally and no unchecked result was recorded.

C-12 Task 4 route audit: Active spec is `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`; active plan is `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`. Alignment remains contract-led and evidence-gated: Task 4 used only Hermes workflow tooling against the returned C-7 adapter artifacts already present under `/tmp`; `check-real-run` passed for the failed handoff manifest structure, `check-metric-results` failed closed because the simulator result was failed and `metric_result_manifest` was absent, `record-real-result` was skipped, and `assess-real-run-recovery` classified `real_001` as `tool_result_failed` with `retry_same_candidate` recommended. Drift: none. No adapter rerun, real tool rerun, manual manifest repair, PSF parsing, formula rewriting, retry package preparation, or optimizer ledger/state row occurred.

C-12 Task 4 review evidence: spec-compliance review approved by Euclid (`019e8da2-93d8-7b60-b406-cd1b2e136e3a`) with no findings. Code-quality/evidence review approved by Ramanujan (`019e8da5-684d-71d0-a48c-4624e76df34a`) after stale C-12 overview/checkpoint wording and the Task 4 commit pathspec were fixed; re-review found no Critical, Important, or Minor findings.

Fast C-7 debug lane checkpoint: user explicitly authorized quick real-tool debugging after C-12 exposed a real adapter failure. Root cause for SPECTRE-132 was confirmed: C-7 used `-log psf/spectre.out`, but this Spectre invocation requires `=log psf/spectre.out` for log-file-only output. Working tree patch now uses `=log`. Real-tool debug then exposed follow-up contract gaps: relative include sidecars such as `ade_e.scs` are not packaged into run dirs, whitespace unit values such as `"0.3 um"` render into invalid Spectre parameter assignments, and sample ADE/Maestro metric formulas use a slash namespace that the current standalone adapter PSF does not expose. Detailed sanitized record: `docs/debug/2026-06-03-c7-real-tool-debug-lane.md`. Status is verified-only, not reviewed.

C-7 closure plan checkpoint: `=log` command fix committed as `51fc057`. New focused plan: `docs/superpowers/plans/2026-06-03-c7-real-tool-closure-fixes.md`. It freezes new feature development and scopes only the remaining real-tool closure fixes: exported netlist sidecars, Spectre-safe unit formatting, metric namespace/formula contract, and a final authorized real closure smoke.

C-7 closure Task 0 evidence inventory checkpoint: local bundle prepared at `/tmp/ic_auto_opt_real_tool_evidence/` with 777 hashed files and a file tree under `/tmp/ic_auto_opt_real_tool_evidence/manifests/`. Repo index added at `docs/debug/2026-06-03-real-tool-evidence-index.md`. The bundle includes inverter Spectre/OCEAN smoke evidence, mixer PSS/PAC OCEAN probe evidence, C-7 adapter debug contexts, and C-12 controlled real-tool practice evidence. Raw files remain local-only and must not be staged or committed. Current scope remains C-7 Real Tool Closure Fixes. next_allowed_action: start C-7 Real Tool Closure Fixes Task 1 exported netlist bundle sidecars; do not run real tools until sidecar/unit/formula contract fixes are complete and user authorizes the closure smoke.

C-7 closure Task 1 checkpoint: complete, verified-only. Added tests for preserving exported netlist sidecars and rejecting symlinked exported bundle entries. `prepare-real-run` now copies safe regular files from `netlists/exported/` into the real run directory before writing the rendered `input.scs`, so relative sidecars such as `ade_e.scs`, hidden simulator files, and nested directories can travel with the prepared run package. Verification passed with focused real-run/next-run/recovery tests, C-7 adapter tests, ruff, and `git diff --check`. Current scope remains C-7 Real Tool Closure Fixes. next_allowed_action: start C-7 Real Tool Closure Fixes Task 2 Spectre-safe unit formatting guard; do not run real tools until sidecar/unit/formula contract fixes are complete and user authorizes the closure smoke.

C-7 closure Task 2 checkpoint: complete, verified-only. Added validation coverage that rejects whitespace-separated unit suffixes such as `0.3 um` for `continuous_step` variables. Shipped template and test fixture variable ranges now use compact Spectre-safe suffixes such as `0.3u`, `3u`, and `0.2u`. Mock optimizer continuous candidate generation now preserves compact unit formatting, so prepared Spectre parameter assignments render as `WN=0.3u` instead of `WN=0.3 um`. Verification passed with focused validation/mock/dry-run/real-run/next-run/recovery tests, C-7 adapter tests, ruff, cadence checker, and `git diff --check`.

C-7 real-tool closure checkpoint: complete, verified-only. The fix follows the proven Phase4 Cadence flow instead of changing metric formulas. Root cause: flattening the Maestro netlist bundle into `runs/real/<run_id>/` made OCEAN see plain signal names; running Spectre from `runs/real/<run_id>/netlist/` with sibling `runs/real/<run_id>/psf/` restores slash names such as `/VOUT`, `/VDD`, and `/M0/S`. Code now prepares `runs/real/<run_id>/netlist/input.scs`, copies exported sidecars into that `netlist` directory, runs Spectre from it, and leaves approved OCEAN formulas unchanged. Real closure passed in `/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv`: adapter succeeded, `check-real-run` passed, `check-metric-results` passed, and `record-real-result` wrote ledger/state. Verification: `python3 -m pytest -q` passed 445 tests; `python3 -m ruff check .` passed. next_allowed_action: commit this C-7 closure fix with explicit pathspecs, then decide whether to rerun C-12 controlled real-tool practice from a clean project.

The C-10 design spec and implementation plan remain aligned with the implementation: failed `input.scs` is preserved literally for retry packages, approved OCEAN formula contracts are compared by text/hash and are not rewritten, retry targets and decision files reject symlink/overwrite hazards, CLI commands delegate to recovery logic only, unsafe declared result artifacts classify as partial tool results, and C-10 still does not write optimizer ledger/state or call real tools.

C-10 Task 4 review found and fixed two route-sensitive deadlocks: a retry-prepared source run no longer blocks forever after the retry run is recorded by C-8, and it no longer blocks forever after the retry run itself is resolved abandoned. Code-quality review also found and fixed hidden report writes from the guard path; `assert_no_unresolved_real_runs()` now keeps nested checker calls non-persistent when used as a C-9 guard. C-10 Task 5 review found and fixed stale recovery-report output for pre-assessment validation failures; CLI now prints report details only when the current command updates the recovery report. Final review found and fixed unsafe artifact classification and symlinked decision-read hardening.

Workspace-level agent constraints now exist in `AGENTS.md`. Future agents should read it before code or docs changes; it locks the role model, contract-only boundaries, formula safety policy, per-task stop-and-report cadence, and the user's coding guidelines for explicit assumptions, simplicity, surgical changes, and verification-first execution.

## Completed Scope

- Plan A Hermes File Contract MVP Task 1-9: complete.
- Plan B mock optimization loop: complete.
- Plan C C-1 netlist template contract: complete.
- Plan C C-2 dry-run candidate renderer: complete.
- Plan C C-3 execution package preflight readiness: complete and reviewed.
- Plan C C-4 post-approval real-run execution contract: complete and reviewed.
- Plan C C-5 real-run result handoff contract: complete and reviewed.
- Plan C C-5.5 dual-agent result handoff simulation gate: complete; simulation gate passed.
- Toolchain evidence for Spectre + OCEAN metric extraction: complete.
- Plan C C-6 Spectre + OCEAN metric result contract: complete and reviewed.
- Plan C C-7 Spectre + OCEAN execution adapter: complete and reviewed.
- Plan C C-8 real result ledger/state update: complete and reviewed.
- Plan C C-9 next real-run package contract: complete and reviewed.
- Plan C C-10 real-run failure/retry policy contract: complete and reviewed.
- Plan C C-11 local/fake controlled smoke: complete and reviewed.
- Plan C C-12 controlled real-tool/agent practice: Task 4 complete and reviewed; Hermes classified the structured Spectre failure as `tool_result_failed` and did not record an unchecked result.

## Spectre + OCEAN Backend Decision

Confirmed route:

```text
Maestro/ADE exports or provides input.scs
-> Hermes templates only approved top-level Spectre parameters
-> Hermes prepares approved real-run package
-> execution agent runs standalone Spectre
-> execution agent runs batch OCEAN on the generated PSF
-> OCEAN evaluates exact user/project-approved formulas
-> Python records scalar outputs, formula text, result path, logs, and provenance
```

Evidence:

- Inverter transient/DC smoke:
  - Directory: `docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/`
  - Result: Maestro point-level PSF and standalone Spectre replay PSF both opened in batch OCEAN.
  - Scalar values for `rise`, `fall`, and `DC` matched between Maestro PSF OCEAN and standalone PSF OCEAN.
- Mixer PSS/PAC/PNoise probe:
  - Directory: `docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/`
  - Summary: `PSS_PAC_DIRECTPLOT_OCEAN_SUMMARY.md`
  - Result: Maestro point-level PSF and standalone Spectre replay PSF both opened in batch OCEAN.
  - Scalar values for `BW` and `MAX_GAIN` matched between Maestro PSF OCEAN and standalone PSF OCEAN.
  - `drplPacVolGnExpDen` is callable in batch OCEAN in this environment, but formula rewriting is not allowed. Evaluate the exact approved formula.

Policy locked by this evidence:

- `metrics.yaml` formulas are authoritative contract inputs.
- Maestro/ADE formula discovery may generate drafts, but user/project approval is required before execution.
- Do not translate `vh` to `drpl` or `drpl` to `vh`.
- Do not parse PSF in Python.
- Do not reimplement Calculator/OCEAN formulas in Python.

## Plan C-6 Implementation Node

Implemented:

- `metrics.yaml` supports exact approved executable OCEAN formula blocks.
- `spectre.yaml` accepts `psfxl`; C-6 real metric request generation requires an OCEAN-ready output format.
- `prepare-real-run` writes `metric_extraction_request.json` and records its SHA-256 in `real_run_manifest.json`.
- Returned `result_manifest.json` can reference PSF artifacts and `metric_result_manifest.json`.
- `check-metric-results` validates request authority, formula text/hash, metric identity, finite scalar values, simulator handoff status, and artifact path safety.

Current verification:

```bash
python3 -m pytest -q
# 282 passed

python3 -m ruff check src tests tools
# All checks passed

git diff --check
# no output
```

Still excluded:

- Hermes running Spectre or OCEAN.
- Python parsing PSF/waveform data.
- Python reimplementing OCEAN/Calculator formulas.
- Optimizer ledger append or optimizer state update from real metrics.

Plan C-4 Task 1-4 added:

- `src/hermes_workflow/real_run.py`: post-approval guard, execution manifest loading, supervisor instruction loading, approved config hash equality check, immutable config drift guard, lower-bound first real-run candidate rendering, `candidate.json`, `real_run_manifest.json`, overwrite refusal, and partial-run cleanup.
- `tests/test_real_run.py`: 14 focused tests for guard failures, successful package creation, hash mismatch, template rendering, run-id validation, missing template, unexpected template variables, overwrite refusal, and write-failure cleanup.
- `hermes-workflow prepare-real-run`: CLI command that prepares `runs/real/real_001/` after approval and reports expected contract failures without tracebacks.

Plan C-3 added or aligned:

- `EXECUTION_TASK.md` responsibility split: execution agent exports or places `netlists/exported/input.scs`; Hermes owns deterministic preflight.
- `src/hermes_workflow/health.py`: writes `state/health_check.json` and fails closed when pre-approval real-run artifacts exist.
- `hermes-workflow preflight-health PROJECT_DIR`: CLI wrapper around the health report writer.
- Approval wording: generic preflight wording, no Claude-specific preflight wording.
- End-to-end pre-approval regression coverage: `init -> package -> prepare-netlist -> dry-run -> preflight-health -> approve`.
- Task 6 final verification and review gate: complete.
- Code-quality hardening: missing preflight reports now reject structurally, package failures clean up partial execution packages, required preflight report paths have one source, and health best-candidate path handling is constant-backed.

## Important Commits

Plan C-3 design and plan:

- `a60b229 docs: design preflight readiness contract`
- `1233954 docs: plan preflight readiness contract`

Plan C-3 implementation:

- `362f34c fix: align execution package preflight contract`
- `adb3f4a fix: clarify execution task templating ownership`
- `caf2175 feat: write preflight health reports`
- `5bae3c1 test: cover optimizer state preflight artifact`
- `ded8d11 feat: add preflight health cli`
- `79df214 test: cover preapproval readiness flow`
- `900dcf2 fix: harden preapproval flow tests`
- `edb107f fix: harden preflight readiness gates`

Plan C-3 handoff/docs cleanup:

- `a4e2473 docs: record preflight readiness progress`
- `bbbfcd7 docs: fill preflight readiness progress hash`
- `6befb7b docs: clarify preflight readiness resume state`
- `88a8c21 docs: align preflight readiness pending verification`
- `f3bc789 docs: mark stale handoff notes historical`
- `919bb84 docs: refresh opencode handoff for c3 verification`
- `d01d139 docs: clarify c3 final verification scope`
- `f678b7c docs: refresh c3 handoff metadata`

Plan C-4 design:

- `docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md`
- `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`

Plan C-4 implementation commits so far:

- `e195bd9 feat: guard post approval real runs`
- `d6804a8 feat: prepare first real run package`
- `fc34c6d fix: harden real run package creation`
- `1ce650e feat: add prepare real run cli`
- `f40966e docs: record real run package progress`
- `a9bc98f docs: close real run package contract`

Plan C-5 design and plan:

- `ce4ce0d docs: design real run result handoff contract`
- `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`

Plan C-5 implementation commits so far:

- `55ec944 feat: add real run check report models`
- `ced01cc feat: validate real run result handoff`
- `72d1696 fix: harden real run handoff validation`
- `414d61f fix: validate real run result manifest shape`
- `8272b04 feat: add real run handoff cli`
- `36a027a docs: record real run result handoff progress`

Plan C-5.5 design and plan:

- `929d657 docs: design dual agent result handoff simulation`
- `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`
- Simulation report: `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`

## Final Verification

Task 6 final verification:

```bash
pytest tests/test_approvals.py tests/test_package.py tests/test_reports.py tests/test_health.py -q
# 28 passed

pytest -q
# 173 passed

ruff check .
# All checks passed
```

Final review gates:

- Final spec review: passed; no Critical or Important findings.
- Final code-quality review: passed after `edb107f`; no Critical or Important findings.
- C-5 combined final spec/code-quality review: passed with no Critical or Important findings. Minor findings only: clearer missing prepared input message, no dedicated CLI `--run-id` test, and harmless sorted-key test fixture mismatch.

C-5 final verification:

```bash
pytest tests/test_result_handoff.py tests/test_cli.py -v
# 40 passed

pytest -q
# 211 passed

ruff check .
# All checks passed
```

C-5.5 final verification: `pytest -q` passed with 211 tests; `ruff check .` passed; combined docs/spec review passed with no Critical or Important findings.

```bash
pytest -q
# 211 passed

ruff check .
# All checks passed
```

The first combined review found report-evidence gaps; the re-review found those addressed and only Task 5 bookkeeping remained. The closeout commit addresses that bookkeeping.

## Plan C-8 Implementation Node

Implemented:

- `LedgerRow` and real-result record report schemas support real-result provenance without breaking mock rows.
- `record_real_result()` reruns `check-real-run` and `check-metric-results` in memory before optimizer writes.
- Precondition failures, missing manifests, duplicate `run_id`, duplicate `candidate_id`, and invalid ledger rows fail closed before unsafe writes. `state/best_candidate.json` is derived from ledger rows and is repaired or removed when stale.
- Checked real metric results append to `ledger/experiment_ledger.jsonl`, update `state/optimizer_state.json`, and update `state/best_candidate.json` only when feasible and better.
- `hermes-workflow record-real-result PROJECT_DIR --run-id real_001` formats pass/fail output and writes `reports/real_result_record_report.json`.

Current verification:

```bash
python3 -m pytest -q
# 362 passed

python3 -m ruff check src tests tools
# All checks passed

git diff --check
# no output
```

Still excluded from Hermes validators:

- running Spectre/OCEAN from Hermes workflow tooling
- calling the C-7 adapter from Hermes validators
- parsing PSF or waveform data in Python
- recomputing OCEAN/Calculator formulas in Python
- failure-penalty ledger rows for failed real tool execution

## Plan C-9 Implementation Node

Implemented:

- `prepare_next_real_run()` selects the next unique candidate from the deterministic optimizer initialization sequence after C-8 records a checked real result.
- `hermes-workflow prepare-next-real-run` writes the next C-4/C-6-compatible package under `runs/real/<run_id>/`.
- C-9 deduplicates against strict ledger rows and already prepared run packages.
- C-9 validates immutable config hashes, optimizer state consistency, ledger schema, max-evaluation bounds, run-id safety, overwrite safety, partial run directory safety, and symlinked real-run directory refusal.
- Fake handoff coverage confirms `real_002` can flow through `check-real-run`, `check-metric-results`, and `record-real-result`.

Still excluded:

- running real tools from C-9
- calling the C-7 adapter from C-9
- parsing PSF or waveform data in Python
- rewriting OCEAN formulas
- writing optimizer ledger/state in C-9
- failure-penalty ledger rows for failed real tool execution

## Plan C-10 Planning Node

Design and plan:

- Spec: `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- Plan: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`
- Commits:
  - `68c404a docs: design real run failure retry policy`
  - `13d39e9 docs: plan real run failure retry policy`

Planned implementation:

- Task 1: recovery report schema. Complete and reviewed in `104ef26 feat: add real run recovery report schema`.
- Task 2: deterministic recovery classifier. Complete and reviewed in `a9dc13a feat: classify real run recovery state`.
- Task 3: recovery decisions and retry package writer. Complete and reviewed in `c76f152 feat: prepare real run retry packages`.
- Task 4: C-9 unresolved real-run guard. Complete and reviewed in `e6d19a5 feat: block next runs on unresolved real runs`.
- Task 5: CLI integration. Complete and reviewed in `7994d83 feat: add real run recovery cli`.
- Task 6: docs, progress, final verification. Complete and reviewed.

Task 3 verification and review:

- `python3 -m pytest tests/test_real_run_recovery.py -q`: passed, 36 tests.
- `python3 -m pytest tests/test_real_run_recovery.py tests/test_real_run.py tests/test_metric_results.py tests/test_result_handoff.py tests/test_real_result_record.py -q`: passed, 151 tests.
- `python3 -m ruff check src/hermes_workflow/real_run.py src/hermes_workflow/real_run_recovery.py tests/test_real_run_recovery.py`: passed.
- `git diff --check`: passed.
- Spec review passed after hardening parent/dangling symlink handling, exact failed-input preservation, metric formula contract comparison, and plan/design sync.
- Code-quality review passed with no Critical, Important, or Minor findings.

Task 4 verification and review:

- `python3 -m pytest tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_pending_package tests/test_next_real_run.py::test_prepare_next_real_run_refuses_unresolved_failed_package tests/test_next_real_run.py::test_prepare_next_real_run_continues_after_abandoned_candidate tests/test_next_real_run.py::test_prepare_next_real_run_refuses_symlinked_real_run_parent -q`: passed, 4 tests.
- `python3 -m pytest tests/test_real_run_recovery.py::test_unresolved_guard_blocks_retry_prepared_decision tests/test_real_run_recovery.py::test_unresolved_guard_allows_c9_after_retry_is_recorded tests/test_real_run_recovery.py::test_unresolved_guard_allows_c9_after_retry_is_abandoned -q`: passed, 3 tests.
- `python3 -m pytest tests/test_real_run_recovery.py::test_unresolved_guard_does_not_persist_checker_reports tests/test_next_real_run.py::test_prepare_next_real_run_refuses_invalid_ledger tests/test_next_real_run.py::test_prepare_next_real_run_refuses_coerced_ledger_types -q`: passed, 3 tests.
- `python3 -m pytest tests/test_next_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py -q`: passed, 83 tests.
- `python3 -m pytest -q`: passed, 424 tests.
- `python3 -m ruff check src tests tools`: passed.
- `git diff --check`: passed.
- Spec review initially found retry resolution deadlocks; both were fixed and re-reviewed. Final spec review passed.
- Code-quality review initially found hidden checker report writes from the guard path; this was fixed and re-reviewed. Final code-quality review passed.

Locked C-10 boundary:

- C-10 is contract-only.
- C-10 does not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- C-10 does not parse PSF, rewrite formulas, write optimizer ledger/state, or add failure-penalty rows.
- C-10 final gate has passed. C-11 local smoke is now the next scope, but should stay local/fake controlled before direct real tool/agent integration.

## Next Task

C-6, C-7, C-8, C-9, and C-10 are closed. The workflow remains on a per-task stop-and-report cadence. Next:

- Start C-11 local smoke design/plan: chain C-9 -> C-7 -> C-8 with one controlled C-10 failure/retry case.
- C-11 should remain a local/fake controlled smoke first; do not jump straight to real Virtuoso/Spectre/OCEAN/agent integration.

## Completed C-5.5 Dual-Agent Result Handoff Simulation Gate

C-5.5 ran before any real Hermes or Claude CLI tool integration. It used two simulated Codex roles:

- Execution-agent role: receives only the C-4 package contract and writes `runs/real/real_001/result_manifest.json` plus sanitized fake artifacts.
- Hermes-observer role: runs `check-real-run`, inspects `reports/real_run_check_report.json`, and records whether unsafe or ambiguous behavior was blocked by deterministic file checks.

Simulation cases:

- Happy path: valid `succeeded` handoff.
- Valid simulator failure: `status: failed` with existing sanitized log.
- Unsafe path attempt: absolute or traversal artifact path.
- Mutated prepared deck: changed `input.scs` after C-4.
- Identity mismatch: wrong `candidate_id` or `run_id`.

C-5.5 did not call real Spectre, real Virtuoso, real Hermes, or real Claude CLI as an execution agent. It validated the workflow behavior gate before physical tool adapters. The later toolchain evidence did call real Maestro/Spectre/OCEAN through `virtuoso-bridge-lite` to validate backend feasibility; that evidence is separate from C-5.5 and should inform C-6.

Report:

- `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`

## Local Data Warning

Real `input.scs` examples under:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example
```

are local reference material only. Do not copy or commit them into the repository.

## Optimizer Practice-First Node

Current scope: `Optimizer Practice-First Plan`.

Status: planned, verified-only.

- C-7 real-tool closure is complete and committed as `d440c95 fix: preserve ADE netlist layout for real runs`.
- The next development direction is not optimizer implementation yet. It is an optimizer practice-first flow recorded in `docs/superpowers/plans/2026-06-03-optimizer-practice-first.md`.
- The known-good Spectre + OCEAN single-point chain is only the foundation check. A few hand-picked candidate points are not sufficient to validate optimizer development.
- Before Hermes optimizer development, the practice must use `virtuoso-bridge-lite/skills/optimizer/SKILL.md` and local TuRBO at `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO`.
- For four `bridge_test_inv` variables, the minimum TuRBO practice budget is `n_init=8`, `max_evals=9`, `batch_size=1`, so at least one candidate is chosen after TuRBO's initial sample set.
- No new optimizer algorithm, schema, broad framework, PSF parser, or formula rewrite is authorized by this plan.
next_allowed_action: wait for user confirmation, then execute Optimizer Practice-First Task 4 only.

Task 1 baseline package shape checkpoint:

- Status: complete, verified-only.
- Practice project: `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv`.
- Netlist bundle source: `/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv/netlists/exported`.
- Passed commands: `hermes-workflow init`, `validate`, `package`, `prepare-netlist`, `dry-run`, `preflight-health`, `approve`, and `prepare-real-run --run-id real_001`.
- Verified package shape: `runs/real/real_001/netlist/input.scs`, sidecars such as `netlist/ade_e.scs`, and `netlist/amap/`.
- Verified `metric_extraction_request.json` keeps approved expressions unchanged and declares `expected_psf_dir` as `runs/real/real_001/psf`.
- No Spectre, OCEAN, C-7 adapter, TuRBO, or optimizer loop was run in Task 1.

Task 2 single-point replay checkpoint:

- Status: complete, verified-only.
- Initial replay on `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv` returned `rise/fall non_scalar` for `FN=2`, `WN=0.3u`, `FP=2`, `WP=0.3u`.
- Interpretation: because the same OCEAN script, metric request, Maestro/ADE layout, and approved formulas still produce scalars for other parameter points, this is candidate-level performance failure, not OCEAN/formula/layout drift. A parameter point that cannot produce the required scalar metrics should be treated as not satisfying the performance target.
- Optimizer practice must treat this class of metric failure as a finite penalty or constraint failure for the candidate, not as a workflow/tool-chain failure.
- Successful replay workspace: `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv_baseline_001`.
- Successful baseline parameters: `FN=4`, `WN=0.6u`, `FP=4`, `WP=1.2u`.
- Passed commands: C-7 adapter through the sourced Cadence shell, `hermes-workflow check-real-run`, `check-metric-results`, and `record-real-result`.
- Metrics exactly matched C-7 closure: `rise=7.52016846017672e-11 s`, `fall=1.078998721053984e-10 s`, `DC=0.0002588877964196586 W`.
- Ledger has one checked real row and `state/optimizer_state.json` has `current_evaluations = 1`.
- `state/best_candidate.json` is absent because the checked row is `real_constraint_fail`; this does not block Task 2.
- No Hermes code, OCEAN formula, adapter layout, or PSF parser change was made.

Task 3 optimizer skill and TuRBO environment gate:

- Status: complete, verified-only.
- `virtuoso-bridge-lite/skills/optimizer/SKILL.md` was read. It confirms black-box optimization, TuRBO/scipy backend choices, TuRBO's minimum `2 * n_params` initialization guidance, minimization semantics, and finite failure penalties rather than `nan`/`inf`.
- Project-local Linux `.venv` was created under `ic-auto-opt-workflow/.venv` and ignored via `.gitignore`.
- `.venv` was populated with CPU-only `torch=2.12.0+cpu`, `gpytorch=1.15.2`, `numpy=2.4.6`, and `scipy=1.17.1`.
- Local TuRBO import passed with `.venv/bin/python`: `from turbo import Turbo1` printed `Turbo1`.
- Route audit: aligned with the practice-first plan and top-level plan. No Hermes optimizer code, real tools, C-7 adapter run, PSF parser, formula rewrite, or broad framework asset was added.
- next_allowed_action: wait for user confirmation, then execute Optimizer Practice-First Task 4 only.

Task 4 native optimizer full-loop practice:

- Status: complete, verified-only.
- Temporary script: `/tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py`.
- Evidence directory: `/tmp/ic_auto_opt_optimizer_practice/turbo_bridge_test_inv_001/`.
- Launch command: `./.venv/bin/python /tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py`.
- The run used `Turbo1`, `PARAMS = ["FN", "WN", "FP", "WP"]`, approved variable bounds, `n_init=8`, `max_evals=9`, and `batch_size=1`.
- All evaluations used Hermes package/check/record contracts plus the C-7 Spectre/OCEAN adapter. No PSF parsing or formula rewrite was introduced.
- Result: `evaluation_count=9`, `post_initial_evaluations=1`, `successful_evaluations=9`, `penalty_evaluations=0`.
- Best post-initial TuRBO candidate: `FN=12`, `WN=1.3u`, `FP=2`, `WP=2.5u`, `objective=4.183168953894332e-14`.
- Seven rows were `real_constraint_fail` and two were `real_pass`; all had finite OCEAN scalar metrics.
- next_allowed_action: wait for user confirmation, then execute Optimizer Practice-First Task 5 only.

Task 5 productization decision:

- Status: complete, verified-only.
- Practice note: `docs/debug/2026-06-03-optimizer-practice-first-result.md`.
- Decision: `B. Native optimizer passed but Hermes lacks explicit candidate injection; add that contract first.`
- Rationale: Task 4 proved the real optimizer route, but the temporary script injected candidates by creating isolated `/tmp` projects and locking `config/variables.yaml` lower/upper values to each candidate. That is valid practice evidence but should not become the product interface.
- Smallest next scope: design a narrow candidate-injection package contract so an optimizer-selected parameter set can become a deterministic `runs/real/<run_id>/` package for that exact candidate.
- next_allowed_action: wait for user confirmation, then write a narrow candidate-injection package contract design spec only.

Candidate-injection package contract design:

- Status: complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md`.
- Scope: add a narrow explicit candidate request contract and a package-preparation command, `prepare-candidate-real-run`, so optimizer-selected parameters can become deterministic `runs/real/<run_id>/` packages without rewriting `config/variables.yaml`.
- Boundary: this design does not add optimizer algorithms, does not replace C-4 first real-run preparation, does not replace C-9 deterministic next-run preparation, does not run real tools, and does not parse PSF or rewrite OCEAN formulas.
- Route audit: aligned with the top-level plan and the practice-first decision B. Drift: none.
- next_allowed_action: wait for user confirmation, then write the candidate-injection package contract implementation plan only.

Candidate-injection package contract implementation plan:

- Status: complete, verified-only.
- Implementation plan: `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md`.
- Scope: four narrow tasks: candidate request validation, package writer reuse, CLI plus fake C-7 handoff smoke, and final verification/review gate.
- Boundary: the plan does not authorize real Virtuoso/Spectre/OCEAN/SSH/bridge execution, optimizer algorithm productization, PSF parsing, OCEAN formula rewriting, or replacement of C-4/C-9 flows.
- Route audit: aligned with the active design spec and top-level practice-first route. Drift: none.
- next_allowed_action: wait for user confirmation, then execute Candidate-Injection Package Contract Task 1 only.

Candidate-injection package contract Tasks 1-2:

- Status: complete, verified-only.
- Code: `src/hermes_workflow/real_run.py`.
- Tests: `tests/test_candidate_injection_real_run.py`.
- Task 1 added explicit candidate request validation against `config/variables.yaml`, including safe candidate ids, exact variable names, integer bounds/steps, continuous-step bounds/steps, and Spectre-safe attached unit suffixes.
- Task 2 reused the existing real-run package writer to prepare explicit candidate packages. It writes `runs/real/<run_id>/candidate_request.json`, records `candidate_request_sha256` in `candidate.json` and `real_run_manifest.json`, rejects duplicate ledger candidate ids and parameter tuples, and keeps `config/variables.yaml` unchanged.
- Route audit: aligned with `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md` and the top-level practice-first route. Drift: none. No optimizer algorithm productization, real-tool execution, PSF parsing, OCEAN formula rewriting, C-4 replacement, or C-9 replacement was added.
- Verification: `python3 -m pytest tests/test_candidate_injection_real_run.py -q`; `python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py -q`; `python3 -m ruff check src tests tools`; `python3 tools/check_development_cadence.py`; `git diff --check`.
- next_allowed_action: wait for user confirmation, then execute Candidate-Injection Package Contract Task 3 only.

Candidate-injection package contract Task 3:

- Status: complete, verified-only.
- Code: `src/hermes_workflow/cli.py`.
- Tests: `tests/test_candidate_injection_real_run.py`.
- Added `hermes-workflow prepare-candidate-real-run PROJECT_DIR --candidate-file PATH [--run-id real_###]`.
- Added CLI success/failure coverage and a fake C-7 handoff smoke that prepares `real_002`, writes sanitized fake result and metric manifests, runs `check_real_run`, `check_metric_results`, and `record_real_result`, and verifies the ledger records the explicit optimizer candidate id `candidate_000009`.
- Plan correction: Task 3 uses local fake handoff writers that preserve the explicit candidate id instead of importing `tests.test_next_real_run` helper writers, because those helpers intentionally set `candidate_id` to the run id.
- Route audit: aligned with `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md` and the top-level practice-first route. Drift: none. No optimizer algorithm productization, real-tool execution, PSF parsing, OCEAN formula rewriting, C-4 replacement, or C-9 replacement was added.
- Verification: red test `python3 -m pytest tests/test_candidate_injection_real_run.py -q` failed on missing CLI command; green verification passed with `python3 -m pytest tests/test_candidate_injection_real_run.py -q`, `python3 -m pytest tests/test_cli.py tests/test_candidate_injection_real_run.py -q`, `python3 -m pytest tests/test_next_real_run.py tests/test_real_result_record.py tests/test_metric_results.py -q`, and `python3 -m ruff check src tests tools`.
- next_allowed_action: wait for user confirmation, then execute Candidate-Injection Package Contract Task 4 final verification and review gate only.

Candidate-injection package contract Task 4:

- Status: complete, reviewed.
- Final verification passed: `python3 -m pytest tests/test_candidate_injection_real_run.py -q` (20 passed), `python3 -m pytest tests/test_real_run.py tests/test_next_real_run.py tests/test_real_run_recovery.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_result_record.py tests/test_cli.py -q` (214 passed), `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.
- Initial spec review found required fixes: reject pre-existing override run directories, add true prepared-package duplicate coverage, add forced write-failure cleanup coverage, and reject whitespace-padded continuous candidate values.
- Fixes made: candidate run-id override now rejects any existing `runs/real/<run_id>` directory; continuous candidate values require compact formatting; prepared duplicate tests use resolved-abandoned prepared packages to exercise prepared dedupe; cleanup test uses an exported sidecar symlink failure and confirms the newly created run directory is removed.
- Review gate: spec re-review by Ptolemy passed with no Critical, Important, or Minor findings. Code-quality re-review by Linnaeus passed with no Critical, Important, or Minor findings.
- Route audit: aligned with `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md` and the top-level practice-first route. Drift: none. The review fixes tightened implementation to the existing spec; no optimizer algorithm productization, real-tool execution, PSF parsing, OCEAN formula rewriting, C-4 replacement, or C-9 replacement was added.
- next_allowed_action: wait for user confirmation, then decide the next narrow Hermes optimizer productization scope; do not start broad optimizer framework work

C-13 Single-Candidate Optimizer Suggestion MVP design:

- Status: design spec complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md`.
- Scope: productize only the missing step from recorded optimizer state and ledger to exactly one candidate request JSON compatible with the existing candidate-injection package contract.
- Boundary: C-13 must not run real tools, create a broad optimizer framework, add batch orchestration, parse PSF, rewrite OCEAN formulas, or replace the native Maestro/ADE/Spectre/OCEAN layout.
- Route audit: aligned with the top-level practice-first route and the completed candidate-injection package contract. Drift: none.
- next_allowed_action: write the narrow C-13 implementation plan for single-candidate optimizer suggestion; do not start C-13 code until that plan exists

C-13 Single-Candidate Optimizer Suggestion MVP implementation plan:

- Status: implementation plan complete, verified-only.
- Implementation plan: `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md`.
- Scope: four narrow tasks: library writer with initialization fallback, TuRBO one-step suggestion and safety failures, CLI/fake handoff smoke, and final verification/review gate.
- Boundary: C-13 stays local and contract-only for real-tool behavior. It does not run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or the C-7 subprocess adapter. C-14 is the first real-tool acceptance step.
- Route audit: aligned with `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md` and the top-level practice-first route. Drift: none.
- next_allowed_action: execute C-13 Task 1: Library Writer With Initialization Fallback; do not start Task 2 or real-tool acceptance until Task 1 is complete and recorded

C-13 Single-Candidate Optimizer Suggestion MVP Tasks 1-3:

- Status: complete, verified-only. Final review gate is still pending in Task 4.
- Code: `src/hermes_workflow/optimizer_suggestion.py`, `src/hermes_workflow/cli.py`.
- Tests: `tests/test_optimizer_suggestion.py`.
- Implemented `suggest_candidate_request()` to write exactly one candidate request JSON from checked ledger/state, with initialization fallback, existing unresolved-run guard, existing optimizer-state checks, atomic output writing, existing candidate dedupe inputs, and hashes for ledger/state provenance.
- Added optional one-step TuRBO suggestion path when enough finite observations exist. If TuRBO imports are unavailable, the command explicitly falls back to the existing initialization sequence instead of failing or inventing a new algorithm.
- Added `hermes-workflow suggest-candidate PROJECT_DIR [--candidate-id ID] [--output PATH]`.
- Verified the suggested request can be consumed by `prepare_candidate_real_run()` and does not write `runs/real/<run_id>` itself.
- Verification: `python3 -m pytest tests/test_optimizer_suggestion.py -q`; `python3 -m pytest tests/test_candidate_injection_real_run.py tests/test_next_real_run.py -q`; `python3 -m pytest tests/test_cli.py tests/test_optimizer_suggestion.py -q`; `python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py tests/test_metric_results.py tests/test_cli.py tests/test_optimizer_suggestion.py -q`; `python3 -m ruff check src tests tools`.
- Route audit: aligned with the C-13 spec and implementation plan. Drift: none. No real-tool invocation, PSF parsing, OCEAN formula rewriting, batch loop, daemon, broad optimizer framework, or layout replacement was added.
- next_allowed_action: execute C-13 Task 4 final verification/review gate; do not enter C-14 real-tool acceptance until Task 4 is complete and recorded

C-13 Single-Candidate Optimizer Suggestion MVP Task 4:

- Status: complete, reviewed.
- Final verification passed: `python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py -q` (33 passed); `python3 -m pytest tests/test_next_real_run.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_real_result_record.py tests/test_metric_results.py tests/test_cli.py -q` (186 passed); `python3 -m ruff check src tests tools`; `python3 tools/check_development_cadence.py`; `git diff --check`.
- Initial review findings: spec review found race-unsafe overwrite rejection; code-quality review found race-unsafe overwrite rejection, missing validation of generated candidate requests before write, and incomplete temp cleanup on write/close failures.
- Fixes made: `src/hermes_workflow/optimizer_suggestion.py` now validates the generated payload with `CandidateInjectionRequest`, reuses candidate parameter and uniqueness checks before writing, and publishes via temp file plus no-clobber `os.link()` with cleanup in `finally`. Added direct tests for invalid candidate id before write, missing optimizer state, max evaluations reached, and competing output creation during write.
- Review gate: spec re-review by Hypatia found no Critical, Important, or Minor findings and cleared C-13 as reviewed. Code-quality re-review by Nash found no Critical or Important findings, confirmed C-13 code-quality review passed, and the only Minor stale plan snippet was fixed.
- Route audit: aligned with the C-13 spec and top-level practice-first route. Drift: none. C-13 did not run real tools, parse PSF, rewrite OCEAN formulas, create a broad optimizer framework, add batch orchestration, or replace native layout.
- next_allowed_action: write C-14 real-tool acceptance plan for suggest-candidate -> prepare-candidate-real-run -> C-7 adapter -> check/record; do not run real tools until that plan exists and the user confirms

C-14 Real-Tool Acceptance plan:

- Status: implementation plan complete, verified-only.
- Active spec: `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md` because its Real-Tool Acceptance section defines C-14.
- Implementation plan: `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md`.
- Scope: one clean local acceptance flow, using a known-good seed `real_001`, `hermes-workflow suggest-candidate` for `candidate_000002`, `prepare-candidate-real-run` for `real_002`, the C-7 Spectre/OCEAN adapter, and existing `check-real-run`/`check-metric-results`/`record-real-result` contracts.
- Boundary: no broad optimizer framework, no new algorithms, no batch orchestration, no PSF parsing, no OCEAN formula rewrite, and no native Maestro/ADE layout replacement.
- Route audit: aligned with the top-level practice-first route and C-13's explicit C-14 acceptance requirement. Drift: none.
- next_allowed_action: execute C-14 Task 1 clean acceptance workspace and seed package; do not run real tools until Task 2 is explicitly confirmed

C-14 Real-Tool Acceptance Task 1:

- Status: complete, verified-only.
- Local project: `/tmp/ic_auto_opt_c14/bridge_test_inv`.
- Local evidence: `/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001/`.
- Plan correction: `prepare-candidate-real-run` correctly refuses `real_001`, so Task 1 was corrected to use the C-4 first-run contract for `real_001`; candidate-injection remains the `real_002+` path after a checked ledger row exists.
- Setup completed: Hermes CLI available at `/home/zzchen/.venvs/openclaw/bin/hermes-workflow`, project initialized, known-good C-7 closure netlist bundle copied locally, `input.scs` hash/tree captured under `/tmp`, local acceptance-only lower bounds set to `FN=4`, `WN=0.6u`, `FP=4`, `WP=1.2u`, upper bounds preserved for later suggestions.
- Hermes commands passed: `validate`, `package`, `prepare-netlist`, `dry-run`, `preflight-health`, `approve`, and `prepare-real-run --run-id real_001`.
- Prepared package shape: `runs/real/real_001/netlist/input.scs`, `netlist/ade_e.scs`, `netlist/amap/`, `candidate.json` with the known-good seed parameters, and `metric_extraction_request.json` with approved OCEAN formulas unchanged.
- Route audit: aligned with C-14 plan, C-13 spec, and the top-level practice-first route. Drift found in the initial C-14 plan was corrected: do not use candidate-injection for `real_001`.
- Boundary: no Spectre, OCEAN, SSH, bridge, C-7 adapter, PSF parsing, formula rewrite, raw deck commit, or Cadence artifact commit occurred.
- next_allowed_action: wait for user confirmation, then execute C-14 Task 2 seed real-tool run

C-14 Real-Tool Acceptance Task 2:

- Status: complete, verified-only.
- Local project: `/tmp/ic_auto_opt_c14/bridge_test_inv`.
- Local evidence: `/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001/`.
- First adapter attempt note: running Spectre inside the Codex sandbox failed before OCEAN with `cannot create pipe [Operation not permitted]` and `can't create server socket`. Comparison against C-7 closure showed the Spectre command shape matched the known-good command. Rerunning the same adapter outside the sandbox through the approved Cadence `csh -fc` path succeeded; no adapter command, metric formula, or netlist-layout change was needed.
- Real-tool result: `real_001` produced `result_manifest.json` and `metrics/metric_result_manifest.json`; `check-real-run`, `check-metric-results`, and `record-real-result` all passed.
- OCEAN scalar metrics: `rise=7.52016846017672e-11 s`, `fall=1.078998721053984e-10 s`, `DC=0.0002588877964196586 W`.
- Ledger/state: one ledger row was recorded, `optimizer_state.current_evaluations = 1`, and the row status is `real_constraint_fail`, meaning scalar extraction worked but the seed does not satisfy configured performance constraints.
- Route audit: aligned with C-14 plan, C-13 spec, and the top-level practice-first route. Drift: none. No production code changed, no PSF parsing, no OCEAN formula rewriting, and the native Maestro/ADE layout was preserved.
- next_allowed_action: wait for user confirmation, then execute C-14 Task 3 suggest and package real_002

C-14 Real-Tool Acceptance Tasks 3-5:

- Status: complete, verified-only.
- Task 3: `suggest-candidate` wrote `/tmp/ic_auto_opt_c14/bridge_test_inv/candidate_requests/candidate_000002.json` with selection mode `initialization_fallback`, and `prepare-candidate-real-run` prepared `runs/real/real_002` with the explicit candidate request, candidate manifest, native netlist sidecars, and unchanged approved OCEAN formulas.
- Task 4: `real_002` ran through the existing C-7 Spectre/OCEAN adapter outside the sandbox and succeeded. `check-real-run`, `check-metric-results`, and `record-real-result` all passed.
- Task 4 scalar metrics: `rise=3.326181720494057e-11 s`, `fall=4.973593602698243e-11 s`, `DC=0.0009838038264352862 W`.
- Ledger/state: ledger now has 2 rows and `optimizer_state.current_evaluations = 2`. Both rows have `simulation_status = real_constraint_fail`, meaning scalar extraction worked but neither point satisfied configured performance constraints.
- Task 5 closeout: `docs/debug/2026-06-04-c14-real-tool-acceptance-result.md`.
- Decision: proceed to narrow optimizer loop productization. The next scope should stay small: one explicit loop that repeatedly asks for one candidate, prepares one real-run package, runs the existing C-7 adapter, records the result or classified failure, and stops on a fixed evaluation budget.
- Route audit: aligned with the C-13 real-tool acceptance section and the top-level practice-first route. Drift: none. No production code changed, no PSF parsing, no OCEAN formula rewriting, no returned manifest hand-editing, and native Maestro/ADE layout was preserved.
- next_allowed_action: wait for user confirmation, then plan the narrow optimizer loop productization scope

C-15 Narrow Optimizer Loop Productization Tasks 1-3:

- Status: complete, verified-only; final review gate remains pending.
- Design spec: `docs/superpowers/specs/2026-06-04-narrow-optimizer-loop-productization-design.md`.
- Implementation plan: `docs/superpowers/plans/2026-06-04-narrow-optimizer-loop-productization.md`.
- Code: `src/hermes_workflow/optimizer_loop.py`, `tools/run_real_optimizer_loop.py`.
- Tests: `tests/test_optimizer_loop.py`.
- Task 1 added a small one-cycle orchestration library with injectable adapter runner. It allocates deterministic candidate/run ids, calls existing `suggest-candidate` and `prepare-candidate-real-run` contracts, invokes the adapter runner, then uses existing `check-real-run`, `check-metric-results`, and `record-real-result`.
- Task 2 added `tools/run_real_optimizer_loop.py` with `PROJECT_DIR`, `--max-new-evaluations`, and `--cadence-cshrc`. It writes a sanitized `reports/optimizer_loop_report.json` inside the local project.
- Task 3 real-tool acceptance ran one additional loop cycle on `/tmp/ic_auto_opt_c14/bridge_test_inv`: `candidate_000003` was prepared as `real_003`, the C-7 adapter ran outside the sandbox, Hermes checks passed, and the result was recorded.
- Real `real_003` metrics: `rise=6.508914194299693e-11 s`, `fall=6.17648525412794e-11 s`, `DC=0.0003515194271758733 W`.
- Ledger/state: ledger now has 3 rows; `candidate_000003` is `real_pass` and is the current best candidate.
- Verification so far: `python3 -m pytest tests/test_optimizer_loop.py -q` passed, `python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py -q` passed, and focused ruff for C-15 files passed.
- Route audit: aligned with C-15 design and top-level practice-first route. Drift: none. No new optimizer algorithm, daemon, scheduler, PSF parser, formula rewrite, or native-layout replacement was added.
- next_allowed_action: run C-15 Task 4 final verification, review gate, and closeout before starting any broader optimizer work

C-15 Narrow Optimizer Loop Productization Task 4:

- Status: complete, reviewed.
- Final verification passed: `python3 -m pytest tests/test_optimizer_loop.py -q` (9 passed), `python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py tests/test_real_result_record.py tests/test_metric_results.py -q` (102 passed), `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.
- Review gate: local spec review by Ohm passed with no Critical findings; local code-quality review by Jason passed with no Critical findings. The Important review notes were fixed before closeout: direct `result_check_failed` and `record_failed` tests were added, adapter failure stdout/stderr is bounded in `reports/optimizer_loop_report.json`, and the loop CLI uses the shared `RECORDED` constant.
- Re-review gate: Ohm and Jason both returned PASS with no remaining blockers.
- Route audit: aligned with `docs/superpowers/specs/2026-06-04-narrow-optimizer-loop-productization-design.md` and the top-level practice-first route. Drift: none. C-15 remains a narrow fixed-budget loop around existing contracts and the proven C-7 adapter path; no broad optimizer framework, daemon, scheduler, PSF parser, formula rewrite, or native-layout replacement was added.
- next_allowed_action: wait for user confirmation, then choose the next narrow real-practice-backed optimizer productization step; do not start a broad optimizer framework

C-16 100-Point Real Optimizer Acceptance Task 0:

- Status: complete, verified-only.
- Plan: `docs/superpowers/plans/2026-06-04-100-point-real-optimizer-acceptance.md`.
- User clarified an important settings distinction: Spectre `+mt` is per-Spectre process thread count; `spectre.parallel_jobs` is the maximum number of simultaneous Spectre processes. C-16 must not map `parallel_jobs` to `+mt`.
- Task 0 patch aligns run settings before the 100-point run: `metric_extraction_request.json` carries `spectre.threads_per_run` as per-process `+mt` and `spectre.parallel_jobs` as the concurrency cap, C-7 adapter rejects request/prepared setting drift, Spectre argv now uses requested `preset`, `threads_per_run`, and `output_format`, result manifests record simulator `preset/threads_per_run/output_format/timeout_s`, and `check-real-run` detects recorded simulator setting drift. Current project setting is `+preset=ax`, `+mt=10`, `output_format=psfxl`, and `parallel_jobs=10`.
- Final verification passed: `python3 -m pytest -q` (492 passed), `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.
- Route audit: aligned with the top-level practice-first route. Drift: none. This is a blocker fix before C-16 100-point execution, not broad optimizer framework work.
- next_allowed_action: wait for user confirmation, then start C-16 Task 1 100-point sequential real optimizer run

C-16 100-Point Real Optimizer Acceptance Tasks 1-2:

- Status: complete with follow-up required.
- current_scope: C-16 100-Point Real Optimizer Acceptance closeout.
- Local project: `/tmp/ic_auto_opt_c14/bridge_test_inv`.
- The real loop reached `100` recorded evaluations and `optimizer_state.status = completed`.
- First attempt used system `python3`; it ran real Spectre/OCEAN correctly but did not use TuRBO because that interpreter lacked `torch/gpytorch`. The run was stopped at 55 recorded rows after this was discovered.
- Environment fix: installed the project into the existing `.venv`, which already had `torch/gpytorch`; `.venv` can now import Hermes, TuRBO, `torch`, and `gpytorch`.
- `real_056` had completed result/metric manifests when the invalid fallback run was stopped; Hermes `check-real-run`, `check-metric-results`, and `record-real-result` passed for `real_056`.
- Resumed run used `.venv` and recorded `real_057` through `real_100`.
- TuRBO handoff: `real_057` through `real_091`, `real_093`, and `real_095` through `real_100` used `selection_mode = turbo`.
- Remaining optimizer blocker: `real_092` and `real_094` silently fell back to `selection_mode = initialization_fallback` even after TuRBO was available. The next fix must surface/retry/classify TuRBO duplicate or quantization fallback instead of silently using initialization.
- Spectre/OCEAN contract result: all `check-real-run` and `check-metric-results` reports passed for `real_004` through `real_100`.
- Spectre settings audit: all new result manifests from `real_004` through `real_100` recorded `preset = ax`, `threads_per_run = 10`, `output_format = psfxl`; request/prepared manifests kept `threads_per_run = 10` and `parallel_jobs = 10`.
- Ledger summary: `100` rows total, `8 real_pass`, `92 real_constraint_fail`, `0` recorded tool failures, `0` recorded metric failures.
- Best feasible candidate remains `candidate_000003` / `real_003`, objective `4.4591643476084205e-14`, parameters `FN=6`, `FP=4`, `WN=2.4u`, `WP=1.4u`.
- Route audit: aligned with the practice-first top-level route. Drift found: C-16 is not a clean optimizer acceptance because silent post-TuRBO fallback occurred at `real_092` and `real_094`.
- next_allowed_action: write or implement a narrow TuRBO suggestion robustness fix; do not run another broad 100-point acceptance until silent fallback is surfaced, retried, or classified

## Resume Prompt

```text
请继续 IC auto optimization workflow。当前 repo 是 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow，branch 是 plan-a-hermes-file-contract-mvp。先阅读 docs/CURRENT_TASK_STATE.json、AGENTS.md、docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md、docs/EXECUTION_PROGRESS_2026-05-29.md、docs/COMPACT_RESUME_CHECKPOINT.md、docs/superpowers/plans/2026-06-04-real-tool-acceptance.md，并按需阅读 docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md、docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md、docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md、docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md。当前活动节点是 C-14 Real-Tool Acceptance，Task 1 已完成并 verified-only。下一步只能在用户确认后执行 C-14 Task 2 seed real-tool run；Task 2 会运行真实 Spectre/OCEAN/C-7 adapter。不要写 broad optimizer framework，不要提交 raw input.scs、ade_e.scs、PSF/raw、完整 Cadence log、docs/OCEAN_DOC_*、docs/toolchain_evidence/。不要用 Python 解析 PSF，不要让 agent 翻译或重写 Calculator/OCEAN 公式。
```
