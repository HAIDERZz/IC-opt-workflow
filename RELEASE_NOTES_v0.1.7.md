# Release Notes v0.1.7

Date: 2026-06-16

## Product Contract

`opt_requirement.md` is the source for first-run optimizer and simulator
settings:

- budget and batch size
- candidate parallelism
- Spectre thread count
- optimizer CPU cap
- algorithm, strategy, initialization, and random seed
- output format
- process corners
- metric formulas
- objective and constraints
- retention policy

The product CLI keeps one value-changing continuation entry for existing runs:

```bash
ic-opt PROJECT_DIR --real --continue N
```

Use `--ssh-profile PROFILE` to select a remote execution profile. Use
`--cadence-cshrc PATH` only when the project does not already provide the
Cadence setup file.

## Optimizer Modes

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO fits spaces where legal variable steps are fine enough that snapping a
continuous candidate to the legal grid is a small perturbation, for example
about `0.1u`. Use `openbox_prf_eic` for coarse integer grids or duplicate-heavy
snapped spaces.

`random_baseline` is for diagnostics.

## Fixes And Evidence Added

- B-01: product CLI keeps first-run settings in `opt_requirement.md`; only
  continuation count is accepted from CLI.
- B-03/B-04: remote timeout and parent aggregate metadata were verified in the
  development workflow.
- B-05: `require_license_check` now runs real local/remote Spectre/license
  probes through doctor.
- B-07: Sobol initialization is seed-controlled, and OpenBox/native TuRBO
  workflows use requirement initialization.
- B-08: metric flow is psfxl-only and fails closed for unsupported output.
- B-10: Spectre/OCEAN result manifests include sanitized command traces.
- B-11: optimizer CPU thread-limit runtime audit is recorded.
- Parent aggregate manifests include child trace references for multi-testbench
  and multi-corner runs.

## Release Checks

- Full test suite passed in the development package before release packaging.
- Ruff passed.
- `git diff --check` passed.
- Release examples were regenerated from a verified Mixer requirement and
  checked with current requirement intake. Placeholder path failures are
  expected until users replace `maestro_point_root`.

## Boundaries

Cadence Virtuoso, Spectre, OCEAN, PDK files, simulator licenses, and user
Maestro/ADE result directories are not included. Users must provide valid
Maestro/ADE point roots and a working Cadence setup file.

Optimizer reports identify the best observed feasible candidate. They do not
claim a mathematical global optimum.
