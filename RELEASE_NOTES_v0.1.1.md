# Release Notes v0.1.1

Date: 2026-06-08

## Summary

v0.1.1 is the first clean-install release candidate validated from GitHub on a
real multi-testbench Spectre/OCEAN optimization flow.

The intended user flow is:

```bash
git clone git@github.com:HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .

./.venv/bin/ic-opt /path/to/project --doctor
./.venv/bin/ic-opt /path/to/project --real --max-evals 100 --batch-size 10
./.venv/bin/ic-opt /path/to/project --continue 40
```

## Highlights

- Improved README for IC users who are not Python package specialists.
- Added `ic-opt PROJECT --doctor` for lightweight project and environment
  diagnostics before running real tools.
- Added `ic-opt PROJECT --continue M` for user-style continuation after an
  existing optimizer run.
- Hardened continuation so it inherits prior optimizer-history resource settings
  by default, preventing accidental `parallel_jobs` drift.
- Clarified doctor output after an optimizer run so continuation-ready projects
  are reported as `ready_for_continuation_or_closeout_review`.
- Updated agent-facing docs and runtime starter assets to use the product CLI
  flow.

## Real-Tool Acceptance Evidence

This release was validated from a fresh GitHub clone in a clean product virtual
environment.

Validated flow:

```text
clean clone
-> install requirements-product.txt
-> ic-opt --help
-> ic-opt PROJECT --doctor
-> ic-opt PROJECT --real --max-evals 100 --batch-size 10
-> ic-opt PROJECT --continue 40
```

Final acceptance evidence:

```text
acceptance_status: accepted
evaluations: 140
status_counts:
  constraint_failed: 95
  feasible: 29
  metric_check_failed: 16
issues: []
warnings: []
parallel_jobs_counts: {"12": 140}
doctor_status: pass
doctor_project_ready: ready_for_continuation_or_closeout_review
```

Recommended best-observed point from the validation project:

```text
run: real_066
parameters: {"F": "26", "L": "40n", "VB_LO": "310m", "W": "1u"}
```

## Boundaries

- Cadence Virtuoso, Spectre, OCEAN, PDK files, and licenses are not included.
- Users must provide valid Maestro/ADE point roots and a working Cadence setup
  file such as `cadence_env.csh`.
- The optimizer reports the best observed feasible point. It does not claim a
  mathematical global optimum.
- No open-source license has been selected yet. Keep the repository private or
  add a real `LICENSE` before public reuse or redistribution.
