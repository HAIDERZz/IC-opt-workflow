# Role Model And Terminology

This release uses a file-based product workflow:

```text
User -> opt_requirement.md -> ic-opt CLI -> Spectre/OCEAN/optimizer -> artifacts -> user or agent review
```

## User

The user owns circuit intent and approves machine-critical inputs in
`opt_requirement.md`: workflow mode, variables, metrics, constraints,
objective, fixed points, waveform exports, simulator resources, optimizer
settings, and process corners.

## Agent

The recommended agent instruction is `skills/ic-opt/SKILL.md`.

The agent may:

- read `opt_requirement.md`
- run `ic-opt PROJECT_DIR --doctor`
- run `ic-opt PROJECT_DIR --real`
- run `ic-opt PROJECT_DIR --real --continue N`
- inspect reports and manifests
- explain the selected candidate and warnings
- explain fix-run waveform CSV evidence and child failures

The agent must not:

- invent candidate points
- rewrite OCEAN formulas
- parse PSF in Python
- change search space, resources, strategy, initialization, or process corners
  outside `opt_requirement.md`
- treat chat text as proof when artifacts show failure

## Product CLI

`ic-opt` is the product entrypoint. It reads project files, runs validation,
launches real workflow steps, and writes reports.

## Artifacts

Workflow acceptance comes from files:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/fix_run_report.json
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

Multi-testbench and multi-corner runs also write parent aggregate manifests.

## Best Observed Result

Optimizer reports identify the best observed feasible candidate under the
configured objective and process-corner policy. This is not a proof of global
optimality.

## Fix-Run Result

Fix-run reports identify whether each requested fixed point and child
testbench/corner completed. They are characterization evidence, not optimizer
recommendations.
