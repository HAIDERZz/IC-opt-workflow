# Release Notes v0.1.7

Date: 2026-06-16

## Current Product Contract

- Initial real optimization reads machine-critical settings only from
  `opt_requirement.md` / generated config: `max_evaluations`, `batch_size`,
  `parallel_jobs`, `threads_per_run`, `optimizer_cpu_threads`, optimizer
  strategy, initialization, process corners, output format, retention policy,
  metric formulas, and constraints.
- Product CLI continuation keeps one budget delta:
  `ic-opt PROJECT --real --continue N`.
- Do not pass initial-run workload/resource/optimizer overrides such as
  `--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads`, or
  `--strategy` to `ic-opt PROJECT --real`.

## Capabilities

- Multi-corner real optimization is configured in `opt_requirement.md` under
  `Process Corners`; no `--multi-corner` CLI switch exists.
- Release examples include:
  - `examples/spectre_maestro_project/opt_requirement.multi_corner.md`
  - `examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`
- Supported production strategy choices are peers:
  - `algorithm: openbox`, `strategy: openbox_gp_eic`
  - `algorithm: openbox`, `strategy: openbox_prf_eic`
  - `algorithm: turbo`, `strategy: turbo_trust_region`
- `openbox_auto` is the default automatic OpenBox mode when the user has not
  selected a strategy. `random_baseline` is diagnostic only.
- Use `turbo_trust_region` when legal variable steps are fine enough that
  snapping continuous TuRBO candidates is a small perturbation, for example
  about `0.1u`; avoid it for coarse steps, finger-count-like integers, and
  categorical choices.
- `docs/OPTIMIZER_ALGORITHM_MODES.md` explains strategy selection.
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md` explains multi-corner
  aggregation and what the optimizer sees.

## Fixed Bugs And Contract Hardening

- B-01: removed product CLI strategy override from the initial-run contract.
- B-03/B-04: remote timeout and parent aggregate simulator metadata are carried
  from requirement/config into real artifacts.
- B-05: `require_license_check` now runs real local/remote license probes and
  fails closed when required.
- B-07: optimizer `initialization` now passes through to OpenBox and native
  TuRBO, including seeded Sobol behavior.
- B-08: `output_format` contract is fail-closed to `psfxl`; `psfascii` is not
  accepted by product requirement intake.
- B-10: local/remote Spectre/OCEAN manifests include sanitized command traces.
- Parent aggregate traceability: multi-testbench/multi-corner parent manifests
  include child command-trace references.
- B-11: optimizer CPU thread-limit runtime audit records requested/effective
  threads, threadpool/Torch state, and local/remote transport mode.

## Dependencies

- `vendor/open-box`
- `vendor/TuRBO`
- TuRBO/Sobol/runtime-audit dependencies in product requirements:
  `scipy`, `threadpoolctl`, `torch`, and `gpytorch`.

## Validation Summary

- Dev full pytest: `1075 passed, 13 warnings`.
- Dev ruff: `All checks passed!`.
- Release package pytest: `1075 passed, 13 warnings`.
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
