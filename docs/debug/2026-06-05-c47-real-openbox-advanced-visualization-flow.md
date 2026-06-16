# C-47 Real OpenBox Advanced Visualization Flow

> Historical command notice: command examples in this debug note may show old
> workload/resource CLI flags. Current release product first runs read those
> values only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

Date: 2026-06-05

## Scope

This note records the first full real-tool optimizer flow that completed with
OpenBox official advanced visualization artifacts enabled.

The run used the existing accepted inverter project baseline, preserved the
native Maestro/ADE netlist layout, and did not hand-pick candidates.

## Workspace

```text
/tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
```

The workspace was prepared from the C-34 accepted baseline by copying only:

- `config/`
- `netlists/`
- `execution_package/`
- `supervisor_instruction.json`

Old `ledger/`, `state/`, `reports/`, and `runs/` were not copied.

## Environment

OpenBox execution venv:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

Cadence cshrc:

```text
/home/zzchen/cadence_ic231_env.csh
```

Advanced visualization dependencies were verified before execution:

```text
openbox, hermes_workflow.openbox_backend, shap, lightgbm, pyrfr, pyrfr.regression
```

## Real Execution

Execution shape:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_real_flow_t77ky7/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow run-openbox-real /tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Spectre/OpenBox resource settings:

```text
preset=ax
threads_per_run=10
parallel_jobs=10
batch_size=10
max_evals=100
output_format=psfxl
```

## Results

Closeout commands passed:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
.venv/bin/hermes-workflow finalize-optimizer-run /tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
.venv/bin/hermes-workflow optimizer-status /tmp/ic_auto_opt_real_flow_t77ky7/bridge_test_inv
```

Summary:

```text
evaluations: 100
feasible: 43
constraint_failed: 51
metric_check_failed: 6
real_check_failed: 0
decision: accept_best_observed
confidence: medium
global_optimum_claim: false
continuation recommended: false
plateau detected: true
```

Best observed candidate:

```text
run_id: real_071
FN: 12
WN: 2.7u
FP: 7
WP: 0.7u
rise: 69.604322 ps
fall: 56.781892 ps
DC: 326.978183 uW
objective: 4.1325534822170306e-14
```

## OpenBox Advanced Visualization

Manifest:

```text
reports/openbox_advanced_visualization_manifest.json
```

Manifest result:

```text
status: generated
includes:
- objective_and_constraint_history
- surrogate_fit_verification
- parameter_importance
```

HTML artifact:

```text
reports/openbox_advanced_visualization/history/hermes_openbox_real/hermes_openbox_real_2026-06-05-20-31-16-757633.html
```

JSON artifact:

```text
reports/openbox_advanced_visualization/history/hermes_openbox_real/visualization_data_hermes_openbox_real_2026-06-05-20-31-16-757633.json
```

LightGBM emitted repeated `No further splits with positive gain` warnings while
training the visualization/importance model. This did not block report
generation and was not a Spectre/OCEAN/OpenBox flow failure.

## Boundary

- No candidate was hand-picked.
- No metric formula was changed.
- No PSF or waveform database was parsed by Hermes/Python.
- No OCEAN formula was rewritten.
- No raw Cadence artifacts were committed.

## Conclusion

C-47 is now proven in a full real OpenBox/Spectre/OCEAN optimizer flow. The
advanced visualization route generated official OpenBox HTML/JSON artifacts
with surrogate verification and parameter importance present.
