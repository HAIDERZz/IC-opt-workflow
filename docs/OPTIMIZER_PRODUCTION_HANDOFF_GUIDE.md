# Optimizer production handoff guide

Date: 2026-06-16

This guide is for operators and agents running a real IC optimization project.
Use the product CLI first.

## Commands

First real run:

```bash
ic-opt PROJECT_DIR --real
```

Readiness check:

```bash
ic-opt PROJECT_DIR --doctor
```

Continuation:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Remote run:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

Initial-run optimizer, resource, Spectre, metric, retention, and process-corner
values come from `PROJECT_DIR/opt_requirement.md` and generated config. Do not
ask an agent or operator to supply those values on the CLI.

## Agent role

The agent may read `skills/ic-opt/SKILL.md`, run the product CLI, and inspect
artifacts. It should not choose candidate points, rewrite formulas, parse PSF in
Python, or change the search space.

## Required evidence

Do not accept a real run from prose. Inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner projects, inspect the parent aggregate
manifest as well.

Check that artifacts record the expected algorithm, strategy, initialization,
random seed, budget, batch size, parallelism, Spectre threads, optimizer CPU
cap, process corners, `output_format: psfxl`, license probe behavior, and
sanitized Spectre/OCEAN `command_trace`.

## Optimizer modes

Use the mode selected in `opt_requirement.md`:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO works best when legal variable steps are fine enough that snapping to the
legal grid is a small perturbation, for example about `0.1u`.

## Fail-closed conditions

Stop and report the artifact path when any of these appear:

- requirement/config mismatch;
- license probe failure when `require_license_check` is enabled;
- missing child or aggregate manifests;
- missing `command_trace` in real Spectre/OCEAN artifacts;
- missing CPU thread-limit audit when `optimizer_cpu_threads` is set;
- a report that presents the selected point as a proven global optimum.
