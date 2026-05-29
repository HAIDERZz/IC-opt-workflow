# IC Auto Opt Workflow

Hermes-side file contracts for IC auto optimization on top of `virtuoso-bridge-lite`.

The first MVP validates five structured YAML files, builds Claude execution packages, reads Claude preflight reports, and writes first-run supervisor instructions. It does not parse `USER_TASK.md`, invoke Claude CLI, run Virtuoso, run Spectre, or run an optimizer loop.

## MVP CLI

```bash
hermes-workflow init projects/bridge_test_inv
hermes-workflow validate projects/bridge_test_inv
hermes-workflow package projects/bridge_test_inv
hermes-workflow approve projects/bridge_test_inv
```

The `approve` command only approves the first real run when config validation, netlist preparation report, dry-run report, and health check all pass.
