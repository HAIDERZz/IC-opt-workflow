# Toolchain Execution Reference

Use this before running Virtuoso, Spectre, OCEAN, OpenBox, native TuRBO,
license probes, optimizer commands, or fix-run commands from the release
package.

## Product Commands

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`opt_requirement.md` supplies workflow mode, initial-run budget, batch size,
Spectre parallelism, Spectre thread count, optimizer CPU cap, algorithm,
strategy, initialization, process corners, output format, metric formulas,
objective, constraints, fixed points, and waveform exports.

`--continue N` preserves the backend recorded by the project. Both OpenBox and
native TuRBO continuation are supported; enabled History Warm Start remains an
OpenBox-only new-project capability.

## Product Environment

Install from the release root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Import check:

```bash
./.venv/bin/python -c "import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, hermes_workflow; print('product optimizer env ok')"
```

The low-level `check-toolchain-env` command checks the environment containing
the invoked `hermes-workflow` unless `--openbox-venv PATH` is supplied. A
portable optimizer task package likewise omits the packaging machine's venv
path by default and records an explicit path only when requested.
Packaged post-run audit commands also record `--expected-backend`, so a task
cannot validate artifacts left by a different optimizer backend.
`package-optimizer-task` resolves its default backend from project configuration;
an explicit `--backend` must agree with that resolved backend.

## Cadence Environment

`ic-opt` discovers the user-approved Cadence setup in this order:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

Do not infer shell startup files. Do not hardcode a Spectre version.

## Real Workflow Evidence

After a real run, inspect:

```text
config/optimizer.yaml
config/spectre.yaml
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/fix_run_report.json
state/optimizer_state.json
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

For multi-corner projects, inspect parent aggregate manifests and confirm each
expected corner/testbench child appears in aggregate evidence.

For command traceability, confirm `command_trace` includes sanitized
Spectre/OCEAN argv summaries and does not include cshrc contents, SSH wrappers,
or secrets.

For CPU-limit audit, confirm optimizer reports include `runtime_thread_limits`
with requested and effective thread evidence.

For fix-run, confirm `reports/fix_run_report.json` reports
`workflow_mode: fix_run`, expected child counts, waveform CSV paths when
requested, and no optimizer state or optimizer decision report.
