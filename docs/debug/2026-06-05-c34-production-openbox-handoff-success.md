# C-34 Production OpenBox Handoff Success

Date: 2026-06-05

## Scope

C-34 completed one production-style OpenBox optimizer handoff using the C-33
guide and the existing Hermes Spectre/OCEAN execution path.

## Environment Fixes Required

The first attempt stopped before real tools because OpenBox was not installed in
the active project `.venv`.

The successful run used the existing OpenBox spike venv:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

That venv already contained editable OpenBox from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box
```

Hermes workflow tooling was installed editable into the same venv before the
successful run. This avoided downgrading the project `.venv` numeric stack.

## Workspace Fixes Required

The first clean workspace attempt copied only `config/` and `netlists/`, then
failed because `execution_package/execution_manifest.json` was missing.

The successful workspace was:

```text
/tmp/ic_auto_opt_c34_clean2/bridge_test_inv
```

It was prepared from the accepted C-29 project by preserving:

- `config/`
- `netlists/`
- generated `execution_package/execution_manifest.json`
- generated `execution_package/OPTIMIZER_EXECUTION_TASK.md`
- generated `execution_package/optimizer_execution_manifest.json`
- approved `supervisor_instruction.json` with config hashes matching the new
  `execution_manifest.json`

Old `ledger/`, `state/`, `reports/`, and `runs/` were not copied.

## Execution Command

The successful execution used the same OpenBox production command shape:

```bash
hermes-workflow run-openbox-real /tmp/ic_auto_opt_c34_clean2/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

## Results

- Backend: `openbox`
- Execution mode: `real`
- Evaluations: `100`
- Batches: `10`
- Max batch worker count: `10`
- Feasible: `43`
- Constraint failed: `51`
- Metric check failed: `6`
- Real check failed: `0`

Best observed candidate:

```text
run_id: real_071
FN: 12
WN: 2.7u
FP: 7
WP: 0.7u
rise: 69.60432235471526 ps
fall: 56.78189223340601 ps
DC: 326.9781831574406 uW
objective: 4.1325534822170306e-14
```

## Supervisor Audit

`check-optimizer-run`:

```text
optimizer run accepted
```

`summarize-optimizer-run`:

```text
decision: accept_best_observed
confidence: medium
global_optimum_claim: false
```

`finalize-optimizer-run`:

```text
status: pass
best_observed_run_id: real_071
```

Generated reports include:

- `reports/optimizer_run_report.json`
- `reports/optimizer_evaluations.jsonl`
- `reports/optimizer_run_acceptance_report.json`
- `reports/optimizer_completion_report.json`
- `reports/optimizer_insight_report.json`
- `reports/optimizer_insight_report.md`
- `reports/optimizer_visuals/convergence.svg`
- `reports/optimizer_visuals/status_distribution.svg`
- `reports/optimizer_visuals/parameter_objective_scatter.svg`
- `reports/optimizer_finalize_report.json`

## Conclusion

C-34 production OpenBox handoff is accepted, with the important caveat that the
execution environment must expose both OpenBox and Hermes workflow tooling.

The best candidate is the best observed candidate, not a global optimum claim.
