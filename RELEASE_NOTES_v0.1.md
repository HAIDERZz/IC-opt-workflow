# Release Notes v0.1.x

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
python3.11 -m venv .venv
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
