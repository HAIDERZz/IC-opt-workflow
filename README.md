# IC Auto Opt Workflow

Hermes-side file contracts for IC auto optimization on top of `virtuoso-bridge-lite`.

The first MVP validates five structured YAML files, builds Claude execution packages, reads Claude preflight reports, and writes first-run supervisor instructions. It does not parse `USER_TASK.md`, invoke Claude CLI, run Virtuoso, run Spectre, or run an optimizer loop.
