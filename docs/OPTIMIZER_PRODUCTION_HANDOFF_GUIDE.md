# Optimizer Production Handoff Guide

Date: 2026-06-16

This guide describes the current product handoff model. Historical task-packet
commands in older notes may show `--max-evals`, `--batch-size`, or
`--parallel-jobs`; those are not product first-run inputs anymore.

## Product Boundary

Product first run:

```bash
ic-opt PROJECT_DIR --real
```

Product continuation:

```bash
ic-opt PROJECT_DIR --real --continue N
```

All first-run optimizer, resource, Spectre, metric, retention, and process
corner values come from `PROJECT_DIR/opt_requirement.md` and generated config.
Do not ask the execution agent to invent or override these values on the CLI.

Low-level `hermes-workflow` commands are maintainer tools for inspecting a
specific stage. They are not the user-facing product interface and should not be
used to bypass the requirement contract.

## Roles

Supervisor agent:

- validates the project contract;
- runs dry orchestration and doctor gates;
- dispatches the runtime-native execution agent when needed;
- accepts results only through Hermes reports and manifests;
- decides whether to accept the best observed candidate or continue.

Execution agent:

- runs the generated task package exactly when a task package is used;
- does not hand-pick optimizer points;
- does not change resource, budget, strategy, initialization, corner, or metric
  values outside the requirement/config contract;
- returns manifests, reports, ledger, state, and failure evidence.

## Preflight

Before any real run, verify:

- `PROJECT_DIR/opt_requirement.md` is current and reviewed.
- `PROJECT_DIR/cadence_env.csh`, `~/.ic-opt/cadence_env.csh`, or
  `IC_OPT_CADENCE_CSHRC` points to the user-approved Cadence setup.
- `ic-opt PROJECT_DIR --doctor` passes when `require_license_check: true`.
- `ic-opt PROJECT_DIR --real --dry-orchestration` passes before a long run.
## Backend Selection

Backend choice is made in `opt_requirement.md`. Production strategy
choices are peers:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic OpenBox mode when the user has
not selected a strategy. `random_baseline` is diagnostic only. Use TuRBO
only when legal variable steps are fine enough that snapping is a small
perturbation, for example about `0.1u`; avoid it for coarse steps,
finger-count-like integers, and categorical choices.

Use `docs/OPTIMIZER_ALGORITHM_MODES.md` when explaining tradeoffs.
Use `docs/OPTIMIZER_ALGORITHM_MODES.md` when explaining tradeoffs.

## Multi-Corner Handoff

Multi-corner execution is configured only in `opt_requirement.md` under
`Process Corners`. There is no product `--multi-corner` switch.

Use these release examples:

```text
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

Read `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md` for the candidate/result
aggregation flow that the optimizer sees.

## Result Evidence

Do not accept a real run from prose. Inspect:

```text
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
state/optimizer_state.json
ledger/experiment_ledger.jsonl
```

For real Spectre/OCEAN traceability, inspect child and aggregate manifests:

```text
runs/real/<run_id>/result_manifest.json
runs/real/<run_id>/metrics/metric_result_manifest.json
```

For CPU-limit audit, inspect `runtime_thread_limits` in optimizer reports.

## Failure Handling

Treat these as fail-closed:

- requirement/config mismatch;
- license probe failure when `require_license_check: true`;
- missing or stale result manifests;
- missing child `command_trace` in real Spectre/OCEAN artifacts;
- multi-corner parent aggregate missing expected children;
- optimizer reports missing runtime thread-limit audit when CPU limit is set;
- any report that claims global optimum rather than best observed evidence.
