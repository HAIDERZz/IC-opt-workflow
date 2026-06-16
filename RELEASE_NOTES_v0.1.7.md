# Release Notes v0.1.7

Date: 2026-06-16

## Current Product Contract

- Initial real optimization reads machine-critical settings only from
  `opt_requirement.md` / generated config:
  `max_evaluations`, `batch_size`, `parallel_jobs`, `threads_per_run`,
  `optimizer_cpu_threads`, optimizer strategy, initialization, process corners,
  output format, retention policy, metric formulas, and constraints.
- Product CLI continuation keeps one budget delta:
  `ic-opt PROJECT --real --continue N`.
- Do not pass initial-run workload/resource/optimizer overrides such as
  `--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads`, or
  `--strategy` to `ic-opt PROJECT --real`.

## New/Updated Capabilities

- Multi-corner real optimization is configured in `opt_requirement.md` under
  `Process Corners`. No `--multi-corner` CLI switch exists.
- Release examples include:
  - `examples/spectre_maestro_project/opt_requirement.multi_corner.md`
  - `examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`
- Supported OpenBox strategy combinations:
  - `algorithm: openbox`, `strategy: openbox_auto`
  - `algorithm: openbox`, `strategy: openbox_gp_eic`
  - `algorithm: openbox`, `strategy: openbox_prf_eic`
- Native TuRBO is supported as `algorithm: turbo`,
  `strategy: turbo_trust_region` for mostly continuous trust-region search.
- `docs/OPTIMIZER_ALGORITHM_MODES.md` explains when to use OpenBox auto, GP+EIC,
  PRF+EIC, TuRBO, and random baseline.
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md` explains multi-corner aggregation
  and what the optimizer sees.

## Fixed Bugs And Contract Hardening

- B-01: removed product CLI strategy override from the initial-run contract.
  Strategy now comes from `opt_requirement.md`.
- B-03/B-04: remote timeout and parent aggregate simulator metadata are carried
  from request/prepared Spectre settings instead of stale defaults.
- B-05: `require_license_check` is enforced by local/remote doctor license probe.
  The probe uses csh-compatible syntax and records `license_probe_report.json`.
- B-07: optimizer `initialization` is passed through to OpenBox and native
  TuRBO. Sobol initialization is deterministic for the same seed and changes
  for different seeds.
- B-08: `output_format` contract is fail-closed to `psfxl`; `psfascii` is not a
  supported real metric flow.
- B-10: local/remote child Spectre/OCEAN artifacts persist sanitized
  `command_trace` in `result_manifest.json` and `metric_result_manifest.json`.
- Parent aggregate traceability: multi-testbench/multi-corner parent aggregate
  manifests now index child sanitized command traces.
- B-11: optimizer CPU thread limit runtime audit records requested/effective
  threads, environment variables, threadpool state, and separate
  `transport_mode` for local vs remote workflows.

## Dependencies

- Product requirements install both optimizer vendors:
  - `vendor/open-box`
  - `vendor/TuRBO`
- Product requirements include TuRBO/Sobol/runtime-audit dependencies:
  `scipy`, `threadpoolctl`, `torch`, and `gpytorch`.

## Validation Summary

- Dev package full pytest: `1075 passed, 13 warnings`.
- Dev package ruff: `All checks passed!`.
- Release package full pytest: `1075 passed, 13 warnings`.
- Release package ruff: `All checks passed!`.
- Dev/release `src/hermes_workflow` and `tests` are synced, excluding cache and
  local state directories.

## Boundaries

- Cadence Virtuoso, Spectre, OCEAN, PDK files, and simulator licenses are not
  included.
- Users must provide valid Maestro/ADE point roots and a working Cadence setup
  file such as `cadence_env.csh`.
- The optimizer reports the best observed feasible point under the configured
  objective/policy. It does not claim a mathematical global optimum.
