# Product Release Checklist

Use this checklist before treating `ic-auto-opt-workflow` as ready for another
user or another clean machine.

## 1. Current Product Contract

Initial real optimization is requirement driven. The only supported product
first-run command is:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

The only product CLI budget delta is continuation:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Do not document or use product first-run CLI overrides for `max_evaluations`,
`batch_size`, `parallel_jobs`, `threads_per_run`, `optimizer_cpu_threads`,
optimizer strategy, optimizer initialization, process corners, output format,
metric formulas, constraints, or retention policy. Those values must come from
`PROJECT_DIR/opt_requirement.md` and the generated `config/*.yaml` files.

## 2. Product Environment

Install the product environment from the release package:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Required dependency smoke:

```bash
./.venv/bin/python -c "import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, hermes_workflow; print('product optimizer env ok')"
```

Expected scripts:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

Do not use `/tmp/ic_auto_opt_openbox_spike/.venv` as a product dependency.

## 3. User Project Contract

The user project should contain only user inputs before the first run:

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

`constraints.md` and `context/` are optional. Generated directories such as
`config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, `state/`, and
`execution_package/` are created by Hermes workflow tooling.

The release includes current examples:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

## 4. Cadence Environment Anchor

The user supplies one Cadence cshrc anchor:

```text
PROJECT_DIR/cadence_env.csh
```

or:

```text
~/.ic-opt/cadence_env.csh
```

or:

```bash
export IC_OPT_CADENCE_CSHRC=/path/to/user/cadence_env.csh
```

Do not infer `.bashrc` or `.zshrc` automatically. Do not hardcode a Spectre
version in product docs or command examples.

## 5. Dry Orchestration Gate

Before a long real run on a new project, dry orchestration should pass:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
```

This should stop before real Spectre/OCEAN execution.

## 6. Real Product Acceptance

Run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

Acceptance requires:

- `reports/optimizer_flow_run_report.json` has `status=pass`.
- Evaluation count equals `optimizer.max_evaluations` from the requirement.
- Generated `config/optimizer.yaml` and `config/spectre.yaml` match the
  requirement values.
- Child result and metric manifests include sanitized `command_trace`.
- Multi-corner parent manifests include aggregate child command traces when
  the requirement enables process corners.
- Optimizer reports include runtime thread-limit audit when
  `optimizer_cpu_threads` is configured.
- `reports/optimizer_decision_report.md` recommends a best observed feasible
  candidate when feasible evidence exists.
- The workflow does not claim a mathematical global optimum.

## 7. Supported Optimizer Modes

Release-supported product modes are:

- `algorithm: openbox`, `strategy: openbox_auto`
- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`
- `algorithm: random`, `strategy: random_baseline` for diagnostic baseline use

Read `docs/OPTIMIZER_ALGORITHM_MODES.md` before recommending a mode.

## 8. Final User Acceptance

The optimizer flow stops before final user acceptance. Only after the user
accepts the recommended best-observed candidate should the operator record a
final decision:

```bash
./.venv/bin/hermes-workflow record-optimizer-decision PROJECT_DIR \
  --decision accept_best_observed \
  --reason "User accepted the current best observed optimizer result."
./.venv/bin/hermes-workflow write-optimizer-final-summary PROJECT_DIR
./.venv/bin/hermes-workflow check-project-ready PROJECT_DIR
```

Expected closeout readiness:

```text
project readiness: pass
readiness: ready_for_closeout_review
```

## 9. Files That Must Not Be Released

Do not commit or publish raw `input.scs`, protected sidecars, encrypted PDK
includes, PSF/raw simulator databases, full Cadence logs, user proprietary
Maestro point-root bundles, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`
unless the user explicitly approves a sanitized evidence release.
