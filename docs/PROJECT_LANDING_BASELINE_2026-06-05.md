# Project Landing Baseline

Date: 2026-06-05
Last updated: 2026-06-06

This document freezes the current proven workflow after C-48 and lists the
remaining work needed before routine real-project adoption.

It is intentionally narrow. Do not treat it as a new framework or a replacement
for the active plans. Use it as the current baseline when deciding the next
development step.

## Current Proven Route

The current route is:

```text
user / supervisor agent defines approved contracts
-> Hermes workflow tooling validates config and packages handoff files
-> execution agent follows the generated task packet
-> OpenBox or native TuRBO proposes candidates
-> Spectre runs with approved precision and resource settings
-> OCEAN evaluates approved metric formulas
-> Hermes audits manifests, summarizes completion, and generates reports
-> supervisor accepts best observed, continues, revises search, or stops
```

The accepted production optimizer path is OpenBox-backed, with native TuRBO
preserved as an available backend. OpenBox is not a silent fallback; it must be
selected and its execution environment must pass the toolchain gate.

## Solidified Pieces

Role model:

- Supervisor agent owns user interaction, planning, approvals, and decisions.
- Hermes workflow tooling owns deterministic contracts, validation, packaging,
  audits, summaries, and reports.
- Execution agent owns real tool operation after an approved task packet exists.

Metric route:

- Standalone Spectre plus batch OCEAN is the accepted metric backend.
- Python does not parse PSF and does not reimplement Calculator/OCEAN formulas.
- Approved formulas in `metrics.yaml` remain authoritative.

Optimizer route:

- OpenBox real optimizer flow is productized through `run-openbox-real`.
- Continuation is productized through `continue-openbox-real`.
- Candidate generation is backend-owned; agents must not hand-pick points.
- Best result wording is `best observed`, not global optimum.

Multi-testbench route:

- A single optimizer candidate can now render the same approved parameters into
  multiple preserved Maestro/ADE point-root testbench bundles.
- Each child testbench runs its own Spectre/OCEAN job and writes child result
  and metric manifests.
- Hermes aggregates child scalar metrics into the existing candidate-level
  `result_manifest.json` and `metrics/metric_result_manifest.json` paths.
- Testbenches are not merged into a synthetic Spectre deck.

Handoff route:

- `package-optimizer-task --backend openbox` writes the execution-agent packet.
- The task packet includes toolchain gate, exact execution command, audit
  commands, non-sandbox wording, and expected returned artifacts.
- `finalize-optimizer-run` is the machine acceptance closeout.
- `optimizer-status` is the supervisor-facing one-screen closeout.

Reporting route:

- `optimizer_insight_report.md` now includes IC-native summaries, top feasible
  candidates, constraint margins, feasible-only convergence, constraint margin
  plots, and OpenBox parameter-importance summaries when available.
- OpenBox official advanced visualization artifacts are generated after final
  OpenBox closeout.
- Report generation is post-run and can be improved without changing candidate
  generation or rerunning Spectre/OCEAN.

Toolchain route:

- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` is the mandatory reference before real
  Virtuoso/Spectre/OCEAN/OpenBox/native-TuRBO/bridge work.
- Known-good OpenBox execution venv:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

- Known Cadence cshrc:

```text
/home/zzchen/cadence_ic231_env.csh
```

- Accepted inverter settings:

```text
preset=ax
threads_per_run=10
parallel_jobs=10
output_format=psfxl
```

`threads_per_run` is Spectre `+mt` for one Spectre process.
`parallel_jobs` is the number of concurrent Spectre processes.

## Real Evidence Anchors

Spectre + OCEAN evidence:

- `docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/`
- `docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/`

OpenBox production handoff evidence:

- C-34: first successful production OpenBox handoff from a clean workspace.
- C-46: 100-evaluation real-scale OpenBox handoff.
- C-47: 100-evaluation real OpenBox flow with official advanced visualization.
- C-48: IC-native offline optimizer insight report regenerated from the C-47
  real samples without rerunning Spectre/OCEAN.
- C-49: strict `opt_requirement.md` intake generated a real Mixer project from
  user-provided Maestro point-root data and passed a real single-point
  Spectre/OCEAN smoke.
- C-50: multi-testbench Mixer route completed 100 real three-testbench
  OpenBox/Spectre/OCEAN evaluations.

Current high-value local workspace:

```text
/tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
```

Its 100-evaluation result:

```text
43 feasible
51 constraint_failed
6 metric_check_failed
0 real_check_failed
best observed: real_071
decision: accept_best_observed
confidence: medium
global_optimum_claim: false
```

Continuation evidence:

- C-39: continued a real OpenBox run from 100 to 120 evaluations.
- C-42: generated continuation packet and continued from 120 to 130
  evaluations through the handoff route.

Multi-testbench evidence:

```text
/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb
```

Its 100-evaluation result:

```text
19 feasible
65 constraint_failed
16 metric_check_failed
0 recorded real_check_failed
best observed: real_068
decision: accept_best_observed
confidence: medium
global_optimum_claim: false
testbenches: cg_nf, iip3, p1db
metrics: BW, MAX_GAIN, NF_3G, IIP3, P1DB
```

## What Is Production-Usable Now

Given a project with a strict `opt_requirement.md` and reviewed Maestro/ADE
point-root inputs, the workflow can:

1. validate and package the project;
2. generate deterministic config files and safe imported netlist bundles;
3. generate an execution-agent OpenBox task packet;
4. run OpenBox-generated candidates through single-testbench or
   multi-testbench Spectre/OCEAN evaluation;
5. audit returned manifests;
6. summarize best observed result and continuation recommendation;
7. generate supervisor-facing reports and visual artifacts;
8. continue an accepted OpenBox run for more evaluations.

This is enough for controlled adoption on a prepared project.

## Remaining Work Before Routine Real-Project Landing

Required for a smooth first non-demo adoption:

1. Formula and variable approval checkpoint.
   - Existing `metrics.yaml`, `variables.yaml`, and `spectre.yaml` are already
     strict once written.
   - The missing product step is a concise supervisor/user approval stage for
     newly drafted formulas, variables, constraints, objective, and resource
     settings before real execution.

2. Production usage guide tightening around the first-project path.
   - `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` covers the current handoff.
   - It still needs to describe the complete `opt_requirement.md` to
     single-testbench/multi-testbench optimizer run entry flow.

3. Final optimizer closeout/status polish.
   - The current reports are usable, but the supervisor-facing closeout should
     make per-testbench failures, candidate-level metric failures, continuation
     advice, and user-action recommendations more concise.

Useful but not blocking:

- Report polish and additional offline visualizations.
- More examples beyond `bridge_test_inv`.
- Continuation policy tuning after more real projects.
- Cleaner packaging of the OpenBox execution environment.

Not recommended now:

- Deleting native TuRBO.
- Replacing the role model.
- Rebuilding the Spectre/OCEAN adapter foundation.
- Adding a broad workflow engine.
- Adding real-time visualization.
- Adding automatic formula rewriting or PSF parsing.
- Creating overlapping schemas or speculative assets.

## Recommended Next Step

The next narrow development step should be:

```text
C-51 Production User Entry And Closeout Guide
```

Recommended scope:

- update the production handoff guide for `opt_requirement.md`;
- include single-testbench and multi-testbench examples;
- add a concise user/supervisor approval checkpoint for formulas, variables,
  constraints, objective, and resource settings;
- document the C-50 multi-testbench evidence as the reference flow;
- keep implementation changes minimal unless the guide exposes a concrete
  missing CLI/report field.
