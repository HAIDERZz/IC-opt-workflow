# Compact Resume Checkpoint

Date: 2026-05-28
Last updated: 2026-06-03

This checkpoint preserves the planning state for continuing after context compaction.

## Latest Execution Checkpoint

As of 2026-05-29, implementation has started on branch `plan-a-hermes-file-contract-mvp`.

Read this newer execution handoff first:

```text
ic-auto-opt-workflow/docs/CURRENT_TASK_STATE.json
ic-auto-opt-workflow/docs/EXECUTION_PROGRESS_2026-05-29.md
ic-auto-opt-workflow/docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md
ic-auto-opt-workflow/AGENTS.md
```

Current execution state:

- Task 1 complete and reviewed.
- Task 2 complete and reviewed.
- Task 3 complete and reviewed.
- Task 4 complete and reviewed.
- Claude Review MCP project tooling complete and available.
- Task 5 complete and reviewed.
- Task 6 complete and reviewed.
- Task 7 complete and reviewed.
- Task 8 complete and reviewed.
- Task 9 complete and reviewed.
- Focused Plan A is complete. Hermes File Contract MVP ends at Task 9; there is no Plan A Task 10.
- Plan B mock optimization loop is complete and committed.
- Plan C netlist template contract has started.
- Plan C Task 1 complete and reviewed: `1ab42e1 feat: prepare spectre netlist templates`.
- Plan C Task 2 complete and reviewed: `6ce3e69 fix: support continued spectre parameters`.
- Plan C Task 3 complete and reviewed: `8e59ac9 fix: report unsafe netlist templating failures`.
- Plan C Task 4 complete and reviewed: `04fa358 feat: add prepare netlist cli`.
- Plan C Task 5 complete: full tests, ruff, and local-only real deck smoke passed.
- Plan C Task 6 complete: final review blockers fixed in `da23a7f fix: harden netlist parameter scanner`; final spec and code-quality re-reviews passed.
- Plan C C-1 was complete at this checkpoint. The next scope was confirmed, leading to C-2 and C-3 below.
- Plan C-2 dry-run candidate renderer design spec exists: `e2b1c30 docs: design dry-run candidate renderer`.
- Plan C-2 implementation plan exists: `5441972 docs: plan dry-run candidate renderer`.
- The historical broad plan has been aligned to the current route: the supervisor agent owns planning and decisions; Hermes workflow tooling owns deterministic preflight and file-contract validation; the execution agent owns Maestro export and post-approval real execution.
- The locked role model is documented in `docs/ROLE_MODEL_AND_TERMINOLOGY.md`. Future work must not use "Hermes agent" to mean the supervisor agent.
- C-2 dry-run candidate renderer is complete and reviewed. Final verification: `pytest -q` passed, 159 tests; `ruff check .` passed; local-only smoke passed.
- C-3 execution package preflight readiness design spec exists: `a60b229 docs: design preflight readiness contract`.
- C-3 implementation plan exists: `docs/superpowers/plans/2026-05-30-execution-package-preflight-readiness.md`.
- C-3 is complete and reviewed as of 2026-05-31. Final verification: `pytest -q` passed, 173 tests; `ruff check .` passed; final spec and code-quality reviews passed with no Critical or Important findings.
- C-3 final code-quality hardening commit: `edb107f fix: harden preflight readiness gates`.
- C-4 post-approval real-run execution contract design spec exists: `docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md`.
- C-4 implementation plan exists: `docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`.
- C-4 Task 1 complete and reviewed: `e195bd9 feat: guard post approval real runs`.
- C-4 Task 2 complete and reviewed: `d6804a8 feat: prepare first real run package`.
- C-4 Task 3 complete and reviewed: `fc34c6d fix: harden real run package creation`.
- C-4 Task 4 implementation complete with local deterministic verification: `1ce650e feat: add prepare real run cli`.
- C-4 documentation progress update complete: `f40966e docs: record real run package progress`.
- C-4 complete and reviewed. Final verification: `pytest -q` passed with 190 tests; `ruff check .` passed; combined final spec/code-quality review passed with no Critical or Important findings.
- C-5 real-run result handoff design spec exists: `docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md`.
- C-5 implementation plan exists: `docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`.
- C-5 real-run result handoff contract is complete and reviewed.
- C-5 final verification: `pytest -q` passed with 211 tests; `ruff check .` passed; combined final review gate passed with no Critical or Important findings.
- C-5.5 dual-agent result handoff simulation gate design spec exists: `docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`.
- C-5.5 implementation plan exists: `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`.
- C-5.5 simulation report exists: `docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`.
- C-5.5 dual-agent result handoff simulation gate passed.
- C-5.5 final verification: `pytest -q` passed with 211 tests; `ruff check .` passed; combined docs/spec review passed with no Critical or Important findings. The first combined review found report-evidence gaps; the re-review found those addressed and only Task 5 bookkeeping remained. The closeout commit addresses that bookkeeping.
- Spectre + OCEAN backend evidence is complete as of 2026-06-01. Both the transient/DC inverter smoke and the PSS/PAC/PNoise mixer probe show that Maestro point-level PSF and standalone Spectre replay PSF can be opened by batch OCEAN and produce matching scalar values for approved formulas.
- New evidence directories:
  - `docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/`
  - `docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/`
- C-6 Spectre + OCEAN real metric result contract design spec exists: `docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md`.
- C-6 implementation plan exists: `docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md`.
- C-6 is complete and reviewed. Final verification: `pytest -q` passed with 282 tests; `ruff check src tests tools` passed; `git diff --check` passed. Final combined review gate approved with no Critical, Important, or Minor findings.
- C-7 Spectre + OCEAN execution adapter design spec exists: `docs/superpowers/specs/2026-06-02-spectre-ocean-execution-adapter-design.md`.
- C-7 implementation plan exists: `docs/superpowers/plans/2026-06-02-spectre-ocean-execution-adapter.md`.
- C-7 is complete and reviewed. Current C-7 artifacts include `src/hermes_workflow/execution_adapters/spectre_ocean.py`, `tests/test_spectre_ocean_adapter.py`, and `tools/run_spectre_ocean_adapter.py`.
- C-7 policy is locked: the adapter is an execution-side tool boundary, not a Hermes validator; tests use fake runners only; Python does not parse PSF or rewrite OCEAN formulas; supervisor agent must still run `check-real-run` and `check-metric-results`.
- C-7 final verification: `python3 -m pytest tests/test_spectre_ocean_adapter.py -q` passed with 55 tests; `python3 -m pytest -q` passed with 337 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output. Final re-review approved with no findings.
- C-8 real result ledger/state update design spec exists: `docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`.
- C-8 implementation plan exists: `docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`.
- C-8 is complete and reviewed. Implemented schema/report extension, fail-closed record preconditions, successful real result ledger/state/best writes, duplicate protection, ledger-derived best-candidate repair, maximize objective normalization, and `hermes-workflow record-real-result` CLI.
- C-8 policy is locked: record only checked `check-real-run` + `check-metric-results` outputs; do not run real tools, call the C-7 adapter, parse PSF, rewrite formulas, generate next candidates, or add failure-penalty rows.
- C-8 final verification after review fixes: `python3 -m pytest -q` passed with 362 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output. Final re-review approved after ledger-derived best-candidate docs cleanup.
- C-9 next real-run package contract design spec exists: `docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`.
- C-9 implementation plan exists: `docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`.
- C-9 is complete and reviewed. It adds `prepare_next_real_run()` and `hermes-workflow prepare-next-real-run`, selecting the next unique candidate from the deterministic initialization sequence after C-8 has recorded checked real results. C-9 remains contract-only and does not run real tools, call C-7, write ledger/state, parse PSF, or rewrite formulas. Final review found and fixed a symlinked real-run directory issue; explicit run-id writes, default next-run scanning, and prepared-candidate scanning now fail closed on symlinked `real_###` directories.
- C-9 final verification: `python3 -m pytest -q` passed with 380 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` produced no output.
- C-10 real-run failure/retry policy contract design spec exists: `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md` (`68c404a docs: design real run failure retry policy`).
- C-10 implementation plan exists: `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md` (`13d39e9 docs: plan real run failure retry policy`).
- C-10 Task 1 recovery report schemas are complete and reviewed: `104ef26 feat: add real run recovery report schema`.
- C-10 Task 2 recovery assessment classifier is complete and reviewed: `a9dc13a feat: classify real run recovery state`.
- C-10 Task 3 recovery decisions and retry package writer is complete and reviewed: `c76f152 feat: prepare real run retry packages`.
- C-10 Task 3 final verification: recovery tests passed with 36 tests; focused compatibility suite passed with 151 tests; focused ruff and `git diff --check` passed; spec and code-quality reviews passed with no remaining Critical or Important findings.
- C-10 Task 4 C-9 unresolved real-run guard is complete and reviewed: `e6d19a5 feat: block next runs on unresolved real runs`. It blocks `prepare-next-real-run` while pending, failed, partial, metric-failed, retry-prepared, stopped, contract-invalid, or recordable real-run packages are unresolved. It allows already-recorded and resolved-abandoned packages to continue. It also keeps retry-prepared source runs blocking only until the retry run is recorded or resolved abandoned.
- C-10 Task 4 final verification: focused next-run/recovery/record tests passed with 83 tests; full `python3 -m pytest -q` passed with 424 tests; `python3 -m ruff check src tests tools` passed; `git diff --check` passed. Spec review passed after fixing retry resolution deadlocks; code-quality review passed after eliminating hidden checker report writes from the guard path.
- Route consistency audit after C-10 Task 4 found no technical-route drift. The C-10 design spec and implementation plan are aligned with Task 4: C-9 cannot advance past unresolved real runs, failed evidence remains preserved, C-10 remains contract-only, and C-10 still does not write optimizer ledger/state or call real tools.
- Workspace-level agent constraints are recorded in `AGENTS.md`. Future agents must read it before continuing; it locks the role model, formula safety policy, per-task stop-and-report cadence, and coding guidelines.
- C-10 Task 5 CLI Integration is complete and reviewed: `7994d83 feat: add real run recovery cli`. It adds `assess-real-run-recovery`, `prepare-real-run-retry`, and `resolve-real-run-failure` CLI commands, with report/issue output and no traceback on expected contract failures. A code-quality finding about stale recovery report output was fixed by printing report details only when the current command updates the recovery report.
- C-10 Task 6 docs/progress/final verification is complete and reviewed. Final verification passed with 434 tests, ruff clean, and `git diff --check` clean.
- C-10 final review fixes: unsafe declared result artifacts now classify as `tool_result_partial` with retry/stop actions; symlinked `recovery_decision.json` files are rejected in assessment read paths and write-path preflights.
- C-10 real-run failure/retry policy contract is complete and reviewed.
- C-11 local smoke design spec exists: `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`.
- C-11 local smoke implementation plan exists: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`.
- Plan C process hardening lightweight cadence guard is complete; verified-only. It adds `docs/CURRENT_TASK_STATE.json`, `tools/check_development_cadence.py`, and `docs/superpowers/specs/2026-06-03-process-hardening-lightweight-cadence-design.md`.
- Current scope: Plan C C-11 Task 2 library happy-path smoke
- Current status: C-11 Task 2 library happy-path smoke complete and reviewed
- Current next action: wait for user confirmation before C-11 Task 3 controlled failure/retry smoke.
- C-11 Task 1 checkpoint: complete and reviewed. Added the single helper seed-recording smoke and test-only real-run smoke helper module. Spec review and code-quality review approved with no Critical, Important, or Minor findings.
- C-11 Task 1 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only; drift is none.
- C-11 Task 2 checkpoint: implementation complete and verified-only. Added only `test_c11_library_happy_path_records_next_real_run` to `tests/test_local_real_run_smoke.py`; it seeds `real_001`, prepares `real_002`, writes fake C-7-style result/metric manifests, checks and records the run, and asserts ledger/state/best/report outputs plus no unresolved real runs.
- C-11 Task 2 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only; drift is none. Task 3 retry flow, Task 4 CLI smoke, final gate work, real tools, subprocess-backed C-7 adapter, network, PSF parsing, and formula rewriting were not added.
- C-11 Task 2 review evidence: spec-compliance review approved by Socrates (`019e8caf-9520-75e3-9cf4-e9d913d872d0`); code-quality review approved by Dirac (`019e8cb1-9279-7273-a76e-7e760fed813e`). Both reviews reported no Critical, Important, or Minor findings.
- Keep C-11 local/fake controlled first; do not jump straight to real Virtuoso/Spectre/OCEAN/agent integration.
- Real `input.scs` examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` are local-only references and must not be committed.

## Files Already Read

- `ic-auto-opt-workflow/PROJECT_STRUCTURE.md`
- `ic-auto-opt-workflow/docs/HANDOFF_TO_LINUX_CODEX.md`
- `virtuoso-bridge-lite/README.md`
- `virtuoso-bridge-lite/AGENTS.md`
- `virtuoso-bridge-lite/skills/virtuoso/SKILL.md`
- `virtuoso-bridge-lite/skills/spectre/SKILL.md`
- `virtuoso-bridge-lite/skills/optimizer/SKILL.md`
- `virtuoso-bridge-lite/examples/01_virtuoso/maestro/08_set_simulator_mode.py`
- `virtuoso-bridge-lite/examples/02_spectre/*`
- `virtuoso-bridge-lite/examples/01_virtuoso/maestro/*`

## Active Plan Files

- Current focused plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md`
- Earlier broad plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Active Plan C follow-up plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-05-30-netlist-template-contract.md`
- Active Plan C spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-05-30-netlist-template-contract-design.md`
- Active C-2 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-05-30-dry-run-candidate-renderer-design.md`
- Active C-2 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-05-30-dry-run-candidate-renderer.md`
- Active C-3 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-05-30-execution-package-preflight-readiness-design.md`
- Active C-3 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-05-30-execution-package-preflight-readiness.md`
- Active C-4 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-05-31-post-approval-real-run-contract-design.md`
- Active C-4 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-01-post-approval-real-run-contract.md`
- Active C-5 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-01-real-run-result-handoff-contract-design.md`
- Active C-5 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-01-real-run-result-handoff-contract.md`
- Active C-5.5 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`
- Active C-5.5 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`
- Active C-5.5 simulation report: `ic-auto-opt-workflow/docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md`
- Active C-6 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-01-spectre-ocean-real-metric-result-contract-design.md`
- Active C-6 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-02-spectre-ocean-real-metric-result-contract.md`
- Active C-8 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-02-real-result-ledger-state-update-design.md`
- Active C-8 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-02-real-result-ledger-state-update.md`
- Active C-9 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-02-next-real-run-package-contract-design.md`
- Active C-9 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-02-next-real-run-package-contract.md`
- Active C-10 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- Active C-10 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`
- Active C-11 design spec: `ic-auto-opt-workflow/docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`
- Active C-11 implementation plan: `ic-auto-opt-workflow/docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`

Plan A, Plan B, Plan C C-1, Plan C C-2, Plan C C-3, Plan C C-4, Plan C C-5, and Plan C C-5.5 are complete. C-5.5 passed the dual-agent simulation gate. C-6, C-7, C-8, C-9, and C-10 are complete and reviewed.

## Confirmed Plan A Scope

Plan A name: Hermes File Contract MVP.

Plan A consumes already-generated structured YAML files:

```text
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
```

Plan A does not implement:

- `USER_TASK.md` Markdown parser
- natural-language-to-YAML extraction
- Claude CLI / `Claude-cli-skill` invocation
- real Virtuoso execution
- real Spectre execution
- TuRBO loop implementation
- `render_netlist.py`, `dry_run.py`, `run_candidate.py`, or `optimization_loop.py` logic
- final optimization report generation

Those belong to later plans.

## Backend Decision

Continue the first MVP with the confirmed standalone Spectre + batch OCEAN backend:

```text
Maestro export input.scs
-> template approved variables
-> run standalone Spectre
-> open generated PSF with batch OCEAN
-> evaluate exact approved OCEAN/Calculator formulas
-> record scalar metric values and provenance
-> optimizer loop
```

Do not pivot the first MVP to a Maestro-managed simulation loop yet.

Important nuance:

- Formula choice is authoritative contract input. If the approved formula uses `vh`, evaluate `vh`; if it uses `drplPacVolGnExpDen`, evaluate `drplPacVolGnExpDen`. Do not rewrite formulas across dialects.
- Agent/tool formula discovery from Maestro/ADE outputs is allowed only to draft or audit `metrics.yaml`; discovered formulas require user/project approval before execution.
- Python must not parse PSF waveforms or reimplement Calculator/OCEAN formulas. Python only invokes OCEAN and records OCEAN-produced scalar/text outputs.
- C-6 adds explicit executable OCEAN formula contracts to `metrics.yaml` with provenance, analysis/result selection, scalarization expectations, and failure behavior.

## Confirmed YAML Contracts

### `project_config.yaml`

Purpose: project identity, single-corner Maestro testbench locator, netlist path contract, and safety policy.

Confirmed:

- First version supports one corner only.
- Multi-corner is deferred.
- Netlist paths are generated by Hermes/template, not normally user-selected.
- Netlist paths must be project-relative, must not contain `..`, and must stay under `netlists/exported/` and `netlists/templates/`.

Shape:

```yaml
schema_version: "1.0"

project:
  name: bridge_test_inv
  description: "Optimize inverter sizing from an existing Maestro testbench"
  backend: maestro_exported_spectre_deck

testbench:
  virtuoso_library: Virtuoso_Bridge_test
  cell: bridge_test_inv
  design_view: schematic
  maestro_view: maestro
  test_name: tran_dc_test
  corner: Nominal

netlist:
  source: existing_maestro_setup
  export_method: maeCreateNetlistForCorner
  exported_input_scs: netlists/exported/input.scs
  template_scs: netlists/templates/template.scs

safety:
  immutable_after_package: true
  require_hermes_approval_before_real_run: true
  allow_maestro_setup_modification: false
  allow_only_variable_templating: true
```

### `variables.yaml`

Purpose: whitelist exact variables Claude may template and define the quantized search space.

Confirmed:

- First version supports only `integer` and `continuous_step`.
- Do not require `description`, `device`, or separate `unit`.
- Users/upstream Hermes provide complete values with units where needed, such as `"0.3 um"`.
- Variable names must be unique and match `[A-Za-z_][A-Za-z0-9_]*`.
- `continuous_step` lower, upper, and step must use compatible unit suffixes.

Shape:

```yaml
schema_version: "1.0"

variables:
  - name: FN
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WN
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"

  - name: FP
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WP
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"
```

### `metrics.yaml`

Purpose: define metrics, hard constraints, and scalar objective in one file.

Confirmed:

- `metrics`, `constraints`, and `objective` live together.
- Constraint ops: `lt`, `le`, `gt`, `ge`; no `eq`.
- Objective directions: `minimize`, `maximize`.
- `maximize` can later be converted to minimization by negating the scalar objective.
- In Plan A, `maestro_formula` was traceability/reference only.
- In C-6, the metrics contract should add or clarify executable OCEAN formula fields. The formula text remains exact and user/project-approved; agent-discovered formulas are drafts until approved.
- `required_signals` is explicit and non-empty.
- Plan A validates references and objective expression symbols only.

Shape:

```yaml
schema_version: "1.0"

metrics:
  - name: rise
    unit: ps
    maestro_formula: "riseTime(VT('/VOUT') 0 nil 1.2 nil 10 90 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: fall
    unit: ps
    maestro_formula: "fallTime(VT('/VOUT') 0 nil 1.2 nil 90 10 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: DC
    unit: u
    maestro_formula: "average(abs(IT('/VDD')))"
    required_signals:
      - VDD

constraints:
  - metric: rise
    op: lt
    value: "80 ps"

  - metric: fall
    op: lt
    value: "80 ps"

  - metric: DC
    op: lt
    value: "400 u"

objective:
  direction: minimize
  expression: "(rise + fall) * DC"
```

### `spectre.yaml`

Purpose: standalone Spectre execution policy for exported deck.

Confirmed:

- First version supports only Spectre X presets: `cx`, `ax`, `mx`, `lx`, `vx`.
- Do not expose plain Spectre, APS, Spectre FX, or ADE-style Spectre/APS accuracy settings in first version.
- Existing `virtuoso-bridge-lite` maps `spectre_mode_args("ax")` to `+preset=ax +mt`.
- `+mt` enables Spectre multithreading per simulation task. Thread count is not exposed in first version and is left to Spectre/environment/host policy.
- Historical Plan A fixtures used `output_format: psfascii` for the earlier parser-oriented route.
- C-6 must update or extend this for the confirmed Spectre + OCEAN backend with an OCEAN-readable PSF format; current toolchain evidence used `psfxl`.
- `timeout_s` is required from user/upstream config and has no hidden default.
- `parallel_jobs` is candidate-level concurrency and server resource limit.

Shape:

```yaml
schema_version: "1.0"

spectre:
  engine: spectre_x
  preset: ax
  output_format: psfxl
  parallel_jobs: 10
  timeout_s: 3600
  require_license_check: true
  keep_failed_runs: true
  keep_successful_runs: true
```

### `optimizer.yaml`

Purpose: candidate search strategy, total candidate budget, batch size, reproducibility, and failure penalty.

Confirmed:

- First version supports `algorithm: turbo` and `algorithm: random`.
- `random` is allowed for debug/fallback.
- `initialization` controls first candidate generation before model-based search has data.
- Supported initialization: `sobol`, `latin_hypercube`, `random`.
- `max_evaluations` is total candidate simulations, not optimizer rounds.
- One evaluation equals one candidate parameter set, one Spectre run, and one ledger row.
- `batch_size` is candidates per optimizer batch.
- `max_batches = ceil(max_evaluations / batch_size)` is derived and must not be stored.
- Hard rule: `optimizer.batch_size <= spectre.parallel_jobs`.
- `random_seed` is required.
- `failure_penalty` must be positive finite.
- `deduplicate_candidates` must be true in MVP.
- If `algorithm` is `turbo`, `max_evaluations >= 2 * number_of_variables`.

Shape:

```yaml
schema_version: "1.0"

optimizer:
  algorithm: turbo
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  random_seed: 20260528
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

## Next Step

Plan A, Plan B, Plan C C-1, Plan C C-2, Plan C C-3, Plan C C-4, Plan C C-5, and Plan C C-5.5 are complete as of 2026-06-01. C-6, C-7, C-8, and C-9 are complete and reviewed as of 2026-06-02. C-10 real-run failure/retry policy contract is complete and reviewed as of 2026-06-03.

Current next step: wait for user confirmation before C-11 Task 3 controlled failure/retry smoke. Current state is `Plan C C-11 Task 2 library happy-path smoke`, reviewed. Before continuing, read `docs/CURRENT_TASK_STATE.json` and run `python3 tools/check_development_cadence.py`. C-11 must stay local/fake controlled: C-9 -> fake C-7-style returned artifacts -> C-5/C-6 checks -> C-8 with one controlled C-10 failure/retry case. Do not run real Virtuoso/Spectre/OCEAN/SSH/agent/bridge in C-11. Do not redo Plan A Tasks 1-9 or completed Plan B/C modules unless new review feedback appears.

Read the handoff files first:

```text
ic-auto-opt-workflow/AGENTS.md
ic-auto-opt-workflow/docs/OPENCODE_HANDOFF_2026-05-29.md
ic-auto-opt-workflow/docs/EXECUTION_PROGRESS_2026-05-29.md
ic-auto-opt-workflow/docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md
```

## Resume Prompt

Use this prompt after compact:

```text
请继续 IC auto optimization workflow。先阅读：
1. ic-auto-opt-workflow/AGENTS.md
2. ic-auto-opt-workflow/docs/CURRENT_TASK_STATE.json
3. ic-auto-opt-workflow/docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md
4. ic-auto-opt-workflow/docs/EXECUTION_PROGRESS_2026-05-29.md
5. ic-auto-opt-workflow/docs/COMPACT_RESUME_CHECKPOINT.md
6. ic-auto-opt-workflow/docs/superpowers/specs/2026-06-03-process-hardening-lightweight-cadence-design.md
7. 如需背景，再读 ic-auto-opt-workflow/docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md

当前 repo 是 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow，branch 是 plan-a-hermes-file-contract-mvp。当前活动节点是 Plan C C-11 Task 2 library happy-path smoke，状态为 reviewed；下一步请等待用户确认后进入 C-11 Task 3 controlled failure/retry smoke。运行或更新任务前先执行 python3 tools/check_development_cadence.py。不要运行真实 Virtuoso/Spectre/OCEAN/SSH/agent/bridge，不要调用 C-7 subprocess adapter，不要解析 PSF，不要重写 Calculator/OCEAN 公式。真实 input.scs 示例在 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example 下，仅供本地参考，请勿将其提交到仓库。
```
