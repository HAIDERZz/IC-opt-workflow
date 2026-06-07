# Release Notes v0.1.2

Date: 2026-06-08

## Summary

v0.1.2 is a license and packaging metadata patch release.

The project now uses the MIT License.

## Changes

- Added repository-level `LICENSE` with the MIT License.
- Removed `LICENSE_NOT_SELECTED.md`.
- Updated README and user-facing docs to state the MIT License.
- Updated `pyproject.toml` package metadata to version `0.1.2` and MIT license
  classifiers.

## Functional Changes

No optimizer behavior changed from v0.1.1.

The validated v0.1.1 real-tool flow remains the current acceptance evidence:

```text
clean clone
-> install requirements-product.txt
-> ic-opt --help
-> ic-opt PROJECT --doctor
-> ic-opt PROJECT --real --max-evals 100 --batch-size 10
-> ic-opt PROJECT --continue 40
```

## Boundaries

- Cadence Virtuoso, Spectre, OCEAN, PDK files, and simulator licenses are not
  included.
- Users must provide valid Maestro/ADE point roots and a working Cadence setup
  file such as `cadence_env.csh`.
- The optimizer reports the best observed feasible point. It does not claim a
  mathematical global optimum.
