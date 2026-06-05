# Toolchain Execution Reference

Date: 2026-06-05

This is the mandatory reference for real tool execution in
`ic-auto-opt-workflow`.

Read this before running Virtuoso, Spectre, OCEAN, OpenBox, native TuRBO, or any
optimizer handoff command.

The purpose is to stop repeating the same failures:

- running real Cadence inside a restrictive sandbox;
- running OpenBox from a venv that cannot import OpenBox;
- running Hermes from a venv that cannot import Hermes workflow tooling;
- reusing stale optimizer workspaces with old ledger/state;
- doing long fake-run ladders before validating the real path.

## Canonical Repo

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Branch:

```text
plan-a-hermes-file-contract-mvp
```

## Environment Rules

### Project Development Venv

Use this for normal repository development, tests, docs checks, and contract-only
Hermes commands:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv
```

Known use:

```bash
.venv/bin/hermes-workflow validate PROJECT_DIR
.venv/bin/hermes-workflow package PROJECT_DIR
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
.venv/bin/hermes-workflow check-optimizer-run PROJECT_DIR
.venv/bin/hermes-workflow summarize-optimizer-run PROJECT_DIR
.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
python3 tools/check_development_cadence.py
python3 -m pytest -q
python3 -m ruff check src tests tools
```

Do not assume this venv can run OpenBox. As of C-34, this venv did not import
OpenBox. Installing OpenBox here may downgrade or conflict with the current
numeric stack.

### OpenBox Production Execution Venv

Use this for OpenBox real optimizer execution:

```text
/tmp/ic_auto_opt_openbox_spike/.venv
```

Known contents after C-34:

- editable OpenBox from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box
```

- editable Hermes workflow tooling from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Required import check:

```bash
/tmp/ic_auto_opt_openbox_spike/.venv/bin/python -c "import openbox, hermes_workflow.openbox_backend; print('openbox hermes env ok')"
```

Preferred project gate after C-36:

```bash
.venv/bin/hermes-workflow check-toolchain-env --openbox-venv /tmp/ic_auto_opt_openbox_spike/.venv --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --report /tmp/toolchain_environment_report.json
```

This checks the OpenBox venv, OpenBox/Hermes imports in the same Python
environment, the `hermes-workflow` script in that venv, and the Cadence cshrc.
It does not run Spectre, OCEAN, Virtuoso, or an optimizer loop.

Use this venv by putting it first in `PATH`:

```bash
setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH
```

Do not silently fall back from OpenBox to native TuRBO if this venv is missing
or broken. Fix the OpenBox/Hermes execution environment first.

### Cadence Environment

Cadence cshrc:

```text
/home/zzchen/cadence_ic231_env.csh
```

Spectre/OCEAN/OpenBox real execution command shape:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_c34/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow run-openbox-real PROJECT_DIR --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Keep `MPLCONFIGDIR` set to a writable `/tmp` directory for real OpenBox runs.
Without it, OpenBox/Matplotlib may still import but can emit cache-directory
warnings and slow down process startup.

`+mt` / `threads_per_run` and run-level parallelism are different:

- `threads_per_run` maps to Spectre `+mt` for one Spectre process.
- `parallel_jobs` is the maximum number of concurrent Spectre runs.

For the accepted inverter flow:

```text
preset=ax
threads_per_run=10
parallel_jobs=10
output_format=psfxl
```

## Sandbox Rule

Real Cadence execution must not be treated as a normal sandboxed command.

When using Codex tooling, real commands that launch Spectre/OCEAN/OpenBox
workers must run through an approved non-sandbox/escalated path. Earlier
sandboxed runs produced invalid Spectre pipe/socket failures.

Do not count sandboxed Spectre failures as toolchain evidence.

Allowed normal-sandbox work:

- reading files;
- editing docs/code;
- running unit tests;
- generating task packets;
- running contract-only `check-*`, `summarize-*`, and `finalize-*` reports.

Needs non-sandbox/escalated execution:

- `run-openbox-real`;
- `run-native-turbo` when it launches real Spectre/OCEAN;
- direct `spectre`;
- direct `ocean`;
- `virtuoso-bridge-lite` real bridge actions;
- SSH/remote tool execution.

## Canonical Successful References

### Spectre + OCEAN Backend

Reference evidence:

```text
docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/
docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/
```

Use these as proof that OCEAN can evaluate approved formulas on Maestro
point-level PSF and standalone Spectre replay PSF.

Do not change formulas to compensate for adapter bugs.

### OpenBox Real Handoff

Reference note:

```text
docs/debug/2026-06-05-c34-production-openbox-handoff-success.md
```

Successful workspace:

```text
/tmp/ic_auto_opt_c34_clean2/bridge_test_inv
```

Successful result:

```text
backend: openbox
execution_mode: real
evaluations: 100
feasible: 43
constraint_failed: 51
metric_check_failed: 6
real_check_failed: 0
best_observed: real_071
```

Successful closeout:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c34_clean2/bridge_test_inv
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c34_clean2/bridge_test_inv
.venv/bin/hermes-workflow finalize-optimizer-run /tmp/ic_auto_opt_c34_clean2/bridge_test_inv
.venv/bin/hermes-workflow optimizer-status /tmp/ic_auto_opt_c34_clean2/bridge_test_inv
```

All passed. `global_optimum_claim=false`.

Latest fresh packet/status handoff smoke:

```text
docs/debug/2026-06-05-c45-fresh-optimizer-status-handoff-drill.md
```

This C-45 smoke used a fresh workspace and the updated task packet with
`optimizer-status` in `audit_commands`.

Latest real-scale packet/status handoff:

```text
docs/debug/2026-06-05-c46-real-scale-optimizer-status-handoff.md
```

This C-46 run used a fresh workspace, the updated task packet with
`optimizer-status`, and completed 100 real OpenBox/Spectre/OCEAN evaluations.

## Fresh Workspace Preparation

Do not rerun production optimizer acceptance in a stale project with old
`ledger/`, `state/`, `reports/`, or `runs/`.

For a fresh production-style optimizer handoff, preserve:

```text
config/
netlists/
```

Then generate:

```bash
.venv/bin/hermes-workflow validate PROJECT_DIR
.venv/bin/hermes-workflow package PROJECT_DIR
.venv/bin/hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
```

The fresh workspace must contain:

```text
execution_package/execution_manifest.json
execution_package/OPTIMIZER_EXECUTION_TASK.md
execution_package/optimizer_execution_manifest.json
supervisor_instruction.json
```

If `supervisor_instruction.json` is copied from a known-good approved project,
the `approved_config_hashes` must exactly match
`execution_package/execution_manifest.json`.

Do not copy:

```text
ledger/
state/
reports/
runs/
```

unless the task is explicitly a continuation run that is designed to preserve
optimizer state.

## OpenBox Real Run Command

Use the generated task packet command. The C-34 accepted command was:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_c34/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow run-openbox-real /tmp/ic_auto_opt_c34_clean2/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

After it finishes, do not trust exit status alone. Run:

```bash
.venv/bin/hermes-workflow finalize-optimizer-run PROJECT_DIR
```

Acceptance requires:

- finalize status pass;
- optimizer run accepted;
- completion status pass;
- insight status pass;
- reports and SVGs generated.

## Native TuRBO Real Run Command

Native TuRBO remains available and must not be deleted or silently substituted
for OpenBox.

Command shape:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; .venv/bin/hermes-workflow run-native-turbo PROJECT_DIR --parallel --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Use this only when the user explicitly selects native TuRBO or when a plan says
the current task is native TuRBO acceptance.

## Fake Run Rule

Fake runs are allowed only to check contracts, CLI wiring, schema shape, or unit
behavior before a real run.

Do not spend many cycles on fake runs when the feature's value depends on
real Cadence/OpenBox behavior.

Default rule:

- At most one focused fake/local smoke per new command path.
- Then run the smallest meaningful real practice flow.
- For optimizer backend acceptance, meaningful means a real optimizer-guided run,
  not hand-picked points.

Fake run outputs must never override real evidence.

## Common Failure Table

| Symptom | Root Cause | Correct Fix |
| --- | --- | --- |
| `OpenBox is not installed` | Running OpenBox from project `.venv` instead of the OpenBox/Hermes venv | Use `/tmp/ic_auto_opt_openbox_spike/.venv` or build a stable OpenBox/Hermes execution venv |
| `ModuleNotFoundError: pydantic` in OpenBox venv | OpenBox venv lacks Hermes workflow dependencies | Install `ic-auto-opt-workflow` editable into the OpenBox venv |
| `ledger already contains candidate_id` | Reused stale optimizer workspace with old ledger/state | Rebuild a fresh workspace without old `ledger/`, `state/`, `reports/`, `runs/` |
| `execution manifest is missing` | Fresh workspace skipped `hermes-workflow package` | Run `package` before `package-optimizer-task` |
| `supervisor instruction is missing` | Fresh workspace lacks approved `supervisor_instruction.json` | Generate approval through normal flow or copy only when config hashes match |
| Spectre pipe/socket errors in sandbox | Real Cadence run executed in restrictive sandbox | Rerun through approved non-sandbox/escalated path |
| OCEAN scalar non-scalar/failed metric | Candidate/tool produced invalid scalar for approved formula | Record as candidate-level `metric_check_failed`; do not rewrite formula in Python |

## Never Do These

- Do not hand-pick optimizer points for backend acceptance.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not flatten Maestro/ADE netlist layout.
- Do not silently fall back from OpenBox to TuRBO.
- Do not commit raw `input.scs`, `ade_e.scs`, PSF/raw, or full Cadence logs.
- Do not treat chat prose or command exit status as acceptance evidence.
