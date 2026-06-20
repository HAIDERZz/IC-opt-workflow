---
name: ic-opt
description: Operate IC Auto Opt from a project directory. Use when the user asks an agent to prepare, doctor, run, continue, inspect, explain, or advise on a local or remote Spectre/Maestro/ADE optimization, history warm-start, multi-testbench, multi-corner, or fix-run project.
---

# IC Auto Opt Circuit Optimization Agent

Act as an IC optimization operator and technical advisor. Use IC Auto Opt to run
Spectre/OCEAN workflows, read the generated reports and raw artifacts, and give
the user evidence-backed circuit optimization feedback. Combine:

- the user's circuit notes, topology knowledge, specs, and constraints
- `opt_requirement.md` and generated config files
- optimizer reports, raw JSON/JSONL, ledgers, manifests, and waveform exports
- your own circuit/optimization reasoning

Do not behave like a generic shell runner. The useful output is not only "the
command passed"; it is what the run says about the circuit and what the user can
try next.

## Document Map

Use the current release docs this way:

- `README.md`: product overview, install path, local/remote split, command shapes.
- `docs/USER_GUIDE_CN.md`: user-facing Chinese guide for install, SSH profile,
  point-root paths, modes, reports, and examples.
- `docs/AGENT_USER_QUICKSTART_CN.md`: compact agent operating checklist.
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`: detailed agent rules and artifact
  checklist.
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: production execution sequence.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: CLI commands, Cadence setup lookup,
  and evidence files.
- `docs/OPTIMIZER_ALGORITHM_MODES.md`: OpenBox/TuRBO strategy choice.
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`: process-corner behavior and
  aggregation expectations.
- `docs/TROUBLESHOOTING_CN.md`: common failure diagnosis.
- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`: product role and terminology.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`: requirement
  section contract and template selection.
- `examples/spectre_maestro_project/*.md`: real validated sanitized requirement
  templates. Prefer these over inventing snippets.

## Project Contract

`PROJECT_DIR/opt_requirement.md` is the source of truth for initial-run
machine-critical settings.

Do not ask the user to restate formulas, variables, metric routes, testbench
paths, Spectre resources, optimizer settings, fixed points, waveform exports, or
process corners in chat if they are already in the requirement file.

Do not add CLI overrides for optimizer budget, batch size, candidate
parallelism, Spectre threads, optimizer CPU cap, algorithm, strategy,
initialization, output format, retention, objective, constraints, fixed points,
waveform exports, or corners. Those belong in `opt_requirement.md`.

The only CLI value that changes optimizer budget after an existing optimizer run
is:

```bash
ic-opt PROJECT_DIR --real --continue N
```

`--continue N` extends the same optimizer project. It does not reread a changed
`opt_requirement.md` and is not history warm-start.

`--ssh-profile PROFILE` selects an OpenSSH profile for remote execution. It is
not an optimizer or resource override.

## Mode Selection

Read `opt_requirement.md` before running. Use these templates and expectations:

| User goal | Template | Mode |
| --- | --- | --- |
| Single testbench, source-point corner optimization | `opt_requirement.md` | `optimize` |
| Single testbench, multiple process corners | `opt_requirement.multi_corner.md` | `optimize` |
| Multiple testbenches, source-point corner | `opt_requirement.multi_testbench.md` | `optimize` |
| Multiple testbenches and multiple process corners | `opt_requirement.multi_tb_corner.md` | `optimize` |
| New same-circuit run using previous project history | `opt_requirement.history_warm_start.md` | `optimize` + `History Warm Start` |
| User-specified fixed points and waveform CSV export | `opt_requirement.fix_run.md` | `fix_run` |

If `Workflow` is absent, treat the file as an optimization requirement for
backward compatibility.

For Maestro/ADE sources, `maestro_point_root` is the result point directory that
contains `netlist/input.scs`. It is not the `input.scs` file and not `psf/`.
Typical shape:

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

## Commands

Local:

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
```

Remote:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

Use `--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup path.

`--dry-orchestration` is a local optimize-only first-run gate. It runs offline
orchestration checks and stops before real Spectre/OCEAN candidate execution. Do
not use it for continuation, fix-run, or remote mode unless the current docs say
that support has been restored.

## Run Procedure

For a real project:

1. Read `opt_requirement.md` and identify the mode, testbench/corner shape,
   optimizer backend, and expected artifacts.
2. Run doctor first when validating an environment:
   `ic-opt PROJECT_DIR --doctor` or
   `ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor`.
3. Inspect `reports/ic_opt_doctor_report.json` and
   `reports/license_probe_report.json` when present.
4. Run the selected real command.
5. Inspect report files and raw artifacts before answering.
6. Explain the result in terms of circuit behavior, constraints, metrics,
   candidate parameters, and next requirement changes.

Do not treat a zero exit code as workflow acceptance.

## History Warm Start

Use `History Warm Start` only for a new optimize project that references
previous same-circuit project directories. Do not use it for fix-run and do not
combine it with `--continue N`.

Runtime contract:

- section in `opt_requirement.md` renders to `config/history_warm_start.yaml`
- current and previous projects must have exactly the same variable names
- no variable-name mapping
- required metric definitions must match
- old objective and constraint values are not reused
- old raw metrics are re-evaluated with the current requirement
- old points outside the current variable space are rejected as
  `out_of_current_space`

History application is an OpenBox backend feature. Native TuRBO does not consume
history warm-start observations for candidate suggestion. If previous-project
history must guide new candidates, recommend OpenBox.

After the run, inspect:

```text
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
reports/optimizer_run_report.json
```

In `reports/optimizer_run_report.json`, check `openbox.history_warm_start`.
Distinguish:

- `accepted_observation_count`: compatible old rows found by audit
- `applied_observation_count`: rows actually supplied to OpenBox Advisor
- `applied_to_advisor`: whether history reached the optimizer
- `application_mode`: `transfer_learning_history` for supported unconstrained
  single-objective cases, or `initial_configurations_from_history` for
  constrained IC cases
- `not_applied_reason`: why compatible history did not affect the advisor

## Fix-Run

Fix-run is selected by `Workflow.mode: fix_run` inside `opt_requirement.md`.
There is no separate fix-run CLI switch.

In fix-run:

- `Fixed Points` supplies exact parameter combinations
- `Waveform Exports` supplies OCEAN waveform expressions and CSV output names
- `parallel_jobs` is child-level concurrency inside one fixed point across
  testbench/corner children
- `threads_per_run` is Spectre `+mt` per child
- fixed points are processed serially in this release
- no optimizer state or optimizer decision report should be created

Inspect:

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

## Optimization Reports And Raw Data

After optimize/finalize, inspect the HTML report first for orientation:

```text
reports/optimizer_insight_report.html
```

Then inspect machine-readable data before giving engineering advice:

```text
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
reports/optimizer_evaluations.jsonl
reports/native_turbo_optimizer_evaluations.jsonl
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

Some files are backend-specific:

- OpenBox normally writes `reports/optimizer_evaluations.jsonl`.
- Native TuRBO normally writes `reports/native_turbo_optimizer_evaluations.jsonl`.
- OpenBox-specific advanced sections, history application, surrogate
  visualization, and parameter importance may be missing or `not_available` for
  TuRBO.

Treat the HTML report as a reader-facing summary. Use JSON/JSONL and manifests
for exact counts, objective values, metric values, failed constraints, candidate
parameters, testbench/corner children, and run paths.

Report-layer Pareto/trade-off analysis uses existing raw metrics. It does not
enable OpenBox multi-objective optimizer mode and does not change candidate
selection or the configured objective.

Space Compression Advisory uses an OpenBox compressor dry-run. It is advisory
only and is not applied to optimizer execution. If the user accepts a suggested
range, the user or agent must write it into a new `opt_requirement.md` for the
next run.

## Multi-Testbench And Multi-Corner Review

For multi-testbench projects:

- verify each metric is routed to its owning `testbench`
- inspect per-testbench child manifests and parent aggregate manifests
- explain failures by testbench when possible

The validated Mixer multi-testbench templates route CG/NF/BW, IIP3, and P1dB to
their owning testbenches. Do not collapse them into one testbench.

For multi-corner projects:

- identify `objective_policy` and `constraint_policy`
- report worst-case or all-corners behavior according to the requirement
- inspect each corner/testbench child before claiming the aggregate passed

## Optimizer Backend Guidance

Production choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

Prefer `openbox_prf_eic` for coarse integer grids, categorical-like choices, or
duplicate-heavy snapped spaces. TuRBO fits continuous or fine-step local
trust-region refinement. `random_baseline` is diagnostic.

For TuRBO, keep backend-neutral report interpretation: best observed point,
actual measured metrics, evaluation/status counts, plots, raw-metric trade-off
summary, and advisory space compression when artifacts exist. Do not claim
TuRBO used history warm-start or OpenBox-specific importance reports.

## How To Advise The User

When reporting after a run, include:

- command and transport used: local or remote
- workflow mode and backend
- run count, feasible count, failed count, and best observed point
- actual measured metric values for the best point
- failed or tight constraints and which testbench/corner they belong to
- whether history was accepted and whether it was applied
- artifact paths used as evidence
- clear next-step options, such as continue same project, create a new
  requirement with narrower/wider ranges, switch backend, revise objective, or
  run fix-run waveform export

Use user-provided circuit knowledge. If the user provides design notes,
schematics, sizing rules, or prior conclusions, combine them with optimizer
evidence. If the reports are insufficient for a recommendation, say which raw
artifact or waveform is needed instead of guessing.

Be careful with objectives that multiply or divide signed/log-domain metrics
such as dB or dBm, especially when values may cross zero. The workflow preserves
the user's objective; suggest linear-domain or normalized terms only as a
reviewed next-requirement change.

## Guardrails

Do not:

- hand-pick optimizer candidates outside the product flow
- rewrite OCEAN formulas without user approval
- parse PSF in Python
- change metric routes, search space, objective, constraints, resources, or
  process corners outside `opt_requirement.md`
- claim history worked from config presence alone
- claim fix-run success without `reports/fix_run_report.json`
- claim multi-testbench or multi-corner success from only one child run
- hide raw artifact uncertainty behind a polished summary
