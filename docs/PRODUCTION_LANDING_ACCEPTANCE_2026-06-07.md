# Production Landing Acceptance 2026-06-07

Status: accepted for first production trial, verified-only.

This note closes the current landing milestone for `ic-auto-opt-workflow`.
The project is now usable as a first production optimizer workflow for a
user-prepared Spectre optimization project. This is not a claim that every
future circuit, formula, PDK, or optimizer policy is complete.

## Accepted Scope

The accepted production route is:

```text
user project with opt_requirement.md and optional constraints.md
-> hermes-workflow check-requirement
-> hermes-workflow prepare-from-requirement
-> hermes-workflow validate
-> hermes-workflow check-project-ready
-> hermes-workflow run-openbox-real or execution-agent packet handoff
-> hermes-workflow check-optimizer-run
-> hermes-workflow summarize-optimizer-run
-> hermes-workflow finalize-optimizer-run
-> hermes-workflow visualize-optimizer-run
-> hermes-workflow decide-optimizer-run
-> hermes-workflow record-optimizer-decision
-> hermes-workflow write-optimizer-final-summary
-> hermes-workflow check-project-ready
```

This route preserves the key project boundary:

- Supervisor agent: planning, user-facing decisions, formula approval, and
  accepting or continuing optimizer results.
- Hermes workflow tooling: deterministic file contracts, validation,
  readiness checks, packaging, report inspection, and final summaries.
- Execution agent or approved runner: real Spectre/OCEAN/OpenBox execution
  through explicit commands or generated task packets.

## Real Evidence

Reference project:

```text
/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb
```

Fresh readiness evidence:

```text
project readiness: pass
readiness: ready_for_closeout_review
core ready: true
final summary ready: true
multi_testbench_netlists: pass - 3 testbench netlist bundles are ready
optimizer_final_summary: pass - final optimizer summary accepts real_093
```

Accepted optimizer result:

```text
run_id: real_093
action: accept_best_observed
global_optimum_claim: false
parameters: F=20, W=1.4u, L=30n, VB_LO=310m
metrics:
  BW=20427078494.05402
  MAX_GAIN=4.34394017341075
  NF_3G=11.79600779830737
  IIP3=2.739385297952587
  P1DB=-1.547739364191455
score:
  combined_score=0.7085522728550304
  weighted_score=0.8940502593720163
  bottleneck_score=0.6290531357763223
  bottleneck_metric=BW
status_counts:
  feasible=19
  constraint_failed=65
  metric_check_failed=16
```

Primary user-facing artifact:

```text
/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb/reports/optimizer_final_summary.md
```

## Ready For First Production Trial

The following are ready enough to use on the next real project:

- Strict file-based intake using `opt_requirement.md` and optional
  `constraints.md`.
- Safe import of full Maestro/ADE point-root netlist bundles.
- Single-testbench and multi-testbench candidate evaluation.
- OpenBox real optimizer execution through existing Spectre/OCEAN adapters.
- Candidate-level aggregation of child testbench metrics.
- Final reporting chain from run audit to final user summary.
- Offline project readiness check through `check-project-ready`.
- Visual and insight artifacts generated from evaluated optimizer samples.

## Boundaries

Keep these boundaries explicit in future work:

- The accepted point is best observed, not a global optimum certificate.
- Do not hand-pick optimizer points when validating optimizer behavior.
- Do not merge multiple testbenches into one synthetic Spectre deck.
- Do not parse PSF in Python.
- Do not rewrite approved OCEAN formulas.
- Do not commit raw `input.scs`, protected sidecars, PSF/raw data, or full
  Cadence logs.
- Do not expand the framework speculatively before a real project exposes the
  need.

## Next Work

The next development step should be driven by the next real optimization
project or by a concrete issue from production use.

Recommended next action:

```text
Onboard the next real project using docs/OPTIMIZER_PRODUCTION_QUICKSTART.md.
Run check-project-ready before and after the optimizer flow.
Only add features when the real workflow exposes a specific missing capability.
```

Possible future work, only when needed:

- continuation policy refinements for specific projects;
- richer final report formatting;
- additional user-facing requirement examples;
- production packaging/install cleanup.
