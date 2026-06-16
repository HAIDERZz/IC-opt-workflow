# IC Auto Opt Workflow

`ic-auto-opt-workflow` runs requirement-driven IC optimization for
Maestro-exported Spectre/OCEAN projects. It prepares simulation inputs, runs
approved Spectre/OCEAN evaluations, aggregates metrics, and writes optimizer
reports for local or remote execution.

## Product Entry

Run a real optimization:

```bash
ic-opt /path/to/project --real
```

Check readiness:

```bash
ic-opt /path/to/project --doctor
```

Continue an existing run with more evaluations:

```bash
ic-opt /path/to/project --real --continue N
```

Run on a configured remote profile:

```bash
ic-opt --ssh-profile PROFILE /remote/project --real
```

`--continue N` is the only CLI value that changes the number of new
simulations. Initial-run budget, batch size, parallelism, Spectre thread count,
optimizer CPU cap, algorithm, strategy, initialization, process corners, output
format, retention, objective, constraints, and metric routes come from
`opt_requirement.md`.

## Project Layout

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. Use `constraints.md` for human guidance
and `context/` for notes, screenshots, or prior reports. Generated directories
such as `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, and `state/`
are created by the workflow.

## Requirement Scope

`opt_requirement.md` defines:

- Maestro/ADE point roots and testbench routes
- OCEAN metric expressions
- design variables, legal ranges, and steps
- objective, FoM, and constraints
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- license probe, retention, and artifact policy
- Process Corners and multi-corner policies

Release examples:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

## Optimizer Modes

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic mode. `random_baseline` is diagnostic.
TuRBO is a fit when legal variable steps are fine enough that snapping
continuous candidates to the legal grid is a small perturbation, for example
about `0.1u`; avoid it for coarse steps, finger-count-like integers,
categorical choices, and duplicate-heavy snapped spaces.

See `docs/OPTIMIZER_ALGORITHM_MODES.md`.

## Install

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Expected entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## Cadence Environment

The Cadence/Spectre/OCEAN setup is user supplied. Configure it through one of:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

Use doctor before real runs when validating a project or environment:

```bash
ic-opt /path/to/project --doctor
```

When `require_license_check` is enabled in `opt_requirement.md`, doctor runs the
real Spectre/license probe and writes `reports/license_probe_report.json`.

## Agent Use

For agent-assisted operation, give the agent:

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

The agent should operate the same product CLI and inspect artifacts before
reporting success. The release package keeps one agent skill entry:
`skills/ic-opt/SKILL.md`.

## Workflow Evidence

For real workflow acceptance, inspect:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

Multi-testbench and multi-corner runs also write parent aggregate manifests.
These artifacts record requirement pass-through, command traces, license probe
status, optimizer CPU thread-limit audit, selected candidate, and reported
metrics.

## Current Release

Version `0.1.7` includes:

- requirement-driven local and remote optimization;
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO;
- multi-testbench and multi-corner support;
- psfxl-only metric flow;
- real license probe doctor gate;
- sanitized Spectre/OCEAN command trace artifacts;
- optimizer CPU thread-limit runtime audit;
- release examples and agent skill guidance synchronized with the current CLI.

See `RELEASE_NOTES_v0.1.7.md` for the release summary.
