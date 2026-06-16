# Agent Optimizer Usage Manual

This manual describes how an agent should operate the current IC Auto Opt
product workflow. The product core is the shell CLI:

```bash
ic-opt PROJECT_DIR --real
```

The recommended agent path is to read `skills/ic-opt/SKILL.md`, operate the
product CLI, and inspect workflow artifacts before reporting success.

## 1. Project Inputs

Create one project directory:

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. `constraints.md` and `context/` are for
human guidance and supporting notes. Do not manually create generated
directories such as `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, or
`state/`; the workflow creates them.

## 2. Requirement Contract

`opt_requirement.md` is the only product entry for initial-run machine-critical
settings:

- Maestro/ADE point roots and testbench routes
- OCEAN metric expressions
- design variables, ranges, and legal steps
- constraints, objective, and FoM
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- retention policy
- license probe requirement
- Process Corners and multi-corner policies

Use only the product commands in this manual. The CLI keeps one budget delta
for continuation:

```bash
ic-opt PROJECT_DIR --real --continue N
```

All other values stay inherited from `opt_requirement.md` and generated config.

## 3. Product Commands

Local doctor:

```bash
ic-opt PROJECT_DIR --doctor
```

Local real run:

```bash
ic-opt PROJECT_DIR --real
```

Remote doctor:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
```

Remote real run:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

Remote continuation:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

Dry orchestration check:

```bash
ic-opt PROJECT_DIR --real --dry-orchestration
```

`--ssh-profile PROFILE` selects the remote execution profile. It is not an
optimizer or resource override. `--cadence-cshrc PATH` may be used when the
project does not already provide the Cadence setup path.

## 4. Agent Behavior

The agent should:

- read `opt_requirement.md` before running;
- run doctor before real execution when validating an environment;
- use the product CLI rather than low-level developer commands;
- inspect reports and manifests before saying a run passed;
- report command status, evaluation counts, selected run id, selected or worst
  corner when present, recommended parameters, metrics, warnings, and artifact
  paths.

The agent must not:

- ask the user to restate formulas, variable ranges, Spectre resources,
  optimizer settings, or process corners in chat;
- hand-pick candidate points;
- rewrite OCEAN formulas;
- parse PSF in Python;
- change the search space, objective, constraints, or metric routes;
- treat a zero exit code as full acceptance without artifact inspection.

## 5. Optimizer Modes

Explain these production strategies as peer choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` is the default automatic mode. `random_baseline` is diagnostic.
TuRBO is a fit when legal variable steps are fine enough that snapping
continuous candidates to the legal grid is a small perturbation, for example
about `0.1u`; avoid it for coarse steps, finger-count-like integers,
categorical choices, and duplicate-heavy snapped spaces.

## 6. Multi-Corner Runs

Multi-corner optimization is configured in the Process Corners section of
`opt_requirement.md`. Use the release examples:

```text
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

The agent should inspect aggregate artifacts and report the objective policy,
constraint policy, selected run, corner-level metrics, and worst-case/all-corner
constraint result.

## 7. Artifact Acceptance Checklist

For real workflow acceptance, inspect at least:

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

For multi-testbench or multi-corner projects, also inspect the parent aggregate
manifest. Confirm that requirement values reached artifacts and execution:
algorithm, strategy, initialization, random seed, budget, batch size,
parallelism, Spectre threads, optimizer CPU cap, process corners,
`output_format: psfxl`, license probe behavior, and sanitized Spectre/OCEAN
`command_trace`.
