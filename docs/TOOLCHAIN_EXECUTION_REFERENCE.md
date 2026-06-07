# Toolchain Execution Reference

This document records the public v0.1 rules for running real Cadence tools.

## Required User Environment

Users must provide a shell setup file that makes Spectre and OCEAN available.
The recommended project-local name is:

```text
PROJECT_DIR/cadence_env.csh
```

The product CLI also accepts:

```bash
ic-opt PROJECT_DIR --real --cadence-cshrc /path/to/cadence_env.csh
```

Do not hardcode a Spectre version in prompts, docs, or scripts. Tool versions
belong to the user's Cadence environment.

## Python Environment

Use one product-level Python environment for this repository:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .
```

Do not create a separate virtualenv inside each optimization project.

## Real Run Sandbox Boundary

Real Spectre/OCEAN runs need access to process services, sockets, pipes, and
licenses. If a sandboxed run fails with messages such as "cannot create pipe" or
"can't create server socket", treat it as an execution-environment failure, not
as evidence that the optimizer contract is broken.

## Standard Product Command

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --max-evals 100 --batch-size 10
```

Optional explicit environment:

```bash
./.venv/bin/ic-opt PROJECT_DIR \
  --real \
  --max-evals 100 \
  --batch-size 10 \
  --cadence-cshrc /path/to/cadence_env.csh
```

## Continuation

Continuation should inherit project resource settings:

```bash
./.venv/bin/hermes-workflow continue-openbox-real PROJECT_DIR \
  --additional-evals 40 \
  --batch-size 10 \
  --cadence-cshrc /path/to/cadence_env.csh
```

Do not add `--parallel-jobs` during continuation unless the user intentionally
requests a resource change. Mixed resource histories are rejected by acceptance
checks because they are harder to compare.

## Closeout Reports

The product flow writes reports under:

```text
PROJECT_DIR/reports/
```

Primary files:

```text
optimizer_flow_run_report.json
optimizer_decision_report.md
optimizer_insight_report.md
optimizer_final_summary.md
```
