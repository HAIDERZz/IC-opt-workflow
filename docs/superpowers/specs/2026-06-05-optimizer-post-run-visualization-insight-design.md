# Optimizer Post-Run Visualization And Insight Report Design

Date: 2026-06-05

## Status

Design scope for C-31.

## Context

C-25 accepts completed optimizer artifacts and C-26 writes a concise completion
decision. The next user-facing gap is a visual post-run report:

```text
accepted optimizer artifacts
-> static plots
-> observed variable/result relationship summary
-> supervisor-readable Markdown/JSON report
```

This report is intentionally post-run. It must not run during the optimizer
loop, must not launch real tools, and must not make accepted optimization runs
fail because optional visualization dependencies are missing.

## Scope

C-31 adds one read-only report command:

```bash
hermes-workflow visualize-optimizer-run PROJECT_DIR
```

It reads existing optimizer artifacts and writes:

```text
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_visuals/convergence.svg
reports/optimizer_visuals/status_distribution.svg
reports/optimizer_visuals/parameter_objective_scatter.svg
```

The MVP uses standard-library SVG generation. It does not require matplotlib,
OpenBox HTML, SHAP, LightGBM, pyrfr, a browser, or a GUI.

## Insight Semantics

The report may summarize observed relationships, but it must not claim causal
truth or global optimality.

Examples:

- `FN` has positive observed correlation with objective.
- `WP` has negative observed correlation with `fall`.
- Correlation is weak or insufficient data.

The report must label these as observed correlations from evaluated samples.

## Advanced Surrogate Visualization

OpenBox supports advanced HTML visualization from an OpenBox `History`, with
optional surrogate verification and SHAP importance. That path is valuable but
has extra dependencies and currently requires a persisted/reconstructed OpenBox
history. C-31 records this as a future optional add-on, not as a hard dependency.

The MVP report includes an `advanced_surrogate_visualization` status field:

```json
{
  "status": "not_generated",
  "reason": "C-31 MVP uses dependency-light static plots; OpenBox History/SHAP integration is a future add-on."
}
```

## Non-Goals

- Do not run Virtuoso, Spectre, OCEAN, SSH, or virtuoso-bridge.
- Do not change optimizer algorithms.
- Do not change OpenBox or TuRBO candidate generation.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not generate raw Cadence artifacts.
- Do not require browser or GUI access.
- Do not add broad dashboard/service/database infrastructure.

## Acceptance Criteria

- `visualize-optimizer-run` reads backend-neutral and legacy native artifacts
  through the existing artifact loader.
- It writes JSON, Markdown, and SVG outputs.
- The convergence SVG shows objective and best-so-far trend.
- The status SVG shows evaluated status distribution.
- The parameter/objective SVG shows static scatter panels for evaluated
  parameters.
- The JSON report includes best observed candidate, status counts, plot paths,
  and observed variable/target correlations.
- Missing or insufficient data fails closed with clear issues.
- No real tools are run.

## Route Audit

- Active top-level direction: lightweight, practice-first workflow around
  proven real-tool execution.
- Alignment: C-31 adds user-facing interpretation after accepted optimizer
  artifacts exist; it does not alter execution or optimization behavior.
- Drift: none intended. OpenBox advanced surrogate visualization remains a
  future optional report layer.
