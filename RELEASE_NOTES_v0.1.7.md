# Release notes v0.1.7

Date: 2026-06-16

## Product contract

`opt_requirement.md` is the only source for initial-run optimizer and simulator
settings. This includes budget, batch size, candidate parallelism, Spectre
thread count, optimizer CPU cap, algorithm, strategy, initialization, random
seed, output format, process corners, metric formulas, objective, constraints,
and retention policy.

The product CLI keeps one budget delta for existing runs:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Use `--ssh-profile PROFILE` to select a remote execution profile. Use
`--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup file.

## Main changes

- Added real local and remote doctor gates with Spectre/license probe reports.
- Tightened metric flow to `output_format: psfxl`.
- Added sanitized Spectre/OCEAN `command_trace` to child and aggregate
  manifests.
- Added runtime audit for optimizer CPU thread limits.
- Added requirement-driven OpenBox initialization pass-through.
- Fixed Sobol initialization so `random_seed` affects native TuRBO Sobol
  samples while keeping same-seed reproducibility.
- Added multi-testbench and multi-corner release examples.
- Updated `skills/ic-opt/SKILL.md` to use the current `ic-opt` product CLI.

## Optimizer modes

Production strategies:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic OpenBox mode. `random_baseline` is for
diagnostics. TuRBO fits search spaces where legal variable steps are fine enough
that snapping continuous candidates to the legal grid is a small perturbation,
for example about `0.1u`.

## Release checks

- Release package test suite: `1075 passed, 13 warnings`.
- Ruff: all checks passed.
- Dev and release source/tests were synchronized before packaging.

## Boundaries

Cadence Virtuoso, Spectre, OCEAN, PDK files, and simulator licenses are not
included. Users must provide valid Maestro/ADE point roots and a working
Cadence setup file.

The optimizer reports the best observed feasible point under the configured
objective and process-corner policy. It does not claim a mathematical global
optimum.
