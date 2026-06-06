# Multi-Testbench Candidate Evaluation Implementation Plan

> **For agentic workers:** Use the normal project cadence, but keep this flow
> practice-first and narrow. Do not build a broad scheduler or optimizer
> framework. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the current single-testbench candidate evaluation route so one
optimizer candidate can run multiple preserved Maestro/ADE testbench bundles and
produce one aggregated metric observation.

**Active spec:** `docs/superpowers/specs/2026-06-06-multi-testbench-candidate-evaluation-design.md`

## Task 1: Contract Shape And Intake Mapping

- [x] Add the smallest schema/config support for named testbenches.
- [x] Extend requirement intake so `opt_requirement.md` can define either the
      existing single `Maestro Source` block or a new `testbenches` list.
- [x] Add metric routing by `metric.testbench`.
- [x] Preserve single-testbench backwards compatibility.
- [x] Verify with focused intake/schema tests only.

Status: complete, verified-only. `config/testbenches.yaml` is optional and only
emitted for multi-testbench intake. Single-testbench requirement projects keep
the existing `project_config.yaml`/`netlists/exported/` route unchanged.

Acceptance:

- Single-testbench C-49 fixtures still validate.
- A multi-testbench fixture renders `testbenches.yaml` and metrics with routing
  keys.
- Missing or duplicate testbench ids fail closed.
- Metrics referencing unknown testbench ids fail closed.

## Task 2: Multi-Testbench Netlist Import And Render

- [x] Import each named `maestro_point_root/netlist/` into a namespaced project
      bundle.
- [x] Render the same candidate parameters into every named testbench template.
- [x] Keep the existing single-testbench netlist layout working.
- [x] Reject unsafe symlinks with the same C-49 policy.

Status: complete, verified-only. Multi-testbench requirement preparation now
imports each point-root into `netlists/testbenches/<id>/exported/`, templates
each child deck into `netlists/testbenches/<id>/templates/template.scs`, and
keeps the primary legacy `netlists/exported/` + `netlists/templates/` path for
existing commands. `dry-run` renders the lower-bound candidate into
`runs/dry_run/testbenches/<id>/input.scs` for every named testbench.

Acceptance:

- Namespaced exported bundles keep regular sidecars.
- Rendered child `input.scs` files contain the same approved candidate values.
- No PSF parsing, formula rewriting, or synthetic testbench merge is introduced.

## Task 3: Child Run Manifests And Aggregated Metric Manifest

- [x] Define child run directories under `runs/real/<run_id>/testbenches/<id>/`.
- [x] Let each child produce its own result and metric manifests.
- [x] Aggregate child manifests into the existing top-level
      `result_manifest.json` and `metrics/metric_result_manifest.json`.
- [x] Preserve partial child metrics for diagnosis while failing the candidate
      if required metrics are missing or invalid.

Status: complete, verified-only. `aggregate_multi_testbench_run()` now combines
per-testbench child result/metric manifests into the existing candidate-level
`result_manifest.json` and `metrics/metric_result_manifest.json`. Child
references are preserved in optional `child_results` and
`child_metric_results` fields, while existing `check-real-run` and
`check-metric-results` continue to operate on the aggregate files.

Acceptance:

- One fake multi-testbench candidate can aggregate two child metric manifests.
- `check-real-run` and `check-metric-results` see the candidate-level aggregate.
- Failure classes distinguish metric failure from real-tool failure.

## Task 4: Single-Candidate Real Multi-Testbench Smoke

- [x] Use the existing Mixer CG/NF point-root and one additional user-provided
      point-root.
- [x] Run one approved candidate through both Spectre/OCEAN child runs.
- [x] Produce one aggregated metric manifest.
- [x] Run supervisor checks on the aggregate.

Status: complete, verified-only. The user-provided multi-testbench Mixer
project at `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` ran real
multi-testbench Spectre/OCEAN candidates with child runs for `cg_nf`, `iip3`,
and `p1db`. The best observed candidate `real_068` has all three child result
manifests succeeded, all three child metric manifests succeeded, and an
aggregated candidate-level metric manifest containing `BW`, `MAX_GAIN`,
`NF_3G`, `IIP3`, and `P1DB`.

Acceptance:

- Both child runs preserve native Maestro/ADE netlist layout.
- The aggregate check passes when both child metrics are scalar.
- The global `parallel_jobs` cap is respected across child jobs.

## Task 5: Optimizer Integration Gate

- [x] Route OpenBox/native TuRBO candidate observations through the
      multi-testbench evaluator when the project has multiple testbenches.
- [x] Run a tiny real optimizer smoke only after Task 4 passes.
- [x] Keep `optimizer_cpu_threads`, `parallel_jobs`, and `threads_per_run`
      semantics separate in reports.

Status: complete, verified-only. The OpenBox real optimizer route completed
100 real multi-testbench evaluations in 10 batches of 10 for
`/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb`. Final reports were refreshed
after the optimizer process finished:

- `reports/optimizer_run_report.json`: `status=completed`,
  `evaluation_count=100`.
- `reports/optimizer_evaluations.jsonl`: 100 rows with
  `19 feasible`, `65 constraint_failed`, and `16 metric_check_failed`.
- `reports/optimizer_run_acceptance_report.json`: accepted.
- `reports/optimizer_completion_report.json`: `accept_best_observed`,
  `confidence=medium`, `global_optimum_claim=false`.
- `reports/optimizer_finalize_report.json`: passed.
- `reports/optimizer_insight_report.md`: regenerated from the final
  100-evaluation state.

Best observed:

```text
run_id: real_068
F=26, W=1u, L=40n, VB_LO=310m
BW=19171311625.11458 Hz
MAX_GAIN=4.242801858394763 dB
NF_3G=11.81241967045868 dB
IIP3=3.206487765822459 dBm
P1DB=-0.8997623115419788 dBm
objective=-0.0503357919658288
```

Acceptance:

- At least one small real optimizer batch uses multi-testbench candidate
  evaluation without hand-picked points.
- Reports make clear that the result is best observed, not global optimum.
- No broad scheduler/framework rewrite is added.

## C-50 Closeout

C-50 is complete, verified-only. The original first-evidence target was a
single candidate with two testbenches; the final evidence is stronger: a real
three-testbench Mixer OpenBox/Spectre/OCEAN optimizer run completed 100
candidate evaluations without merging testbenches, parsing PSF, rewriting
OCEAN formulas, or multiplying `parallel_jobs` per testbench.

## Post-C50 Reporting Refinements

Status: complete through C-51, verified-only.

- Objective expressions now support safe `min()`, `max()`, and `ln()` for
  offline report re-scoring.
- `optimizer_insight_report` now includes all-evaluable FoM ranking,
  configured-objective ranking, and bottleneck/weighted normalized-margin
  plot data.
- `hermes-workflow decide-optimizer-run PROJECT_DIR` now writes
  `reports/optimizer_decision_report.json` and
  `reports/optimizer_decision_report.md`.
- The decision report is supervisor-facing: recommended run, basis,
  action, confidence, best-observed/no-global-optimum boundary, bottleneck
  metric, status counts, and next steps.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` generated
  the C-51 decision report without rerunning Spectre/OCEAN. It recommends
  feasible `real_093` under the normalized FoM, with action
  `accept_best_observed_or_continue`, confidence `medium`,
  `global_optimum_claim=false`, and bottleneck `BW`.
- `hermes-workflow record-optimizer-decision PROJECT_DIR` now writes
  `reports/optimizer_supervisor_decision.json` and
  `reports/optimizer_supervisor_decision.md`.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` recorded
  `accept_best_observed` for feasible `real_093` as the current optimizer
  result. This is still a best-observed decision, not a global-optimum claim,
  and it did not rerun Spectre/OCEAN.
- `hermes-workflow write-optimizer-final-summary PROJECT_DIR` now writes
  `reports/optimizer_final_summary.json` and
  `reports/optimizer_final_summary.md`.
- The final summary is user-facing and gathers accepted run, parameters,
  metrics, score summary, bottleneck, status counts, visual links, source
  reports, next steps, and boundaries from existing artifacts. The real Mixer
  multi-testbench project generated this report for accepted `real_093`
  without rerunning Spectre/OCEAN.
- C-54 added the production landing quickstart and offline readiness check.
  `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md` documents the supported user path
  from project creation through final summary. `hermes-workflow
  check-project-ready PROJECT_DIR` writes
  `reports/project_readiness_report.json` and checks requirement/config/netlist
  readiness plus final summary availability without running real tools.
- Real project `/home/zzchen/spectre_opt_prj/Mixer_opt_muti_tb` passed
  `check-project-ready` with `readiness=ready_for_closeout_review`, three
  testbench netlist bundles, and final summary accepting `real_093`.
