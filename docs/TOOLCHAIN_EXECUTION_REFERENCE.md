# Toolchain Execution Reference

Use this before running Virtuoso, Spectre, OCEAN, OpenBox, native TuRBO,
license probes, or optimizer commands from the release package.

## Product Commands

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

## Fix-Run Workflow

Fix-run mode runs Spectre/OCEAN at user-specified design points without an
optimizer loop. The command is the same as the optimizer entry:

```bash
ic-opt PROJECT_DIR --real
```

The workflow inspects `Workflow.mode` in `opt_requirement.md`. When the mode
is `fix_run`, it dispatches the fix-run path instead of the optimizer loop.

### Requirement Sections

Fix-run requires these sections in `opt_requirement.md`:

```text
Workflow (mode: fix_run)
Project
Maestro Source
Design Variables
Spectre Settings
Fixed Points
Approval Checklist
```

At least one of `Metrics` or `Waveform Exports` must be present. `Optimizer
Settings`, `Constraints`, and `Objective` are not required.

### Fix-Run Evidence

After a fix-run, inspect:

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

Do not expect `optimizer.yaml`, `optimizer_state.json`, or
`optimizer_decision_report.md` in fix-run output.

For multi-corner fix-run, confirm each fixed point is evaluated at every
declared process corner and that per-corner manifests appear.
