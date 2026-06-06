# Project Landing Baseline

Date: 2026-06-05

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

## What Is Production-Usable Now

Given an already prepared project with reviewed config files and a correct
Maestro/ADE-style exported netlist bundle, the workflow can:

1. validate and package the project;
2. generate an execution-agent OpenBox task packet;
3. run OpenBox-generated candidates through Spectre/OCEAN;
4. audit returned manifests;
5. summarize best observed result and continuation recommendation;
6. generate supervisor-facing reports and visual artifacts;
7. continue an accepted OpenBox run for more evaluations.

This is enough for controlled adoption on a prepared project.

## Remaining Work Before Routine Real-Project Landing

Required for a smooth first non-demo adoption:

1. User intake to structured contract.
   - Missing today: a formal `user_intake.json` or equivalent contract that
     captures user intent before rendering the existing YAML files.
   - The correct boundary is: supervisor agent drafts structured intake; Hermes
     validates and renders deterministic config files.
   - Do not build a generic natural-language parser inside Hermes.

2. New-project bootstrap drill from a user-selected real cell.
   - The current proven optimizer flow uses prepared inverter project bundles.
   - A first real adoption should verify the complete path from user-provided
     cell/testbench information and exported Maestro netlist sidecars into the
     current OpenBox handoff route.

3. Formula and variable approval checkpoint.
   - Existing `metrics.yaml`, `variables.yaml`, and `spectre.yaml` are already
     strict once written.
   - The missing product step is a concise supervisor/user approval stage for
     newly drafted formulas, variables, constraints, objective, and resource
     settings before real execution.

4. Production usage guide tightening around the first-project path.
   - `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` covers the current handoff.
   - It still assumes the project contracts already exist and are reviewed.
   - After the intake/bootstrap work, the guide should describe the complete
     user-to-run entry flow.

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
C-49 User Intake Structured Contract MVP
```

Recommended scope:

- define one structured intake contract for supervisor-authored project intent;
- validate required fields, unknowns, and user-confirmation blockers;
- render the existing `config/*.yaml` files from that intake only after required
  fields are explicit;
- preserve existing config schemas as the execution source of truth;
- keep LLM/natural-language ambiguity outside Hermes deterministic execution.

After C-49, run a first-project bootstrap/adoption drill using a user-selected
cell and the current OpenBox handoff route.
