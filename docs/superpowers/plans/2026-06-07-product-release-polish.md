# C-61 Product Release Polish

## Status

Completed, verified-only.

## Goal

Make the repository's top-level release entry match the product route proven by
C-60.

## Scope

- Replace the stale contract-only README with a product-facing README.
- Add a short release checklist.
- Pin product visualization/report dependencies that were previously left
  floating.
- Do not change optimizer behavior, formulas, testbench aggregation, or real
  tool adapters.

## Changes

- `README.md` now documents install, Cadence environment anchor setup, user
  project layout, `ic-opt PROJECT --real`, reports, proven C-60 evidence, and
  hard boundaries.
- `docs/PRODUCT_RELEASE_CHECKLIST.md` records product environment, user project
  contract, Cadence env anchor, dry gate, real acceptance, final user
  acceptance, and non-release files.
- `requirements-product.txt` pins `shap==0.49.1` and `lightgbm==4.6.0`, matching
  the product environment used by the C-60 real acceptance.

## Verification

- Product import check passed in the repo `.venv`.
- `ic-opt --help` and `hermes-workflow --help` are available from the repo
  `.venv`.
- Development cadence check passed.
- `git diff --check` passed.

## Route Audit

- Aligned with C-58 through C-60 product landing.
- No real-tool rerun was needed.
- No optimizer math, OCEAN formula, Spectre version, multi-testbench
  aggregation, product command behavior, or per-project venv policy changed.
