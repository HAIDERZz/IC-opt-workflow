# C-47 OpenBox Advanced Visualization Artifact

Date: 2026-06-05

## Purpose

Add OpenBox official post-run visualization artifacts to the existing optimizer
workflow without changing Spectre/OCEAN execution, metric formulas, candidate
selection, or optimizer acceptance rules.

## Scope

- Generate OpenBox `History.visualize_html(...)` artifacts after an OpenBox run
  finishes.
- Keep `open_html=false`; reports are generated for later review, not opened
  during execution.
- Record a deterministic manifest at
  `reports/openbox_advanced_visualization_manifest.json`.
- Link the manifest and generated HTML/JSON from
  `reports/optimizer_run_report.json` and
  `reports/optimizer_insight_report.{json,md}`.
- Distinguish `generated`, `generated_partial`, `failed`, and `not_available`.

## Out Of Scope

- No real Spectre/OCEAN rerun.
- No PSF parsing.
- No OCEAN formula rewrite.
- No optimizer backend replacement.
- No custom surrogate/SHAP implementation.
- No live visualization server or browser auto-open.

## Implementation Notes

- The OpenBox advisor already remains in scope until
  `openbox_backend._run_openbox_batches` exits, so C-47 calls
  `advisor.get_history().visualize_html(...)` at final closeout.
- The report parser inspects OpenBox visualization JSON instead of trusting
  file existence alone.
- Full `generated` means all requested sections are present:
  objective/constraint history, surrogate verification, and parameter
  importance.
- If OpenBox creates HTML/JSON but omits parameter importance, the status is
  `generated_partial`.

## Evidence

- Unit coverage:
  - successful advanced artifact manifest;
  - dependency failure manifest;
  - partial advanced artifact manifest;
  - optimizer insight report links to OpenBox advanced visualization.
- Full test suite passed after implementation.
- OpenBox-only fake workflow probe generated official HTML/JSON and correctly
  reported `generated`.

## Known Toolchain Note

OpenBox 0.9 requires the older numeric stack. Do not install unpinned latest
`shap`; it upgrades `numpy`, `scipy`, `scikit-learn`, and `pandas` to versions
incompatible with OpenBox 0.9.

Current compatible OpenBox visualization dependency state:

- `numpy==1.26.4`
- `scipy==1.12.0`
- `scikit-learn==1.3.2`
- `pandas==2.1.4`
- `shap==0.44.1`
- `lightgbm==4.6.0`
- `swig==4.4.1`
- `pyrfr==0.9.0`

OpenBox 0.9 still imports `pyrfr` through its feature-importance package.
This was resolved without system package changes by installing PyPI `swig`
inside the OpenBox venv, then installing `pyrfr` with
`--no-build-isolation`. With `pyrfr` present, the C-47 OpenBox-only probe
records full `generated` status including parameter importance.

## Verification

```bash
/home/zzchen/.venvs/openclaw/bin/python -m pytest tests/test_openbox_backend.py tests/test_optimizer_insights.py tests/test_optimizer_finalize.py
/home/zzchen/.venvs/openclaw/bin/python -m pytest
/home/zzchen/.venvs/openclaw/bin/python -m ruff check src/hermes_workflow/openbox_backend.py src/hermes_workflow/optimizer_insights.py tests/test_openbox_backend.py tests/test_optimizer_insights.py
```
