# Toolchain Execution Reference

Date: 2026-06-16

Mandatory reference before running Virtuoso, Spectre, OCEAN, OpenBox, native
TuRBO, license probes, or optimizer handoff commands in this repo.

## Canonical Repo

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

Release package:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1
```

## Current Product Command Contract

Initial real optimization:

```bash
.venv/bin/ic-opt PROJECT_DIR --real
```

Dry orchestration:

```bash
.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
```

Doctor gate:

```bash
.venv/bin/ic-opt PROJECT_DIR --doctor
```

Continuation:

```bash
.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Do not pass first-run workload/resource/optimizer overrides such as
`--max-evals`, `--batch-size`, `--parallel-jobs`, `--threads-per-run`,
`--optimizer-cpu-threads`, or `--strategy` to product `ic-opt`. Those values
come from `PROJECT_DIR/opt_requirement.md` and generated config.

## Product Environment

Install from the repo or release package root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements-product.txt
```

Required import check:

```bash
.venv/bin/python -c "import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, hermes_workflow; print('product optimizer env ok')"
```

Do not fall back to `/tmp/ic_auto_opt_openbox_spike/.venv` for product
acceptance. That older environment is historical debugging evidence only.

## Cadence Environment

`ic-opt` discovers the user-approved Cadence setup in this order:

1. explicit `--cadence-cshrc PATH`
2. `PROJECT_DIR/cadence_env.csh`
3. `IC_OPT_CADENCE_CSHRC`
4. `~/.ic-opt/cadence_env.csh`

Do not infer `.bashrc` or `.zshrc`. Do not hardcode a Spectre version.

## Real Workflow Evidence

After a real run, inspect files rather than chat claims:

```text
config/optimizer.yaml
config/spectre.yaml
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
state/optimizer_state.json
ledger/experiment_ledger.jsonl
runs/real/<run_id>/result_manifest.json
runs/real/<run_id>/metrics/metric_result_manifest.json
```

For multi-corner projects, also inspect parent aggregate manifests and confirm
each expected corner/testbench child appears under aggregate child evidence.

For B-10 traceability, confirm `command_trace` includes sanitized Spectre/OCEAN
argv summaries and does not include cshrc contents, SSH wrappers, or secrets.

For B-11 CPU-limit audit, confirm optimizer reports include
`runtime_thread_limits` with requested/effective thread evidence.

## Historical Command Notes

Older development logs in `docs/` may show low-level commands such as
`run-openbox-real --max-evals ...` or product commands that passed
`--max-evals`, `--batch-size`, and `--parallel-jobs`. Treat those as historical
evidence only. Current product usage is the requirement-driven `ic-opt`
contract above.
