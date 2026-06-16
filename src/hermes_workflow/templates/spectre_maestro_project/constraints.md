# Optimization Constraints And Guidance

This file is optional supervisor-agent guidance. It is not converted directly
into Spectre settings, OCEAN formulas, optimizer bounds, hard constraints, or
process corners.

Put machine-critical execution fields in `opt_requirement.md`.

Example guidance:

- Prefer feasible points that satisfy all listed metric constraints before
  comparing objective values.
- Stop and ask the user before widening the search space.
- Preserve approved OCEAN formula text exactly.
