# Optimizer production quickstart

Use this path for a real Maestro-exported Spectre/OCEAN optimization project.

## 1. Install the product environment

From the release root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Check the entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## 2. Prepare the project

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

`opt_requirement.md` is the machine-readable optimization request. It supplies
budget, batch size, Spectre resources, optimizer CPU cap, algorithm, strategy,
initialization, output format, testbenches, process corners, metrics,
objective, and constraints.

For each testbench, run one known-good Maestro/ADE point first. Put the point
root in `opt_requirement.md`; it must contain:

```text
<maestro_point_root>/netlist/input.scs
```

## 3. Configure Cadence

Provide a `csh`/`tcsh` setup file through one of:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

The setup must expose `spectre`, `ocean`, and license tools.

## 4. Run

Doctor gate:

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

Real run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

Continuation:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Remote run:

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

## 5. Read the reports

Start with:

```text
reports/optimizer_decision_report.md
reports/optimizer_run_report.json
reports/project_doctor_report.json
reports/license_probe_report.json
```

For real Spectre/OCEAN evidence, inspect:

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner runs, inspect parent aggregate manifests.

## 6. Agent use

Give the agent:

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

The agent should run the product CLI and verify artifacts before reporting
success.
