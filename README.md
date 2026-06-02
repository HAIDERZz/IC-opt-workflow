# IC Auto Opt Workflow

Hermes workflow file contracts for IC auto optimization on top of `virtuoso-bridge-lite`.

Hermes workflow tooling validates five structured YAML files, builds execution packages, prepares safe Spectre netlist templates, renders deterministic dry-run candidates, writes preflight health reports, and emits first-run supervisor instructions. It does not parse `USER_TASK.md`, invoke Claude CLI, run Virtuoso, run Spectre, or run a real optimizer loop.

The role model is locked in `docs/ROLE_MODEL_AND_TERMINOLOGY.md`: the supervisor agent owns planning and decisions, Hermes workflow tooling owns deterministic file contracts and validation, and the execution agent owns approved Virtuoso/Spectre/OCEAN tool-side actions.

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
hermes-workflow prepare-real-run projects/bridge_test_inv
# Execution agent invokes the explicit C-7 adapter outside Hermes validators
python tools/run_spectre_ocean_adapter.py projects/bridge_test_inv --run-id real_001
# Execution agent runs the prepared deck outside Hermes and writes result_manifest.json
hermes-workflow check-real-run projects/bridge_test_inv
# Execution agent runs batch OCEAN outside Hermes and writes metric_result_manifest.json
hermes-workflow check-metric-results projects/bridge_test_inv
hermes-workflow record-real-result projects/bridge_test_inv --run-id real_001
```

The `approve` command only approves the first real run when config validation, Hermes workflow netlist preparation, Hermes workflow dry-run, and Hermes-written preflight health all pass.
`prepare-real-run` prepares `runs/real/real_001/` after approval, but it does not run Spectre, Virtuoso, subprocesses, or an optimizer loop.
`check-real-run` validates the returned file contract only. It does not launch Spectre, parse simulator databases, compute real metrics, append ledger rows, or advance optimizer state.
Metric extraction is contract-only in Hermes workflow tooling. The execution agent runs standalone Spectre and batch OCEAN outside Hermes workflow tooling, then writes `metric_result_manifest.json`. Hermes workflow tooling validates formula identity, scalar values, and artifact paths; it does not parse PSF or reimplement Calculator/OCEAN formulas.
After both handoff checks pass, `record-real-result` appends a real evaluation row and updates optimizer state from checked contract files only. It does not run Spectre, run OCEAN, parse PSF, or generate the next candidate.

The C-7 execution-side adapter is an explicit tool boundary, not a Hermes validator:

```bash
python tools/run_spectre_ocean_adapter.py projects/bridge_test_inv --run-id real_001
```

The supervisor agent should still run `check-real-run` and `check-metric-results` after the adapter returns. Adapter success alone is not workflow success.
