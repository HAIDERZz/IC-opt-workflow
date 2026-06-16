# Role model and terminology

This release uses a file-based product workflow.

```text
User -> opt_requirement.md -> ic-opt CLI -> Spectre/OCEAN/optimizer -> artifacts -> user or agent review
```

## User

The user owns the circuit intent and approves the machine-critical inputs in
`opt_requirement.md`: variables, metrics, constraints, objective, simulator
resources, optimizer settings, and process corners.

## Agent

An agent may help operate the workflow. The recommended agent instruction is
`skills/ic-opt/SKILL.md`.

The agent may:

- read `opt_requirement.md`;
- run `ic-opt PROJECT_DIR --doctor`;
- run `ic-opt PROJECT_DIR --real`;
- run `ic-opt PROJECT_DIR --real --continue N`;
- inspect reports and manifests;
- explain the selected candidate and warnings.

The agent must not:

- invent candidate points;
- rewrite OCEAN formulas;
- parse PSF in Python;
- change search space, resources, strategy, initialization, or process corners
  outside `opt_requirement.md`;
- treat chat text as proof when artifacts show failure.

## Product CLI

`ic-opt` is the product entrypoint. It reads the project files, runs validation,
launches real workflow steps, and writes reports.

## Artifacts

The workflow accepts results through files:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

Multi-testbench and multi-corner runs also write parent aggregate manifests.

## Best observed result

The optimizer reports the best observed feasible candidate under the configured
objective and process-corner policy. This is not a proof of global optimum.
