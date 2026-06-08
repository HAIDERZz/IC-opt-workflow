# Product Release Checklist

Use this checklist before treating `ic-auto-opt-workflow` as ready for another
user or another clean machine.

Important boundary: this checklist validates the implemented shell automation
core and platform-neutral agent skill assets. The implemented shell entrypoint is
`ic-opt PROJECT_DIR --real`; agent runtimes should load the platform-neutral
`skills/ic-opt/SKILL.md` and then use `/ic-opt PROJECT_DIR --real`. The current
agent operates the deterministic CLI and explains the reports. See
`docs/AGENT_OPTIMIZER_USAGE_MANUAL.md` before describing agent usage.

For a Chinese user guide, read `docs/USER_GUIDE_CN.md`.

## 1. Product Environment

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -c "import openbox, hermes_workflow; print('product optimizer env ok')"
```

Optional advanced OpenBox surrogate/importance visualization can be checked
separately with `requirements-advanced.txt`. Do not block the core product
release on `pyrfr`, `shap`, or `lightgbm`.

Expected scripts:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

Do not use `.venv` as a product dependency.

Confirm the agent-facing skill is present:

```bash
./.venv/bin/hermes-workflow agent-skill-path
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

Agent acceptance additionally requires:

- the platform-neutral skill is visible to the agent;
- the agent runs the product command rather than rebuilding lower-level steps;
- the agent reads closeout reports and explains the decision without asking the
  user to restate machine-critical information.

## 6. Remote Product Acceptance

Remote acceptance uses the same project contract, but the project directory and
Cadence setup live on the remote Linux EDA server:

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE /remote/path/to/project --doctor

./.venv/bin/ic-opt --ssh-profile PROFILE /remote/path/to/project \
  --real \
  --max-evals 80 \
  --batch-size 10 \
  --parallel-jobs 10

./.venv/bin/ic-opt --ssh-profile PROFILE /remote/path/to/project \
  --continue 20 \
  --batch-size 10 \
  --parallel-jobs 10
```

Remote acceptance requires:

- passwordless SSH passes with `ssh -o BatchMode=yes PROFILE true`;
- remote doctor passes;
- 80 real evaluations pass through remote Spectre/OCEAN;
- 20 continuation evaluations reach 100 cumulative evaluations;
- reports exist both under remote `PROJECT/reports/` and local
  `~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/`;
- remote Spectre/OCEAN diagnostics are present for successful and failed
  candidate paths.

## 7. Final User Acceptance

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

## 8. Files That Must Not Be Released

Do not commit or publish:

- raw `input.scs`;
- protected sidecars such as encrypted includes;
- PSF/raw simulator databases;
- full Cadence logs;
- user proprietary Maestro point-root bundles;
- `docs/OCEAN_DOC_*`;
- `docs/toolchain_evidence/` unless the user explicitly approves a sanitized
  evidence release.

## 9. GitHub Source Publication

Before pushing the source package to GitHub:

- confirm the target repository and visibility;
- confirm `LICENSE` is present and matches the intended release policy;
- run the sensitive-path scan from `docs/GITHUB_PUBLISH_GUIDE.md`;
- confirm `.gitignore` excludes generated optimizer project artifacts;
- keep `tests/` in the source repository for developer verification;
- do not include a repository-level `.venv`.

For the first publication procedure, see `docs/GITHUB_PUBLISH_GUIDE.md`.
