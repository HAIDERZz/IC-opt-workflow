# IC Auto Optimization Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the upper Hermes workflow layer for Maestro-exported Spectre deck optimization while treating `virtuoso-bridge-lite` as the lower tool/skill dependency.

**Architecture:** The supervisor agent owns planning, user-facing decisions, formula approval, and workflow progression. Hermes workflow tooling owns deterministic file contracts, schema validation, preflight, execution package creation, approval files, report/state inspection, and final reporting. Deterministic preflight includes safe netlist preparation and dry-run candidate rendering because those steps are contract checks that must be reproducible and reviewable before any real simulator action. The execution agent owns tool-side actions: Maestro deck export through `virtuoso-bridge-lite`, post-approval standalone Spectre execution, batch OCEAN metric extraction from PSF results, and optimizer execution through approved adapter boundaries. The workflow is file-contract driven and never depends on chat history.

**Tech Stack:** Python 3.11+, `pydantic>=2`, `PyYAML`, `typer`, `pytest`, `ruff`, local dependency on sibling `../virtuoso-bridge-lite`, Cadence/Virtuoso/Spectre/OCEAN only behind explicit dry-run and approval gates.

---

## Source Context Read

- `ic-auto-opt-workflow/AGENTS.md`
- `ic-auto-opt-workflow/PROJECT_STRUCTURE.md`
- `ic-auto-opt-workflow/docs/HANDOFF_TO_LINUX_CODEX.md`
- `virtuoso-bridge-lite/README.md`
- `virtuoso-bridge-lite/AGENTS.md`
- `virtuoso-bridge-lite/skills/virtuoso/SKILL.md`
- `virtuoso-bridge-lite/skills/spectre/SKILL.md`
- `virtuoso-bridge-lite/skills/optimizer/SKILL.md`

## Current Implementation Node

As of 2026-06-07, Plan A, Plan B, and Plan C through C-64 are complete, with
post-C-49 real Mixer OpenBox/Spectre/OCEAN evidence through 200 cumulative
NF=12dB evaluations and C-50 real multi-testbench evidence through 100
three-testbench evaluations. Post-C50/C-54 reporting now re-scores existing
results under the configured FoM, plots bottleneck/weighted normalized-margin
tradeoffs, writes a supervisor-facing optimizer decision report, and records a
supervisor acceptance decision for the selected best observed point, then
writes a user-facing final optimization summary. C-54 adds the production
quickstart and `check-project-ready` readiness command. The workflow is now
usable as a first production landing MVP; the next active scope should be driven
by the next real user project or continuation need rather than broad framework
work.

C-55 records the production landing acceptance note at
`docs/PRODUCTION_LANDING_ACCEPTANCE_2026-06-07.md`. The real Mixer
multi-testbench project passed `check-project-ready` with
`readiness=ready_for_closeout_review` and final summary acceptance of
`real_093`. The accepted boundary is first production trial readiness, not a
claim of global optimizer completeness.

C-56 hardens the production handoff after the full user -> supervisor agent ->
execution agent -> real optimizer simulation. It fixes `decide-optimizer-run`
so a non-feasible configured-objective best point cannot become the primary
recommended run when feasible candidates exist. The simulation project
`/tmp/ic_auto_opt_agent_e2e_g2qieZ/Mixer_opt_muti_tb_full` now recommends
feasible `real_066` instead of constraint-failed `real_057` without rerunning
Spectre/OCEAN. The production manuals now require package/preflight/approval
before execution, avoid hardcoded Spectre-version wording, and document
low-frequency execution-agent status polling. A design-only future route for
`hermes-workflow optimize PROJECT_DIR --real` is recorded in
`docs/superpowers/specs/2026-06-07-one-command-optimizer-flow-design.md`.

C-57 implements that one-command route as
`hermes-workflow optimize PROJECT_DIR --real`. The command wraps the proven
production sequence from requirement intake through package/preflight/approval,
approved OpenBox real execution, optimizer acceptance/completion/finalization,
visualization, and decision reporting. It writes
`reports/optimizer_flow_run_report.json` and stops before final user
acceptance. `--dry-orchestration` verifies the offline gates through
`package-optimizer-task` and stops before real Spectre/OCEAN/OpenBox execution.

C-58 productizes the route as `ic-opt PROJECT_DIR --real` from the repository
product `.venv`. `requirements-product.txt` installs this repo, the local
OpenBox checkout, and visualization dependencies into one product environment;
user optimization projects remain data/artifact directories and must not create
their own Python virtualenvs. A dry orchestration passed from `ic-opt`, and an
unsandboxed real Mixer multi-testbench run at
`/tmp/ic_auto_opt_c58_real_unsandboxed_rj40MJ/Mixer_opt_muti_tb` completed 100
OpenBox/Spectre/OCEAN evaluations with `19 feasible`, `65 constraint_failed`,
and `16 metric_check_failed`, generated OpenBox advanced visualization, and
recommended feasible `real_066`. A sandboxed real attempt failed with Spectre
pipe/socket errors, so real Cadence/Spectre/OCEAN acceptance must be run
unsandboxed.

C-59 removes the remaining repeated Cadence environment flag from the product
entrypoint without changing the lower-level audited command. The Cadence setup
path remains user supplied once through explicit `--cadence-cshrc`,
`PROJECT_DIR/cadence_env.csh`, `IC_OPT_CADENCE_CSHRC`, or
`~/.ic-opt/cadence_env.csh`; then the product route is
`ic-opt PROJECT_DIR --real`. `hermes-workflow optimize` remains explicit.

C-60 validates that product route with a fresh real Mixer multi-testbench
workspace at `/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb`.
The workspace copied only `opt_requirement.md` and project-local
`cadence_env.csh`, then ran `ic-opt PROJECT --real --max-evals 100
--batch-size 10 --parallel-jobs 10` without `--cadence-cshrc`. The flow passed
100 real OpenBox/Spectre/OCEAN evaluations, recommended feasible `real_051`,
generated OpenBox advanced visualization, and kept
`global_optimum_claim=false`.

C-61 polishes the release-facing entrypoints. The root README now documents the
current product install and `ic-opt PROJECT --real` path rather than the early
contract-only MVP. `docs/PRODUCT_RELEASE_CHECKLIST.md` records release
readiness gates, and `requirements-product.txt` pins the product visualization
dependencies validated by C-60.

C-62 corrects the agent-integration boundary. The implemented shell product
route is `ic-opt PROJECT_DIR --real`, backed by `hermes-workflow optimize` and
Hermes file/task-package contracts. The canonical boundary note is
`docs/AGENT_INTEGRATION_STATUS.md`, and the detailed Chinese project status
explanation is `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

C-63 implements and validates the first real Claude CLI slash-skill entrypoint:
`/ic-opt PROJECT_DIR --real` after installing `claude_skills/ic-opt`. The fresh
project `/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb` started
with only `opt_requirement.md` and `cadence_env.csh`; Claude CLI then completed
100 real OpenBox/Spectre/OCEAN evaluations and recommended feasible `real_051`
with `global_optimum_claim=false`. This proves a short Claude agent-facing
entrypoint to the automation core.

C-64 implements and validates observable Claude supervisor-agent to independent
Claude CLI execution-agent handoff. The Claude `/ic-opt` skill appends
`--execution-agent claude` by default; `optimizer_flow` dispatches an
independent Claude CLI execution-agent process after `package-optimizer-task`,
captures `reports/execution_agent_handoff_report.json` and transcript, then
resumes supervisor-side closeout. The fresh project
`/tmp/ic_auto_opt_c64_handoff_zX9JrO/Mixer_opt_muti_tb` started with only
`opt_requirement.md` and `cadence_env.csh`; `claude -p
--dangerously-skip-permissions "/ic-opt PROJECT --real"` completed the handoff,
100 real OpenBox/Spectre/OCEAN evaluations, and recommended feasible
`real_051` with `global_optimum_claim=false`. This proves the Claude runtime
two-agent handoff route; Codex/non-Claude runtime adapters and clean-machine
skill installer remain future work.

The accepted route is no longer an abstract contract-only optimizer plan; it is
a practice-first production handoff flow that has been exercised with real
OpenBox, Spectre, and OCEAN runs. C-50 has addressed the real Mixer landing
gap where one optimizer candidate needs metrics from multiple Maestro/ADE
testbenches such as CG/NF/BW, IIP3, and P1dB.

Current production route:

```text
user supplies a Cadence env anchor once
-> shell/operator runs ic-opt PROJECT_DIR --real
-> Claude CLI can run /ic-opt PROJECT_DIR --real after installing claude_skills/ic-opt
-> supervisor agent must use the short command and project files, not a long prompt
-> Hermes workflow tooling validates/package contracts
-> Hermes writes optimizer execution task packet
-> Claude /ic-opt dispatches an independent Claude CLI execution-agent process
-> execution agent follows the generated optimizer task package command exactly
-> OpenBox/native TuRBO generates candidates, not hand-picked points
-> Spectre runs with approved precision/thread settings
-> OCEAN computes approved metrics
-> Hermes audits manifests/reports
-> supervisor reads finalize + optimizer-status
```

Completed optimizer milestones since C-26:

- C-27 through C-29 introduced and productized the OpenBox backend while
  preserving native TuRBO and the existing Spectre/OCEAN adapter boundary.
- C-30 through C-34 created and validated production optimizer task packet
  handoff for OpenBox, including the known-good OpenBox/Hermes execution venv.
- C-35 and C-36 locked the real-tool execution reference and added
  `check-toolchain-env` so future runs do not repeat venv/Cadence setup errors.
- C-38 through C-42 added OpenBox continuation, proved real continuation from
  100 to 120 and then 120 to 130 cumulative evaluations, and validated the
  generated continuation packet path.
- C-43 added `hermes-workflow optimizer-status PROJECT_DIR`, a concise
  supervisor-facing closeout summary.
- C-44 integrated `optimizer-status` into generated optimizer task packet audit
  commands and the production handoff guide.
- C-45 validated a fresh production-style OpenBox handoff from a clean
  workspace for 10 real evaluations using the updated packet. The run closed out
  through `check-optimizer-run`, `summarize-optimizer-run`,
  `finalize-optimizer-run`, and `optimizer-status`. The 10-eval smoke produced
  `9 constraint_failed` and `1 metric_check_failed`, no feasible point, and the
  correct supervisor decision `stop_for_user_review` with confidence `low`.
- C-46 validated the same current packet/status route at 100 real
  evaluations from a fresh workspace. The run produced `43 feasible`,
  `51 constraint_failed`, and `6 metric_check_failed`; closeout accepted best
  observed `real_071` with confidence `medium` and `global_optimum_claim=false`.
- C-47 added OpenBox official post-run advanced visualization artifacts and
  proved the feature in a full real 100-evaluation OpenBox/Spectre/OCEAN flow.
  The generated manifest status was `generated`, including
  objective/constraint history, surrogate verification, and parameter
  importance.
- C-48 improved the offline supervisor-facing optimizer insight report using
  existing evaluated samples. The report now includes IC-native top feasible
  candidates, constraint margins, feasible-only convergence, and OpenBox SHAP
  importance summaries with metric labels.
- C-49 implemented the file-based user intake route: strict `opt_requirement.md`
  plus optional `constraints.md`, safe import of full Maestro point-root netlist
  bundles, duplicate-YAML-key rejection, and real Mixer single-point plus
  OpenBox optimizer practice evidence.
- Post-C-49 Mixer NF=12dB continuation completed 200 cumulative real
  evaluations in `/home/zzchen/spectre_opt_prj/Mixer_opt_openbox_nf12_001` with
  `48 feasible`, `134 constraint_failed`, `18 metric_check_failed`, and
  `0 real_check_failed`; best observed remains `real_100`.
- A narrow resource-control fix added `optimizer_cpu_threads` for Python-side
  optimizer math/threadpool work only. It remains separate from
  `spectre.parallel_jobs` and `spectre.threads_per_run`.
- C-50 completed the multi-testbench route. Task 1 added the contract/intake
  shape for named testbenches and metric routing while preserving the existing
  single-testbench path. Task 2 added namespaced multi-testbench netlist
  import/template/render while preserving the primary legacy single-testbench
  path. Task 3 added child manifest aggregation into the existing
  candidate-level `result_manifest.json` and
  `metrics/metric_result_manifest.json` paths. Task 4/5 completed real
  evidence in `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb`: 100
  three-testbench OpenBox/Spectre/OCEAN evaluations with `19 feasible`,
  `65 constraint_failed`, `16 metric_check_failed`, best observed `real_068`,
  and final decision `accept_best_observed`, `global_optimum_claim=false`.
  C-50 did not merge testbenches into a synthetic deck, parse PSF, rewrite
  formulas, change approved formulas, or multiply `parallel_jobs` per
  testbench.
- Post-C50/C-54 completed offline decision reporting from existing evaluated
  artifacts. `optimizer_insight_report` now provides configured-objective
  ranking and bottleneck/weighted score data, while
  `hermes-workflow decide-optimizer-run PROJECT_DIR` writes
  `optimizer_decision_report.{json,md}` and
  `hermes-workflow record-optimizer-decision PROJECT_DIR` writes
  `optimizer_supervisor_decision.{json,md}`.
  `hermes-workflow write-optimizer-final-summary PROJECT_DIR` writes
  `optimizer_final_summary.{json,md}`. The real Mixer multi-testbench project
  `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` accepted feasible `real_093`
  under the normalized FoM as the current best observed point, marks it as best
  observed rather than global optimum, identifies `BW` as the bottleneck, links
  the visualization/report artifacts, and does not rerun Spectre/OCEAN for
  reporting or recording.
- C-54 completed production landing polish. `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
  documents the supported user path from `opt_requirement.md` to final summary.
  `hermes-workflow check-project-ready PROJECT_DIR` writes
  `reports/project_readiness_report.json` and checks requirement/config/netlist
  readiness plus final summary availability without running real tools. The
  real Mixer multi-testbench project passed with
  `readiness=ready_for_closeout_review`.
- C-56 hardened agent handoff and decision safety. Production usage is now
  explicitly short-request/file-driven, package/preflight/approval is required
  before execution, real-tool environment setup comes from user/project config
  rather than hardcoded Spectre versions, execution-agent status checks should
  be low-frequency, and `decide-optimizer-run` must recommend a feasible point
  when feasible evidence exists.
- C-57 added the thin `hermes-workflow optimize PROJECT_DIR --real`
  orchestration command plus `reports/optimizer_flow_run_report.json`. The
  command reduces supervisor-agent prompt complexity while preserving the
  existing deterministic gates and stopping before user acceptance.

Current code-level entry points:

- `hermes-workflow optimize PROJECT_DIR --real --max-evals N --batch-size B --parallel-jobs P --cadence-cshrc CADENCE_CSHRC`
- `hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --max-evals N --cadence-cshrc CADENCE_CSHRC --parallel`
- `hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --continuation --additional-evals N --cadence-cshrc CADENCE_CSHRC --parallel`
- `hermes-workflow run-openbox-real PROJECT_DIR --max-evals N --batch-size B --parallel-jobs P --cadence-cshrc CADENCE_CSHRC`
- `hermes-workflow continue-openbox-real PROJECT_DIR --additional-evals N --batch-size B --parallel-jobs P --cadence-cshrc CADENCE_CSHRC`
- `hermes-workflow check-toolchain-env --openbox-venv /tmp/ic_auto_opt_openbox_spike/.venv --cadence-cshrc /home/zzchen/cadence_ic231_env.csh`
- `hermes-workflow check-optimizer-run PROJECT_DIR`
- `hermes-workflow summarize-optimizer-run PROJECT_DIR`
- `hermes-workflow finalize-optimizer-run PROJECT_DIR`
- `hermes-workflow optimizer-status PROJECT_DIR`
- `hermes-workflow decide-optimizer-run PROJECT_DIR`
- `hermes-workflow record-optimizer-decision PROJECT_DIR`
- `hermes-workflow write-optimizer-final-summary PROJECT_DIR`
- `hermes-workflow check-project-ready PROJECT_DIR`

The next work should stay narrow and practice-first. Do not start a broad
optimizer framework rewrite. The next production step should convert the proven
C-49/C-50 route into clearer user-facing operation: requirement template/README
tightening, multi-testbench guide, formula/variable/resource approval
checkpoint, and final optimizer closeout/status reporting polish. After C-57,
the preferred next step is to use `hermes-workflow optimize PROJECT_DIR --real`
on the next real project, or to run `--dry-orchestration` first on a prepared
project. New features should be added only when that real workflow exposes a
specific missing capability.

## Current Route Alignment

This broad plan was originally drafted with some preflight runner scripts living inside the generated execution package. The current accepted route, confirmed after focused Plan A and Plan C, supersedes that detail:

- The role model is locked in `docs/ROLE_MODEL_AND_TERMINOLOGY.md`:
  - `supervisor agent` is the planning and decision-making agent.
  - `Hermes workflow tooling` is the deterministic file-contract and validation layer.
  - `execution agent` is the tool-side agent that operates Virtuoso/Spectre/OCEAN through approved boundaries.
- Hermes workflow tooling owns deterministic preflight:
  - `hermes-workflow validate`
  - `hermes-workflow prepare-netlist`
  - planned `hermes-workflow dry-run`
  - `hermes-workflow package`
  - `hermes-workflow approve`
- The execution agent owns non-deterministic or tool-side operations:
  - inspect/export Maestro deck through `virtuoso-bridge-lite`
  - copy or place exported `input.scs`
  - run real Spectre only after `approve_first_real_run`
  - invoke batch OCEAN on generated PSF results to compute user-approved metric formulas
  - execute the real optimizer loop after result contracts pass
- Project-local runner scripts such as `render_netlist.py` and `dry_run.py` are no longer the preferred route for preflight. The corresponding behavior is implemented or planned as Hermes modules:
  - `src/hermes_workflow/netlists.py`
  - `src/hermes_workflow/dry_run.py`
- The project template keeps `src/.gitkeep` as a future extension area, not as the source of deterministic preflight behavior.
- The placeholder syntax is `{{VARIABLE_NAME}}`, not the early draft `@@NAME@@`.

## Latest Toolchain Evidence: Spectre + OCEAN Route

As of 2026-06-01, the standalone Spectre + batch OCEAN backend is the confirmed metric route for the next development scope.

Evidence:

- Transient/DC inverter path: Maestro-generated point-level PSF opened in batch OCEAN; standalone Spectre replay produced matching OCEAN scalar values for `rise`, `fall`, and `DC`.
- PSS/PAC/PNoise mixer path: Maestro-generated point-level PSF opened in batch OCEAN; standalone Spectre replay produced matching OCEAN scalar values for `BW` and `MAX_GAIN`.
- Evidence directories:
  - `docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/`
  - `docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/`

Confirmed backend contract:

```text
Maestro/ADE exports or provides input.scs
-> Hermes templates only approved top-level Spectre parameters
-> Hermes prepares approved real-run package
-> execution agent runs standalone Spectre
-> execution agent invokes batch OCEAN on the generated PSF
-> OCEAN evaluates exact user/project-approved formulas
-> Python records scalar outputs and provenance only
```

Metric formulas remain authoritative contract inputs. A tool may read formulas from Maestro outputs to draft a contract, but generated formulas require user/project approval before execution. Do not rewrite formulas across dialects such as `vh(...)` and `drplPacVolGnExpDen(...)`; if the approved formula uses `drpl`, evaluate `drpl`, and if it uses `vh`, evaluate `vh`.

## Hard Constraints

- Do not reimplement `virtuoso-bridge-lite` skills or duplicate bridge internals.
- Do not modify Maestro simulation setup: analyses, model includes, save/output settings, simulator options, and corners remain sourced from exported `input.scs`.
- Template only user-approved variables, using `{{VARIABLE_NAME}}` markers in `template.scs`.
- Do not build a generic Maestro calculator parser for MVP. Hermes stores exact user/project-approved formulas and required result expectations. Python may invoke OCEAN and parse already-produced scalar/text outputs, but must not parse PSF data directly or reimplement Calculator/OCEAN formulas.
- Do not let agents rewrite metric formulas across dialects. Formula discovery from Maestro/ADE is allowed only as a draft/audit source; the executable formula must be locked in the file contract before real execution.
- Do not run real Spectre or optimizer before Hermes deterministic preflight artifacts pass and Hermes writes approval.
- Persist all state in files: configs, execution manifest, reports, ledger, optimizer state, health, escalation, and final summary.
- Treat the `Claude-cli-skill` interface as an external adapter boundary. The first implementation verifies file contracts before wiring the real invocation path.

## File Structure To Create

```text
ic-auto-opt-workflow/
├── README.md
├── pyproject.toml
├── src/hermes_workflow/
│   ├── __init__.py
│   ├── cli.py
│   ├── schemas.py
│   ├── validate.py
│   ├── package.py
│   ├── reports.py
│   ├── approvals.py
│   ├── netlists.py
│   ├── dry_run.py
│   └── final_report.py
├── src/hermes_workflow/templates/spectre_maestro_project/
│   ├── TASK.md
│   ├── METRICS.md
│   ├── CIRCUIT_KNOWLEDGE.md
│   ├── FAILURE_PLAYBOOK.md
│   ├── config/
│   │   ├── project_config.yaml
│   │   ├── variables.yaml
│   │   ├── metrics.yaml
│   │   ├── spectre.yaml
│   │   └── optimizer.yaml
│   ├── netlists/exported/.gitkeep
│   ├── netlists/templates/.gitkeep
│   ├── src/.gitkeep
│   ├── execution_package/.gitkeep
│   ├── ledger/.gitkeep
│   ├── state/.gitkeep
│   └── reports/.gitkeep
├── examples/bridge_test_inv/
│   ├── USER_TASK.md
│   ├── expected_project_config.yaml
│   └── expected_metric_contract.yaml
└── tests/
    ├── fixtures/bridge_test_inv/
    │   ├── USER_TASK.md
    │   ├── project_config.yaml
    │   ├── variables.yaml
    │   ├── metrics.yaml
    │   ├── spectre.yaml
    │   ├── optimizer.yaml
    │   ├── reports/
    │   │   ├── netlist_preparation_report.pass.json
    │   │   ├── dry_run_report.pass.json
    │   │   └── review_report.pass.md
    │   └── state/
    │       ├── health_check.pass.json
    │       ├── best_candidate.pass.json
    │       └── optimizer_state.pass.json
    ├── test_schemas.py
    ├── test_validate_config.py
    ├── test_package_execution.py
    ├── test_report_contracts.py
    ├── test_approvals.py
    └── test_cli.py
```

## Contract Overview

### Project Config Files

`config/project_config.yaml` holds immutable project identity and testbench locator:

```yaml
project:
  name: bridge_test_inv
  created_by: hermes
  backend: maestro_exported_spectre_deck
testbench:
  virtuoso_library: Virtuoso_Bridge_test
  cell: bridge_test_inv
  design_view: schematic
  maestro_view: maestro
  test_name: tran_dc_test
  corner: Nominal
  netlist_source: existing_maestro_setup
  netlist_export_method: maeCreateNetlistForCorner
contracts:
  immutable_after_package: true
  require_hermes_approval_before_real_run: true
```

`config/variables.yaml` stores bounds and quantization:

```yaml
variables:
  - name: FN
    device: M1 NMOS
    kind: integer
    lower: 2
    upper: 12
    step: 1
    unit: count
  - name: WN
    device: M1 NMOS
    kind: continuous_step
    lower: 0.3u
    upper: 3u
    step: 0.2u
    unit: m
  - name: FP
    device: M0 PMOS
    kind: integer
    lower: 2
    upper: 12
    step: 1
    unit: count
  - name: WP
    device: M0 PMOS
    kind: continuous_step
    lower: 0.3u
    upper: 3u
    step: 0.2u
    unit: m
```

`config/metrics.yaml` stores formulas, required signals, constraints, and objective:

```yaml
metrics:
  - name: rise
    unit: ps
    maestro_formula: riseTime(VT("/VOUT") 0 nil 1.2 nil 10 90 nil "time")
    required_signals: [time, VOUT]
  - name: fall
    unit: ps
    maestro_formula: fallTime(VT("/VOUT") 0 nil 1.2 nil 90 10 nil "time")
    required_signals: [time, VOUT]
  - name: DC
    unit: u
    maestro_formula: average(abs(IT("/VDD")))
    required_signals: [VDD]
constraints:
  - metric: rise
    op: lt
    value: 80
    unit: ps
  - metric: fall
    op: lt
    value: 80
    unit: ps
  - metric: DC
    op: lt
    value: 400
    unit: u
objective:
  direction: minimize
  expression: "(rise + fall) * DC"
```

`config/spectre.yaml` and `config/optimizer.yaml` define execution policy:

```yaml
spectre:
  mode: ax
  parallel_jobs: 10
  output_format: psfxl
  require_license_check: true
```

Note: `psfascii` was the original Plan A parser-era placeholder. The confirmed Spectre + OCEAN route should use an OCEAN-readable PSF format; current toolchain evidence used `psfxl`. C-6 must update or extend the schema and fixtures explicitly instead of relying on the old Plan A default.

```yaml
optimizer:
  algorithm: turbo
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  failure_penalty: 1000000.0
  min_initial_points_rule: "max(2 * n_variables, batch_size)"
```

### Preflight Report Contracts

`reports/netlist_preparation_report.json`:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "exported_input_scs": "netlists/exported/input.scs",
  "template_scs": "netlists/templates/template.scs",
  "approved_variables_template_status": {
    "FN": true,
    "WN": true,
    "FP": true,
    "WP": true
  },
  "analysis_statements": ["tran", "dc"],
  "forbidden_setup_changes_detected": false,
  "issues": []
}
```

`reports/dry_run_report.json`:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "rendered_candidate_scs": "runs/dry_run/input.scs",
  "placeholder_check": {
    "unresolved_placeholders": [],
    "unexpected_template_variables": []
  },
  "metrics_import_ok": true,
  "mock_metrics_ok": true,
  "objective_ok": true,
  "constraints_ok": true,
  "ledger_write_ok": true,
  "state_write_ok": true,
  "issues": []
}
```

`state/health_check.json`:

```json
{
  "schema_version": "1.0",
  "status": "healthy",
  "real_run_started": false,
  "current_evaluations": 0,
  "best_candidate_path": null,
  "last_batch_id": null,
  "issues": []
}
```

## Task 1: Python Package Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/hermes_workflow/__init__.py`
- Create: `src/hermes_workflow/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write CLI smoke test**

```python
from typer.testing import CliRunner

from hermes_workflow.cli import app


def test_cli_version_smoke():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "hermes-workflow" in result.output
```

- [ ] **Step 2: Run smoke test and confirm it fails before scaffold**

Run: `cd ic-auto-opt-workflow && pytest tests/test_cli.py -q`

Expected: FAIL with an import error for `hermes_workflow`.

- [ ] **Step 3: Create minimal package scaffold**

Create `pyproject.toml` with project metadata, dependencies, pytest path config, and `hermes-workflow` console script.

Create `src/hermes_workflow/__init__.py` with `__version__ = "0.1.0"`.

Create `src/hermes_workflow/cli.py` with a Typer app and `version` command.

- [ ] **Step 4: Verify smoke test passes**

Run: `cd ic-auto-opt-workflow && pytest tests/test_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add pyproject.toml README.md src/hermes_workflow/__init__.py src/hermes_workflow/cli.py tests/test_cli.py
git commit -m "chore: scaffold hermes workflow package"
```

## Task 2: Core Schema Models

**Files:**
- Create: `src/hermes_workflow/schemas.py`
- Test: `tests/test_schemas.py`
- Test fixtures: `tests/fixtures/bridge_test_inv/*.yaml`

- [ ] **Step 1: Write schema tests for valid bridge example**

Tests must load `project_config.yaml`, `variables.yaml`, `metrics.yaml`, `spectre.yaml`, and `optimizer.yaml` from `tests/fixtures/bridge_test_inv/`, then instantiate:

```python
ProjectConfig
VariablesConfig
MetricsConfig
SpectreConfig
OptimizerConfig
```

Assert the project name is `bridge_test_inv`, variables are `["FN", "WN", "FP", "WP"]`, and optimizer `max_evaluations` is `100`.

- [ ] **Step 2: Write schema tests for invalid bounds**

Create an in-memory variable with `lower: 12`, `upper: 2`, and assert validation raises a Pydantic error containing `lower must be less than upper`.

- [ ] **Step 3: Implement schema models**

Define strict Pydantic models for:

```python
ProjectIdentity
TestbenchSource
ProjectContracts
ProjectConfig
VariableSpec
VariablesConfig
MetricSpec
ConstraintSpec
ObjectiveSpec
MetricsConfig
SpectreConfig
OptimizerConfig
ExecutionManifest
SupervisorInstruction
NetlistPreparationReport
DryRunReport
HealthCheck
BestCandidate
OptimizerState
EscalationReport
```

Use enums for variable kind, constraint operator, spectre mode, optimizer algorithm, report status, and supervisor action.

- [ ] **Step 4: Verify schema tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_schemas.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/schemas.py tests/test_schemas.py tests/fixtures/bridge_test_inv
git commit -m "feat: define workflow file contract schemas"
```

## Task 3: Configuration Validation

**Files:**
- Create: `src/hermes_workflow/validate.py`
- Test: `tests/test_validate_config.py`

- [ ] **Step 1: Write validation tests**

Cover these cases:

```text
valid bridge_test_inv fixture returns no issues
constraint metric "delay" returns unknown metric issue
objective expression "rise + slew" returns unknown symbol issue
continuous_step variable with zero step returns invalid step issue
integer variable with fractional bound returns integer-bound issue
spectre parallel_jobs less than 1 returns invalid parallelism issue
optimizer max_evaluations less than min_initial_points returns insufficient budget issue
```

- [ ] **Step 2: Run validation tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_validate_config.py -q`

Expected: FAIL because `validate_project_contracts` is not defined.

- [ ] **Step 3: Implement validator**

`validate.py` must export these callables:

```text
load_yaml(path: Path) -> dict
load_project_bundle(project_dir: Path) -> ProjectBundle
validate_project_contracts(bundle: ProjectBundle) -> list[ValidationIssue]
assert_valid_project(bundle: ProjectBundle) -> None
```

`ValidationIssue` must include `severity`, `path`, `code`, and `message`.

Objective symbol extraction must parse Python expression syntax with `ast.parse` and accept only metric names and arithmetic operators.

- [ ] **Step 4: Verify validation tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_validate_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/validate.py tests/test_validate_config.py
git commit -m "feat: validate optimization project contracts"
```

## Task 4: Project Template Generation

**Files:**
- Create: `src/hermes_workflow/templates/spectre_maestro_project/**`
- Modify: `src/hermes_workflow/cli.py`
- Create: `src/hermes_workflow/package.py`
- Test: `tests/test_package_execution.py`

- [ ] **Step 1: Write template generation test**

Test command:

```bash
hermes-workflow init-project tests/tmp/bridge_test_inv --name bridge_test_inv
```

Expected created paths:

```text
TASK.md
METRICS.md
CIRCUIT_KNOWLEDGE.md
FAILURE_PLAYBOOK.md
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
netlists/exported/
netlists/templates/
src/
execution_package/
ledger/
state/
reports/
```

- [ ] **Step 2: Run test and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_init_project_creates_contract_tree -q`

Expected: FAIL because `init-project` does not exist.

- [ ] **Step 3: Implement template copier**

`package.py` must export:

```text
create_project_from_template(target_dir: Path, project_name: str, force: bool = False) -> Path
```

Rules:

```text
refuse to overwrite non-empty target without force
write project name into config/project_config.yaml
create empty ledger/state/report directories with .gitkeep
leave netlists/exported and netlists/templates empty
```

- [ ] **Step 4: Add CLI command**

Add `init-project TARGET --name NAME [--force]` to `cli.py`.

- [ ] **Step 5: Verify tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_init_project_creates_contract_tree -q`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add templates src/hermes_workflow/package.py src/hermes_workflow/cli.py tests/test_package_execution.py
git commit -m "feat: generate spectre maestro project template"
```

## Task 5: Execution Package Builder

**Files:**
- Modify: `src/hermes_workflow/package.py`
- Modify: `src/hermes_workflow/schemas.py`
- Test: `tests/test_package_execution.py`

- [ ] **Step 1: Write execution package tests**

Given a valid project directory, `build-execution-package` must create:

```text
execution_package/EXECUTION_TASK.md
execution_package/execution_manifest.json
execution_package/config/project_config.yaml
execution_package/config/variables.yaml
execution_package/config/metrics.yaml
execution_package/config/spectre.yaml
execution_package/config/optimizer.yaml
```

Assert manifest contains SHA-256 hashes for copied immutable contract files and declares the required preflight reports.

- [ ] **Step 2: Run package tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_build_execution_package_manifest -q`

Expected: FAIL because `build_execution_package` is not defined.

- [ ] **Step 3: Implement package builder**

`package.py` must export:

```text
sha256_file(path: Path) -> str
build_execution_package(project_dir: Path) -> ExecutionManifest
```

Manifest must include:

```json
{
  "schema_version": "1.0",
  "project_name": "bridge_test_inv",
  "created_by": "hermes_workflow",
  "required_skills": ["virtuoso", "spectre", "optimizer"],
  "required_first_action": "read_execution_task",
  "approval_required_before_real_run": true,
  "immutable_files": {
    "config/project_config.yaml": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "config/variables.yaml": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "config/metrics.yaml": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "config/spectre.yaml": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "config/optimizer.yaml": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  },
  "expected_outputs": [
    "reports/netlist_preparation_report.json",
    "reports/dry_run_report.json",
    "reports/review_report.md",
    "state/health_check.json"
  ]
}
```

- [ ] **Step 4: Add CLI command**

Add `build-execution-package PROJECT_DIR`.

- [ ] **Step 5: Verify tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py -q`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/package.py src/hermes_workflow/schemas.py src/hermes_workflow/cli.py tests/test_package_execution.py
git commit -m "feat: build claude execution package"
```

## Task 6: Claude Execution Task Document

**Files:**
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/execution_package/.gitkeep`
- Create through package builder: `execution_package/EXECUTION_TASK.md`
- Test: `tests/test_package_execution.py`

- [ ] **Step 1: Write content assertions**

Assert generated `EXECUTION_TASK.md` contains:

```text
Use the virtuoso skill to inspect/export Maestro setup.
Use maeCreateNetlistForCorner.
Do not modify analysis statements, model includes, simulatorOptions, saveOptions, corners, or output setup.
Template only variables listed in config/variables.yaml.
Write reports/netlist_preparation_report.json.
Run mandatory dry run without real Spectre.
Wait for supervisor_instruction.json before first real Spectre/optimizer run.
Use spectre skill only after approval.
Use optimizer skill only after approval.
```

- [ ] **Step 2: Run content assertions and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_execution_task_contains_safety_instructions -q`

Expected: FAIL until the renderer writes those clauses.

- [ ] **Step 3: Implement task document renderer**

`package.py` must export:

```text
render_execution_task(project_dir: Path, manifest: ExecutionManifest) -> str
```

The document must include exact local paths, required skill names, output contract list, approval gate behavior, and escalation behavior.

- [ ] **Step 4: Verify tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_execution_task_contains_safety_instructions -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/package.py tests/test_package_execution.py
git commit -m "feat: render claude execution task instructions"
```

## Task 7: Report And State Contract Readers

**Files:**
- Create: `src/hermes_workflow/reports.py`
- Modify: `src/hermes_workflow/schemas.py`
- Test: `tests/test_report_contracts.py`

- [ ] **Step 1: Write report reader tests**

Cover:

```text
valid netlist preparation pass report loads
missing templated variable fails
forbidden_setup_changes_detected true fails approval readiness
dry_run_report with unresolved placeholders fails approval readiness
health_check with real_run_started true fails first approval readiness
invalid JSON reports return structured issue instead of traceback
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_report_contracts.py -q`

Expected: FAIL because report readers are not defined.

- [ ] **Step 3: Implement report readers**

`reports.py` must export:

```text
load_preflight_reports(project_dir: Path) -> PreflightReports
```

Validation must aggregate readiness messages from `netlist_preparation_report.json`, `dry_run_report.json`, and `state/health_check.json`.

- [ ] **Step 4: Verify tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_report_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/reports.py src/hermes_workflow/schemas.py tests/test_report_contracts.py
git commit -m "feat: read and validate preflight reports"
```

## Task 8: Hermes Approval Gate

**Files:**
- Create: `src/hermes_workflow/approvals.py`
- Modify: `src/hermes_workflow/cli.py`
- Test: `tests/test_approvals.py`

- [ ] **Step 1: Write approval tests**

Cover:

```text
all pass reports produce supervisor_instruction.json with action approve_first_real_run
netlist preparation failure produces reject_first_real_run
dry_run failure produces reject_first_real_run
contract hash drift produces reject_first_real_run
escalation_report.json produces action respond_to_escalation
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_approvals.py -q`

Expected: FAIL because approval gate is not defined.

- [ ] **Step 3: Implement approval gate**

`approvals.py` must export:

```text
decide_first_run_approval(project_dir: Path) -> SupervisorInstruction
write_supervisor_instruction(project_dir: Path, instruction: SupervisorInstruction) -> Path
```

`SupervisorInstruction` actions:

```text
approve_first_real_run
reject_first_real_run
respond_to_escalation
continue_after_escalation
stop_project
```

- [ ] **Step 4: Add CLI commands**

Add:

```text
inspect-preflight PROJECT_DIR
approve-first-run PROJECT_DIR
reject-first-run PROJECT_DIR --reason TEXT
```

- [ ] **Step 5: Verify approval tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_approvals.py -q`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/approvals.py src/hermes_workflow/cli.py tests/test_approvals.py
git commit -m "feat: add hermes first-run approval gate"
```

## Task 9: Agent Verification Harnesses

**Files:**
- Create: `tests/test_agent_contracts.py`
- Create: `tests/fixtures/claude_stub_outputs/`
- Create: `tests/fixtures/hermes_stub_inputs/`
- Modify: `src/hermes_workflow/package.py`
- Modify: `src/hermes_workflow/reports.py`

- [ ] **Step 1: Write Hermes-stub test for preflight outputs**

The test builds an execution package, copies fixture preflight outputs into the project, and asserts Hermes accepts or rejects based only on files.

- [ ] **Step 2: Write Claude-stub test for Hermes instructions**

The test simulates:

```text
preflight files are present and passing
Hermes writes approve_first_real_run
execution state reports healthy batch state
Hermes reads best_candidate and health_check
Hermes can produce final_summary input for final report
```

- [ ] **Step 3: Implement harness helpers**

Create helper functions inside test files rather than production modules unless behavior is reused by CLI.

- [ ] **Step 4: Verify harness tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_agent_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add tests/test_agent_contracts.py tests/fixtures/claude_stub_outputs tests/fixtures/hermes_stub_inputs src/hermes_workflow
git commit -m "test: verify hermes claude file contracts"
```

## Task 10: Mock Optimization Loop Contract

**Files:**
- Create: `src/hermes_workflow/templates/spectre_maestro_project/src/mock_simulator.py`
- Create: `tests/test_mock_optimization_contract.py`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/src/optimization_loop.py`

- [ ] **Step 1: Write mock loop tests**

The generated project must run a mock loop without Cadence:

```bash
python src/optimization_loop.py --mock --max-evaluations 6
```

Expected files:

```text
ledger/experiment_ledger.jsonl
state/optimizer_state.json
state/best_candidate.json
state/health_check.json
```

Assert every ledger row contains:

```text
candidate_id
parameters
metrics
constraints_passed
objective
simulation_status
timestamp_utc
```

- [ ] **Step 2: Run mock test and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_mock_optimization_contract.py -q`

Expected: FAIL until template runner exists.

- [ ] **Step 3: Implement mock runner template**

The mock runner must:

```text
read config/*.yaml
generate deterministic candidates from variable bounds
apply integer and continuous_step quantization
compute mock metrics with deterministic formulas
apply constraints and objective expression
append JSONL ledger rows
update optimizer_state, best_candidate, and health_check
never import virtuoso_bridge
never run Spectre
```

- [ ] **Step 4: Verify mock loop tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_mock_optimization_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/templates/spectre_maestro_project/src tests/test_mock_optimization_contract.py
git commit -m "feat: validate optimization state contract with mock loop"
```

## Task 11: Exported `input.scs` Preparation Contract

**Current route:** completed as Plan C C-1 in Hermes, not as an execution-package render-netlist script.

**Files:**
- Create: `src/hermes_workflow/netlists.py`
- Create: `tests/test_netlists.py`
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write netlist templating tests**

Fixture `input.scs` must include:

```spectre
parameters FN=4 WN=1u FP=4 WP=1u
tran tran stop=1n
dcOp dc
simulatorOptions options reltol=1e-3
saveOptions options save=allpub
```

Tests assert:

```text
only FN/WN/FP/WP values are replaced with {{FN}}/{{WN}}/{{FP}}/{{WP}}
analysis statements remain byte-identical
include/model lines remain byte-identical
simulatorOptions remain byte-identical
saveOptions remain byte-identical
unapproved variable VDD is not templated
missing approved variable writes a fail netlist_preparation_report.json
```

- [ ] **Step 2: Run netlist tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_netlist_template_contract.py -q`

Expected: FAIL until templating helper exists.

- [ ] **Step 3: Implement Hermes netlist preparation**

`netlists.py` must expose:

```text
prepare_netlist(project_dir: Path) -> NetlistPreparationReport
```

Matching must target top-level Spectre `parameters` assignment RHS values and must not run a free-form global replace across the full file.

- [ ] **Step 4: Verify netlist tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_netlist_template_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/netlists.py src/hermes_workflow/cli.py tests/test_netlists.py tests/test_cli.py
git commit -m "feat: constrain exported spectre netlist templating"
```

## Task 12: Spectre + OCEAN Runner Contract After Approval

**Current route:** historical broad-plan placeholder, superseded by focused Plan C C-4/C-5/C-6 decomposition. C-4 now prepares a contract-only real-run package, C-5 validates the returned result handoff, and C-6 is the next scope for a real metric result contract centered on standalone Spectre plus batch OCEAN. Do not implement project-template `run_candidate.py`/`optimization_loop.py` as deterministic Hermes preflight.

**Files:**
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/src/run_candidate.py`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/src/optimization_loop.py`
- Test: `tests/test_spectre_runner_contract.py`

- [ ] **Step 1: Write approval enforcement tests**

Future tests should assert the execution-side contract, not a Hermes preflight runner:

```text
run_candidate refuses real mode when supervisor_instruction.json is missing
run_candidate refuses real mode when action is reject_first_real_run
run_candidate allows real mode only when action is approve_first_real_run
real mode runs standalone Spectre only from a C-4 prepared package
real mode invokes batch OCEAN on the produced PSF
real mode evaluates exact approved metric formulas without Python PSF parsing
real mode writes a C-5/C-6-compatible result manifest with metric provenance
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_spectre_runner_contract.py -q`

Expected: FAIL until runner guard exists.

- [ ] **Step 3: Implement Spectre runner template**

The physical adapter may use `virtuoso-bridge-lite` Spectre helpers or a generated shell script, but the result backend must follow the confirmed OCEAN route:

```text
source Cadence environment
spectre -64 input.scs ... -format psfxl -raw <psf_dir>
ocean -nograph -replay <metric_probe.ocn> -log <metric_probe.log>
```

The implementation must serialize simulator status, PSF/result paths, OCEAN status, scalar metric values, formula text, formula provenance, and sanitized artifacts into a local result manifest. Python must not compute metrics from PSF waveforms.

- [ ] **Step 4: Verify runner tests pass with mocked SpectreSimulator**

Run: `cd ic-auto-opt-workflow && pytest tests/test_spectre_runner_contract.py -q`

Expected: PASS without requiring Cadence or SSH.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/templates/spectre_maestro_project/src/run_candidate.py src/hermes_workflow/templates/spectre_maestro_project/src/optimization_loop.py tests/test_spectre_runner_contract.py
git commit -m "feat: guard real spectre execution behind approval"
```

## Task 13: Virtuoso/Maestro Export Instructions

**Files:**
- Modify: `execution_package/EXECUTION_TASK.md` renderer in `src/hermes_workflow/package.py`
- Create: `docs/CLAUDE_EXECUTION_CONTRACT.md`
- Test: `tests/test_package_execution.py`

- [ ] **Step 1: Write contract assertions**

Assert docs and generated execution task mention these `virtuoso` skill requirements:

```text
run virtuoso-bridge status before Maestro operations
use snapshot for focused Maestro inspection when possible
use maeCreateNetlistForCorner for export
download remote input.scs through bridge file transfer
do not invent SKILL calls without checking references
do not use Maestro GUI simulation loop for optimization
write escalation_report.json if variables cannot be templated
```

- [ ] **Step 2: Implement docs and renderer text**

Use the exact boundary language from this plan and the handoff document. Include the `virtuoso` skill guardrail that remote files stay remote until downloaded.

- [ ] **Step 3: Verify contract assertions pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py::test_execution_task_mentions_virtuoso_export_contract -q`

Expected: PASS.

- [ ] **Step 4: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add docs/CLAUDE_EXECUTION_CONTRACT.md src/hermes_workflow/package.py tests/test_package_execution.py
git commit -m "docs: define claude maestro export contract"
```

## Task 14: Final Summary And Report Generation

**Files:**
- Create: `src/hermes_workflow/final_report.py`
- Modify: `src/hermes_workflow/cli.py`
- Test: `tests/test_final_report.py`

- [ ] **Step 1: Write final report tests**

Given ledger, best candidate, optimizer state, and final summary fixture, assert generated `reports/final_report.md` contains:

```text
project name
testbench locator
best candidate parameters
best candidate metrics
hard constraint pass/fail table
objective value
budget used and total
whether any escalation occurred
paths to ledger and state artifacts
```

- [ ] **Step 2: Run final report tests and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_final_report.py -q`

Expected: FAIL until report generator exists.

- [ ] **Step 3: Implement final report generator**

`final_report.py` must export:

```text
load_final_artifacts(project_dir: Path) -> FinalArtifacts
render_final_report(artifacts: FinalArtifacts) -> str
write_final_report(project_dir: Path) -> Path
```

- [ ] **Step 4: Add CLI command**

Add `write-final-report PROJECT_DIR`.

- [ ] **Step 5: Verify tests pass**

Run: `cd ic-auto-opt-workflow && pytest tests/test_final_report.py -q`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/final_report.py src/hermes_workflow/cli.py tests/test_final_report.py
git commit -m "feat: generate hermes final optimization report"
```

## Task 15: End-To-End File-Contract Smoke Test

**Files:**
- Create: `tests/test_end_to_end_file_contract.py`
- Modify: `README.md`

- [ ] **Step 1: Write end-to-end smoke test**

Test flow:

```text
create project from template
copy bridge_test_inv fixture configs
validate contracts
build execution package
copy passing preflight fixtures
inspect preflight
write approve_first_real_run supervisor instruction
run mock optimization loop
write final report
```

No step may call Virtuoso, SSH, Spectre, or TuRBO.

- [ ] **Step 2: Run end-to-end test and confirm failure**

Run: `cd ic-auto-opt-workflow && pytest tests/test_end_to_end_file_contract.py -q`

Expected: FAIL until previous tasks are wired through CLI or importable helpers.

- [ ] **Step 3: Fix only integration gaps**

Limit changes to command names, return types, path handling, and schema field consistency discovered by the smoke test.

- [ ] **Step 4: Verify full test suite**

Run:

```bash
cd ic-auto-opt-workflow
pytest -q
ruff check .
```

Expected: all tests pass and ruff reports no issues.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add README.md tests/test_end_to_end_file_contract.py src/hermes_workflow templates
git commit -m "test: cover end-to-end file contract workflow"
```

## Task 16: Real Integration Readiness Checklist

**Files:**
- Create: `docs/REAL_INTEGRATION_CHECKLIST.md`
- Modify: `README.md`

- [ ] **Step 1: Document environment checks**

Include exact commands:

```bash
cd virtuoso-bridge-lite
source .venv/bin/activate
virtuoso-bridge status
virtuoso-bridge license
virtuoso-bridge windows
```

Expected status:

```text
[tunnel] running
[daemon] OK
[spectre] OK
```

- [ ] **Step 2: Document manual first real run gate**

Include sequence:

```text
Hermes validates project
Hermes builds execution package
Execution agent exports input.scs through virtuoso skill
Hermes prepares template.scs and writes netlist_preparation_report.json
Hermes runs deterministic dry-run without real Spectre and writes dry_run_report.json
Hermes writes supervisor_instruction.json
Execution agent runs first real Spectre batch only after approve_first_real_run
```

- [ ] **Step 3: Document escalation triggers**

Include:

```text
missing approved variable in input.scs
approved variable resolved to non-templateable value
raw data lacks required signal
metric implementation cannot match metric contract
Spectre license unavailable
optimizer returns non-finite objective
any immutable config hash drift
```

- [ ] **Step 4: Verify docs mention all safety gates**

Run: `cd ic-auto-opt-workflow && pytest tests/test_package_execution.py tests/test_approvals.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
cd ic-auto-opt-workflow
git add docs/REAL_INTEGRATION_CHECKLIST.md README.md
git commit -m "docs: add real integration readiness checklist"
```

## Implementation Order

1. Tasks 1-3: file contracts and schema validation.
2. Tasks 4-6: project template and execution package.
3. Tasks 7-8: preflight report reading and Hermes approval gate.
4. Task 9: independent agent file-contract verification.
5. Task 10: mock optimization loop without Cadence.
6. Task 11 / Plan C C-1: Hermes exported `input.scs` templating contract.
7. Plan C C-2: Hermes deterministic dry-run candidate renderer.
8. Plan C C-4: post-approval real-run package contract.
9. Plan C C-5: real-run result handoff contract.
10. Plan C C-5.5: dual-agent result handoff simulation gate.
11. Plan C C-6: real metric result contract for Spectre + OCEAN, including formula provenance and scalar output schema.
12. Plan C C-6.5: optional real metric extraction simulation/evidence gate using captured Spectre/OCEAN artifacts before optimizer-loop wiring.
13. Plan C C-7: physical execution adapter wiring for standalone Spectre + OCEAN through `virtuoso-bridge-lite`/execution-agent boundary.
14. Plan C C-8: ledger append and optimizer state update from checked real metric results.
15. Plan C C-9: next real-run package contract after checked recorded real results.
16. Plan C C-10: real-run failure/retry policy contract and unresolved-run guard.
17. Plan C C-11: local/fake controlled smoke for C-9 -> fake C-7-style artifacts -> C-5/C-6 -> C-8 plus one C-10 retry path.
18. Plan C C-12: controlled real-tool/agent practice for one approved real run.
19. C-7 real-tool closure fixes: preserve the proven Maestro/ADE `netlist/` and `psf/` layout in the physical Spectre + OCEAN adapter.
20. Optimizer practice-first flow: use the known-good real `real_001` chain as a foundation check, then run a real `optimizer.skill` + TuRBO loop before implementing new Hermes optimizer behavior.
21. C-13/C-15: narrow single-candidate suggestion, candidate injection, and fixed-budget loop productization around the proven real-run contracts.
22. C-17/C-18: native TuRBO optimizer runner and batch parallel evaluator using `Turbo1.optimize()`, bounded by `spectre.parallel_jobs` while preserving per-process `threads_per_run`.
23. C-19/C-20: execution-agent handoff acceptance using concise task packets, non-sandbox real-tool execution, and supervisor/Hermes manifest-level audit.
24. C-21: OCEAN-only metric extraction retry policy for command/license failures after Spectre succeeds.
25. C-22: execution package task wording alignment with the locked execution-agent role model and manifest-level audit rule.
26. C-23: optimizer execution-agent task packet MVP generated by Hermes from the proven `run-native-turbo --parallel` handoff.
27. C-24: generated C-23 optimizer task packet handoff acceptance with one local worker-agent execution and supervisor/Hermes manifest-level audit.
28. C-25: deterministic optimizer run acceptance audit command for completed native TuRBO handoff artifacts.

## Verification Commands

Run after each task:

```bash
cd ic-auto-opt-workflow
pytest <task-specific-test> -q
```

Run before requesting implementation review:

```bash
cd ic-auto-opt-workflow
pytest -q
ruff check .
```

Run before any real Cadence integration:

```bash
cd virtuoso-bridge-lite
source .venv/bin/activate
virtuoso-bridge status
virtuoso-bridge license
```

## Self-Review

- Spec coverage: The plan covers file contracts, schema definition, Hermes template generation, validation, execution package builder, Hermes deterministic preflight, agent verification harnesses, mock optimization loop, exported `input.scs` templating, approved Spectre/OCEAN result routing, and real integration readiness.
- Boundary check: The plan keeps `virtuoso-bridge-lite` as a dependency and does not copy its `virtuoso`, `spectre`, or `optimizer` implementations.
- Safety check: The plan enforces dry run and `supervisor_instruction.json` approval before real Spectre or optimizer execution.
- Open interface check: The `Claude-cli-skill` boundary is handled by file contracts first, with real adapter wiring deferred until its exact invocation interface is known.
