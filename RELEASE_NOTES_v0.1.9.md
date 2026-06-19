# IC Auto Opt Workflow v0.1.9

Release date: 2026-06-20

v0.1.9 adds OpenBox history warm-start support and the optimizer insight report
upgrade, while preserving the v0.1.8 fix-run workflow.

## History Warm Start

- Added optional `History Warm Start` requirement section for new optimize
  projects that reference previous same-circuit project directories.
- Added generated `config/history_warm_start.yaml`.
- Added `reports/history_warm_start_audit.json` and
  `reports/history_warm_start_audit.md`.
- Added `openbox.history_warm_start` reporting in
  `reports/optimizer_run_report.json`.
- Constrained IC projects use history as OpenBox initial configurations.
- Unconstrained single-objective OpenBox projects may use OpenBox transfer
  learning history.
- Native TuRBO does not consume history warm-start data.

History warm-start is optimize-only. It is not a CLI flag, is not supported for
fix-run, and must not be combined with `--continue N`.

## Optimizer Insight Report

- Added `reports/optimizer_insight_report.html` as the main reader-facing
  optimizer report.
- Added actual measured metrics for the best observed point.
- Added report-layer raw-metric Pareto/trade-off summaries.
- Added history reuse summaries with clear confidence boundaries.
- Added advisory-only OpenBox space-compression dry-run summaries.
- Kept dense JSON/JSONL artifacts as the source of truth for agent analysis.

The Pareto/trade-off section does not enable OpenBox multi-objective optimizer
mode, and the space-compression section does not change optimizer execution.

## Requirement Examples

- Added `examples/spectre_maestro_project/opt_requirement.history_warm_start.md`.
- Restored multi-testbench examples to real validated Mixer requirements with
  `cg_nf`, `iip3`, and `p1db` testbenches.
- Preserved metric ownership for `BW`, `MAX_GAIN`, `NF_3G`, `IIP3`, and `P1DB`.
- Mirrored all requirement examples into packaged templates under
  `src/hermes_workflow/templates/spectre_maestro_project/`.

Private local paths in examples are replaced with placeholders.

## Carried Forward From v0.1.8

- Local and remote fix-run workflow support.
- Fix-run child-level parallelism through `Spectre Settings.parallel_jobs`.
- Waveform CSV export manifests for fix-run child runs.
- Requirement template `opt_requirement.fix_run.md`.
- Requirement-driven local and remote optimization.
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO strategy support.
- Multi-testbench and multi-corner optimization support.
- `output_format: psfxl` metric flow.
- Real license probe doctor gate.
- Sanitized Spectre/OCEAN command trace artifacts.
- Optimizer CPU thread-limit runtime audit.
