# IC Auto Opt Workflow

Hermes-side file contracts for IC auto optimization on top of `virtuoso-bridge-lite`.

Hermes validates five structured YAML files, builds execution packages, prepares safe Spectre netlist templates, renders deterministic dry-run candidates, writes preflight health reports, and emits first-run supervisor instructions. It does not parse `USER_TASK.md`, invoke Claude CLI, run Virtuoso, run Spectre, or run a real optimizer loop.

## MVP CLI

```bash
hermes-workflow init projects/bridge_test_inv
hermes-workflow validate projects/bridge_test_inv
hermes-workflow package projects/bridge_test_inv
# Execution agent exports or places projects/bridge_test_inv/netlists/exported/input.scs
hermes-workflow prepare-netlist projects/bridge_test_inv
hermes-workflow dry-run projects/bridge_test_inv
hermes-workflow preflight-health projects/bridge_test_inv
hermes-workflow approve projects/bridge_test_inv
```

The `approve` command only approves the first real run when config validation, Hermes netlist preparation, Hermes dry-run, and Hermes-written preflight health all pass.
