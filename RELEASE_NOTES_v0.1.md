# Release Notes v0.1.x

## v0.1.6

Date: 2026-06-12

### Summary

v0.1.6 hardens product readiness checks and agent-facing diagnostics. Local
`ic-opt PROJECT --doctor` now uses the product doctor path directly, and
unsupported objective functions no longer produce duplicate unknown-metric
diagnostics.

### Changes

- Fixed local product CLI doctor routing:
  - `ic-opt PROJECT --doctor` now runs the product doctor directly.
  - Local doctor no longer falls through to optimizer execution or emits
    `optimize requires --real`.
  - Doctor remains a no-Spectre/no-OCEAN readiness check.
- Fixed objective semantic diagnostics:
  - unsupported function calls such as `eval(1)` now report
    `OBJECTIVE_UNSUPPORTED_FUNCTION` only;
  - unsupported function names are no longer also reported as unknown metrics.
- Updated README, Chinese user guide, production quickstart, troubleshooting,
  agent usage docs, and the platform-neutral `ic-opt` skill to clarify:
  - local doctor is standalone;
  - agents should prefer `structured_issues` over plain `issues`;
  - agents should not treat doctor failures as optimizer failures.

### Verification

- `tests/test_requirement_intake.py tests/test_product_cli.py`: 51 passed.
- Full test suite: 745 passed, 14 warnings.
- Ruff checks passed.
- `git diff --check` passed.
- Local CLI smoke confirmed `ic-opt PROJECT --doctor` no longer enters the
  optimizer path.

## v0.1.5

Date: 2026-06-12

### Summary

v0.1.5 improves real-run report readability and hardens remote SSH failure
handling. Optimizer visual reports now default to PNG, and remote users get
clearer guidance that high `parallel_jobs` values can overload SSH before they
improve optimization throughput.

### Changes

- Changed `reports/optimizer_visuals/` from SVG output to PNG output by
  default.
- Embedded PNG plots directly in `optimizer_insight_report.md`.
- Improved plot readability for real IC optimization reports:
  - all-evaluable FoM trend;
  - bottleneck-vs-weighted normalized score;
  - convergence and feasible convergence;
  - status distribution;
  - parameter-vs-objective scatter;
  - constraint margins.
- Added automatic cleanup of the old fixed-name SVG visual files when
  regenerating insight reports, so old projects do not show mixed SVG/PNG
  artifacts.
- Added `matplotlib` to the product dependency set.
- Hardened remote Spectre/OCEAN diagnostic and manifest behavior so SSH/tool
  failures are recorded as inspectable run artifacts instead of leaving missing
  manifests.
- Documented remote SSH concurrency guidance across README, user guide,
  troubleshooting guide, agent skill, and release checklist:
  `parallel_jobs` is candidate-level concurrency, not per-testbench
  concurrency; normal remote multi-testbench runs should start around 4-8.

### Verification

- Generated PNG reports from a real 100-evaluation Mixer multi-testbench run
  with 18 feasible points.
- Generated PNG reports from a real 150-evaluation remote Mixer run to confirm
  penalty/outlier clipping keeps plots readable.
- Targeted optimizer insight tests passed.
- Ruff checks passed for the modified insight-reporting code.
- Diff whitespace checks passed.

## v0.1.4

Date: 2026-06-09

### Summary

v0.1.4 adds the first productized remote SSH execution path. The optimizer and
OpenBox environment can run on a local Linux/macOS/Windows workstation, while
Spectre/OCEAN execute on a remote Linux EDA server through passwordless
OpenSSH.

### Changes

- Added `ic-opt --ssh-profile PROFILE PROJECT --doctor`.
- Added `ic-opt --ssh-profile PROFILE PROJECT --real ...`.
- Added `ic-opt --ssh-profile PROFILE PROJECT --continue M ...`.
- Reused the canonical local Spectre/OCEAN argv builders in remote mode so
  remote execution does not invent a separate simulator command path.
- Added remote artifact validation and diagnostic persistence for Spectre and
  OCEAN stdout/stderr/log/scalar artifacts.
- Mirrored remote reports to
  `~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/` while keeping
  reports on the remote project under `PROJECT/reports/`.
- Updated README and Chinese user guide with remote SSH, Windows, and macOS
  installation guidance.
- Updated the platform-neutral `ic-opt` agent skill with remote-mode operating
  rules.

### Verification

- Remote doctor passed on a real multi-testbench Mixer project.
- Remote real optimization passed for 80 evaluations.
- Remote continuation passed for 20 more evaluations, reaching 100 cumulative
  evaluations.
- The final accepted remote run contained 17 feasible, 67 constraint-failed,
  and 16 metric-check-failed evaluations.
- Targeted release regression tests passed for remote SSH, remote project
  preparation, remote Spectre/OCEAN adapter parity, product CLI remote routing,
  optimizer flow, requirement intake, OpenBox backend, and agent skill runtime.

## v0.1.3

Date: 2026-06-08

### Summary

v0.1.3 clarifies production user guidance and fixes maximize-style FoM reporting.

### Changes

- Documented how to find the correct Maestro/ADE `maestro_point_root` directory:
  use the leaf run directory containing both `netlist/` and `psf/`; verify that
  `<maestro_point_root>/netlist/input.scs` exists.
- Documented objective/FoM behavior:
  - `direction: minimize` means smaller user FoM is better.
  - `direction: maximize` means larger user FoM is better, while the optimizer
    internally minimizes `-FoM` for feasible candidates.
- Added simple and normalized weighted FoM examples for IC users.
- Updated the multi-testbench Mixer template to use a normalized bottleneck plus
  weighted higher-is-better FoM.
- Fixed optimizer insight reporting for `direction: maximize`: reports now keep
  user FoM and internal minimized objective separate, and rank all-evaluable FoM
  using the correct direction.

### Verification

- `tests/test_optimizer_insights.py`
- `tests/test_requirement_intake.py`
- `tests/test_product_cli.py`

Result: 42 tests passed.

## v0.1.0

Date: 2026-06-07

## Summary

v0.1.0 is the first packaged product snapshot of IC Auto Opt Workflow. It is
intended for real Cadence Spectre/OCEAN optimization practice using a structured
project directory and the `ic-opt` command.

## Included

- Product CLI: `ic-opt`.
- Lower-level workflow CLI: `hermes-workflow`.
- Structured `opt_requirement.md` intake.
- Single-testbench and multi-testbench Spectre/OCEAN project preparation.
- OpenBox real optimizer backend.
- Continuation support for additional evaluations.
- Optimizer decision, insight, final-summary, and visualization reports.
- Claude and OpenCode starter runtime assets.
- Product docs and beginner Chinese usage guide.
- Regression tests.

## Real-Tool Evidence Before Packaging

The development workspace validated:

- Fresh Mixer multi-testbench project from `opt_requirement.md` and
  `cadence_env.csh`.
- 100 real OpenBox/Spectre/OCEAN evaluations through `ic-opt`.
- Multi-testbench aggregation for CG/NF, IIP3, and P1dB.
- OpenBox advanced visualization generation.
- Continuation hardening up to 140 cumulative evaluations on the C-66 validation
  project.

## Important Boundaries

- The project depends on a working user Cadence environment.
- It does not ship Cadence, Spectre, OCEAN, PDK files, or simulator licenses.
- It does not claim global optimum.
- Public GitHub release still needs a selected LICENSE file.

## Recommended First User Flow

```bash
cd /path/to/ic-auto-opt-workflow-v0.1
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .

./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10

./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --max-evals 100 \
  --batch-size 10
```
