# Product Release Checklist

Use this checklist before treating `ic-auto-opt-workflow` as ready for another
user or another clean machine.

Important boundary: this checklist validates the implemented shell automation
core and C-65 runtime-native adapter assets. The implemented shell entrypoint is
`ic-opt PROJECT_DIR --real`; agent runtimes should install their own adapter and
then use `/ic-opt PROJECT_DIR --real` so the current runtime supervisor can
delegate to a same-runtime execution subagent. The historical C-64
`--execution-agent claude` subprocess route is development acceptance evidence,
not the C-65 default product target. See `docs/AGENT_INTEGRATION_STATUS.md`
before describing runtime support.

For a Chinese user guide, read `docs/USER_GUIDE_CN.md`.

## 1. Product Environment

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -c "import openbox, hermes_workflow, lightgbm, shap, pyrfr; print('product optimizer env ok')"
```

Expected scripts:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

Do not use `.venv` as a product dependency.

Install runtime adapters as needed:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
./.venv/bin/hermes-workflow install-runtime-adapter opencode
./.venv/bin/hermes-workflow runtime-adapter-status
```

## 2. User Project Contract

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

## 3. Cadence Environment Anchor

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

Do not infer `.bashrc`/`.zshrc` automatically. Do not hardcode a Spectre
version in product docs or command examples.

## 4. Dry Orchestration Gate

Before a long real run on a new project, dry orchestration should pass:

```bash
./.venv/bin/ic-opt PROJECT_DIR \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

This should stop before `run-openbox-real`.

## 5. Real Product Acceptance

The real product route is:

```bash
./.venv/bin/ic-opt PROJECT_DIR \
  --real \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

Shell acceptance requires:

- `reports/optimizer_flow_run_report.json` has `status=pass`.
- `reports/optimizer_run_report.json` has `evaluation_count=max_evals`.
- `reports/optimizer_decision_report.md` recommends a feasible candidate when
  feasible evidence exists.
- OpenBox advanced visualization status is `generated` or explicitly recorded
  as unavailable with a reason.
- `global_optimum_claim=false`.

Runtime-native agent acceptance additionally requires:

- the runtime adapter is installed and visible to that CLI;
- the supervisor gate writes `execution_package/OPTIMIZER_EXECUTION_TASK.md`;
- the same-runtime execution subagent runs the approved task package;
- the supervisor runs closeout and reports the decision without asking the user
  to restate machine-critical information.

## 6. Final User Acceptance

The optimizer flow stops before final user acceptance. Only after the user
accepts the recommended best-observed candidate:

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

## 7. Files That Must Not Be Released

Do not commit or publish:

- raw `input.scs`;
- protected sidecars such as encrypted includes;
- PSF/raw simulator databases;
- full Cadence logs;
- user proprietary Maestro point-root bundles;
- `docs/OCEAN_DOC_*`;
- `docs/toolchain_evidence/` unless the user explicitly approves a sanitized
  evidence release.

## 8. GitHub Source Publication

Before pushing the source package to GitHub:

- confirm the target repository and visibility;
- keep the repository private while `LICENSE_NOT_SELECTED.md` is the only
  license file;
- run the sensitive-path scan from `docs/GITHUB_PUBLISH_GUIDE.md`;
- confirm `.gitignore` excludes generated optimizer project artifacts;
- keep `tests/` in the source repository for developer verification;
- do not include a repository-level `.venv`.

For the first publication procedure, see `docs/GITHUB_PUBLISH_GUIDE.md`.
