# Optimization Task

This project is driven by `opt_requirement.md` and the generated files under `config/`.

This project directory was rendered from a template, so the `ic-opt` commands
below are shown by their bare command name; run them as `./.venv/bin/ic-opt`
from the tool checkout root, or activate that virtual environment first, so
`ic-opt` resolves on `PATH`.

## Getting Started

1. Read `OPT_REQUIREMENT_README.md` in this directory first. It is the
   authoritative contract for every field in `opt_requirement.md`.
2. Pick the closest of the eleven `opt_requirement*.md` templates in this
   directory and copy it to `opt_requirement.md`, then replace all private
   paths, formulas, model sections, variable ranges, fixed points, and
   circuit-specific values.
3. Choose `mode: optimize` (optimizer-driven search over Design Variables) or
   `mode: fix_run` (fixed-point Spectre/OCEAN characterization) in the
   `Workflow` section, or omit `Workflow` for a legacy optimize requirement.
4. Run `ic-opt <project> --doctor` to check project and optimizer/toolchain
   readiness before any real run. The lower-level `hermes-workflow`
   commands (`check-requirement`, `prepare-from-requirement`, `validate`,
   `check-project-ready`) validate the requirement/config parsing layer only;
   they are not a substitute for the doctor gate.
5. Run `ic-opt <project> --real` for the first run, and
   `ic-opt <project> --real --continue N --ssh-profile <profile>` for an
   approved continuation of an existing optimizer project.

Keep first-run optimizer settings in `opt_requirement.md`. Use the `ic-opt`
CLI only for workflow actions such as doctor checks, real runs, and approved
continuation; it does not reread a changed `opt_requirement.md` after the
first run.

## Project File Guide

- `opt_requirement.md` -- the machine-checked contract for this run. Edit
  this before a first run; it is not reread on continuation.
- `OPT_REQUIREMENT_README.md` -- the authoritative field-by-field contract
  reference for `opt_requirement.md`.
- `CIRCUIT_KNOWLEDGE.md` -- optional agent scratch notes: circuit-specific
  interpretation recorded during execution. Never a source of machine
  behavior.
- `FAILURE_PLAYBOOK.md` -- optional agent scratch notes: project-specific
  recovery notes after a doctor check or real run reports an actionable
  failure.
- `constraints.md` -- optional human/supervisor guidance. It is not
  converted into Spectre settings, OCEAN formulas, optimizer bounds, or
  machine Constraints; see the `## Constraints` section of
  `opt_requirement.md` for enforced thresholds.
