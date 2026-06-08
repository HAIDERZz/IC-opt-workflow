# Execution Progress 2026-05-29

This note preserves the implementation state for continuing Plan A after context compaction or quota reset.

## Repository State

- Repo: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Baseline branch: `master`
- Baseline commit: `885e97f docs: capture workflow planning baseline`
- Latest C-3 code commit before docs-only cleanup: `edb107f fix: harden preflight readiness gates`; docs cleanup continues through current HEAD
- Active plan: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Current scope: C-69 Remote SSH Execution Backend Design
- current_scope: C-69 Remote SSH Execution Backend Design
- current_scope_exact: C-69 Remote SSH Execution Backend Design
- Current status: C-69 design spec is written, verified-only. It defines a
  remote SSH execution mode where the Linux EDA server remains the source of
  truth for the project directory, user-configured passwordless SSH is required,
  local workstation `ic-opt` runs OpenBox/controller/report logic, and remote
  Linux runs Spectre/OCEAN while preserving full artifacts.
- Next allowed action: User review C-69 remote SSH execution backend design spec; if approved, write implementation plan starting with Remote SSH Runner and doctor MVP.
- Execution method: `superpowers:subagent-driven-development`
- Dependencies installed in active Python environment on 2026-05-29: `pytest`, `typer`, `pydantic`, `PyYAML`, `ruff`

## C-66 Claude `/ic-opt` Continuation Validation 2026-06-07

C-66 is a real product-continuation validation checkpoint.

Evidence:

```text
docs/CLAUDE_IC_OPT_CONTINUATION_VALIDATION_2026-06-07.md
```

First real command:

```text
claude -p --dangerously-skip-permissions "/ic-opt /tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb --real --max-evals 100 --batch-size 10 --parallel-jobs 10"
```

Result:

```text
Project: /tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb
Initial files: opt_requirement.md, cadence_env.csh
Evaluations: 100
Recommended: feasible real_066
Parameters: F=26, L=40n, VB_LO=310m, W=1u
Global optimum claim: false
```

Follow-up simulated user command:

```text
请再进行40个点的优化
```

Observed behavior:

- Claude correctly translated the short request into
  `hermes-workflow continue-openbox-real ... --additional-evals 40`.
- The command did not append new evaluations.
- `reports/optimizer_evaluations.jsonl` remained at 100 rows.
- Claude returned a continuation failure because OpenBox could not fill the
  requested batch of 10 unique candidates after 300 deduplication attempts.

Current truth:

```text
Validated:
  one-line Claude /ic-opt real optimization
  short follow-up continuation intent routing
  narrow continuation hardening in code/tests
  real repair path reached 140 cumulative evaluations

Product rule after hardening:
  generated continuation task packages must inherit project Spectre resources
  and must not hardcode parallel_jobs unless the user explicitly requests a
  resource change
```

No optimizer backend change, OCEAN formula rewrite, Spectre setup change, PSF
parsing, fake-run ladder, or hand-picked point selection occurred. The manual
repair command did use `parallel_jobs=10` against a project initially run with
`parallel_jobs=12`; `check-optimizer-run` correctly rejected the mixed-resource
ledger, which is why continuation packages now omit `--parallel-jobs` by
default.

## Current C-64 Checkpoint 2026-06-07

C-64 is an observable Claude execution-agent handoff checkpoint.

Implemented today:

- Added `src/hermes_workflow/execution_agent_handoff.py`.
- Added `--execution-agent direct|claude` to `ic-opt` and lower-level
  `hermes-workflow optimize`.
- Kept shell `ic-opt` default behavior as `direct`.
- Updated `claude_skills/ic-opt/SKILL.md` so Claude `/ic-opt` appends
  `--execution-agent claude` by default.
- Added `docs/CLAUDE_EXECUTION_AGENT_HANDOFF_2026-06-07.md`.
- Added C-64 design spec and implementation plan.

Real evidence:

```text
Project: /tmp/ic_auto_opt_c64_handoff_zX9JrO/Mixer_opt_muti_tb
Initial files: opt_requirement.md, cadence_env.csh
Command: claude -p --dangerously-skip-permissions "/ic-opt PROJECT --real"
Handoff: reports/execution_agent_handoff_report.json status=pass, execution_agent=claude, returncode=0
Evaluations: 100
Counts: 16 feasible, 68 constraint_failed, 16 metric_check_failed
Recommended: feasible real_051
Global optimum claim: false
```

Current truth:

```text
Implemented:
  ic-opt PROJECT_DIR --real
  Claude CLI /ic-opt PROJECT_DIR --real after installing claude_skills/ic-opt
  Claude CLI observable supervisor -> independent execution-agent handoff
  hermes-workflow optimize PROJECT_DIR --real --execution-agent direct|claude
  file contracts, task package, real optimizer reports

Not implemented:
  Codex or non-Claude /ic-opt runtime adapters
  clean-machine installer for the Claude skill
  automatic final user acceptance
```

No optimizer code, simulator behavior, OCEAN formula, Spectre setup, OpenBox
strategy, product environment policy, or multi-testbench contract changed.

## C-63 Checkpoint 2026-06-07

C-63 is a real Claude CLI slash-skill landing checkpoint.

Implemented today:

- Added `claude_skills/ic-opt/SKILL.md`.
- Added `claude_skills/README.md`.
- Linked the skill locally under `~/.claude/skills/ic-opt` for validation.
- Added `docs/CLAUDE_IC_OPT_REAL_LANDING_2026-06-07.md`.
- Added `docs/superpowers/plans/2026-06-07-claude-ic-opt-real-landing.md`.
- Synchronized product-facing docs to state that Claude CLI `/ic-opt` is now
  implemented, while automatic supervisor-agent to independent execution-agent
  dispatch remains future work.

Real evidence:

```text
Project: /tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb
Initial files: opt_requirement.md, cadence_env.csh
Command: claude -p --dangerously-skip-permissions "/ic-opt PROJECT --real"
Evaluations: 100
Counts: 16 feasible, 68 constraint_failed, 16 metric_check_failed
Recommended: feasible real_051
Global optimum claim: false
```

Current truth:

```text
Implemented:
  ic-opt PROJECT_DIR --real
  Claude CLI /ic-opt PROJECT_DIR --real after installing claude_skills/ic-opt
  hermes-workflow optimize PROJECT_DIR --real
  file contracts, task package, real optimizer reports

Not implemented:
  automatic supervisor-agent -> independent execution-agent dispatch
  Codex or non-Claude /ic-opt runtime adapters
  clean-machine installer for the Claude skill
```

No optimizer code, simulator behavior, OCEAN formula, Spectre setup, or
multi-testbench contract changed.

## C-62 Checkpoint 2026-06-07

C-62 is a docs/status correction checkpoint.

Implemented today:

- Added `docs/AGENT_INTEGRATION_STATUS.md`.
- Added `docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.
- Synchronized product-facing docs and progress files to distinguish the
  implemented shell CLI from the unimplemented two-agent runtime layer.

Current truth:

```text
Implemented:
  ic-opt PROJECT_DIR --real
  hermes-workflow optimize PROJECT_DIR --real
  file contracts, task package, real optimizer reports

Not implemented:
  /ic-opt slash command in an agent runtime
  automatic supervisor-agent -> execution-agent dispatch
```

No code or simulator behavior changed.

## Current C-50 Checkpoint 2026-06-06

Active spec:

```text
docs/superpowers/specs/2026-06-06-multi-testbench-candidate-evaluation-design.md
```

Active implementation plan:

```text
docs/superpowers/plans/2026-06-06-multi-testbench-candidate-evaluation.md
```

C-50 introduces the multi-testbench candidate evaluation route required for
real Mixer optimization:

```text
candidate parameters
-> render same parameters into each named Maestro/ADE testbench bundle
-> run child Spectre/OCEAN jobs
-> aggregate child scalar metric manifests
-> evaluate constraints/objective once at candidate level
```

Planned scope:

- preserve each testbench's native Maestro point-root netlist bundle;
- route metrics by `metric.testbench`;
- aggregate child result/metric manifests without parsing PSF or rewriting
  formulas;
- respect global `spectre.parallel_jobs` across all child jobs;
- keep OpenBox/native TuRBO as candidate generators.

Task 1 result:

- `TestbenchesConfig` and `metric.testbench` routing are available in the
  contract layer.
- `prepare-from-requirement` writes `config/testbenches.yaml` only for
  multi-testbench intake and preserves the old single-testbench layout
  otherwise.
- Duplicate testbench ids and unknown metric routes fail closed.
- Verification passed:
  `python3 -m pytest tests/test_schemas.py tests/test_requirement_intake.py`
  (`39 passed`) and
  `python3 -m pytest tests/test_validate.py tests/test_package.py tests/test_cli.py`
  (`65 passed`).

Task 2 result:

- Multi-testbench point-root imports are namespaced under
  `netlists/testbenches/<id>/exported/` while the primary legacy
  `netlists/exported/` path is preserved for existing commands.
- Child templates are written under
  `netlists/testbenches/<id>/templates/template.scs`.
- `dry-run` writes child rendered candidates under
  `runs/dry_run/testbenches/<id>/input.scs`.
- Unsafe symlinks in any named child point-root fail closed and include the
  testbench id in the issue text.
- Verification passed:
  targeted Task 2 tests (`3 passed`),
  requirement/netlist/dry-run/validate tests (`59 passed`), and
  package/CLI tests (`46 passed`).

Task 3 result:

- `aggregate_multi_testbench_run()` aggregates child result/metric manifests
  from `runs/real/<run_id>/testbenches/<id>/`.
- Aggregate candidate-level manifests are written to the existing
  `runs/real/<run_id>/result_manifest.json` and
  `runs/real/<run_id>/metrics/metric_result_manifest.json` paths.
- Optional `child_results` and `child_metric_results` fields preserve child
  provenance while keeping single-testbench manifests backward-compatible.
- Existing `check-real-run` and `check-metric-results` pass on a fake
  two-testbench aggregate and distinguish metric failures from real-tool
  failures.
- Verification passed:
  `python3 -m pytest tests/test_multi_testbench_aggregation.py` (`3 passed`),
  `python3 -m pytest tests/test_result_handoff.py tests/test_metric_results.py tests/test_requirement_intake.py`
  (`101 passed`),
  `python3 -m pytest tests/test_package.py tests/test_cli.py tests/test_validate.py`
  (`65 passed`), and targeted `ruff check`.

Task 4 result:

- User project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` provided real
  multi-testbench evidence with `cg_nf`, `iip3`, and `p1db`.
- Best observed candidate `real_068` has all child result manifests succeeded
  and all child metric manifests succeeded.
- The aggregate candidate-level metric manifest contains `BW`, `MAX_GAIN`,
  `NF_3G`, `IIP3`, and `P1DB`.
- The aggregate candidate-level result manifest preserves child references for
  all three testbenches.

Task 5 result:

- OpenBox completed 100 real multi-testbench Spectre/OCEAN evaluations in
  `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb`.
- The final run had 10 batches of 10, `evaluation_count=100`, and no remaining
  optimizer process.
- Status counts from `reports/optimizer_evaluations.jsonl`:
  `19 feasible`, `65 constraint_failed`, and `16 metric_check_failed`.
- `check-optimizer-run`, `summarize-optimizer-run`,
  `visualize-optimizer-run`, and `finalize-optimizer-run` were rerun after the
  process finished so the final reports all reflect 100 evaluations.
- Best observed is `real_068`: `F=26`, `W=1u`, `L=40n`, `VB_LO=310m`;
  `BW=19171311625.11458 Hz`, `MAX_GAIN=4.242801858394763 dB`,
  `NF_3G=11.81241967045868 dB`, `IIP3=3.206487765822459 dBm`,
  `P1DB=-0.8997623115419788 dBm`; objective `-0.0503357919658288`.
- Decision: `accept_best_observed`, confidence `medium`,
  `global_optimum_claim=false`.

C-50 closeout route audit:

- Aligned with the active spec and top-level plan.
- The completed real evidence is stronger than the original first-evidence
  target: three testbenches and 100 optimizer evaluations instead of a
  two-testbench single candidate.
- No broad scheduler/framework rewrite, synthetic merged Spectre deck, PSF
  parsing, formula rewrite, or `parallel_jobs` multiplication was introduced.

## C-55 Production Landing Acceptance 2026-06-07

Status: complete, verified-only.

- Added `docs/PRODUCTION_LANDING_ACCEPTANCE_2026-06-07.md`.
- Fresh readiness check passed for
  `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb`.
- Readiness state: `ready_for_closeout_review`.
- Final summary accepts `real_093`.
- Accepted point: `F=20`, `W=1.4u`, `L=30n`, `VB_LO=310m`.
- Accepted scope: best observed under evaluated artifacts and configured FoM,
  not a global optimum certificate.
- No Spectre/OCEAN rerun, PSF parsing, formula rewrite, or synthetic
  multi-testbench merge was introduced.

## C-57/C-58 Product Entrypoint Checkpoint 2026-06-07

C-57 implementation:

- Commit `e6ce269`: added `hermes-workflow optimize PROJECT_DIR --real`.
- Commit `4550ce8`: recorded C-57 one-command flow docs/progress.
- The command wraps the proven route from requirement intake through decision
  reporting and stops before final user acceptance.

Fresh real drill:

- Project copy: `/tmp/ic_auto_opt_optimize_real_jPaNVI/Mixer_opt_muti_tb`.
- Result: 100 real multi-testbench OpenBox/Spectre/OCEAN evaluations.
- Acceptance: `check-optimizer-run` accepted.
- Status counts: `65 constraint_failed`, `19 feasible`,
  `16 metric_check_failed`.
- Recommended feasible candidate: `real_066`.
- Parameters: `F=26`, `L=40n`, `VB_LO=310m`, `W=1u`.

Product gap:

- `./.venv/bin/hermes-workflow optimize ... --real` failed because OpenBox was
  not installed in the repo `.venv`.
- Invoking the same route from the development OpenBox environment succeeded.
- This is not an acceptable release shape; C-58 must provide one product
  environment for `ic-auto-opt-workflow`, OpenBox, TuRBO, and report
  dependencies.

C-58 plan:

```text
docs/superpowers/plans/2026-06-07-product-entrypoint-unified-environment.md
```

Historical C-58 target UX, superseded by C-63 boundary clarification:

```text
implemented shell entry: ic-opt /path/to/project --real
implemented Claude CLI entry after skill install: /ic-opt /path/to/project --real
```

C-63 clarification: the shell entry and Claude CLI slash-skill entry are
implemented; automatic supervisor-agent to independent execution-agent dispatch
is not.
See `docs/AGENT_INTEGRATION_STATUS.md` and
`docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

## C-58 Product Entrypoint Completion 2026-06-07

C-58 is complete, verified-only.

Implementation:

- Added `requirements-product.txt` for one product-level environment.
- Added the `ic-opt` product console script, backed by the existing optimizer
  flow instead of a new workflow engine.
- Kept `hermes-workflow optimize` as the lower-level implementation command.

Verification:

- Repo `.venv` imports `openbox`, `hermes_workflow`, `lightgbm`, `shap`, and
  `pyrfr`.
- `./.venv/bin/ic-opt --help` shows `ic-opt [OPTIONS] PROJECT_DIR`.
- Targeted tests passed: `tests/test_product_cli.py` and
  `tests/test_optimizer_flow.py` (`5 passed`); targeted ruff passed.
- Dry orchestration passed at
  `/tmp/ic_auto_opt_c58_dry_jCiZAA/Mixer_opt_muti_tb`.
- Unsandboxed real product acceptance passed at
  `/tmp/ic_auto_opt_c58_real_unsandboxed_rj40MJ/Mixer_opt_muti_tb` with 100
  evaluations, `65 constraint_failed`, `19 feasible`, `16 metric_check_failed`,
  and recommended feasible `real_066`.

Execution note:

- A sandboxed real attempt failed with Spectre `cannot create pipe` and
  `can't create server socket`. Future real Cadence/Spectre/OCEAN acceptance
  must run unsandboxed; otherwise the failure can be a sandbox artifact rather
  than a project/tool-flow bug.

User project directories remain data-only; no per-project Python virtualenvs.

## C-59 Product One-Line Cadence Environment Discovery 2026-06-07

C-59 is complete, verified-only.

Implementation:

- `ic-opt --cadence-cshrc` is now optional.
- Discovery order is explicit `--cadence-cshrc`, `PROJECT_DIR/cadence_env.csh`,
  `IC_OPT_CADENCE_CSHRC`, then `~/.ic-opt/cadence_env.csh`.
- The setup path is still user supplied; the product does not infer or hardcode
  a Spectre version from shell startup files.
- Lower-level `hermes-workflow optimize` remains explicit for audit/admin use.

Verification:

- Product CLI tests cover explicit override, project-local discovery,
  environment variable discovery, and fail-closed missing env.
- `./.venv/bin/ic-opt --help` shows `ic-opt [OPTIONS] PROJECT_DIR`; the Cadence
  cshrc option is not required.
- One-line dry orchestration passed at
  `/tmp/ic_auto_opt_c59_dry_5J81NM/Mixer_opt_muti_tb` with
  `PROJECT_DIR/cadence_env.csh` and no `--cadence-cshrc` flag.

Route audit:

- No optimizer math, OCEAN formulas, multi-testbench aggregation, Spectre
  version, or product virtualenv contract changed.

## C-60 Product One-Line Real Acceptance 2026-06-07

C-60 is complete, verified-only.

Real acceptance:

- Workspace: `/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb`.
- Fresh start copied only `opt_requirement.md` and
  `PROJECT_DIR/cadence_env.csh`; no old generated optimizer artifacts were
  copied.
- Command:
  `./.venv/bin/ic-opt /tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb --real --max-evals 100 --batch-size 10 --parallel-jobs 10`.
- The command did not pass `--cadence-cshrc`, proving project-local environment
  anchor discovery in a real run.
- Flow status: `pass`.
- Evaluations: `100`.
- Status counts: `68 constraint_failed`, `16 feasible`,
  `16 metric_check_failed`.
- Recommended feasible run: `real_051`.
- Recommended action: `accept_best_observed_or_continue`.
- OpenBox advanced visualization: `generated`.
- `global_optimum_claim=false`.

Recommended point:

```text
F=30
L=40n
VB_LO=310m
W=0.8u
BW=19592140591.69946
MAX_GAIN=4.028875688617442
NF_3G=11.79754488809267
IIP3=3.2821304958007
P1DB=-0.8653580069775275
```

Route audit:

- Aligned with the product landing route.
- No optimizer math, OCEAN formula, Spectre version, multi-testbench
  aggregation, or product virtualenv contract changed.

## C-61 Product Release Polish 2026-06-07

C-61 is complete, verified-only.

Changes:

- Replaced root `README.md` with a product-facing release entry.
- Added `docs/PRODUCT_RELEASE_CHECKLIST.md`.
- Pinned `requirements-product.txt` visualization/report dependencies to
  `shap==0.49.1` and `lightgbm==4.6.0`, matching the C-60 product environment.

Verification:

- Product import check passed in the repo `.venv`.
- `ic-opt --help` and `hermes-workflow --help` are available from the repo
  `.venv`.
- Development cadence check and `git diff --check` passed.

Route audit:

- No real-tool rerun was needed.
- No optimizer math, OCEAN formula, Spectre version, multi-testbench
  aggregation, product command behavior, or per-project venv policy changed.

Post-C-49 real smoke:

- `real_001`: default lower-bound candidate `F=14`, `W=0.4u`, `L=30n`,
  `VB_LO=150m`; Spectre 25.1 and OCEAN ran, but `BW` was non-scalar at this
  candidate, so it is candidate-level evidence rather than the clean pass.
- `real_002`: approved-grid baseline smoke `F=26`, `W=1u`, `L=40n`,
  `VB_LO=310m`; Spectre 25.1 succeeded, OCEAN succeeded, `check-real-run`
  passed, and `check-metric-results` passed.
- `real_002` scalar results: `BW=19171311623.07684 Hz`,
  `MAX_GAIN=4.242801858622344 dB`, `NF_3G=11.81241967045867 dB`.
- Mixer encrypted `ade_e.scs` requires Spectre 25.1. Spectre 23.1 reports
  `FATAL (SFE-79): Cannot decrypt the data` for this bundle.

Post-C-49 Mixer OpenBox optimizer practice:

- Clean workspace: `/home/zzchen/spectre_opt_prj/Mixer_opt_openbox_001`.
- Run settings: OpenBox, `max_evals=100`, `batch_size=10`,
  `parallel_jobs=10`, `threads_per_run=10`, `preset=cx`, Spectre 25.1 wrapper
  `/tmp/ic_auto_opt_mixer_spectre251_env.csh`.
- Result: `run-openbox-real` completed 100 real evaluations;
  `check-optimizer-run`, `summarize-optimizer-run`, `finalize-optimizer-run`,
  and `optimizer-status` all passed.
- Status counts: `constraint_failed=59`, `metric_check_failed=41`,
  `real_check_failed=0`, `feasible=0`.
- Scalar constraint pass counts: `BW=15/59`, `MAX_GAIN=15/59`,
  `NF_3G=0/59`.
- Decision: `stop_for_user_review`, confidence `low`,
  `global_optimum_claim=false`, continuation not recommended before user
  review.
- OpenBox advanced visualization generated under
  `reports/openbox_advanced_visualization/`.
- Follow-up: no-feasible best-candidate semantics need improvement because
  `best observed` can point at a metric-check-failed row when no feasible
  candidate exists.

Post-C-49 Mixer NF=12dB optimizer practice:

- Clean workspace: `/home/zzchen/spectre_opt_prj/Mixer_opt_openbox_nf12_001`.
- Only contract change: `NF_3G lt 11.5 dB` -> `NF_3G lt 12 dB`.
- Run settings: OpenBox, `max_evals=100`, `batch_size=10`,
  `parallel_jobs=10`, `threads_per_run=10`, `preset=cx`, Spectre 25.1 wrapper
  `/tmp/ic_auto_opt_mixer_spectre251_env.csh`.
- Result: `run-openbox-real` completed 100 real evaluations;
  `check-optimizer-run`, `summarize-optimizer-run`, `finalize-optimizer-run`,
  and `optimizer-status` all passed.
- Status counts: `constraint_failed=70`, `feasible=12`,
  `metric_check_failed=18`, `real_check_failed=0`.
- Best feasible observed: `real_100`, objective `1.134258035990259e-10`,
  parameters `F=24`, `W=1.4u`, `L=40n`, `VB_LO=350m`;
  metrics `BW=19225783343.99703 Hz`, `MAX_GAIN=5.48152961454769 dB`,
  `NF_3G=11.95357122269306 dB`.
- Decision: `continue_more_evals`, confidence `medium`,
  `global_optimum_claim=false`, continuation recommended because recent window
  improved and plateau was not detected.
- Continuation blocker: attempting `continue-openbox-real --additional-evals 100
  --batch-size 10 --parallel-jobs 10` did not create `real_101+` or append
  evaluations. The OpenBox Python process stayed high-CPU for about 10 minutes
  in candidate generation after loading prior observations and was terminated.
  Existing 100-eval results remain valid. This is an OpenBox continuation
  candidate-generation performance issue, not a Spectre/OCEAN failure.

Verification:

```text
python3 -m pytest tests/test_requirement_intake.py tests/test_validate.py tests/test_netlists.py tests/test_package.py tests/test_cli.py -q
python3 -m pytest -q
python3 -m ruff check src tests tools
```

Result: targeted tests passed with `88 passed`; full suite passed with `592 passed, 1 skipped`; ruff passed.

Route audit: aligned. C-49 did not run real tools, parse PSF, rewrite OCEAN formulas, change optimizer execution behavior, or flatten the Maestro/ADE netlist layout. The only schema extension was accepting `optimizer.algorithm: openbox`, matching the already-developed OpenBox backend route.

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

Historical next recommended action, superseded by C-10:

- C-10 failure/retry policy was selected and is now implemented through Task 5.
- C-10 final gate has passed; next chain C-9 -> C-7 -> C-8 with one controlled C-10 failure/retry case in C-11 local smoke.

## Plan C C-10 Real-Run Failure Retry Policy Contract

Status: complete and reviewed as of 2026-06-03.

Spec:

- `docs/superpowers/specs/2026-06-02-real-run-failure-retry-policy-contract-design.md`
- Commit: `68c404a docs: design real run failure retry policy`

Implementation plan:

- `docs/superpowers/plans/2026-06-02-real-run-failure-retry-policy-contract.md`
- Commit: `13d39e9 docs: plan real run failure retry policy`

Planned:

- Add recovery report schemas for real-run recovery status, classification, allowed actions, and assessment reports. Complete in `104ef26 feat: add real run recovery report schema`.
- Add `real_run_recovery.py` to classify pending, invalid, failed, partial, metric-failed, recordable, already-recorded, retry-prepared, abandoned, and stopped real-run states. Complete in `a9dc13a feat: classify real run recovery state`.
- Add explicit supervisor recovery decisions through `recovery_decision.json`. Complete in `c76f152 feat: prepare real run retry packages`.
- Add retry package preparation for the same candidate using a new `run_id`, while preserving failed-run artifacts. Complete in `c76f152 feat: prepare real run retry packages`.
- Add a C-9 unresolved-run guard so `prepare-next-real-run` cannot advance past unresolved pending/failed/partial/retry-prepared packages. Complete in `e6d19a5 feat: block next runs on unresolved real runs`.
- Add CLI commands: `assess-real-run-recovery`, `prepare-real-run-retry`, and `resolve-real-run-failure`. Complete in `7994d83 feat: add real run recovery cli`.

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
- Spec review passed after fixing retry resolution deadlocks. A retry-prepared source run now remains blocking while the retry is pending, but unblocks once the retry run is recorded or resolved abandoned.
- Code-quality review passed after eliminating hidden checker report writes from the C-9 guard path and restoring direct ledger parser coverage in tests.

Task 5 verification and review:

- `python3 -m pytest tests/test_cli.py tests/test_real_run_recovery.py tests/test_next_real_run.py -q`: passed, 95 tests.
- `python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/real_run_recovery.py tests/test_cli.py`: passed.
- `git diff --check`: passed.
- Spec review passed after confirming the CLI commands delegate only to recovery logic, expose pass/fail output without tracebacks, and do not invoke real tools or C-7.
- Code-quality review initially found stale recovery-report output for pre-assessment validation failures. The fix fingerprints any existing recovery report before command execution and only prints report details if the current command updates the report. Re-review passed.

Full C-10 verification baseline after Task 5:

- `python3 -m pytest -q`: passed, 432 tests.
- `python3 -m ruff check src tests tools`: passed.
- `git diff --check`: passed.

Task 6 final verification and review:

- `python3 -m pytest tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_cli.py -q`: passed, 97 tests.
- `python3 -m pytest -q`: passed, 434 tests.
- `python3 -m ruff check src tests tools`: passed.
- `git diff --check`: passed.
- Final spec review initially found an unsafe artifact classification mismatch. The fix classifies both missing and unsafe declared result artifacts as `tool_result_partial`, matching the C-10 spec and preserving retry/stop actions.
- Final code-quality review found that assessment reads could follow symlinked `recovery_decision.json` files. The fix rejects symlinked decision files in optional read paths and preflights decision targets before write-path assessment. Spec and code-quality re-reviews passed.

Locked C-10 policy:

- C-10 is contract-only.
- It must not run Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or the C-7 adapter.
- It must not parse PSF, rewrite OCEAN formulas, compute metrics in Python, write optimizer ledger/state, or add failure-penalty rows.
- C-10 final gate has passed. C-11 local smoke is now the next scope, but should stay local/fake controlled before direct real tool/agent integration.

Next required action:

- C-11 local smoke design spec exists: `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`.
- C-11 local smoke implementation plan exists: `docs/superpowers/plans/2026-06-03-local-real-run-smoke.md`.
- Plan C process hardening lightweight cadence guard is complete; verified-only. It adds `docs/CURRENT_TASK_STATE.json`, a 200-line-budget cadence checker, and a process-hardening design spec so future context resumes have a single current-state anchor and cannot falsely claim `reviewed` without evidence.
- Current scope: C-7 Real Tool Closure Fixes
- Current status: verified-only; C-7 Real Tool Closure Fixes Task 2 Spectre-safe unit formatting guard is complete, and continuous variables now use compact Spectre-safe unit suffixes.
- Next recommended action: start C-7 Real Tool Closure Fixes Task 3 metric namespace contract.
- next_allowed_action: start C-7 Real Tool Closure Fixes Task 3 metric namespace contract; do not run real tools until formula contract fixes are complete and user authorizes the closure smoke
- C-11 Task 1 checkpoint: added `tests/test_local_real_run_smoke.py` with only `test_c11_helper_seeds_recorded_real_result` and `tests/real_run_smoke_helpers.py` with test-only synthetic project, fake result/metric manifests, checked recording, and ledger row helpers.
- C-11 Task 1 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only; drift is none.
- C-11 Task 1 review evidence: spec-compliance review approved by Bohr (`019e8c9f-2249-7db3-bcaf-c7744f427cbc`); code-quality review approved by Volta (`019e8ca0-424e-7683-bebe-bb44e2340c5c`). Both reviews reported no Critical, Important, or Minor findings.
- C-11 Task 2 checkpoint: added only `test_c11_library_happy_path_records_next_real_run` to `tests/test_local_real_run_smoke.py`. The smoke seeds `real_001` with `record_checked_run`, prepares `real_002`, writes fake result and metric manifests, runs `check_real_run`, `check_metric_results`, and `record_real_result`, and asserts ledger/state/best/report outputs plus `assert_no_unresolved_real_runs`.
- C-11 Task 2 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only; drift is none. No real tools, subprocess-backed C-7 adapter, network, PSF parsing, formula rewriting, Task 3 retry flow, Task 4 CLI smoke, or final gate work was added.
- C-11 Task 2 verification checkpoint: focused happy-path smoke passed immediately using Task 1 helpers; focused smoke/next-run/record regression suite passed; focused ruff passed.
- C-11 Task 2 review evidence: spec-compliance review approved by Socrates (`019e8caf-9520-75e3-9cf4-e9d913d872d0`); code-quality review approved by Dirac (`019e8cb1-9279-7273-a76e-7e760fed813e`). Both reviews reported no Critical, Important, or Minor findings.
- C-11 Task 3 checkpoint: active scope is Plan C C-11 Task 3 controlled failure/retry smoke. Added the controlled failure/retry library smoke for seed `real_001`, failed `real_002`, retry `real_003`, and next prepared `real_004`. It asserts `TOOL_RESULT_FAILED`, `RETRY_SAME_CANDIDATE`, unresolved-run blocking, retry candidate identity/parameters/metadata, checked retry success, source `real_002` becoming `ALREADY_RECORDED`, ledger rows `real_001` and `real_003`, and `assert_no_unresolved_real_runs` after retry success.
- C-11 Task 3 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only; drift is none. No real tools, subprocess-backed C-7 adapter, network, PSF parsing, formula rewriting, Task 4 CLI smoke, or final gate work was added.
- C-11 Task 3 review evidence: spec-compliance review approved by Ptolemy (`019e8cc5-30bf-7022-bca2-657b57fec88a`) after stale handoff prompts were fixed; code-quality review approved by Heisenberg (`019e8cc8-c26b-7ef2-8fd4-d5679088521d`). Both reviews reported no remaining Critical, Important, or Minor findings.
- C-11 Task 4 implementation checkpoint: added the narrow CLI smoke for `prepare-next-real-run -> fake C-7-style returned artifacts -> check-real-run -> check-metric-results -> record-real-result`. It uses `CliRunner` and `hermes_workflow.cli.app`, seeds checked `real_001`, prepares explicit `real_002`, verifies CLI output strings, records the checked run, and asserts ledger rows `real_001` and `real_002`.
- C-11 Task 4 route audit: Active spec is `docs/superpowers/specs/2026-06-03-local-real-run-smoke-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains local/fake controlled smoke only. C-11 verifies the C-9 -> fake C-7-style returned artifacts -> C-5/C-6 checks -> C-8 happy path and one C-10 failure/retry path without real Virtuoso/Spectre/OCEAN/SSH/agent/bridge execution. Drift is none; no real tools, subprocess-backed C-7 adapter, network, PSF parsing, or formula rewriting were added. Status is complete and reviewed.
- C-11 Task 4 review evidence: spec-compliance review approved by Aquinas (`019e8cd9-0de1-78e0-9201-560c807edc39`) with no findings. Code-quality review approved by Feynman (`019e8cd9-33ae-7880-aab0-767a5ed1facb`); the only low bookkeeping finding was the already-completed Step 6 checkbox, fixed in the final status update.
- C-12 initial route audit: Active spec is `docs/superpowers/specs/2026-06-03-controlled-real-tool-agent-practice-design.md`; top-level plan is `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`; alignment remains contract-led and evidence-gated. C-12 is scoped to one known cell, one approved real-run package, one execution-agent/C-7 adapter invocation, and Hermes `check-real-run`/`check-metric-results`/`record-real-result`. This initial audit predated the implementation plan and real-tool Task 3 attempt; it is superseded by the Task 3 and Task 4 checkpoints below. PSF parsing remains forbidden, and formula rewriting remains forbidden.
- C-12 implementation plan checkpoint: Active plan is `docs/superpowers/plans/2026-06-03-controlled-real-tool-agent-practice.md`. It defines five stop-and-review tasks and requires explicit user confirmation before Task 3 runs the real C-7 adapter. No real tools were run while writing the plan.
- C-12 Task 1 blocker checkpoint: local practice workspace was created under `/tmp/ic_auto_opt_c12`, `hermes-workflow` was found at `/home/zzchen/.venvs/openclaw/bin/hermes-workflow` with version `0.1.0`, `hermes-workflow init /tmp/ic_auto_opt_c12/bridge_test_inv` succeeded, fixed cell contract values were confirmed, and approved OCEAN formula text was confirmed. Task 1 stopped at Step 7 because `/tmp/ic_auto_opt_c12/bridge_test_inv/netlists/exported/input.scs` is missing. Route audit remains aligned with the C-12 spec and top-level plan: no real tools, C-7 adapter, SSH, bridge, PSF parsing, formula rewriting, or sample deck copying were used.
- C-12 Task 1 blocker review evidence: spec-compliance review approved by Plato (`019e8d35-a238-7980-ba60-607d6457152d`) with no Critical, Important, or Minor findings. Code-quality review approved by Aristotle (`019e8d36-b189-7a02-aa9f-fb52a510daef`) for the modified tracked-file changes. The only Important residual risk is that untracked `docs/OCEAN_DOC_*` and `docs/toolchain_evidence/` remain an accidental-commit risk; use explicit pathspecs only.
- C-12 Task 1 input gate completion checkpoint: `/tmp/ic_auto_opt_c12/bridge_test_inv/netlists/exported/input.scs` now exists, and its local-only SHA256 evidence file was written to `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/exported_input_scs.sha256`. Route audit remains aligned with the C-12 spec and top-level plan. Drift: none. No real tools, C-7 adapter, SSH, bridge, PSF parsing, formula rewriting, or deck commit occurred.
- C-12 Task 1 completion review evidence: spec-compliance review approved by Epicurus (`019e8d56-4dd7-7712-b7ae-abdc6fc88c02`) after fixing the Step 10 pathspec Minor. Code-quality review approved by Ohm (`019e8d58-ba6e-7b42-91fe-ef05eb5b611e`) with no Critical, Important, or Minor findings. Task 1 is complete and reviewed; do not start Task 2 until the user confirms.
- C-12 Task 2 checkpoint: user confirmed the provided `input.scs` corresponds to the template `metrics.yaml`, then Hermes `validate`, `package`, `prepare-netlist`, `dry-run`, `preflight-health`, `approve`, and `prepare-real-run --run-id real_001` all completed. `real_001` exists under `/tmp/ic_auto_opt_c12/bridge_test_inv/runs/real/real_001`, and local-only pre-execution hashes were written to `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/real_001_pre_execution_hashes.sha256`. Plan correction: the approval file exists at `$C12_PROJECT/supervisor_instruction.json`, matching `src/hermes_workflow/approvals.py` and `src/hermes_workflow/real_run.py`; the implementation plan Step 6 expected path was corrected from `reports/supervisor_instruction.json`. Route audit remains aligned with the C-12 spec and top-level plan. Drift: none. No real Spectre/OCEAN execution, C-7 adapter invocation, SSH, bridge, PSF parsing, formula rewriting, or deck commit occurred.
- C-12 Task 2 review evidence: spec-compliance review approved by Noether (`019e8d66-cfe1-73a2-9b12-a70c59305735`) with no findings. Code-quality review approved by Mill (`019e8d68-4d37-7ba0-98fa-4892078d7aed`) after stale C-12 overview wording was fixed. Task 2 is complete and reviewed; Task 3 remains blocked until the user explicitly confirms real Spectre/OCEAN adapter execution.
- C-12 Task 3 checkpoint: execution-agent/C-7 adapter invocation failed or was blocked for real_001. Returned artifacts/logs were preserved locally; Hermes failure checks and recovery assessment are pending.
- C-12 Task 3 route audit: user explicitly confirmed the real-tool adapter attempt with `进行Task 3`; Spectre/OCEAN were visible after sourcing `/home/zzchen/cadence_ic231_env.csh`; boundary evidence was written under `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice/08_execution_boundary.txt`; the adapter transcript was captured in `09_adapter_run.txt`; returned artifact hashes were captured in `real_001_returned_artifact_hashes.sha256`. The adapter wrote `result_manifest.json` with `status: failed`, `metric_result_manifest: null`, and `notes: spectre command failed`. `spectre.stdout` reports `SPECTRE-132`: the adapter's current `-log psf/spectre.out` argument is interpreted as a second input file by this Spectre invocation. Drift found and synchronized: the implementation plan now uses `csh -fc` instead of unsupported `csh -lc`, and future transcript commands should use pipefail so `tee` does not mask adapter exit status. No manual manifest repair, PSF parsing, formula rewriting, retry package preparation, Hermes check/record, additional adapter rerun, or deck/log commit occurred.
- C-12 Task 3 review evidence: spec-compliance review approved by Heisenberg (`019e8d87-de02-7a11-aa3f-cf7ab47895cb`) after stale resume prompts were fixed. Code-quality/evidence review approved by Pascal (`019e8d8d-707e-7052-b58e-1488b3fdd145`) after the current-state Task 4 confirmation gate and canonical Task 3 spec-review evidence were fixed. Both reviews reported no remaining Critical, Important, or Minor findings. Task 3 is complete and reviewed; do not enter Task 4 or rerun the adapter without user confirmation.
- C-12 Task 4 checkpoint: Hermes validation or recording failed for real_001. Recovery assessment was written locally and no unchecked result was recorded.
- C-12 Task 4 route audit: user confirmed doing lightweight C-12 Task 4 before the C-7 fix. Hermes `check-real-run` exited 0 and wrote `reports/real_run_check_report.json`; Hermes `check-metric-results` exited 1 with issues `simulator result is not succeeded`, `result manifest is missing metric_result_manifest`, and `metric result manifest is missing`; `record-real-result` was skipped; `assess-real-run-recovery` exited 0 and wrote `reports/real_run_recovery_report.json` with classification `tool_result_failed`, allowed actions `retry_same_candidate`, `abandon_candidate`, `stop_workflow`, recommended action `retry_same_candidate`, attempt number `1`, and retry budget remaining `1`. Local transcripts and hashes were written under `/tmp/ic_auto_opt_c12/evidence/2026-06-03-c12-controlled-real-tool-agent-practice`. Drift: none. No adapter rerun, real tool rerun, manual manifest repair, PSF parsing, formula rewriting, retry package preparation, or optimizer ledger/state row occurred.
- C-12 Task 4 review evidence: spec-compliance review approved by Euclid (`019e8da2-93d8-7b60-b406-cd1b2e136e3a`) with no findings. Code-quality/evidence review approved by Ramanujan (`019e8da5-684d-71d0-a48c-4624e76df34a`) after stale C-12 overview/checkpoint wording and the Task 4 commit pathspec were fixed; re-review found no Critical, Important, or Minor findings.
- Fast C-7 debug lane checkpoint: root cause for the C-12 Spectre SPECTRE-132 failure was C-7's `-log psf/spectre.out` argument; local Spectre requires `=log psf/spectre.out` for log-file-only output. Working tree patch and focused adapter test cover this. Follow-up real-tool issues are now scoped separately: full exported netlist sidecars, Spectre-safe unit formatting, and approved metric formulas matching the actual OCEAN result namespace. Debug details are in `docs/debug/2026-06-03-c7-real-tool-debug-lane.md`; raw `/tmp` evidence and `docs/toolchain_evidence/` remain uncommitted.
- C-7 closure plan checkpoint: `=log` command fix committed as `51fc057`. New focused plan: `docs/superpowers/plans/2026-06-03-c7-real-tool-closure-fixes.md`. It freezes new feature development and scopes only the remaining real-tool closure fixes: exported netlist sidecars, Spectre-safe unit formatting, metric namespace/formula contract, and a final authorized real closure smoke.
- C-7 closure Task 0 evidence inventory checkpoint: local bundle prepared at `/tmp/ic_auto_opt_real_tool_evidence/` with 777 hashed files and a file tree under `/tmp/ic_auto_opt_real_tool_evidence/manifests/`. Repo index added at `docs/debug/2026-06-03-real-tool-evidence-index.md`. The bundle includes inverter Spectre/OCEAN smoke evidence, mixer PSS/PAC OCEAN probe evidence, C-7 adapter debug contexts, and C-12 controlled real-tool practice evidence. Raw files remain local-only and must not be staged or committed. Current scope remains C-7 Real Tool Closure Fixes. next_allowed_action: start C-7 Real Tool Closure Fixes Task 1 exported netlist bundle sidecars; do not run real tools until sidecar/unit/formula contract fixes are complete and user authorizes the closure smoke.
- C-7 closure Task 1 checkpoint: complete, verified-only. Added tests for preserving exported netlist sidecars and rejecting symlinked exported bundle entries. `prepare-real-run` now copies safe regular files from `netlists/exported/` into the real run directory before writing the rendered `input.scs`, so relative sidecars such as `ade_e.scs`, hidden simulator files, and nested directories can travel with the prepared run package. Verification passed with focused real-run/next-run/recovery tests, C-7 adapter tests, ruff, and `git diff --check`. Current scope remains C-7 Real Tool Closure Fixes. next_allowed_action: start C-7 Real Tool Closure Fixes Task 2 Spectre-safe unit formatting guard; do not run real tools until sidecar/unit/formula contract fixes are complete and user authorizes the closure smoke.
- C-7 closure Task 2 checkpoint: complete, verified-only. Added validation coverage that rejects whitespace-separated unit suffixes such as `0.3 um` for `continuous_step` variables. Shipped template and test fixture variable ranges now use compact Spectre-safe suffixes such as `0.3u`, `3u`, and `0.2u`. Mock optimizer continuous candidate generation now preserves compact unit formatting, so prepared Spectre parameter assignments render as `WN=0.3u` instead of `WN=0.3 um`.
- C-7 real-tool closure checkpoint: complete, verified-only. Root cause was not formula text. Flattening the Maestro netlist bundle into `runs/real/<run_id>/` made OCEAN expose plain names; using ADE-style `runs/real/<run_id>/netlist/` as Spectre cwd with sibling `runs/real/<run_id>/psf/` restores slash names such as `/VOUT`, `/VDD`, and `/M0/S`. Code now prepares `runs/real/<run_id>/netlist/input.scs`, copies exported sidecars into that `netlist` directory, runs Spectre from it, and leaves approved OCEAN formulas unchanged. Real closure passed in `/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv`: adapter succeeded, `check-real-run` passed, `check-metric-results` passed, and `record-real-result` wrote ledger/state. Verification: `python3 -m pytest -q` passed 445 tests; `python3 -m ruff check .` passed. next_allowed_action: commit this C-7 closure fix with explicit pathspecs, then decide whether to rerun C-12 controlled real-tool practice from a clean project.
- C-7 closure commit checkpoint: committed as `d440c95 fix: preserve ADE netlist layout for real runs`.
- Optimizer practice-first planning checkpoint: created and corrected `docs/superpowers/plans/2026-06-03-optimizer-practice-first.md`. Current scope is `Optimizer Practice-First Plan`, status `verified-only`. The plan does not implement optimizer code. The clean `real_001` replay is only a foundation check; before Hermes optimizer development, the required practice is a real optimizer loop using `virtuoso-bridge-lite/skills/optimizer/SKILL.md` and local TuRBO at `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO`. For four variables, minimum practice budget is `n_init=8`, `max_evals=9`, `batch_size=1`.
- Optimizer Practice-First Task 1 checkpoint: complete, verified-only. Practice project `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv` was initialized from the known-good C-7 closure netlist bundle at `/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv/netlists/exported`. `hermes-workflow init`, `validate`, `package`, `prepare-netlist`, `dry-run`, `preflight-health`, `approve`, and `prepare-real-run --run-id real_001` all passed. Verified `runs/real/real_001/netlist/input.scs`, `netlist/ade_e.scs`, `netlist/amap/`, unchanged approved metric expressions, and `expected_psf_dir = runs/real/real_001/psf`. No Spectre, OCEAN, C-7 adapter, TuRBO, or optimizer loop was run. next_allowed_action: wait for user confirmation, then execute Optimizer Practice-First Task 2 only.
- Optimizer Practice-First Task 2 checkpoint: complete, verified-only. Initial replay on `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv` returned `rise/fall non_scalar` for `FN=2`, `WN=0.3u`, `FP=2`, `WP=0.3u`. Because the same OCEAN script, metric request, Maestro/ADE layout, and approved formulas produce scalars for other parameter points, this is candidate-level performance failure that optimizer practice must penalize, not OCEAN/formula/layout drift. A parameter point that cannot produce the required scalar metrics should be treated as not satisfying the performance target. Successful replay used `/tmp/ic_auto_opt_optimizer_practice/bridge_test_inv_baseline_001` with `FN=4`, `WN=0.6u`, `FP=4`, `WP=1.2u`. C-7 adapter, Spectre, OCEAN, `check-real-run`, `check-metric-results`, and `record-real-result` all passed. Metrics matched C-7 closure exactly: `rise=7.52016846017672e-11 s`, `fall=1.078998721053984e-10 s`, `DC=0.0002588877964196586 W`. One checked real row and `optimizer_state.current_evaluations = 1` were recorded. No Hermes code, OCEAN formula, adapter layout, or PSF parser change was made. Task 3 was completed later as the optimizer skill and TuRBO environment gate.
- Optimizer Practice-First Task 3 checkpoint: complete, verified-only. Read `virtuoso-bridge-lite/skills/optimizer/SKILL.md`; it confirms black-box optimization, TuRBO/scipy backend choices, `2 * n_params` initial sample guidance, minimization semantics, and finite failure penalties. Created project-local Linux `.venv`, installed CPU-only `torch=2.12.0+cpu`, `gpytorch=1.15.2`, `numpy=2.4.6`, and `scipy=1.17.1`, and ignored `.venv/` via `.gitignore`. `.venv/bin/python` imported local `Turbo1` from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/TuRBO`. No Hermes optimizer code, real tools, C-7 adapter run, PSF parser, formula rewrite, or broad framework asset was added. next_allowed_action: wait for user confirmation, then execute Optimizer Practice-First Task 4 only.
- Optimizer Practice-First Task 4 checkpoint: complete, verified-only. Temporary script `/tmp/ic_auto_opt_optimizer_practice/run_turbo_bridge_test_inv.py` ran local `Turbo1` with `PARAMS = ["FN", "WN", "FP", "WP"]`, approved bounds, `n_init=8`, `max_evals=9`, and `batch_size=1`. It evaluated 9 candidates through Hermes package/check/record contracts plus the C-7 Spectre/OCEAN adapter. All 9 evaluations produced OCEAN scalar metrics and finite objectives; 7 were `real_constraint_fail`, 2 were `real_pass`, and 0 used penalty. Best post-initial TuRBO candidate: `FN=12`, `WN=1.3u`, `FP=2`, `WP=2.5u`, objective `4.183168953894332e-14`.
- Optimizer Practice-First Task 5 checkpoint: complete, verified-only. Practice note `docs/debug/2026-06-03-optimizer-practice-first-result.md` chooses Productization Decision B: native optimizer passed but Hermes lacks explicit candidate injection; add that contract first. Smallest next scope is a narrow candidate-injection package contract so optimizer-selected parameters can become deterministic `runs/real/<run_id>/` packages without rewriting project-level variable ranges. next_allowed_action: wait for user confirmation, then write a narrow candidate-injection package contract design spec only.
- Candidate-injection package contract design checkpoint: complete, verified-only. Design spec `docs/superpowers/specs/2026-06-04-candidate-injection-package-contract-design.md` defines a narrow explicit candidate request contract and `prepare-candidate-real-run` package-preparation command. It does not add optimizer algorithms, replace C-4, replace C-9, run real tools, parse PSF, or rewrite OCEAN formulas. next_allowed_action: wait for user confirmation, then write the candidate-injection package contract implementation plan only.
- Candidate-injection package contract implementation plan checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-candidate-injection-package-contract.md` defines four tasks: candidate request validation, package writer reuse, CLI plus fake C-7 handoff smoke, and final verification/review gate. It does not authorize real tools, optimizer algorithm productization, PSF parsing, or OCEAN formula rewriting. next_allowed_action: wait for user confirmation, then execute Candidate-Injection Package Contract Task 1 only.
- Candidate-injection package contract Tasks 1-2 checkpoint: complete, verified-only. `src/hermes_workflow/real_run.py` now validates explicit candidate requests against `config/variables.yaml` and reuses the existing real-run package writer to prepare explicit candidate packages. `runs/real/<run_id>/candidate_request.json` is persisted as package evidence, `candidate_request_sha256` is recorded, duplicate ledger candidate ids/parameter tuples are rejected, and `config/variables.yaml` remains unchanged. Verification passed with focused candidate-injection tests, adjacent real-run/next-run tests, ruff, cadence check, and `git diff --check`.
- Candidate-injection package contract Task 3 checkpoint: complete, verified-only. `src/hermes_workflow/cli.py` now exposes `hermes-workflow prepare-candidate-real-run PROJECT_DIR --candidate-file PATH [--run-id real_###]`. `tests/test_candidate_injection_real_run.py` now covers CLI success/failure and a fake C-7 handoff smoke that preserves the explicit optimizer candidate id through `check_real_run`, `check_metric_results`, and `record_real_result`. Plan correction: the test uses local fake handoff writers rather than `tests.test_next_real_run` helper writers because the latter intentionally write `candidate_id = run_id`. Verification passed with focused candidate-injection tests, CLI tests, adjacent real-run/record/metric tests, and ruff. next_allowed_action: wait for user confirmation, then execute Candidate-Injection Package Contract Task 4 final verification and review gate only.
- Candidate-injection package contract Task 4 checkpoint: complete, reviewed. Final verification passed with candidate-injection tests (20 passed), targeted real-run/recovery/result/CLI regression (214 passed), ruff, cadence check, and `git diff --check`. Initial spec review found and the implementation fixed: existing override run-dir rejection, true prepared-package duplicate coverage, forced write-failure cleanup coverage, and compact continuous-value validation. Spec re-review by Ptolemy passed with no findings; code-quality re-review by Linnaeus passed with no findings. Candidate-Injection Package Contract is now complete/reviewed. next_allowed_action: wait for user confirmation, then decide the next narrow Hermes optimizer productization scope; do not start broad optimizer framework work.
- C-13 Single-Candidate Optimizer Suggestion MVP checkpoint: design spec complete, verified-only. Design spec `docs/superpowers/specs/2026-06-04-single-candidate-optimizer-suggestion-design.md` scopes only the missing `ledger/state -> one candidate_request.json -> existing prepare-candidate-real-run` productization step. It does not authorize broad optimizer framework work, real-tool execution, batch orchestration, PSF parsing, OCEAN formula rewriting, or native layout replacement. next_allowed_action: write the narrow C-13 implementation plan for single-candidate optimizer suggestion; do not start C-13 code until that plan exists.
- C-13 Single-Candidate Optimizer Suggestion MVP implementation plan checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-single-candidate-optimizer-suggestion.md` defines four narrow tasks: library writer with initialization fallback, TuRBO one-step suggestion and safety failures, CLI/fake handoff smoke, and final verification/review gate. It keeps real-tool acceptance in C-14 and does not authorize Virtuoso/Spectre/OCEAN/SSH/bridge execution, broad optimizer framework work, PSF parsing, OCEAN formula rewriting, or layout replacement. next_allowed_action: execute C-13 Task 1: Library Writer With Initialization Fallback; do not start Task 2 or real-tool acceptance until Task 1 is complete and recorded.
- C-13 Single-Candidate Optimizer Suggestion MVP Tasks 1-3 checkpoint: complete, verified-only. Added `src/hermes_workflow/optimizer_suggestion.py`, `hermes-workflow suggest-candidate`, and `tests/test_optimizer_suggestion.py`. The command writes one candidate request JSON from checked ledger/state, supports initialization fallback, optionally uses a one-step TuRBO suggestion when enough finite observations exist and imports are available, preserves candidate-injection handoff compatibility, and does not write real-run packages. Verification passed with focused optimizer suggestion tests, candidate-injection/next-run regression, CLI regression, targeted real-run/result regression, and ruff. next_allowed_action: execute C-13 Task 4 final verification/review gate; do not enter C-14 real-tool acceptance until Task 4 is complete and recorded.
- C-13 Single-Candidate Optimizer Suggestion MVP Task 4 checkpoint: complete, reviewed. Final verification passed with optimizer suggestion plus candidate-injection tests (33 passed), targeted real-run/recovery/result/CLI regression (186 passed), ruff, cadence check, and `git diff --check`. Initial spec review found and the implementation fixed race-unsafe overwrite rejection. Initial code-quality review found and the implementation fixed race-safe no-clobber writing, generated payload validation before write, and temp cleanup on write/close failures. Spec re-review by Hypatia passed with no findings. Code-quality re-review by Nash passed with no Critical or Important findings, and the only Minor stale plan snippet was fixed. C-13 is now complete/reviewed. next_allowed_action: write C-14 real-tool acceptance plan for `suggest-candidate -> prepare-candidate-real-run -> C-7 adapter -> check/record`; do not run real tools until that plan exists and the user confirms.
- C-14 Real-Tool Acceptance plan checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-real-tool-acceptance.md` defines the first real acceptance flow for the reviewed C-13 suggestion command: prepare a clean local project, seed known-good `real_001`, run `suggest-candidate` for `candidate_000002`, prepare `real_002`, run the C-7 Spectre/OCEAN adapter, then check/record or classify through existing Hermes contracts. It does not add broad optimizer framework work, new algorithms, batch orchestration, PSF parsing, formula rewriting, or layout replacement. next_allowed_action: execute C-14 Task 1 clean acceptance workspace and seed package; do not run real tools until Task 2 is explicitly confirmed.
- C-14 Real-Tool Acceptance Task 1 checkpoint: complete, verified-only. Local project `/tmp/ic_auto_opt_c14/bridge_test_inv` was prepared from the known-good exported netlist bundle, local acceptance-only lower bounds were set to the proven scalar seed, Hermes preflight/approval passed, and `prepare-real-run --run-id real_001` prepared the first-run seed package. Initial plan drift was corrected: `prepare-candidate-real-run` must not target `real_001`; candidate injection starts at `real_002+` after a checked ledger row exists. next_allowed_action: wait for user confirmation, then execute C-14 Task 2 seed real-tool run.
- C-14 Real-Tool Acceptance Task 2 checkpoint: complete, verified-only. Seed `real_001` ran through the existing C-7 Spectre/OCEAN adapter outside the Codex sandbox, produced result and metric manifests, passed `check-real-run`, `check-metric-results`, and `record-real-result`, and recorded one ledger row with `optimizer_state.current_evaluations = 1`. First sandboxed adapter attempt failed before OCEAN with Spectre pipe/socket permission errors; comparison against C-7 closure showed no adapter command, formula, or native-layout drift. Metrics returned by OCEAN: `rise=7.52016846017672e-11 s`, `fall=1.078998721053984e-10 s`, `DC=0.0002588877964196586 W`. The ledger row status is `real_constraint_fail`, so scalar extraction worked but this seed did not satisfy configured performance constraints. next_allowed_action: wait for user confirmation, then execute C-14 Task 3 suggest and package `real_002`.
- C-14 Real-Tool Acceptance Tasks 3-5 checkpoint: complete, verified-only. `suggest-candidate` wrote `candidate_000002` with selection mode `initialization_fallback`; `prepare-candidate-real-run` prepared `real_002`; the C-7 adapter ran `real_002` through real Spectre/OCEAN outside the sandbox; `check-real-run`, `check-metric-results`, and `record-real-result` all passed. OCEAN metrics for `real_002`: `rise=3.326181720494057e-11 s`, `fall=4.973593602698243e-11 s`, `DC=0.0009838038264352862 W`. Ledger now has 2 rows, both with scalar metrics and `real_constraint_fail`. Sanitized closeout is `docs/debug/2026-06-04-c14-real-tool-acceptance-result.md`. Decision: proceed to narrow optimizer loop productization.
- C-15 Narrow Optimizer Loop Productization Tasks 1-3 checkpoint: complete, verified-only; final review gate pending. Added `src/hermes_workflow/optimizer_loop.py`, `tools/run_real_optimizer_loop.py`, and `tests/test_optimizer_loop.py`. The loop productizes only the proven C-14 path with one candidate per cycle and fixed budget. Fake-adapter tests passed, and one real loop cycle ran on `/tmp/ic_auto_opt_c14/bridge_test_inv`: `candidate_000003`/`real_003` passed C-7 adapter, Hermes checks, and recording. OCEAN metrics: `rise=6.508914194299693e-11 s`, `fall=6.17648525412794e-11 s`, `DC=0.0003515194271758733 W`. Ledger now has 3 rows; `candidate_000003` is `real_pass` and current best. next_allowed_action: run C-15 Task 4 final verification, review gate, and closeout before broader optimizer work.
- C-15 Narrow Optimizer Loop Productization Task 4 checkpoint: complete, reviewed. Final verification passed with focused C-15 tests (9 passed), adjacent optimizer/candidate/result/metric contract regressions (102 passed), ruff, cadence checker, and `git diff --check`. Local spec review by Ohm and local code-quality review by Jason passed; their Important notes were fixed by adding direct `result_check_failed` and `record_failed` tests, bounding adapter stdout/stderr issues in `optimizer_loop_report.json`, and using the shared `RECORDED` constant. Narrow re-review by both local reviewers passed with no remaining blockers. C-15 remains a narrow fixed-budget loop around existing contracts and the proven C-7 adapter path; no broad optimizer framework, daemon, scheduler, PSF parser, formula rewrite, or native-layout replacement was added. next_allowed_action: wait for user confirmation, then choose the next narrow real-practice-backed optimizer productization step.
- C-16 100-Point Real Optimizer Acceptance Task 0 checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-100-point-real-optimizer-acceptance.md` scopes the next meaningful optimizer validation as a 100-point real run, not another small-point smoke. User clarified that Spectre `+mt` is per-process thread count while `spectre.parallel_jobs` is maximum simultaneous Spectre process count. Task 0 aligns settings before the 100-point run: request/prepared manifests carry and cross-check `threads_per_run` as per-process `+mt` and `parallel_jobs` as a concurrency cap, C-7 argv uses requested `preset/threads_per_run/output_format`, generated result manifests record simulator `preset/threads_per_run/output_format/timeout_s`, and `check-real-run` detects simulator setting drift. Current intended settings are `+preset=ax`, `+mt=10`, `output_format=psfxl`, and `parallel_jobs=10`; `parallel_jobs` is not mapped to Spectre `+mt`. Final verification passed with 492 tests, ruff, cadence checker, and `git diff --check`. next_allowed_action: wait for user confirmation, then start C-16 Task 1 100-point sequential real optimizer run.
- C-16 100-Point Real Optimizer Acceptance Tasks 1-2 checkpoint: complete with follow-up required. `/tmp/ic_auto_opt_c14/bridge_test_inv` reached 100 recorded real Spectre/OCEAN evaluations: `8 real_pass`, `92 real_constraint_fail`, no recorded tool failures, no recorded metric failures. Environment blocker found and corrected: system `python3` had Hermes dependencies but lacked `torch/gpytorch`; project `.venv` had `torch/gpytorch` but lacked Hermes dependencies. Installing the project into `.venv` allowed `.venv` to run Hermes + TuRBO. `real_057` onward mostly used `selection_mode=turbo`, but `real_092` and `real_094` still silently fell back to `initialization_fallback`, so C-16 is not a clean optimizer acceptance. Spectre/OCEAN contracts passed for `real_004` through `real_100`; settings stayed `+preset=ax`, `+mt=10`, `output_format=psfxl`, `parallel_jobs=10`. next_allowed_action: narrow TuRBO suggestion robustness fix; do not run another broad 100-point acceptance until silent fallback is fixed or classified.
- C-16 corrected optimizer-skill practice checkpoint: complete, verified-only. The previous one-candidate C-15/C-16 loop is not accepted as a valid optimizer proof. A corrected `/tmp` practice used native `Turbo1.optimize()` with the proven Hermes + Spectre/OCEAN evaluator path for 100 evaluations: 8 initialization evaluations, 92 TuRBO trust-region evaluations, 73 recorded real Spectre/OCEAN scalar evaluations, 24 duplicate quantized candidates skipped, and 3 metric non-scalar candidates converted to finite penalties. Best candidate was `real_011`: `FN=11`, `WN=1.9u`, `FP=9`, `WP=0.5u`, `rise=72.489655ps`, `fall=64.569947ps`, `DC=301.334349uW`, objective `4.1300765965648685e-14`. Sanitized archive: `docs/debug/2026-06-04-optimizer-skill-real-flow-practice.md`.
- C-17 Native TuRBO Optimizer Runner MVP design spec exists: `docs/superpowers/specs/2026-06-04-native-turbo-optimizer-runner-mvp-design.md`.
- C-17 implementation plan exists: `docs/superpowers/plans/2026-06-04-native-turbo-optimizer-runner-mvp.md`.
- C-17 Task 1 checkpoint: complete, verified-only. Added `src/hermes_workflow/native_turbo.py` and `tests/test_native_turbo.py` for contract loading, approved-variable quantization, compact unit formatting, feasibility-first objective scoring, and compact evaluation trace modeling. Verification passed with focused native/optimizer/mock tests and focused ruff. No real tools, PSF parsing, formula rewrite, broad optimizer framework, or raw Cadence artifact commit occurred.
- C-17 Tasks 2-6 checkpoint: complete, verified-only. Added duplicate-aware native `Turbo1.optimize()` runner behavior, bounded quantized-candidate replacement, real evaluator bridge through existing Hermes package/check/recovery/record contracts, `hermes-workflow run-native-turbo`, compact report/JSONL trace writing, repeated workflow-level failure stop guard, and `.gitignore` protection for local raw evidence paths. Real acceptance on `/tmp/ic_auto_opt_c17_native_turbo_002/bridge_test_inv` completed 100 evaluations: 8 initialization, 92 trust-region, 45 feasible, 43 constraint failed, 12 metric check failed. Best candidate was `real_030` with `FN=12`, `FP=2`, `WN=1.7u`, `WP=2.7u`, `rise=6.72081749122453e-11`, `fall=6.190153048273253e-11`, `DC=0.0003265612598325413`. Spectre settings stayed `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, and `output_format=psfxl` across all 100 prepared manifests. Sanitized archive: `docs/debug/2026-06-04-native-turbo-runner-real-acceptance.md`.
- C-18 Batch Native TuRBO Parallel Runner design checkpoint: complete, verified-only. Spec `docs/superpowers/specs/2026-06-04-batch-native-turbo-parallel-runner-design.md` scopes the next useful optimizer step: keep native `Turbo1.optimize()`, add a batch-aware Hermes evaluator, run Spectre/OCEAN workers concurrently up to `spectre.parallel_jobs`, keep each Spectre process on `spectre.threads_per_run` as `+mt`, and keep package preparation plus ledger/state recording sequential. The design explicitly notes that local TuRBO currently selects a batch but evaluates `self.f(x)` sequentially, so implementation must not assume `batch_size=10` alone creates real parallelism.
- C-18 Batch Native TuRBO Parallel Runner implementation plan checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-batch-native-turbo-parallel-runner.md` scopes six narrow tasks: batch runner seam and trace metadata, local batch-aware `Turbo1` wrapper, bounded parallel real evaluator, `run-native-turbo --parallel` CLI/report wiring, one user-confirmed real acceptance with `max_evals=100`, `batch_size=10`, `parallel_jobs=10`, and `threads_per_run=10`, then final verification/review/commit. The plan keeps package preparation and ledger/state recording sequential, only parallelizes Spectre/OCEAN adapter workers, and does not authorize broad scheduler/framework work.
- C-18 Batch Native TuRBO Parallel Runner completion checkpoint: complete, verified-only. Added `run-native-turbo --parallel`, batch report summary fields, bounded parallel real batch evaluation, and a sanitized real acceptance note at `docs/debug/2026-06-04-batch-native-turbo-parallel-acceptance.md`. Real acceptance on `/tmp/ic_auto_opt_c18_batch_native_turbo_001/bridge_test_inv` completed 100 evaluations: 36 feasible, 50 constraint failed, 14 metric check failed, 16 initialization, 84 TuRBO trust-region, 11 batches, and max worker metadata 10. Best candidate was `real_018` with `FN=12`, `FP=10`, `WN=1.7u`, `WP=0.5u`, `rise=6.608725022174673e-11`, `fall=6.129060537337709e-11`, `DC=0.0003329717286877405`. Spectre settings stayed `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, and `output_format=psfxl` across all 100 prepared manifests. Full verification passed with `python3 -m pytest -q` (513 passed, 1 skipped) and `python3 -m ruff check .`.
- C-19 Execution-Agent Optimizer Practice Acceptance plan checkpoint: complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-execution-agent-optimizer-practice-acceptance.md` scopes the next real-use validation around the original supervisor-agent to execution-agent handoff goal. It uses the existing C-18 `run-native-turbo --parallel` path, not a new optimizer framework. The execution agent receives a task packet, preserves native Maestro/ADE netlist layout, runs one real 100-evaluation optimizer command after user confirmation, and returns reports/evidence for supervisor/Hermes audit.
- C-19 Task 1 checkpoint: complete, verified-only. Local-only execution-agent task packet was written to `/tmp/ic_auto_opt_c19/evidence/execution_agent_optimizer_acceptance_001/EXECUTION_AGENT_TASK.md`. Clean practice project `/tmp/ic_auto_opt_c19/bridge_test_inv` was copied from the accepted C-18 project, preserving `netlists/exported/input.scs`, `ade_e.scs`, and `amap/`, while removing old `runs/`, `reports/`, `state/`, and `data/` outputs. No real tools were run.
- C-19 Task 2 checkpoint: complete with blocker evidence, verified-only. User confirmed real-tool execution and `run-native-turbo --parallel --max-evals 100` was run once against `/tmp/ic_auto_opt_c19/bridge_test_inv`. It exited before real Spectre/OCEAN execution with stdout `optimizer state is missing`, empty stderr, and no summary/trace/state/ledger output files.
- C-19 Task 3 checkpoint: complete, verified-only. Sanitized audit note `docs/debug/2026-06-04-c19-execution-agent-optimizer-acceptance.md` classifies the blocker as clean-project state inconsistency: Task 1 deleted `state/optimizer_state.json` but retained stale `ledger/experiment_ledger.jsonl` rows from C-18. `prepare_explicit_candidate_real_run()` requires optimizer state when ledger rows exist, so the run failed before the physical tool boundary. Smallest next action is C-19 Task 4 Branch B: clean stale optimizer ledger rows or initialize matching empty state, then rerun once.
- C-19 Task 4 checkpoint: complete, verified-only. Branch B fixed clean project preparation by removing stale `ledger/experiment_ledger.jsonl` rows and fixed native TuRBO quantization so off-grid continuous-step upper bounds clamp to the last approved grid step. A sandboxed rerun was rejected as invalid evidence because Spectre failed with pipe/socket permission errors. A clean non-sandbox rerun completed 100 real evaluations through `run-native-turbo --parallel`: `33 feasible`, `46 constraint_failed`, `21 metric_check_failed`; 100 result manifests succeeded; 79 metric manifests succeeded and 21 failed as candidate-level metric failures; max worker metadata was 10; settings audit passed with `preset=ax`, `threads_per_run=10`, `output_format=psfxl`, and trace `parallel_jobs=10`. Best accepted candidate was `real_041`, `FN=8`, `WN=2.3u`, `FP=9`, `WP=0.5u`, objective `4.169592842385839e-14`.
- C-20 checkpoint: complete, verified-only. Fresh local worker subagents validated the autonomous execution-agent handoff. Attempt 1 proved the original packet was too weak because a sandboxed command exited 0 while all 100 result manifests failed. The packet was corrected to require non-sandbox execution and manifest-level audit. Attempt 2 completed 100 optimizer evaluations with 100 result manifests succeeded, 100 metric manifests produced, 80 metric manifests succeeded, and 20 metric manifests failed. Status counts were `31 feasible`, `49 constraint_failed`, and `20 metric_check_failed`; settings audit passed with `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, and `output_format=psfxl`. The worker correctly reported the residual blocker: `real_057` and `real_075` had OCEAN command/license failures. Autonomous handoff behavior is accepted; fully green real-tool acceptance needs OCEAN-only retry/concurrency handling.
- C-21 OCEAN retry checkpoint: complete, verified-only, committed in the current HEAD. Added OCEAN-only retry to the C-7 Spectre/OCEAN adapter and manifest/checker support for `ocean.attempts` plus `ocean.return_codes`. Permanent OCEAN command failures still fail closed, while transient OCEAN command failures can retry without rerunning Spectre. Real rerun on `/tmp/ic_auto_opt_c21/bridge_test_inv` completed 100 evaluations with 100 result manifests succeeded, 100 metric manifests produced, 86 metric manifests succeeded, 14 candidate-level non-scalar metric failures, and 0 final OCEAN command/license failures. Settings stayed `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, and `output_format=psfxl`.
- C-22 Execution-Agent Task Package Alignment checkpoint: Task 1 complete, verified-only, committed in the current HEAD. Generated `execution_package/EXECUTION_TASK.md` now uses generic execution-agent wording instead of Claude-specific wording and carries the C-20 manifest-level audit rule that command exit status alone is not acceptance evidence. No real-tool command, optimizer logic, new handoff framework, PSF parsing, or OCEAN formula change was added.
- current_scope: C-22 Execution-Agent Task Package Alignment.
- next_allowed_action: wait for user confirmation before choosing the next narrow real-practice-backed optimizer or execution-agent validation step.

- C-23 Optimizer Execution-Agent Task Packet MVP checkpoint: complete, verified-only, committed in the current HEAD. Hermes now generates `execution_package/OPTIMIZER_EXECUTION_TASK.md` and `execution_package/optimizer_execution_manifest.json` for the proven `run-native-turbo --parallel` optimizer handoff path. The generated packet includes manifest-level audit requirements, Spectre settings expectations, native runner returned artifact names, and forbidden-action language for hand-picked points, PSF parsing, and OCEAN formula rewriting.
- C-23 post-sync local review fix: generated optimizer task packet commands now use absolute project/cadence paths and shell-safe command rendering, so a worker agent can run the copied command from a different cwd.
- current_scope: C-23 Optimizer Execution-Agent Task Packet MVP complete.
- next_allowed_action: wait for user confirmation, then run one local worker-agent handoff using the generated optimizer task packet.

- C-24 Generated Optimizer Task Packet Handoff Acceptance checkpoint: implementation plan complete, verified-only. Plan `docs/superpowers/plans/2026-06-04-generated-optimizer-task-packet-handoff-acceptance.md` scopes one generated C-23 task-packet handoff to a local worker agent and supervisor/Hermes manifest-level audit. Task 1 is workspace and packet generation only; Task 2 is the first real worker-agent execution step.
- C-24 Generated Optimizer Task Packet Handoff Acceptance completion: complete, verified-only. Task 1 generated the packet. The first Task 2 worker attempt was rejected because sandboxed Spectre failed before OCEAN with pipe/socket permission errors. Task 2R reran the same generated-packet semantics through the approved non-sandbox Cadence path and completed 100 evaluations: 36 feasible, 43 constraint_failed, 21 metric_check_failed; 100 result manifests succeeded; 100 metric manifests were produced; 79 metric manifests succeeded; settings audit passed with preset=ax, threads_per_run=10, parallel_jobs=10, output_format=psfxl. Sanitized audit: `docs/debug/2026-06-04-c24-generated-task-packet-handoff.md`.
- current_scope: C-24 Generated Optimizer Task Packet Handoff Acceptance complete.
- next_allowed_action: wait for user confirmation, then choose the next narrow practice-backed productization or acceptance step; do not start a broad optimizer framework.

- C-25 Optimizer Run Acceptance Audit planning: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-04-optimizer-run-acceptance-audit-design.md` and implementation plan `docs/superpowers/plans/2026-06-04-optimizer-run-acceptance-audit.md`.
- C-25 scope: productize the C-24 manual supervisor/Hermes manifest-level audit into `hermes-workflow check-optimizer-run PROJECT_DIR`, which reads existing native TuRBO report/trace/result/metric manifests and writes `reports/optimizer_run_acceptance_report.json`.
- C-25 boundary: no real tools, no optimizer algorithm changes, no broad framework, no PSF parsing, no OCEAN formula rewriting, and no native Maestro/ADE layout replacement.
- current_scope: C-25 Optimizer Run Acceptance Audit.
- next_allowed_action: execute C-25 Task 1 library acceptance report only; do not run real tools or start broad optimizer framework work.

- C-25 Optimizer Run Acceptance Audit completion: complete, verified-only.
- Added `src/hermes_workflow/optimizer_acceptance.py`, `tests/test_optimizer_acceptance.py`, and `hermes-workflow check-optimizer-run PROJECT_DIR`.
- The command reads existing native TuRBO report/trace/result/metric manifests and writes `reports/optimizer_run_acceptance_report.json`.
- Local C-24 retry shape smoke passed on `/tmp/ic_auto_opt_c24_retry/bridge_test_inv` with `optimizer run accepted`.
- Verification passed: `python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py tests/test_native_turbo.py -q`, `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.
- current_scope: C-25 Optimizer Run Acceptance Audit complete.
- next_allowed_action: wait for user confirmation before choosing the next narrow practice-backed step; do not start broad optimizer framework work.

- C-26 Optimizer Completion And Continuation Decision Report design: complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-05-optimizer-completion-continuation-decision-design.md`.
- Scope: read an already accepted optimizer run and write `reports/optimizer_completion_report.json` with best observed candidate, status distribution, search-space estimate, improvement evidence, and a deterministic continuation decision.
- Boundary: no real tools, optimizer algorithm change, broad framework, PSF parsing, OCEAN formula rewriting, metric/constraint changes, or native-layout replacement.
- current_scope: C-26 Optimizer Completion And Continuation Decision Report.
- next_allowed_action: review C-26 design spec, then write C-26 implementation plan only after user confirmation; do not implement code, run real tools, or start broad optimizer framework work.
- C-26 Optimizer Completion And Continuation Decision Report implementation: complete, verified-only, committed at `ca1c9c1`.
- Added `src/hermes_workflow/optimizer_completion.py`, `tests/test_optimizer_completion.py`, and CLI `hermes-workflow summarize-optimizer-run PROJECT_DIR`.
- The command reads existing accepted optimizer artifacts and writes `reports/optimizer_completion_report.json`.
- Report output includes best observed candidate, optimizer status counts, finite search-space estimate, evaluated fraction, full-coverage/global-optimum claim flag, best-so-far improvement evidence, and deterministic supervisor decision.
- First-version decisions are intentionally narrow: `accept_best_observed`, `continue_more_evals`, `switch_to_exhaustive_sweep`, and `stop_for_user_review`.
- Focused verification passed: `python3 -m pytest tests/test_optimizer_completion.py -q`; `python3 -m ruff check src/hermes_workflow/optimizer_completion.py src/hermes_workflow/cli.py tests/test_optimizer_completion.py`.
- Final verification passed before commit: `python3 -m pytest tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py tests/test_native_turbo.py -q`; `python3 -m ruff check src tests tools`; `python3 tools/check_development_cadence.py`; `git diff --check`.
- current_scope: OpenBox Optimizer Backend Decision Checkpoint.
- next_allowed_action: discuss whether to write C-27 OpenBox Optimizer Backend Evidence Spike design spec; do not replace TuRBO or run real tools before that decision.
- OpenBox Optimizer Backend Decision Checkpoint: written, verified-only. Decision document: `docs/OPENBOX_OPTIMIZER_BACKEND_DECISION_CHECKPOINT_2026-06-05.md`. Local OpenBox reference clone: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box`, commit `2ab34cc`. The project is paused before C-27 to decide whether OpenBox should replace or coexist with the current TuRBO backend. No production replacement has been made.

- OpenBox Backend Evidence Spike: complete, verified-only. Evidence note: `docs/debug/2026-06-05-openbox-backend-evidence-spike.md`. Local-only fake inverter probes ran in `/tmp/ic_auto_opt_openbox_spike/.venv`; no production code, real tools, execution agents, PSF parsing, or OCEAN formula rewrite occurred. Single ask-and-tell probe produced 40 candidates with 0 grid issues and 0 duplicates; batch ask-and-tell produced 10 batches of 4 with 0 grid issues and 0 duplicates. Constraints were recorded in history. Current decision: OpenBox is viable enough for a narrow C-27 backend seam MVP discussion, but TuRBO remains the implemented backend.

- C-27 OpenBox Backend Seam MVP: implementation complete, verified-only. Added backend-neutral optimizer artifact loading, fake OpenBox artifact generation, C-25/C-26 compatibility, and `hermes-workflow run-openbox-fake`. Full local regression passed with `544 passed, 1 skipped`; targeted C-27 `ruff` passed. OpenBox import smoke was skipped because `openbox` is not installed. No real tools, execution agents, TuRBO replacement, PSF parsing, or OCEAN formula rewrite occurred. next_allowed_action: wait for user decision on the next narrow OpenBox step.

- C-28 OpenBox Real Backend Acceptance Spike: design spec and implementation plan written, verified-only. Scope is one narrow local-only real-tool evidence spike to decide whether OpenBox should be productized. It preserves the current Spectre/OCEAN execution path and C-25/C-26 audit flow. next_allowed_action: execute C-28 Task 1 Environment And Known-Good Project Gate; real OpenBox/Spectre/OCEAN execution is not allowed until Task 2 is explicitly confirmed.

- C-28 OpenBox Real Backend Acceptance Spike completion: complete, verified-only. Sanitized evidence note: `docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md`. Local-only runner `/tmp/ic_auto_opt_c28_openbox_real/run_openbox_real_spike.py` used OpenBox ask-and-tell to generate 100 candidates, then evaluated them through the existing Hermes Spectre/OCEAN path under `/tmp/ic_auto_opt_c28_openbox_real/bridge_test_inv`. Results: 43 feasible, 51 constraint_failed, 6 metric_check_failed, 0 real_check_failed, 0 duplicate replacements. C-25 accepted all 100 result manifests and 100 metric manifests with stable `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`, `output_format=psfxl`. C-26 decision: `accept_best_observed`, confidence `medium`, `global_optimum_claim=false`. Best observed: `real_071`, `FN=12`, `WN=2.7u`, `FP=7`, `WP=0.7u`, objective `4.1325534822170306e-14`. Productization blockers discovered and worked around locally: OpenBox stepped continuous variables need Hermes effective grid upper bounds, and the local real project bundle must include `netlists/templates/template.scs`. next_allowed_action: write C-29 OpenBox productization plan; do not replace TuRBO or broaden optimizer framework work without a narrow approved plan.

- C-29 OpenBox Production Backend planning: design spec and implementation plan written, verified-only. Design spec: `docs/superpowers/specs/2026-06-05-openbox-production-backend-design.md`. Implementation plan: `docs/superpowers/plans/2026-06-05-openbox-production-backend.md`. Scope: productize OpenBox candidate generation and ask-and-tell observation updates while preserving the existing Hermes candidate package, Spectre/OCEAN execution adapter, backend-neutral optimizer artifacts, C-25 acceptance, and C-26 completion decision. Boundaries: no TuRBO replacement, no hidden `FN=FP`, no broad optimizer framework, no PSF parsing, no OCEAN formula rewrite. next_allowed_action: execute C-29 Task 1 OpenBox Search Space Contract; do not run real tools, replace TuRBO, delete native_turbo, add hidden FN=FP coupling, or broaden the optimizer framework.

- C-29 OpenBox Production Backend completion: complete, verified-only. Productized OpenBox ask-and-tell candidate generation while preserving the existing Spectre/OCEAN execution path, candidate package, ledger recording, C-25 acceptance, and C-26 completion reports. Added `hermes-workflow run-openbox-real`, effective stepped-grid upper handling (`0.3u..3u step 0.2u` -> OpenBox upper `2.9`), and removed hidden `FN=FP` fallback behavior from OpenBox suggestions. Real acceptance on `/tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv` completed 100 evaluations: 43 feasible, 51 constraint_failed, 6 metric_check_failed, 0 real_check_failed, 0 duplicate replacements, 100 unique parameter sets. C-25 accepted the run; C-26 decision was `accept_best_observed`, confidence `medium`, `global_optimum_claim=false`. Sanitized evidence: `docs/debug/2026-06-05-openbox-production-backend-real-acceptance.md`. current_scope: C-29 OpenBox Production Backend complete. next_allowed_action: wait for user confirmation, then choose the next narrow post-C-29 step; recommended next is C-30 OpenBox execution-agent task packet/dependency handoff, not TuRBO deletion or broad optimizer framework work.

- C-30 OpenBox Execution-Agent Task Packet completion: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-05-openbox-execution-agent-task-packet-design.md` and implementation plan `docs/superpowers/plans/2026-06-05-openbox-execution-agent-task-packet.md`. Scope is strictly package rendering and CLI handoff: native TuRBO remains default, while `package-optimizer-task --backend openbox` renders `run-openbox-real`, OpenBox dependency-blocker wording, no-silent-fallback wording, backend-neutral required artifacts, and post-run `check-optimizer-run` / `summarize-optimizer-run` commands. No real tools or optimizer algorithm changes are part of C-30. Verification passed: `python3 -m pytest -q` (`551 passed, 1 skipped`), `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.
- current_scope: C-30 OpenBox Execution-Agent Task Packet complete.

- C-31 Optimizer Post-Run Visualization And Insight Report completion: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-05-optimizer-post-run-visualization-insight-design.md` and implementation plan `docs/superpowers/plans/2026-06-05-optimizer-post-run-visualization-insight.md`. Added `src/hermes_workflow/optimizer_insights.py` and CLI `hermes-workflow visualize-optimizer-run PROJECT_DIR`. The command reads existing optimizer artifacts and writes `reports/optimizer_insight_report.json`, `reports/optimizer_insight_report.md`, `reports/optimizer_visuals/convergence.svg`, `reports/optimizer_visuals/status_distribution.svg`, and `reports/optimizer_visuals/parameter_objective_scatter.svg`. C-31 uses standard-library SVG only and reports observed correlations without causal/global-optimum claims. Advanced OpenBox SHAP/surrogate HTML remains an optional future add-on. Focused verification passed for optimizer insights, completion, acceptance, task package, and targeted ruff.
- current_scope: C-31 Optimizer Post-Run Visualization And Insight Report complete.

- C-32 Optimizer Finalize Workflow completion: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-05-optimizer-finalize-workflow-design.md` and implementation plan `docs/superpowers/plans/2026-06-05-optimizer-finalize-workflow.md`. Added `src/hermes_workflow/optimizer_finalize.py` and CLI `hermes-workflow finalize-optimizer-run PROJECT_DIR`. The command runs acceptance, completion summary, and insight report generation in order, then writes `reports/optimizer_finalize_report.json`. It fails closed if acceptance rejects or completion fails, and does not run real tools or modify optimizer behavior. Focused verification passed for finalize, insights, completion, acceptance, and targeted ruff.
- current_scope: C-32 Optimizer Finalize Workflow complete.

- C-33 Optimizer Production Handoff Guide completion: complete, verified-only. Added `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md`, a concise supervisor/execution-agent usage guide covering backend choice, task packet generation, execution-agent responsibilities, returned artifacts, `finalize-optimizer-run` acceptance, failure categories, and forbidden actions. No code, real-tool, backend, PSF, or OCEAN formula behavior changed.
- current_scope: C-33 Optimizer Production Handoff Guide complete.

- C-34 Production Optimizer Handoff Acceptance Task 1: complete, verified-only. Added `docs/superpowers/plans/2026-06-05-production-optimizer-handoff-acceptance.md` and generated the OpenBox production handoff task packet for `/tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv`. Local evidence is under `/tmp/ic_auto_opt_c34/`; no real Cadence command was run. The next step requires explicit user approval for C-34 Task 2 real execution.
- current_scope: C-34 Production Optimizer Handoff Acceptance Task 1 complete.

- C-34 Production Optimizer Handoff Acceptance Task 2: complete, verified-only. The initial OpenBox dependency blocker was resolved by using the existing OpenBox venv and installing Hermes workflow tooling editable into it. A clean approved workspace was rebuilt at `/tmp/ic_auto_opt_c34_clean2/bridge_test_inv` with config, netlists, standard execution manifest, optimizer task packet, and matching supervisor instruction. Real OpenBox handoff completed 100 evaluations: 43 feasible, 51 constraint_failed, 6 metric_check_failed, 0 real_check_failed. `finalize-optimizer-run` passed with best observed `real_071`. Sanitized note: `docs/debug/2026-06-05-c34-production-openbox-handoff-success.md`.
- current_scope: C-34 Production Optimizer Handoff Acceptance complete.

- C-35 Toolchain Execution Reference: complete, verified-only. Added `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` and updated `AGENTS.md` so future real-tool work starts from the proven C-34 environment and execution path: project `.venv` for normal Hermes/test commands, `/tmp/ic_auto_opt_openbox_spike/.venv` for OpenBox real execution, Cadence cshrc `/home/zzchen/cadence_ic231_env.csh`, non-sandbox/escalated real-tool command rule, clean workspace package sequence, and `finalize-optimizer-run` closeout. Fake-run guidance is now stricter: at most one focused fake/local smoke per new command path before the smallest meaningful real practice flow.
- current_scope: C-35 Toolchain Execution Reference complete.

- C-36 Stable OpenBox/Hermes Execution Environment Gate: complete, verified-only. Added `hermes-workflow check-toolchain-env`, backed by `src/hermes_workflow/toolchain_env.py` and `tests/test_toolchain_env.py`. The gate checks OpenBox execution venv existence, venv Python, venv `hermes-workflow`, Cadence cshrc, and same-Python imports of `openbox` plus `hermes_workflow.openbox_backend`. Current C-34 venv `/tmp/ic_auto_opt_openbox_spike/.venv` passed and wrote `/tmp/toolchain_environment_report_c36.json`. No real optimizer run, Spectre, OCEAN, Virtuoso, bridge, PSF parsing, or formula rewrite occurred.
- current_scope: C-36 Stable OpenBox/Hermes Execution Environment Gate complete.

- C-38 OpenBox Continuation / Multi-Run Optimizer Workflow: complete, verified-only. Added `hermes-workflow continue-openbox-real`, OpenBox continuation warm-start from prior backend-neutral traces, cumulative optimizer artifact writing, duplicate seeding from prior candidates, continued evaluation/run/batch numbering, and `package-optimizer-task --backend openbox --continuation --additional-evals N`. Verification passed with full tests (`566 passed, 1 skipped`) and full ruff. No real optimizer run, Spectre, OCEAN, Virtuoso, bridge, PSF parsing, or formula rewrite occurred.
- current_scope: C-38 OpenBox Continuation / Multi-Run Optimizer Workflow complete.

- C-39 OpenBox Real Continuation Acceptance: complete, verified-only. Acceptance plan: `docs/superpowers/plans/2026-06-05-openbox-real-continuation-acceptance.md`; sanitized evidence: `docs/debug/2026-06-05-c39-openbox-real-continuation-acceptance.md`. First attempt exposed a C-38 package guard issue: explicit continuation candidate packaging rejected a prior `completed` optimizer state. Fixed with a continuation-only allowance while keeping normal completed/stopped guards intact. Real rerun on `/tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv` passed toolchain gate, continued C34 from `100` to `120` cumulative evaluations, added `real_101` through `real_120`, and closed out with `check-optimizer-run` accepted, `summarize-optimizer-run` `accept_best_observed` confidence `medium` `global_optimum_claim=false`, and `finalize-optimizer-run` passed. New continuation statuses: `15 feasible`, `5 constraint_failed`; cumulative statuses: `58 feasible`, `56 constraint_failed`, `6 metric_check_failed`; best observed remained `real_071`.
- current_scope: C-39 OpenBox Real Continuation Acceptance complete.

- C-40 OpenBox Continuation Production Handoff: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-05-openbox-continuation-production-handoff-design.md` and plan `docs/superpowers/plans/2026-06-05-openbox-continuation-production-handoff.md`. Strengthened generated OpenBox task packets so continuation handoff includes the toolchain gate, known-good OpenBox venv, non-sandbox/escalated execution note, `finalize-optimizer-run`, and supervisor closeout artifacts. Updated `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` with first-run and continuation packet flows. No real tools were run.
- current_scope: C-40 OpenBox Continuation Production Handoff complete.

- C-41 Optimizer Continuation Decision Detail: complete, verified-only. Added design spec `docs/superpowers/specs/2026-06-05-optimizer-continuation-decision-detail-design.md` and plan `docs/superpowers/plans/2026-06-05-optimizer-continuation-decision-detail.md`. `summarize-optimizer-run` now writes `continuation` detail into `reports/optimizer_completion_report.json`, including whether continuation is recommended, suggested additional eval count, recent-window improvement, plateau detection, feasible ratio, low-feasible-ratio flag, estimated remaining finite combinations, and reason. Existing top-level decisions remain unchanged. No real tools were run.
- current_scope: C-41 Optimizer Continuation Decision Detail complete.

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
1. ic-auto-opt-workflow/AGENTS.md
2. ic-auto-opt-workflow/docs/CURRENT_TASK_STATE.json
3. ic-auto-opt-workflow/docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md
4. ic-auto-opt-workflow/docs/EXECUTION_PROGRESS_2026-05-29.md
5. ic-auto-opt-workflow/docs/COMPACT_RESUME_CHECKPOINT.md
6. ic-auto-opt-workflow/docs/superpowers/specs/2026-06-05-openbox-production-backend-design.md
7. ic-auto-opt-workflow/docs/superpowers/plans/2026-06-05-openbox-production-backend.md
8. ic-auto-opt-workflow/docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md

当前活动节点是 C-29 OpenBox Production Backend。C-29 design spec 和 implementation plan 已完成。下一步是 execute C-29 Task 1 OpenBox Search Space Contract; do not run real tools, replace TuRBO, delete native_turbo, add hidden FN=FP coupling, or broaden the optimizer framework。不要直接替换 TuRBO，不要删除 native_turbo，不要启动 broad optimizer framework，不要提交 raw input.scs、ade_e.scs、PSF/raw、完整 Cadence log、docs/OCEAN_DOC_*、docs/toolchain_evidence/。不要解析 PSF，不要重写 OCEAN 公式。
```


C-42 OpenBox Continuation Packet Handoff Drill Completion:

- Status: complete, verified-only.
- Active spec: `docs/superpowers/specs/2026-06-05-openbox-continuation-production-handoff-design.md`.
- Active plan: `docs/superpowers/plans/2026-06-05-openbox-continuation-packet-handoff-drill.md`.
- Sanitized evidence: `docs/debug/2026-06-05-c42-openbox-continuation-packet-handoff-drill.md`.
- Workspace: `/tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv`, copied from accepted C39 workspace `/tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv`.
- Packet generated by `package-optimizer-task --backend openbox --continuation --additional-evals 10` and verified to contain `check-toolchain-env`, `/tmp/ic_auto_opt_openbox_spike/.venv`, `continue-openbox-real`, `finalize-optimizer-run`, non-sandbox/escalated execution wording, and supervisor report artifacts.
- Real packet drill passed toolchain gate, then completed OpenBox/Spectre/OCEAN continuation from `120` to `130` cumulative evaluations.
- New run ids: `real_121` through `real_130`; new statuses: `4 feasible`, `6 constraint_failed`.
- Cumulative statuses: `62 feasible`, `62 constraint_failed`, `6 metric_check_failed`, `0 real_check_failed`.
- `check-optimizer-run`: accepted. `summarize-optimizer-run`: `accept_best_observed`, confidence `medium`, `global_optimum_claim=false`. `finalize-optimizer-run`: passed.
- Best observed remained `real_071`; continuation detail reports `recommended=false`, `plateau_detected=true`.
- Boundary: no formula changes, no hand-picked candidates, no PSF parsing, no OCEAN formula rewrite, no raw Cadence artifacts committed.
- current_scope: C-42 OpenBox Continuation Packet Handoff Drill complete.
- next_allowed_action: wait for user confirmation before the next narrow production step; recommended next is a small supervisor-facing optimizer run-status command or user-guided production adoption of the C-40/C-42 packet handoff path.


C-43 Optimizer Status Command Completion:

- Status: complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-05-optimizer-status-command-design.md`.
- Implementation plan: `docs/superpowers/plans/2026-06-05-optimizer-status-command.md`.
- Code: added `src/hermes_workflow/optimizer_status.py` and CLI `hermes-workflow optimizer-status PROJECT_DIR`.
- Behavior: reuses `finalize_optimizer_run`, reads existing completion/finalize data, and prints a compact supervisor-facing summary: status, decision, confidence, `global_optimum_claim`, best observed run id, evaluation count, status counts, continuation recommendation, plateau flag, reason, and report paths.
- Real-workspace smoke on `/tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv`: status `pass`, decision `accept_best_observed`, confidence `medium`, `global_optimum_claim=false`, best observed `real_071`, `130` evaluations, counts `constraint_failed=62`, `feasible=62`, `metric_check_failed=6`, continuation recommended `false`.
- Verification: `python3 -m pytest tests/test_optimizer_status.py -q` passed; `python3 -m pytest tests/test_optimizer_status.py tests/test_optimizer_finalize.py tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py -q` passed; targeted ruff passed.
- Boundary: no real optimizer execution, Spectre, OCEAN, Virtuoso, bridge, objective change, new report contract, PSF parsing, or OCEAN formula rewrite occurred.
- current_scope: C-43 Optimizer Status Command complete.
- next_allowed_action: wait for user confirmation before the next narrow production step; recommended next is production use of optimizer-status on a fresh execution-agent handoff, or a small user-facing optimizer adoption guide update if needed.


C-44 Optimizer Status Handoff Integration Completion:

- Status: complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`.
- Implementation plan: `docs/superpowers/plans/2026-06-05-optimizer-status-handoff-integration.md`.
- Code: updated `src/hermes_workflow/optimizer_task_package.py` so generated native TuRBO and OpenBox optimizer task packets include `hermes-workflow optimizer-status PROJECT_DIR` in `audit_commands` and task text.
- Guide: updated `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` so supervisor closeout runs `finalize-optimizer-run` for machine acceptance and then `optimizer-status` for the concise decision summary.
- Verification: RED packet tests failed before implementation; GREEN packet tests passed (`9 passed`); adjacent status/finalize/package tests passed (`15 passed`); targeted ruff passed.
- Boundary: no real optimizer execution, Spectre, OCEAN, Virtuoso, bridge, optimizer behavior change, new report contract, PSF parsing, or OCEAN formula rewrite occurred.
- current_scope: C-44 Optimizer Status Handoff Integration complete.
- next_allowed_action: wait for user confirmation before the next narrow production step; recommended next is a fresh production-style optimizer handoff using the updated packet and optimizer-status closeout, or a small adoption guide/example if the user wants documentation first.


C-45 Fresh Optimizer Status Handoff Drill Completion:

- Status: complete, verified-only.
- Active spec: `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`.
- Active plan: `docs/superpowers/plans/2026-06-05-fresh-optimizer-status-handoff-drill.md`.
- Sanitized evidence: `docs/debug/2026-06-05-c45-fresh-optimizer-status-handoff-drill.md`.
- Workspace: `/tmp/ic_auto_opt_c45_fresh_status_handoff_001/bridge_test_inv`.
- Fresh workspace preparation copied only `config/`, `netlists/`, and matching `supervisor_instruction.json` from `/tmp/ic_auto_opt_c34_clean2/bridge_test_inv`; old `ledger/`, `state/`, `reports/`, and `runs/` were not copied.
- Generated updated OpenBox task packet with `--max-evals 10`; packet task text and manifest audit commands include `optimizer-status`.
- Real execution passed `check-toolchain-env` and completed 10 OpenBox-generated Spectre/OCEAN evaluations with `parallel_jobs=10`, `threads_per_run=10`, and approved Cadence cshrc.
- Closeout passed through `check-optimizer-run`, `summarize-optimizer-run`, `finalize-optimizer-run`, and `optimizer-status`.
- Result summary: `9 constraint_failed`, `1 metric_check_failed`, `0 feasible`, best observed `real_009`, decision `stop_for_user_review`, confidence `low`, `global_optimum_claim=false`, continuation recommended `false`.
- Route sync: updated `AGENTS.md` stale cadence wording, top-level plan current node, and `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` closeout reference.
- Boundary: no hand-picked candidates, no variable/formula changes, no PSF parsing, no OCEAN formula rewrite, and no raw Cadence artifacts committed.
- current_scope: C-45 Fresh Optimizer Status Handoff Drill complete.
- next_allowed_action: wait for user confirmation before the next production step; recommended next is user-selected real project scale adoption using the current packet/status handoff, or a narrow usability fix only if the user wants one before adoption.


C-46 Real-Scale Optimizer Status Handoff Completion:

- Status: complete, verified-only.
- Active spec: `docs/superpowers/specs/2026-06-05-optimizer-status-handoff-integration-design.md`.
- Active plan: `docs/superpowers/plans/2026-06-05-real-scale-optimizer-status-handoff.md`.
- Sanitized evidence: `docs/debug/2026-06-05-c46-real-scale-optimizer-status-handoff.md`.
- Workspace: `/tmp/ic_auto_opt_c46_real_scale_status_handoff_001/bridge_test_inv`.
- Fresh workspace preparation copied only `config/`, `netlists/`, and matching `supervisor_instruction.json`; old `ledger/`, `state/`, `reports/`, and `runs/` were not copied.
- Generated updated OpenBox task packet with `--max-evals 100`; packet includes `optimizer-status`, `parallel_jobs=10`, `batch_size=10`, and `threads_per_run=10`.
- Real execution passed `check-toolchain-env` and completed 100 OpenBox-generated Spectre/OCEAN evaluations.
- Closeout passed through `check-optimizer-run`, `summarize-optimizer-run`, `finalize-optimizer-run`, and `optimizer-status`.
- Result summary: `43 feasible`, `51 constraint_failed`, `6 metric_check_failed`, best observed `real_071`, decision `accept_best_observed`, confidence `medium`, `global_optimum_claim=false`, continuation recommended `false`, plateau detected `true`.
- Best observed parameters: `FN=12`, `WN=2.7u`, `FP=7`, `WP=0.7u`; metrics: `rise=69.604322ps`, `fall=56.781892ps`, `DC=326.978183uW`; objective `4.1325534822170306e-14`.
- Boundary: no hand-picked candidates, no variable/formula changes, no PSF parsing, no OCEAN formula rewrite, and no raw Cadence artifacts committed.
- current_scope: C-46 Real-Scale Optimizer Status Handoff complete.
- next_allowed_action: wait for user confirmation before the next production step; recommended next is user-selected project adoption at the desired evaluation budget, or a narrow usability/reporting fix if the C-46 real-scale evidence exposes a specific need.


C-47 OpenBox Advanced Visualization Artifact Completion:

- Status: complete, verified-only.
- Active plan: `docs/superpowers/plans/2026-06-05-openbox-advanced-visualization-artifact.md`.
- OpenBox backend now generates official post-run HTML/JSON visualization artifacts from `advisor.get_history().visualize_html(...)` at final OpenBox closeout.
- Manifest: `reports/openbox_advanced_visualization_manifest.json`.
- Report linkage: `optimizer_run_report.json` records `openbox.advanced_visualization`; `optimizer_insight_report.{json,md}` links the artifact and warnings.
- Status model: `generated`, `generated_partial`, `failed`, `not_available`.
- Real OpenBox-only probe now produced `generated`: surrogate verification and parameter importance are present.
- OpenBox venv dependency correction: latest unpinned SHAP briefly upgraded OpenBox-incompatible numeric packages; venv was restored to `numpy==1.26.4`, `scipy==1.12.0`, `scikit-learn==1.3.2`, `pandas==2.1.4`, `shap==0.44.1`, `lightgbm==4.6.0`, `swig==4.4.1`, and `pyrfr==0.9.0`.
- `pyrfr` was built without system package changes by installing PyPI `swig` inside the OpenBox venv and then running `pip install --no-build-isolation pyrfr`.
- Verification: full suite passed (`574 passed, 1 skipped`) and targeted ruff passed.
- Boundary: no real Spectre/OCEAN rerun, no metric formula changes, no PSF parsing, no backend replacement.
- current_scope: C-47 OpenBox Advanced Visualization Artifact complete.

C-47 Real OpenBox Advanced Visualization Flow Completion:

- Status: complete, verified-only.
- Evidence: `docs/debug/2026-06-05-c47-real-openbox-advanced-visualization-flow.md`.
- Workspace: `/tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv`.
- Full real OpenBox/Spectre/OCEAN flow completed 100 evaluations and passed `check-optimizer-run`, `summarize-optimizer-run`, `finalize-optimizer-run`, and `optimizer-status`.
- Counts: `43 feasible`, `51 constraint_failed`, `6 metric_check_failed`, `0 real_check_failed`.
- Best observed: `real_071`, `FN=12`, `WN=2.7u`, `FP=7`, `WP=0.7u`; `rise=69.604322ps`, `fall=56.781892ps`, `DC=326.978183uW`; objective `4.1325534822170306e-14`.
- OpenBox advanced visualization: manifest status `generated`, including objective/constraint history, surrogate verification, and parameter importance.
- Boundary: no hand-picked candidates, formula changes, PSF parsing, OCEAN formula rewrite, or raw Cadence artifact commit.
- current_scope: C-47 Real OpenBox Advanced Visualization Flow complete.

C-48 IC-native Offline Optimizer Insight Report Completion:

- Status: complete, verified-only.
- `optimizer_insight_report` now adds IC-native report sections from existing evaluated samples: best feasible summary, top feasible candidates, constraint margin summary, feasible-only convergence, constraint margin plot, and OpenBox SHAP importance summary with constraint metric labels.
- Real sample probe: `/tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv` regenerated successfully without Spectre/OCEAN rerun.
- Verification: `tests/test_optimizer_insights.py` passed, adjacent optimizer report/closeout tests passed (`22 passed`), targeted ruff passed.
- Boundary: reporting-only change; no candidate selection, formula, adapter, acceptance, continuation, or PSF parsing change.
- current_scope: C-48 IC-native Offline Optimizer Insight Report complete.

Project Landing Baseline Consolidation:

- Status: complete, verified-only.
- Baseline: `docs/PROJECT_LANDING_BASELINE_2026-06-05.md`.
- current_scope: Project landing baseline consolidation after C-48.
- Solidified state: prepared projects with reviewed config and Maestro/ADE-style exported netlist bundles can run OpenBox optimizer handoff, close out through `finalize-optimizer-run` and `optimizer-status`, generate IC-native insight reports, and continue accepted OpenBox runs.
- Remaining required landing gaps: user intent to structured intake/config, first user-selected real-cell bootstrap/adoption drill, formula/variable/resource approval checkpoint, and production guide tightening for the full user-to-run entry flow.
- Boundary: docs/state consolidation only; no code change, real tool run, optimizer behavior change, candidate selection change, formula change, PSF parsing, or OCEAN formula rewrite.

C-49 Requirement.md Driven Config Intake Design:

- Status: complete, verified-only.
- Design spec: `docs/superpowers/specs/2026-06-05-requirement-md-config-intake-design.md`.
- current_scope: C-49 Requirement.md Driven Config Intake design spec complete.
- Direction: users create `~/spectre_opt_prj/<project_name>/`, write strict `opt_requirement.md` with fixed Markdown headings and fenced YAML blocks, optionally write `constraints.md`, and provide `maestro_point_root`; Hermes later validates/renders existing config YAML and imports the Maestro point-root netlist bundle.
- Boundary: design-only; no code change, real tool run, optimizer behavior change, formula rewrite, PSF parsing, or schema replacement.

Post-C50 Objective Safe Math And All-Evaluable FoM Plot:

- Status: complete, verified-only.
- Objective expression evaluator now supports `min()`, `max()`, and `ln()` with validation and runtime rejection for unsupported functions.
- `optimizer_insight_report` now writes `all_evaluable_fom_summary` and `reports/optimizer_visuals/all_evaluable_fom.svg`.
- Existing-result formula probe succeeded without Spectre/OCEAN rerun: the user's proposed normalized FoM formula, using the current metric name `P1DB`, recomputed 84 samples and selected `real_093` in `/tmp/ic_auto_opt_fom_formula_probe`.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` was refreshed under its current objective: `source=configured_objective`, `sample_count=84`, best current-objective run `real_059`.
- Verification: targeted optimizer/report tests passed (`147 passed, 1 skipped`) and targeted ruff passed.
- current_scope: Post-C50 Objective Safe Math And All-Evaluable FoM Plot complete.

Post-C50 Configured Objective Ranking:

- Status: complete, verified-only.
- `optimizer_insight_report` now includes `configured_objective_ranking`, a current-objective re-score/re-rank view that does not overwrite original run-time `best_observed`.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` now uses the normalized FoM formula in `config/metrics.yaml` and `opt_requirement.multi_testbench.md`.
- Real project checks passed: `validate`, `check-requirement`, and offline `visualize-optimizer-run`; no Spectre/OCEAN rerun.
- Configured ranking result: `84` computable samples, best `real_093`, feasible, objective `-0.7085522728550304`, parameters `F=20`, `W=1.4u`, `L=30n`, `VB_LO=310m`.
- Verification: optimizer insight/closeout/status/OpenBox backend tests passed (`36 passed`) and targeted ruff passed.
- current_scope: Post-C50 Configured Objective Ranking complete.

Post-C50 Bottleneck Weighted Score Plot:

- Status: complete, verified-only.
- `optimizer_insight_report` now writes `bottleneck_weighted_score_summary` and `reports/optimizer_visuals/bottleneck_weighted_score.svg`.
- Plot semantics: x = weighted-sum score, y = bottleneck `min(z_i)`, iso-lines = `0.7*bottleneck + 0.3*weighted`.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` refreshed the report without Spectre/OCEAN rerun; SVG contains all `84` computable points and highlights feasible `real_093`.
- Verification: optimizer insight/closeout/status/OpenBox backend tests passed (`37 passed`) and targeted ruff passed.
- current_scope: Post-C50 Bottleneck Weighted Score Plot complete.

C-51 Optimizer Decision Report MVP:

- Status: complete, verified-only.
- `optimizer_decision_report.{json,md}` is now generated by `hermes-workflow decide-optimizer-run` from existing optimizer insight artifacts.
- The report is supervisor-facing: recommended candidate, basis, action, confidence, best-observed boundary, bottleneck metric, status counts, and next steps.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` generated the report without Spectre/OCEAN rerun.
- Real decision: recommended feasible `real_093`, action `accept_best_observed_or_continue`, confidence `medium`, `global_optimum_claim=false`, bottleneck `BW`.
- Verification: new decision tests passed (`2 passed`), adjacent optimizer report/closeout/status tests passed (`26 passed`), and targeted ruff passed.
- current_scope: C-51 Optimizer Decision Report MVP complete.

C-52 Optimizer Supervisor Decision Record:

- Status: complete, verified-only.
- `record-optimizer-decision` now records a supervisor action from the existing optimizer decision report into `optimizer_supervisor_decision.{json,md}`.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` recorded `accept_best_observed` for `real_093`, with `global_optimum_claim=false` and no Spectre/OCEAN rerun.
- Verification: new supervisor decision tests passed (`2 passed`), adjacent optimizer report/closeout/status tests passed (`28 passed`), and targeted ruff passed.
- current_scope: C-52 Optimizer Supervisor Decision Record complete.

C-53 Optimizer Final Summary:

- Status: complete, verified-only.
- `write-optimizer-final-summary` now writes a user-facing final summary from accepted optimizer decision artifacts.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` generated `optimizer_final_summary.{json,md}` for accepted `real_093`, including parameters, metrics, score/bottleneck, status counts, visual links, report links, and boundaries.
- Verification: new final summary tests passed (`2 passed`), adjacent optimizer report/closeout/status tests passed (`30 passed`), and targeted ruff passed.
- current_scope: C-53 Optimizer Final Summary complete.

C-54 Production Landing MVP:

- Status: complete, verified-only.
- Added a production quickstart and `check-project-ready` CLI for offline project readiness checks.
- `check-project-ready` writes `reports/project_readiness_report.json` and checks requirement files, core config files, contract validation, native netlist bundle readiness, and final summary availability.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` passed with `readiness=ready_for_closeout_review`, 3 testbench netlist bundles, and accepted `real_093`.
- Verification: project readiness/intake/validate/final-report tests passed (`53 passed`), targeted ruff passed, cadence check passed, and `git diff --check` passed.
- current_scope: C-54 Production Landing MVP complete.

C-56 Optimizer Decision Handoff Hardening:

- Status: complete, verified-only.
- Commit: `df796f4 fix: harden optimizer decision handoff`.
- Fixed the production issue exposed by the full agent E2E simulation: `decide-optimizer-run` no longer uses a non-feasible configured-objective best candidate as the primary recommendation when feasible candidates exist.
- The decision path now prefers feasible configured candidates, otherwise feasible stored best-observed/top-feasible candidates, and records warnings for ignored non-feasible configured-best points.
- Real simulation recheck on `/tmp/ic_auto_opt_agent_e2e_g2qieZ/Mixer_opt_muti_tb_full` regenerated only the decision report and now recommends feasible `real_066` instead of constraint-failed `real_057`.
- Production docs now require the package/preflight/approval gate before real execution, use the user/project Cadence environment setup instead of hardcoded Spectre-version wording, and document low-frequency execution-agent status checks.
- Added design-only spec `docs/superpowers/specs/2026-06-07-one-command-optimizer-flow-design.md` for a future thin one-command optimizer orchestration route.
- Verification: `python3 -m pytest tests/test_optimizer_decision.py -q` passed (`3 passed`); adjacent optimizer closeout/report/status tests passed (`31 passed`); targeted ruff and `git diff --check` passed.
- current_scope: C-56 Optimizer Decision Handoff Hardening complete.

C-57 One-Command Optimizer Flow:

- Status: complete, verified-only.
- Commit: `e6ce269 feat: add optimizer one-command flow`.
- Added `hermes_workflow.optimizer_flow.optimize_project` and CLI command `hermes-workflow optimize PROJECT_DIR --real`.
- The command wraps the existing proven production command sequence and writes `reports/optimizer_flow_run_report.json`.
- `--dry-orchestration` runs all offline gates through `package-optimizer-task` and stops before real Spectre/OCEAN/OpenBox execution.
- Full real mode runs real OpenBox execution and the closeout report chain through `decide-optimizer-run`, then stops for user acceptance. It does not auto-record the final user decision.
- Production quickstart and agent usage manual now prefer the one-command route and keep manual commands as fallback.
- Verification: `tests/test_optimizer_flow.py` passed (`3 passed`); adjacent CLI/readiness/decision/final-summary tests passed (`46 passed`); targeted ruff passed; `git diff --check` passed.
- current_scope: C-57 One-Command Optimizer Flow complete.

C-65 Runtime-Native Agent Adapters:

- Status: complete, verified-only.
- Product boundary corrected: shell `ic-opt PROJECT_DIR --real` is deterministic automation; agent product UX is `/ic-opt PROJECT_DIR --real` in the active runtime, with the supervisor delegating to the same runtime's native execution subagent.
- Added `agent_runtime` installer/status support and runtime assets for Claude and OpenCode.
- Claude adapter smoke: `/ic-opt` entered the new skill; clean Mixer dry-orchestration project passed all 10 supervisor gate steps and stopped before `run-openbox-real` with `execution_agent=direct`.
- OpenCode adapter smoke: `ic-opt-execution` appears as a subagent; `/ic-opt` command entered the new command; clean Mixer dry-orchestration project passed and did not dispatch real execution.
- User-facing docs now point IC users to `docs/AGENT_USER_QUICKSTART_CN.md` and clarify that C-64 `--execution-agent claude` is development/acceptance evidence, not the default product route.
- Verification: `tests/test_agent_runtime.py tests/test_product_cli.py` passed (`14 passed`), targeted ruff passed, runtime adapter install/status checks passed, and Claude/OpenCode dry runtime smoke checks passed.
- current_scope: C-65 Runtime-native agent adapters complete.
