# Toolchain execution reference

Date: 2026-06-16

Use this before running Virtuoso, Spectre, OCEAN, OpenBox, native TuRBO, license
probes, or optimizer commands from the release package.

## Product commands

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
ic-opt PROJECT_DIR --real --dry-orchestration
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`opt_requirement.md` supplies initial-run budget, batch size, Spectre
parallelism, Spectre thread count, optimizer CPU cap, algorithm, strategy,
initialization, process corners, output format, metric formulas, objective, and
constraints.

## Product environment

Install from the release root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements-product.txt
```

Import check:

```bash
.venv/bin/python -c "import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, hermes_workflow; print('product optimizer env ok')"
```

## Cadence environment

`ic-opt` discovers the user-approved Cadence setup in this order:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

Do not infer shell startup files. Do not hardcode a Spectre version.

## Real workflow evidence

After a real run, inspect files:

```text
config/optimizer.yaml
config/spectre.yaml
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
state/optimizer_state.json
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-corner projects, inspect parent aggregate manifests and confirm each
expected corner/testbench child appears in aggregate evidence.

For command traceability, confirm `command_trace` includes sanitized
Spectre/OCEAN argv summaries and does not include cshrc contents, SSH wrappers,
or secrets.

For CPU-limit audit, confirm optimizer reports include `runtime_thread_limits`
with requested and effective thread evidence.
