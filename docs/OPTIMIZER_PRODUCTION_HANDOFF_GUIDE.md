# Optimizer Production Handoff Guide

Use this guide when handing a real IC optimization project to an operator or
agent.

## Product Commands

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

Initial-run optimizer, resource, Spectre, metric, retention, and process-corner
values come from `PROJECT_DIR/opt_requirement.md` and generated config. Do not
ask an operator or agent to supply those values on the CLI.

## Agent Role

The agent may read `skills/ic-opt/SKILL.md`, run the product CLI, and inspect
artifacts. It must not choose candidate points, rewrite formulas, parse PSF in
Python, or change the search space.

## Required Evidence

Do not accept a real run from prose. Inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner runs, inspect parent aggregate manifests.

Artifacts must show algorithm, strategy, initialization, random seed, budget,
batch size, parallelism, Spectre threads, optimizer CPU cap, process corners,
`output_format: psfxl`, license probe behavior, and sanitized Spectre/OCEAN
`command_trace`.

## Optimizer Modes

Set the strategy in `opt_requirement.md`:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO works best when legal variable steps are fine enough that snapping to the
legal grid is a small perturbation, for example about `0.1u`.

## Fail-Closed Conditions

Stop and report failure when any of these are true:

- requirement/config mismatch
- license probe failure when `require_license_check: true`
- missing child or aggregate manifests
- missing `command_trace` in real Spectre/OCEAN artifacts
- missing CPU thread-limit audit when `optimizer_cpu_threads` is set
- report presents the selected point as a proven global optimum
