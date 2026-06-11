# Optimization Constraints And Guidance

This file is optional human/operator/agent guidance. It is not converted directly
into Spectre settings, OCEAN formulas, optimizer bounds, or hard constraints.

Put machine-critical execution fields in `opt_requirement.md`.

Example guidance:

- Prefer feasible points that satisfy all listed metric constraints before
  comparing FoM.
- Stop and ask the user before widening the search space.
- Preserve approved OCEAN formula text exactly.
