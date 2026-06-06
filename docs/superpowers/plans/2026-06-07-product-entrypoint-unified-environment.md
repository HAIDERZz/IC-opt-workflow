# C-58 Product Entrypoint And Unified Environment

## Status

Completed, verified-only.

## Goal

Turn the proven optimizer route into a product-shaped entrypoint for users who
are IC designers first and Python developers second.

The target user experience is:

```text
/ic-opt /path/to/project --real
```

or the shell-equivalent command:

```bash
ic-opt /path/to/project --real
```

The project directory remains data-only:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

There must not be a per-project Python virtualenv.

## Product Environment Decision

Use one product installation environment for `ic-auto-opt-workflow` and its
optimizer dependencies.

Acceptable release shapes:

- bundled repo with OpenBox and TuRBO vendored or submoduled under documented
  paths; or
- documented dependency install that builds one product virtualenv from the
  project's requirement files.

Unacceptable release shapes:

- relying on `/tmp/ic_auto_opt_openbox_spike/.venv`;
- requiring every user project to create its own Python virtualenv;
- requiring the user to provide long chat prompts to compensate for missing
  command behavior;
- hardcoding a Spectre version in product code or agent prompts.

The Cadence/Spectre/OCEAN environment remains user/project supplied through a
known shell setup path such as `--cadence-cshrc /path/to/user_env.csh`.

## Current Evidence

C-57 implemented:

```bash
hermes-workflow optimize PROJECT_DIR --real
```

and verified the one-command route in tests.

A real Mixer multi-testbench project copy also completed 100 evaluations with
the same route when invoked from the development OpenBox environment:

```text
/tmp/ic_auto_opt_optimize_real_jPaNVI/Mixer_opt_muti_tb
```

Result:

```text
evaluations=100
status_counts={"constraint_failed": 65, "feasible": 19, "metric_check_failed": 16}
recommended=real_066
parameters={"F": "26", "L": "40n", "VB_LO": "310m", "W": "1u"}
```

This exposed a product gap: the repo `.venv` entrypoint failed because OpenBox
was not installed there, while the development OpenBox venv succeeded. C-58
must remove that split before the project is considered product-shaped.

C-58 completion evidence:

- Added the product console entrypoint `ic-opt`.
- Added `requirements-product.txt` as the product-level dependency installer for
  this repo plus the local OpenBox checkout and visualization dependencies.
- Installed and verified the repo `.venv` can import `openbox`,
  `hermes_workflow`, `lightgbm`, `shap`, and `pyrfr`.
- Verified `ic-opt --help` exposes the product command shape:
  `ic-opt [OPTIONS] PROJECT_DIR`.
- Verified dry orchestration from the product entrypoint:
  `/tmp/ic_auto_opt_c58_dry_jCiZAA/Mixer_opt_muti_tb`, stopped before
  `run-openbox-real`.
- A sandboxed real-tool attempt at
  `/tmp/ic_auto_opt_c58_real_6Oz6Xf/Mixer_opt_muti_tb` failed because Spectre
  could not create pipe/server socket under sandbox restrictions. This is a
  tool-execution environment failure, not a product-flow failure.
- The unsandboxed product-entrypoint acceptance at
  `/tmp/ic_auto_opt_c58_real_unsandboxed_rj40MJ/Mixer_opt_muti_tb` completed 100
  real multi-testbench OpenBox/Spectre/OCEAN evaluations with the repo
  `.venv/bin/ic-opt`, passed all optimizer flow gates, and recommended feasible
  `real_066`.

Unsandboxed acceptance summary:

```text
evaluations=100
status_counts={"constraint_failed": 65, "feasible": 19, "metric_check_failed": 16}
recommended=real_066
parameters={"F": "26", "L": "40n", "VB_LO": "310m", "W": "1u"}
metrics={"BW": 19171311625.11458, "MAX_GAIN": 4.242801858394763, "NF_3G": 11.81241967045868, "IIP3": 3.206487765822459, "P1DB": -0.8997623115419788}
global_optimum_claim=false
advanced_visualization=generated
```

## Tasks

### Task 1: Product Dependency And Environment Contract

Status: Complete.

- Define the supported install command for one product virtualenv.
- Ensure the install includes the OpenBox backend dependencies used by the real
  route, including advanced visualization dependencies that are already proven.
- Keep TuRBO available as a supported backend dependency if the repo still
  exposes native TuRBO commands.
- Document the Cadence environment boundary separately from Python dependency
  installation.

Verification:

```bash
ic-opt --help
hermes-workflow optimize --help
python -c "import openbox; import hermes_workflow"
```

### Task 2: User-Facing Entrypoint

Status: Complete.

- Add `ic-opt` as the product-facing console command.
- Route `ic-opt PROJECT_DIR --real` to the existing `hermes-workflow optimize
  PROJECT_DIR --real` implementation.
- Keep `hermes-workflow` as the lower-level developer/admin command.
- Do not introduce a new workflow engine.

Verification:

```bash
ic-opt PROJECT_DIR --dry-orchestration --cadence-cshrc /path/to/user_env.csh
```

### Task 3: Agent Slash Command Contract

Status: Complete.

- Document `/ic-opt PROJECT_DIR --real` as the supervisor-agent-facing command
  form.
- The slash command may map to the shell command `ic-opt`; it should not be a
  long natural-language prompt.
- The supervisor agent should read the project files and report only failures
  or final results.

Verification:

```text
User sends one short command.
Supervisor does not ask for formulas, variables, or testbench paths already in
opt_requirement.md.
```

### Task 4: Real Product-Shape Acceptance

Status: Complete.

Run a fresh copy of the Mixer multi-testbench project with the product entrypoint
from the product virtualenv, not from `/tmp/ic_auto_opt_openbox_spike/.venv`.

Acceptance:

- `ic-opt PROJECT_DIR --real` reaches 100 evaluations.
- `check-optimizer-run` accepts the run.
- `optimizer_flow_run_report.json`, decision report, insight report,
  visualization artifacts, and readiness report are present.
- The result is reported as best observed, not global optimum.
- The command does not require a long user prompt.

## Non-Goals

- Do not change the optimizer algorithm.
- Do not replace OpenBox or re-litigate TuRBO.
- Do not add a generic natural-language parser.
- Do not parse PSF.
- Do not rewrite approved OCEAN formulas.
- Do not merge multiple testbenches into one synthetic deck.
- Do not create per-project virtualenvs.
